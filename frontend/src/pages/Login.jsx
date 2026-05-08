import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { HiMail, HiLockClosed, HiUser, HiArrowRight } from 'react-icons/hi';
import toast from 'react-hot-toast';

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ username: '', password: '' });
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await login(form.username, form.password);
      toast.success('Welcome back!');
      navigate('/dashboard');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-surface-950 relative overflow-hidden">
      {/* Background effects */}
      <div className="absolute inset-0">
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-primary-600/20 rounded-full blur-3xl animate-pulse-slow" />
        <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-accent-600/20 rounded-full blur-3xl animate-pulse-slow" style={{animationDelay: '1.5s'}} />
      </div>

      <div className="relative w-full max-w-md animate-slide-up">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="w-16 h-16 rounded-2xl gradient-bg flex items-center justify-center font-bold text-white text-2xl mx-auto mb-4 shadow-lg shadow-primary-500/30">N</div>
          <h1 className="text-3xl font-bold gradient-text">NAVISCAPE</h1>
          <p className="text-surface-400 mt-1">Sign in to your account</p>
        </div>

        {/* Form */}
        <div className="glass-card p-8">
          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label className="text-sm font-medium text-surface-300 mb-2 block">Username</label>
              <div className="relative">
                <HiUser className="absolute left-4 top-1/2 -translate-y-1/2 text-surface-400 w-5 h-5" />
                <input type="text" className="input-field pl-12" placeholder="Enter username" value={form.username}
                  onChange={e => setForm({...form, username: e.target.value})} required />
              </div>
            </div>
            <div>
              <label className="text-sm font-medium text-surface-300 mb-2 block">Password</label>
              <div className="relative">
                <HiLockClosed className="absolute left-4 top-1/2 -translate-y-1/2 text-surface-400 w-5 h-5" />
                <input type="password" className="input-field pl-12" placeholder="Enter password" value={form.password}
                  onChange={e => setForm({...form, password: e.target.value})} required />
              </div>
            </div>
            <button type="submit" disabled={loading} className="btn-primary w-full flex items-center justify-center gap-2">
              {loading ? <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : <><span>Sign In</span><HiArrowRight /></>}
            </button>
          </form>

          <div className="mt-6 text-center text-sm text-surface-400">
            Don't have an account?{' '}
            <Link to="/register" className="text-primary-400 hover:text-primary-300 font-medium">Create one</Link>
          </div>

          <div className="mt-4 p-3 rounded-xl bg-surface-800/50 border border-surface-700/50">
            <p className="text-xs text-surface-500 text-center">Demo: <span className="text-primary-400">admin</span> / <span className="text-primary-400">admin123</span></p>
          </div>
        </div>
      </div>
    </div>
  );
}
