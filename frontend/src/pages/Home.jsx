import { Link } from 'react-router-dom';
import { HiMap, HiChartBar, HiShieldCheck, HiLightningBolt, HiGlobe, HiCube } from 'react-icons/hi';

const features = [
  { icon: HiMap, title: 'Smart Navigation', desc: 'Route optimization with real-time traffic data from Bangalore junctions' },
  { icon: HiChartBar, title: 'Traffic Prediction', desc: 'LSTM neural networks trained on 2 years of junction data to forecast congestion' },
  { icon: HiShieldCheck, title: 'Risk-Aware Routing', desc: 'XGBoost model scores accident risk based on location, time, and road conditions' },
  { icon: HiLightningBolt, title: 'Live Monitoring', desc: 'Real-time dashboards showing vehicle counts and congestion levels per junction' },
  { icon: HiGlobe, title: 'Interactive Maps', desc: 'OpenStreetMap with route visualization, heatmaps, and live navigation mode' },
  { icon: HiCube, title: 'Graph Pathfinding', desc: 'A* and Dijkstra algorithms with multi-objective cost functions' },
];

export default function Home() {
  return (
    <div className="min-h-screen bg-surface-950">
      {/* Hero */}
      <section className="min-h-screen flex items-center justify-center px-6">
        <div className="text-center max-w-3xl mx-auto animate-fade-in">
          <h1 className="text-5xl md:text-7xl font-bold mb-6 text-surface-100 tracking-tight">
            NAVISCAPE
          </h1>
          <p className="text-xl md:text-2xl text-surface-300 mb-3 font-light">
            Intelligent Navigation System
          </p>
          <p className="text-base text-surface-400 mb-10 max-w-xl mx-auto leading-relaxed">
            A traffic prediction and risk-aware routing platform built with LSTM, XGBoost, 
            and graph algorithms. Final year BE AI & Data Science project.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Link to="/dashboard" className="btn-primary text-lg px-8 py-4">
              Open Dashboard
            </Link>
            <Link to="/about" className="btn-secondary text-lg px-8 py-4">About the Project</Link>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="py-20 px-6 border-t border-surface-800/60">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-14">
            <h2 className="text-2xl md:text-3xl font-bold text-surface-100 mb-3">What It Does</h2>
            <p className="text-surface-400 max-w-lg mx-auto">The system combines ML predictions with graph-based routing to help navigate Bangalore's traffic.</p>
          </div>
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-5">
            {features.map((f, i) => (
              <div key={i} className="stat-card animate-slide-up" style={{animationDelay: `${i * 0.05}s`}}>
                <f.icon className="w-6 h-6 text-primary-400 mb-3" />
                <h3 className="text-base font-semibold text-surface-100 mb-1.5">{f.title}</h3>
                <p className="text-surface-400 text-sm leading-relaxed">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-surface-800/60 py-8 px-6 text-center">
        <p className="text-surface-500 text-sm">© 2025 NAVISCAPE — Final Year BE AI & Data Science Project</p>
      </footer>
    </div>
  );
}
