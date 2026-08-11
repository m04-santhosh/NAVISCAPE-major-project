import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { HiMail, HiLockClosed, HiShieldCheck, HiArrowRight, HiArrowLeft, HiRefresh, HiCheckCircle } from 'react-icons/hi';
import toast from 'react-hot-toast';

export default function ForgotPin() {
  const { forgotPinSendOTP, forgotPinVerifyOTP, resetPin } = useAuth();
  const navigate = useNavigate();

  // Step 1: Enter Email, Step 2: Verify OTP, Step 3: Set New PIN, Step 4: Success
  const [step, setStep] = useState(1);
  const [email, setEmail] = useState('');
  const [otp, setOtp] = useState('');
  const [verificationToken, setVerificationToken] = useState('');
  const [newPin, setNewPin] = useState('');
  const [confirmPin, setConfirmPin] = useState('');
  const [loading, setLoading] = useState(false);

  // Resend cooldown timer
  const [cooldown, setCooldown] = useState(0);

  useEffect(() => {
    let timer;
    if (cooldown > 0) {
      timer = setInterval(() => setCooldown((c) => c - 1), 1000);
    }
    return () => clearInterval(timer);
  }, [cooldown]);

  // Step 1: Send OTP
  const handleSendOTP = async (e) => {
    e.preventDefault();
    if (!email) {
      toast.error('Please enter your email address');
      return;
    }
    setLoading(true);
    try {
      const res = await forgotPinSendOTP(email);
      toast.success(res.message || 'Verification code sent!');
      setStep(2);
      setCooldown(60);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to send verification code');
    } finally {
      setLoading(false);
    }
  };

  // Resend OTP
  const handleResendOTP = async () => {
    if (cooldown > 0) return;
    setLoading(true);
    try {
      await forgotPinSendOTP(email);
      toast.success('New verification code sent!');
      setCooldown(60);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to resend verification code');
    } finally {
      setLoading(false);
    }
  };

  // Step 2: Verify OTP
  const handleVerifyOTP = async (e) => {
    e.preventDefault();
    if (otp.length !== 6) {
      toast.error('Please enter the full 6-digit code');
      return;
    }
    setLoading(true);
    try {
      const res = await forgotPinVerifyOTP(email, otp);
      setVerificationToken(res.verification_token);
      toast.success('Code verified successfully!');
      setStep(3);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Invalid or expired verification code');
    } finally {
      setLoading(false);
    }
  };

  // Step 3: Reset PIN
  const handleResetPIN = async (e) => {
    e.preventDefault();
    if (newPin.length < 4 || newPin.length > 6) {
      toast.error('PIN must be 4 to 6 digits');
      return;
    }
    if (newPin !== confirmPin) {
      toast.error('PINs do not match');
      return;
    }
    setLoading(true);
    try {
      const res = await resetPin(email, verificationToken, newPin, confirmPin);
      toast.success(res.message || 'PIN updated successfully!');
      setStep(4);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to reset PIN');
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
          <p className="text-surface-400 mt-2">Reset your security PIN</p>
        </div>

        {/* Step indicator */}
        {step <= 3 && (
          <div className="flex items-center justify-between mb-6 px-4">
            {[
              { num: 1, label: 'Email' },
              { num: 2, label: 'Verify Code' },
              { num: 3, label: 'New PIN' },
            ].map((s) => (
              <div key={s.num} className="flex items-center gap-2">
                <div
                  className={`w-8 h-8 rounded-full flex items-center justify-center font-bold text-xs transition-all ${
                    step === s.num
                      ? 'bg-primary-500 text-white ring-4 ring-primary-500/20'
                      : step > s.num
                      ? 'bg-green-500/20 text-green-400 border border-green-500/40'
                      : 'bg-surface-800 text-surface-500 border border-surface-700'
                  }`}
                >
                  {step > s.num ? '✓' : s.num}
                </div>
                <span
                  className={`text-xs font-medium ${
                    step === s.num ? 'text-surface-200' : 'text-surface-500'
                  }`}
                >
                  {s.label}
                </span>
              </div>
            ))}
          </div>
        )}

        {/* Form Card */}
        <div className="glass-card p-8">
          {/* STEP 1: Enter Email */}
          {step === 1 && (
            <form onSubmit={handleSendOTP} className="space-y-5">
              <div>
                <label className="text-sm font-medium text-surface-300 mb-2 block">
                  Gmail / Email Address
                </label>
                <div className="relative">
                  <HiMail className="absolute left-4 top-1/2 -translate-y-1/2 text-surface-400 w-5 h-5" />
                  <input
                    type="email"
                    className="input-field pl-12"
                    placeholder="user@gmail.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                  />
                </div>
                <p className="text-xs text-surface-500 mt-1">
                  If an account exists, a 6-digit verification code will be sent.
                </p>
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
                    <span>Send Reset Code</span>
                    <HiArrowRight className="w-5 h-5" />
                  </>
                )}
              </button>
            </form>
          )}

          {/* STEP 2: Enter 6-Digit OTP */}
          {step === 2 && (
            <form onSubmit={handleVerifyOTP} className="space-y-5">
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-sm font-medium text-surface-300">Verification Code</label>
                  <button
                    type="button"
                    onClick={() => setStep(1)}
                    className="text-xs text-surface-400 hover:text-surface-200 flex items-center gap-1"
                  >
                    <HiArrowLeft className="w-3.5 h-3.5" /> Change email
                  </button>
                </div>
                <p className="text-xs text-surface-400 mb-3">
                  Sent to <span className="text-primary-400 font-medium">{email}</span>
                </p>
                <div className="relative">
                  <HiShieldCheck className="absolute left-4 top-1/2 -translate-y-1/2 text-surface-400 w-5 h-5" />
                  <input
                    type="text"
                    maxLength={6}
                    className="input-field pl-12 tracking-[0.5em] text-center text-xl font-mono font-bold"
                    placeholder="123456"
                    value={otp}
                    onChange={(e) => setOtp(e.target.value.replace(/\D/g, ''))}
                    required
                    autoFocus
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
                    <span>Verify Code</span>
                    <HiArrowRight className="w-5 h-5" />
                  </>
                )}
              </button>

              <div className="text-center pt-2">
                <button
                  type="button"
                  onClick={handleResendOTP}
                  disabled={cooldown > 0 || loading}
                  className={`text-xs font-medium flex items-center justify-center gap-1.5 mx-auto ${
                    cooldown > 0 ? 'text-surface-600 cursor-not-allowed' : 'text-primary-400 hover:text-primary-300'
                  }`}
                >
                  <HiRefresh className="w-3.5 h-3.5" />
                  {cooldown > 0 ? `Resend code in ${cooldown}s` : 'Resend code'}
                </button>
              </div>
            </form>
          )}

          {/* STEP 3: Create New PIN */}
          {step === 3 && (
            <form onSubmit={handleResetPIN} className="space-y-4">
              <div>
                <label className="text-sm font-medium text-surface-300 mb-1.5 block">
                  New Security PIN (4–6 digits)
                </label>
                <div className="relative">
                  <HiLockClosed className="absolute left-4 top-1/2 -translate-y-1/2 text-surface-400 w-5 h-5" />
                  <input
                    type="password"
                    maxLength={6}
                    className="input-field pl-12 tracking-widest text-lg font-mono"
                    placeholder="••••••"
                    value={newPin}
                    onChange={(e) => setNewPin(e.target.value.replace(/\D/g, ''))}
                    required
                  />
                </div>
              </div>

              <div>
                <label className="text-sm font-medium text-surface-300 mb-1.5 block">
                  Confirm New Security PIN
                </label>
                <div className="relative">
                  <HiLockClosed className="absolute left-4 top-1/2 -translate-y-1/2 text-surface-400 w-5 h-5" />
                  <input
                    type="password"
                    maxLength={6}
                    className="input-field pl-12 tracking-widest text-lg font-mono"
                    placeholder="••••••"
                    value={confirmPin}
                    onChange={(e) => setConfirmPin(e.target.value.replace(/\D/g, ''))}
                    required
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={loading}
                className="btn-primary w-full flex items-center justify-center gap-2 py-3 text-base font-semibold mt-2"
              >
                {loading ? (
                  <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                ) : (
                  <>
                    <span>Reset Security PIN</span>
                    <HiArrowRight className="w-5 h-5" />
                  </>
                )}
              </button>
            </form>
          )}

          {/* STEP 4: Success */}
          {step === 4 && (
            <div className="text-center py-4 space-y-4">
              <div className="w-16 h-16 rounded-full bg-green-500/20 text-green-400 flex items-center justify-center mx-auto border border-green-500/30">
                <HiCheckCircle className="w-10 h-10" />
              </div>
              <h3 className="text-xl font-bold text-surface-100">PIN Reset Successful</h3>
              <p className="text-sm text-surface-400">
                Your security PIN has been updated. You can now log in using your new PIN.
              </p>
              <button
                onClick={() => navigate('/login')}
                className="btn-primary w-full py-3 mt-4 text-base font-semibold"
              >
                Go to Sign In
              </button>
            </div>
          )}

          {step < 4 && (
            <div className="mt-6 text-center text-sm text-surface-400 border-t border-surface-700/40 pt-5">
              Remember your PIN?{' '}
              <Link to="/login" className="text-primary-400 hover:text-primary-300 font-medium">
                Sign in
              </Link>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
