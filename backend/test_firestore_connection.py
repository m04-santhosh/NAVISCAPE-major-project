"""
NAVISCAPE Firestore Read/Write Connectivity Test
Safely tests write, read, verification, and cleanup on Cloud Firestore.
"""

import sys
import os
import time

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.firebase import get_firebase_app, get_firestore_db


def run_test():
    print("=" * 60)
    print("NAVISCAPE — Cloud Firestore Connectivity Test")
    print("=" * 60)

    # 1. Initialize Firebase & Firestore
    print("\n[1/5] Initializing Firebase Admin SDK & Firestore client...")
    app = get_firebase_app()
    if not app:
        print("  [FAIL] Firebase Admin SDK initialization failed.")
        sys.exit(1)

    db = get_firestore_db()
    if not db:
        print("  [FAIL] Could not obtain Firestore client instance.")
        sys.exit(1)

    print(f"  [PASS] Connected to Firestore client (Project: {app.project_id})")

    collection_name = "_system_tests"
    doc_id = "firestore_connection_test"
    doc_ref = db.collection(collection_name).document(doc_id)

    payload = {
        "test": True,
        "message": "NAVISCAPE Firestore connection test",
        "timestamp": int(time.time()),
    }

    write_ok = False
    read_ok = False
    delete_ok = False

    try:
        # 2. WRITE test
        print(f"\n[2/5] Testing WRITE operation to '{collection_name}/{doc_id}'...")
        doc_ref.set(payload)
        write_ok = True
        print("  [PASS] WRITE: Successful")

        # 3. READ test
        print(f"\n[3/5] Testing READ operation from '{collection_name}/{doc_id}'...")
        snapshot = doc_ref.get()
        if snapshot.exists:
            data = snapshot.to_dict()
            print(f"  Retrieved data: {data}")
            if data.get("test") is True and data.get("message") == payload["message"] and data.get("timestamp") == payload["timestamp"]:
                read_ok = True
                print("  [PASS] READ: Successful (Data integrity verified)")
            else:
                print("  [FAIL] READ: Failed (Data mismatch)")
        else:
            print("  [FAIL] READ: Failed (Document does not exist after write)")

    except Exception as e:
        print(f"  [ERROR] during write/read: {e}")
    finally:
        # 4. DELETE / Clean-up test
        print(f"\n[4/5] Testing DELETE operation to clean up '{collection_name}/{doc_id}'...")
        try:
            doc_ref.delete()
            # Verify deletion
            verify_snap = doc_ref.get()
            if not verify_snap.exists:
                delete_ok = True
                print("  [PASS] DELETE: Successful (Document successfully removed, no residue)")
            else:
                print("  [FAIL] DELETE: Failed (Document still exists)")
        except Exception as e:
            print(f"  [ERROR] during cleanup/delete: {e}")

    # 5. Summary Report
    print("\n" + "=" * 60)
    print("SUMMARY RESULTS")
    print("=" * 60)
    print(f"  WRITE:  {'PASS' if write_ok else 'FAIL'}")
    print(f"  READ:   {'PASS' if read_ok else 'FAIL'}")
    print(f"  DELETE: {'PASS' if delete_ok else 'FAIL'}")
    print("=" * 60)

    if write_ok and read_ok and delete_ok:
        print("\nALL TESTS PASSED: Firestore is fully accessible for READ, WRITE, and DELETE operations.\n")
        sys.exit(0)
    else:
        print("\nCONNECTIVITY TEST FAILED.\n")
        sys.exit(1)


if __name__ == "__main__":
    run_test()
