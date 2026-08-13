import { useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { useTheme } from '../../context/ThemeContext';
import toast from 'react-hot-toast';
import {
  HiHome as IconHome,
  HiMap as IconMap,
  HiChartBar as IconAnalytics,
  HiInformationCircle as IconAbout,
  HiClock as IconHistory,
  HiShieldCheck as IconShield,
  HiChevronRight as IconRight,
  HiChevronLeft as IconLeft,
  HiSun as IconSun,
  HiMoon as IconMoon,
  HiUserCircle as IconUser,
  HiLogout as IconLogout
} from 'react-icons/hi';

const navItems = [
  { to: '/navigate', icon: IconMap, label: 'Navigation' },
  { to: '/dashboard', icon: IconHome, label: 'Dashboard' },
  { to: '/analytics', icon: IconAnalytics, label: 'Analytics' },
  { to: '/dashboard', icon: IconHistory, label: 'Route History' },
  {
    to: '#women-safety',
    icon: IconShield,
    label: 'Women Safety',
    isPlaceholder: true,
    badge: 'SOON'
  },
  { to: '/about', icon: IconAbout, label: 'About' },
];

export default function Sidebar() {
  const { user, logout } = useAuth();
  const { isDark, toggleTheme } = useTheme();
  const [collapsed, setCollapsed] = useState(true); // Collapsed by default
  const navigate = useNavigate();

  const handlePlaceholderClick = (e, item) => {
    if (item.isPlaceholder) {
      e.preventDefault();
      toast('Women Safety features are coming soon in Phase 2!', { icon: '🛡️' });
    }
  };

  return (
    <aside
      className={`
        fixed top-0 left-0 h-full z-[1001] bg-surface-900/95 backdrop-blur-xl border-r border-surface-800/80 shadow-2xl
        transition-all duration-300 flex flex-col justify-between select-none
        ${collapsed ? 'w-16' : 'w-56'}
      `}
    >
      {/* ===== TOP SECTION: LOGO & COLLAPSE TOGGLE ===== */}
      <div>
        <div className="flex items-center justify-between h-16 px-3 border-b border-surface-800/80">
          <button
            onClick={() => setCollapsed(!collapsed)}
            className="flex items-center gap-3 w-full focus:outline-none group"
            title={collapsed ? 'Expand Sidebar' : 'Collapse Sidebar'}
          >
            {/* Logo Icon */}
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-cyan-500/20 to-cyan-500/10 border border-cyan-500/40 text-cyan-400 font-black flex items-center justify-center text-lg flex-shrink-0 group-hover:border-cyan-400 shadow-md transition-all">
              N
            </div>
            {!collapsed && (
              <span className="font-black text-sm text-surface-100 tracking-tight truncate">
                NAVISCAPE
              </span>
            )}
          </button>
        </div>

        {/* Expand / Collapse Floating Toggle Arrow */}
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="absolute -right-3 top-20 w-6 h-6 rounded-full bg-surface-800 border border-surface-700 text-surface-300 hover:text-cyan-400 hover:border-cyan-500 flex items-center justify-center shadow-lg transition-all z-50"
          title={collapsed ? 'Expand Menu' : 'Collapse Menu'}
        >
          {collapsed ? <IconRight className="w-3.5 h-3.5" /> : <IconLeft className="w-3.5 h-3.5" />}
        </button>

        {/* ===== NAVIGATION MENU ITEMS ===== */}
        <nav className="p-2 space-y-1.5 mt-2">
          {navItems.map((item, i) => {
            const Icon = item.icon;
            if (item.isPlaceholder) {
              return (
                <a
                  key={i}
                  href={item.to}
                  onClick={(e) => handlePlaceholderClick(e, item)}
                  className={`
                    group relative flex items-center gap-3 px-3 py-2.5 rounded-xl text-xs font-semibold text-surface-400 hover:text-surface-200 hover:bg-surface-800/60 transition-all cursor-pointer
                    ${collapsed ? 'justify-center' : ''}
                  `}
                >
                  <Icon className="w-5 h-5 flex-shrink-0 text-pink-400" />
                  {!collapsed && (
                    <div className="flex items-center justify-between w-full truncate">
                      <span className="truncate">{item.label}</span>
                      <span className="text-[9px] font-black px-1.5 py-0.5 rounded bg-pink-500/20 text-pink-300 border border-pink-500/40 ml-1 flex-shrink-0">
                        {item.badge}
                      </span>
                    </div>
                  )}

                  {/* Collapsed Tooltip */}
                  {collapsed && (
                    <div className="absolute left-16 z-50 px-2.5 py-1 rounded-lg bg-surface-900 border border-surface-700 text-surface-200 text-xs font-semibold whitespace-nowrap shadow-xl opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity">
                      {item.label} <span className="text-[9px] text-pink-400 font-bold ml-1">({item.badge})</span>
                    </div>
                  )}
                </a>
              );
            }

            return (
              <NavLink
                key={i}
                to={item.to}
                className={({ isActive }) => `
                  group relative flex items-center gap-3 px-3 py-2.5 rounded-xl text-xs font-bold transition-all
                  ${collapsed ? 'justify-center' : ''}
                  ${isActive
                    ? 'bg-cyan-950/60 text-cyan-300 border border-cyan-500/40 shadow-sm'
                    : 'text-surface-400 hover:text-surface-100 hover:bg-surface-800/60'}
                `}
              >
                <Icon className="w-5 h-5 flex-shrink-0" />
                {!collapsed && <span className="truncate">{item.label}</span>}

                {/* Collapsed Tooltip */}
                {collapsed && (
                  <div className="absolute left-16 z-50 px-2.5 py-1 rounded-lg bg-surface-900 border border-surface-700 text-surface-200 text-xs font-semibold whitespace-nowrap shadow-xl opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity">
                    {item.label}
                  </div>
                )}
              </NavLink>
            );
          })}
        </nav>
      </div>

      {/* ===== BOTTOM SECTION: PROFILE, THEME & LOGOUT ===== */}
      <div className="p-2 border-t border-surface-800/80 space-y-1">
        {/* Theme Toggle */}
        <button
          onClick={toggleTheme}
          className={`
            group relative flex items-center gap-3 w-full px-3 py-2 rounded-xl text-xs font-semibold text-surface-400 hover:text-surface-100 hover:bg-surface-800/60 transition-all
            ${collapsed ? 'justify-center' : ''}
          `}
          title={isDark ? 'Switch to Light Theme' : 'Switch to Dark Theme'}
        >
          {isDark ? <IconSun className="w-5 h-5 text-amber-400 flex-shrink-0" /> : <IconMoon className="w-5 h-5 text-indigo-400 flex-shrink-0" />}
          {!collapsed && <span>{isDark ? 'Light Mode' : 'Dark Mode'}</span>}
          {collapsed && (
            <div className="absolute left-16 z-50 px-2.5 py-1 rounded-lg bg-surface-900 border border-surface-700 text-surface-200 text-xs font-semibold whitespace-nowrap shadow-xl opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity">
              {isDark ? 'Light Theme' : 'Dark Theme'}
            </div>
          )}
        </button>

        {/* User Profile Info */}
        <div
          className={`
            group relative flex items-center gap-3 w-full px-3 py-2 rounded-xl text-xs font-semibold text-surface-300
            ${collapsed ? 'justify-center' : ''}
          `}
        >
          <IconUser className="w-5 h-5 text-cyan-400 flex-shrink-0" />
          {!collapsed && (
            <div className="overflow-hidden truncate text-left">
              <p className="text-xs font-bold text-surface-200 truncate">{user?.email?.split('@')[0] || 'User'}</p>
              <p className="text-[9px] text-cyan-400">Verified User</p>
            </div>
          )}
          {collapsed && (
            <div className="absolute left-16 z-50 px-2.5 py-1 rounded-lg bg-surface-900 border border-surface-700 text-surface-200 text-xs font-semibold whitespace-nowrap shadow-xl opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity">
              {user?.email || 'User Account'}
            </div>
          )}
        </div>

        {/* Sign Out */}
        <button
          onClick={logout}
          className={`
            group relative flex items-center gap-3 w-full px-3 py-2 rounded-xl text-xs font-bold text-red-400 hover:text-red-300 hover:bg-red-500/10 transition-all
            ${collapsed ? 'justify-center' : ''}
          `}
          title="Sign Out"
        >
          <IconLogout className="w-5 h-5 flex-shrink-0" />
          {!collapsed && <span>Sign Out</span>}
          {collapsed && (
            <div className="absolute left-16 z-50 px-2.5 py-1 rounded-lg bg-surface-900 border border-surface-700 text-red-300 text-xs font-semibold whitespace-nowrap shadow-xl opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity">
              Sign Out
            </div>
          )}
        </button>
      </div>
    </aside>
  );
}
