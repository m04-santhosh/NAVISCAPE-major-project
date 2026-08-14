"""
Traffic Collector & LSTM Service — NAVISCAPE Phase 8
Manages background traffic data collection, database persistence,
LSTM model training, and genuine LSTM prediction inference.
"""

import os
import time
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session

from ..config import settings
from ..database import SessionLocal
from ..models.traffic import TrafficData, TrafficHourly
from .traffic_intelligence import MONITORED_JUNCTIONS, _fetch_tomtom_flow_point, MAX_VEHICLE_COUNT, HOUR_PATTERNS

logger = logging.getLogger(__name__)


def compute_congestion_level(speed_ratio: Optional[float]) -> str:
    """
    Computes standard congestion level string from speed_ratio using NAVISCAPE documented thresholds:
    - speed_ratio < 0.4: 'critical'
    - speed_ratio < 0.7: 'high'
    - speed_ratio < 0.9: 'medium'
    - speed_ratio >= 0.9 (or default): 'low'
    """
    if speed_ratio is None:
        return "low"
    if speed_ratio < 0.4:
        return "critical"
    if speed_ratio < 0.7:
        return "high"
    if speed_ratio < 0.9:
        return "medium"
    return "low"


async def fetch_and_store_junction_traffic(
    db: Session,
    is_test: bool = False,
    override_now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Fetches real TomTom traffic flow data for all 8 monitored junctions and stores
    the observations safely in the database.
    
    Guarantees:
    - Concurrently attempts all 8 junctions using asyncio.gather.
    - Handles single or multiple junction API failures safely without aborting others.
    - Accurately computes and stores congestion_level from real speed_ratio.
    - Skips duplicate observations at the minute level.
    - Rolls back SQLAlchemy session on commit/database errors and logs diagnostics.
    - Never fabricates synthetic observations for missing/failed junction probes.
    - Returns detailed collection summary metrics.
    """
    api_key = settings.TOMTOM_API_KEY
    if not api_key:
        logger.warning("TomTom API key not configured. Cannot collect traffic observations.")
        return {
            "successful_junctions": 0,
            "failed_junctions": len(MONITORED_JUNCTIONS),
            "records_inserted": 0,
            "duplicates_skipped": 0,
            "stored_count": 0,
            "status": "error",
            "message": "TomTom API key not configured.",
        }

    now = override_now or datetime.now()
    minute_ts = now.replace(second=0, microsecond=0)

    # Fetch helper for a single junction with exception isolation
    async def _fetch_single(junc: Dict[str, Any]) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]], Optional[Exception]]:
        try:
            flow = await _fetch_tomtom_flow_point(junc["lat"], junc["lng"], api_key)
            return junc, flow, None
        except Exception as exc:
            logger.warning(f"Error collecting traffic for junction {junc.get('id')} ({junc.get('name')}): {exc}")
            return junc, None, exc

    # Gather all 8 junction requests concurrently
    tasks = [_fetch_single(junc) for junc in MONITORED_JUNCTIONS]
    results = await asyncio.gather(*tasks, return_exceptions=False)

    successful_count = 0
    failed_count = 0
    records_inserted = 0
    duplicates_skipped = 0

    try:
        for junc, flow, exc in results:
            if flow is not None and exc is None:
                successful_count += 1
                # Check if an observation for this junction already exists at this exact minute
                exists = db.query(TrafficData).filter(
                    TrafficData.junction_id == junc["id"],
                    TrafficData.timestamp == minute_ts
                ).first()

                if not exists:
                    speed_ratio = flow.get("speed_ratio")
                    congestion = compute_congestion_level(speed_ratio)
                    obs = TrafficData(
                        junction_id=junc["id"],
                        latitude=junc["lat"],
                        longitude=junc["lng"],
                        timestamp=minute_ts,
                        vehicle_count=0,
                        avg_speed=flow.get("current_speed_kmh"),
                        free_flow_speed=flow.get("free_flow_speed_kmh"),
                        speed_ratio=speed_ratio,
                        congestion_level=congestion,
                        day_of_week=minute_ts.weekday(),
                        hour_of_day=minute_ts.hour,
                        is_test=is_test
                    )
                    db.add(obs)
                    records_inserted += 1
                else:
                    duplicates_skipped += 1
                    logger.debug(f"Observation for junction {junc['id']} at {minute_ts} already exists. Skipping duplicate.")
            else:
                failed_count += 1
                logger.warning(
                    f"Failed to fetch TomTom flow for junction {junc.get('id')} ({junc.get('name')}). "
                    f"Skipping observation without fabricating data."
                )

        if records_inserted > 0:
            db.commit()
            logger.info(
                f"Stored {records_inserted} real TomTom traffic observations at {minute_ts} "
                f"(Success: {successful_count}, Failed: {failed_count}, Duplicates skipped: {duplicates_skipped})"
            )
        elif successful_count > 0 and duplicates_skipped > 0:
            logger.info(f"Traffic collection cycle completed for {minute_ts}: {duplicates_skipped} duplicates skipped.")

        return {
            "successful_junctions": successful_count,
            "failed_junctions": failed_count,
            "records_inserted": records_inserted,
            "duplicates_skipped": duplicates_skipped,
            "stored_count": records_inserted,
            "status": "success",
        }

    except Exception as db_exc:
        db.rollback()
        logger.exception(f"Database error while saving traffic observations for timestamp {minute_ts}: {db_exc}")
        return {
            "successful_junctions": successful_count,
            "failed_junctions": failed_count,
            "records_inserted": 0,
            "duplicates_skipped": duplicates_skipped,
            "stored_count": 0,
            "status": "db_error",
            "error": str(db_exc),
        }


async def traffic_collector_loop(stop_event: Optional[asyncio.Event] = None):
    """
    Background loop that collects TomTom traffic data on anchored 5-minute intervals.
    Targets regular 5-minute clock boundaries (:00, :05, :10, :15...) to avoid drift.
    Handles clean cancellation and session finalization during shutdown.
    """
    logger.info("Starting anchored 5-minute TomTom traffic collection background service...")
    try:
        while True:
            if stop_event and stop_event.is_set():
                logger.info("Traffic collector received stop signal. Exiting loop.")
                break

            # Execute collection cycle
            db = SessionLocal()
            try:
                summary = await fetch_and_store_junction_traffic(db)
                logger.info(
                    f"Traffic collection cycle finished: {summary.get('records_inserted', 0)} inserted, "
                    f"{summary.get('duplicates_skipped', 0)} skipped, "
                    f"{summary.get('successful_junctions', 0)} succeeded, "
                    f"{summary.get('failed_junctions', 0)} failed."
                )
            except Exception as e:
                logger.exception("Unexpected error in traffic collector background service loop:")
            finally:
                db.close()

            # Anchored 5-minute schedule calculation:
            # Targets the next 5-minute boundary (:00, :05, :10, etc.)
            now_ts = time.time()
            interval = 300.0  # 5 minutes
            next_tick = (now_ts // interval + 1) * interval
            sleep_duration = max(0.1, next_tick - time.time())

            if stop_event:
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=sleep_duration)
                    break
                except asyncio.TimeoutError:
                    pass
            else:
                await asyncio.sleep(sleep_duration)

    except asyncio.CancelledError:
        logger.info("TomTom traffic collector background task received cancellation. Shutting down cleanly.")
        raise


def classify_data_quality(sample_count: int) -> str:
    """
    Classifies the hourly observation completeness based on 12 target 5-min samples/hour:
    - sample_count >= 10 (>= 83% coverage): 'COMPLETE'
    - 4 <= sample_count < 10 (33% - 75% coverage): 'PARTIAL'
    - 1 <= sample_count < 4 (< 33% coverage): 'LOW_COVERAGE'
    """
    if sample_count >= 10:
        return "COMPLETE"
    elif sample_count >= 4:
        return "PARTIAL"
    else:
        return "LOW_COVERAGE"


def aggregate_5min_to_hourly(
    db: Session,
    junction_id: int = 1,
    is_test: bool = False
) -> List[Dict[str, Any]]:
    """
    Aggregates raw 5-minute TomTom observations into a clean hourly time series
    for the specified junction.
    
    Computes mean speed_ratio, mean avg_speed, sample_count, and data_quality per 1-hour bucket.
    Returns a chronologically sorted list of dicts.
    Never fabricates missing observations.
    """
    records = (
        db.query(TrafficData)
        .filter(
            TrafficData.junction_id == junction_id,
            TrafficData.is_test == is_test,
            TrafficData.speed_ratio != None
        )
        .order_by(TrafficData.timestamp.asc())
        .all()
    )

    if not records:
        return []

    hourly_buckets: Dict[datetime, List[TrafficData]] = {}
    for r in records:
        if not r.timestamp:
            continue
        hour_bucket = r.timestamp.replace(minute=0, second=0, microsecond=0)
        if hour_bucket not in hourly_buckets:
            hourly_buckets[hour_bucket] = []
        hourly_buckets[hour_bucket].append(r)

    series = []
    for dt_bucket in sorted(hourly_buckets.keys()):
        bucket_obs = hourly_buckets[dt_bucket]
        mean_ratio = sum(float(o.speed_ratio) for o in bucket_obs if o.speed_ratio is not None) / len(bucket_obs)
        valid_speeds = [float(o.avg_speed) for o in bucket_obs if o.avg_speed is not None]
        mean_speed = sum(valid_speeds) / len(valid_speeds) if valid_speeds else None
        sample_count = len(bucket_obs)
        quality = classify_data_quality(sample_count)

        series.append({
            "timestamp": dt_bucket,
            "speed_ratio": round(mean_ratio, 4),
            "avg_speed": round(mean_speed, 1) if mean_speed is not None else None,
            "hour_of_day": dt_bucket.hour,
            "day_of_week": dt_bucket.weekday(),
            "sample_count": sample_count,
            "data_quality": quality
        })

    return series


def materialize_hourly_traffic(
    db: Session,
    junction_id: Optional[int] = None,
    is_test: bool = False
) -> Dict[str, Any]:
    """
    Deterministically materializes and updates hourly historical traffic dataset (TrafficHourly)
    from raw 5-minute TrafficData records.
    
    Guarantees:
    - Idempotent upsert: Safe to run repeatedly without creating duplicates.
    - Strictly isolates is_test=False (production) and is_test=True (test).
    - Preserves all raw TrafficData observations intact.
    - Accurately classifies data_quality ('COMPLETE', 'PARTIAL', 'LOW_COVERAGE').
    - Never fabricates synthetic values for missing hours.
    """
    query = db.query(TrafficData).filter(
        TrafficData.is_test == is_test,
        TrafficData.speed_ratio != None
    )
    if junction_id is not None:
        query = query.filter(TrafficData.junction_id == junction_id)

    raw_records = query.order_by(TrafficData.timestamp.asc()).all()
    if not raw_records:
        return {
            "status": "success",
            "hourly_records_processed": 0,
            "created": 0,
            "updated": 0,
            "is_test": is_test,
            "quality_breakdown": {"COMPLETE": 0, "PARTIAL": 0, "LOW_COVERAGE": 0},
            "message": "No raw observations found to materialize."
        }

    # Group by (junction_id, hour_bucket)
    buckets: Dict[Tuple[int, datetime], List[TrafficData]] = {}
    for r in raw_records:
        if not r.timestamp:
            continue
        hour_bucket = r.timestamp.replace(minute=0, second=0, microsecond=0)
        key = (r.junction_id, hour_bucket)
        if key not in buckets:
            buckets[key] = []
        buckets[key].append(r)

    created_count = 0
    updated_count = 0
    quality_counts = {"COMPLETE": 0, "PARTIAL": 0, "LOW_COVERAGE": 0}

    try:
        for (jid, dt_bucket), bucket_obs in sorted(buckets.items()):
            mean_ratio = sum(float(o.speed_ratio) for o in bucket_obs if o.speed_ratio is not None) / len(bucket_obs)
            valid_speeds = [float(o.avg_speed) for o in bucket_obs if o.avg_speed is not None]
            mean_speed = sum(valid_speeds) / len(valid_speeds) if valid_speeds else None
            sample_count = len(bucket_obs)
            quality = classify_data_quality(sample_count)
            quality_counts[quality] = quality_counts.get(quality, 0) + 1

            # Check if hourly record already exists
            existing = db.query(TrafficHourly).filter(
                TrafficHourly.junction_id == jid,
                TrafficHourly.timestamp == dt_bucket,
                TrafficHourly.is_test == is_test
            ).first()

            if existing:
                existing.avg_speed = round(mean_speed, 2) if mean_speed is not None else None
                existing.speed_ratio = round(mean_ratio, 4)
                existing.avg_confidence = 1.0
                existing.sample_count = sample_count
                existing.data_quality = quality
                updated_count += 1
            else:
                hourly_rec = TrafficHourly(
                    junction_id=jid,
                    timestamp=dt_bucket,
                    avg_speed=round(mean_speed, 2) if mean_speed is not None else None,
                    speed_ratio=round(mean_ratio, 4),
                    avg_confidence=1.0,
                    sample_count=sample_count,
                    data_quality=quality,
                    is_test=is_test
                )
                db.add(hourly_rec)
                created_count += 1

        db.commit()
        logger.info(
            f"Hourly traffic materialization complete (is_test={is_test}): "
            f"{created_count} created, {updated_count} updated. Quality: {quality_counts}"
        )
        return {
            "status": "success",
            "hourly_records_processed": len(buckets),
            "created": created_count,
            "updated": updated_count,
            "is_test": is_test,
            "quality_breakdown": quality_counts,
        }
    except Exception as exc:
        db.rollback()
        logger.exception(f"Error during hourly traffic materialization: {exc}")
        return {
            "status": "error",
            "error": str(exc),
            "created": 0,
            "updated": 0,
            "is_test": is_test,
        }


def get_hourly_traffic_summary(db: Session, is_test: bool = False) -> Dict[str, Any]:
    """
    Read-only query service reporting hourly historical dataset statistics:
    - total hourly records
    - records per junction
    - earliest/latest hourly timestamps
    - data quality breakdown
    - raw observation preservation verification
    """
    hourly_records = (
        db.query(TrafficHourly)
        .filter(TrafficHourly.is_test == is_test)
        .order_by(TrafficHourly.timestamp.asc())
        .all()
    )
    raw_count = db.query(TrafficData).filter(TrafficData.is_test == is_test).count()

    total_records = len(hourly_records)
    junction_counts = {}
    for jid in range(1, 9):
        junction_counts[jid] = sum(1 for h in hourly_records if h.junction_id == jid)

    earliest = hourly_records[0].timestamp.isoformat() if hourly_records else None
    latest = hourly_records[-1].timestamp.isoformat() if hourly_records else None

    quality_breakdown = {"COMPLETE": 0, "PARTIAL": 0, "LOW_COVERAGE": 0}
    for h in hourly_records:
        q = h.data_quality
        quality_breakdown[q] = quality_breakdown.get(q, 0) + 1

    return {
        "is_test": is_test,
        "total_hourly_records": total_records,
        "raw_observations_count": raw_count,
        "junction_counts": junction_counts,
        "earliest_timestamp": earliest,
        "latest_timestamp": latest,
        "quality_breakdown": quality_breakdown,
    }


def get_traffic_data_quality(
    db: Session,
    junction_id: int,
    is_test: bool = False
) -> Dict[str, Any]:
    """
    Read-only historical traffic quality and coverage analysis for a single junction.

    Computes:
    - Raw observation count
    - Hourly record count with COMPLETE/PARTIAL/LOW_COVERAGE breakdown
    - Expected hourly buckets (inclusive range between earliest & latest hourly timestamp)
    - Missing hourly buckets
    - Coverage percentage and complete-coverage percentage
    - Longest continuous hourly sequence (from actual timestamp gaps, not record count)
    - Longest continuous COMPLETE-quality hourly sequence
    - Earliest/latest raw and hourly timestamps
    - Data readiness status (NOT LSTM readiness — see Phase 13.3 spec)

    Guarantees:
    - Never creates, modifies, or deletes any database records.
    - Handles junctions with zero data safely (no division-by-zero).
    - Does not fabricate expected time ranges when no observations exist.
    """
    # --- Raw observation metrics ---
    raw_count = db.query(TrafficData).filter(
        TrafficData.junction_id == junction_id,
        TrafficData.is_test == is_test,
    ).count()

    from sqlalchemy import func as sa_func
    earliest_raw = db.query(sa_func.min(TrafficData.timestamp)).filter(
        TrafficData.junction_id == junction_id,
        TrafficData.is_test == is_test,
    ).scalar()
    latest_raw = db.query(sa_func.max(TrafficData.timestamp)).filter(
        TrafficData.junction_id == junction_id,
        TrafficData.is_test == is_test,
    ).scalar()

    # --- Hourly record metrics ---
    hourly_records = (
        db.query(TrafficHourly)
        .filter(
            TrafficHourly.junction_id == junction_id,
            TrafficHourly.is_test == is_test,
        )
        .order_by(TrafficHourly.timestamp.asc())
        .all()
    )

    hourly_count = len(hourly_records)

    # Quality breakdown
    complete_hours = sum(1 for h in hourly_records if h.data_quality == "COMPLETE")
    partial_hours = sum(1 for h in hourly_records if h.data_quality == "PARTIAL")
    low_coverage_hours = sum(1 for h in hourly_records if h.data_quality == "LOW_COVERAGE")

    # --- Handle zero-data junction safely ---
    if hourly_count == 0:
        return {
            "junction_id": junction_id,
            "raw_observations": raw_count,
            "hourly_observations": 0,
            "complete_hours": 0,
            "partial_hours": 0,
            "low_coverage_hours": 0,
            "expected_hours": 0,
            "missing_hours": 0,
            "coverage_percentage": 0.0,
            "complete_coverage_percentage": 0.0,
            "longest_continuous_hours": 0,
            "longest_complete_continuous_hours": 0,
            "earliest_timestamp": earliest_raw.isoformat() if earliest_raw else None,
            "latest_timestamp": latest_raw.isoformat() if latest_raw else None,
            "earliest_hourly_timestamp": None,
            "latest_hourly_timestamp": None,
            "data_readiness": "insufficient_data",
        }

    earliest_hourly = hourly_records[0].timestamp
    latest_hourly = hourly_records[-1].timestamp

    # Expected hours = inclusive range between earliest and latest hourly timestamp
    total_span_seconds = (latest_hourly - earliest_hourly).total_seconds()
    expected_hours = int(total_span_seconds / 3600) + 1  # +1 for inclusive

    # Missing hours
    missing_hours = expected_hours - hourly_count

    # Coverage percentages (safe: expected_hours >= 1 here since hourly_count >= 1)
    coverage_percentage = round((hourly_count / expected_hours) * 100, 2)
    complete_coverage_percentage = round((complete_hours / expected_hours) * 100, 2)

    # --- Longest continuous sequence from actual timestamps ---
    # Sort timestamps and check for exactly 1-hour gaps
    timestamps_sorted = sorted([h.timestamp for h in hourly_records])

    longest_continuous = 1
    current_run = 1
    for i in range(1, len(timestamps_sorted)):
        delta = (timestamps_sorted[i] - timestamps_sorted[i - 1]).total_seconds()
        if delta == 3600:  # exactly 1 hour
            current_run += 1
            if current_run > longest_continuous:
                longest_continuous = current_run
        else:
            current_run = 1

    # --- Longest continuous COMPLETE-quality sequence from actual timestamps ---
    complete_records = sorted(
        [h for h in hourly_records if h.data_quality == "COMPLETE"],
        key=lambda h: h.timestamp
    )
    longest_complete_continuous = 0
    if complete_records:
        longest_complete_continuous = 1
        current_complete_run = 1
        for i in range(1, len(complete_records)):
            delta = (complete_records[i].timestamp - complete_records[i - 1].timestamp).total_seconds()
            if delta == 3600:  # exactly 1 hour
                current_complete_run += 1
                if current_complete_run > longest_complete_continuous:
                    longest_complete_continuous = current_complete_run
            else:
                current_complete_run = 1

    # --- Data readiness classification ---
    # NOTE: This is historical data coverage readiness ONLY.
    # It does NOT indicate LSTM readiness, production model readiness,
    # sufficient training data, or prediction availability.
    # The LSTM pipeline uses its own independent training/readiness requirements.
    if hourly_count < 24 or coverage_percentage < 25.0:
        data_readiness = "insufficient_data"
    elif hourly_count < 120 or coverage_percentage <= 75.0:
        data_readiness = "partial_data"
    elif longest_continuous >= 24:
        data_readiness = "historically_ready"
    else:
        # 120+ hours and >75% coverage but no 24-hour continuous run
        data_readiness = "partial_data"

    return {
        "junction_id": junction_id,
        "raw_observations": raw_count,
        "hourly_observations": hourly_count,
        "complete_hours": complete_hours,
        "partial_hours": partial_hours,
        "low_coverage_hours": low_coverage_hours,
        "expected_hours": expected_hours,
        "missing_hours": missing_hours,
        "coverage_percentage": coverage_percentage,
        "complete_coverage_percentage": complete_coverage_percentage,
        "longest_continuous_hours": longest_continuous,
        "longest_complete_continuous_hours": longest_complete_continuous,
        "earliest_timestamp": earliest_raw.isoformat() if earliest_raw else None,
        "latest_timestamp": latest_raw.isoformat() if latest_raw else None,
        "earliest_hourly_timestamp": earliest_hourly.isoformat(),
        "latest_hourly_timestamp": latest_hourly.isoformat(),
        "data_readiness": data_readiness,
    }


def get_traffic_coverage_summary(
    db: Session,
    is_test: bool = False
) -> Dict[str, Any]:
    """
    Read-only cross-junction historical traffic coverage summary.

    Aggregates get_traffic_data_quality() for all 8 production junctions (IDs 1-8).
    Overall coverage is weighted by actual expected hourly buckets, NOT averaged.

    Guarantees:
    - Never creates, modifies, or deletes any database records.
    - If total_expected_hours == 0, returns 0 for both coverage percentages.
    - data_readiness per junction is historical coverage readiness ONLY (not LSTM readiness).
    """
    junction_reports = []
    total_raw = 0
    total_hourly = 0
    total_expected = 0
    total_complete = 0
    total_missing = 0
    readiness_counts = {"insufficient_data": 0, "partial_data": 0, "historically_ready": 0}

    for jid in range(1, 9):
        report = get_traffic_data_quality(db, junction_id=jid, is_test=is_test)
        junction_reports.append(report)
        total_raw += report["raw_observations"]
        total_hourly += report["hourly_observations"]
        total_expected += report["expected_hours"]
        total_complete += report["complete_hours"]
        total_missing += report["missing_hours"]
        readiness_counts[report["data_readiness"]] = readiness_counts.get(report["data_readiness"], 0) + 1

    # Weighted overall coverage (NOT averaged across junctions)
    if total_expected > 0:
        overall_coverage = round((total_hourly / total_expected) * 100, 2)
        overall_complete_coverage = round((total_complete / total_expected) * 100, 2)
    else:
        overall_coverage = 0.0
        overall_complete_coverage = 0.0

    return {
        "is_test": is_test,
        "total_raw_observations": total_raw,
        "total_hourly_observations": total_hourly,
        "total_expected_hours": total_expected,
        "total_missing_hours": total_missing,
        "overall_coverage_percentage": overall_coverage,
        "overall_complete_coverage_percentage": overall_complete_coverage,
        "junctions_ready": readiness_counts.get("historically_ready", 0),
        "junctions_partial": readiness_counts.get("partial_data", 0),
        "junctions_insufficient": readiness_counts.get("insufficient_data", 0),
        "junctions": junction_reports,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Phase 14: Production LSTM Model Training, Health & Inference
# ─────────────────────────────────────────────────────────────────────────────

MODEL_MAX_AGE_HOURS = 168  # 7 days before model is classified as stale


def _get_lstm_artifact_paths(junction_id: int = 1, is_test: bool = False) -> Dict[str, str]:
    """
    Returns isolated artifact paths for production vs test models.
    Production: ml/models/production/
    Test: ml/models/test/
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    sub_dir = "test" if is_test else "production"
    ml_dir = os.path.join(base_dir, "ml", "models", sub_dir)
    os.makedirs(ml_dir, exist_ok=True)

    tag = "test" if is_test else "prod"
    return {
        "dir": ml_dir,
        "model": os.path.join(ml_dir, f"traffic_lstm_{tag}_j{junction_id}.h5"),
        "scaler": os.path.join(ml_dir, f"traffic_scaler_{tag}_j{junction_id}.pkl"),
        "meta": os.path.join(ml_dir, f"traffic_lstm_meta_{tag}_j{junction_id}.json"),
    }


def train_lstm_from_db(
    db: Session,
    junction_id: int = 1,
    is_test: bool = False
) -> Dict[str, Any]:
    """
    Phase 14 Production Training Pipeline:
    1. Evaluates per-junction Phase 13.3 readiness gate (requires historically_ready: >=120 hrs, >75% coverage, >=24 continuous).
    2. Uses ONLY verified TrafficHourly records (is_test=False for prod, is_test=True for test).
    3. Builds training sequences strictly from continuous 24-hour timestamps (never skips gaps).
    4. Trains LSTM model and saves artifacts to isolated directory (production/ vs test/).
    5. Validates model reload and inference before declaring success.
    """
    # ── 1. Phase 13.3 Readiness Gate (Per-Junction) ─────────────────────────
    quality = get_traffic_data_quality(db, junction_id=junction_id, is_test=is_test)

    # In production (is_test=False), strictly require historically_ready status
    if not is_test:
        is_ready = (
            quality["hourly_observations"] >= 120
            and quality["coverage_percentage"] > 75.0
            and quality["longest_continuous_hours"] >= 24
            and quality["data_readiness"] == "historically_ready"
        )
        if not is_ready:
            return {
                "trained": False,
                "status": "insufficient_real_data",
                "reason": (
                    f"Production LSTM training requires historically_ready real hourly traffic data for junction {junction_id}. "
                    f"Current: {quality['hourly_observations']}/120 hourly records, "
                    f"{quality['coverage_percentage']}% coverage, "
                    f"{quality['longest_continuous_hours']}/24 longest continuous sequence."
                ),
                "junction_id": junction_id,
                "hourly_observation_count": quality["hourly_observations"],
                "coverage_percentage": quality["coverage_percentage"],
                "longest_continuous_hours": quality["longest_continuous_hours"],
                "required_hourly_observations": 120,
            }

    # ── 2. Query Verified TrafficHourly Dataset ─────────────────────────────
    hourly_records = (
        db.query(TrafficHourly)
        .filter(
            TrafficHourly.junction_id == junction_id,
            TrafficHourly.is_test == is_test,
            TrafficHourly.speed_ratio != None,
        )
        .order_by(TrafficHourly.timestamp.asc())
        .all()
    )

    if len(hourly_records) < 25:
        return {
            "trained": False,
            "status": "insufficient_sequence_length",
            "reason": f"Insufficient hourly records ({len(hourly_records)} < 25) to build a continuous sequence.",
            "junction_id": junction_id,
            "hourly_observation_count": len(hourly_records),
        }

    # ── 3. Build Sequences Enforcing Timestamp Continuity ────────────────────
    WINDOW_SIZE = 24
    X_raw, y_raw = [], []

    for i in range(len(hourly_records) - WINDOW_SIZE):
        window = hourly_records[i : i + WINDOW_SIZE]
        target = hourly_records[i + WINDOW_SIZE]

        # Verify strict 1-hour continuity throughout the window
        is_continuous = True
        for k in range(1, len(window)):
            delta = (window[k].timestamp - window[k - 1].timestamp).total_seconds()
            if delta != 3600:
                is_continuous = False
                break

        # Verify target is exactly 1 hour after window end
        if is_continuous:
            target_delta = (target.timestamp - window[-1].timestamp).total_seconds()
            if target_delta != 3600:
                is_continuous = False

        if is_continuous:
            X_raw.append([float(h.speed_ratio) for h in window])
            y_raw.append(float(target.speed_ratio))

    if len(X_raw) < 5:
        return {
            "trained": False,
            "status": "insufficient_continuous_sequences",
            "reason": f"Insufficient continuous 24-hour sequences found ({len(X_raw)} < 5). Real timestamp continuity is required.",
            "junction_id": junction_id,
            "hourly_observation_count": len(hourly_records),
        }

    import numpy as np
    import joblib
    import json
    from sklearn.preprocessing import MinMaxScaler

    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
    from tensorflow.keras.models import Sequential, load_model
    from tensorflow.keras.layers import LSTM, Dense, Dropout, Input

    # ── 4. Scale Data ────────────────────────────────────────────────────────
    X_arr = np.array(X_raw, dtype="float32")  # shape: (N, 24)
    y_arr = np.array(y_raw, dtype="float32").reshape(-1, 1)  # shape: (N, 1)

    scaler = MinMaxScaler(feature_range=(0, 1))
    all_values = np.concatenate([X_arr.flatten(), y_arr.flatten()]).reshape(-1, 1)
    scaler.fit(all_values)

    X_scaled = scaler.transform(X_arr.reshape(-1, 1)).reshape(len(X_arr), WINDOW_SIZE, 1)
    y_scaled = scaler.transform(y_arr)

    # Train / Validation split (80/20)
    split = max(1, int(len(X_scaled) * 0.8))
    X_train, X_val = X_scaled[:split], X_scaled[split:]
    y_train, y_val = y_scaled[:split], y_scaled[split:]

    if len(X_val) == 0:
        X_val, y_val = X_train, y_train

    # ── 5. Build and Train LSTM Model ───────────────────────────────────────
    model = Sequential([
        Input(shape=(WINDOW_SIZE, 1)),
        LSTM(64, return_sequences=True),
        Dropout(0.2),
        LSTM(32, return_sequences=False),
        Dropout(0.2),
        Dense(16, activation='relu'),
        Dense(1),
    ])
    model.compile(optimizer='adam', loss='mse', metrics=['mae'])

    history = model.fit(
        X_train, y_train,
        epochs=20,
        batch_size=min(32, len(X_train)),
        validation_data=(X_val, y_val),
        verbose=0,
    )

    val_loss = float(history.history['val_loss'][-1]) if 'val_loss' in history.history else None
    val_mae = float(history.history['val_mae'][-1]) if 'val_mae' in history.history else None

    # ── 6. Save Model Artifacts to Isolated Directory ────────────────────────
    paths = _get_lstm_artifact_paths(junction_id=junction_id, is_test=is_test)

    model.save(paths["model"])
    joblib.dump(scaler, paths["scaler"])

    trained_time = datetime.now()
    metadata = {
        "model_version": "1.0.0",
        "trained_at": trained_time.isoformat(),
        "is_test": is_test,
        "junction_id": junction_id,
        "training_data_source": "TrafficHourly",
        "raw_observation_count": quality["raw_observations"],
        "hourly_observation_count": len(hourly_records),
        "complete_hour_count": quality["complete_hours"],
        "coverage_percentage": quality["coverage_percentage"],
        "longest_continuous_hours": quality["longest_continuous_hours"],
        "continuous_sequences_used": len(X_raw),
        "sequence_length": WINDOW_SIZE,
        "feature_columns": ["speed_ratio"],
        "scaling_method": "MinMaxScaler(0, 1)",
        "train_split_ratio": 0.8,
        "validation_loss_mse": val_loss,
        "validation_mae": val_mae,
        "model_status": "trained_and_available",
    }
    with open(paths["meta"], "w") as f:
        json.dump(metadata, f, indent=2)

    # ── 7. Post-Serialization Model Validation ───────────────────────────────
    try:
        loaded_model = load_model(paths["model"], compile=False)
        loaded_scaler = joblib.load(paths["scaler"])

        sample_input = X_val[0:1]
        test_pred_scaled = loaded_model.predict(sample_input, verbose=0)
        test_pred_val = float(loaded_scaler.inverse_transform(test_pred_scaled)[0][0])

        if not np.isfinite(test_pred_val) or test_pred_val < 0.0 or test_pred_val > 1.0:
            logger.error(f"Post-training validation failed: invalid prediction value {test_pred_val}")
            metadata["model_status"] = "model_validation_failure"
            with open(paths["meta"], "w") as f:
                json.dump(metadata, f, indent=2)
            return {
                "trained": False,
                "status": "model_validation_failure",
                "reason": f"Model validation failed: test inference value {test_pred_val} out of bounds.",
                "junction_id": junction_id,
            }
    except Exception as e:
        logger.exception(f"Post-training model reload error for junction {junction_id}: {e}")
        return {
            "trained": False,
            "status": "model_load_failure",
            "reason": f"Model failed to reload after serialization: {e}",
            "junction_id": junction_id,
        }

    # Reset lazy loader
    from . import traffic_intelligence
    traffic_intelligence._lstm_loaded = False
    traffic_intelligence._lstm_model = None
    traffic_intelligence._lstm_scaler = None

    return {
        "trained": True,
        "status": "trained_and_available",
        "message": f"Successfully trained and validated LSTM traffic model for junction {junction_id} on {len(hourly_records)} real hourly records ({len(X_raw)} continuous sequences).",
        "junction_id": junction_id,
        "hourly_observation_count": len(hourly_records),
        "continuous_sequences_count": len(X_raw),
        "metadata": metadata,
    }


def get_lstm_model_status(
    db: Session,
    junction_id: int = 1,
    use_test_model: bool = False
) -> Dict[str, Any]:
    """
    Returns comprehensive model health and availability status for the junction without exposing
    absolute filesystem paths or credentials.
    """
    paths = _get_lstm_artifact_paths(junction_id=junction_id, is_test=use_test_model)

    model_exists = os.path.exists(paths["model"])
    scaler_exists = os.path.exists(paths["scaler"])
    meta_exists = os.path.exists(paths["meta"])

    quality = get_traffic_data_quality(db, junction_id=junction_id, is_test=use_test_model)

    metadata = None
    if meta_exists:
        try:
            import json
            with open(paths["meta"], "r") as f:
                metadata = json.load(f)
        except Exception:
            pass

    # Model health evaluation
    if model_exists and scaler_exists and metadata:
        # Check staleness
        trained_at_str = metadata.get("trained_at")
        is_stale = False
        if trained_at_str:
            try:
                trained_dt = datetime.fromisoformat(trained_at_str)
                age_hours = (datetime.now() - trained_dt).total_seconds() / 3600.0
                if age_hours > MODEL_MAX_AGE_HOURS:
                    is_stale = True
            except Exception:
                pass

        if is_stale:
            status = "stale_model"
            prediction_available = False
        else:
            status = metadata.get("model_status", "trained_and_available")
            prediction_available = (status == "trained_and_available")
    elif not quality.get("data_readiness") == "historically_ready":
        status = "insufficient_real_data"
        prediction_available = False
    else:
        status = "not_trained"
        prediction_available = False

    return {
        "status": status,
        "prediction_available": prediction_available,
        "junction_id": junction_id,
        "is_test": use_test_model,
        "model_trained": model_exists and scaler_exists,
        "raw_observation_count": quality["raw_observations"],
        "hourly_observation_count": quality["hourly_observations"],
        "complete_hour_count": quality["complete_hours"],
        "coverage_percentage": quality["coverage_percentage"],
        "longest_continuous_hours": quality["longest_continuous_hours"],
        "required_hourly_observations": 120,
        "validation_loss_mse": metadata.get("validation_loss_mse") if metadata else None,
        "validation_mae": metadata.get("validation_mae") if metadata else None,
        "trained_at": metadata.get("trained_at") if metadata else None,
        "model_version": metadata.get("model_version") if metadata else None,
    }


def predict_traffic_lstm(
    db: Session,
    junction_id: int = 1,
    hours_ahead: int = 1,
    use_test_model: bool = False
) -> Optional[List[dict]]:
    """
    Performs genuine LSTM traffic forecasting for a junction:
    - Verifies model health and un-stale status.
    - Requires strictly continuous 24-hour historical TrafficHourly sequence.
    - Forecasts next-hour speed_ratio using persisted scaler.
    - Never fabricates missing input observations or half-hour targets.
    """
    # 1. Check Model Health
    status_info = get_lstm_model_status(db, junction_id=junction_id, use_test_model=use_test_model)
    if not status_info["prediction_available"]:
        return None

    paths = _get_lstm_artifact_paths(junction_id=junction_id, is_test=use_test_model)

    try:
        import joblib
        import numpy as np
        os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
        from tensorflow.keras.models import load_model
        model = load_model(paths["model"], compile=False)
        scaler = joblib.load(paths["scaler"])
    except Exception as e:
        logger.warning(f"Failed to load LSTM model for junction {junction_id}: {e}")
        return None

    # 2. Fetch latest 24 TrafficHourly records
    hourly_records = (
        db.query(TrafficHourly)
        .filter(
            TrafficHourly.junction_id == junction_id,
            TrafficHourly.is_test == use_test_model,
            TrafficHourly.speed_ratio != None,
        )
        .order_by(TrafficHourly.timestamp.desc())
        .limit(24)
        .all()
    )

    if len(hourly_records) < 24:
        logger.info(f"Insufficient hourly observations ({len(hourly_records)}/24) for junction {junction_id}. Cannot run LSTM prediction.")
        return None

    # Sort chronologically ascending
    hourly_records = list(reversed(hourly_records))

    # Verify strict 1-hour continuity
    for k in range(1, len(hourly_records)):
        delta = (hourly_records[k].timestamp - hourly_records[k - 1].timestamp).total_seconds()
        if delta != 3600:
            logger.info(f"Hourly sequence for junction {junction_id} has gaps (gap of {delta}s). Cannot run continuous LSTM inference.")
            return None

    recent_24 = [float(h.speed_ratio) for h in hourly_records]

    seq_arr = np.array(recent_24, dtype="float32").reshape(1, 24, 1)
    scaled_seq = scaler.transform(seq_arr.reshape(-1, 1)).reshape(1, 24, 1)

    now = datetime.now()
    predictions = []
    current_window = scaled_seq.copy()

    for i in range(1, hours_ahead + 1):
        pred_scaled = model.predict(current_window, verbose=0)
        pred_speed_ratio = float(scaler.inverse_transform(pred_scaled)[0][0])

        if not np.isfinite(pred_speed_ratio):
            logger.warning(f"LSTM predicted non-finite speed_ratio for junction {junction_id}: {pred_speed_ratio}")
            return None

        pred_speed_ratio = max(0.0, min(1.0, pred_speed_ratio))

        target_time = now + timedelta(hours=i)
        target_hour = target_time.hour

        if pred_speed_ratio < 0.4:
            congestion = "critical"
        elif pred_speed_ratio < 0.7:
            congestion = "high"
        elif pred_speed_ratio < 0.9:
            congestion = "medium"
        else:
            congestion = "low"

        predicted_count = int((1.0 - pred_speed_ratio) * MAX_VEHICLE_COUNT)

        predictions.append({
            "hour": target_hour,
            "timestamp": target_time.isoformat(),
            "predicted_vehicle_count": predicted_count,
            "predicted_speed_ratio": round(pred_speed_ratio, 4),
            "congestion_level": congestion,
            "prediction_source": "lstm_model",
            "forecast_horizon_hours": i,
        })

        next_val_scaled = pred_scaled[0][0]
        current_window = np.append(current_window[0][1:], [[next_val_scaled]], axis=0).reshape(1, 24, 1)

    return predictions

