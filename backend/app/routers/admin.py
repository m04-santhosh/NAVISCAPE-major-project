"""
Admin Router — DISABLED
This router is NOT registered in main.py and is not accessible to users.

The upload logic (traffic/accident CSV) and monitoring endpoints are preserved
here for potential future internal use, but no public route is exposed.

To re-enable for internal use, add proper authentication and re-register the
router in main.py with a restricted prefix.
"""
# Admin functionality has been removed from the normal NAVISCAPE application flow.
# There is no admin panel, no admin login, and no admin-only user-facing endpoints.
# This file is kept to preserve the CSV upload and stats logic in case it is needed
# for a future internal tooling use — it is NOT importable from main.py currently.
