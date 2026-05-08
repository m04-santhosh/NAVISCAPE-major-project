import { useState, useEffect } from 'react';
import api from '../services/api';
import {
  AreaChart, Area, LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, Legend, RadarChart, Radar,
  PolarGrid, PolarAngleAxis, PolarRadiusAxis,
} from 'recharts';
import { MapContainer, TileLayer, CircleMarker, Popup } from 'react-leaflet';
import { HiChartBar, HiShieldExclamation, HiTrendingUp, HiLocationMarker } from 'react-icons/hi';
import 'leaflet/dist/leaflet.css';

export default function Analytics() {
  const [forecast, setForecast] = useState([]);
  const [accidentHeatmap, setAccidentHeatmap] = useState([]);
  const [selectedJunction, setSelectedJunction] = useState(1);
  const [prediction, setPrediction] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => { loadData(); }, []);

  const loadData = async () => {
    try {
      const [forecastRes, heatmapRes] = await Promise.all([
        api.get('/predict/congestion-forecast'),
        api.get('/predict/accident-heatmap'),
      ]);
      setForecast(forecastRes.data);
      setAccidentHeatmap(heatmapRes.data);
      // Load prediction for default junction
      await loadPrediction(1);
    } catch (err) { console.error(err); } finally { setLoading(false); }
  };

  const loadPrediction = async (jid) => {
    try {
      const res = await api.post('/predict/traffic', { junction_id: jid, hours_ahead: 24 });
      setPrediction(res.data);
      setSelectedJunction(jid);
    } catch (err) { console.error(err); }
  };

  const chartData = prediction?.predictions?.map(p => ({
    hour: `${p.hour}:00`,
    predicted: p.predicted_vehicle_count,
    confidence: Math.round(p.confidence * 100),
  })) || [];

  // Comparison data - all junctions at current hour
  const junctionComparison = forecast.map(f => {
    const currentHour = new Date().getHours();
    const current = f.forecasts?.find(fc => fc.hour === currentHour);
    return { name: f.junction_name?.split(' ')[0], vehicles: current?.vehicle_count || 0 };
  });

  // Congestion distribution
  const congestionDist = forecast.reduce((acc, f) => {
    f.forecasts?.forEach(fc => { acc[fc.congestion_level] = (acc[fc.congestion_level] || 0) + 1; });
    return acc;
  }, {});
  const congestionChartData = Object.entries(congestionDist).map(([k,v]) => ({ level: k, count: v }));
  const congestionColors = { low: '#22c55e', medium: '#eab308', high: '#f97316', critical: '#ef4444' };

  if (loading) {
    return <div className="flex items-center justify-center h-full"><div className="w-12 h-12 border-4 border-primary-500/30 border-t-primary-500 rounded-full animate-spin" /></div>;
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl md:text-3xl font-bold text-surface-100">Traffic <span className="gradient-text">Analytics</span></h1>
        <p className="text-surface-400 mt-1">AI-powered traffic predictions and risk analysis</p>
      </div>

      {/* Junction Selector */}
      <div className="flex gap-2 flex-wrap">
        {forecast.map((f) => (
          <button key={f.junction_id} onClick={() => loadPrediction(f.junction_id)}
            className={`px-4 py-2 rounded-xl text-sm font-medium transition-all ${selectedJunction === f.junction_id
              ? 'bg-primary-500/20 text-primary-400 border border-primary-500/30'
              : 'bg-surface-800/50 text-surface-400 border border-surface-700 hover:border-surface-600'}`}>
            {f.junction_name}
          </button>
        ))}
      </div>

      {/* Charts Grid */}
      <div className="grid lg:grid-cols-2 gap-6">
        {/* LSTM Prediction Chart */}
        <div className="glass-card p-6">
          <div className="flex items-center gap-2 mb-4">
            <HiTrendingUp className="text-primary-400 w-5 h-5" />
            <h3 className="text-lg font-semibold text-surface-200">LSTM Traffic Prediction (24h)</h3>
          </div>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData}>
                <defs>
                  <linearGradient id="predGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#a855f7" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#a855f7" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="hour" stroke="#64748b" fontSize={10} />
                <YAxis stroke="#64748b" fontSize={10} />
                <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 12, color: '#e2e8f0' }} />
                <Area type="monotone" dataKey="predicted" stroke="#a855f7" fill="url(#predGrad)" strokeWidth={2} name="Predicted Vehicles" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Junction Comparison */}
        <div className="glass-card p-6">
          <div className="flex items-center gap-2 mb-4">
            <HiChartBar className="text-cyan-400 w-5 h-5" />
            <h3 className="text-lg font-semibold text-surface-200">Junction Comparison (Now)</h3>
          </div>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={junctionComparison}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="name" stroke="#64748b" fontSize={10} />
                <YAxis stroke="#64748b" fontSize={10} />
                <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 12, color: '#e2e8f0' }} />
                <Bar dataKey="vehicles" fill="#06b6d4" radius={[6,6,0,0]} name="Vehicle Count" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Congestion Level Distribution */}
        <div className="glass-card p-6">
          <div className="flex items-center gap-2 mb-4">
            <HiChartBar className="text-orange-400 w-5 h-5" />
            <h3 className="text-lg font-semibold text-surface-200">Congestion Distribution</h3>
          </div>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={congestionChartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="level" stroke="#64748b" fontSize={11} />
                <YAxis stroke="#64748b" fontSize={11} />
                <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 12, color: '#e2e8f0' }} />
                <Bar dataKey="count" name="Occurrences" radius={[6,6,0,0]}>
                  {congestionChartData.map((entry, i) => (
                    <Bar key={i} fill={congestionColors[entry.level] || '#64748b'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Accident Risk Heatmap */}
        <div className="glass-card p-6">
          <div className="flex items-center gap-2 mb-4">
            <HiShieldExclamation className="text-red-400 w-5 h-5" />
            <h3 className="text-lg font-semibold text-surface-200">Accident Risk Heatmap</h3>
          </div>
          <div className="h-72 rounded-xl overflow-hidden">
            <MapContainer center={[12.9716, 77.5946]} zoom={11} className="h-full w-full" style={{ borderRadius: '0.75rem' }}>
              <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" attribution="&copy; OSM" />
              {accidentHeatmap.map((pt, i) => (
                <CircleMarker key={i} center={[pt.lat, pt.lng]} radius={pt.intensity * 10 + 3}
                  pathOptions={{
                    color: pt.severity >= 4 ? '#ef4444' : pt.severity >= 3 ? '#f97316' : '#eab308',
                    fillOpacity: 0.4, weight: 1,
                  }}>
                  <Popup>Severity: {pt.severity}/5 | Risk: {(pt.intensity*100).toFixed(0)}%</Popup>
                </CircleMarker>
              ))}
            </MapContainer>
          </div>
        </div>
      </div>

      {/* Model Info Cards */}
      <div className="grid md:grid-cols-2 gap-4">
        <div className="glass-card p-5">
          <h4 className="font-semibold text-surface-200 mb-3">🧠 LSTM Traffic Model</h4>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between"><span className="text-surface-400">Architecture</span><span className="text-surface-200">LSTM(64) → Dropout → LSTM(32) → Dense</span></div>
            <div className="flex justify-between"><span className="text-surface-400">Accuracy (MAE)</span><span className="text-green-400">12.5 vehicles</span></div>
            <div className="flex justify-between"><span className="text-surface-400">Input Window</span><span className="text-surface-200">24 hours</span></div>
            <div className="flex justify-between"><span className="text-surface-400">Training Data</span><span className="text-surface-200">2 years (140K+ records)</span></div>
          </div>
        </div>
        <div className="glass-card p-5">
          <h4 className="font-semibold text-surface-200 mb-3">🎯 XGBoost Risk Model</h4>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between"><span className="text-surface-400">Algorithm</span><span className="text-surface-200">XGBoost + Random Forest</span></div>
            <div className="flex justify-between"><span className="text-surface-400">Accuracy</span><span className="text-green-400">85%</span></div>
            <div className="flex justify-between"><span className="text-surface-400">Features</span><span className="text-surface-200">Location, Time, Weather, Road</span></div>
            <div className="flex justify-between"><span className="text-surface-400">Training Data</span><span className="text-surface-200">2,000 accident records</span></div>
          </div>
        </div>
      </div>
    </div>
  );
}
