# NAVISCAPE - System Architecture

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    CLIENT (Browser)                          │
│  ┌─────────────┐  ┌──────────┐  ┌───────────┐  ┌────────┐ │
│  │  React.js   │  │ Leaflet  │  │ Recharts  │  │ Axios  │ │
│  │  + Tailwind │  │  Maps    │  │  Charts   │  │  HTTP  │ │
│  └──────┬──────┘  └────┬─────┘  └─────┬─────┘  └───┬────┘ │
└─────────┼──────────────┼──────────────┼─────────────┼──────┘
          │              │              │             │
          └──────────────┴──────────────┴─────────────┘
                              │ REST API (JSON)
                              │ JWT Auth Header
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                  SERVER (FastAPI)                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              CORS + JWT Middleware                     │   │
│  └──────────────────────┬───────────────────────────────┘   │
│                         │                                    │
│  ┌──────────┐  ┌────────┴───────┐  ┌───────────────────┐   │
│  │  Auth    │  │  Navigation    │  │   Traffic         │   │
│  │  Router  │  │  Router        │  │   Router          │   │
│  └──────────┘  └────────────────┘  └───────────────────┘   │
│  ┌──────────┐  ┌────────────────┐                           │
│  │  Predict │  │  Admin         │                           │
│  │  Router  │  │  Router        │                           │
│  └────┬─────┘  └────────────────┘                           │
│       │                                                      │
│  ┌────┴──────────────────────────────────────────────────┐  │
│  │              ML INFERENCE LAYER                        │  │
│  │  ┌────────────┐  ┌────────────┐  ┌─────────────────┐ │  │
│  │  │ LSTM       │  │ XGBoost    │  │ A* / Dijkstra   │ │  │
│  │  │ Predictor  │  │ Risk       │  │ Route Optimizer │ │  │
│  │  └────────────┘  └────────────┘  └─────────────────┘ │  │
│  └───────────────────────────────────────────────────────┘  │
│                         │                                    │
│  ┌──────────────────────┴───────────────────────────────┐   │
│  │           SQLAlchemy ORM (Session Manager)            │   │
│  └──────────────────────┬───────────────────────────────┘   │
└─────────────────────────┼───────────────────────────────────┘
                          │
                          ▼
              ┌───────────────────┐
              │   SQLite (WAL)    │
              │  ┌─────────────┐  │
              │  │ users       │  │
              │  │ traffic     │  │
              │  │ accidents   │  │
              │  │ routes      │  │
              │  └─────────────┘  │
              └───────────────────┘
```

## Data Flow

### Navigation Flow
1. User enters source/destination on the map
2. Frontend sends POST /api/navigate with coordinates
3. Backend calculates haversine distance
4. Route optimizer generates waypoints with deviation
5. Risk analyzer scores each route segment
6. Multiple route alternatives returned to frontend
7. Frontend displays routes on Leaflet map with color coding

### Prediction Flow
1. Frontend requests prediction for a junction
2. Backend loads LSTM model (or simulates)
3. Model processes 24-hour sliding window input
4. Predicted vehicle counts returned for next N hours
5. Frontend renders prediction chart with Recharts

### Authentication Flow
1. User submits login credentials
2. Backend verifies password hash with bcrypt
3. JWT token generated with username + expiry
4. Token stored in localStorage
5. Axios interceptor attaches token to all requests
6. Backend middleware validates token on protected routes
