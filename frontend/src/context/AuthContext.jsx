import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import api from '../services/api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(() => localStorage.getItem('naviscape-token'));
  const [loading, setLoading] = useState(true);

  // ── Sync token to Axios headers whenever it changes ───────────────────────
  useEffect(() => {
    if (token) {
      api.defaults.headers.common['Authorization'] = `Bearer ${token}`;
    } else {
      delete api.defaults.headers.common['Authorization'];
    }
  }, [token]);

  // ── Check existing JWT session on mount ───────────────────────────────────
  useEffect(() => {
    let isMounted = true;

    const restoreSession = async () => {
      const storedToken = localStorage.getItem('naviscape-token');
      if (storedToken) {
        try {
          api.defaults.headers.common['Authorization'] = `Bearer ${storedToken}`;
          const res = await api.get('/auth/me');
          if (isMounted) {
            setUser(res.data);
            setToken(storedToken);
          }
        } catch {
          if (isMounted) {
            localStorage.removeItem('naviscape-token');
            delete api.defaults.headers.common['Authorization'];
            setUser(null);
            setToken(null);
          }
        }
      } else {
        if (isMounted) {
          delete api.defaults.headers.common['Authorization'];
          setUser(null);
          setToken(null);
        }
      }
      if (isMounted) {
        setLoading(false);
      }
    };

    restoreSession();

    return () => {
      isMounted = false;
    };
  }, []);

  // ── Auth actions ──────────────────────────────────────────────────────────

  const _setSession = useCallback((accessToken, userData) => {
    localStorage.setItem('naviscape-token', accessToken);
    api.defaults.headers.common['Authorization'] = `Bearer ${accessToken}`;
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

  const logout = useCallback(async () => {
    try {
      await api.post('/auth/logout');
    } catch {
      // Ignore logout endpoint failures on network disconnect
    }
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
