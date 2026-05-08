# NAVISCAPE - API Documentation

## Base URL
```
http://localhost:8000/api
```

## Authentication
All protected endpoints require a JWT token in the Authorization header:
```
Authorization: Bearer <token>
```

---

## Auth Endpoints

### POST /auth/register
Register a new user account.

**Request:**
```json
{
  "username": "johndoe",
  "email": "john@example.com",
  "password": "securepass",
  "full_name": "John Doe"
}
```

**Response (201):**
```json
{
  "access_token": "eyJhbGciOi...",
  "token_type": "bearer",
  "user": {
    "id": 1,
    "username": "johndoe",
    "email": "john@example.com",
    "full_name": "John Doe",
    "is_admin": false,
    "is_active": true
  }
}
```

### POST /auth/login
Login with credentials.

**Request:**
```json
{
  "username": "johndoe",
  "password": "securepass"
}
```

### GET /auth/me
Get current user profile. **Auth required.**

---

## Navigation Endpoints

### POST /navigate
Generate a route. **Auth required.**

**Request:**
```json
{
  "source_lat": 12.9170,
  "source_lng": 77.6230,
  "dest_lat": 12.9698,
  "dest_lng": 77.7500,
  "source_name": "Silk Board",
  "dest_name": "Whitefield",
  "route_type": "balanced"
}
```

**Response:**
```json
{
  "route_type": "balanced",
  "distance_km": 15.2,
  "duration_min": 42.5,
  "safety_score": 78.3,
  "waypoints": [[12.917, 77.623], ...],
  "risk_zones": [{"lat": 12.94, "lng": 77.65, "radius": 300, "risk_level": "high"}]
}
```

### GET /route-alternatives?source_lat=...&source_lng=...&dest_lat=...&dest_lng=...
Get shortest, safest, and balanced routes. **Auth required.**

### GET /route-history
Get user's past routes. **Auth required.**

---

## Traffic Endpoints

### GET /traffic/current
Current traffic at all junctions. **Auth required.**

### GET /traffic/historical?junction_id=1&days=7
Historical traffic data. **Auth required.**

### GET /traffic/heatmap
Traffic density heatmap points. **Auth required.**

### GET /traffic/junctions
List all monitored junctions. **Auth required.**

---

## Prediction Endpoints

### POST /predict/traffic
LSTM-based traffic prediction. **Auth required.**

**Request:**
```json
{
  "junction_id": 1,
  "hours_ahead": 24
}
```

### POST /predict/risk
Risk score for a location. **Auth required.**

**Request:**
```json
{
  "latitude": 12.9170,
  "longitude": 77.6230,
  "hour": 18,
  "weather": "rain"
}
```

### GET /predict/congestion-forecast
24h forecast for all junctions. **Auth required.**

### GET /predict/accident-heatmap
Accident hotspot data. **Auth required.**

---

## Admin Endpoints (Admin role required)

### GET /admin/stats
System statistics.

### GET /admin/users
List all users.

### DELETE /admin/users/{id}
Delete a user.

### POST /admin/upload-traffic
Upload traffic CSV. Multipart form-data with `file` field.

### POST /admin/upload-accidents
Upload accident CSV. Multipart form-data with `file` field.

### GET /admin/predictions-monitor
ML model performance metrics.
