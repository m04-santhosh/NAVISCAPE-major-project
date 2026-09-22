import { useState, useEffect, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import api from '../services/api';
import {
  AreaChart, Area, BarChart, Bar, LineChart, Line, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, ReferenceLine,
} from 'recharts';
import { MapContainer, TileLayer, CircleMarker, Popup } from 'react-leaflet';
import {
  HiMap,
  HiShieldCheck,
  HiShieldExclamation,
  HiTrendingUp,
  HiLocationMarker,
  HiExclamationCircle,
  HiArrowRight,
  HiDatabase,
  HiClock,
  HiLightBulb,
  HiCheckCircle,
  HiFlag,
} from 'react-icons/hi';
import 'leaflet/dist/leaflet.css';

export default function Analytics() {
  const { user } = useAuth();

  // ── Independent state per section for resilient isolated loading ───────────
  const [history, setHistory] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyError, setHistoryError] = useState(null);

  const [hazards, setHazards] = useState([]);
  const [hazardsLoading, setHazardsLoading] = useState(true);

  const [accidentStats, setAccidentStats] = useState(null);
  const [statsLoading, setStatsLoading] = useState(true);

  const [accidentHeatmap, setAccidentHeatmap] = useState([]);
  const [heatmapLoading, setHeatmapLoading] = useState(true);

  const [forecast, setForecast] = useState([]);
  const [forecastLoading, setForecastLoading] = useState(true);
  const [selectedJunction, setSelectedJunction] = useState(1);

  useEffect(() => {
    loadDashboardData();
  }, []);

  const loadDashboardData = async () => {
    const [historyRes, hazardsRes, statsRes, heatmapRes, forecastRes] = await Promise.allSettled([
      api.get('/route-history'),
      api.get('/hazards'),
      api.get('/accidents/stats'),
      api.get('/accidents/heatmap?limit=3000'),
      api.get('/predict/congestion-forecast'),
    ]);

    if (historyRes.status === 'fulfilled') {
      setHistory(Array.isArray(historyRes.value.data) ? historyRes.value.data : []);
      setHistoryError(null);
    } else {
      console.warn('Route history fetch warning:', historyRes.reason);
      setHistoryError('Route history unavailable');
      setHistory([]);
    }
    setHistoryLoading(false);

    if (hazardsRes.status === 'fulfilled') {
      setHazards(Array.isArray(hazardsRes.value.data) ? hazardsRes.value.data : []);
    } else {
      console.warn('Hazards fetch warning:', hazardsRes.reason);
      setHazards([]);
    }
    setHazardsLoading(false);

    if (statsRes.status === 'fulfilled') {
      setAccidentStats(statsRes.value.data);
    } else {
      console.warn('Accident stats fetch warning:', statsRes.reason);
      setAccidentStats(null);
    }
    setStatsLoading(false);

    if (heatmapRes.status === 'fulfilled') {
      setAccidentHeatmap(Array.isArray(heatmapRes.value.data) ? heatmapRes.value.data : []);
    } else {
      console.warn('Accident heatmap fetch warning:', heatmapRes.reason);
      setAccidentHeatmap([]);
    }
    setHeatmapLoading(false);

    if (forecastRes.status === 'fulfilled') {
      const data = Array.isArray(forecastRes.value.data) ? forecastRes.value.data : [];
      setForecast(data);
      if (data.length > 0) {
        setSelectedJunction(data[0].junction_id);
      }
    } else {
      console.warn('Congestion forecast fetch warning:', forecastRes.reason);
      setForecast([]);
    }
    setForecastLoading(false);
  };

  // ── Personal Safety Analytics Calculations (Real User Data Only) ───────────
  const totalRoutes = history.length;

  const avgSafetyScoreNum = useMemo(() => {
    if (totalRoutes === 0) return null;
    const sum = history.reduce((acc, r) => acc + (Number(r.safety_score) || 0), 0);
    return sum / totalRoutes;
  }, [history, totalRoutes]);

  const avgSafetyScore = avgSafetyScoreNum !== null ? avgSafetyScoreNum.toFixed(1) : '—';

  const totalDistanceKm = useMemo(() => {
    if (totalRoutes === 0) return null;
    return history.reduce((acc, r) => acc + (Number(r.distance_km) || 0), 0);
  }, [history, totalRoutes]);

  const totalDurationMin = useMemo(() => {
    if (totalRoutes === 0) return null;
    return history.reduce((acc, r) => acc + (Number(r.duration_min) || 0), 0);
  }, [history, totalRoutes]);

  const safeRoutesCount = useMemo(() => {
    return history.filter((r) => (Number(r.safety_score) || 0) >= 80).length;
  }, [history]);

  const cautionRoutesCount = useMemo(() => {
    return history.filter((r) => (Number(r.safety_score) || 0) < 60).length;
  }, [history]);

  // Safest & lowest safety routes
  const sortedRoutes = useMemo(() => {
    return [...history].sort((a, b) => (b.safety_score || 0) - (a.safety_score || 0));
  }, [history]);

  const safestRoute = sortedRoutes.length > 0 ? sortedRoutes[0] : null;
  const lowestSafetyRoute = sortedRoutes.length > 1 ? sortedRoutes[sortedRoutes.length - 1] : null;

  // Chronological safety trend chart data (oldest to newest)
  const safetyTrendData = useMemo(() => {
    return [...history]
      .reverse()
      .map((r, idx) => {
        const dateStr = r.created_at
          ? new Date(r.created_at).toLocaleDateString(undefined, {
              month: 'short',
              day: 'numeric',
            })
          : `Trip ${idx + 1}`;
        return {
          id: r.id || idx,
          tripNumber: `Trip ${idx + 1}`,
          date: dateStr,
          score: r.safety_score !== null && r.safety_score !== undefined ? Number(r.safety_score.toFixed(1)) : null,
          from: r.source_name || 'Origin',
          to: r.dest_name || 'Destination',
          distance: r.distance_km ? `${r.distance_km.toFixed(1)} km` : '—',
          duration: r.duration_min ? `${Math.round(r.duration_min)} min` : '—',
          type: r.route_type || 'balanced',
        };
      })
      .filter((d) => d.score !== null);
  }, [history]);

  // Deterministic Personal Safety Insights
  const safetyInsights = useMemo(() => {
    if (totalRoutes === 0) return [];
    const insights = [];

    // 1. Completion count insight
    insights.push({
      icon: HiCheckCircle,
      color: 'text-cyan-400',
      text: `You have completed ${totalRoutes} journey${totalRoutes > 1 ? 's' : ''} with NAVISCAPE intelligent routing.`,
    });

    // 2. Score quality insight
    if (avgSafetyScoreNum !== null) {
      if (avgSafetyScoreNum >= 80) {
        insights.push({
          icon: HiShieldCheck,
          color: 'text-emerald-400',
          text: `Your overall safety rating is optimal at ${avgSafetyScore}/100 with consistent low-risk routing.`,
        });
      } else if (avgSafetyScoreNum >= 60) {
        insights.push({
          icon: HiShieldCheck,
          color: 'text-amber-400',
          text: `Your average journey safety score is ${avgSafetyScore}/100 across moderate-risk urban corridors.`,
        });
      } else {
        insights.push({
          icon: HiExclamationCircle,
          color: 'text-rose-400',
          text: `Your average safety score is ${avgSafetyScore}/100. Choose "Safest Route" mode to bypass accident-prone areas.`,
        });
      }
    }

    // 3. Recent vs Historical Trend comparison
    if (totalRoutes >= 2) {
      const latestScore = Number(history[0]?.safety_score) || 0;
      const diff = latestScore - (avgSafetyScoreNum || 0);
      if (Math.abs(diff) >= 1.0) {
        if (diff > 0) {
          insights.push({
            icon: HiTrendingUp,
            color: 'text-emerald-400',
            text: `Your latest journey (${latestScore.toFixed(1)}) scored +${diff.toFixed(1)} points higher than your historical average.`,
          });
        } else {
          insights.push({
            icon: HiShieldExclamation,
            color: 'text-amber-400',
            text: `Your latest journey (${latestScore.toFixed(1)}) passed through higher risk corridors than your historical average (${avgSafetyScore}).`,
          });
        }
      }
    }

    // 4. Optimal route proportion
    if (totalRoutes >= 3) {
      const safePct = Math.round((safeRoutesCount / totalRoutes) * 100);
      insights.push({
        icon: HiLightBulb,
        color: 'text-indigo-400',
        text: `${safePct}% of your completed journeys achieved high-safety ratings (80+ empirical score).`,
      });
    }

    return insights;
  }, [totalRoutes, avgSafetyScoreNum, avgSafetyScore, history, safeRoutesCount]);

  // Selected junction forecast chart data
  const currentJunctionForecast = forecast.find((f) => f.junction_id === selectedJunction) || forecast[0];
  const forecastChartData = currentJunctionForecast?.forecasts?.map((f) => ({
    hour: `${f.hour}:00`,
    predicted: f.vehicle_count,
    level: f.congestion_level,
  })) || [];

  // Top districts chart data
  const topDistrictsData = accidentStats?.top_districts?.slice(0, 6).map((d) => ({
    name: d.district?.replace(' City', '').replace(' Dist', ''),
    count: d.count,
  })) || [];

  const displayName = user?.full_name || user?.username || user?.email?.split('@')[0] || 'Explorer';

  const formatDateTime = (isoString) => {
    if (!isoString) return '—';
    try {
      return new Date(isoString).toLocaleString(undefined, {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return '—';
    }
  };

  return (
    <div className="p-4 md:p-8 space-y-8 animate-fade-in max-w-7xl mx-auto">
      {/* ── 1. DASHBOARD HEADER ── */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-surface-800/80 pb-6">
        <div>
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-cyan-500/10 border border-cyan-500/30 text-cyan-400 text-xs font-semibold uppercase tracking-wider mb-2">
            <span>Intelligent Safety Platform</span>
          </div>
          <h1 className="text-2xl md:text-3xl font-extrabold text-surface-100 tracking-tight">
            NAVISCAPE Dashboard
          </h1>
          <p className="text-surface-400 text-sm md:text-base mt-1">
            Welcome back, <strong className="text-surface-200">{displayName}</strong>. Your navigation, traffic and road-safety overview.
          </p>
        </div>

        <Link
          to="/navigate"
          className="btn-primary inline-flex items-center justify-center gap-2 px-5 py-2.5 text-sm font-semibold shadow-lg shadow-cyan-500/20 whitespace-nowrap"
        >
          <span>Start Navigation</span>
          <HiArrowRight className="w-4 h-4" />
        </Link>
      </div>

      {/* ── 2. SUMMARY CARDS (4 Real Metrics) ── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 md:gap-5">
        {/* A. Routes Completed */}
        <div className="stat-card">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-surface-400 uppercase tracking-wider">Routes Completed</span>
            <div className="w-8 h-8 rounded-lg bg-cyan-500/10 border border-cyan-500/30 text-cyan-400 flex items-center justify-center">
              <HiMap className="w-4 h-4" />
            </div>
          </div>
          <p className="text-2xl md:text-3xl font-bold text-surface-100 mt-2">
            {historyLoading ? '...' : totalRoutes}
          </p>
          <p className="text-xs text-surface-400 mt-1">Authenticated journeys</p>
        </div>

        {/* B. Average Safety Score */}
        <div className="stat-card">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-surface-400 uppercase tracking-wider">Avg Safety Score</span>
            <div className="w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 flex items-center justify-center">
              <HiShieldCheck className="w-4 h-4" />
            </div>
          </div>
          <p className={`text-2xl md:text-3xl font-bold mt-2 ${
            avgSafetyScore !== '—' && Number(avgSafetyScore) >= 80
              ? 'text-emerald-400'
              : avgSafetyScore !== '—' && Number(avgSafetyScore) >= 60
              ? 'text-amber-400'
              : avgSafetyScore !== '—'
              ? 'text-rose-400'
              : 'text-surface-100'
          }`}>
            {historyLoading ? '...' : avgSafetyScore}
            {avgSafetyScore !== '—' && <span className="text-sm font-normal text-surface-400 ml-1">/ 100</span>}
          </p>
          <p className="text-xs text-surface-400 mt-1">Empirical safety rating</p>
        </div>

        {/* C. Active Road Hazards */}
        <div className="stat-card">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-surface-400 uppercase tracking-wider">Active Hazards</span>
            <div className="w-8 h-8 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-400 flex items-center justify-center">
              <HiExclamationCircle className="w-4 h-4" />
            </div>
          </div>
          <p className="text-2xl md:text-3xl font-bold text-amber-400 mt-2">
            {hazardsLoading ? '...' : hazards.length}
          </p>
          <p className="text-xs text-surface-400 mt-1">Live community hazard reports</p>
        </div>

        {/* D. Accident Dataset */}
        <div className="stat-card">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-surface-400 uppercase tracking-wider">Accident Dataset</span>
            <div className="w-8 h-8 rounded-lg bg-indigo-500/10 border border-indigo-500/30 text-indigo-400 flex items-center justify-center">
              <HiDatabase className="w-4 h-4" />
            </div>
          </div>
          <p className="text-2xl md:text-3xl font-bold text-indigo-300 mt-2">
            {statsLoading ? '...' : (accidentStats?.total_records?.toLocaleString() || '95,723')}
          </p>
          <p className="text-xs text-surface-400 mt-1">
            {statsLoading ? 'Loading...' : `${accidentStats?.districts_count || 31} Karnataka districts`}
          </p>
        </div>
      </div>

      {/* ── PHASE 2: PERSONAL SAFETY PROFILE & INSIGHTS ── */}
      <div className="grid lg:grid-cols-12 gap-6">
        {/* Personal Safety Profile */}
        <div className="glass-card p-6 lg:col-span-7 flex flex-col justify-between space-y-5">
          <div>
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-emerald-500/15 text-emerald-400 flex items-center justify-center border border-emerald-500/30">
                  <HiShieldCheck className="w-5 h-5" />
                </div>
                <div>
                  <h2 className="text-base md:text-lg font-bold text-surface-100">Your Safety Profile</h2>
                  <p className="text-xs text-surface-400">Personalized analytics from your completed journeys</p>
                </div>
              </div>
              {totalRoutes > 0 && (
                <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                  {safeRoutesCount} Optimal Safety Trips
                </span>
              )}
            </div>

            {historyLoading ? (
              <div className="py-12 flex items-center justify-center">
                <div className="w-8 h-8 border-2 border-emerald-500/30 border-t-emerald-400 rounded-full animate-spin" />
              </div>
            ) : totalRoutes === 0 ? (
              /* Clean Empty State for 0 routes */
              <div className="py-8 px-4 text-center rounded-xl bg-surface-900/40 border border-dashed border-surface-800 space-y-3">
                <HiShieldCheck className="w-12 h-12 text-surface-600 mx-auto" />
                <h3 className="text-sm font-semibold text-surface-200">No completed journeys yet</h3>
                <p className="text-xs text-surface-400 max-w-md mx-auto">
                  Start navigating to build your personal safety profile, track empirical road safety scores, and view risk trend predictions.
                </p>
                <Link
                  to="/navigate"
                  className="btn-primary inline-flex items-center gap-2 text-xs font-semibold px-4 py-2 mt-2"
                >
                  <span>Start First Journey</span>
                  <HiArrowRight className="w-3.5 h-3.5" />
                </Link>
              </div>
            ) : (
              /* Populated Personal Safety Profile Tiles */
              <div className="space-y-4">
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div className="p-3.5 rounded-xl bg-surface-900/60 border border-surface-800">
                    <p className="text-[11px] text-surface-400 font-medium">Avg Safety Rating</p>
                    <p className="text-lg font-bold text-emerald-400 mt-1">{avgSafetyScore} <span className="text-xs text-surface-500">/100</span></p>
                  </div>
                  <div className="p-3.5 rounded-xl bg-surface-900/60 border border-surface-800">
                    <p className="text-[11px] text-surface-400 font-medium">Total Distance</p>
                    <p className="text-lg font-bold text-surface-100 mt-1">
                      {totalDistanceKm !== null ? `${totalDistanceKm.toFixed(1)} km` : '—'}
                    </p>
                  </div>
                  <div className="p-3.5 rounded-xl bg-surface-900/60 border border-surface-800">
                    <p className="text-[11px] text-surface-400 font-medium">Travel Time</p>
                    <p className="text-lg font-bold text-surface-100 mt-1">
                      {totalDurationMin !== null ? `${Math.round(totalDurationMin)} min` : '—'}
                    </p>
                  </div>
                  <div className="p-3.5 rounded-xl bg-surface-900/60 border border-surface-800">
                    <p className="text-[11px] text-surface-400 font-medium">Caution Routes</p>
                    <p className={`text-lg font-bold mt-1 ${cautionRoutesCount > 0 ? 'text-amber-400' : 'text-surface-100'}`}>
                      {cautionRoutesCount}
                    </p>
                  </div>
                </div>

                {/* Best & Caution Route Cards */}
                {safestRoute && (
                  <div className="grid sm:grid-cols-2 gap-3 pt-1">
                    <div className="p-3.5 rounded-xl bg-emerald-500/10 border border-emerald-500/25">
                      <div className="flex justify-between items-center mb-1">
                        <span className="text-xs font-bold text-emerald-400">Safest Recent Journey</span>
                        <span className="text-xs font-extrabold px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300">
                          {safestRoute.safety_score?.toFixed(1)} / 100
                        </span>
                      </div>
                      <p className="text-xs text-surface-200 font-medium truncate mt-1">
                        {safestRoute.source_name || 'Origin'} &rarr; {safestRoute.dest_name || 'Destination'}
                      </p>
                      <p className="text-[11px] text-surface-400 mt-0.5">
                        {safestRoute.distance_km ? `${safestRoute.distance_km.toFixed(1)} km · ` : ''}
                        {safestRoute.duration_min ? `${Math.round(safestRoute.duration_min)} min · ` : ''}
                        <span className="capitalize">{safestRoute.route_type || 'balanced'}</span>
                      </p>
                    </div>

                    {lowestSafetyRoute ? (
                      <div className="p-3.5 rounded-xl bg-amber-500/10 border border-amber-500/25">
                        <div className="flex justify-between items-center mb-1">
                          <span className="text-xs font-bold text-amber-400">Lowest Safety Score</span>
                          <span className="text-xs font-extrabold px-2 py-0.5 rounded bg-amber-500/20 text-amber-300">
                            {lowestSafetyRoute.safety_score?.toFixed(1)} / 100
                          </span>
                        </div>
                        <p className="text-xs text-surface-200 font-medium truncate mt-1">
                          {lowestSafetyRoute.source_name || 'Origin'} &rarr; {lowestSafetyRoute.dest_name || 'Destination'}
                        </p>
                        <p className="text-[11px] text-surface-400 mt-0.5">
                          {lowestSafetyRoute.distance_km ? `${lowestSafetyRoute.distance_km.toFixed(1)} km · ` : ''}
                          {lowestSafetyRoute.duration_min ? `${Math.round(lowestSafetyRoute.duration_min)} min · ` : ''}
                          <span className="capitalize">{lowestSafetyRoute.route_type || 'balanced'}</span>
                        </p>
                      </div>
                    ) : (
                      <div className="p-3.5 rounded-xl bg-surface-900/50 border border-surface-800 flex items-center justify-center">
                        <p className="text-xs text-surface-400 text-center">Complete more routes to compare highest and lowest safety corridors.</p>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="flex items-center justify-between text-xs text-surface-400 pt-3 border-t border-surface-800/60">
            <span>Empirical Engine: <strong className="text-surface-200">KSP Historical Spatial Density</strong></span>
            <Link to="/navigate" className="text-cyan-400 hover:text-cyan-300 font-semibold inline-flex items-center gap-1">
              <span>Plan Safe Route</span>
              <HiArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>
        </div>

        {/* Personal Safety Insights */}
        <div className="glass-card p-6 lg:col-span-5 flex flex-col justify-between space-y-4">
          <div>
            <div className="flex items-center gap-2 mb-3">
              <div className="w-8 h-8 rounded-lg bg-indigo-500/15 text-indigo-400 flex items-center justify-center border border-indigo-500/30">
                <HiLightBulb className="w-5 h-5" />
              </div>
              <div>
                <h2 className="text-base md:text-lg font-bold text-surface-100">Safety Insights</h2>
                <p className="text-xs text-surface-400">Deterministic journey analytics</p>
              </div>
            </div>

            {totalRoutes === 0 ? (
              <div className="p-6 rounded-xl bg-surface-900/40 border border-dashed border-surface-800 text-center space-y-2 mt-4">
                <HiLightBulb className="w-8 h-8 text-surface-600 mx-auto" />
                <p className="text-xs text-surface-300 font-medium">No personal insights available</p>
                <p className="text-[11px] text-surface-500">
                  Insights generate automatically after your journeys are logged in route history.
                </p>
              </div>
            ) : (
              <div className="space-y-3 mt-4">
                {safetyInsights.map((insight, idx) => {
                  const Icon = insight.icon;
                  return (
                    <div key={idx} className="p-3.5 rounded-xl bg-surface-900/60 border border-surface-800/80 flex items-start gap-3">
                      <Icon className={`w-5 h-5 flex-shrink-0 mt-0.5 ${insight.color}`} />
                      <p className="text-xs text-surface-200 leading-relaxed">{insight.text}</p>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          <div className="p-3 rounded-xl bg-surface-900/80 border border-surface-800 text-[11px] text-surface-400">
            <span className="font-semibold text-surface-300">Note:</span> Safety scores are calculated empirically from verified accident frequency, road hazards, and traffic delay along candidate road segments.
          </div>
        </div>
      </div>

      {/* ── PHASE 2: SAFETY SCORE TREND CHART ── */}
      <div className="glass-card p-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-4">
          <div>
            <div className="flex items-center gap-2">
              <HiTrendingUp className="text-emerald-400 w-5 h-5" />
              <h2 className="text-base md:text-lg font-bold text-surface-100">Safety Score Trend</h2>
            </div>
            <p className="text-xs text-surface-400 mt-0.5">Empirical safety score progression across completed journeys</p>
          </div>
          {safetyTrendData.length > 0 && (
            <div className="flex items-center gap-4 text-xs">
              <span className="inline-flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-emerald-400" /> Optimal (&ge;80)</span>
              <span className="inline-flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-amber-400" /> Moderate (60-79)</span>
              <span className="inline-flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-rose-400" /> Caution (&lt;60)</span>
            </div>
          )}
        </div>

        {historyLoading ? (
          <div className="h-64 flex items-center justify-center">
            <div className="w-8 h-8 border-2 border-emerald-500/30 border-t-emerald-400 rounded-full animate-spin" />
          </div>
        ) : safetyTrendData.length === 0 ? (
          <div className="h-64 flex flex-col items-center justify-center text-center p-6 bg-surface-900/40 rounded-xl border border-dashed border-surface-800 space-y-2">
            <HiTrendingUp className="w-10 h-10 text-surface-600" />
            <p className="text-sm font-semibold text-surface-300">No route trend data available yet</p>
            <p className="text-xs text-surface-500 max-w-sm">
              Complete routes in the Navigation page to visualize your safety score trends over time.
            </p>
          </div>
        ) : (
          <div className="h-72 mt-3">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={safetyTrendData} margin={{ top: 10, right: 20, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="safetyScoreGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#10b981" stopOpacity={0.35} />
                    <stop offset="95%" stopColor="#10b981" stopOpacity={0.0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.6} />
                <XAxis dataKey="tripNumber" stroke="#64748b" fontSize={11} tickLine={false} />
                <YAxis stroke="#64748b" fontSize={11} domain={[0, 100]} tickLine={false} />
                <ReferenceLine y={80} stroke="#10b981" strokeDasharray="4 4" opacity={0.6} label={{ value: 'Safe (80)', fill: '#10b981', fontSize: 10, position: 'insideTopLeft' }} />
                <ReferenceLine y={60} stroke="#f59e0b" strokeDasharray="4 4" opacity={0.4} label={{ value: 'Caution (60)', fill: '#f59e0b', fontSize: 10, position: 'insideTopLeft' }} />
                <Tooltip
                  content={({ active, payload }) => {
                    if (active && payload && payload.length) {
                      const data = payload[0].payload;
                      return (
                        <div className="p-3 rounded-xl bg-surface-900/95 border border-surface-700 shadow-xl text-xs space-y-1 text-surface-200">
                          <p className="font-bold text-surface-100">{data.tripNumber} · {data.date}</p>
                          <p className="text-surface-300 truncate">{data.from} &rarr; {data.to}</p>
                          <div className="flex items-center justify-between gap-4 pt-1 border-t border-surface-800">
                            <span className="text-surface-400">Safety Score:</span>
                            <span className={`font-bold ${data.score >= 80 ? 'text-emerald-400' : data.score >= 60 ? 'text-amber-400' : 'text-rose-400'}`}>
                              {data.score} / 100
                            </span>
                          </div>
                          <div className="flex items-center justify-between gap-4">
                            <span className="text-surface-400">Distance / Time:</span>
                            <span className="font-medium text-surface-200">{data.distance} · {data.duration}</span>
                          </div>
                        </div>
                      );
                    }
                    return null;
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="score"
                  stroke="#10b981"
                  strokeWidth={2.5}
                  fill="url(#safetyScoreGrad)"
                  dot={{ fill: '#10b981', stroke: '#0f172a', strokeWidth: 2, r: 4 }}
                  activeDot={{ fill: '#34d399', stroke: '#0f172a', strokeWidth: 2, r: 6 }}
                  name="Safety Score"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* ── 4. TRAFFIC OVERVIEW & 5. ACCIDENT STATISTICS ── */}
      <div className="grid lg:grid-cols-2 gap-6">
        {/* 4. Traffic Overview (Forecast) */}
        <div className="glass-card p-6 flex flex-col justify-between">
          <div>
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-4">
              <div className="flex items-center gap-2">
                <HiTrendingUp className="text-cyan-400 w-5 h-5" />
                <h3 className="text-base font-bold text-surface-200">Traffic Forecast</h3>
                <span className="text-[10px] uppercase font-bold px-2 py-0.5 rounded bg-cyan-500/15 text-cyan-400 border border-cyan-500/30">
                  24h Predictive Model
                </span>
              </div>
              <span className="text-xs text-surface-400">
                {forecast.length} Monitored Junctions
              </span>
            </div>

            {/* Junction Tabs */}
            {forecast.length > 0 && (
              <div className="flex gap-2 overflow-x-auto pb-2 scrollbar-thin">
                {forecast.map((f) => (
                  <button
                    key={f.junction_id}
                    onClick={() => setSelectedJunction(f.junction_id)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all ${
                      selectedJunction === f.junction_id
                        ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40'
                        : 'bg-surface-800/40 text-surface-400 border border-surface-700 hover:border-surface-600'
                    }`}
                  >
                    {f.junction_name?.split(' ')[0]}
                  </button>
                ))}
              </div>
            )}

            {/* Chart / State */}
            {forecastLoading ? (
              <div className="h-56 flex items-center justify-center">
                <div className="w-8 h-8 border-2 border-cyan-500/30 border-t-cyan-400 rounded-full animate-spin" />
              </div>
            ) : forecastChartData.length > 0 ? (
              <div className="h-56 mt-3">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={forecastChartData}>
                    <defs>
                      <linearGradient id="forecastGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#06b6d4" stopOpacity={0.3} />
                        <stop offset="95%" stopColor="#06b6d4" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                    <XAxis dataKey="hour" stroke="#64748b" fontSize={10} />
                    <YAxis stroke="#64748b" fontSize={10} />
                    <Tooltip
                      contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 10, color: '#e2e8f0', fontSize: '12px' }}
                    />
                    <Area
                      type="monotone"
                      dataKey="predicted"
                      stroke="#06b6d4"
                      fill="url(#forecastGrad)"
                      strokeWidth={2}
                      name="Forecast Vehicle Count"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <div className="h-56 flex flex-col items-center justify-center text-center p-4 bg-surface-900/30 rounded-xl border border-surface-800 mt-3">
                <HiClock className="w-8 h-8 text-surface-500 mb-2" />
                <p className="text-sm font-medium text-surface-300">Traffic Forecast Data Unavailable</p>
                <p className="text-xs text-surface-500 max-w-sm mt-1">
                  Predictive observations are currently compiling. Real-time routing remains fully active.
                </p>
              </div>
            )}
          </div>

          <div className="flex items-center justify-between text-xs text-surface-400 pt-3 border-t border-surface-800/60 mt-2">
            <span>Junction: <strong className="text-surface-200">{currentJunctionForecast?.junction_name || 'Bangalore Grid'}</strong></span>
            <span>Source: <strong className="text-surface-200">{currentJunctionForecast?.prediction_source || 'ML Forecast'}</strong></span>
          </div>
        </div>

        {/* 5. Accident Dataset Statistics */}
        <div className="glass-card p-6 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <HiLocationMarker className="text-indigo-400 w-5 h-5" />
                <h3 className="text-base font-bold text-surface-200">Karnataka Accident Statistics</h3>
              </div>
              <span className="text-xs text-surface-400">Authoritative Dataset</span>
            </div>

            {statsLoading ? (
              <div className="h-64 flex items-center justify-center">
                <div className="w-8 h-8 border-2 border-indigo-500/30 border-t-indigo-400 rounded-full animate-spin" />
              </div>
            ) : accidentStats ? (
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-3">
                  <div className="p-3.5 rounded-xl bg-surface-900/60 border border-surface-800">
                    <p className="text-xs text-surface-400">Total Recorded Incidents</p>
                    <p className="text-lg font-bold text-surface-100 mt-1">
                      {accidentStats.total_records?.toLocaleString()}
                    </p>
                  </div>
                  <div className="p-3.5 rounded-xl bg-surface-900/60 border border-surface-800">
                    <p className="text-xs text-surface-400">Geo-Tagged Coordinates</p>
                    <p className="text-lg font-bold text-emerald-400 mt-1">
                      {accidentStats.records_with_coordinates?.toLocaleString()}
                    </p>
                  </div>
                  <div className="p-3.5 rounded-xl bg-surface-900/60 border border-surface-800">
                    <p className="text-xs text-surface-400">Districts Covered</p>
                    <p className="text-lg font-bold text-cyan-400 mt-1">
                      {accidentStats.districts_count}
                    </p>
                  </div>
                  <div className="p-3.5 rounded-xl bg-surface-900/60 border border-surface-800">
                    <p className="text-xs text-surface-400">Fatal Incidents</p>
                    <p className="text-lg font-bold text-rose-400 mt-1">
                      {(accidentStats.severity_breakdown?.['Fatal'] || 0).toLocaleString()}
                    </p>
                  </div>
                </div>

                {topDistrictsData.length > 0 && (
                  <div>
                    <p className="text-xs font-semibold text-surface-400 mb-2">High Incident Districts</p>
                    <div className="h-36">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={topDistrictsData}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                          <XAxis dataKey="name" stroke="#64748b" fontSize={10} />
                          <YAxis stroke="#64748b" fontSize={10} />
                          <Tooltip
                            contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 8, color: '#e2e8f0', fontSize: '11px' }}
                          />
                          <Bar dataKey="count" fill="#6366f1" radius={[4, 4, 0, 0]} name="Recorded Incidents" />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="h-64 flex items-center justify-center text-center p-4">
                <p className="text-xs text-surface-400">Accident statistics data unavailable.</p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── 6. ACCIDENT RISK DENSITY MAP ── */}
      <div className="glass-card p-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-4">
          <div className="flex items-center gap-2">
            <HiShieldExclamation className="text-rose-400 w-5 h-5" />
            <h3 className="text-base font-bold text-surface-200">Accident Risk Density Map</h3>
          </div>
          <div className="flex items-center gap-3">
            <span className="flex items-center gap-3 text-xs text-surface-400">
              <span className="inline-flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-rose-500" /> Fatal</span>
              <span className="inline-flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-amber-500" /> Injury</span>
            </span>
            <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-rose-500/15 text-rose-400 border border-rose-500/30">
              {accidentHeatmap.length.toLocaleString()} Incidents Mapped
            </span>
          </div>
        </div>

        {heatmapLoading ? (
          <div className="h-80 flex items-center justify-center">
            <div className="w-8 h-8 border-2 border-rose-500/30 border-t-rose-400 rounded-full animate-spin" />
          </div>
        ) : (
          <div className="h-80 rounded-xl overflow-hidden relative border border-surface-800">
            <MapContainer
              center={[12.9716, 77.5946]}
              zoom={11}
              className="h-full w-full"
              style={{ background: '#0f172a' }}
            >
              <TileLayer
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                attribution="&copy; OpenStreetMap"
              />
              {accidentHeatmap.map((pt, idx) => (
                <CircleMarker
                  key={idx}
                  center={[pt.lat, pt.lng]}
                  radius={pt.severity === 'Fatal' ? 6 : 4}
                  pathOptions={{
                    color: pt.severity === 'Fatal' ? '#ef4444' : pt.severity === 'Grievous Injury' ? '#f97316' : '#eab308',
                    fillColor: pt.severity === 'Fatal' ? '#ef4444' : pt.severity === 'Grievous Injury' ? '#f97316' : '#eab308',
                    fillOpacity: 0.6,
                    weight: 1,
                  }}
                >
                  <Popup>
                    <div className="text-xs space-y-1 text-surface-100">
                      <p className="font-bold text-surface-100">{pt.district || 'Location'}</p>
                      <p>Severity: <span className="font-semibold text-rose-400">{pt.severity || 'Recorded'}</span></p>
                      <p className="text-surface-400">GPS: {pt.lat?.toFixed(4)}, {pt.lng?.toFixed(4)}</p>
                    </div>
                  </Popup>
                </CircleMarker>
              ))}
            </MapContainer>
          </div>
        )}
      </div>

      {/* ── 7. PERSONAL ROUTE INTELLIGENCE (Recent Route History) ── */}
      <div className="glass-card p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <HiMap className="text-cyan-400 w-5 h-5" />
            <h2 className="text-base md:text-lg font-bold text-surface-100">Personal Route Intelligence</h2>
          </div>
          <Link
            to="/navigate"
            className="text-xs font-semibold text-cyan-400 hover:text-cyan-300 inline-flex items-center gap-1"
          >
            <span>Navigate new route</span>
            <HiArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>

        {historyLoading ? (
          <div className="h-36 flex items-center justify-center">
            <div className="w-6 h-6 border-2 border-cyan-500/30 border-t-cyan-400 rounded-full animate-spin" />
          </div>
        ) : history.length === 0 ? (
          <div className="text-center py-10 px-4 bg-surface-900/40 rounded-xl border border-dashed border-surface-800 space-y-3">
            <HiMap className="w-10 h-10 text-surface-500 mx-auto" />
            <p className="text-sm font-medium text-surface-300">
              No routes yet. Start navigating to see your route history.
            </p>
            <Link
              to="/navigate"
              className="btn-primary inline-flex items-center gap-2 text-xs font-semibold px-4 py-2"
            >
              <span>Explore Routes</span>
              <HiArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs md:text-sm text-left">
              <thead>
                <tr className="text-surface-400 border-b border-surface-800">
                  <th className="pb-3 font-semibold">Origin & Destination</th>
                  <th className="pb-3 font-semibold">Date & Time</th>
                  <th className="pb-3 font-semibold">Distance</th>
                  <th className="pb-3 font-semibold">Duration</th>
                  <th className="pb-3 font-semibold">Safety Score</th>
                  <th className="pb-3 font-semibold">Risk Level</th>
                  <th className="pb-3 font-semibold">Route Type</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-800/60">
                {history.slice(0, 10).map((r, i) => {
                  const score = Number(r.safety_score);
                  const isSafe = !isNaN(score) && score >= 80;
                  const isModerate = !isNaN(score) && score >= 60 && score < 80;
                  const isCaution = !isNaN(score) && score < 60;

                  return (
                    <tr key={r.id || i} className="hover:bg-surface-800/30 transition-colors">
                      <td className="py-3 font-medium text-surface-200">
                        <div className="truncate max-w-[200px]">
                          <span className="text-surface-100">{r.source_name || 'Origin Coordinate'}</span>
                          <span className="text-surface-500 mx-1.5">&rarr;</span>
                          <span className="text-surface-100">{r.dest_name || 'Destination Coordinate'}</span>
                        </div>
                      </td>
                      <td className="py-3 text-surface-400 whitespace-nowrap">
                        {formatDateTime(r.created_at)}
                      </td>
                      <td className="py-3 text-surface-300">
                        {r.distance_km ? `${r.distance_km.toFixed(1)} km` : '—'}
                      </td>
                      <td className="py-3 text-surface-300">
                        {r.duration_min ? `${Math.round(r.duration_min)} min` : '—'}
                      </td>
                      <td className="py-3">
                        <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-bold ${
                          isSafe
                            ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30'
                            : isModerate
                            ? 'bg-amber-500/15 text-amber-400 border border-amber-500/30'
                            : isCaution
                            ? 'bg-rose-500/15 text-rose-400 border border-rose-500/30'
                            : 'text-surface-400'
                        }`}>
                          {!isNaN(score) ? score.toFixed(1) : '—'}
                        </span>
                      </td>
                      <td className="py-3">
                        <span className={`inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded ${
                          isSafe
                            ? 'text-emerald-400 bg-emerald-500/10'
                            : isModerate
                            ? 'text-amber-400 bg-amber-500/10'
                            : isCaution
                            ? 'text-rose-400 bg-rose-500/10'
                            : 'text-surface-400'
                        }`}>
                          {isSafe ? 'Low Risk' : isModerate ? 'Moderate' : isCaution ? 'High Risk' : 'Unknown'}
                        </span>
                      </td>
                      <td className="py-3">
                        <span className="capitalize px-2 py-0.5 rounded text-[11px] font-semibold bg-surface-800 text-surface-300 border border-surface-700">
                          {r.route_type || 'balanced'}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
