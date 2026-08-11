import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../services/api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(() => localStorage.getItem('naviscape-token'));
  const [loading, setLoading] = useState(true);

  // ── Rehydrate user from token on mount ────────────────────────────────────
  useEffect(() => {
    const rehydrate = async () => {
      const stored = localStorage.getItem('naviscape-token');
      if (!stored) {
        setLoading(false);
        return;
      }
      try {
        api.defaults.headers.common['Authorization'] = `Bearer ${stored}`;
        const res = await api.get('/auth/me');
        setUser(res.data);
        setToken(stored);
      } catch {
        // Token invalid or expired — clear it
        localStorage.removeItem('naviscape-token');
        delete api.defaults.headers.common['Authorization'];
        setUser(null);
        setToken(null);
      } finally {
        setLoading(false);
      }
    };
    rehydrate();
  }, []);

  // ── Sync token to Axios headers whenever it changes ───────────────────────
  useEffect(() => {
    if (token) {
      api.defaults.headers.common['Authorization'] = `Bearer ${token}`;
    } else {
      delete api.defaults.headers.common['Authorization'];
    }
  }, [token]);

  // ── Auth actions ──────────────────────────────────────────────────────────

  const _setSession = useCallback((accessToken, userData) => {
    localStorage.setItem('naviscape-token', accessToken);
    setToken(accessToken);
    setUser(userData);
  }, []);

  const login = useCallback(async (email, pin) => {
    const res = await api.post('/auth/login', { email, pin });
    _setSession(res.data.access_token, res.data.user);
    return res.data.user;
  }, [_setSession]);

  const logout = useCallback(() => {
    localStorage.removeItem('naviscape-token');
    setToken(null);
    setUser(null);
    // api interceptor handles the 401 redirect; direct logout goes to /login
  }, []);

  // ── OTP signup helpers (stateless — UI manages step state) ────────────────

  const sendSignupOTP = useCallback(async (email) => {
    const res = await api.post('/auth/send-signup-otp', { email });
    return res.data;
  }, []);

  const verifySignupOTP = useCallback(async (email, otp) => {
    const res = await api.post('/auth/verify-signup-otp', { email, otp });
    return res.data; // { verification_token, message }
  }, []);

  const setPin = useCallback(async (email, verificationToken, pin, confirmPin) => {
    const res = await api.post('/auth/set-pin', {
      email,
      verification_token: verificationToken,
      pin,
      confirm_pin: confirmPin,
    });
    _setSession(res.data.access_token, res.data.user);
    return res.data.user;
  }, [_setSession]);

  // ── Forgot PIN helpers ────────────────────────────────────────────────────

  const forgotPinSendOTP = useCallback(async (email) => {
    const res = await api.post('/auth/forgot-pin/send-otp', { email });
    return res.data;
  }, []);

  const forgotPinVerifyOTP = useCallback(async (email, otp) => {
    const res = await api.post('/auth/forgot-pin/verify-otp', { email, otp });
    return res.data; // { verification_token, message }
  }, []);

  const resetPin = useCallback(async (email, verificationToken, newPin, confirmPin) => {
    const res = await api.post('/auth/forgot-pin/reset', {
      email,
      verification_token: verificationToken,
      new_pin: newPin,
      confirm_pin: confirmPin,
    });
    return res.data; // { message }
  }, []);

  const value = {
    user,
    token,
    loading,
    isAuthenticated: !!user,
    login,
    logout,
    sendSignupOTP,
    verifySignupOTP,
    setPin,
    forgotPinSendOTP,
    forgotPinVerifyOTP,
    resetPin,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export const useAuth = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
};
