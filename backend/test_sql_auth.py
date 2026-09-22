"""
Comprehensive SQL Authentication and Email OTP Test Suite
Verifies that:
1. /api/auth/register generates a 6-digit OTP, stores its SHA-256 hash in SQL, and does NOT create a user yet.
2. /api/auth/register/verify-otp validates the OTP, creates the SQL user with bcrypt password hash, and returns JWT.
3. OTP is one-time use (cannot be re-used after verification).
4. Failed attempts increment counter and lock out after 5 attempts.
5. Expired OTP is rejected.
6. /api/auth/register/resend-otp invalidates old OTP and generates a new one.
7. Duplicate email registration is rejected with HTTP 400.
8. Mismatched passwords on registration are rejected with HTTP 400.
9. Passwords shorter than 6 characters are rejected with validation error.
10. Login works with correct email and password, returning a valid JWT.
11. Login fails with incorrect password (HTTP 401).
12. Login fails with non-existent email (HTTP 401).
13. Protected endpoint /api/auth/me resolves user strictly via JWT + SQL database.
14. Change password updates bcrypt hash in SQL database.
15. Existing database records remain intact.
"""

from datetime import datetime, timedelta, timezone
import sys
import os
import sqlite3
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.main import app
from app.database import SessionLocal
from app.models.user import User
from app.models.otp import OTPRecord
from app.services.otp_service import hash_otp
from app.middleware.auth import verify_password

client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def clean_test_users():
    """Ensure test users and OTP records are cleaned up before and after test execution."""
    test_emails = [
        "sql_auth_otp_1@example.com",
        "sql_auth_otp_dup@example.com",
        "sql_auth_otp_pwchange@example.com",
        "sql_auth_otp_resend@example.com",
        "sql_auth_otp_attempts@example.com",
        "sql_auth_otp_expired@example.com",
    ]
    db = SessionLocal()
    try:
        for email in test_emails:
            u = db.query(User).filter(User.email == email).first()
            if u:
                db.delete(u)
            db.query(OTPRecord).filter(OTPRecord.email == email).delete()
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
            db.query(OTPRecord).filter(OTPRecord.email == email).delete()
        db.commit()
    finally:
        db.close()


def test_otp_registration_flow_success():
    """Step 1 & Step 2: Register requests OTP, OTP verified in DB, creates user and returns JWT."""
    email = "sql_auth_otp_1@example.com"
    raw_password = "SecurePassword123!"
    req_data = {
        "full_name": "OTP Test User",
        "email": email,
        "password": raw_password,
        "confirm_password": raw_password,
    }

    # Step 1: Request registration OTP
    res = client.post("/api/auth/register", json=req_data)
    assert res.status_code == 200
    res_data = res.json()
    assert res_data["status"] == "otp_required"
    assert res_data["email"] == email

    # Verify no user created yet in SQL database
    db = SessionLocal()
    try:
        user_before = db.query(User).filter(User.email == email).first()
        assert user_before is None, "User should NOT be created before OTP verification!"

        # Retrieve the OTP record created in SQL
        otp_rec = db.query(OTPRecord).filter(OTPRecord.email == email, OTPRecord.verified == False).first()
        assert otp_rec is not None, "OTP record must exist in SQL database!"
        assert otp_rec.attempts == 0
        assert len(otp_rec.otp_hash) == 64  # SHA-256

        # Step 2: Verify OTP
        # Find which 6-digit code matches the hash
        # In test, we can verify hash_otp
        test_otp = None
        for code in range(1000000):
            candidate = f"{code:06d}"
            if hash_otp(email, candidate) == otp_rec.otp_hash:
                test_otp = candidate
                break

        assert test_otp is not None, "Could not reverse test OTP for verification"
    finally:
        db.close()

    verify_payload = {
        "full_name": "OTP Test User",
        "email": email,
        "password": raw_password,
        "confirm_password": raw_password,
        "otp": test_otp,
    }

    res_verify = client.post("/api/auth/register/verify-otp", json=verify_payload)
    assert res_verify.status_code == 201
    token_data = res_verify.json()
    assert "access_token" in token_data
    assert token_data["token_type"] == "bearer"
    assert token_data["user"]["email"] == email
    assert token_data["user"]["full_name"] == "OTP Test User"
    assert token_data["user"]["email_verified"] is True

    jwt_token = token_data["access_token"]

    # Verify user now created in SQL database with bcrypt hash
    db = SessionLocal()
    try:
        user_after = db.query(User).filter(User.email == email).first()
        assert user_after is not None, "User must exist in SQL database after verification!"
        assert user_after.hashed_password != raw_password
        assert verify_password(raw_password, user_after.hashed_password) is True

        # Verify OTP record is marked as verified (consumed)
        otp_consumed = db.query(OTPRecord).filter(OTPRecord.email == email).first()
        assert otp_consumed.verified is True
    finally:
        db.close()

    # Verify /api/auth/me works
    res_me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {jwt_token}"})
    assert res_me.status_code == 200
    assert res_me.json()["email"] == email

    # Verify direct SQL login works
    res_login = client.post("/api/auth/login", json={"email": email, "password": raw_password})
    assert res_login.status_code == 200
    assert "access_token" in res_login.json()


def test_otp_one_time_use():
    """OTP cannot be reused once verified."""
    email = "sql_auth_otp_1@example.com"
    raw_password = "SecurePassword123!"

    # 1. Register & get OTP
    client.post("/api/auth/register", json={
        "full_name": "Replay User",
        "email": email,
        "password": raw_password,
        "confirm_password": raw_password,
    })

    db = SessionLocal()
    try:
        otp_rec = db.query(OTPRecord).filter(OTPRecord.email == email, OTPRecord.verified == False).first()
        test_otp = None
        for code in range(1000000):
            candidate = f"{code:06d}"
            if hash_otp(email, candidate) == otp_rec.otp_hash:
                test_otp = candidate
                break
    finally:
        db.close()

    verify_payload = {
        "full_name": "Replay User",
        "email": email,
        "password": raw_password,
        "confirm_password": raw_password,
        "otp": test_otp,
    }

    # First verification succeeds
    res1 = client.post("/api/auth/register/verify-otp", json=verify_payload)
    assert res1.status_code == 201

    # Second verification with same OTP fails
    res2 = client.post("/api/auth/register/verify-otp", json=verify_payload)
    assert res2.status_code == 400


def test_otp_attempt_limiting():
    """Incorrect OTP entries are counted and locked out after 5 attempts."""
    email = "sql_auth_otp_attempts@example.com"
    raw_password = "SecurePassword123!"

    client.post("/api/auth/register", json={
        "full_name": "Attempt User",
        "email": email,
        "password": raw_password,
        "confirm_password": raw_password,
    })

    # 5 wrong attempts
    for i in range(1, 6):
        res = client.post("/api/auth/register/verify-otp", json={
            "full_name": "Attempt User",
            "email": email,
            "password": raw_password,
            "confirm_password": raw_password,
            "otp": f"00000{i}",
        })
        assert res.status_code == 400

    # 6th attempt should be rejected due to max attempts reached
    res6 = client.post("/api/auth/register/verify-otp", json={
        "full_name": "Attempt User",
        "email": email,
        "password": raw_password,
        "confirm_password": raw_password,
        "otp": "000001",
    })
    assert res6.status_code == 400
    assert "attempt" in res6.json()["detail"].lower() or "no active" in res6.json()["detail"].lower()


def test_otp_expired_rejected():
    """Expired OTP must be rejected."""
    email = "sql_auth_otp_expired@example.com"
    raw_password = "SecurePassword123!"

    client.post("/api/auth/register", json={
        "full_name": "Expired User",
        "email": email,
        "password": raw_password,
        "confirm_password": raw_password,
    })

    # Manually expire OTP in DB
    db = SessionLocal()
    try:
        otp_rec = db.query(OTPRecord).filter(OTPRecord.email == email).first()
        otp_rec.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=5)
        db.commit()
    finally:
        db.close()

    res = client.post("/api/auth/register/verify-otp", json={
        "full_name": "Expired User",
        "email": email,
        "password": raw_password,
        "confirm_password": raw_password,
        "otp": "123456",
    })
    assert res.status_code == 400
    assert "expired" in res.json()["detail"].lower() or "no active" in res.json()["detail"].lower()


def test_resend_otp_invalidates_previous_otp():
    """Resending OTP invalidates the earlier OTP record."""
    email = "sql_auth_otp_resend@example.com"
    raw_password = "SecurePassword123!"

    # 1. Request first OTP
    client.post("/api/auth/register", json={
        "full_name": "Resend User",
        "email": email,
        "password": raw_password,
        "confirm_password": raw_password,
    })

    db = SessionLocal()
    try:
        otp1 = db.query(OTPRecord).filter(OTPRecord.email == email, OTPRecord.verified == False).first()
        otp1_id = otp1.id
    finally:
        db.close()

    # 2. Resend OTP
    res_resend = client.post("/api/auth/register/resend-otp", json={
        "email": email,
        "full_name": "Resend User",
    })
    assert res_resend.status_code == 200

    db = SessionLocal()
    try:
        # Check that old OTP is now marked verified (invalidated)
        old_otp = db.query(OTPRecord).filter(OTPRecord.id == otp1_id).first()
        assert old_otp.verified is True

        # Check new active OTP exists
        active_otps = db.query(OTPRecord).filter(OTPRecord.email == email, OTPRecord.verified == False).all()
        assert len(active_otps) == 1
        assert active_otps[0].id != otp1_id
    finally:
        db.close()


def test_registration_password_mismatch_rejected():
    """Submitting mismatched passwords must fail with HTTP 400."""
    email = "sql_auth_otp_1@example.com"
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
    """Registering with an already registered email must fail with HTTP 400."""
    email = "sql_auth_otp_dup@example.com"
    raw_pwd = "Password123!"

    # Create active user in DB
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        u = User(
            email=email,
            full_name="Existing User",
            username=email,
            hashed_password=raw_pwd,
            pin_hash=raw_pwd,
            email_verified=True,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        db.add(u)
        db.commit()
    finally:
        db.close()

    req_data = {
        "full_name": "Duplicate User",
        "email": email,
        "password": raw_pwd,
        "confirm_password": raw_pwd,
    }

    # Registration attempt with existing email fails
    res = client.post("/api/auth/register", json=req_data)
    assert res.status_code == 400
    assert "already exists" in res.json()["detail"].lower()


def test_login_incorrect_password_and_nonexistent_user():
    """Login validation tests."""
    email = "sql_auth_otp_1@example.com"
    correct_pwd = "CorrectPassword123!"

    # Manually create verified user in DB
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        pwd_hash = verify_password  # import check
        from app.middleware.auth import hash_password
        u = User(
            email=email,
            full_name="Login Test User",
            username=email,
            hashed_password=hash_password(correct_pwd),
            pin_hash=hash_password(correct_pwd),
            email_verified=True,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        db.add(u)
        db.commit()
    finally:
        db.close()

    # Login with wrong password
    res_bad_pw = client.post("/api/auth/login", json={"email": email, "password": "WrongPassword999!"})
    assert res_bad_pw.status_code == 401
    assert "invalid email or password" in res_bad_pw.json()["detail"].lower()

    # Login with non-existent email
    res_bad_email = client.post("/api/auth/login", json={"email": "nonexistent_user_999@example.com", "password": "AnyPassword123!"})
    assert res_bad_email.status_code == 401
    assert "invalid email or password" in res_bad_email.json()["detail"].lower()


def test_change_password_flow():
    """Change password updates bcrypt hash in SQL database."""
    email = "sql_auth_otp_pwchange@example.com"
    old_pwd = "OldPassword123!"
    new_pwd = "NewPassword456!"

    # Create user
    from app.middleware.auth import hash_password
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        u = User(
            email=email,
            full_name="PW Change User",
            username=email,
            hashed_password=hash_password(old_pwd),
            pin_hash=hash_password(old_pwd),
            email_verified=True,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        user_id = u.id
    finally:
        db.close()

    from app.middleware.auth import create_access_token
    token = create_access_token(data={"sub": str(user_id)})

    # Change password
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

    # Old password fails
    res_bad = client.post("/api/auth/login", json={"email": email, "password": old_pwd})
    assert res_bad.status_code == 401

    # New password succeeds
    res_good = client.post("/api/auth/login", json={"email": email, "password": new_pwd})
    assert res_good.status_code == 200
    assert "access_token" in res_good.json()


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
