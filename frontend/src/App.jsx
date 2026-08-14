import { BrowserRouter, Routes, Route, Navigate, Outlet } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import { ThemeProvider } from './context/ThemeContext';
import { AuthProvider, useAuth } from './context/AuthContext';
import Sidebar from './components/layout/Sidebar';

import Home from './pages/Home';
import Navigation from './pages/Navigation';
import Analytics from './pages/Analytics';
import Login from './pages/Login';
import Register from './pages/Register';
import ForgotPin from './pages/ForgotPin';

/** Route guard: redirects unauthenticated users to /login */
function ProtectedRoute() {
  const { isAuthenticated, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-surface-950">
        <div className="w-12 h-12 border-4 border-primary-500/30 border-t-primary-500 rounded-full animate-spin" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return <Outlet />;
}

/** Route guard for public landing page: redirects authenticated users directly to /navigate */
function HomeRoute() {
  const { isAuthenticated, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-surface-950">
        <div className="w-12 h-12 border-4 border-primary-500/30 border-t-primary-500 rounded-full animate-spin" />
      </div>
    );
  }

  if (isAuthenticated) {
    return <Navigate to="/navigate" replace />;
  }

  return <Home />;
}

/** Route guard for public auth pages (redirects to /navigate if already logged in) */
function PublicOnlyRoute({ children }) {
  const { isAuthenticated, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-surface-950">
        <div className="w-12 h-12 border-4 border-primary-500/30 border-t-primary-500 rounded-full animate-spin" />
      </div>
    );
  }

  if (isAuthenticated) {
    return <Navigate to="/navigate" replace />;
  }

  return children;
}

/** Layout wrapper for authenticated app pages (full screen canvas with sleek compact sidebar) */
function AppLayout() {
  return (
    <div className="min-h-screen w-full relative bg-surface-950 overflow-hidden flex">
      <Sidebar />
      <main className="flex-1 min-h-screen w-full relative pl-16 transition-all duration-300">
        <Outlet />
      </main>
    </div>
  );
}

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <BrowserRouter>
          <Toaster
            position="top-right"
            toastOptions={{
              style: { background: '#1e293b', color: '#e2e8f0', border: '1px solid #334155', borderRadius: '12px' },
              success: { iconTheme: { primary: '#06b6d4', secondary: '#0f172a' } },
              error: { iconTheme: { primary: '#ef4444', secondary: '#0f172a' } },
            }}
          />
          <Routes>
            {/* Public landing page — redirects to /navigate if authenticated */}
            <Route path="/" element={<HomeRoute />} />

            {/* Public authentication screens */}
            <Route path="/login" element={<PublicOnlyRoute><Login /></PublicOnlyRoute>} />
            <Route path="/register" element={<PublicOnlyRoute><Register /></PublicOnlyRoute>} />
            <Route path="/forgot-pin" element={<PublicOnlyRoute><ForgotPin /></PublicOnlyRoute>} />

            {/* Authenticated application routes with compact sidebar */}
            <Route element={<ProtectedRoute />}>
              <Route element={<AppLayout />}>
                <Route path="/navigate" element={<Navigation />} />
                <Route path="/analytics" element={<Analytics />} />
              </Route>
            </Route>

            {/* Catch-all — redirects to / (which redirects authenticated users to /navigate) */}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </ThemeProvider>
  );
}


