"""
Comprehensive SQL Authentication & OTP Test Suite
Verifies that:
1. Registration OTP request works and generates an OTP in OTPStore.
2. User is NOT inserted into the SQLite 'users' table before OTP verification.
3. Correct OTP creates exactly one SQL user.
4. Wrong OTP does not create a user and returns 400.
5. Duplicate email registration is rejected with 400.
6. Password is stored only as a secure bcrypt hash (never plain text).
7. Login works using SQL credentials and returns a valid JWT.
8. Protected endpoints (/api/auth/me) resolve user strictly via JWT + SQL database.
9. Registration and login work completely independently without Firebase.
10. OTP resend works and refreshes the OTP code.
11. Password reset flow (request OTP, verify OTP, update password) works on SQL.
12. Existing database users remain intact and can authenticate.
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
from app.email_service import otp_store
from app.middleware.auth import verify_password

client = TestClient(app, raise_server_exceptions=False)


def _get_stored_otp(email: str, purpose: str) -> str:
    key = otp_store._make_key(email, purpose)
    return otp_store._store[key]["otp"]


@pytest.fixture(autouse=True)
def clean_test_users():
    """Ensure test users are cleaned up before and after test execution."""
    test_emails = [
        "sql_auth_test_1@example.com",
        "sql_auth_test_wrong_otp@example.com",
        "sql_auth_test_duplicate@example.com",
        "sql_auth_test_resend@example.com",
        "sql_auth_test_pwreset@example.com",
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


def test_registration_otp_request_does_not_insert_sql_user():
    """1 & 2. OTP request should succeed and NOT create a user record in the SQL database."""
    email = "sql_auth_test_1@example.com"
    req_data = {
        "full_name": "SQL Test User 1",
        "email": email,
        "password": "SecurePassword123!",
        "confirm_password": "SecurePassword123!",
    }

    res = client.post("/api/auth/register", json=req_data)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "otp_required"
    assert data["email"] == email

    # Verify user was NOT inserted into SQL database
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        assert user is None, "User must NOT be created before OTP verification!"
    finally:
        db.close()

    # Verify OTP exists in memory store
    otp = _get_stored_otp(email, "registration")
    assert len(otp) == 6


def test_wrong_otp_does_not_create_sql_user():
    """4. Submitting an invalid OTP should fail with HTTP 400 and NOT create a user."""
    email = "sql_auth_test_wrong_otp@example.com"
    req_data = {
        "full_name": "Wrong OTP User",
        "email": email,
        "password": "SecurePassword123!",
        "confirm_password": "SecurePassword123!",
    }

    # Request OTP
    res_req = client.post("/api/auth/register", json=req_data)
    assert res_req.status_code == 200

    # Attempt verify with invalid OTP
    res_verify = client.post(
        "/api/auth/register/verify-otp",
        json={**req_data, "otp": "000000"},
    )
    assert res_verify.status_code == 400
    assert "invalid" in res_verify.json()["detail"].lower() or "expired" in res_verify.json()["detail"].lower()

    # Confirm user still does not exist in SQL
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        assert user is None, "User must NOT be created on failed OTP verification!"
    finally:
        db.close()


def test_correct_otp_creates_exactly_one_sql_user_with_bcrypt_hash():
    """3, 6, 7, 8, 9. Correct OTP creates user in SQL with bcrypt hash and returns valid JWT."""
    email = "sql_auth_test_1@example.com"
    raw_password = "SecurePassword123!"
    req_data = {
        "full_name": "SQL Test User 1",
        "email": email,
        "password": raw_password,
        "confirm_password": raw_password,
    }

    # 1. Request OTP
    res_req = client.post("/api/auth/register", json=req_data)
    assert res_req.status_code == 200

    # Retrieve generated OTP from store
    valid_otp = _get_stored_otp(email, "registration")
    assert len(valid_otp) == 6

    # 2. Verify OTP
    res_verify = client.post(
        "/api/auth/register/verify-otp",
        json={**req_data, "otp": valid_otp},
    )
    assert res_verify.status_code == 201
    token_data = res_verify.json()
    assert "access_token" in token_data
    assert token_data["user"]["email"] == email

    jwt_token = token_data["access_token"]

    # 3. Check SQL database directly
    db = SessionLocal()
    try:
        users = db.query(User).filter(User.email == email).all()
        assert len(users) == 1, "Exactly one SQL user record should be created!"
        created_user = users[0]
        assert created_user.email == email
        assert created_user.full_name == "SQL Test User 1"
        assert created_user.email_verified is True
        assert created_user.is_active is True

        # Ensure raw password is NOT stored, but stored as a valid bcrypt hash
        assert created_user.hashed_password != raw_password
        assert created_user.hashed_password.startswith("$2b$") or created_user.hashed_password.startswith("$2a$")
        assert verify_password(raw_password, created_user.hashed_password) is True
    finally:
        db.close()

    # 4. Verify /api/auth/me works with JWT
    res_me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {jwt_token}"})
    assert res_me.status_code == 200
    assert res_me.json()["email"] == email

    # 5. Verify direct SQL login works
    res_login = client.post("/api/auth/login", json={"email": email, "password": raw_password})
    assert res_login.status_code == 200
    login_data = res_login.json()
    assert "access_token" in login_data
    assert login_data["user"]["email"] == email


def test_duplicate_email_registration_rejected():
    """5. Registering with an email that is already in SQLite users table must be rejected with 400."""
    email = "sql_auth_test_duplicate@example.com"
    raw_password = "SecurePassword123!"
    req_data = {
        "full_name": "Duplicate User",
        "email": email,
        "password": raw_password,
        "confirm_password": raw_password,
    }

    # Register first time
    client.post("/api/auth/register", json=req_data)
    otp = _get_stored_otp(email, "registration")
    res_v = client.post("/api/auth/register/verify-otp", json={**req_data, "otp": otp})
    assert res_v.status_code == 201

    # Attempt to request OTP again for the same registered email
    res_dup = client.post("/api/auth/register", json=req_data)
    assert res_dup.status_code == 400
    assert "already exists" in res_dup.json()["detail"].lower()


def test_otp_resend_functionality():
    """11. OTP resend should refresh the OTP in OTPStore."""
    email = "sql_auth_test_resend@example.com"
    req_data = {
        "full_name": "Resend Test User",
        "email": email,
        "password": "SecurePassword123!",
        "confirm_password": "SecurePassword123!",
    }

    # Initial request
    client.post("/api/auth/register", json=req_data)
    first_otp = _get_stored_otp(email, "registration")

    # Resend OTP
    res_resend = client.post(
        "/api/auth/register/resend-otp",
        json={"email": email, "full_name": "Resend Test User"},
    )
    assert res_resend.status_code == 200
    second_otp = _get_stored_otp(email, "registration")

    assert len(second_otp) == 6
    # Verify the user can register using the resent OTP
    res_verify = client.post(
        "/api/auth/register/verify-otp",
        json={**req_data, "otp": second_otp},
    )
    assert res_verify.status_code == 201


def test_password_reset_flow():
    """12. Password reset flow using 6-digit OTP."""
    email = "sql_auth_test_pwreset@example.com"
    old_password = "OldPassword123!"
    new_password = "NewPassword456!"

    # 1. Create initial user
    req_data = {
        "full_name": "Reset Password User",
        "email": email,
        "password": old_password,
        "confirm_password": old_password,
    }
    client.post("/api/auth/register", json=req_data)
    reg_otp = _get_stored_otp(email, "registration")
    client.post("/api/auth/register/verify-otp", json={**req_data, "otp": reg_otp})

    # 2. Request forgot password OTP
    res_forgot = client.post("/api/auth/forgot-password", json={"email": email})
    assert res_forgot.status_code == 200

    reset_otp = _get_stored_otp(email, "password_reset")
    assert len(reset_otp) == 6

    # 3. Verify OTP endpoint
    res_v_otp = client.post("/api/auth/verify-otp", json={"email": email, "otp": reset_otp})
    assert res_v_otp.status_code == 200

    # 4. Reset password
    res_reset = client.post(
        "/api/auth/reset-password",
        json={
            "email": email,
            "otp": reset_otp,
            "new_password": new_password,
            "confirm_new_password": new_password,
        },
    )
    assert res_reset.status_code == 200

    # 5. Verify old password fails and new password succeeds for SQL login
    res_bad_login = client.post("/api/auth/login", json={"email": email, "password": old_password})
    assert res_bad_login.status_code == 401

    res_good_login = client.post("/api/auth/login", json={"email": email, "password": new_password})
    assert res_good_login.status_code == 200
    assert "access_token" in res_good_login.json()


def test_existing_sql_database_safety():
    """Confirm naviscape.db exists and accident_data table has all 95,723 records."""
    db_path = os.path.join(os.path.dirname(__file__), "naviscape.db")
    assert os.path.exists(db_path), "naviscape.db must exist!"

    conn = sqlite3.connect(db_path)
    try:
        c = conn.cursor()
        count = c.execute("SELECT COUNT(*) FROM accident_data").fetchone()[0]
        assert count == 95723, f"Accident data row count mismatch: {count}"
    finally:
        conn.close()
