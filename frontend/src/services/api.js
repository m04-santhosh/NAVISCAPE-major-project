import axios from "axios";

const api = axios.create({
  baseURL:
    import.meta.env.VITE_API_URL ||
    "http://127.0.0.1:8000/api",
  headers: {
    "Content-Type": "application/json",
  },
  timeout: 15000,
});

export default api;


// Request interceptor — attach token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('naviscape-token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Response interceptor — handle 401
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('naviscape-token');
      // No redirect since login page is removed
    }
    return Promise.reject(error);
  }
);
