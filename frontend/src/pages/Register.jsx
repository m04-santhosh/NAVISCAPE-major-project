import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import {
  HiUser,
  HiMail,
  HiLockClosed,
  HiArrowRight,
  HiArrowLeft,
  HiKey,
  HiRefresh,
  HiClock,
  HiShieldCheck,
} from 'react-icons/hi';
import toast from 'react-hot-toast';

export default function Register() {
  const { requestRegisterOtp, verifyRegisterOtp, resendRegisterOtp } = useAuth();
  const navigate = useNavigate();

  // Step: 'FORM' | 'OTP'
  const [step, setStep] = useState('FORM');

  const [form, setForm] = useState({
    full_name: '',
    email: '',
    password: '',
    confirm_password: '',
  });

  const [otp, setOtp] = useState('');
  const [loading, setLoading] = useState(false);
  const [resending, setResending] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  // Timers for OTP: 60s resend cooldown, 600s (10 min) expiry countdown
  const [resendCooldown, setResendCooldown] = useState(60);
  const [expiresIn, setExpiresIn] = useState(600);

  useEffect(() => {
    let timer;
    if (step === 'OTP') {
      timer = setInterval(() => {
        setResendCooldown((prev) => (prev > 0 ? prev - 1 : 0));
        setExpiresIn((prev) => (prev > 0 ? prev - 1 : 0));
      }, 1000);
    }
    return () => {
      if (timer) clearInterval(timer);
    };
  }, [step]);

  const handleChange = (e) => {
    setForm({ ...form, [e.target.name]: e.target.value });
    if (errorMsg) setErrorMsg('');
  };

  const handleOtpChange = (e) => {
    const val = e.target.value.replace(/\D/g, '').slice(0, 6);
    setOtp(val);
    if (errorMsg) setErrorMsg('');
  };

  // Step 1: Request OTP / Submit Registration Details
  const handleRequestOtp = async (e) => {
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
      const res = await requestRegisterOtp(
        form.full_name,
        form.email,
        form.password,
        form.confirm_password
      );
      setStep('OTP');
      setOtp('');
      setResendCooldown(60);
      setExpiresIn(600);
      toast.success(res.message || 'Verification code sent to your email!');
    } catch (err) {
      const msg = err.response?.data?.detail || 'Failed to send verification code. Please try again.';
      setErrorMsg(msg);
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  };

  // Step 2: Verify OTP & Complete Account Creation
  const handleVerifyOtp = async (e) => {
    e.preventDefault();
    setErrorMsg('');

    if (!otp || otp.length !== 6) {
      toast.error('Please enter the complete 6-digit verification code');
      return;
    }

    setLoading(true);
    try {
      await verifyRegisterOtp(
        form.full_name,
        form.email,
        form.password,
        form.confirm_password,
        otp
      );
      toast.success('Account verified and created successfully! Welcome to NAVISCAPE.');
      navigate('/navigate');
    } catch (err) {
      const msg = err.response?.data?.detail || 'Invalid or expired verification code.';
      setErrorMsg(msg);
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  };

  // Resend OTP handler
  const handleResendOtp = async () => {
    if (resendCooldown > 0 || resending) return;
    setResending(true);
    setErrorMsg('');
    try {
      const res = await resendRegisterOtp(form.email, form.full_name);
      setResendCooldown(60);
      setExpiresIn(600);
      toast.success(res.message || 'New verification code sent to your email!');
    } catch (err) {
      const msg = err.response?.data?.detail || 'Failed to resend verification code.';
      setErrorMsg(msg);
      toast.error(msg);
    } finally {
      setResending(false);
    }
  };

  // Format MM:SS for expiry timer
  const formatTime = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-surface-950">
      <div className="w-full max-w-md animate-fade-in">
        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-surface-100 tracking-tight">NAVISCAPE</h1>
          <p className="text-surface-400 mt-2">
            {step === 'FORM' ? 'Create your account' : 'Verify your email'}
          </p>
        </div>

        {/* Card */}
        <div className="glass-card p-8">
          {errorMsg && (
            <div className="mb-5 p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm text-center">
              {errorMsg}
            </div>
          )}

          {step === 'FORM' ? (
            /* ── STEP 1: Registration Input Details ── */
            <form onSubmit={handleRequestOtp} className="space-y-5">
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
                    <span>Continue to Verification</span>
                    <HiArrowRight className="w-5 h-5" />
                  </>
                )}
              </button>
            </form>
          ) : (
            /* ── STEP 2: OTP Verification Screen ── */
            <form onSubmit={handleVerifyOtp} className="space-y-6">
              <div className="text-center space-y-2">
                <div className="w-14 h-14 rounded-full bg-primary-500/20 text-primary-400 flex items-center justify-center mx-auto border border-primary-500/30">
                  <HiShieldCheck className="w-8 h-8" />
                </div>
                <h3 className="text-lg font-semibold text-surface-100">Check Your Email</h3>
                <p className="text-sm text-surface-400">
                  We sent a 6-digit verification code to:
                </p>
                <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-surface-800/80 border border-surface-700 text-sm font-medium text-primary-300">
                  <HiMail className="w-4 h-4" />
                  <span>{form.email}</span>
                </div>
              </div>

              {/* 6-Digit OTP Input */}
              <div>
                <label className="text-sm font-medium text-surface-300 mb-2 block text-center">
                  Enter 6-Digit Verification Code
                </label>
                <div className="relative">
                  <HiKey className="absolute left-4 top-1/2 -translate-y-1/2 text-surface-400 w-5 h-5" />
                  <input
                    type="text"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    maxLength={6}
                    className="input-field pl-12 text-center text-2xl font-mono font-bold tracking-[0.4em] text-primary-300 placeholder:text-surface-600"
                    placeholder="••••••"
                    value={otp}
                    onChange={handleOtpChange}
                    autoFocus
                    required
                  />
                </div>
              </div>

              {/* Expiration Timer Indicator */}
              <div className="flex items-center justify-between text-xs text-surface-400 px-1">
                <div className="flex items-center gap-1">
                  <HiClock className="w-4 h-4 text-primary-400" />
                  <span>
                    Expires in:{' '}
                    <strong className={expiresIn < 60 ? 'text-red-400' : 'text-surface-200'}>
                      {formatTime(expiresIn)}
                    </strong>
                  </span>
                </div>

                {/* Resend button */}
                <button
                  type="button"
                  onClick={handleResendOtp}
                  disabled={resendCooldown > 0 || resending}
                  className="text-primary-400 hover:text-primary-300 disabled:text-surface-500 disabled:cursor-not-allowed font-medium inline-flex items-center gap-1 transition-colors"
                >
                  <HiRefresh className={`w-3.5 h-3.5 ${resending ? 'animate-spin' : ''}`} />
                  {resendCooldown > 0 ? `Resend code (${resendCooldown}s)` : 'Resend code'}
                </button>
              </div>

              {/* Submit Button */}
              <button
                type="submit"
                disabled={loading || otp.length !== 6}
                className="btn-primary w-full flex items-center justify-center gap-2 py-3 text-base font-semibold disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loading ? (
                  <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                ) : (
                  <>
                    <span>Verify & Create Account</span>
                    <HiArrowRight className="w-5 h-5" />
                  </>
                )}
              </button>

              {/* Back to change details */}
              <div className="text-center pt-2">
                <button
                  type="button"
                  onClick={() => {
                    setStep('FORM');
                    setErrorMsg('');
                  }}
                  className="text-xs text-surface-400 hover:text-surface-200 inline-flex items-center gap-1"
                >
                  <HiArrowLeft className="w-3.5 h-3.5" />
                  <span>Change registration details</span>
                </button>
              </div>
            </form>
          )}

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
