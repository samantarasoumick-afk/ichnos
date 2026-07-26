"""
Passwordless "magic link" login: /api/auth/magic-link/request always
returns the same generic message (so it can't be used to enumerate
which emails have accounts), and /api/auth/magic-link/verify exchanges
a valid, unused, unexpired token for a normal access token - the same
token type /api/auth/login issues. This is also DataFe's de facto
password-reset path: there's no separate "reset my password" flow,
since anyone who can receive mail at the account's address can always
get back in this way.
"""

import re
import unittest
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.db.database import SessionLocal
from app.models.magic_login_token import MagicLoginToken
from app.models.user import User
from app.api.auth import (
    MAGIC_LINK_REQUEST_LIMIT,
    MAGIC_LINK_GENERIC_RESPONSE,
)


def _extract_token_from_email_body(body: str) -> str:
    match = re.search(r"token=([\w\-]+)", body)
    assert match, f"no token found in email body: {body}"
    return match.group(1)


class MagicLinkLoginTests(unittest.TestCase):

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

    def _request_link_and_get_token(self, email):
        with patch("app.api.auth.send_email") as mock_send:
            r = self.client.post("/api/auth/magic-link/request", json={"email": email})
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(r.json(), MAGIC_LINK_GENERIC_RESPONSE)
            body = mock_send.call_args.kwargs["body"]
            return _extract_token_from_email_body(body)

    def test_request_for_unknown_email_returns_generic_message_and_sends_nothing(self):
        with patch("app.api.auth.send_email") as mock_send:
            r = self.client.post("/api/auth/magic-link/request", json={
                "email": f"nobody{self._n}@nowhere.com",
            })
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(r.json(), MAGIC_LINK_GENERIC_RESPONSE)
            mock_send.assert_not_called()

    def test_request_and_verify_logs_in(self):
        email = f"magic{self._n}@a.com"
        self._register(email, f"Magic Org {self._n}")

        token = self._request_link_and_get_token(email)

        r = self.client.post("/api/auth/magic-link/verify", json={"token": token})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("access_token", r.json())

        # The issued token works like any other access token.
        headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
        me = self.client.get("/api/auth/me", headers=headers)
        self.assertEqual(me.status_code, 200, me.text)
        self.assertEqual(me.json()["email"], email)

    def test_token_can_only_be_used_once(self):
        email = f"magiconce{self._n}@a.com"
        self._register(email, f"Magic Once Org {self._n}")

        token = self._request_link_and_get_token(email)

        r1 = self.client.post("/api/auth/magic-link/verify", json={"token": token})
        self.assertEqual(r1.status_code, 200, r1.text)

        r2 = self.client.post("/api/auth/magic-link/verify", json={"token": token})
        self.assertEqual(r2.status_code, 400, r2.text)

    def test_expired_token_is_rejected(self):
        email = f"magicexpired{self._n}@a.com"
        self._register(email, f"Magic Expired Org {self._n}")

        token = self._request_link_and_get_token(email)

        db = SessionLocal()
        try:
            user = db.query(User).filter(User.email == email).first()
            row = (
                db.query(MagicLoginToken)
                .filter(MagicLoginToken.user_id == user.id)
                .first()
            )
            row.expires_at = datetime.utcnow() - timedelta(minutes=1)
            db.commit()
        finally:
            db.close()

        r = self.client.post("/api/auth/magic-link/verify", json={"token": token})
        self.assertEqual(r.status_code, 400, r.text)

    def test_bogus_token_is_rejected(self):
        r = self.client.post("/api/auth/magic-link/verify", json={"token": "not-a-real-token"})
        self.assertEqual(r.status_code, 400, r.text)

    def test_request_is_rate_limited(self):
        email = f"magiclimit{self._n}@a.com"
        self._register(email, f"Magic Limit Org {self._n}")

        for _ in range(MAGIC_LINK_REQUEST_LIMIT):
            with patch("app.api.auth.send_email") as mock_send:
                r = self.client.post("/api/auth/magic-link/request", json={"email": email})
                self.assertEqual(r.status_code, 200, r.text)
                mock_send.assert_called_once()

        # One more, past the limit within the window - generic
        # response still comes back (no enumeration signal), but no
        # email actually goes out.
        with patch("app.api.auth.send_email") as mock_send:
            r = self.client.post("/api/auth/magic-link/request", json={"email": email})
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(r.json(), MAGIC_LINK_GENERIC_RESPONSE)
            mock_send.assert_not_called()

    def test_deactivated_user_gets_generic_response_and_no_email(self):
        email = f"magicinactive{self._n}@a.com"
        self._register(email, f"Magic Inactive Org {self._n}")

        db = SessionLocal()
        try:
            user = db.query(User).filter(User.email == email).first()
            user.is_active = False
            db.commit()
        finally:
            db.close()

        with patch("app.api.auth.send_email") as mock_send:
            r = self.client.post("/api/auth/magic-link/request", json={"email": email})
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(r.json(), MAGIC_LINK_GENERIC_RESPONSE)
            mock_send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
