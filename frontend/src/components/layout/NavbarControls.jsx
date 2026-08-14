import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { useTheme } from '../../context/ThemeContext';
import {
  HiSun,
  HiMoon,
  HiUserCircle,
  HiLogout,
  HiChartBar,
  HiChevronDown,
  HiMap
} from 'react-icons/hi';

export default function NavbarControls({ showTraffic, onToggleTraffic }) {
  const { user, logout } = useAuth();
  const { isDark, toggleTheme } = useTheme();
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const dropdownRef = useRef(null);
  const navigate = useNavigate();

  // Close dropdown on outside click
  useEffect(() => {
    function handleClickOutside(event) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setDropdownOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  return (
    <div className="fixed top-4 right-4 z-[1000] flex items-center gap-2 pointer-events-auto">
      {/* Live Traffic Toggle Button */}
      <button
        onClick={onToggleTraffic}
        title={showTraffic ? 'Hide Live Traffic Layer' : 'Show Live Traffic Layer'}
        className={`px-3 py-2 rounded-xl border text-xs font-semibold shadow-lg backdrop-blur-md transition-all duration-200 active:scale-95 flex items-center gap-2 ${
          showTraffic
            ? 'bg-emerald-950/85 border-emerald-500/50 text-emerald-300 hover:bg-emerald-900/85 shadow-emerald-950/50'
            : 'bg-surface-900/90 border-surface-700/60 text-surface-400 hover:bg-surface-800'
        }`}
      >
        <span className={`w-2 h-2 rounded-full ${showTraffic ? 'bg-emerald-400 animate-pulse' : 'bg-surface-500'}`} />
        <span className="hidden sm:inline">Traffic</span>
      </button>

      {/* Quick Theme Toggle Icon */}
      <button
        onClick={toggleTheme}
        title={isDark ? 'Switch to Light Theme' : 'Switch to Dark Theme'}
        className="p-2.5 rounded-xl border border-surface-700/60 bg-surface-900/90 text-surface-300 hover:text-surface-100 hover:bg-surface-800 shadow-lg backdrop-blur-md transition-all duration-200 active:scale-95"
      >
        {isDark ? <HiSun className="w-5 h-5 text-amber-400" /> : <HiMoon className="w-5 h-5 text-indigo-400" />}
      </button>

      {/* User Profile Dropdown */}
      <div className="relative" ref={dropdownRef}>
        <button
          onClick={() => setDropdownOpen((prev) => !prev)}
          className="flex items-center gap-2 pl-2.5 pr-3 py-2 rounded-xl border border-surface-700/60 bg-surface-900/90 hover:bg-surface-800 shadow-lg backdrop-blur-md transition-all duration-200 text-surface-200 active:scale-95"
        >
          <HiUserCircle className="w-5 h-5 text-cyan-400 flex-shrink-0" />
          <span className="text-xs font-semibold max-w-[120px] truncate hidden sm:inline">
            {user?.email ? user.email.split('@')[0] : 'User'}
          </span>
          <HiChevronDown className={`w-4 h-4 text-surface-400 transition-transform duration-200 ${dropdownOpen ? 'rotate-180' : ''}`} />
        </button>

        {/* Dropdown Menu */}
        {dropdownOpen && (
          <div className="absolute right-0 mt-2 w-56 rounded-2xl border border-surface-700/70 bg-surface-900/95 backdrop-blur-xl shadow-2xl p-2 space-y-1 animate-in fade-in zoom-in-95 duration-150">
            {/* User Profile Info */}
            <div className="px-3 py-2.5 border-b border-surface-800/80">
              <p className="text-xs font-bold text-surface-100 truncate">{user?.email || 'User Account'}</p>
              <p className="text-[10px] text-cyan-400 font-medium mt-0.5">Verified NAVISCAPE User</p>
            </div>

            {/* App Views Submenu */}
            <div className="py-1 space-y-0.5">
              <div className="px-3 py-1 text-[10px] font-bold text-surface-500 uppercase tracking-wider">
                Application
              </div>
              <button
                onClick={() => { navigate('/navigate'); setDropdownOpen(false); }}
                className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs text-cyan-400 font-semibold bg-cyan-950/40 border border-cyan-500/30"
              >
                <HiMap className="w-4 h-4" /> Map Navigation
              </button>
              <button
                onClick={() => { navigate('/analytics'); setDropdownOpen(false); }}
                className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs text-surface-300 hover:text-surface-100 hover:bg-surface-800/80 transition-colors"
              >
                <HiChartBar className="w-4 h-4 text-surface-400" /> Analytics
              </button>
            </div>

            {/* Theme Toggle option */}
            <div className="border-t border-surface-800/80 pt-1">
              <button
                onClick={() => { toggleTheme(); }}
                className="w-full flex items-center justify-between px-3 py-2 rounded-xl text-xs text-surface-300 hover:text-surface-100 hover:bg-surface-800/80 transition-colors"
              >
                <span className="flex items-center gap-2.5">
                  {isDark ? <HiSun className="w-4 h-4 text-amber-400" /> : <HiMoon className="w-4 h-4 text-indigo-400" />}
                  <span>{isDark ? 'Light Theme' : 'Dark Theme'}</span>
                </span>
              </button>
            </div>

            {/* Sign Out Button */}
            <div className="border-t border-surface-800/80 pt-1">
              <button
                onClick={() => { logout(); setDropdownOpen(false); }}
                className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-semibold text-red-400 hover:text-red-300 hover:bg-red-500/10 transition-colors"
              >
                <HiLogout className="w-4 h-4" /> Sign Out
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
