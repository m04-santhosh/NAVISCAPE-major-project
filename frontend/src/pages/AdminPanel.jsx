import { useState, useEffect } from 'react';
import api from '../services/api';
import toast from 'react-hot-toast';
import { HiUpload, HiUsers, HiChartBar, HiTrash, HiRefresh, HiBan, HiCheckCircle } from 'react-icons/hi';

export default function AdminPanel() {
  const [stats, setStats] = useState(null);
  const [users, setUsers] = useState([]);
  const [predictions, setPredictions] = useState(null);
  const [activeTab, setActiveTab] = useState('overview');
  const [uploading, setUploading] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => { loadData(); }, []);

  const loadData = async () => {
    try {
      const [statsRes, usersRes, predRes] = await Promise.all([
        api.get('/admin/stats'),
        api.get('/admin/users'),
        api.get('/admin/predictions-monitor'),
      ]);
      setStats(statsRes.data);
      setUsers(usersRes.data);
      setPredictions(predRes.data);
    } catch (err) { console.error(err); toast.error('Failed to load admin data'); } finally { setLoading(false); }
  };

  const uploadFile = async (endpoint, file) => {
    if (!file) return;
    setUploading(true);
    const formData = new FormData();
    formData.append('file', file);
    try {
      const res = await api.post(endpoint, formData, { headers: { 'Content-Type': 'multipart/form-data' } });
      toast.success(res.data.message);
      loadData();
    } catch (err) { toast.error(err.response?.data?.detail || 'Upload failed'); } finally { setUploading(false); }
  };

  const toggleUser = async (userId) => {
    try {
      const res = await api.put(`/admin/users/${userId}/toggle-active`);
      toast.success(res.data.message);
      loadData();
    } catch (err) { toast.error('Failed to update user'); }
  };

  const deleteUser = async (userId) => {
    if (!confirm('Are you sure?')) return;
    try {
      const res = await api.delete(`/admin/users/${userId}`);
      toast.success(res.data.message);
      loadData();
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed to delete user'); }
  };

  const tabs = [
    { id: 'overview', label: 'Overview', icon: HiChartBar },
    { id: 'users', label: 'Users', icon: HiUsers },
    { id: 'datasets', label: 'Datasets', icon: HiUpload },
    { id: 'models', label: 'Models', icon: HiRefresh },
  ];

  if (loading) return <div className="flex items-center justify-center h-full"><div className="w-12 h-12 border-4 border-primary-500/30 border-t-primary-500 rounded-full animate-spin" /></div>;

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl md:text-3xl font-bold text-surface-100">Admin Panel</h1>
        <p className="text-surface-400 mt-1">Manage datasets, users, and monitor system performance</p>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 flex-wrap">
        {tabs.map(tab => (
          <button key={tab.id} onClick={() => setActiveTab(tab.id)}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all ${
              activeTab === tab.id ? 'bg-primary-500/20 text-primary-400 border border-primary-500/30' : 'bg-surface-800/50 text-surface-400 border border-surface-700 hover:border-surface-600'}`}>
            <tab.icon className="w-4 h-4" />{tab.label}
          </button>
        ))}
      </div>

      {/* Overview */}
      {activeTab === 'overview' && stats && (
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {[
            { label: 'Total Users', value: stats.total_users, icon: HiUsers },
            { label: 'Total Routes', value: stats.total_routes, icon: HiChartBar },
            { label: 'Traffic Records', value: stats.total_traffic_records, icon: HiUpload },
            { label: 'Accident Records', value: stats.total_accident_records, icon: HiRefresh },
          ].map((card, i) => (
            <div key={i} className="stat-card">
              <card.icon className="w-5 h-5 text-primary-400 mb-3" />
              <p className="text-2xl font-bold text-surface-100">{card.value}</p>
              <p className="text-sm text-surface-400">{card.label}</p>
            </div>
          ))}
        </div>
      )}

      {/* Users */}
      {activeTab === 'users' && (
        <div className="glass-card p-6">
          <h3 className="text-lg font-semibold text-surface-200 mb-4">User Management ({users.length} users)</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-left text-surface-400 border-b border-surface-700">
                <th className="pb-3">Username</th><th className="pb-3">Email</th><th className="pb-3">Role</th><th className="pb-3">Status</th><th className="pb-3">Actions</th>
              </tr></thead>
              <tbody>
                {users.map(u => (
                  <tr key={u.id} className="border-b border-surface-800 hover:bg-surface-800/50">
                    <td className="py-3 text-surface-200 font-medium">{u.username}</td>
                    <td className="py-3 text-surface-300">{u.email}</td>
                    <td className="py-3"><span className={`badge ${u.is_admin ? 'bg-accent-500/20 text-accent-400' : 'bg-surface-600/20 text-surface-400'}`}>{u.is_admin ? 'Admin' : 'User'}</span></td>
                    <td className="py-3"><span className={`badge ${u.is_active ? 'badge-low' : 'badge-critical'}`}>{u.is_active ? 'Active' : 'Inactive'}</span></td>
                    <td className="py-3">
                      <div className="flex gap-2">
                        <button onClick={() => toggleUser(u.id)} className="p-1.5 rounded-lg hover:bg-surface-700 text-surface-400 hover:text-yellow-400 transition-colors" title="Toggle status">
                          {u.is_active ? <HiBan className="w-4 h-4" /> : <HiCheckCircle className="w-4 h-4" />}
                        </button>
                        {!u.is_admin && (
                          <button onClick={() => deleteUser(u.id)} className="p-1.5 rounded-lg hover:bg-red-500/10 text-surface-400 hover:text-red-400 transition-colors" title="Delete">
                            <HiTrash className="w-4 h-4" />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Datasets */}
      {activeTab === 'datasets' && (
        <div className="grid md:grid-cols-2 gap-6">
          {[
            { title: 'Traffic Dataset', desc: 'CSV with junction_id, latitude, longitude, timestamp, vehicle_count, avg_speed, congestion_level', endpoint: '/admin/upload-traffic' },
            { title: 'Accident Dataset', desc: 'CSV with latitude, longitude, severity, timestamp, weather_condition, road_condition, description, casualties', endpoint: '/admin/upload-accidents' },
          ].map((ds, i) => (
            <div key={i} className="glass-card p-6">
              <h3 className="text-lg font-semibold text-surface-200 mb-2">{ds.title}</h3>
              <p className="text-sm text-surface-400 mb-4">{ds.desc}</p>
              <label className={`flex flex-col items-center justify-center w-full h-32 border-2 border-dashed rounded-xl cursor-pointer transition-all ${
                uploading ? 'border-primary-500/50 bg-primary-500/5' : 'border-surface-600 hover:border-primary-500/50 hover:bg-surface-800/50'}`}>
                <HiUpload className="w-8 h-8 text-surface-400 mb-2" />
                <span className="text-sm text-surface-400">{uploading ? 'Uploading...' : 'Click to upload CSV'}</span>
                <input type="file" accept=".csv" className="hidden" disabled={uploading}
                  onChange={(e) => uploadFile(ds.endpoint, e.target.files[0])} />
              </label>
            </div>
          ))}
        </div>
      )}

      {/* Models Monitor */}
      {activeTab === 'models' && predictions && (
        <div className="grid md:grid-cols-2 gap-6">
          {Object.entries(predictions).map(([key, model]) => (
            <div key={key} className="glass-card p-6">
              <h3 className="text-lg font-semibold text-surface-200 mb-4">{model.name}</h3>
              <div className="space-y-3">
                {Object.entries(model).filter(([k]) => k !== 'name').map(([k, v]) => (
                  <div key={k} className="flex justify-between text-sm">
                    <span className="text-surface-400 capitalize">{k.replace(/_/g, ' ')}</span>
                    <span className={`font-medium ${typeof v === 'number' && v < 1 ? 'text-green-400' : 'text-surface-200'}`}>
                      {typeof v === 'number' ? (v < 1 ? `${(v*100).toFixed(1)}%` : v.toLocaleString()) : v}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
