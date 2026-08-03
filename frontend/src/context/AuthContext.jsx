import { createContext, useContext, useState, useEffect } from 'react';
import api from '../services/api';

const AuthContext = createContext();

export function AuthProvider({ children }) {
  const [user, setUser] = useState({
    id: 1,
    username: 'admin',
    full_name: 'Admin (Demo)',
    email: 'admin@naviscape.com',
    is_admin: true
  });
  const [token, setToken] = useState('demo-token');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.defaults.headers.common['Authorization'] = `Bearer ${token}`;
  }, []);

  const login = async (username, password) => { return user; };
  const register = async (username, email, password, full_name) => { return user; };
  const logout = () => {};

  return (
    <AuthContext.Provider value={{ user, token, loading, login, register, logout, isAuthenticated: true, isAdmin: true }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
