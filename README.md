# NAVISCAPE: Intelligent Navigation System for Predictive Traffic Analysis and Risk-Aware Routing

An AI-powered navigation platform combining LSTM-based traffic prediction, XGBoost risk analysis, and graph-based route optimization. Built as a final-year BE AI & Data Science project.

![NAVISCAPE](https://img.shields.io/badge/NAVISCAPE-AI%20Navigation-06b6d4?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?style=flat-square&logo=react&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?style=flat-square&logo=fastapi&logoColor=white)
![TensorFlow](https://img.shields.io/badge/TensorFlow-2.16-FF6F00?style=flat-square&logo=tensorflow&logoColor=white)

## Features

- **Smart Navigation**: Source-to-destination routing with interactive map and multiple route alternatives
- **LSTM Traffic Prediction**: 24-hour congestion forecasting trained on historical traffic data
- **Risk-Aware Routing**: XGBoost-based accident risk scoring with safety-optimized paths
- **A\*/Dijkstra Algorithms**: Multi-objective route optimization (shortest vs safest vs balanced)
- **Real-Time Dashboard**: Live traffic analytics, risk heatmaps, and prediction charts
- **Admin Panel**: Dataset management, user administration, and model monitoring
- **JWT Authentication**: Secure login/register with role-based access control
- **Dark/Light Mode**: Modern glassmorphism UI with smooth theme transitions

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, TailwindCSS 3, Leaflet.js, Recharts, Axios |
| Backend | Python FastAPI, SQLAlchemy, JWT (python-jose) |
| Database | SQLite (WAL mode) |
| ML Models | TensorFlow/Keras (LSTM), XGBoost, Random Forest, scikit-learn |
| Maps | OpenStreetMap, React-Leaflet |

## Project Structure

```
NAVISCAPE-major-project/
├── frontend/          # React + Vite application
├── backend/           # FastAPI REST API
├── ml/                # ML training scripts & datasets
├── docs/              # Documentation
├── README.md
└── .gitignore
```

## Installation & Setup

### Prerequisites
- Python 3.10+
- Node.js 18+
- npm or yarn

### 1. Clone the Repository
```bash
git clone https://github.com/your-username/NAVISCAPE-major-project.git
cd NAVISCAPE-major-project
```

### 2. Backend Setup
```bash
cd backend
python -m venv venv
venv\Scripts\activate      # Windows
# source venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
python run.py
```
Backend runs at `http://localhost:8000` | API docs at `http://localhost:8000/docs`

### 3. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```
Frontend runs at `http://localhost:5173`

### 4. ML Model Training (Optional)
```bash
cd ml
pip install -r requirements.txt
python generate_datasets.py    # Generate synthetic data
python train_traffic_model.py  # Train LSTM model
python train_risk_model.py     # Train XGBoost model
```

## Default Credentials
- **Admin**: username `admin` / password `admin123`
- Register new accounts via the signup page

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/register` | Register new user |
| POST | `/api/auth/login` | Login, get JWT |
| GET | `/api/auth/me` | Current user profile |
| POST | `/api/navigate` | Generate route |
| GET | `/api/route-alternatives` | Get route options |
| GET | `/api/traffic/current` | Current traffic data |
| GET | `/api/traffic/heatmap` | Traffic heatmap |
| POST | `/api/predict/traffic` | Predict traffic |
| POST | `/api/predict/risk` | Predict risk score |
| GET | `/api/predict/congestion-forecast` | 24h forecast |
| POST | `/api/admin/upload-traffic` | Upload traffic CSV |
| GET | `/api/admin/stats` | System statistics |

## Architecture

```
[User] → [React Frontend] → [FastAPI Backend] → [SQLite DB]
                                    ↓
                            [ML Models (LSTM, XGBoost)]
                                    ↓
                         [Route Optimizer (A*/Dijkstra)]
```

## Deployment

### Using Docker (Recommended)
```bash
# Build and run
docker-compose up --build
```

### Manual Deployment
1. Build frontend: `cd frontend && npm run build`
2. Serve frontend with nginx or similar
3. Run backend with gunicorn: `gunicorn -w 1 -k uvicorn.workers.UvicornWorker app.main:app`

## License
This project is developed for academic purposes as a final-year BE AI & Data Science project.

---
Built with ❤️ using React, FastAPI, TensorFlow, and OpenStreetMap