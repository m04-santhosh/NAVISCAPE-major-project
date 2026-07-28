import requests

url = "http://localhost:8000/api/auth/register"
data = {
    "username": "testuser",
    "email": "test@example.com",
    "password": "testpassword",
    "full_name": "Test User"
}

try:
    response = requests.post(url, json=data)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")
except Exception as e:
    print(f"Error: {e}")
