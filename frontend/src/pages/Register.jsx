import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import {
  HiUser,
  HiMail,
  HiLockClosed,
  HiArrowRight,
} from 'react-icons/hi';
import toast from 'react-hot-toast';

export default function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();

  const [form, setForm] = useState({
    full_name: '',
    email: '',
    password: '',
    confirm_password: '',
  });

  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  const handleChange = (e) => {
    setForm({ ...form, [e.target.name]: e.target.value });
    if (errorMsg) setErrorMsg('');
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrorMsg('');

    if (!form.full_name.trim()) {
      toast.error('Please enter your full name');
      return;
    }
    if (!form.email) {
      toast.error('Please enter your email address');
      return;
    }
    if (form.password.length < 6) {
      toast.error('Password must be at least 6 characters');
      return;
    }
    if (form.password !== form.confirm_password) {
      toast.error('Passwords do not match');
      return;
    }

    setLoading(true);
    try {
      await register(
        form.full_name,
        form.email,
        form.password,
        form.confirm_password
      );
      toast.success('Account created successfully! Welcome to NAVISCAPE.');
      navigate('/navigate');
    } catch (err) {
      const msg = err.response?.data?.detail || 'Registration failed. Please try again.';
      setErrorMsg(msg);
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-surface-950">
      <div className="w-full max-w-md animate-fade-in">
        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-surface-100 tracking-tight">NAVISCAPE</h1>
          <p className="text-surface-400 mt-2">Create your account</p>
        </div>

        {/* Card */}
        <div className="glass-card p-8">
          {errorMsg && (
            <div className="mb-5 p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm text-center">
              {errorMsg}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-5">
            {/* Full Name */}
            <div>
              <label className="text-sm font-medium text-surface-300 mb-2 block">Full Name</label>
              <div className="relative">
                <HiUser className="absolute left-4 top-1/2 -translate-y-1/2 text-surface-400 w-5 h-5" />
                <input
                  type="text"
                  name="full_name"
                  className="input-field pl-12"
                  placeholder="John Doe"
                  value={form.full_name}
                  onChange={handleChange}
                  required
                />
              </div>
            </div>

            {/* Email */}
            <div>
              <label className="text-sm font-medium text-surface-300 mb-2 block">Email</label>
              <div className="relative">
                <HiMail className="absolute left-4 top-1/2 -translate-y-1/2 text-surface-400 w-5 h-5" />
                <input
                  type="email"
                  name="email"
                  className="input-field pl-12"
                  placeholder="user@gmail.com"
                  value={form.email}
                  onChange={handleChange}
                  required
                />
              </div>
            </div>

            {/* Password */}
            <div>
              <label className="text-sm font-medium text-surface-300 mb-2 block">Password</label>
              <div className="relative">
                <HiLockClosed className="absolute left-4 top-1/2 -translate-y-1/2 text-surface-400 w-5 h-5" />
                <input
                  type="password"
                  name="password"
                  className="input-field pl-12"
                  placeholder="Min. 6 characters"
                  value={form.password}
                  onChange={handleChange}
                  required
                />
              </div>
            </div>

            {/* Confirm Password */}
            <div>
              <label className="text-sm font-medium text-surface-300 mb-2 block">Confirm Password</label>
              <div className="relative">
                <HiLockClosed className="absolute left-4 top-1/2 -translate-y-1/2 text-surface-400 w-5 h-5" />
                <input
                  type="password"
                  name="confirm_password"
                  className="input-field pl-12"
                  placeholder="••••••••"
                  value={form.confirm_password}
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
                  <span>Create Account</span>
                  <HiArrowRight className="w-5 h-5" />
                </>
              )}
            </button>
          </form>

          <div className="mt-6 text-center text-sm text-surface-400 border-t border-surface-700/40 pt-5">
            Already have an account?{' '}
            <Link to="/login" className="text-primary-400 hover:text-primary-300 font-medium">
              Sign in
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
