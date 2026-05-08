# NAVISCAPE - Viva Questions & Answers

## General Questions

### 1. What is NAVISCAPE?
NAVISCAPE is an Intelligent Navigation System that combines predictive traffic analysis with risk-aware routing using AI/ML. It uses LSTM for traffic prediction, XGBoost for risk analysis, and A*/Dijkstra for route optimization.

### 2. What problem does NAVISCAPE solve?
Urban traffic congestion leads to significant time wastage and increased accident risk. NAVISCAPE addresses this by predicting congestion 24 hours in advance and suggesting routes that balance travel time with safety.

### 3. What is the tech stack?
- **Frontend**: React.js, TailwindCSS, Leaflet.js, Recharts
- **Backend**: Python FastAPI, SQLAlchemy, JWT
- **Database**: SQLite
- **ML**: TensorFlow/Keras (LSTM), XGBoost, scikit-learn
- **Maps**: OpenStreetMap

### 4. Why did you choose FastAPI over Flask?
FastAPI offers automatic API documentation (Swagger), native async support, type validation with Pydantic, and is significantly faster than Flask. It's better suited for ML-serving applications.

### 5. Why SQLite instead of MySQL?
SQLite is sufficient for a project demo — it requires no separate server, uses WAL mode for concurrency, and simplifies deployment. The SQLAlchemy ORM makes it trivial to switch to PostgreSQL/MySQL for production.

---

## Machine Learning

### 6. Explain the LSTM model architecture.
Our LSTM uses: LSTM(64, return_sequences=True) → Dropout(0.2) → LSTM(32) → Dropout(0.2) → Dense(16, ReLU) → Dense(1). It takes 24-hour sliding windows of vehicle counts and predicts the next hour.

### 7. Why LSTM for traffic prediction?
LSTMs are designed for sequential/time-series data. They have gates (forget, input, output) that selectively retain information across long sequences, making them ideal for capturing daily/weekly traffic patterns.

### 8. What is the difference between LSTM and GRU?
GRU has 2 gates (reset, update) vs LSTM's 3 gates (forget, input, output). GRU is computationally simpler and faster to train, while LSTM can model more complex long-term dependencies. Both work well for traffic prediction.

### 9. Explain XGBoost for risk prediction.
XGBoost is a gradient boosted decision tree algorithm. We train it on accident data with features: location (lat/lng), time (hour, day), weather condition, and road condition. It classifies accident severity on a 1-5 scale.

### 10. What is the A* algorithm?
A* is a best-first search algorithm that finds the optimal path between nodes. It uses f(n) = g(n) + h(n), where g(n) is the cost from start and h(n) is a heuristic estimate to the goal. It's more efficient than Dijkstra because the heuristic guides the search.

### 11. How does Dijkstra differ from A*?
Dijkstra explores all directions uniformly (no heuristic), guaranteeing the shortest path. A* uses a heuristic to prioritize promising directions, making it faster but requiring an admissible heuristic function.

### 12. How do you handle multi-objective optimization?
We use a weighted cost function: cost = α × distance + β × risk_score. For "shortest" route α=1.0, β=0; for "safest" α=0.3, β=0.7; for "balanced" α=0.6, β=0.4.

### 13. What preprocessing did you apply to the traffic data?
- MinMaxScaler normalization (0 to 1 range)
- Sliding window transformation (24-hour sequences)
- Temporal splitting (80% train, 20% test — no shuffling to preserve time order)

### 14. What evaluation metrics did you use?
- Traffic LSTM: MSE (Mean Squared Error), MAE (Mean Absolute Error)
- Risk XGBoost: Accuracy, Precision, Recall, F1-Score, Classification Report

### 15. What is the sliding window technique?
We convert time series into supervised learning by using N consecutive time steps as input features and the next time step as the target. With window=24, the model uses 24 hours of data to predict hour 25.

---

## Frontend & Backend

### 16. Explain JWT authentication flow.
1. User sends credentials to /api/auth/login
2. Server validates, generates JWT with username as subject and expiry
3. JWT is returned and stored in localStorage
4. Frontend attaches JWT in Authorization header for all subsequent requests
5. Server decodes and validates JWT on each protected endpoint

### 17. What is CORS and why is it needed?
Cross-Origin Resource Sharing allows the frontend (localhost:5173) to make requests to the backend (localhost:8000). Without CORS middleware, the browser blocks cross-origin requests for security.

### 18. Explain the React component architecture.
We use React functional components with hooks. Context API manages global state (auth, theme). React Router handles navigation. Components are organized by feature: layout, pages, charts, map.

### 19. How does the heatmap visualization work?
We use Leaflet CircleMarker components positioned at accident/traffic coordinates. The circle radius and color intensity represent severity/density. Multiple overlapping circles create a heatmap effect.

### 20. What is Recharts?
Recharts is a React charting library built on D3.js. We use it for AreaChart (traffic predictions), BarChart (junction comparison), and LineChart (historical trends) with responsive containers.

---

## Database & API

### 21. Explain the database schema.
Four tables: `users` (auth + profiles), `traffic_data` (junction measurements), `accident_data` (incident records with severity/conditions), `route_history` (user navigation log with safety scores).

### 22. What is SQLAlchemy ORM?
Object-Relational Mapping lets us define database tables as Python classes and perform queries using Python methods instead of raw SQL. It provides database abstraction and migration support.

### 23. What is WAL mode in SQLite?
Write-Ahead Logging mode allows concurrent reads while writing, improving performance for web applications. Without WAL, SQLite locks the entire database during writes.

### 24. How are API routes organized?
Using FastAPI's APIRouter, routes are grouped by domain: auth (authentication), navigation (routing), traffic (data), prediction (ML), admin (management). Each router has its own prefix and tags.

### 25. What is dependency injection in FastAPI?
FastAPI uses the Depends() function to inject dependencies like database sessions and authenticated users into route handlers. This promotes code reuse and separation of concerns.

---

## Architecture & Deployment

### 26. Describe the system architecture.
Three-tier: React frontend → FastAPI REST API → SQLite database, with ML models loaded in memory for inference. The frontend communicates via JSON over HTTP with JWT authentication.

### 27. How would you scale this for production?
- Replace SQLite with PostgreSQL
- Deploy backend with multiple Gunicorn workers
- Use Redis for caching predictions
- Host OSRM for self-managed routing
- Add Celery for async ML training
- Deploy on AWS/GCP with load balancer

### 28. What security measures are implemented?
- bcrypt password hashing (never stored in plain text)
- JWT tokens with expiration
- CORS whitelist
- Admin role-based access control
- Input validation with Pydantic
- SQL injection prevention via ORM

### 29. How is error handling implemented?
- Backend: HTTPException with status codes, try-catch in services
- Frontend: Axios interceptors for 401 redirect, toast notifications for errors
- Validation: Pydantic models reject malformed requests automatically

### 30. What is the difference between classification and regression in this project?
- Regression: LSTM predicts continuous vehicle count values
- Classification: XGBoost classifies accident severity into discrete categories (1-5)
- Both: Risk scoring combines regression (continuous 0-100 score) with classification (low/medium/high/critical levels)

---

## Advanced Questions

### 31. What is backpropagation through time (BPTT)?
BPTT is how LSTMs learn. Gradients flow backward through the unrolled time steps. The forget gate prevents vanishing gradients by controlling information flow, allowing learning over long sequences.

### 32. What is the vanishing gradient problem?
In traditional RNNs, gradients shrink exponentially during backpropagation through many time steps, preventing learning of long-term patterns. LSTMs solve this with their cell state and gating mechanism.

### 33. What is overfitting and how did you prevent it?
Overfitting occurs when a model memorizes training data but fails on new data. We prevent it with: Dropout layers (0.2), early stopping potential, proper train/test splitting, and regularization in XGBoost.

### 34. Explain the haversine formula.
It calculates great-circle distance between two GPS coordinates on a sphere. Formula: a = sin²(Δlat/2) + cos(lat1)·cos(lat2)·sin²(Δlon/2), d = 2R·arcsin(√a). We use R=6371 km (Earth's radius).

### 35. What are React hooks?
Functions that let you use state and lifecycle features in functional components. We use: useState (local state), useEffect (side effects/API calls), useContext (global state), useRef (DOM references).

### 36-50. Additional topics to study:
- Feature importance in Random Forest
- Cross-validation techniques
- REST vs GraphQL
- WebSocket for real-time updates
- Docker containerization
- CI/CD pipelines
- Transfer learning possibilities
- Ensemble methods
- Geospatial indexing
- Time complexity of A* vs Dijkstra
- React Virtual DOM
- OAuth2 flow
- Database normalization
- Batch vs real-time prediction
- Model versioning and MLOps
