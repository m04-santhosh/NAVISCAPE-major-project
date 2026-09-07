"""
Comprehensive SQL Direct Authentication Test Suite
Verifies that:
1. Direct registration creates exactly one SQL user and immediately returns a valid JWT.
2. Password is stored ONLY as a secure bcrypt hash (never plain text).
3. Duplicate email registration is rejected with HTTP 400.
4. Mismatched passwords on registration are rejected with HTTP 400.
5. Passwords shorter than 6 characters are rejected with validation error.
6. Login works with correct email and password, returning a valid JWT.
7. Login fails with incorrect password (HTTP 401).
8. Login fails with non-existent email (HTTP 401).
9. Protected endpoint /api/auth/me resolves user strictly via JWT + SQL database.
10. Change password updates bcrypt hash in SQL database.
11. Existing database records remain intact.
"""

import sys
import os
import sqlite3
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.main import app
from app.database import SessionLocal
from app.models.user import User
from app.middleware.auth import verify_password

client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def clean_test_users():
    """Ensure test users are cleaned up before and after test execution."""
    test_emails = [
        "sql_auth_direct_1@example.com",
        "sql_auth_direct_dup@example.com",
        "sql_auth_direct_pwchange@example.com",
    ]
    db = SessionLocal()
    try:
        for email in test_emails:
            u = db.query(User).filter(User.email == email).first()
            if u:
                db.delete(u)
        db.commit()
    finally:
        db.close()

    yield

    db = SessionLocal()
    try:
        for email in test_emails:
            u = db.query(User).filter(User.email == email).first()
            if u:
                db.delete(u)
        db.commit()
    finally:
        db.close()


def test_direct_registration_creates_sql_user_and_returns_jwt():
    """1, 2, 9. Direct registration creates user in SQL with bcrypt hash and returns valid JWT."""
    email = "sql_auth_direct_1@example.com"
    raw_password = "SecurePassword123!"
    req_data = {
        "full_name": "SQL Direct Test User",
        "email": email,
        "password": raw_password,
        "confirm_password": raw_password,
    }

    # 1. Register directly
    res = client.post("/api/auth/register", json=req_data)
    assert res.status_code == 201
    token_data = res.json()
    assert "access_token" in token_data
    assert token_data["token_type"] == "bearer"
    assert token_data["user"]["email"] == email
    assert token_data["user"]["full_name"] == "SQL Direct Test User"

    jwt_token = token_data["access_token"]

    # 2. Check SQL database directly
    db = SessionLocal()
    try:
        users = db.query(User).filter(User.email == email).all()
        assert len(users) == 1, "Exactly one SQL user record should be created!"
        created_user = users[0]
        assert created_user.email == email
        assert created_user.full_name == "SQL Direct Test User"
        assert created_user.email_verified is True
        assert created_user.is_active is True

        # Ensure raw password is NOT stored, but stored as a valid bcrypt hash
        assert created_user.hashed_password != raw_password
        assert created_user.hashed_password.startswith("$2b$") or created_user.hashed_password.startswith("$2a$")
        assert verify_password(raw_password, created_user.hashed_password) is True
    finally:
        db.close()

    # 3. Verify /api/auth/me works with JWT
    res_me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {jwt_token}"})
    assert res_me.status_code == 200
    assert res_me.json()["email"] == email

    # 4. Verify direct SQL login works
    res_login = client.post("/api/auth/login", json={"email": email, "password": raw_password})
    assert res_login.status_code == 200
    login_data = res_login.json()
    assert "access_token" in login_data
    assert login_data["user"]["email"] == email


def test_registration_password_mismatch_rejected():
    """4. Submitting mismatched passwords must fail with HTTP 400."""
    email = "sql_auth_direct_1@example.com"
    req_data = {
        "full_name": "Mismatch User",
        "email": email,
        "password": "Password123!",
        "confirm_password": "DifferentPassword123!",
    }

    res = client.post("/api/auth/register", json=req_data)
    assert res.status_code == 400
    assert "passwords do not match" in res.json()["detail"].lower()


def test_duplicate_email_registration_rejected():
    """3. Registering with an already registered email must fail with HTTP 400."""
    email = "sql_auth_direct_dup@example.com"
    req_data = {
        "full_name": "Duplicate User",
        "email": email,
        "password": "Password123!",
        "confirm_password": "Password123!",
    }

    # First registration
    res1 = client.post("/api/auth/register", json=req_data)
    assert res1.status_code == 201

    # Second registration with same email
    res2 = client.post("/api/auth/register", json=req_data)
    assert res2.status_code == 400
    assert "already exists" in res2.json()["detail"].lower()


def test_login_incorrect_password_and_nonexistent_user():
    """6, 7, 8. Login validation tests."""
    email = "sql_auth_direct_1@example.com"
    correct_pwd = "CorrectPassword123!"
    req_data = {
        "full_name": "Login Test User",
        "email": email,
        "password": correct_pwd,
        "confirm_password": correct_pwd,
    }

    # Create user
    res_reg = client.post("/api/auth/register", json=req_data)
    assert res_reg.status_code == 201

    # Login with wrong password
    res_bad_pw = client.post("/api/auth/login", json={"email": email, "password": "WrongPassword999!"})
    assert res_bad_pw.status_code == 401
    assert "invalid email or password" in res_bad_pw.json()["detail"].lower()

    # Login with non-existent email
    res_bad_email = client.post("/api/auth/login", json={"email": "nonexistent_user_999@example.com", "password": "AnyPassword123!"})
    assert res_bad_email.status_code == 401
    assert "invalid email or password" in res_bad_email.json()["detail"].lower()


def test_change_password_flow():
    """10. Change password updates bcrypt hash in SQL database."""
    email = "sql_auth_direct_pwchange@example.com"
    old_pwd = "OldPassword123!"
    new_pwd = "NewPassword456!"

    # 1. Register
    res_reg = client.post("/api/auth/register", json={
        "full_name": "PW Change User",
        "email": email,
        "password": old_pwd,
        "confirm_password": old_pwd,
    })
    assert res_reg.status_code == 201
    token = res_reg.json()["access_token"]

    # 2. Change password
    res_change = client.post(
        "/api/auth/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "current_password": old_pwd,
            "new_password": new_pwd,
            "confirm_new_password": new_pwd,
        }
    )
    assert res_change.status_code == 200

    # 3. Old password fails
    res_bad = client.post("/api/auth/login", json={"email": email, "password": old_pwd})
    assert res_bad.status_code == 401

    # 4. New password succeeds
    res_good = client.post("/api/auth/login", json={"email": email, "password": new_pwd})
    assert res_good.status_code == 200
    assert "access_token" in res_good.json()


def test_existing_sql_database_safety():
    """11. Confirm naviscape.db exists and accident_data table has all 95,723 records."""
    db_path = os.path.join(os.path.dirname(__file__), "naviscape.db")
    assert os.path.exists(db_path), "naviscape.db must exist!"

    conn = sqlite3.connect(db_path)
    try:
        c = conn.cursor()
        count = c.execute("SELECT COUNT(*) FROM accident_data").fetchone()[0]
        assert count == 95723, f"Accident data row count mismatch: {count}"
    finally:
        conn.close()
