import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { HiLockClosed, HiArrowRight, HiCheckCircle, HiShieldCheck } from 'react-icons/hi';
import toast from 'react-hot-toast';
import api from '../services/api';

export default function ForgotPassword() {
  const { isAuthenticated } = useAuth();
  const navigate = useNavigate();

  const [form, setForm] = useState({
    current_password: '',
    new_password: '',
    confirm_new_password: '',
  });
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);

  const handleChange = (e) => setForm({ ...form, [e.target.name]: e.target.value });

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (form.new_password.length < 6) {
      toast.error('New password must be at least 6 characters');
      return;
    }
    if (form.new_password !== form.confirm_new_password) {
      toast.error('New passwords do not match');
      return;
    }

    setLoading(true);
    try {
      await api.post('/auth/change-password', {
        current_password: form.current_password,
        new_password: form.new_password,
        confirm_new_password: form.confirm_new_password,
      });
      setSuccess(true);
      toast.success('Password updated successfully!');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to update password. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  // If not authenticated, show a helpful message pointing to login
  if (!isAuthenticated) {
    return (
      <div className="min-h-screen flex items-center justify-center p-4 bg-surface-950">
        <div className="w-full max-w-md animate-fade-in">
          <div className="text-center mb-8">
            <h1 className="text-3xl font-bold text-surface-100 tracking-tight">NAVISCAPE</h1>
            <p className="text-surface-400 mt-2">Change your password</p>
          </div>

          <div className="glass-card p-8 text-center space-y-4">
            <div className="w-16 h-16 rounded-full bg-primary-500/20 text-primary-400 flex items-center justify-center mx-auto border border-primary-500/30">
              <HiShieldCheck className="w-9 h-9" />
            </div>
            <h3 className="text-lg font-semibold text-surface-100">Sign in to change your password</h3>
            <p className="text-sm text-surface-400 leading-relaxed">
              To update your password, please sign in to your account first. You can change your password from the settings once logged in.
            </p>
            <button
              onClick={() => navigate('/login')}
              className="btn-primary w-full py-3 font-semibold text-base mt-2 flex items-center justify-center gap-2"
            >
              <span>Go to Sign In</span>
              <HiArrowRight className="w-5 h-5" />
            </button>
            <div className="text-center text-sm text-surface-500">
              Don't have an account?{' '}
              <Link to="/register" className="text-primary-400 hover:text-primary-300 font-medium">
                Create one
              </Link>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-surface-950">
      <div className="w-full max-w-md animate-fade-in">
        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-surface-100 tracking-tight">NAVISCAPE</h1>
          <p className="text-surface-400 mt-2">Change your password</p>
        </div>

        {/* Form Card */}
        <div className="glass-card p-8">
          {success ? (
            /* Success State */
            <div className="text-center py-4 space-y-4">
              <div className="w-16 h-16 rounded-full bg-green-500/20 text-green-400 flex items-center justify-center mx-auto border border-green-500/30">
                <HiCheckCircle className="w-10 h-10" />
              </div>
              <h3 className="text-xl font-bold text-surface-100">Password Updated</h3>
              <p className="text-sm text-surface-400">
                Your password has been changed successfully.
              </p>
              <button
                onClick={() => navigate('/navigate')}
                className="btn-primary w-full py-3 mt-4 text-base font-semibold"
              >
                Back to App
              </button>
            </div>
          ) : (
            /* Change Password Form */
            <form onSubmit={handleSubmit} className="space-y-5">
              <div>
                <label className="text-sm font-medium text-surface-300 mb-2 block">Current Password</label>
                <div className="relative">
                  <HiLockClosed className="absolute left-4 top-1/2 -translate-y-1/2 text-surface-400 w-5 h-5" />
                  <input
                    type="password"
                    name="current_password"
                    className="input-field pl-12"
                    placeholder="Your current password"
                    value={form.current_password}
                    onChange={handleChange}
                    required
                  />
                </div>
              </div>

              <div>
                <label className="text-sm font-medium text-surface-300 mb-2 block">New Password</label>
                <div className="relative">
                  <HiLockClosed className="absolute left-4 top-1/2 -translate-y-1/2 text-surface-400 w-5 h-5" />
                  <input
                    type="password"
                    name="new_password"
                    className="input-field pl-12"
                    placeholder="Min. 6 characters"
                    value={form.new_password}
                    onChange={handleChange}
                    required
                  />
                </div>
              </div>

              <div>
                <label className="text-sm font-medium text-surface-300 mb-2 block">Confirm New Password</label>
                <div className="relative">
                  <HiLockClosed className="absolute left-4 top-1/2 -translate-y-1/2 text-surface-400 w-5 h-5" />
                  <input
                    type="password"
                    name="confirm_new_password"
                    className="input-field pl-12"
                    placeholder="••••••••"
                    value={form.confirm_new_password}
                    onChange={handleChange}
                    required
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={loading}
                className="btn-primary w-full flex items-center justify-center gap-2 py-3 text-base font-semibold"
              >
                {loading ? (
                  <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                ) : (
                  <>
                    <span>Update Password</span>
                    <HiArrowRight className="w-5 h-5" />
                  </>
                )}
              </button>
            </form>
          )}

          {!success && (
            <div className="mt-6 text-center text-sm text-surface-400 border-t border-surface-700/40 pt-5">
              <Link to="/navigate" className="text-primary-400 hover:text-primary-300 font-medium">
                ← Back to app
              </Link>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
