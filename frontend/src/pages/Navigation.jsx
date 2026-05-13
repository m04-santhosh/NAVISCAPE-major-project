import { useState, useEffect, useRef, useCallback } from 'react';
import { MapContainer, TileLayer, Marker, Popup, Polyline, useMap, CircleMarker } from 'react-leaflet';
import L from 'leaflet';
import api from '../services/api';
import toast from 'react-hot-toast';
import { HiLocationMarker, HiSwitchHorizontal, HiSearch, HiShieldCheck, HiClock, HiPlay, HiStop, HiArrowRight, HiArrowUp, HiArrowLeft, HiOutlineLocationMarker, HiNavigation } from 'react-icons/hi';
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

/* ---- helper: interpolate dense points along waypoints ---- */
function interpolateRoute(waypoints, totalSteps = 200) {
  if (waypoints.length < 2) return waypoints;
  const segs = [];
  let totalDist = 0;
  for (let i = 0; i < waypoints.length - 1; i++) {
    const d = Math.sqrt(
      Math.pow(waypoints[i + 1][0] - waypoints[i][0], 2) +
      Math.pow(waypoints[i + 1][1] - waypoints[i][1], 2)
    );
    segs.push({ from: waypoints[i], to: waypoints[i + 1], dist: d });
    totalDist += d;
  }
  const pts = [];
  for (const seg of segs) {
    const n = Math.max(1, Math.round((seg.dist / totalDist) * totalSteps));
    for (let j = 0; j < n; j++) {
      const t = j / n;
      pts.push([
        seg.from[0] + (seg.to[0] - seg.from[0]) * t,
        seg.from[1] + (seg.to[1] - seg.from[1]) * t,
      ]);
    }
  }
  pts.push(waypoints[waypoints.length - 1]);
  return pts;
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

  // Live navigation state
  const [isNavigating, setIsNavigating] = useState(false);
  const [navPosition, setNavPosition] = useState(null);
  const [navIndex, setNavIndex] = useState(0);
  const [navPoints, setNavPoints] = useState([]);
  const [navBearing, setNavBearing] = useState(0);
  const [navProgress, setNavProgress] = useState(0);
  const [navSpeed, setNavSpeed] = useState(0);
  const [navETA, setNavETA] = useState(0);
  const [navDistLeft, setNavDistLeft] = useState(0);
  const [navInstruction, setNavInstruction] = useState({ icon: HiArrowUp, text: 'Head straight' });
  const [travelledPath, setTravelledPath] = useState([]);
  const watchIdRef = useRef(null);
  const mapRef = useRef(null);

  const filteredSource = PRESET_LOCATIONS.filter(l => l.name.toLowerCase().includes(source.toLowerCase()));
  const filteredDest = PRESET_LOCATIONS.filter(l => l.name.toLowerCase().includes(dest.toLowerCase()));

  const selectSource = (loc) => { setSource(loc.name); setSourceCoord([loc.lat, loc.lng]); setShowSourceDD(false); };
  const selectDest = (loc) => { setDest(loc.name); setDestCoord([loc.lat, loc.lng]); setShowDestDD(false); };
  const swapLocations = () => { setSource(dest); setDest(source); setSourceCoord(destCoord); setDestCoord(sourceCoord); };

  const findRoutes = async () => {
    if (!sourceCoord || !destCoord) { toast.error('Select both locations'); return; }
    setLoading(true);
    try {
      const res = await api.get('/route-alternatives', {
        params: { source_lat: sourceCoord[0], source_lng: sourceCoord[1], dest_lat: destCoord[0], dest_lng: destCoord[1] }
      });
      setRoutes(res.data);
      setSelectedRoute(res.data[2]);
      const riskRes = await api.post('/predict/risk', { latitude: (sourceCoord[0]+destCoord[0])/2, longitude: (sourceCoord[1]+destCoord[1])/2 });
      setRiskZones([{ lat: riskRes.data.latitude, lng: riskRes.data.longitude, risk: riskRes.data.risk_score, level: riskRes.data.risk_level }]);
      const all = res.data.flatMap(r => r.waypoints);
      setBounds(L.latLngBounds(all.map(p => [p[0], p[1]])));
      toast.success('Routes calculated!');
    } catch { toast.error('Failed to find routes'); }
    finally { setLoading(false); }
  };

  const saveRoute = async (route) => {
    try { await api.post('/navigate', { source_lat: sourceCoord[0], source_lng: sourceCoord[1], dest_lat: destCoord[0], dest_lng: destCoord[1], source_name: source, dest_name: dest, route_type: route.route_type }); } catch {}
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

  /* ---------- LIVE NAVIGATION ---------- */
  const startNavigation = useCallback(() => {
    if (!selectedRoute) { toast.error('Select a route first'); return; }
    if (!("geolocation" in navigator)) { toast.error('Geolocation not supported'); return; }

    setIsNavigating(true);
    setNavPoints(selectedRoute.waypoints);
    setTravelledPath([sourceCoord]);
    setNavPosition(sourceCoord);
    saveRoute(selectedRoute);
    toast.success('Real-time tracking started! 🚗');

    watchIdRef.current = navigator.geolocation.watchPosition(
      (position) => {
        const { latitude, longitude, heading, speed } = position.coords;
        const currentPos = [latitude, longitude];
        
        setNavPosition(currentPos);
        setTravelledPath(prev => [...prev, currentPos]);
        setNavBearing(heading || 0);
        setNavSpeed(Math.round((speed || 0) * 3.6)); // Convert m/s to km/h

        // Find progress along route
        if (selectedRoute.waypoints.length > 1) {
          // Simplistic progress: find nearest waypoint
          let minD = Infinity;
          let nearestIdx = 0;
          selectedRoute.waypoints.forEach((p, i) => {
            const d = Math.sqrt(Math.pow(p[0] - latitude, 2) + Math.pow(p[1] - longitude, 2));
            if (d < minD) { minD = d; nearestIdx = i; }
          });
          
          const pct = (nearestIdx / (selectedRoute.waypoints.length - 1)) * 100;
          setNavProgress(pct);
          setNavDistLeft(+(selectedRoute.distance_km * (1 - pct / 100)).toFixed(2));
          setNavETA(+(selectedRoute.duration_min * (1 - pct / 100)).toFixed(1));

          // Instructions
          if (nearestIdx < selectedRoute.waypoints.length - 1) {
            const dir = turnDirection(
              selectedRoute.waypoints[Math.max(0, nearestIdx - 1)],
              currentPos,
              selectedRoute.waypoints[nearestIdx + 1]
            );
            setNavInstruction(dir);
          }

          if (pct > 95) {
            setNavInstruction({ icon: HiLocationMarker, text: 'Arriving at destination' });
          }
          
          if (pct >= 100) {
            stopNavigation();
            toast.success('You have arrived! 🎉');
          }
        }
      },
      (error) => toast.error("Location tracking failed"),
      { enableHighAccuracy: true, maximumAge: 1000 }
    );
  }, [selectedRoute, sourceCoord]);

  const stopNavigation = useCallback(() => {
    setIsNavigating(false);
    if (watchIdRef.current) {
      navigator.geolocation.clearWatch(watchIdRef.current);
      watchIdRef.current = null;
    }
    toast('Tracking stopped', { icon: '🛑' });
  }, []);

  // Remove the old animation useEffect

  const srcIcon = new L.Icon({ iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-green.png', shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png', iconSize: [25,41], iconAnchor: [12,41], popupAnchor: [1,-34], shadowSize: [41,41] });
  const dstIcon = new L.Icon({ iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-red.png', shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png', iconSize: [25,41], iconAnchor: [12,41], popupAnchor: [1,-34], shadowSize: [41,41] });

  return (
    <div className="h-[calc(100vh-2rem)] flex flex-col lg:flex-row gap-4 animate-fade-in relative overflow-hidden">

      {/* ===== LEFT PANEL / SEARCH ===== */}
      <div className={`lg:w-96 space-y-4 flex-shrink-0 transition-all duration-500 ${isNavigating ? 'hidden lg:block' : 'block'} overflow-y-auto max-h-full`}>
        <div className="glass-card p-5">
            <h2 className="text-lg font-semibold text-surface-200 mb-4 flex items-center gap-2">
              <HiLocationMarker className="text-primary-400" /> Route Planner
            </h2>
            {/* Source */}
            <div className="relative mb-3">
              <label className="text-xs font-medium text-surface-400 mb-1 block">Source</label>
              <input className="input-field text-sm" placeholder="Search location..." value={source}
                onChange={e => { setSource(e.target.value); setShowSourceDD(true); }}
                onFocus={() => setShowSourceDD(true)} onBlur={() => setTimeout(() => setShowSourceDD(false), 200)} />
              {showSourceDD && filteredSource.length > 0 && (
                <div className="absolute z-50 w-full mt-1 glass-card max-h-48 overflow-y-auto">
                  {filteredSource.map((l,i) => (
                    <button key={i} onMouseDown={() => selectSource(l)} className="w-full text-left px-4 py-2 text-sm text-surface-300 hover:bg-surface-700 transition-colors">{l.name}</button>
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
              <input className="input-field text-sm" placeholder="Search location..." value={dest}
                onChange={e => { setDest(e.target.value); setShowDestDD(true); }}
                onFocus={() => setShowDestDD(true)} onBlur={() => setTimeout(() => setShowDestDD(false), 200)} />
              {showDestDD && filteredDest.length > 0 && (
                <div className="absolute z-50 w-full mt-1 glass-card max-h-48 overflow-y-auto">
                  {filteredDest.map((l,i) => (
                    <button key={i} onMouseDown={() => selectDest(l)} className="w-full text-left px-4 py-2 text-sm text-surface-300 hover:bg-surface-700 transition-colors">{l.name}</button>
                  ))}
                </div>
              )}
            </div>
            <button onClick={findRoutes} disabled={loading} className="btn-primary w-full flex items-center justify-center gap-2">
              {loading ? <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : <><HiSearch className="w-5 h-5" /><span>Find Routes</span></>}
            </button>
          </div>

          {/* Route cards + Start button */}
          {routes.length > 0 && (
            <div className="glass-card p-5 space-y-3">
              <h3 className="text-sm font-semibold text-surface-300">Route Alternatives</h3>
              {routes.map((r, i) => (
                <button key={i} onClick={() => setSelectedRoute(r)}
                  className={`w-full text-left p-4 rounded-xl border transition-all duration-300 ${selectedRoute?.route_type === r.route_type
                    ? 'border-primary-500 bg-primary-500/10' : 'border-surface-700 bg-surface-800/50 hover:border-surface-600'}`}>
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-medium text-surface-200">{r.label}</span>
                    <span className="w-3 h-3 rounded-full" style={{ background: ROUTE_COLORS[r.route_type] }} />
                  </div>
                  <div className="grid grid-cols-3 gap-2 text-xs">
                    <div className="flex items-center gap-1 text-surface-400"><HiLocationMarker className="w-3 h-3" />{r.distance_km} km</div>
                    <div className="flex items-center gap-1 text-surface-400"><HiClock className="w-3 h-3" />{r.duration_min?.toFixed(0)} min</div>
                    <div className="flex items-center gap-1">
                      <HiShieldCheck className="w-3 h-3" />
                      <span className={r.safety_score >= 80 ? 'text-green-400' : r.safety_score >= 60 ? 'text-yellow-400' : 'text-red-400'}>{r.safety_score}</span>
                    </div>
                  </div>
                </button>
              ))}
              {/* START NAVIGATION BUTTON */}
              <button onClick={startNavigation}
                className="w-full mt-2 py-4 rounded-xl font-bold text-white text-lg bg-gradient-to-r from-green-500 to-emerald-600 hover:from-green-400 hover:to-emerald-500 shadow-lg shadow-green-600/30 hover:shadow-green-500/50 transition-all duration-300 hover:-translate-y-0.5 flex items-center justify-center gap-3">
                <HiPlay className="w-6 h-6" /> Start Navigation
              </button>
            </div>
          )}
        </div>

      {/* ===== NAVIGATION HUD (shown during live nav) ===== */}
      {isNavigating && (
        <div className="absolute top-4 left-4 right-4 lg:left-auto lg:right-4 lg:w-96 z-[1000] flex flex-col gap-3 pointer-events-none">
          <div className="pointer-events-auto">
            {/* Turn instruction card */}
            <div className="glass-card p-6 border-l-4 border-primary-400 shadow-2xl">
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
                <div className="h-full rounded-full bg-gradient-to-r from-primary-500 to-green-400 transition-all duration-200"
                  style={{ width: `${navProgress}%` }} />
              </div>
            </div>

            {/* Stop button */}
            <button onClick={stopNavigation}
              className="w-full mt-3 py-3 rounded-xl font-bold text-white bg-gradient-to-r from-red-500 to-red-600 hover:from-red-400 hover:to-red-500 shadow-lg transition-all duration-300 flex items-center justify-center gap-2">
              <HiStop className="w-5 h-5" /> Stop Navigation
            </button>
          </div>
        </div>
      )}

      {/* ===== MAP ===== */}
      <div className="flex-1 glass-card overflow-hidden min-h-[400px]">
        <MapContainer center={BANGALORE_CENTER} zoom={12} className="h-full w-full" style={{ borderRadius: '1rem', minHeight: 400 }}>
          <TileLayer attribution='&copy; OpenStreetMap' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
          {!isNavigating && <FitBounds bounds={bounds} />}
          <FollowMarker position={navPosition} isNavigating={isNavigating} />

          {/* Source & Dest markers */}
          {sourceCoord && <Marker position={sourceCoord} icon={srcIcon}><Popup><b>Start:</b> {source}</Popup></Marker>}
          {destCoord && <Marker position={destCoord} icon={dstIcon}><Popup><b>Destination:</b> {dest}</Popup></Marker>}

          {/* Dimmed alternative routes */}
          {!isNavigating && routes.map((r, i) => (
            r.route_type !== selectedRoute?.route_type && (
              <Polyline key={i} positions={r.waypoints} pathOptions={{ color: ROUTE_COLORS[r.route_type], weight: 3, opacity: 0.3, dashArray: '8 8' }} />
            )
          ))}

          {/* Selected route */}
          {selectedRoute && (
            <Polyline positions={selectedRoute.waypoints}
              pathOptions={{ color: ROUTE_COLORS[selectedRoute.route_type], weight: isNavigating ? 6 : 5, opacity: 0.9 }} />
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
        </MapContainer>

        {/* Map Overlay Buttons */}
        <div className="absolute bottom-6 right-6 z-[1000] flex flex-col gap-2">
          {!isNavigating && (
            <button onClick={locateUser} title="Locate Me"
              className="p-3 rounded-full bg-surface-800 border border-surface-700 text-primary-400 hover:bg-surface-700 shadow-lg transition-all active:scale-95">
              <HiOutlineLocationMarker className="w-6 h-6" />
            </button>
          )}
          {isNavigating && (
            <button onClick={() => setNavPosition([...navPosition])} title="Recenter"
              className="p-3 rounded-full bg-primary-600 text-white hover:bg-primary-500 shadow-lg transition-all active:scale-95">
              <HiNavigation className="w-6 h-6" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
