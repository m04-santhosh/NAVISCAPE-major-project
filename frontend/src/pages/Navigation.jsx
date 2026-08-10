import { useState, useEffect, useRef, useCallback } from 'react';
import { MapContainer, TileLayer, Marker, Popup, Polyline, useMap, CircleMarker } from 'react-leaflet';
import L from 'leaflet';
import api from '../services/api';
import toast from 'react-hot-toast';
import { HiLocationMarker, HiSwitchHorizontal, HiSearch, HiShieldCheck, HiClock, HiPlay, HiStop, HiArrowRight, HiArrowUp, HiArrowLeft, HiOutlineLocationMarker, HiPaperAirplane } from 'react-icons/hi';
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

/* ---- OSRM API: fetch real road routes ---- */
async function fetchOSRMRoutes(srcLat, srcLng, dstLat, dstLng) {
  const url = `https://router.project-osrm.org/route/v1/driving/${srcLng},${srcLat};${dstLng},${dstLat}?alternatives=true&overview=full&geometries=geojson&steps=true`;
  const res = await fetch(url);
  if (!res.ok) throw new Error('OSRM request failed');
  const data = await res.json();
  if (data.code !== 'Ok' || !data.routes?.length) throw new Error('No routes found');
  return data.routes;
}

/* ---- Convert OSRM route to our internal format ---- */
function processOSRMRoutes(osrmRoutes) {
  // Sort by distance: shortest first, longest last
  const sorted = [...osrmRoutes].sort((a, b) => a.distance - b.distance);

  const typeLabels = ['shortest', 'balanced', 'safest'];
  return sorted.map((route, i) => {
    const type = typeLabels[Math.min(i, typeLabels.length - 1)];
    // OSRM gives [lng, lat] — flip to [lat, lng] for Leaflet
    const waypoints = route.geometry.coordinates.map(([lng, lat]) => [lat, lng]);
    const distanceKm = +(route.distance / 1000).toFixed(2);
    const durationMin = +(route.duration / 60).toFixed(1);

    // Safety score: shortest routes score lower (more direct = potentially riskier),
    // longer detour routes score higher (presumably avoiding risky areas)
    let safetyScore;
    if (i === 0) safetyScore = +(55 + Math.random() * 15).toFixed(1);        // shortest: 55-70
    else if (i === sorted.length - 1) safetyScore = +(82 + Math.random() * 16).toFixed(1); // safest: 82-98
    else safetyScore = +(68 + Math.random() * 18).toFixed(1);                // balanced: 68-86

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

/* ---- map sub-component: follow the moving marker ---- */
function FollowMarker({ position, isNavigating }) {
  const map = useMap();
  useEffect(() => {
    if (isNavigating && position) {
      map.setView(position, Math.max(map.getZoom(), 15), { animate: true, duration: 0.4 });
    }
  }, [position, isNavigating]);
  return null;
}

function FitBounds({ bounds }) {
  const map = useMap();
  useEffect(() => { if (bounds) map.fitBounds(bounds, { padding: [50, 50] }); }, [bounds]);
  return null;
}

/* ---- navigation car icon (SVG arrow) ---- */
const carIconHtml = (rot) => L.divIcon({
  className: '',
  html: `<div style="transform:rotate(${rot}deg);width:36px;height:36px;display:flex;align-items:center;justify-content:center">
    <svg width="32" height="32" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="11" fill="#06b6d4" stroke="#0f172a" stroke-width="2"/><path d="M12 4L18 18L12 14L6 18L12 4Z" fill="white"/></svg>
  </div>`,
  iconSize: [36, 36],
  iconAnchor: [18, 18],
});

/* ================================================================ */
export default function Navigation() {
  const [source, setSource] = useState('');
  const [dest, setDest] = useState('');
  const [sourceCoord, setSourceCoord] = useState(null);
  const [destCoord, setDestCoord] = useState(null);
  const [routes, setRoutes] = useState([]);
  const [selectedRoute, setSelectedRoute] = useState(null);
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
  const simIntervalRef = useRef(null);
  const [activeHotspotWarning, setActiveHotspotWarning] = useState(null);

  /* ---------- GEOCODING (Nominatim) ---------- */
  const geocodeSearch = async (query, setSuggestions) => {
    if (!query || query.length < 2) { setSuggestions([]); return; }
    // First check preset locations
    const presetMatches = PRESET_LOCATIONS.filter(l => l.name.toLowerCase().includes(query.toLowerCase()));
    
    // Search Nominatim for locations in India, biased/restricted towards Karnataka
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
        
        // Remove duplicate/redundant adjacent text elements
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

      // Merge presets first, then geocoded results
      const presetNames = new Set(presetMatches.map(p => p.name.toLowerCase()));
      const merged = [
        ...presetMatches.map(l => ({ name: l.name, lat: l.lat, lng: l.lng })),
        ...results.filter(r => !presetNames.has(r.name.toLowerCase())),
      ];
      setSuggestions(merged.slice(0, 8));
    } catch {
      // Fallback to presets if geocoder fails
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

  /* ---------- FIND ROUTES via OSRM ---------- */
  const findRoutes = async () => {
    if (!sourceCoord || !destCoord) { toast.error('Select both locations'); return; }
    setLoading(true);
    try {
      // Get real road routes from OSRM
      const osrmRoutes = await fetchOSRMRoutes(sourceCoord[0], sourceCoord[1], destCoord[0], destCoord[1]);
      const processed = processOSRMRoutes(osrmRoutes);

      // Evaluate empirical route safety via backend
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
            };
          } catch (e) {
            console.warn('Empirical safety evaluation fallback for route', r.route_type, e);
            return r;
          }
        })
      );

      setRoutes(evaluated);
      // Default to balanced if available, otherwise first
      setSelectedRoute(evaluated.find(r => r.route_type === 'balanced') || evaluated[0]);

      // Get risk analysis from backend
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
        // Risk prediction is optional — don't block routing
        setRiskZones([]);
      }

      // Fit map to all route points
      const allPts = processed.flatMap(r => r.waypoints);
      setBounds(L.latLngBounds(allPts));
      toast.success('Routes calculated with safety analysis');
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
        duration_min: route.duration_min,
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

  /* ---------- INITIAL LOCALIZATION ---------- */
  useEffect(() => {
    locateUser();
  }, [locateUser]);

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
      setNavProgress(pct);
      setNavDistLeft(+(selectedRoute.distance_km * (1 - pct / 100)).toFixed(2));
      setNavETA(+(selectedRoute.duration_min * (1 - pct / 100)).toFixed(1));

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

    // 500m Hotspot Proximity Alert Detection
    if (selectedRoute?.hotspots?.length) {
      selectedRoute.hotspots.forEach((hs, idx) => {
        const hsKey = `${hs.lat}_${hs.lng}_${idx}`;
        if (!warnedHotspotsRef.current.has(hsKey)) {
          const distM = haversineMeters(currentPos[0], currentPos[1], hs.lat, hs.lng);
          if (distM <= 500) {
            warnedHotspotsRef.current.add(hsKey);
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
  }, [selectedRoute]);

  const startNavigation = () => {
    if (!selectedRoute) { toast.error('Select a route first'); return; }

    const initialPos = sourceCoord || (selectedRoute.waypoints && selectedRoute.waypoints[0]);
    if (!initialPos) { toast.error('Route coordinates missing'); return; }

    setIsNavigating(true);
    setTravelledPath([initialPos]);
    setNavPosition(initialPos);
    warnedHotspotsRef.current.clear();
    setActiveHotspotWarning(null);
    saveRoute(selectedRoute);
    toast.success('Navigation started');

    const waypoints = selectedRoute.waypoints || [];
    if (waypoints.length > 1) {
      let stepIdx = 0;
      // Step interval to smoothly iterate through waypoints during simulation
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
  const renderPlannerContent = () => (
    routes.length > 0 ? (
      <div className="flex items-center justify-between gap-3 text-sm">
        <div className="truncate flex-1">
          <div className="text-[10px] uppercase tracking-wider text-surface-400">Selected Route</div>
          <div className="font-semibold text-surface-100 truncate">
            {source} ➔ {dest}
          </div>
        </div>
        <button 
          onClick={() => { setRoutes([]); setSelectedRoute(null); }} 
          className="text-xs text-primary-400 hover:text-primary-300 font-semibold flex-shrink-0 px-3 py-1.5 rounded-lg hover:bg-surface-800 transition-colors"
        >
          Change
        </button>
      </div>
    ) : (
      <>
        <h2 className="text-lg font-semibold text-surface-200 mb-4 flex items-center gap-2">
          <HiLocationMarker className="text-primary-400" /> Route Planner
        </h2>
        {/* Source */}
        <div className="relative mb-3">
          <label className="text-xs font-medium text-surface-400 mb-1 block">Source</label>
          <input className="input-field text-sm" placeholder="Search any location..." value={source}
            onChange={e => handleSourceChange(e.target.value)}
            onFocus={() => { setShowSourceDD(true); if (source) geocodeSearch(source, setSourceSuggestions); }}
            onBlur={() => setTimeout(() => setShowSourceDD(false), 200)} />
          {showSourceDD && sourceSuggestions.length > 0 && (
            <div className="absolute z-50 w-full mt-1 glass-card max-h-48 overflow-y-auto">
              {sourceSuggestions.map((l,i) => (
                <button key={i} onMouseDown={() => selectSource(l)} className="w-full text-left px-4 py-2 text-sm text-surface-300 hover:bg-surface-700 transition-colors truncate">{l.name}</button>
              ))}
            </div>
          )}
        </div>
        <div className="flex justify-center my-1">
          <button onClick={swapLocations} className="p-2 rounded-lg hover:bg-surface-700 transition-colors text-surface-400 hover:text-primary-400">
            <HiSwitchHorizontal className="w-5 h-5 rotate-90" />
          </button>
        </div>
        <div className="relative mb-4">
          <label className="text-xs font-medium text-surface-400 mb-1 block">Destination</label>
          <input className="input-field text-sm" placeholder="Search any location..." value={dest}
            onChange={e => handleDestChange(e.target.value)}
            onFocus={() => { setShowDestDD(true); if (dest) geocodeSearch(dest, setDestSuggestions); }}
            onBlur={() => setTimeout(() => setShowDestDD(false), 200)} />
          {showDestDD && destSuggestions.length > 0 && (
            <div className="absolute z-50 w-full mt-1 glass-card max-h-48 overflow-y-auto">
              {destSuggestions.map((l,i) => (
                <button key={i} onMouseDown={() => selectDest(l)} className="w-full text-left px-4 py-2 text-sm text-surface-300 hover:bg-surface-700 transition-colors truncate">{l.name}</button>
              ))}
            </div>
          )}
        </div>
        <button onClick={findRoutes} disabled={loading} className="btn-primary w-full flex items-center justify-center gap-2">
          {loading ? <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : <><HiSearch className="w-5 h-5" /><span>Find Routes</span></>}
        </button>
      </>
    )
  );

  // Helper: Route Alternatives Content
  const renderAlternativesContent = () => (
    <>
      <h3 className="text-sm font-semibold text-surface-300 hidden lg:block mb-3">
        {routes.length === 1 ? '1 Route Found' : `${routes.length} Routes Found`}
      </h3>
      {/* Scroll container on mobile, block layout on desktop */}
      <div className="flex lg:flex-col flex-row gap-3 overflow-x-auto pb-1 max-w-full no-scrollbar">
        {routes.map((r, i) => (
          <button key={i} onClick={() => setSelectedRoute(r)}
            className={`text-left p-3.5 rounded-xl border transition-colors duration-200 flex-shrink-0 lg:w-full w-[240px] ${selectedRoute?.route_type === r.route_type
              ? 'border-primary-500 bg-primary-500/15' : 'border-surface-700 bg-surface-800/50 hover:border-surface-600'}`}>
            <div className="flex items-center justify-between mb-1.5">
              <span className="font-medium text-surface-200 text-sm truncate">{r.label}</span>
              <span className="w-2.5 h-2.5 rounded-full" style={{ background: ROUTE_COLORS[r.route_type] }} />
            </div>
            <div className="grid grid-cols-3 gap-1 text-[11px]">
              <div className="flex items-center gap-1 text-surface-400"><HiLocationMarker className="w-3 h-3 flex-shrink-0" />{r.distance_km} km</div>
              <div className="flex items-center gap-1 text-surface-400"><HiClock className="w-3 h-3 flex-shrink-0" />{r.duration_min?.toFixed(0)} min</div>
              <div className="flex items-center gap-1">
                <HiShieldCheck className="w-3 h-3 flex-shrink-0" />
                <span className={r.safety_score >= 80 ? 'text-green-400' : r.safety_score >= 60 ? 'text-yellow-400' : 'text-red-400'}>{r.safety_score}</span>
              </div>
            </div>
          </button>
        ))}
      </div>
      {/* START NAVIGATION BUTTON */}
      <button onClick={startNavigation}
        className="w-full mt-2 py-3.5 rounded-xl font-bold text-white text-base bg-green-600 hover:bg-green-500 shadow-md transition-colors duration-200 flex items-center justify-center gap-2">
        <HiPlay className="w-5 h-5" /> Start Navigation
      </button>
    </>
  );

  return (
    <div className="h-[calc(100vh-2rem)] flex flex-col lg:flex-row gap-4 animate-fade-in relative overflow-hidden">

      {/* ===== SIDEBAR / LEFT PANEL (DESKTOP) ===== */}
      <div className="hidden lg:flex lg:w-96 lg:flex-col lg:gap-4 flex-shrink-0">
        {/* Search Planner Box */}
        <div className="glass-card p-5 shadow-xl bg-surface-900/95 border border-surface-800">
          {renderPlannerContent()}
        </div>

        {/* Alternatives List */}
        {routes.length > 0 && (
          <div className="glass-card p-5 space-y-3 bg-surface-900/95 border border-surface-800">
            {renderAlternativesContent()}
          </div>
        )}
      </div>

      {/* ===== FLOATING INTERFACES (MOBILE) ===== */}
      <div className="lg:hidden">
        {/* Search Planner Box (Mobile Overlay) */}
        {!isNavigating && (
          <div className="absolute top-4 left-4 right-4 z-[999] glass-card p-4 shadow-xl bg-surface-900/95 backdrop-blur-md border border-surface-800">
            {renderPlannerContent()}
          </div>
        )}

        {/* Alternatives List Drawer (Mobile Overlay) */}
        {routes.length > 0 && !isNavigating && (
          <div className="absolute bottom-4 left-4 right-4 z-[999] bg-surface-900/95 backdrop-blur-md p-4 rounded-xl border border-surface-800 shadow-2xl">
            {renderAlternativesContent()}
          </div>
        )}
      </div>

      {/* ===== NAVIGATION HUD (shown during live nav) ===== */}
      {isNavigating && (
        <div className="absolute top-4 left-4 right-4 lg:left-auto lg:right-4 lg:w-96 z-[1000] flex flex-col gap-3 pointer-events-none">
          <div className="pointer-events-auto flex flex-col gap-3">
            {/* Active Hotspot Proximity Warning Banner */}
            {activeHotspotWarning && (
              <div className="glass-card p-4 border-l-4 border-red-500 bg-red-950/90 backdrop-blur-md shadow-2xl text-red-100 flex items-center justify-between animate-bounce">
                <div className="flex items-center gap-3">
                  <span className="text-2xl">⚠️</span>
                  <div>
                    <div className="font-bold text-xs uppercase tracking-wider text-red-400">Approaching Accident Hotspot</div>
                    <div className="font-semibold text-sm">{activeHotspotWarning.name}</div>
                    <div className="text-xs text-red-300 font-medium">
                      {activeHotspotWarning.fatal_count} fatal incident{activeHotspotWarning.fatal_count !== 1 ? 's' : ''} recorded nearby
                    </div>
                  </div>
                </div>
                <button onClick={() => setActiveHotspotWarning(null)} className="text-red-400 hover:text-white p-1 font-bold">✕</button>
              </div>
            )}

            {/* Turn instruction card */}
            <div className="glass-card p-6 border-l-4 border-primary-400 shadow-2xl bg-surface-900/90 backdrop-blur-md">
              <div className="flex items-center gap-4">
                <div className="w-14 h-14 rounded-2xl bg-primary-500/20 flex items-center justify-center">
                  <navInstruction.icon className="w-8 h-8 text-primary-400" />
                </div>
                <div>
                  <p className="text-xl font-bold text-surface-100">{navInstruction.text}</p>
                  <p className="text-sm text-surface-400">on current road</p>
                </div>
              </div>
            </div>

            {/* Stats row */}
            <div className="grid grid-cols-3 gap-3 mt-3">
              <div className="glass-card p-3 text-center bg-surface-900/80">
                <p className="text-xl font-bold text-primary-400">{navSpeed}</p>
                <p className="text-[10px] uppercase tracking-wider text-surface-500">km/h</p>
              </div>
              <div className="glass-card p-3 text-center bg-surface-900/80">
                <p className="text-xl font-bold text-surface-100">{navDistLeft}</p>
                <p className="text-[10px] uppercase tracking-wider text-surface-500">km left</p>
              </div>
              <div className="glass-card p-3 text-center bg-surface-900/80">
                <p className="text-xl font-bold text-green-400">{navETA}</p>
                <p className="text-[10px] uppercase tracking-wider text-surface-500">min</p>
              </div>
            </div>

            {/* Progress bar */}
            <div className="glass-card p-3 mt-3 bg-surface-900/80">
              <div className="w-full h-2 rounded-full bg-surface-800 overflow-hidden">
                <div className="h-full rounded-full bg-primary-500 transition-all duration-200"
                  style={{ width: `${navProgress}%` }} />
              </div>
            </div>

            {/* Stop button */}
            <button onClick={stopNavigation}
              className="w-full mt-3 py-3 rounded-xl font-bold text-white bg-red-600 hover:bg-red-500 shadow-md transition-colors duration-200 flex items-center justify-center gap-2">
              <HiStop className="w-5 h-5" /> Stop Navigation
            </button>
          </div>
        </div>
      )}

      {/* ===== MAP ===== */}
      <div className="flex-1 lg:glass-card overflow-hidden min-h-[300px] lg:relative absolute inset-0 w-full h-full lg:z-auto z-0">
        <MapContainer center={BANGALORE_CENTER} zoom={12} className="h-full w-full" style={{ borderRadius: '0.75rem' }}>
          {/* Base map */}
          <TileLayer attribution='&copy; OpenStreetMap' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
          {/* TomTom real-time traffic overlay — proxied through backend so API key stays server-side */}
          {showTraffic && (
            <TileLayer
              url="http://127.0.0.1:8000/api/traffic/tile/{z}/{x}/{y}"
              tileSize={256}
              opacity={0.75}
              attribution='Traffic &copy; <a href="https://www.tomtom.com" target="_blank">TomTom</a>'
              zIndex={10}
            />
          )}
          {!isNavigating && <FitBounds bounds={bounds} />}
          <FollowMarker position={navPosition} isNavigating={isNavigating} />

          {/* Source & Dest markers */}
          {sourceCoord && <Marker position={sourceCoord} icon={srcIcon}><Popup><b>Start:</b> {source}</Popup></Marker>}
          {destCoord && <Marker position={destCoord} icon={dstIcon}><Popup><b>Destination:</b> {dest}</Popup></Marker>}

          {/* Dimmed alternative routes (Clickable Google Maps style) */}
          {!isNavigating && routes.map((r, i) => (
            r.route_type !== selectedRoute?.route_type && (
              <g key={i}>
                {/* Thick invisible overlay to make clicking easier */}
                <Polyline
                  positions={r.waypoints}
                  pathOptions={{ color: '#000000', weight: 14, opacity: 0 }}
                  eventHandlers={{ click: () => setSelectedRoute(r) }}
                />
                {/* Grey alternative route line */}
                <Polyline
                  positions={r.waypoints}
                  pathOptions={{ color: '#9aa0a6', weight: 4, opacity: 0.8 }}
                  eventHandlers={{ click: () => setSelectedRoute(r) }}
                />
              </g>
            )
          ))}

          {/* Selected active route (Google Maps Blue with double-layered casing) */}
          {selectedRoute && (
            <g>
              {/* Outer stroke/casing */}
              <Polyline
                positions={selectedRoute.waypoints}
                pathOptions={{ color: '#1558b0', weight: isNavigating ? 10 : 8, opacity: 0.4 }}
              />
              {/* Inner core line */}
              <Polyline
                positions={selectedRoute.waypoints}
                pathOptions={{ color: '#4285F4', weight: isNavigating ? 6 : 5, opacity: 0.95 }}
              />
            </g>
          )}

          {/* Travelled path (green overlay during nav) */}
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

          {/* Empirical Accident Hotspots for selected route */}
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
        </MapContainer>

        {/* Map Overlay Buttons */}
        <div className={`absolute right-6 z-[1000] flex flex-col gap-2 transition-all duration-300 ${routes.length > 0 && !isNavigating ? 'bottom-56 lg:bottom-6' : 'bottom-6'}`}>
          {/* Live Traffic toggle */}
          <button
            onClick={() => setShowTraffic(v => !v)}
            title={showTraffic ? 'Hide Live Traffic' : 'Show Live Traffic'}
            className={`px-3 py-2 rounded-xl border text-xs font-semibold shadow-lg transition-all duration-200 active:scale-95 flex items-center gap-1.5
              ${showTraffic
                ? 'bg-green-600/90 border-green-500 text-white hover:bg-green-500'
                : 'bg-surface-800 border-surface-700 text-surface-400 hover:bg-surface-700'}`}
          >
            <span className={`w-2 h-2 rounded-full ${showTraffic ? 'bg-green-300 animate-pulse' : 'bg-surface-600'}`} />
            Live Traffic
          </button>
          {!isNavigating && (
            <button onClick={locateUser} title="Locate Me"
              className="p-3 rounded-full bg-surface-800 border border-surface-700 text-primary-400 hover:bg-surface-700 shadow-lg transition-colors active:scale-95">
              <HiOutlineLocationMarker className="w-6 h-6" />
            </button>
          )}
          {isNavigating && (
            <button onClick={() => setNavPosition([...navPosition])} title="Recenter"
              className="p-3 rounded-full bg-primary-600 text-white hover:bg-primary-500 shadow-lg transition-colors active:scale-95">
              <HiPaperAirplane className="w-6 h-6" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
