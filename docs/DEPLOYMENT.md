# NAVISCAPE - Deployment Guide

## Local Development

### Prerequisites
- Python 3.10 or higher
- Node.js 18 or higher
- npm 8+

### Backend
```bash
cd backend
python -m venv venv
venv\Scripts\activate           # Windows
pip install -r requirements.txt
python run.py
```
The API will be available at http://localhost:8000
Swagger docs at http://localhost:8000/docs

### Frontend
```bash
cd frontend
npm install
npm run dev
```
The app will be available at http://localhost:5173

### ML Training (Optional)
```bash
cd ml
pip install -r requirements.txt
python generate_datasets.py
python train_traffic_model.py
python train_risk_model.py
```

---

## Production Deployment

### Option 1: Docker (Recommended)

Create `docker-compose.yml` in project root:
```yaml
version: '3.8'
services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - SECRET_KEY=your-production-secret-key
      - DEBUG=False
    volumes:
      - ./data:/app/data
  
  frontend:
    build: ./frontend
    ports:
      - "3000:80"
    depends_on:
      - backend
```

### Option 2: Cloud Deployment

#### Backend (Render / Railway / AWS)
1. Push code to GitHub
2. Connect to Render/Railway
3. Set build command: `pip install -r requirements.txt`
4. Set start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
5. Set environment variables: SECRET_KEY, DATABASE_URL

#### Frontend (Vercel / Netlify)
1. Build: `npm run build`
2. Output directory: `dist`
3. Set VITE_API_URL environment variable to backend URL

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| SECRET_KEY | naviscape-super-secret... | JWT signing key |
| DATABASE_URL | sqlite:///./naviscape.db | Database connection string |
| DEBUG | True | Enable debug mode |
| ACCESS_TOKEN_EXPIRE_MINUTES | 1440 | JWT token expiry (24h) |
