import { BrowserRouter, Routes, Route, Navigate, Outlet } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import { ThemeProvider } from './context/ThemeContext';
import { AuthProvider } from './context/AuthContext';
import Sidebar from './components/layout/Sidebar';

import Home from './pages/Home';
import Dashboard from './pages/Dashboard';
import Navigation from './pages/Navigation';
import Analytics from './pages/Analytics';
import AdminPanel from './pages/AdminPanel';
import About from './pages/About';

/** Layout wrapper with sidebar */
function AppLayout() {
  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 lg:ml-64 p-4 md:p-6 pt-16 lg:pt-6 transition-all duration-300">
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
            {/* Public routes */}
            <Route path="/" element={<Home />} />

            {/* App routes with sidebar */}
            <Route element={<AppLayout />}>
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/navigate" element={<Navigation />} />
              <Route path="/analytics" element={<Analytics />} />
              <Route path="/about" element={<About />} />
              <Route path="/admin" element={<AdminPanel />} />
            </Route>

            {/* Catch-all */}
            <Route path="*" element={<Navigate to="/" />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </ThemeProvider>
  );
}
