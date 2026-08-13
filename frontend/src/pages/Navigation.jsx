import { useState, useEffect, useRef, useCallback } from 'react';
import { MapContainer, TileLayer, Marker, Popup, Polyline, useMap, CircleMarker, useMapEvents } from 'react-leaflet';
import L from 'leaflet';
import api from '../services/api';
import toast from 'react-hot-toast';
import {
  HiLocationMarker, HiSwitchHorizontal, HiSearch, HiShieldCheck, HiPlay, HiStop,
  HiArrowUp, HiArrowRight, HiArrowLeft, HiOutlineLocationMarker, HiPaperAirplane
} from 'react-icons/hi';
import { useAuth } from '../context/AuthContext';
import NavbarControls from '../components/layout/NavbarControls';
import 'leaflet/dist/leaflet.css';

delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
});

const BANGALORE_CENTER = [12.9716, 77.5946];
const PRESET_LOCATIONS = [
  { name: 'Silk Board Junction', lat: 12.9170, lng: 77.6230 },
  { name: 'Hebbal Flyover', lat: 13.0358, lng: 77.5970 },
  { name: 'KR Puram Junction', lat: 13.0012, lng: 77.6960 },
  { name: 'Marathahalli Bridge', lat: 12.9591, lng: 77.7010 },
  { name: 'Whitefield Junction', lat: 12.9698, lng: 77.7500 },
  { name: 'MG Road Metro', lat: 12.9756, lng: 77.6066 },
  { name: 'Koramangala', lat: 12.9352, lng: 77.6245 },
  { name: 'Electronic City', lat: 12.8440, lng: 77.6630 },
  { name: 'Indiranagar', lat: 12.9784, lng: 77.6408 },
  { name: 'Jayanagar', lat: 12.9260, lng: 77.5830 },
];
const ROUTE_COLORS = { shortest: '#ef4444', safest: '#22c55e', balanced: '#06b6d4' };
const ROUTE_LABELS = { shortest: 'Fastest Route', safest: 'Safest Route', balanced: 'Balanced Route' };

// Traffic level helpers
const TRAFFIC_COLOR = { Low: 'text-green-400', Moderate: 'text-yellow-400', High: 'text-orange-400', Severe: 'text-red-400' };
const TRAFFIC_BG = { Low: 'bg-green-500/15', Moderate: 'bg-yellow-500/15', High: 'bg-orange-500/15', Severe: 'bg-red-500/15' };
const TRAFFIC_ICON = { Low: '🟢', Moderate: '🟡', High: '🟠', Severe: '🔴' };

/* ---- OSRM API: fetch real road routes ---- */
async function fetchOSRMRoutes(srcLat, srcLng, dstLat, dstLng) {
  const url = `https://router.project-osrm.org/route/v1/driving/${srcLng},${srcLat};${dstLng},${dstLat}?alternatives=true&overview=full&geometries=geojson&steps=true`;
  const res = await fetch(url);
  if (!res.ok) throw new Error('OSRM request failed');
  const data = await res.json();
  if (data.code !== 'Ok' || !data.routes?.length) throw new Error('No routes found');
  return data.routes;
}

/* ---- Convert OSRM route to internal candidate format ---- */
function processOSRMRoutes(osrmRoutes) {
  const sorted = [...osrmRoutes].sort((a, b) => a.distance - b.distance);
  const typeLabels = ['shortest', 'balanced', 'safest'];
  return sorted.map((route, i) => {
    const type = typeLabels[Math.min(i, typeLabels.length - 1)];
    const waypoints = route.geometry.coordinates.map(([lng, lat]) => [lat, lng]);
    const distanceKm = +(route.distance / 1000).toFixed(2);
    const durationMin = +(route.duration / 60).toFixed(1);

    let safetyScore;
    if (i === 0) safetyScore = +(55 + Math.random() * 15).toFixed(1);
    else if (i === sorted.length - 1) safetyScore = +(82 + Math.random() * 16).toFixed(1);
    else safetyScore = +(68 + Math.random() * 18).toFixed(1);

    return {
      route_type: type,
      label: ROUTE_LABELS[type],
      distance_km: distanceKm,
      duration_min: durationMin,
      safety_score: safetyScore,
      waypoints,
    };
  });
}

/* ---- helper: distance in meters ---- */
function haversineMeters(lat1, lon1, lat2, lon2) {
  const R = 6371000;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos((lat1 * Math.PI) / 180) *
      Math.cos((lat2 * Math.PI) / 180) *
      Math.sin(dLon / 2) *
      Math.sin(dLon / 2);
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

/* ---- helper: bearing between two points ---- */
function bearing(a, b) {
  const dLng = ((b[1] - a[1]) * Math.PI) / 180;
  const lat1 = (a[0] * Math.PI) / 180;
  const lat2 = (b[0] * Math.PI) / 180;
  const y = Math.sin(dLng) * Math.cos(lat2);
  const x = Math.cos(lat1) * Math.sin(lat2) - Math.sin(lat1) * Math.cos(lat2) * Math.cos(dLng);
  return ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360;
}

function turnDirection(prev, cur, next) {
  if (!prev || !next) return { icon: HiArrowUp, text: 'Head straight' };
  const b1 = bearing(prev, cur);
  const b2 = bearing(cur, next);
  let diff = ((b2 - b1) + 360) % 360;
  if (diff > 315 || diff < 45) return { icon: HiArrowUp, text: 'Continue straight' };
  if (diff >= 45 && diff < 170) return { icon: HiArrowRight, text: 'Turn right' };
  if (diff >= 170 && diff <= 190) return { icon: HiArrowUp, text: 'Make a U-turn' };
  return { icon: HiArrowLeft, text: 'Turn left' };
}

/* ---- map sub-component: follow moving marker ---- */
function FollowMarker({ position, isNavigating }) {
  const map = useMap();
  useEffect(() => {
    if (isNavigating && position) {
      map.setView(position, Math.max(map.getZoom(), 15), { animate: true, duration: 0.4 });
    }
  }, [position, isNavigating, map]);
  return null;
}

function FitBounds({ bounds }) {
  const map = useMap();
  useEffect(() => { if (bounds) map.fitBounds(bounds, { padding: [50, 50] }); }, [bounds, map]);
  return null;
}

function MapClickHandler({ onMapClick, active }) {
  useMapEvents({
    click: (e) => {
      if (active) {
        onMapClick(e.latlng);
      }
    },
  });
  return null;
}

/* ---- hazard custom icons ---- */
const getHazardIcon = (type, severity) => {
  const colors = {
    Low: '#10b981',
    Medium: '#eab308',
    High: '#f97316',
    Critical: '#ef4444',
  };
  const color = colors[severity] || '#3b82f6';
  const animatePulse = severity === 'Critical' ? 'animate-pulse' : '';
  
  let iconSvg = '';
  if (type === 'Accident') {
    iconSvg = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M19 17h2c.6 0 1-.4 1-1v-3c0-.9-.7-1.7-1.5-1.9C18.7 10.6 16 10 16 10s-1.3-1.4-2.2-2.3c-.5-.4-1.1-.7-1.8-.7H5c-1.1 0-2 .9-2 2v7h2" /><circle cx="7" cy="17" r="2" /><circle cx="15" cy="17" r="2" /></svg>`;
  } else if (type === 'Pothole') {
    iconSvg = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z"/><path d="M8 12h8"/></svg>`;
  } else if (type === 'Road construction') {
    iconSvg = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M2 22h20M12 2v20M5 7.5L9.5 3M19 7.5L14.5 3"/></svg>`;
  } else if (type === 'Road blocked') {
    iconSvg = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/></svg>`;
  } else if (type === 'Waterlogging') {
    iconSvg = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2v20M17 5a5 5 0 0 0-10 0v12a5 5 0 0 0 10 0V5z"/></svg>`;
  } else if (type === 'Fallen tree') {
    iconSvg = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19V5M9 8l3-3 3 3M4 19h16"/></svg>`;
  } else if (type === 'Heavy traffic') {
    iconSvg = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="10" rx="2"/><circle cx="7" cy="17" r="1"/><circle cx="17" cy="17" r="1"/></svg>`;
  } else if (type === 'Dangerous road') {
    iconSvg = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="m10.2 3.2 8.6 8.6a2 2 0 0 1 0 2.8l-8.6 8.6a2 2 0 0 1-2.8 0L3.2 14.6a2 2 0 0 1 0-2.8l5.4-5.4"/></svg>`;
  } else {
    iconSvg = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg>`;
  }

  return L.divIcon({
    className: '',
    html: `
      <div style="position:relative;width:32px;height:32px;display:flex;align-items:center;justify-content:center;">
        <div class="${animatePulse}" style="position:absolute;width:28px;height:28px;border-radius:50%;background:${color};opacity:0.25;transform:scale(1);"></div>
        <div style="position:absolute;width:22px;height:22px;border-radius:50%;border:2px solid ${color};background:#0f172a;box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.5);display:flex;align-items:center;justify-content:center;color:${color}">
          ${iconSvg}
        </div>
      </div>
    `,
    iconSize: [32, 32],
    iconAnchor: [16, 16],
    popupAnchor: [0, -16],
  });
};

/* ---- navigation car icon ---- */
const carIconHtml = (rot) => L.divIcon({
  className: '',
  html: `<div style="transform:rotate(${rot}deg);width:36px;height:36px;display:flex;align-items:center;justify-content:center">
    <svg width="32" height="32" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="11" fill="#06b6d4" stroke="#0f172a" stroke-width="2"/><path d="M12 4L18 18L12 14L6 18L12 4Z" fill="white"/></svg>
  </div>`,
  iconSize: [36, 36],
  iconAnchor: [18, 18],
});

export default function Navigation() {
  const { user } = useAuth();
  const [hazards, setHazards] = useState([]);
  const [reportType, setReportType] = useState('Accident');
  const [reportSeverity, setReportSeverity] = useState('Medium');
  const [reportLat, setReportLat] = useState('');
  const [reportLng, setReportLng] = useState('');
  const [reportDesc, setReportDesc] = useState('');
  const [submittingHazard, setSubmittingHazard] = useState(false);
  const [isReporting, setIsReporting] = useState(false);

  const [source, setSource] = useState('');
  const [dest, setDest] = useState('');
  const [sourceCoord, setSourceCoord] = useState(null);
  const [destCoord, setDestCoord] = useState(null);
  const [routes, setRoutes] = useState([]);
  const [selectedRoute, setSelectedRoute] = useState(null);
  const [recommendedRouteId, setRecommendedRouteId] = useState(null);
  const [recommendationReasons, setRecommendationReasons] = useState([]);
  const [riskZones, setRiskZones] = useState([]);
  const [loading, setLoading] = useState(false);
  const [bounds, setBounds] = useState(null);
  const [showSourceDD, setShowSourceDD] = useState(false);
  const [showDestDD, setShowDestDD] = useState(false);
  const [showTraffic, setShowTraffic] = useState(true);

  // Geocoding search results
  const [sourceSuggestions, setSourceSuggestions] = useState([]);
  const [destSuggestions, setDestSuggestions] = useState([]);
  const sourceTimerRef = useRef(null);
  const destTimerRef = useRef(null);

  // Live navigation state
  const [isNavigating, setIsNavigating] = useState(false);
  const [navPosition, setNavPosition] = useState(null);
  const [navBearing, setNavBearing] = useState(0);
  const [navProgress, setNavProgress] = useState(0);
  const [navSpeed, setNavSpeed] = useState(0);
  const [navETA, setNavETA] = useState(0);
  const [navDistLeft, setNavDistLeft] = useState(0);
  const [navInstruction, setNavInstruction] = useState({ icon: HiArrowUp, text: 'Head straight' });
  const [travelledPath, setTravelledPath] = useState([]);
  const watchIdRef = useRef(null);
  const warnedHotspotsRef = useRef(new Set());
  const warnedHazardsRef = useRef(new Set());
  const simIntervalRef = useRef(null);
  const [activeHotspotWarning, setActiveHotspotWarning] = useState(null);

  // Web Audio API context reference for accident warning chime
  const audioCtxRef = useRef(null);

  /* ---------- WEB AUDIO API ALERTS ---------- */
  const initAudioContext = useCallback(() => {
    try {
      if (!audioCtxRef.current) {
        const AudioContextClass = window.AudioContext || window.webkitAudioContext;
        if (AudioContextClass) {
          audioCtxRef.current = new AudioContextClass();
        }
      }
      if (audioCtxRef.current && audioCtxRef.current.state === 'suspended') {
        audioCtxRef.current.resume();
      }
    } catch (e) {
      console.warn("AudioContext init error:", e);
    }
  }, []);

  const playAccidentWarningChime = useCallback(() => {
    try {
      initAudioContext();
      const ctx = audioCtxRef.current;
      if (!ctx) return;
      if (ctx.state === 'suspended') {
        ctx.resume();
      }

      const now = ctx.currentTime;
      
      // Tone 1: High warning chime (880 Hz)
      const osc1 = ctx.createOscillator();
      const gain1 = ctx.createGain();
      osc1.type = 'sine';
      osc1.frequency.setValueAtTime(880, now);
      gain1.gain.setValueAtTime(0.35, now);
      gain1.gain.exponentialRampToValueAtTime(0.001, now + 0.45);
      osc1.connect(gain1);
      gain1.connect(ctx.destination);
      osc1.start(now);
      osc1.stop(now + 0.45);

      // Tone 2: Mid alert pitch (660 Hz)
      const osc2 = ctx.createOscillator();
      const gain2 = ctx.createGain();
      osc2.type = 'sine';
      osc2.frequency.setValueAtTime(660, now + 0.3);
      gain2.gain.setValueAtTime(0.4, now + 0.3);
      gain2.gain.exponentialRampToValueAtTime(0.001, now + 0.85);
      osc2.connect(gain2);
      gain2.connect(ctx.destination);
      osc2.start(now + 0.3);
      osc2.stop(now + 0.85);

      // Tone 3: Sustained warning chime (880 -> 587.33 Hz)
      const osc3 = ctx.createOscillator();
      const gain3 = ctx.createGain();
      osc3.type = 'triangle';
      osc3.frequency.setValueAtTime(880, now + 0.7);
      osc3.frequency.exponentialRampToValueAtTime(587.33, now + 2.3);
      gain3.gain.setValueAtTime(0.3, now + 0.7);
      gain3.gain.exponentialRampToValueAtTime(0.001, now + 2.4);
      osc3.connect(gain3);
      gain3.connect(ctx.destination);
      osc3.start(now + 0.7);
      osc3.stop(now + 2.4);
    } catch (err) {
      console.warn("Accident warning chime error:", err);
    }
  }, [initAudioContext]);

  /* ---------- GEOCODING (Nominatim) ---------- */
  const geocodeSearch = async (query, setSuggestions) => {
    if (!query || query.length < 2) { setSuggestions([]); return; }
    const presetMatches = PRESET_LOCATIONS.filter(l => l.name.toLowerCase().includes(query.toLowerCase()));
    
    try {
      const url = `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(query)}&format=json&limit=10&countrycodes=in&viewbox=74.05,18.45,78.50,11.55&bounded=0&addressdetails=1`;
      const res = await fetch(url, { headers: { 'Accept-Language': 'en' } });
      const data = await res.json();
      
      const results = data.map(item => {
        const addr = item.address || {};
        const main = item.name || item.display_name.split(',')[0];
        const city = addr.city || addr.town || addr.suburb || addr.municipality || addr.county || '';
        const state = addr.state || '';
        const parts = [main, city, state].filter(Boolean);
        
        const uniqueParts = [];
        parts.forEach(p => {
          const trimmed = p.trim();
          if (!uniqueParts.some(x => x.toLowerCase() === trimmed.toLowerCase())) {
            uniqueParts.push(trimmed);
          }
        });
        
        return {
          name: uniqueParts.join(', '),
          lat: parseFloat(item.lat),
          lng: parseFloat(item.lon),
        };
      });

      const presetNames = new Set(presetMatches.map(p => p.name.toLowerCase()));
      const merged = [
        ...presetMatches.map(l => ({ name: l.name, lat: l.lat, lng: l.lng })),
        ...results.filter(r => !presetNames.has(r.name.toLowerCase())),
      ];
      setSuggestions(merged.slice(0, 8));
    } catch {
      setSuggestions(presetMatches.map(l => ({ name: l.name, lat: l.lat, lng: l.lng })));
    }
  };

  const handleSourceChange = (value) => {
    setSource(value);
    setShowSourceDD(true);
    setSourceCoord(null);
    clearTimeout(sourceTimerRef.current);
    sourceTimerRef.current = setTimeout(() => geocodeSearch(value, setSourceSuggestions), 300);
  };

  const handleDestChange = (value) => {
    setDest(value);
    setShowDestDD(true);
    setDestCoord(null);
    clearTimeout(destTimerRef.current);
    destTimerRef.current = setTimeout(() => geocodeSearch(value, setDestSuggestions), 300);
  };

  const selectSource = (loc) => { setSource(loc.name); setSourceCoord([loc.lat, loc.lng]); setShowSourceDD(false); setSourceSuggestions([]); };
  const selectDest = (loc) => { setDest(loc.name); setDestCoord([loc.lat, loc.lng]); setShowDestDD(false); setDestSuggestions([]); };
  const swapLocations = () => { setSource(dest); setDest(source); setSourceCoord(destCoord); setDestCoord(sourceCoord); };

  /* ---------- FIND & OPTIMIZE ROUTES ---------- */
  const findRoutes = async () => {
    if (!sourceCoord || !destCoord) { toast.error('Select both locations'); return; }
    setLoading(true);
    try {
      const osrmRoutes = await fetchOSRMRoutes(sourceCoord[0], sourceCoord[1], destCoord[0], destCoord[1]);
      const processed = processOSRMRoutes(osrmRoutes);

      const candidatePayload = processed.map((r, i) => ({
        route_id: r.route_type || `route_${i}`,
        route_type: r.route_type || 'balanced',
        distance_km: r.distance_km,
        duration_min: r.duration_min,
        waypoints: r.waypoints,
      }));

      try {
        const optRes = await api.post('/navigation/optimize-routes', { routes: candidatePayload });
        const { routes: evalRoutes, recommended_route_id, recommendation_reasons } = optRes.data;

        const merged = evalRoutes.map(r => ({
          ...r,
          label: ROUTE_LABELS[r.route_type] || r.route_type,
          waypoints: (r.waypoints && r.waypoints.length > 0)
            ? r.waypoints
            : (processed.find(p => p.route_type === r.route_type)?.waypoints || []),
        }));

        setRoutes(merged);
        setRecommendedRouteId(recommended_route_id);
        setRecommendationReasons(recommendation_reasons || []);

        const recRoute = merged.find(r => r.route_id === recommended_route_id) || merged[0];
        setSelectedRoute(recRoute);
      } catch (optErr) {
        console.warn('Smart route optimization API fallback:', optErr);
        const evaluated = await Promise.all(
          processed.map(async (r) => {
            try {
              const evalRes = await api.post('/navigation/evaluate-route', {
                route_type: r.route_type,
                waypoints: r.waypoints,
              });
              return {
                ...r,
                safety_score: evalRes.data.empirical_safety_score ?? r.safety_score,
                total_accidents_nearby: evalRes.data.total_accidents_nearby,
                fatal_accidents_nearby: evalRes.data.fatal_accidents_nearby,
                hotspots: evalRes.data.hotspots || [],
                eta_minutes: r.duration_min,
              };
            } catch (e) {
              return { ...r, eta_minutes: r.duration_min };
            }
          })
        );

        setRoutes(evaluated);
        setSelectedRoute(evaluated[0]);
      }

      try {
        const riskRes = await api.post('/predict/risk', {
          latitude: (sourceCoord[0] + destCoord[0]) / 2,
          longitude: (sourceCoord[1] + destCoord[1]) / 2,
        });
        setRiskZones([{
          lat: riskRes.data.latitude,
          lng: riskRes.data.longitude,
          risk: riskRes.data.risk_score,
          level: riskRes.data.risk_level,
        }]);
      } catch {
        setRiskZones([]);
      }

      const allPts = processed.flatMap(r => r.waypoints);
      setBounds(L.latLngBounds(allPts));

      toast.success('Smart route optimization complete');
    } catch (err) {
      console.error('Route error:', err);
      toast.error('Could not find routes. Check your connection.');
    } finally {
      setLoading(false);
    }
  };

  /* ---------- SAVE ROUTE TO BACKEND ---------- */
  const saveRoute = async (route) => {
    try {
      await api.post('/navigate', {
        source_lat: sourceCoord[0],
        source_lng: sourceCoord[1],
        dest_lat: destCoord[0],
        dest_lng: destCoord[1],
        source_name: source,
        dest_name: dest,
        route_type: route.route_type,
        distance_km: route.distance_km,
        duration_min: route.eta_minutes ?? route.duration_min,
        safety_score: route.safety_score,
      });
    } catch (err) {
      console.error('Failed to save route:', err);
    }
  };

  const locateUser = useCallback(() => {
    if (!("geolocation" in navigator)) return;
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const { latitude, longitude } = position.coords;
        const pos = [latitude, longitude];
        setSourceCoord(pos);
        setSource('Your Location');
        setBounds(L.latLngBounds([pos]));
        toast.success("Location updated");
      },
      () => toast.error("Could not find your location")
    );
  }, []);

  const fetchHazards = useCallback(async () => {
    try {
      const res = await api.get('/hazards');
      setHazards(res.data);
    } catch (err) {
      console.error('Failed to fetch road hazards:', err);
    }
  }, []);

  const handleReportHazard = async (e) => {
    e.preventDefault();
    if (!reportLat || !reportLng) {
      toast.error('Please select coordinates on the map or input them.');
      return;
    }
    setSubmittingHazard(true);
    try {
      await api.post('/hazards', {
        hazard_type: reportType,
        severity: reportSeverity,
        latitude: parseFloat(reportLat),
        longitude: parseFloat(reportLng),
        description: reportDesc || null
      });
      toast.success('Road hazard reported successfully!');
      setReportDesc('');
      setReportLat('');
      setReportLng('');
      setIsReporting(false);
      fetchHazards();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to submit report');
    } finally {
      setSubmittingHazard(false);
    }
  };

  const handleResolveHazard = async (hazardId) => {
    try {
      await api.put(`/hazards/${hazardId}/resolve`);
      toast.success('Road hazard resolved/deactivated.');
      fetchHazards();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to resolve hazard');
    }
  };

  useEffect(() => {
    locateUser();
    fetchHazards();
  }, [locateUser, fetchHazards]);

  /* ---------- LIVE NAVIGATION & PROXIMITY ALERTS ---------- */
  const stopNavigation = () => {
    setIsNavigating(false);
    if (watchIdRef.current) {
      navigator.geolocation.clearWatch(watchIdRef.current);
      watchIdRef.current = null;
    }
    if (simIntervalRef.current) {
      clearInterval(simIntervalRef.current);
      simIntervalRef.current = null;
    }
    setActiveHotspotWarning(null);
    toast('Navigation stopped', { icon: '🛑' });
  };

  const processProximityAndLocationUpdate = useCallback((currentPos, heading = 0, speedKmh = 40, nearestIdx = 0) => {
    setNavPosition(currentPos);
    setTravelledPath(prev => [...prev, currentPos]);
    setNavBearing(heading);
    setNavSpeed(speedKmh);

    if (selectedRoute?.waypoints?.length > 1) {
      const totalWp = selectedRoute.waypoints.length;
      const pct = (nearestIdx / (totalWp - 1)) * 100;
      const baseEta = selectedRoute.eta_minutes ?? selectedRoute.duration_min;
      
      setNavProgress(pct);
      setNavDistLeft(+(selectedRoute.distance_km * (1 - pct / 100)).toFixed(2));
      setNavETA(+((baseEta) * (1 - pct / 100)).toFixed(1));

      if (nearestIdx < totalWp - 1) {
        const dir = turnDirection(
          selectedRoute.waypoints[Math.max(0, nearestIdx - 1)],
          currentPos,
          selectedRoute.waypoints[nearestIdx + 1]
        );
        setNavInstruction(dir);
      }

      if (pct > 95) setNavInstruction({ icon: HiLocationMarker, text: 'Arriving at destination' });
    }

    // 500m Hotspot Proximity Alert Detection with Web Audio API chime
    if (selectedRoute?.hotspots?.length) {
      selectedRoute.hotspots.forEach((hs, idx) => {
        const hsKey = `${hs.lat}_${hs.lng}_${idx}`;
        if (!warnedHotspotsRef.current.has(hsKey)) {
          const distM = haversineMeters(currentPos[0], currentPos[1], hs.lat, hs.lng);
          if (distM <= 500) {
            warnedHotspotsRef.current.add(hsKey); // Mark as warned strictly once
            playAccidentWarningChime();           // Play 2-3 sec Web Audio chime
            const warningText = `⚠️ Approaching Accident Hotspot: ${hs.name} (${hs.fatal_count} fatal incidents)`;
            toast.error(warningText, { duration: 6000, id: `hs-toast-${hsKey}` });
            setActiveHotspotWarning({
              name: hs.name,
              fatal_count: hs.fatal_count,
              accident_count: hs.accident_count,
              risk_level: hs.risk_level,
            });
          }
        }
      });
    }

    // 500m User-reported Hazard Proximity Alert Detection
    if (selectedRoute?.live_hazards?.length) {
      selectedRoute.live_hazards.forEach((hz) => {
        const hzKey = `${hz.id}`;
        if (!warnedHazardsRef.current.has(hzKey)) {
          const distM = haversineMeters(currentPos[0], currentPos[1], hz.latitude, hz.longitude);
          if (distM <= 500) {
            warnedHazardsRef.current.add(hzKey);
            const warningText = `⚠️ Alert: Approaching User-Reported Hazard Ahead! Type: ${hz.hazard_type} (${hz.severity} severity)${hz.description ? ` - ${hz.description}` : ''}`;
            toast.error(warningText, { duration: 7000, id: `hz-toast-${hzKey}` });
          }
        }
      });
    }
  }, [selectedRoute, playAccidentWarningChime]);

  const startNavigation = () => {
    if (!selectedRoute) { toast.error('Select a route first'); return; }

    const initialPos = sourceCoord || (selectedRoute.waypoints && selectedRoute.waypoints[0]);
    if (!initialPos) { toast.error('Route coordinates missing'); return; }

    // Unlock Web Audio API on user interaction
    initAudioContext();

    setIsNavigating(true);
    setTravelledPath([initialPos]);
    setNavPosition(initialPos);
    warnedHotspotsRef.current.clear();
    warnedHazardsRef.current.clear();
    setActiveHotspotWarning(null);
    saveRoute(selectedRoute);
    toast.success('Navigation started');

    const waypoints = selectedRoute.waypoints || [];
    if (waypoints.length > 1) {
      let stepIdx = 0;
      const stepInterval = Math.max(1, Math.floor(waypoints.length / 30));

      if (simIntervalRef.current) clearInterval(simIntervalRef.current);
      simIntervalRef.current = setInterval(() => {
        stepIdx += stepInterval;
        if (stepIdx >= waypoints.length - 1) {
          stepIdx = waypoints.length - 1;
          const currentPos = waypoints[stepIdx];
          processProximityAndLocationUpdate(currentPos, 0, 0, stepIdx);
          clearInterval(simIntervalRef.current);
          simIntervalRef.current = null;
          toast.success('You have arrived!');
          return;
        }
        const prevPos = waypoints[Math.max(0, stepIdx - stepInterval)];
        const currentPos = waypoints[stepIdx];
        const brg = bearing(prevPos, currentPos);
        processProximityAndLocationUpdate(currentPos, brg, 45, stepIdx);
      }, 1000);
    }

    if ("geolocation" in navigator) {
      watchIdRef.current = navigator.geolocation.watchPosition(
        (position) => {
          const { latitude, longitude, heading, speed } = position.coords;
          const currentPos = [latitude, longitude];
          let nearestIdx = 0;
          let minD = Infinity;
          waypoints.forEach((p, i) => {
            const d = Math.sqrt(Math.pow(p[0] - latitude, 2) + Math.pow(p[1] - longitude, 2));
            if (d < minD) { minD = d; nearestIdx = i; }
          });
          processProximityAndLocationUpdate(currentPos, heading || 0, Math.round((speed || 0) * 3.6), nearestIdx);
        },
        () => {},
        { enableHighAccuracy: true, maximumAge: 1000 }
      );
    }
  };

  const srcIcon = new L.Icon({ iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-green.png', shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png', iconSize: [25,41], iconAnchor: [12,41], popupAnchor: [1,-34], shadowSize: [41,41] });
  const dstIcon = new L.Icon({ iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-red.png', shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png', iconSize: [25,41], iconAnchor: [12,41], popupAnchor: [1,-34], shadowSize: [41,41] });

  /* ---- RENDER ROUTE PLANNER SEARCH CARD ---- */
  const renderPlannerContent = () => (
    routes.length > 0 ? (
      <div className="flex items-center justify-between gap-3 text-sm">
        <div className="truncate flex-1">
          <div className="text-[10px] uppercase tracking-wider text-cyan-400 font-bold">Selected Route</div>
          <div className="font-semibold text-surface-100 truncate mt-0.5">
            {source} ➔ {dest}
          </div>
        </div>
        <button 
          onClick={() => { setRoutes([]); setSelectedRoute(null); }} 
          className="text-xs text-cyan-400 hover:text-cyan-300 font-bold flex-shrink-0 px-3 py-1.5 rounded-xl bg-cyan-950/60 border border-cyan-500/40 hover:bg-cyan-900/60 transition-all"
        >
          Change
        </button>
      </div>
    ) : (
      <>
        {/* Header */}
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-xl bg-cyan-500/20 border border-cyan-500/40 flex items-center justify-center text-cyan-400 font-black">
              N
            </div>
            <div>
              <h2 className="text-sm font-bold text-surface-100 tracking-tight">NAVISCAPE</h2>
              <p className="text-[10px] text-surface-400">{isReporting ? 'Report Hazard' : 'Smart Route Planner'}</p>
            </div>
          </div>

          <button
            onClick={() => setIsReporting(prev => !prev)}
            className={`text-[11px] px-2.5 py-1.5 rounded-xl border font-bold transition-all duration-200 active:scale-95 flex items-center gap-1
              ${isReporting
                ? 'bg-amber-600/25 border-amber-500/60 text-amber-300'
                : 'bg-surface-800/80 border-surface-700 text-surface-300 hover:bg-surface-700'}`}
          >
            ⚠️ {isReporting ? 'Planner' : 'Report Hazard'}
          </button>
        </div>

        {isReporting ? (
          <form onSubmit={handleReportHazard} className="space-y-2.5 animate-fade-in">
            <div>
              <label className="text-[10px] font-bold uppercase tracking-wider text-surface-400 mb-1 block">Hazard Type</label>
              <select
                value={reportType}
                onChange={e => setReportType(e.target.value)}
                className="input-field text-xs bg-surface-800/90 border-surface-700 text-surface-200 w-full rounded-xl p-2 focus:ring-1 focus:ring-cyan-500 focus:outline-none"
              >
                <option value="Accident">Accident</option>
                <option value="Pothole">Pothole</option>
                <option value="Road construction">Road construction</option>
                <option value="Road blocked">Road blocked</option>
                <option value="Waterlogging">Waterlogging</option>
                <option value="Fallen tree">Fallen tree</option>
                <option value="Heavy traffic">Heavy traffic</option>
                <option value="Dangerous road">Dangerous road</option>
                <option value="Other">Other</option>
              </select>
            </div>

            <div>
              <label className="text-[10px] font-bold uppercase tracking-wider text-surface-400 mb-1 block">Severity</label>
              <select
                value={reportSeverity}
                onChange={e => setReportSeverity(e.target.value)}
                className="input-field text-xs bg-surface-800/90 border-surface-700 text-surface-200 w-full rounded-xl p-2 focus:ring-1 focus:ring-cyan-500 focus:outline-none"
              >
                <option value="Low">Low</option>
                <option value="Medium">Medium</option>
                <option value="High">High</option>
                <option value="Critical">Critical</option>
              </select>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="text-[10px] font-bold uppercase tracking-wider text-surface-400 mb-1 block">Latitude</label>
                <input
                  type="number"
                  step="any"
                  placeholder="12.9716"
                  value={reportLat}
                  onChange={e => setReportLat(e.target.value)}
                  className="input-field text-xs bg-surface-800/90 border-surface-700 text-surface-200 w-full rounded-xl p-2 focus:ring-1 focus:ring-cyan-500 focus:outline-none"
                  required
                />
              </div>
              <div>
                <label className="text-[10px] font-bold uppercase tracking-wider text-surface-400 mb-1 block">Longitude</label>
                <input
                  type="number"
                  step="any"
                  placeholder="77.5946"
                  value={reportLng}
                  onChange={e => setReportLng(e.target.value)}
                  className="input-field text-xs bg-surface-800/90 border-surface-700 text-surface-200 w-full rounded-xl p-2 focus:ring-1 focus:ring-cyan-500 focus:outline-none"
                  required
                />
              </div>
            </div>

            <div className="text-[10px] text-amber-400 font-medium px-0.5 leading-snug">
              💡 Tip: Click anywhere on the map to pin coordinates.
            </div>

            <div>
              <label className="text-[10px] font-bold uppercase tracking-wider text-surface-400 mb-1 block">Description (Optional)</label>
              <textarea
                placeholder="Describe details..."
                value={reportDesc}
                onChange={e => setReportDesc(e.target.value)}
                className="input-field text-xs bg-surface-800/90 border-surface-700 text-surface-200 w-full rounded-xl p-2 h-14 resize-none focus:ring-1 focus:ring-cyan-500 focus:outline-none"
              />
            </div>

            <button
              type="submit"
              disabled={submittingHazard}
              className="btn-primary w-full flex items-center justify-center gap-2 mt-1 bg-amber-600 hover:bg-amber-500 border-amber-500 hover:shadow-lg transition-all active:scale-95 duration-150 py-2 text-xs font-bold"
            >
              {submittingHazard ? (
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              ) : (
                <span>Submit Report</span>
              )}
            </button>
          </form>
        ) : (
          <>
            {/* Source */}
            <div className="relative mb-2">
              <label className="text-[10px] font-bold uppercase tracking-wider text-surface-400 mb-1 block">Source</label>
              <input className="input-field text-xs rounded-xl p-2.5" placeholder="Search source location..." value={source}
                onChange={e => handleSourceChange(e.target.value)}
                onFocus={() => { setShowSourceDD(true); if (source) geocodeSearch(source, setSourceSuggestions); }}
                onBlur={() => setTimeout(() => setShowSourceDD(false), 200)} />
              {showSourceDD && sourceSuggestions.length > 0 && (
                <div className="absolute z-50 w-full mt-1 glass-card bg-surface-900 border border-surface-700 rounded-xl shadow-2xl max-h-48 overflow-y-auto">
                  {sourceSuggestions.map((l,i) => (
                    <button key={i} onMouseDown={() => selectSource(l)} className="w-full text-left px-3 py-2 text-xs text-surface-300 hover:bg-surface-800 hover:text-white transition-colors truncate">{l.name}</button>
                  ))}
                </div>
              )}
            </div>

            {/* Swap Button */}
            <div className="flex justify-center -my-1 relative z-10">
              <button onClick={swapLocations} title="Swap Locations" className="p-1.5 rounded-xl bg-surface-800/90 border border-surface-700 transition-colors text-surface-400 hover:text-cyan-400 hover:bg-surface-700 shadow">
                <HiSwitchHorizontal className="w-4 h-4 rotate-90" />
              </button>
            </div>

            {/* Destination */}
            <div className="relative mb-3">
              <label className="text-[10px] font-bold uppercase tracking-wider text-surface-400 mb-1 block">Destination</label>
              <input className="input-field text-xs rounded-xl p-2.5" placeholder="Search destination location..." value={dest}
                onChange={e => handleDestChange(e.target.value)}
                onFocus={() => { setShowDestDD(true); if (dest) geocodeSearch(dest, setDestSuggestions); }}
                onBlur={() => setTimeout(() => setShowDestDD(false), 200)} />
              {showDestDD && destSuggestions.length > 0 && (
                <div className="absolute z-50 w-full mt-1 glass-card bg-surface-900 border border-surface-700 rounded-xl shadow-2xl max-h-48 overflow-y-auto">
                  {destSuggestions.map((l,i) => (
                    <button key={i} onMouseDown={() => selectDest(l)} className="w-full text-left px-3 py-2 text-xs text-surface-300 hover:bg-surface-800 hover:text-white transition-colors truncate">{l.name}</button>
                  ))}
                </div>
              )}
            </div>

            <button onClick={findRoutes} disabled={loading} className="btn-primary w-full flex items-center justify-center gap-2 py-2.5 text-xs font-bold rounded-xl shadow-lg">
              {loading ? <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : <><HiSearch className="w-4 h-4" /><span>Find Routes</span></>}
            </button>
          </>
        )}
      </>
    )
  );

  /* ---- RENDER ROUTE ALTERNATIVES AND RECOMMENDED HERO CARD ---- */
  const renderAlternativesContent = () => {
    const recommendedRoute = routes.find(r => r.route_id === recommendedRouteId) || routes[0];
    const displayReasons = (recommendationReasons && recommendationReasons.length > 0)
      ? recommendationReasons
      : (recommendedRoute?.reasons || []);

    const totalETA = recommendedRoute?.eta_minutes ?? recommendedRoute?.duration_min;

    return (
      <div className="space-y-3">
        {/* Recommended Route Hero Card */}
        {recommendedRoute && (
          <div className="p-4 rounded-2xl bg-gradient-to-br from-cyan-950/90 via-surface-900 to-surface-900 border border-cyan-500/50 shadow-xl space-y-3">
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-1.5 text-[11px] font-black uppercase tracking-wider text-cyan-400">
                <HiShieldCheck className="w-4 h-4 text-cyan-400" />
                NAVISCAPE RECOMMENDED
              </span>
              <span className="px-2.5 py-0.5 rounded-full text-xs font-black bg-cyan-500/20 text-cyan-300 border border-cyan-500/40">
                Overall {recommendedRoute.overall_score || 85}/100
              </span>
            </div>

            <div className="flex items-baseline justify-between border-b border-surface-800/80 pb-2">
              <div>
                <span className="text-2xl font-black text-surface-100">{totalETA?.toFixed(0)} min</span>
                <span className="text-xs text-surface-400 ml-2">
                  ({recommendedRoute.distance_km} km • base {recommendedRoute.duration_min?.toFixed(0)}m)
                </span>
              </div>
              <span className="text-xs font-bold text-surface-300">{recommendedRoute.label}</span>
            </div>

            {/* Delay breakdown if traffic or hazard delay present */}
            {(recommendedRoute.traffic_delay_minutes > 0 || recommendedRoute.hazard_delay_minutes > 0 || recommendedRoute.expected_delay_minutes > 0) && (
              <div className="flex items-center justify-between text-xs px-2 py-1 bg-surface-800/60 rounded-xl border border-surface-700/50">
                <span className="text-surface-400 font-medium text-[11px]">Backend Delays</span>
                <div className="flex items-center gap-2 text-[11px] font-bold">
                  {recommendedRoute.traffic_delay_minutes > 0 && (
                    <span className="text-amber-400">Traffic: +{recommendedRoute.traffic_delay_minutes}m</span>
                  )}
                  {recommendedRoute.hazard_delay_minutes > 0 && (
                    <span className="text-red-400">Hazard: +{recommendedRoute.hazard_delay_minutes}m</span>
                  )}
                  {recommendedRoute.traffic_delay_minutes === 0 && recommendedRoute.hazard_delay_minutes === 0 && (
                    <span className="text-green-400">+0m delay</span>
                  )}
                </div>
              </div>
            )}

            {/* Stats grid: Safety · Traffic Now · Predicted · Risk */}
            <div className="grid grid-cols-4 gap-1.5 text-center text-xs">
              <div className="bg-surface-800/70 p-2 rounded-xl border border-surface-700/50">
                <div className="text-[9px] text-surface-400 font-bold uppercase">Safety</div>
                <div className={`font-black mt-0.5 ${recommendedRoute.safety_score >= 80 ? 'text-green-400' : recommendedRoute.safety_score >= 60 ? 'text-yellow-400' : 'text-red-400'}`}>
                  {recommendedRoute.safety_score}
                </div>
              </div>
              <div className="bg-surface-800/70 p-2 rounded-xl border border-surface-700/50">
                <div className="text-[9px] text-surface-400 font-bold uppercase">Traffic</div>
                <div className={`font-bold mt-0.5 text-[11px] ${TRAFFIC_COLOR[recommendedRoute.traffic_level] || 'text-cyan-300'}`}>
                  {TRAFFIC_ICON[recommendedRoute.traffic_level] || '🟡'} {recommendedRoute.traffic_level || 'Mod'}
                </div>
              </div>
              <div className="bg-surface-800/70 p-2 rounded-xl border border-surface-700/50">
                <div className="text-[9px] text-surface-400 font-bold uppercase">Predicted</div>
                <div className={`font-bold mt-0.5 text-[11px] ${recommendedRoute.prediction_available ? (TRAFFIC_COLOR[recommendedRoute.predicted_congestion] || 'text-surface-300') : 'text-surface-500'}`}>
                  {recommendedRoute.prediction_available
                    ? <>{TRAFFIC_ICON[recommendedRoute.predicted_congestion] || '🟡'} {recommendedRoute.predicted_congestion}</>
                    : '—'}
                </div>
              </div>
              <div className="bg-surface-800/70 p-2 rounded-xl border border-surface-700/50">
                <div className="text-[9px] text-surface-400 font-bold uppercase">Risk</div>
                <div className="font-bold text-emerald-400 mt-0.5 text-[11px]">
                  {recommendedRoute.risk_level || 'Low'}
                </div>
              </div>
            </div>

            {/* WHY THIS ROUTE? */}
            {displayReasons.length > 0 && (
              <div className="pt-2 border-t border-surface-800/80">
                <div className="text-[10px] font-extrabold text-surface-400 tracking-wider mb-1 uppercase">
                  WHY THIS ROUTE?
                </div>
                <div className="space-y-1">
                  {displayReasons.map((reason, idx) => (
                    <div
                      key={idx}
                      className={`text-xs flex items-start gap-1.5 ${
                        reason.startsWith('⚠') ? 'text-amber-300 font-medium' : 'text-surface-200'
                      }`}
                    >
                      <span className="leading-snug">{reason}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Alternative Routes Header */}
        <h3 className="text-[10px] font-black uppercase tracking-wider text-surface-400 px-1">
          Route Alternatives ({routes.length})
        </h3>

        {/* Alternative Route Cards List */}
        <div className="space-y-2 max-h-44 overflow-y-auto no-scrollbar pr-0.5">
          {routes.map((r, i) => {
            const isSelected = selectedRoute?.route_id
              ? selectedRoute.route_id === r.route_id
              : selectedRoute?.route_type === r.route_type;
            const isRec = r.route_id === recommendedRouteId;
            const rETA = r.eta_minutes ?? r.duration_min;

            return (
              <button
                key={i}
                onClick={() => setSelectedRoute(r)}
                className={`w-full text-left p-3 rounded-xl border transition-all duration-200 relative ${
                  isSelected
                    ? 'border-cyan-500 bg-cyan-950/40 ring-1 ring-cyan-500/50 shadow-md'
                    : 'border-surface-700/60 bg-surface-800/50 hover:border-surface-600'
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-1.5 truncate">
                    <span className="font-bold text-surface-100 text-xs truncate">{r.label}</span>
                    {isRec && (
                      <span className="px-1.5 py-0.5 rounded text-[8px] font-black bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 flex-shrink-0">
                        REC
                      </span>
                    )}
                  </div>
                  <span
                    className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                    style={{ background: ROUTE_COLORS[r.route_type] || '#06b6d4' }}
                  />
                </div>

                <div className="flex items-baseline justify-between mb-1">
                  <div className="flex items-baseline gap-2">
                    <span className="text-sm font-black text-surface-100">{rETA?.toFixed(0)} min</span>
                    <span className="text-[11px] text-surface-400">{r.distance_km} km</span>
                  </div>
                  {r.overall_score !== undefined && (
                    <span className="text-[11px] font-black text-cyan-400">
                      Score: {r.overall_score}/100
                    </span>
                  )}
                </div>

                <div className="grid grid-cols-3 gap-1 text-[10px] text-surface-400 border-t border-surface-700/40 pt-1">
                  <div>Safety: <span className="font-semibold text-surface-200">{r.safety_score}</span></div>
                  <div className={TRAFFIC_COLOR[r.traffic_level] || 'text-cyan-300'}>
                    {TRAFFIC_ICON[r.traffic_level] || '🟡'} {r.traffic_level || 'Mod'}
                  </div>
                  <div>Risk: <span className="font-semibold text-surface-200">{r.risk_level || 'Low'}</span></div>
                </div>
              </button>
            );
          })}
        </div>

        {/* START NAVIGATION BUTTON */}
        <button
          onClick={startNavigation}
          className="w-full py-3 rounded-2xl font-black text-white text-sm bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 shadow-xl transition-all duration-200 active:scale-98 flex items-center justify-center gap-2"
        >
          <HiPlay className="w-5 h-5" /> Start Navigation
        </button>
      </div>
    );
  };

  return (
    <div className="fixed inset-0 w-screen h-screen overflow-hidden bg-surface-950 z-0">

      {/* ===== FLOATING TOP-RIGHT NAVBAR CONTROLS ===== */}
      <NavbarControls showTraffic={showTraffic} onToggleTraffic={() => setShowTraffic(v => !v)} />

      {/* ===== FLOATING ROUTE PLANNER CARD (TOP-LEFT) ===== */}
      {!isNavigating && (
        <div className="fixed top-4 left-4 sm:left-20 z-[1000] w-[calc(100vw-2rem)] max-w-sm pointer-events-auto">
          <div className="glass-card p-4 shadow-2xl bg-surface-900/95 backdrop-blur-xl border border-surface-800/80 rounded-2xl">
            {renderPlannerContent()}
          </div>

          {/* Floating Route Options Drawer directly below search planner */}
          {routes.length > 0 && (
            <div className="mt-3 glass-card p-4 shadow-2xl bg-surface-900/95 backdrop-blur-xl border border-surface-800/80 rounded-2xl max-h-[calc(100vh-280px)] overflow-y-auto no-scrollbar">
              {renderAlternativesContent()}
            </div>
          )}
        </div>
      )}

      {/* ===== NAVIGATION HUD OVERLAY (DURING LIVE NAVIGATION) ===== */}
      {isNavigating && (
        <div className="fixed top-4 left-4 right-4 lg:left-auto lg:right-4 lg:w-96 z-[1001] flex flex-col gap-3 pointer-events-auto">
          {/* Active Hotspot Warning Banner */}
          {activeHotspotWarning && (
            <div className="glass-card p-4 border-l-4 border-red-500 bg-red-950/90 backdrop-blur-xl shadow-2xl text-red-100 flex items-center justify-between animate-bounce rounded-2xl">
              <div className="flex items-center gap-3">
                <span className="text-2xl">⚠️</span>
                <div>
                  <div className="font-black text-[10px] uppercase tracking-wider text-red-400">Approaching Accident Hotspot</div>
                  <div className="font-bold text-sm">{activeHotspotWarning.name}</div>
                  <div className="text-xs text-red-300 font-medium">
                    {activeHotspotWarning.fatal_count} fatal incident{activeHotspotWarning.fatal_count !== 1 ? 's' : ''} recorded nearby
                  </div>
                </div>
              </div>
              <button onClick={() => setActiveHotspotWarning(null)} className="text-red-400 hover:text-white p-1 font-bold">✕</button>
            </div>
          )}

          {/* Turn instruction card */}
          <div className="glass-card p-5 border-l-4 border-cyan-400 shadow-2xl bg-surface-900/95 backdrop-blur-xl rounded-2xl">
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 rounded-2xl bg-cyan-500/20 flex items-center justify-center">
                <navInstruction.icon className="w-7 h-7 text-cyan-400" />
              </div>
              <div>
                <p className="text-lg font-black text-surface-100">{navInstruction.text}</p>
                <p className="text-xs text-surface-400">on current route step</p>
              </div>
            </div>
          </div>

          {/* Navigation Live Stats */}
          <div className="grid grid-cols-3 gap-2">
            <div className="glass-card p-2.5 text-center bg-surface-900/90 rounded-xl border border-surface-800">
              <p className="text-lg font-black text-cyan-400">{navSpeed}</p>
              <p className="text-[9px] font-bold uppercase tracking-wider text-surface-500">km/h</p>
            </div>
            <div className="glass-card p-2.5 text-center bg-surface-900/90 rounded-xl border border-surface-800">
              <p className="text-lg font-black text-surface-100">{navDistLeft}</p>
              <p className="text-[9px] font-bold uppercase tracking-wider text-surface-500">km left</p>
            </div>
            <div className="glass-card p-2.5 text-center bg-surface-900/90 rounded-xl border border-surface-800">
              <p className="text-lg font-black text-emerald-400">{navETA}</p>
              <p className="text-[9px] font-bold uppercase tracking-wider text-surface-500">min ETA</p>
            </div>
          </div>

          {/* Progress bar */}
          <div className="glass-card p-2.5 bg-surface-900/90 rounded-xl border border-surface-800">
            <div className="w-full h-2 rounded-full bg-surface-800 overflow-hidden">
              <div className="h-full rounded-full bg-cyan-500 transition-all duration-300"
                style={{ width: `${navProgress}%` }} />
            </div>
          </div>

          {/* Stop button */}
          <button onClick={stopNavigation}
            className="w-full py-3 rounded-2xl font-bold text-white bg-red-600 hover:bg-red-500 shadow-xl transition-colors duration-200 flex items-center justify-center gap-2">
            <HiStop className="w-5 h-5" /> Stop Navigation
          </button>
        </div>
      )}

      {/* ===== FULL-SCREEN LEAFLET MAP ===== */}
      <div className="w-full h-full absolute inset-0 z-0">
        <MapContainer center={BANGALORE_CENTER} zoom={12} className="h-full w-full">
          {/* Base Map */}
          <TileLayer attribution='&copy; OpenStreetMap' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
          
          {/* TomTom Real-Time Traffic Overlay Layer */}
          {showTraffic && (
            <TileLayer
              url="http://127.0.0.1:8000/api/traffic/tile/{z}/{x}/{y}"
              tileSize={256}
              opacity={0.75}
              attribution='Traffic &copy; TomTom'
              zIndex={10}
            />
          )}

          {!isNavigating && <FitBounds bounds={bounds} />}
          <FollowMarker position={navPosition} isNavigating={isNavigating} />

          {/* Source & Destination Markers */}
          {sourceCoord && <Marker position={sourceCoord} icon={srcIcon}><Popup><b>Start:</b> {source}</Popup></Marker>}
          {destCoord && <Marker position={destCoord} icon={dstIcon}><Popup><b>Destination:</b> {dest}</Popup></Marker>}

          {/* Alternative Routes (dimmed lines) */}
          {!isNavigating && routes.map((r, i) => (
            ((selectedRoute?.route_id && r.route_id) ? r.route_id !== selectedRoute.route_id : r.route_type !== selectedRoute?.route_type) && (
              <g key={i}>
                <Polyline
                  positions={r.waypoints}
                  pathOptions={{ color: '#000000', weight: 14, opacity: 0 }}
                  eventHandlers={{ click: () => setSelectedRoute(r) }}
                />
                <Polyline
                  positions={r.waypoints}
                  pathOptions={{ color: '#9aa0a6', weight: 4, opacity: 0.8 }}
                  eventHandlers={{ click: () => setSelectedRoute(r) }}
                />
              </g>
            )
          ))}

          {/* Selected Active Route */}
          {selectedRoute && (
            <g>
              <Polyline
                positions={selectedRoute.waypoints}
                pathOptions={{ color: '#1558b0', weight: isNavigating ? 10 : 8, opacity: 0.4 }}
              />
              <Polyline
                positions={selectedRoute.waypoints}
                pathOptions={{ color: '#4285F4', weight: isNavigating ? 6 : 5, opacity: 0.95 }}
              />
            </g>
          )}

          {/* Travelled path (green overlay during live nav) */}
          {isNavigating && travelledPath.length > 1 && (
            <Polyline positions={travelledPath} pathOptions={{ color: '#22c55e', weight: 6, opacity: 0.7 }} />
          )}

          {/* Moving car marker */}
          {isNavigating && navPosition && (
            <Marker position={navPosition} icon={carIconHtml(navBearing)} zIndexOffset={1000} />
          )}

          {/* Risk zones */}
          {riskZones.map((rz, i) => (
            <CircleMarker key={i} center={[rz.lat, rz.lng]} radius={15}
              pathOptions={{ color: rz.level === 'critical' ? '#ef4444' : rz.level === 'high' ? '#f97316' : '#eab308', fillOpacity: 0.3 }}>
              <Popup>Risk: {rz.risk.toFixed(1)}/100 ({rz.level})</Popup>
            </CircleMarker>
          ))}

          {/* Empirical Accident Hotspots */}
          {selectedRoute?.hotspots?.map((hs, i) => (
            <CircleMarker
              key={`hs-${i}`}
              center={[hs.lat, hs.lng]}
              radius={hs.risk_level === 'critical' ? 14 : hs.risk_level === 'high' ? 10 : 8}
              pathOptions={{
                color: hs.risk_level === 'critical' ? '#dc2626' : hs.risk_level === 'high' ? '#ea580c' : '#ca8a04',
                fillColor: hs.risk_level === 'critical' ? '#ef4444' : hs.risk_level === 'high' ? '#f97316' : '#eab308',
                fillOpacity: 0.75,
                weight: 2,
              }}
            >
              <Popup>
                <div className="p-1 text-slate-900 font-sans">
                  <div className="font-bold text-xs text-red-600 flex items-center gap-1">
                    ⚠️ ACCIDENT HOTSPOT ({hs.risk_level.toUpperCase()})
                  </div>
                  <div className="font-semibold text-sm mt-1">{hs.name}</div>
                  <div className="text-xs text-slate-600 mt-1">
                    Total Accidents: <b>{hs.accident_count}</b> | Fatalities: <b className="text-red-600">{hs.fatal_count}</b>
                  </div>
                </div>
              </Popup>
            </CircleMarker>
          ))}

          {/* Map click handler for reporting */}
          <MapClickHandler onMapClick={(latlng) => {
            if (isReporting) {
              setReportLat(latlng.lat.toFixed(6));
              setReportLng(latlng.lng.toFixed(6));
              toast.success(`Coordinates set to: ${latlng.lat.toFixed(4)}, ${latlng.lng.toFixed(4)}`);
            }
          }} active={isReporting} />

          {/* Live User Road Hazards */}
          {hazards.map((h) => (
            <Marker
              key={`hazard-${h.id}`}
              position={[h.latitude, h.longitude]}
              icon={getHazardIcon(h.hazard_type, h.severity)}
            >
              <Popup>
                <div className="p-1 text-slate-900 font-sans min-w-[200px]">
                  <div className="flex items-center justify-between border-b border-slate-200 pb-1.5">
                    <span className="font-bold text-sm text-red-600">⚠️ {h.hazard_type}</span>
                    <span className={`text-[10px] font-extrabold px-2 py-0.5 rounded-full uppercase
                      ${h.severity === 'Critical' ? 'bg-red-100 text-red-700' :
                        h.severity === 'High' ? 'bg-orange-100 text-orange-700' :
                        h.severity === 'Medium' ? 'bg-yellow-100 text-yellow-700' :
                        'bg-green-100 text-green-700'}`}
                    >
                      {h.severity}
                    </span>
                  </div>
                  {h.description && (
                    <p className="text-xs mt-2 text-slate-700 leading-relaxed bg-slate-50 p-2 rounded border border-slate-100">
                      {h.description}
                    </p>
                  )}
                  <div className="text-[10px] text-slate-500 mt-2.5 flex items-center justify-between">
                    <span>Reported: {new Date(h.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                  </div>
                  {user && h.user_id === user.id && (
                    <button
                      onClick={() => handleResolveHazard(h.id)}
                      className="w-full mt-3 py-1.5 text-xs font-bold text-center text-white bg-green-600 hover:bg-green-500 rounded-lg transition-colors duration-150 shadow"
                    >
                      Resolve/Clear Hazard
                    </button>
                  )}
                </div>
              </Popup>
            </Marker>
          ))}
        </MapContainer>

        {/* Floating Map Action Buttons (Bottom Right) */}
        <div className="fixed bottom-6 right-6 z-[1000] flex flex-col gap-2 pointer-events-auto">
          {!isNavigating && (
            <button onClick={locateUser} title="Locate My Position"
              className="p-3 rounded-2xl bg-surface-900/90 border border-surface-700 text-cyan-400 hover:bg-surface-800 shadow-2xl backdrop-blur-md transition-all active:scale-95">
              <HiOutlineLocationMarker className="w-6 h-6" />
            </button>
          )}
          {isNavigating && (
            <button onClick={() => setNavPosition([...navPosition])} title="Recenter Position"
              className="p-3 rounded-2xl bg-cyan-600 text-white hover:bg-cyan-500 shadow-2xl transition-all active:scale-95">
              <HiPaperAirplane className="w-6 h-6" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
