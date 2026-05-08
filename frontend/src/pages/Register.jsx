import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { HiMail, HiLockClosed, HiUser, HiArrowRight, HiIdentification } from 'react-icons/hi';
import toast from 'react-hot-toast';

export default function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ username: '', email: '', password: '', full_name: '' });
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await register(form.username, form.email, form.password, form.full_name);
      toast.success('Account created successfully!');
      navigate('/dashboard');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Registration failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-surface-950 relative overflow-hidden">
      <div className="absolute inset-0">
        <div className="absolute top-1/3 right-1/4 w-96 h-96 bg-accent-600/20 rounded-full blur-3xl animate-pulse-slow" />
        <div className="absolute bottom-1/3 left-1/4 w-96 h-96 bg-primary-600/20 rounded-full blur-3xl animate-pulse-slow" style={{animationDelay: '1.5s'}} />
      </div>

      <div className="relative w-full max-w-md animate-slide-up">
        <div className="text-center mb-8">
          <div className="w-16 h-16 rounded-2xl gradient-bg flex items-center justify-center font-bold text-white text-2xl mx-auto mb-4 shadow-lg shadow-primary-500/30">N</div>
          <h1 className="text-3xl font-bold gradient-text">NAVISCAPE</h1>
          <p className="text-surface-400 mt-1">Create your account</p>
        </div>

        <div className="glass-card p-8">
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="text-sm font-medium text-surface-300 mb-1.5 block">Full Name</label>
              <div className="relative">
                <HiIdentification className="absolute left-4 top-1/2 -translate-y-1/2 text-surface-400 w-5 h-5" />
                <input type="text" className="input-field pl-12" placeholder="John Doe" value={form.full_name}
                  onChange={e => setForm({...form, full_name: e.target.value})} />
              </div>
            </div>
            <div>
              <label className="text-sm font-medium text-surface-300 mb-1.5 block">Username</label>
              <div className="relative">
                <HiUser className="absolute left-4 top-1/2 -translate-y-1/2 text-surface-400 w-5 h-5" />
                <input type="text" className="input-field pl-12" placeholder="johndoe" value={form.username}
                  onChange={e => setForm({...form, username: e.target.value})} required />
              </div>
            </div>
            <div>
              <label className="text-sm font-medium text-surface-300 mb-1.5 block">Email</label>
              <div className="relative">
                <HiMail className="absolute left-4 top-1/2 -translate-y-1/2 text-surface-400 w-5 h-5" />
                <input type="email" className="input-field pl-12" placeholder="john@example.com" value={form.email}
                  onChange={e => setForm({...form, email: e.target.value})} required />
              </div>
            </div>
            <div>
              <label className="text-sm font-medium text-surface-300 mb-1.5 block">Password</label>
              <div className="relative">
                <HiLockClosed className="absolute left-4 top-1/2 -translate-y-1/2 text-surface-400 w-5 h-5" />
                <input type="password" className="input-field pl-12" placeholder="Min 6 characters" value={form.password}
                  onChange={e => setForm({...form, password: e.target.value})} required minLength={6} />
              </div>
            </div>
            <button type="submit" disabled={loading} className="btn-primary w-full flex items-center justify-center gap-2 mt-2">
              {loading ? <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : <><span>Create Account</span><HiArrowRight /></>}
            </button>
          </form>
          <div className="mt-6 text-center text-sm text-surface-400">
            Already have an account?{' '}
            <Link to="/login" className="text-primary-400 hover:text-primary-300 font-medium">Sign in</Link>
          </div>
        </div>
      </div>
    </div>
  );
}
