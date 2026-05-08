import { HiAcademicCap, HiCode, HiChip, HiDatabase, HiGlobe, HiShieldCheck } from 'react-icons/hi';

const techStack = [
  { category: 'Frontend', items: ['React.js', 'TailwindCSS', 'Leaflet.js', 'Recharts', 'Axios'], icon: HiCode, color: 'from-cyan-500 to-blue-500' },
  { category: 'Backend', items: ['Python FastAPI', 'SQLAlchemy', 'JWT Auth', 'REST API'], icon: HiDatabase, color: 'from-purple-500 to-pink-500' },
  { category: 'ML/AI', items: ['TensorFlow/Keras LSTM', 'XGBoost', 'Random Forest', 'A*/Dijkstra'], icon: HiChip, color: 'from-green-500 to-emerald-500' },
  { category: 'Maps & Data', items: ['OpenStreetMap', 'GPS Integration', 'Heatmaps', 'Traffic Simulation'], icon: HiGlobe, color: 'from-orange-500 to-red-500' },
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
    <div className="space-y-10 animate-fade-in max-w-5xl mx-auto">
      {/* Header */}
      <div className="text-center">
        <div className="w-20 h-20 rounded-2xl gradient-bg flex items-center justify-center text-3xl font-bold text-white mx-auto mb-6 shadow-lg shadow-primary-500/30">N</div>
        <h1 className="text-3xl md:text-4xl font-bold mb-3">
          <span className="gradient-text">NAVISCAPE</span>
        </h1>
        <p className="text-xl text-surface-300 mb-2">Intelligent Navigation System for Predictive Traffic Analysis and Risk-Aware Routing</p>
        <p className="text-surface-400 max-w-2xl mx-auto">A final-year BE AI & Data Science project demonstrating the integration of machine learning, graph algorithms, and real-time data visualization for intelligent urban navigation.</p>
      </div>

      {/* Abstract */}
      <div className="glass-card p-8">
        <h2 className="text-xl font-bold text-surface-200 mb-4 flex items-center gap-2">
          <HiAcademicCap className="text-primary-400" /> Project Abstract
        </h2>
        <p className="text-surface-300 leading-relaxed">
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
        <h2 className="text-2xl font-bold text-surface-200 mb-6 text-center">Technology Stack</h2>
        <div className="grid md:grid-cols-2 gap-4">
          {techStack.map((tech, i) => (
            <div key={i} className="stat-card">
              <div className={`w-12 h-12 rounded-xl bg-gradient-to-r ${tech.color} flex items-center justify-center mb-4`}>
                <tech.icon className="w-6 h-6 text-white" />
              </div>
              <h3 className="text-lg font-semibold text-surface-200 mb-3">{tech.category}</h3>
              <div className="flex flex-wrap gap-2">
                {tech.items.map((item, j) => (
                  <span key={j} className="px-3 py-1 rounded-lg bg-surface-800/80 text-surface-300 text-sm border border-surface-700">{item}</span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* System Architecture */}
      <div>
        <h2 className="text-2xl font-bold text-surface-200 mb-6 text-center">System Architecture</h2>
        <div className="space-y-4">
          {architecture.map((step, i) => (
            <div key={i} className="flex gap-4 items-start animate-slide-up" style={{ animationDelay: `${i * 0.1}s` }}>
              <div className="w-10 h-10 rounded-xl gradient-bg flex items-center justify-center font-bold text-white flex-shrink-0">{step.step}</div>
              <div className="glass-card p-4 flex-1">
                <h4 className="font-semibold text-surface-200 mb-1">{step.title}</h4>
                <p className="text-sm text-surface-400">{step.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Key Algorithms */}
      <div className="glass-card p-8">
        <h2 className="text-xl font-bold text-surface-200 mb-4 flex items-center gap-2">
          <HiShieldCheck className="text-green-400" /> Key Algorithms & Models
        </h2>
        <div className="grid md:grid-cols-3 gap-6">
          <div>
            <h4 className="font-semibold text-primary-400 mb-2">LSTM Network</h4>
            <p className="text-sm text-surface-400">Long Short-Term Memory neural network captures temporal dependencies in traffic flow patterns for accurate prediction.</p>
          </div>
          <div>
            <h4 className="font-semibold text-accent-400 mb-2">XGBoost Classifier</h4>
            <p className="text-sm text-surface-400">Gradient boosted decision trees analyze multi-factor accident data for risk scoring with 85%+ accuracy.</p>
          </div>
          <div>
            <h4 className="font-semibold text-green-400 mb-2">A* / Dijkstra</h4>
            <p className="text-sm text-surface-400">Graph-based pathfinding with multi-objective cost functions balancing distance, time, and safety scores.</p>
          </div>
        </div>
      </div>

      {/* Footer */}
      <div className="text-center py-8 border-t border-surface-800">
        <p className="text-surface-500 text-sm">© 2024 NAVISCAPE — Final Year BE AI & Data Science Project</p>
        <p className="text-surface-600 text-xs mt-1">Built with React, FastAPI, TensorFlow, and OpenStreetMap</p>
      </div>
    </div>
  );
}
