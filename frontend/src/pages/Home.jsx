import { Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { HiMap, HiChartBar, HiShieldCheck, HiLightningBolt, HiGlobe, HiCube } from 'react-icons/hi';

const features = [
  { icon: HiMap, title: 'Smart Navigation', desc: 'AI-powered route optimization with real-time traffic analysis', color: 'from-cyan-500 to-blue-500' },
  { icon: HiChartBar, title: 'Traffic Prediction', desc: 'LSTM neural networks predict congestion hours in advance', color: 'from-purple-500 to-pink-500' },
  { icon: HiShieldCheck, title: 'Risk-Aware Routing', desc: 'Avoid accident-prone zones with intelligent safety scoring', color: 'from-green-500 to-emerald-500' },
  { icon: HiLightningBolt, title: 'Real-Time Analytics', desc: 'Live dashboards with traffic density and congestion data', color: 'from-orange-500 to-red-500' },
  { icon: HiGlobe, title: 'Interactive Maps', desc: 'OpenStreetMap integration with heatmaps and route visualization', color: 'from-teal-500 to-cyan-500' },
  { icon: HiCube, title: 'A* & Dijkstra', desc: 'Graph-based pathfinding algorithms for optimal route selection', color: 'from-indigo-500 to-purple-500' },
];

const stats = [
  { value: '99.9%', label: 'Uptime' },
  { value: '89%', label: 'Prediction Accuracy' },
  { value: '8+', label: 'Monitored Junctions' },
  { value: '<2s', label: 'Response Time' },
];

export default function Home() {
  const { isAuthenticated } = useAuth(); // kept for potential other uses but mostly redundant now

  return (
    <div className="min-h-screen bg-surface-950 overflow-hidden">
      {/* Hero */}
      <section className="relative min-h-screen flex items-center justify-center px-6">
        <div className="absolute inset-0">
          <div className="absolute top-20 left-10 w-72 h-72 bg-primary-600/15 rounded-full blur-3xl animate-float" />
          <div className="absolute bottom-20 right-10 w-96 h-96 bg-accent-600/15 rounded-full blur-3xl animate-float" style={{animationDelay:'3s'}} />
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-primary-500/5 rounded-full blur-3xl" />
        </div>

        <div className="relative text-center max-w-4xl mx-auto animate-fade-in">
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full glass-card text-sm text-primary-400 mb-6">
            <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
            AI-Powered Navigation System
          </div>
          <h1 className="text-5xl md:text-7xl font-bold mb-6 leading-tight">
            <span className="gradient-text">NAVISCAPE</span>
          </h1>
          <p className="text-xl md:text-2xl text-surface-300 mb-4 font-light">
            Intelligent Navigation System for
          </p>
          <p className="text-lg md:text-xl text-surface-400 mb-10 max-w-2xl mx-auto">
            Predictive Traffic Analysis & Risk-Aware Routing powered by LSTM, XGBoost, and graph algorithms
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Link to="/dashboard" className="btn-primary text-lg px-8 py-4">
              Go to Dashboard →
            </Link>
            <Link to="/about" className="btn-secondary text-lg px-8 py-4">Learn More</Link>
          </div>
        </div>
      </section>

      {/* Stats */}
      <section className="py-16 px-6 border-t border-surface-800">
        <div className="max-w-5xl mx-auto grid grid-cols-2 md:grid-cols-4 gap-6">
          {stats.map((s, i) => (
            <div key={i} className="text-center animate-slide-up" style={{animationDelay: `${i*0.1}s`}}>
              <p className="text-3xl md:text-4xl font-bold gradient-text">{s.value}</p>
              <p className="text-surface-400 mt-1">{s.label}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Features */}
      <section className="py-20 px-6">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-4xl font-bold mb-4">Powered by <span className="gradient-text">Artificial Intelligence</span></h2>
            <p className="text-surface-400 max-w-2xl mx-auto">Advanced machine learning models and graph algorithms working together to deliver intelligent navigation</p>
          </div>
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
            {features.map((f, i) => (
              <div key={i} className="stat-card group animate-slide-up" style={{animationDelay: `${i*0.1}s`}}>
                <div className={`w-12 h-12 rounded-xl bg-gradient-to-r ${f.color} flex items-center justify-center mb-4 group-hover:scale-110 transition-transform`}>
                  <f.icon className="w-6 h-6 text-white" />
                </div>
                <h3 className="text-lg font-semibold text-surface-100 mb-2">{f.title}</h3>
                <p className="text-surface-400 text-sm leading-relaxed">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-surface-800 py-8 px-6 text-center">
        <p className="text-surface-500 text-sm">© 2024 NAVISCAPE — Final Year BE AI-DS Project</p>
      </footer>
    </div>
  );
}
