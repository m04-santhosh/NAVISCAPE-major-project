import { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import api from '../services/api';
import { HiMap, HiShieldCheck, HiChartBar, HiClock, HiTrendingUp, HiLocationMarker } from 'react-icons/hi';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, BarChart, Bar, CartesianGrid } from 'recharts';

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

  const statCards = [
    { icon: HiMap, label: 'Total Routes', value: history.length || 0, color: 'from-cyan-500 to-blue-500', change: '+12%' },
    { icon: HiShieldCheck, label: 'Avg Safety Score', value: history.length ? (history.reduce((a,r) => a + (r.safety_score||0), 0) / history.length).toFixed(1) : '0', color: 'from-green-500 to-emerald-500', change: '+5%' },
    { icon: HiChartBar, label: 'Active Junctions', value: traffic.length || 8, color: 'from-purple-500 to-pink-500', change: 'Live' },
    { icon: HiTrendingUp, label: 'Predictions Today', value: Math.floor(Math.random() * 200) + 50, color: 'from-orange-500 to-red-500', change: '+28%' },
  ];

  const congestionBadge = (level) => {
    const cls = { low: 'badge-low', medium: 'badge-medium', high: 'badge-high', critical: 'badge-critical' };
    return <span className={`badge ${cls[level] || 'badge-low'}`}>{level}</span>;
  };

  // Prepare chart data from first junction's forecast
  const chartData = forecast[0]?.forecasts?.map(f => ({
    hour: `${f.hour}:00`,
    vehicles: f.vehicle_count,
  })) || [];

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="w-12 h-12 border-4 border-primary-500/30 border-t-primary-500 rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div>
        <h1 className="text-2xl md:text-3xl font-bold text-surface-100">
          Welcome back, <span className="gradient-text">{user?.full_name || user?.username}</span>
        </h1>
        <p className="text-surface-400 mt-1">Here's your navigation intelligence overview</p>
      </div>

      {/* Stat Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {statCards.map((card, i) => (
          <div key={i} className="stat-card animate-slide-up" style={{ animationDelay: `${i * 0.1}s` }}>
            <div className="flex items-start justify-between mb-4">
              <div className={`w-11 h-11 rounded-xl bg-gradient-to-r ${card.color} flex items-center justify-center`}>
                <card.icon className="w-5 h-5 text-white" />
              </div>
              <span className="text-xs font-medium text-green-400 bg-green-500/10 px-2 py-1 rounded-lg">{card.change}</span>
            </div>
            <p className="text-2xl font-bold text-surface-100">{card.value}</p>
            <p className="text-sm text-surface-400 mt-1">{card.label}</p>
          </div>
        ))}
      </div>

      {/* Charts Row */}
      <div className="grid lg:grid-cols-2 gap-6">
        {/* Traffic Forecast Chart */}
        <div className="glass-card p-6">
          <h3 className="text-lg font-semibold text-surface-200 mb-4">24h Traffic Forecast — Silk Board</h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData}>
                <defs>
                  <linearGradient id="colorVehicles" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#06b6d4" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#06b6d4" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="hour" stroke="#64748b" fontSize={11} />
                <YAxis stroke="#64748b" fontSize={11} />
                <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 12, color: '#e2e8f0' }} />
                <Area type="monotone" dataKey="vehicles" stroke="#06b6d4" fillOpacity={1} fill="url(#colorVehicles)" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Junction Status */}
        <div className="glass-card p-6">
          <h3 className="text-lg font-semibold text-surface-200 mb-4">Live Junction Status</h3>
          <div className="space-y-3 max-h-64 overflow-y-auto pr-2">
            {traffic.map((t, i) => (
              <div key={i} className="flex items-center justify-between p-3 rounded-xl bg-surface-800/50 hover:bg-surface-800 transition-colors">
                <div className="flex items-center gap-3">
                  <HiLocationMarker className="w-5 h-5 text-primary-400" />
                  <div>
                    <p className="text-sm font-medium text-surface-200">{t.junction_name}</p>
                    <p className="text-xs text-surface-500">{t.vehicle_count} vehicles • {t.avg_speed} km/h</p>
                  </div>
                </div>
                {congestionBadge(t.congestion_level)}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Recent Routes */}
      <div className="glass-card p-6">
        <h3 className="text-lg font-semibold text-surface-200 mb-4">Recent Routes</h3>
        {history.length === 0 ? (
          <p className="text-surface-500 text-center py-8">No routes yet. Start navigating!</p>
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
                  <tr key={i} className="border-b border-surface-800 hover:bg-surface-800/50 transition-colors">
                    <td className="py-3 text-surface-200">{r.source_name || 'Location A'}</td>
                    <td className="py-3 text-surface-200">{r.dest_name || 'Location B'}</td>
                    <td className="py-3 text-surface-300">{r.distance_km?.toFixed(1)} km</td>
                    <td className="py-3 text-surface-300">{r.duration_min?.toFixed(0)} min</td>
                    <td className="py-3">
                      <span className={`font-semibold ${r.safety_score >= 80 ? 'text-green-400' : r.safety_score >= 60 ? 'text-yellow-400' : 'text-red-400'}`}>
                        {r.safety_score?.toFixed(1)}
                      </span>
                    </td>
                    <td className="py-3"><span className="badge bg-primary-500/20 text-primary-400">{r.route_type}</span></td>
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
