import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import api from '../services/api';
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid,
} from 'recharts';
import { MapContainer, TileLayer, CircleMarker, Popup } from 'react-leaflet';
import {
  HiMap,
  HiShieldCheck,
  HiShieldExclamation,
  HiChartBar,
  HiTrendingUp,
  HiLocationMarker,
  HiExclamationCircle,
  HiArrowRight,
  HiDatabase,
  HiClock,
} from 'react-icons/hi';
import 'leaflet/dist/leaflet.css';

export default function Analytics() {
  const { user } = useAuth();

  // Individual state per section for resilient independent rendering
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
    // Independent loading with Promise.allSettled so no single API failure breaks the dashboard
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

  // ── Metrics Calculations ───────────────────────────────────────────────────
  const totalRoutes = history.length;
  const avgSafetyScore = totalRoutes > 0
    ? (history.reduce((sum, r) => sum + (Number(r.safety_score) || 0), 0) / totalRoutes).toFixed(1)
    : '—';

  // Safest and lowest safety routes from real history
  const sortedRoutes = [...history].sort((a, b) => (b.safety_score || 0) - (a.safety_score || 0));
  const safestRoute = sortedRoutes.length > 0 ? sortedRoutes[0] : null;
  const lowestSafetyRoute = sortedRoutes.length > 1 ? sortedRoutes[sortedRoutes.length - 1] : null;

  // Selected junction forecast chart data
  const currentJunctionForecast = forecast.find((f) => f.junction_id === selectedJunction) || forecast[0];
  const chartData = currentJunctionForecast?.forecasts?.map((f) => ({
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

  return (
    <div className="p-4 md:p-8 space-y-8 animate-fade-in max-w-7xl mx-auto">
      {/* ── 1. DASHBOARD HEADER ── */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-surface-800/80 pb-6">
        <div>
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-cyan-500/10 border border-cyan-500/30 text-cyan-400 text-xs font-semibold uppercase tracking-wider mb-2">
            <span>Live Overview</span>
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

      {/* ── 2. SUMMARY CARDS (4 Useful Real Metrics) ── */}
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
          <p className="text-xs text-surface-400 mt-1">User journey history</p>
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
          <p className="text-xs text-surface-400 mt-1">Verified road hazard reports</p>
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

      {/* ── 3. SAFETY OVERVIEW & STATS ROW ── */}
      <div className="grid lg:grid-cols-3 gap-6">
        {/* Safety Overview Card */}
        <div className="glass-card p-6 lg:col-span-1 flex flex-col justify-between space-y-4">
          <div>
            <div className="flex items-center gap-2 mb-3">
              <HiShieldCheck className="text-emerald-400 w-5 h-5" />
              <h3 className="text-base font-bold text-surface-200">Safety Overview</h3>
            </div>
            <p className="text-xs text-surface-400">
              Aggregated safety performance calculated from your completed routes.
            </p>

            <div className="mt-4 p-4 rounded-xl bg-surface-900/60 border border-surface-800 space-y-3">
              <div className="flex justify-between items-center text-sm">
                <span className="text-surface-400">Average Safety Score:</span>
                <span className="font-bold text-surface-100">{avgSafetyScore}</span>
              </div>
              <div className="flex justify-between items-center text-sm">
                <span className="text-surface-400">Total Routes Recorded:</span>
                <span className="font-bold text-surface-100">{totalRoutes}</span>
              </div>
            </div>

            {/* Route Highlights */}
            {safestRoute ? (
              <div className="mt-4 space-y-2.5">
                <div className="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-xs">
                  <div className="flex justify-between items-center mb-1">
                    <span className="font-semibold text-emerald-400">Safest Recent Route</span>
                    <span className="font-bold px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300">
                      {safestRoute.safety_score?.toFixed(1)} / 100
                    </span>
                  </div>
                  <p className="text-surface-300 truncate">
                    {safestRoute.source_name || 'Origin'} &rarr; {safestRoute.dest_name || 'Destination'}
                  </p>
                </div>

                {lowestSafetyRoute && (
                  <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/20 text-xs">
                    <div className="flex justify-between items-center mb-1">
                      <span className="font-semibold text-amber-400">Caution Route</span>
                      <span className="font-bold px-2 py-0.5 rounded bg-amber-500/20 text-amber-300">
                        {lowestSafetyRoute.safety_score?.toFixed(1)} / 100
                      </span>
                    </div>
                    <p className="text-surface-300 truncate">
                      {lowestSafetyRoute.source_name || 'Origin'} &rarr; {lowestSafetyRoute.dest_name || 'Destination'}
                    </p>
                  </div>
                )}
              </div>
            ) : (
              <div className="mt-4 p-4 rounded-xl bg-surface-900/40 border border-dashed border-surface-800 text-center">
                <p className="text-xs text-surface-400">
                  No routes recorded yet. Start navigating to build your personalized safety profile.
                </p>
              </div>
            )}
          </div>

          <Link
            to="/navigate"
            className="text-xs font-semibold text-cyan-400 hover:text-cyan-300 inline-flex items-center gap-1.5 pt-2"
          >
            <span>Plan safe route</span>
            <HiArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>

        {/* ── 4. TRAFFIC OVERVIEW (Traffic Forecast) ── */}
        <div className="glass-card p-6 lg:col-span-2 flex flex-col justify-between">
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
            {forecast.length > 0 ? (
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
            ) : null}

            {/* Chart / State */}
            {forecastLoading ? (
              <div className="h-56 flex items-center justify-center">
                <div className="w-8 h-8 border-2 border-cyan-500/30 border-t-cyan-400 rounded-full animate-spin" />
              </div>
            ) : chartData.length > 0 ? (
              <div className="h-56 mt-3">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={chartData}>
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
      </div>

      {/* ── 5. ACCIDENT STATISTICS & 6. ACCIDENT MAP ── */}
      <div className="grid lg:grid-cols-2 gap-6">
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
                {/* 4 Quick Stat Tiles */}
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

                {/* Top Districts Bar Chart */}
                {topDistrictsData.length > 0 && (
                  <div>
                    <p className="text-xs font-semibold text-surface-400 mb-2">High Incident Districts</p>
                    <div className="h-40">
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

        {/* 6. Accident Map */}
        <div className="glass-card p-6 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <HiShieldExclamation className="text-rose-400 w-5 h-5" />
                <h3 className="text-base font-bold text-surface-200">Accident Risk Density Map</h3>
              </div>
              <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-rose-500/15 text-rose-400 border border-rose-500/30">
                {accidentHeatmap.length.toLocaleString()} Incidents Mapped
              </span>
            </div>

            {heatmapLoading ? (
              <div className="h-72 flex items-center justify-center">
                <div className="w-8 h-8 border-2 border-rose-500/30 border-t-rose-400 rounded-full animate-spin" />
              </div>
            ) : (
              <div className="h-72 rounded-xl overflow-hidden relative border border-surface-800">
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

          <div className="flex items-center justify-between text-xs text-surface-400 pt-3 border-t border-surface-800/60 mt-2">
            <span className="flex items-center gap-3">
              <span className="inline-flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-rose-500" /> Fatal</span>
              <span className="inline-flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-amber-500" /> Injury</span>
            </span>
            <span>Karnataka Geographic Bounds</span>
          </div>
        </div>
      </div>

      {/* ── 7. RECENT ROUTES (Latest 5 User Journeys) ── */}
      <div className="glass-card p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <HiMap className="text-cyan-400 w-5 h-5" />
            <h3 className="text-base font-bold text-surface-200">Recent Route History</h3>
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
          <div className="h-32 flex items-center justify-center">
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
                  <th className="pb-3 font-semibold">From</th>
                  <th className="pb-3 font-semibold">To</th>
                  <th className="pb-3 font-semibold">Distance</th>
                  <th className="pb-3 font-semibold">Duration</th>
                  <th className="pb-3 font-semibold">Safety Score</th>
                  <th className="pb-3 font-semibold">Route Type</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-800/60">
                {history.slice(0, 5).map((r, i) => (
                  <tr key={i} className="hover:bg-surface-800/30 transition-colors">
                    <td className="py-3 font-medium text-surface-200 truncate max-w-[150px]">
                      {r.source_name || 'Origin Coordinate'}
                    </td>
                    <td className="py-3 font-medium text-surface-200 truncate max-w-[150px]">
                      {r.dest_name || 'Destination Coordinate'}
                    </td>
                    <td className="py-3 text-surface-300">
                      {r.distance_km ? `${r.distance_km.toFixed(1)} km` : '—'}
                    </td>
                    <td className="py-3 text-surface-300">
                      {r.duration_min ? `${Math.round(r.duration_min)} min` : '—'}
                    </td>
                    <td className="py-3">
                      <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-bold ${
                        (r.safety_score || 0) >= 80
                          ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30'
                          : (r.safety_score || 0) >= 60
                          ? 'bg-amber-500/15 text-amber-400 border border-amber-500/30'
                          : 'bg-rose-500/15 text-rose-400 border border-rose-500/30'
                      }`}>
                        {r.safety_score !== null && r.safety_score !== undefined
                          ? r.safety_score.toFixed(1)
                          : '—'}
                      </span>
                    </td>
                    <td className="py-3">
                      <span className="capitalize px-2 py-0.5 rounded text-[11px] font-semibold bg-surface-800 text-surface-300 border border-surface-700">
                        {r.route_type || 'balanced'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
