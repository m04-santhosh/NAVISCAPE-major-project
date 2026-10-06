import { useState } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { useTheme } from '../../context/ThemeContext';
import {
  HiMap as IconMap,
  HiChartBar as IconAnalytics,
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
  { to: '/analytics', icon: IconAnalytics, label: 'Dashboard' },
  { to: '/women-safety', icon: IconShield, label: 'Safety', badge: 'SOS Active' },
];

export default function Sidebar() {
  const { user, logout } = useAuth();
  const { isDark, toggleTheme } = useTheme();
  const [collapsed, setCollapsed] = useState(true);
  const location = useLocation();

  return (
    <>
      {/* ========================================================================= */}
      {/* 1. DESKTOP SIDEBAR (md and up)                                            */}
      {/* ========================================================================= */}
      <aside
        className={`
          hidden md:flex fixed top-0 left-0 h-full z-[1001] bg-surface-900/95 backdrop-blur-2xl border-r border-surface-800/80 shadow-2xl
          transition-all duration-300 flex-col justify-between select-none
          ${collapsed ? 'w-16' : 'w-60'}
        `}
      >
        {/* TOP: BRAND LOGO & COLLAPSE TOGGLE */}
        <div>
          <div className="flex items-center justify-between h-16 px-3 border-b border-surface-800/80">
            <button
              onClick={() => setCollapsed(!collapsed)}
              className="flex items-center gap-3 w-full focus:outline-none group text-left"
              title={collapsed ? 'Expand Sidebar' : 'Collapse Sidebar'}
            >
              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-cyan-400 to-cyan-600 text-surface-950 font-black flex items-center justify-center text-lg flex-shrink-0 shadow-lg shadow-cyan-500/20 group-hover:scale-105 transition-all">
                N
              </div>
              {!collapsed && (
                <div className="overflow-hidden">
                  <span className="font-extrabold text-sm text-white tracking-wider block">
                    NAVISCAPE
                  </span>
                  <span className="text-[10px] text-cyan-400 font-semibold tracking-tight block">
                    Safe AI Navigation
                  </span>
                </div>
              )}
            </button>
          </div>

          {/* Floating Toggle Arrow */}
          <button
            onClick={() => setCollapsed(!collapsed)}
            className="absolute -right-3 top-20 w-6 h-6 rounded-full bg-surface-800 border border-surface-700 text-surface-300 hover:text-cyan-400 hover:border-cyan-500 flex items-center justify-center shadow-lg transition-all z-50"
            title={collapsed ? 'Expand Menu' : 'Collapse Menu'}
          >
            {collapsed ? <IconRight className="w-3.5 h-3.5" /> : <IconLeft className="w-3.5 h-3.5" />}
          </button>

          {/* MENU ITEMS */}
          <nav className="p-2 space-y-1.5 mt-3">
            {navItems.map((item, i) => {
              const Icon = item.icon;
              const isActive = location.pathname === item.to;
              return (
                <NavLink
                  key={i}
                  to={item.to}
                  className={`
                    group relative flex items-center gap-3 px-3 py-3 rounded-xl text-xs font-bold transition-all
                    ${collapsed ? 'justify-center' : ''}
                    ${isActive
                      ? 'bg-cyan-500/15 text-cyan-300 border border-cyan-500/30 shadow-md shadow-cyan-950/40'
                      : 'text-surface-400 hover:text-surface-100 hover:bg-surface-800/70'}
                  `}
                >
                  <Icon className={`w-5 h-5 flex-shrink-0 transition-transform ${isActive ? 'text-cyan-400 scale-110' : 'group-hover:scale-105'}`} />
                  {!collapsed && (
                    <div className="flex items-center justify-between w-full truncate">
                      <span className="truncate">{item.label}</span>
                      {item.to === '/women-safety' && (
                        <span className="w-2 h-2 rounded-full bg-rose-500 animate-ping ml-1" />
                      )}
                    </div>
                  )}

                  {/* Collapsed Tooltip */}
                  {collapsed && (
                    <div className="absolute left-16 z-50 px-3 py-1.5 rounded-xl bg-surface-900 border border-surface-700 text-white text-xs font-bold whitespace-nowrap shadow-2xl opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity">
                      {item.label}
                    </div>
                  )}
                </NavLink>
              );
            })}
          </nav>
        </div>

        {/* BOTTOM: PROFILE, THEME & LOGOUT */}
        <div className="p-2 border-t border-surface-800/80 space-y-1">
          {/* Theme Toggle */}
          <button
            onClick={toggleTheme}
            className={`
              group relative flex items-center gap-3 w-full px-3 py-2.5 rounded-xl text-xs font-semibold text-surface-400 hover:text-surface-100 hover:bg-surface-800/60 transition-all
              ${collapsed ? 'justify-center' : ''}
            `}
            title={isDark ? 'Switch to Light Theme' : 'Switch to Dark Theme'}
          >
            {isDark ? <IconSun className="w-5 h-5 text-amber-400 flex-shrink-0" /> : <IconMoon className="w-5 h-5 text-indigo-400 flex-shrink-0" />}
            {!collapsed && <span>{isDark ? 'Light Mode' : 'Dark Mode'}</span>}
            {collapsed && (
              <div className="absolute left-16 z-50 px-3 py-1.5 rounded-xl bg-surface-900 border border-surface-700 text-white text-xs font-semibold whitespace-nowrap shadow-2xl opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity">
                {isDark ? 'Light Mode' : 'Dark Mode'}
              </div>
            )}
          </button>

          {/* User Profile */}
          <div
            className={`
              group relative flex items-center gap-3 w-full px-3 py-2.5 rounded-xl text-xs font-semibold text-surface-300
              ${collapsed ? 'justify-center' : ''}
            `}
          >
            <div className="w-6 h-6 rounded-full bg-cyan-500/20 border border-cyan-500/40 text-cyan-300 font-bold flex items-center justify-center text-[10px] flex-shrink-0">
              {user?.email?.charAt(0).toUpperCase() || 'U'}
            </div>
            {!collapsed && (
              <div className="overflow-hidden truncate text-left">
                <p className="text-xs font-bold text-surface-200 truncate">{user?.email?.split('@')[0] || 'User'}</p>
                <p className="text-[10px] text-cyan-400 font-medium">Verified User</p>
              </div>
            )}
            {collapsed && (
              <div className="absolute left-16 z-50 px-3 py-1.5 rounded-xl bg-surface-900 border border-surface-700 text-white text-xs font-semibold whitespace-nowrap shadow-2xl opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity">
                {user?.email || 'User Account'}
              </div>
            )}
          </div>

          {/* Sign Out */}
          <button
            onClick={logout}
            className={`
              group relative flex items-center gap-3 w-full px-3 py-2.5 rounded-xl text-xs font-bold text-rose-400 hover:text-rose-300 hover:bg-rose-500/10 transition-all
              ${collapsed ? 'justify-center' : ''}
            `}
            title="Sign Out"
          >
            <IconLogout className="w-5 h-5 flex-shrink-0" />
            {!collapsed && <span>Sign Out</span>}
            {collapsed && (
              <div className="absolute left-16 z-50 px-3 py-1.5 rounded-xl bg-surface-900 border border-surface-700 text-rose-300 text-xs font-semibold whitespace-nowrap shadow-2xl opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity">
                Sign Out
              </div>
            )}
          </button>
        </div>
      </aside>

      {/* ========================================================================= */}
      {/* 2. MOBILE NAVIGATION SYSTEM (< md screens)                                 */}
      {/* ========================================================================= */}

      {/* Mobile Top Header */}
      <header className="md:hidden fixed top-0 left-0 right-0 h-14 z-[999] bg-surface-900/90 backdrop-blur-xl border-b border-surface-800/80 px-4 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-cyan-400 to-cyan-600 text-surface-950 font-black flex items-center justify-center text-sm shadow-md shadow-cyan-500/20">
            N
          </div>
          <span className="font-extrabold text-sm text-white tracking-wide">
            NAVISCAPE
          </span>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={toggleTheme}
            className="p-2 rounded-lg bg-surface-800/80 border border-surface-700/60 text-surface-300 active:scale-95"
            title="Toggle Theme"
          >
            {isDark ? <IconSun className="w-4 h-4 text-amber-400" /> : <IconMoon className="w-4 h-4 text-indigo-400" />}
          </button>
          
          <button
            onClick={logout}
            className="p-2 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 active:scale-95 text-xs font-bold flex items-center gap-1"
            title="Logout"
          >
            <IconLogout className="w-4 h-4" />
          </button>
        </div>
      </header>

      {/* Mobile Fixed Bottom Tab Bar */}
      <nav className="md:hidden fixed bottom-0 left-0 right-0 z-[1001] bg-surface-900/95 backdrop-blur-2xl border-t border-surface-800/90 px-3 py-2 pb-safe flex items-center justify-around shadow-2xl">
        {navItems.map((item, i) => {
          const Icon = item.icon;
          const isActive = location.pathname === item.to;
          return (
            <NavLink
              key={i}
              to={item.to}
              className={`
                flex flex-col items-center gap-1 px-4 py-1.5 rounded-xl transition-all min-w-[70px] active:scale-95
                ${isActive ? 'text-cyan-400 font-bold bg-cyan-950/50 border border-cyan-500/30' : 'text-surface-400 font-medium'}
              `}
            >
              <div className="relative">
                <Icon className={`w-5 h-5 ${isActive ? 'scale-110' : ''}`} />
                {item.to === '/women-safety' && (
                  <span className="absolute -top-1 -right-1 w-2.5 h-2.5 rounded-full bg-rose-500 animate-ping" />
                )}
              </div>
              <span className="text-[10px] tracking-tight">{item.label}</span>
            </NavLink>
          );
        })}
      </nav>
    </>
  );
}

