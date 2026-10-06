import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { HiMail, HiLockClosed, HiArrowRight } from 'react-icons/hi';
import toast from 'react-hot-toast';

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ email: '', password: '' });
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.email || !form.password) {
      toast.error('Please enter both email and password');
      return;
    }
    setLoading(true);
    try {
      await login(form.email, form.password);
      toast.success('Welcome back to NAVISCAPE!');
      navigate('/navigate');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Invalid email or password');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen min-h-[100dvh] flex items-center justify-center p-4 bg-surface-950 relative overflow-hidden">
      {/* Ambient background glow elements */}
      <div className="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 w-96 h-96 bg-cyan-500/10 rounded-full blur-3xl pointer-events-none" />
      <div className="absolute bottom-10 right-10 w-80 h-80 bg-indigo-500/10 rounded-full blur-3xl pointer-events-none" />

      <div className="w-full max-w-md animate-fade-in relative z-10 space-y-6">
        {/* Header */}
        <div className="text-center space-y-2">
          <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-cyan-400 to-cyan-600 text-surface-950 font-black text-2xl flex items-center justify-center mx-auto shadow-xl shadow-cyan-500/20">
            N
          </div>
          <h1 className="text-3xl font-black text-white tracking-tight">NAVISCAPE</h1>
          <p className="text-surface-400 text-sm font-medium">Safe AI Navigation & Emergency Protection</p>
        </div>

        {/* Form Card */}
        <div className="glass-card p-6 sm:p-8 space-y-6 border border-surface-700/60 shadow-2xl">
          <div>
            <h2 className="text-lg font-bold text-surface-100">Sign In to Your Account</h2>
            <p className="text-xs text-surface-400 mt-1">Enter your credentials to access safe routes and emergency profile.</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="text-xs font-semibold text-surface-300 mb-1.5 block">Email Address</label>
              <div className="relative">
                <HiMail className="absolute left-3.5 top-1/2 -translate-y-1/2 text-surface-400 w-5 h-5" />
                <input
                  type="email"
                  className="input-field pl-11"
                  placeholder="name@example.com"
                  value={form.email}
                  onChange={(e) => setForm({ ...form, email: e.target.value })}
                  required
                />
              </div>
            </div>

            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="text-xs font-semibold text-surface-300 block">Password</label>
                <Link to="/forgot-pin" className="text-xs font-medium text-cyan-400 hover:text-cyan-300">
                  Forgot Password?
                </Link>
              </div>
              <div className="relative">
                <HiLockClosed className="absolute left-3.5 top-1/2 -translate-y-1/2 text-surface-400 w-5 h-5" />
                <input
                  type="password"
                  className="input-field pl-11"
                  placeholder="••••••••"
                  value={form.password}
                  onChange={(e) => setForm({ ...form, password: e.target.value })}
                  required
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="btn-primary w-full mt-2 text-sm font-bold tracking-wide"
            >
              {loading ? (
                <div className="w-5 h-5 border-2 border-surface-950/30 border-t-surface-950 rounded-full animate-spin" />
              ) : (
                <>
                  <span>Sign In</span>
                  <HiArrowRight className="w-4 h-4" />
                </>
              )}
            </button>
          </form>

          <div className="text-center text-xs text-surface-400 border-t border-surface-800/80 pt-4">
            Don't have an account yet?{' '}
            <Link to="/register" className="text-cyan-400 hover:text-cyan-300 font-bold">
              Create account
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}

