import { createContext, useContext, useState, useEffect, useCallback } from 'react';
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

  const login = useCallback(async (email, password) => {
    const res = await api.post('/auth/login', { email, password });
    _setSession(res.data.access_token, res.data.user);
    return res.data.user;
  }, [_setSession]);

  const register = useCallback(async (name, email, password, confirmPassword) => {
    const res = await api.post('/auth/register', {
      full_name: name,
      email,
      password,
      confirm_password: confirmPassword,
    });
    _setSession(res.data.access_token, res.data.user);
    return res.data.user;
  }, [_setSession]);

  const logout = useCallback(() => {
    localStorage.removeItem('naviscape-token');
    delete api.defaults.headers.common['Authorization'];
    setToken(null);
    setUser(null);
  }, []);

  const value = {
    user,
    token,
    loading,
    isAuthenticated: !!user,
    login,
    register,
    logout,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export const useAuth = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
};
