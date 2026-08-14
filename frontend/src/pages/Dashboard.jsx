/**
 * [RETAINED / LEGACY COMPONENT]
 * Dashboard.jsx is retained for internal reference and is not exposed in the active user-facing navigation.
 */
import { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import api from '../services/api';
import { HiMap, HiShieldCheck, HiChartBar, HiTrendingUp, HiLocationMarker } from 'react-icons/hi';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';

export default function Dashboard() {
  const { user } = useAuth();
  const [traffic, setTraffic] = useState([]);
  const [history, setHistory] = useState([]);
  const [forecast, setForecast] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [trafficRes, historyRes, forecastRes] = await Promise.all([
        api.get('/traffic/current'),
        api.get('/route-history'),
        api.get('/predict/congestion-forecast'),
      ]);
      setTraffic(trafficRes.data);
      setHistory(historyRes.data);
      setForecast(forecastRes.data);
    } catch (err) {
      console.error('Dashboard load error:', err);
    } finally {
      setLoading(false);
    }
  };

  const avgSafety = history.length
    ? (history.reduce((a, r) => a + (r.safety_score || 0), 0) / history.length).toFixed(1)
    : '—';

  const statCards = [
    { icon: HiMap, label: 'Routes Taken', value: history.length },
    { icon: HiShieldCheck, label: 'Avg Safety Score', value: avgSafety },
    { icon: HiChartBar, label: 'Monitored Junctions', value: traffic.length || 0 },
    { icon: HiTrendingUp, label: 'Forecast Hours', value: forecast[0]?.forecasts?.length || 0 },
  ];

  const congestionBadge = (level) => {
    const cls = { low: 'badge-low', medium: 'badge-medium', high: 'badge-high', critical: 'badge-critical' };
    return <span className={`badge ${cls[level] || 'badge-low'}`}>{level}</span>;
  };

  // Chart data from first junction's forecast
  const chartData = forecast[0]?.forecasts?.map(f => ({
    hour: `${f.hour}:00`,
    vehicles: f.vehicle_count,
  })) || [];

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="w-10 h-10 border-3 border-primary-500/30 border-t-primary-500 rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div>
        <h1 className="text-2xl md:text-3xl font-bold text-surface-100">
          Welcome back, {user?.full_name || user?.username}
        </h1>
        <p className="text-surface-400 mt-1">Navigation overview and traffic status</p>
      </div>

      {/* Stat Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {statCards.map((card, i) => (
          <div key={i} className="stat-card">
            <card.icon className="w-5 h-5 text-primary-400 mb-3" />
            <p className="text-2xl font-bold text-surface-100">{card.value}</p>
            <p className="text-sm text-surface-400 mt-1">{card.label}</p>
          </div>
        ))}
      </div>

      {/* Charts Row */}
      <div className="grid lg:grid-cols-2 gap-6">
        {/* Traffic Forecast */}
        <div className="glass-card p-6">
          <h3 className="text-base font-semibold text-surface-200 mb-4">
            24h Traffic Forecast {forecast[0]?.junction_name ? `— ${forecast[0].junction_name}` : ''}
          </h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData}>
                <defs>
                  <linearGradient id="colorVehicles" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#06b6d4" stopOpacity={0.2} />
                    <stop offset="95%" stopColor="#06b6d4" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="hour" stroke="#64748b" fontSize={11} />
                <YAxis stroke="#64748b" fontSize={11} />
                <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8, color: '#e2e8f0' }} />
                <Area type="monotone" dataKey="vehicles" stroke="#06b6d4" fillOpacity={1} fill="url(#colorVehicles)" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Junction Status */}
        <div className="glass-card p-6">
          <h3 className="text-base font-semibold text-surface-200 mb-4">Live Junction Status</h3>
          <div className="space-y-2.5 max-h-64 overflow-y-auto pr-2">
            {traffic.map((t, i) => (
              <div key={i} className="flex items-center justify-between p-3 rounded-lg bg-surface-800/40 hover:bg-surface-800/70 transition-colors">
                <div className="flex items-center gap-3">
                  <HiLocationMarker className="w-4 h-4 text-primary-400" />
                  <div>
                    <p className="text-sm font-medium text-surface-200">{t.junction_name}</p>
                    <p className="text-xs text-surface-500">
                      {t.data_available ? `${t.vehicle_count || 0} vehicles · ${t.avg_speed ? t.avg_speed.toFixed(1) + ' km/h' : 'Speed N/A'}` : 'Data unavailable'}
                    </p>
                  </div>
                </div>
                {t.data_available ? congestionBadge(t.congestion_level) : <span className="badge bg-surface-800 text-surface-400 border border-surface-700 text-xs">Unavailable</span>}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Recent Routes */}
      <div className="glass-card p-6">
        <h3 className="text-base font-semibold text-surface-200 mb-4">Recent Routes</h3>
        {history.length === 0 ? (
          <p className="text-surface-500 text-center py-8">No routes yet. Try navigating first.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-surface-400 border-b border-surface-700">
                  <th className="pb-3 font-medium">From</th>
                  <th className="pb-3 font-medium">To</th>
                  <th className="pb-3 font-medium">Distance</th>
                  <th className="pb-3 font-medium">Duration</th>
                  <th className="pb-3 font-medium">Safety</th>
                  <th className="pb-3 font-medium">Type</th>
                </tr>
              </thead>
              <tbody>
                {history.slice(0, 5).map((r, i) => (
                  <tr key={i} className="border-b border-surface-800 hover:bg-surface-800/30 transition-colors">
                    <td className="py-3 text-surface-200">{r.source_name || 'Location A'}</td>
                    <td className="py-3 text-surface-200">{r.dest_name || 'Location B'}</td>
                    <td className="py-3 text-surface-300">{r.distance_km?.toFixed(1)} km</td>
                    <td className="py-3 text-surface-300">{r.duration_min?.toFixed(0)} min</td>
                    <td className="py-3">
                      <span className={`font-medium ${r.safety_score >= 80 ? 'text-green-400' : r.safety_score >= 60 ? 'text-yellow-400' : 'text-red-400'}`}>
                        {r.safety_score?.toFixed(1)}
                      </span>
                    </td>
                    <td className="py-3"><span className="badge bg-primary-500/15 text-primary-400">{r.route_type}</span></td>
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
