import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { useTheme } from '../../context/ThemeContext';
import {
  HiHome, HiMap, HiChartBar, HiShieldCheck, HiCog,
  HiLogout, HiMenu, HiX, HiSun, HiMoon, HiUserCircle, HiInformationCircle
} from 'react-icons/hi';
import { useState } from 'react';

const navItems = [
  { to: '/dashboard', icon: HiHome, label: 'Dashboard' },
  { to: '/navigate', icon: HiMap, label: 'Navigation' },
  { to: '/analytics', icon: HiChartBar, label: 'Analytics' },
  { to: '/about', icon: HiInformationCircle, label: 'About' },
];

const adminItems = [
  { to: '/admin', icon: HiShieldCheck, label: 'Admin Panel' },
];

export default function Sidebar() {
  const { user, logout, isAdmin } = useAuth();
  const { isDark, toggleTheme } = useTheme();
  const navigate = useNavigate();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  const handleLogout = () => { logout(); navigate('/login'); };

  const linkClass = ({ isActive }) => isActive ? 'nav-link-active' : 'nav-link';

  const SidebarContent = () => (
    <div className="flex flex-col h-full">
      {/* Logo */}
      <div className="flex items-center gap-3 px-4 py-6 border-b border-surface-700/50">
        <div className="w-10 h-10 rounded-xl gradient-bg flex items-center justify-center font-bold text-white text-lg">N</div>
        {!collapsed && (
          <div className="animate-fade-in">
            <h1 className="text-lg font-bold gradient-text">NAVISCAPE</h1>
            <p className="text-xs text-surface-400">AI Navigation</p>
          </div>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        <p className={`text-xs font-semibold text-surface-500 uppercase px-4 mb-2 ${collapsed ? 'hidden' : ''}`}>Main Menu</p>
        {navItems.map(item => (
          <NavLink key={item.to} to={item.to} className={linkClass} onClick={() => setMobileOpen(false)}>
            <item.icon className="w-5 h-5 flex-shrink-0" />
            {!collapsed && <span>{item.label}</span>}
          </NavLink>
        ))}

        {isAdmin && (
          <>
            <p className={`text-xs font-semibold text-surface-500 uppercase px-4 mt-6 mb-2 ${collapsed ? 'hidden' : ''}`}>Admin</p>
            {adminItems.map(item => (
              <NavLink key={item.to} to={item.to} className={linkClass} onClick={() => setMobileOpen(false)}>
                <item.icon className="w-5 h-5 flex-shrink-0" />
                {!collapsed && <span>{item.label}</span>}
              </NavLink>
            ))}
          </>
        )}
      </nav>

      {/* Bottom section */}
      <div className="border-t border-surface-700/50 p-3 space-y-2">
        <button onClick={toggleTheme} className="nav-link w-full">
          {isDark ? <HiSun className="w-5 h-5" /> : <HiMoon className="w-5 h-5" />}
          {!collapsed && <span>{isDark ? 'Light Mode' : 'Dark Mode'}</span>}
        </button>
        <div className="nav-link cursor-default">
          <HiUserCircle className="w-5 h-5 text-primary-400" />
          {!collapsed && (
            <div className="overflow-hidden">
              <p className="text-sm font-medium text-surface-200 truncate">{user?.full_name || user?.username}</p>
              <p className="text-xs text-surface-500 truncate">{user?.email}</p>
            </div>
          )}
        </div>
        <button onClick={handleLogout} className="nav-link w-full text-red-400 hover:text-red-300 hover:bg-red-500/10">
          <HiLogout className="w-5 h-5" />
          {!collapsed && <span>Logout</span>}
        </button>
      </div>
    </div>
  );

  return (
    <>
      {/* Mobile toggle */}
      <button
        onClick={() => setMobileOpen(!mobileOpen)}
        className="fixed top-4 left-4 z-50 lg:hidden p-2 rounded-xl glass-card text-surface-200"
      >
        {mobileOpen ? <HiX className="w-6 h-6" /> : <HiMenu className="w-6 h-6" />}
      </button>

      {/* Mobile overlay */}
      {mobileOpen && (
        <div className="fixed inset-0 bg-black/50 z-40 lg:hidden" onClick={() => setMobileOpen(false)} />
      )}

      {/* Sidebar */}
      <aside className={`
        fixed top-0 left-0 h-full z-40 glass-card border-r border-surface-700/50 transition-all duration-300
        ${collapsed ? 'w-20' : 'w-64'}
        ${mobileOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
      `}>
        {/* Collapse toggle (desktop) */}
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="hidden lg:flex absolute -right-3 top-8 w-6 h-6 rounded-full bg-surface-700 border border-surface-600 items-center justify-center text-surface-300 hover:text-primary-400 hover:border-primary-500 transition-all"
        >
          {collapsed ? '→' : '←'}
        </button>
        <SidebarContent />
      </aside>
    </>
  );
}
