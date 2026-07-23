"""
Brute-force protection on /api/auth/login: after LOGIN_LOCKOUT_THRESHOLD
failed attempts within LOGIN_LOCKOUT_WINDOW_MINUTES, further attempts
are rejected with 429 without even checking the password - and it
resets itself once the oldest failure ages out of the window, since
it's a rolling window over audit_logs rather than a persistent lock
flag.
"""

import unittest
import uuid
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.db.database import SessionLocal
from app.models.audit_log import AuditLog
from app.models.user import User
from app.api.auth import LOGIN_LOCKOUT_THRESHOLD


class LoginLockoutTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        self._n = uuid.uuid4().hex[:8]

    def _register(self, email, org_name):
        r = self.client.post("/api/auth/register", json={
            "email": email,
            "password": "password123",
            "organization_name": org_name,
        })
        self.assertEqual(r.status_code, 200, r.text)

    def test_locks_out_after_threshold_failed_attempts(self):
        email = f"lockout{self._n}@a.com"
        self._register(email, f"Lockout Org {self._n}")

        for _ in range(LOGIN_LOCKOUT_THRESHOLD):
            r = self.client.post("/api/auth/login", json={
                "email": email,
                "password": "wrong-password",
            })
            self.assertEqual(r.status_code, 401)

        # Even the *correct* password is now rejected outright.
        r = self.client.post("/api/auth/login", json={
            "email": email,
            "password": "password123",
        })
        self.assertEqual(r.status_code, 429, r.text)

    def test_lockout_is_per_user_not_global(self):
        email_a = f"lockA{self._n}@a.com"
        email_b = f"lockB{self._n}@b.com"
        self._register(email_a, f"Lock Org A {self._n}")
        self._register(email_b, f"Lock Org B {self._n}")

        for _ in range(LOGIN_LOCKOUT_THRESHOLD):
            self.client.post("/api/auth/login", json={
                "email": email_a,
                "password": "wrong-password",
            })

        # User A is locked out...
        r = self.client.post("/api/auth/login", json={
            "email": email_a,
            "password": "password123",
        })
        self.assertEqual(r.status_code, 429)

        # ...but user B, who never failed a login, is unaffected.
        r = self.client.post("/api/auth/login", json={
            "email": email_b,
            "password": "password123",
        })
        self.assertEqual(r.status_code, 200, r.text)

    def test_failed_attempts_outside_the_window_do_not_count(self):
        email = f"stale{self._n}@a.com"
        self._register(email, f"Stale Org {self._n}")

        db = SessionLocal()
        try:
            user = db.query(User).filter(User.email == email).first()
            for _ in range(LOGIN_LOCKOUT_THRESHOLD):
                db.add(AuditLog(
                    organization_id=user.organization_id,
                    actor_user_id=user.id,
                    actor_email=user.email,
                    action="user.login_failed",
                    details="Incorrect password",
                    created_at=datetime.utcnow() - timedelta(hours=2),
                ))
            db.commit()
        finally:
            db.close()

        # All the failures are 2 hours old, well outside the 15-minute
        # window, so this login should succeed normally.
        r = self.client.post("/api/auth/login", json={
            "email": email,
            "password": "password123",
        })
        self.assertEqual(r.status_code, 200, r.text)

    def test_successful_login_is_still_allowed_below_threshold(self):
        email = f"belowthresh{self._n}@a.com"
        self._register(email, f"Below Thresh Org {self._n}")

        for _ in range(LOGIN_LOCKOUT_THRESHOLD - 1):
            self.client.post("/api/auth/login", json={
                "email": email,
                "password": "wrong-password",
            })

        r = self.client.post("/api/auth/login", json={
            "email": email,
            "password": "password123",
        })
        self.assertEqual(r.status_code, 200, r.text)


if __name__ == "__main__":
    unittest.main()
