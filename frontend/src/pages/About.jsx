import { HiAcademicCap, HiCode, HiChip, HiDatabase, HiGlobe, HiShieldCheck } from 'react-icons/hi';

const techStack = [
  { category: 'Frontend', items: ['React.js', 'TailwindCSS', 'Leaflet.js', 'Recharts', 'Axios'], icon: HiCode },
  { category: 'Backend', items: ['Python FastAPI', 'SQLAlchemy', 'JWT Auth', 'REST API'], icon: HiDatabase },
  { category: 'ML/AI', items: ['TensorFlow/Keras LSTM', 'XGBoost', 'Random Forest', 'A*/Dijkstra'], icon: HiChip },
  { category: 'Maps & Data', items: ['OpenStreetMap', 'GPS Integration', 'Heatmaps', 'Traffic Simulation'], icon: HiGlobe },
];

const architecture = [
  { step: '1', title: 'Data Collection', desc: 'Historical traffic counts, accident records, GPS coordinates, and road network data' },
  { step: '2', title: 'ML Training', desc: 'LSTM model for traffic prediction, XGBoost for risk analysis, trained on 2 years of data' },
  { step: '3', title: 'Route Optimization', desc: 'A* and Dijkstra algorithms compute optimal routes balancing distance and safety' },
  { step: '4', title: 'Real-Time Analysis', desc: 'Live traffic simulation, congestion forecasting, and dynamic risk assessment' },
  { step: '5', title: 'Visualization', desc: 'Interactive maps, heatmaps, charts, and comprehensive analytics dashboard' },
];

export default function About() {
  return (
    <div className="space-y-8 animate-fade-in max-w-4xl mx-auto">
      {/* Header */}
      <div>
        <h1 className="text-2xl md:text-3xl font-bold text-surface-100 mb-2">About NAVISCAPE</h1>
        <p className="text-surface-400">
          Intelligent Navigation System for Predictive Traffic Analysis and Risk-Aware Routing.
          Final year BE AI & Data Science project.
        </p>
      </div>

      {/* Abstract */}
      <div className="glass-card p-6">
        <h2 className="text-lg font-semibold text-surface-200 mb-3 flex items-center gap-2">
          <HiAcademicCap className="text-primary-400 w-5 h-5" /> Project Abstract
        </h2>
        <p className="text-surface-300 leading-relaxed text-sm">
          NAVISCAPE addresses the growing challenges of urban traffic congestion and road safety by combining
          predictive analytics with intelligent routing. The system employs LSTM neural networks trained on
          historical traffic data to forecast congestion patterns up to 24 hours in advance. Simultaneously,
          an XGBoost classifier analyzes accident data incorporating location, time, weather, and road conditions
          to generate real-time risk scores. These predictions feed into a multi-objective route optimization
          engine that uses A* and Dijkstra algorithms to recommend routes that balance travel time with safety.
          The platform features an interactive map interface with real-time heatmaps, a comprehensive analytics
          dashboard, and an admin panel for dataset management, providing a complete solution for intelligent
          urban navigation.
        </p>
      </div>

      {/* Tech Stack */}
      <div>
        <h2 className="text-xl font-bold text-surface-200 mb-4">Technology Stack</h2>
        <div className="grid md:grid-cols-2 gap-4">
          {techStack.map((tech, i) => (
            <div key={i} className="stat-card">
              <div className="flex items-center gap-2 mb-3">
                <tech.icon className="w-5 h-5 text-primary-400" />
                <h3 className="text-base font-semibold text-surface-200">{tech.category}</h3>
              </div>
              <div className="flex flex-wrap gap-2">
                {tech.items.map((item, j) => (
                  <span key={j} className="px-2.5 py-1 rounded-lg bg-surface-800/80 text-surface-300 text-xs border border-surface-700">{item}</span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* System Architecture */}
      <div>
        <h2 className="text-xl font-bold text-surface-200 mb-4">System Architecture</h2>
        <div className="space-y-3">
          {architecture.map((step, i) => (
            <div key={i} className="flex gap-3 items-start">
              <span className="w-7 h-7 rounded-lg bg-primary-500/15 flex items-center justify-center text-sm font-semibold text-primary-400 flex-shrink-0 mt-0.5">
                {step.step}
              </span>
              <div className="glass-card p-4 flex-1">
                <h4 className="font-medium text-surface-200 mb-1 text-sm">{step.title}</h4>
                <p className="text-xs text-surface-400 leading-relaxed">{step.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Key Algorithms */}
      <div className="glass-card p-6">
        <h2 className="text-lg font-semibold text-surface-200 mb-4 flex items-center gap-2">
          <HiShieldCheck className="text-green-400 w-5 h-5" /> Key Algorithms & Models
        </h2>
        <div className="grid md:grid-cols-3 gap-6">
          <div>
            <h4 className="font-medium text-primary-400 mb-1.5 text-sm">LSTM Network</h4>
            <p className="text-xs text-surface-400 leading-relaxed">Long Short-Term Memory neural network captures temporal dependencies in traffic flow patterns for accurate prediction.</p>
          </div>
          <div>
            <h4 className="font-medium text-primary-400 mb-1.5 text-sm">XGBoost Classifier</h4>
            <p className="text-xs text-surface-400 leading-relaxed">Gradient boosted decision trees analyze multi-factor accident data for risk scoring with 85%+ accuracy.</p>
          </div>
          <div>
            <h4 className="font-medium text-green-400 mb-1.5 text-sm">A* / Dijkstra</h4>
            <p className="text-xs text-surface-400 leading-relaxed">Graph-based pathfinding with multi-objective cost functions balancing distance, time, and safety scores.</p>
          </div>
        </div>
      </div>

      {/* Footer */}
      <div className="text-center py-6 border-t border-surface-800/60">
        <p className="text-surface-500 text-sm">© 2025 NAVISCAPE — Final Year BE AI & Data Science Project</p>
        <p className="text-surface-600 text-xs mt-1">Built with React, FastAPI, TensorFlow, and OpenStreetMap</p>
      </div>
    </div>
  );
}
