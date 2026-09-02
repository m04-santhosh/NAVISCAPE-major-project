import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import api from '../services/api';
import {
  auth,
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  signOut,
  onAuthStateChanged,
  getIdToken,
} from '../services/firebase';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(() => localStorage.getItem('naviscape-token'));
  const [loading, setLoading] = useState(true);

  // ── Listen to Firebase Auth state changes ──────────────────────────────────
  useEffect(() => {
    let unsubscribe = () => {};
    try {
      unsubscribe = onAuthStateChanged(auth, async (fbUser) => {
        if (fbUser) {
          try {
            const idToken = await getIdToken(fbUser, /* forceRefresh */ false);
            localStorage.setItem('naviscape-token', idToken);
            api.defaults.headers.common['Authorization'] = `Bearer ${idToken}`;
            setToken(idToken);

            // Fetch authoritative profile from backend
            const res = await api.get('/auth/me');
            setUser(res.data);
          } catch (err) {
            console.warn('Profile fetch after Firebase auth:', err);
            setUser({
              id: fbUser.uid,
              email: fbUser.email,
              full_name: fbUser.displayName || fbUser.email?.split('@')[0] || 'User',
              email_verified: fbUser.emailVerified,
              is_active: true,
            });
          }
        } else {
          // If no Firebase user, check for legacy or existing stored token
          const stored = localStorage.getItem('naviscape-token');
          if (stored) {
            try {
              api.defaults.headers.common['Authorization'] = `Bearer ${stored}`;
              const res = await api.get('/auth/me');
              setUser(res.data);
              setToken(stored);
            } catch {
              localStorage.removeItem('naviscape-token');
              delete api.defaults.headers.common['Authorization'];
              setUser(null);
              setToken(null);
            }
          } else {
            delete api.defaults.headers.common['Authorization'];
            setUser(null);
            setToken(null);
          }
        }
        setLoading(false);
      });
    } catch (e) {
      console.warn('Firebase onAuthStateChanged init fallback:', e);
      setLoading(false);
    }

    return () => unsubscribe();
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
    try {
      // 1. Authenticate with Firebase Client SDK
      const userCred = await signInWithEmailAndPassword(auth, email, password);
      const idToken = await getIdToken(userCred.user, true);
      _setSession(idToken, {
        id: userCred.user.uid,
        email: userCred.user.email,
        full_name: userCred.user.displayName || email.split('@')[0],
        email_verified: userCred.user.emailVerified,
        is_active: true,
      });

      // Sync with backend
      try {
        api.defaults.headers.common['Authorization'] = `Bearer ${idToken}`;
        const res = await api.get('/auth/me');
        setUser(res.data);
        return res.data;
      } catch {
        return userCred.user;
      }
    } catch (firebaseErr) {
      // Fallback to backend direct login if Firebase project credentials are dummy/offline
      console.warn('Firebase login attempt fallback to direct auth API:', firebaseErr.message);
      const res = await api.post('/auth/login', { email, password });
      _setSession(res.data.access_token, res.data.user);
      return res.data.user;
    }
  }, [_setSession]);

  const requestRegisterOtp = useCallback(async (name, email, password, confirmPassword) => {
    const res = await api.post('/auth/register', {
      full_name: name,
      email,
      password,
      confirm_password: confirmPassword,
    });
    return res.data;
  }, []);

  const verifyRegisterOtp = useCallback(async (name, email, password, confirmPassword, otp) => {
    const res = await api.post('/auth/register/verify-otp', {
      full_name: name,
      email,
      password,
      confirm_password: confirmPassword,
      otp: otp.trim(),
    });
    _setSession(res.data.access_token, res.data.user);
    return res.data.user;
  }, [_setSession]);

  const resendRegisterOtp = useCallback(async (email, name) => {
    const res = await api.post('/auth/register/resend-otp', {
      email,
      full_name: name,
    });
    return res.data;
  }, []);

  const register = useCallback(async (name, email, password, confirmPassword) => {
    return requestRegisterOtp(name, email, password, confirmPassword);
  }, [requestRegisterOtp]);

  const logout = useCallback(async () => {
    try {
      await signOut(auth);
    } catch (err) {
      console.warn('Firebase signOut error:', err);
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
    requestRegisterOtp,
    verifyRegisterOtp,
    resendRegisterOtp,
    logout,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export const useAuth = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
};
