"""
General API rate limiting (app/middleware/rate_limit.py): previously
only /api/auth/login had any throttling at all. This is disabled by
default under pytest (see conftest.py - the whole suite runs from one
TestClient "IP" and would trip any per-minute limit almost
immediately), so these tests explicitly patch the module-level
RATE_LIMIT_ENABLED/RATE_LIMIT_PER_MINUTE constants on for their own
scope rather than relying on the env var, since those constants are
read once at import time.
"""

import unittest
import uuid

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app


class RateLimitingTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        self._n = uuid.uuid4().hex[:8]

    def test_requests_beyond_the_limit_get_429(self):
        with patch("app.middleware.rate_limit.RATE_LIMIT_ENABLED", True), \
             patch("app.middleware.rate_limit.RATE_LIMIT_PER_MINUTE", 3):

            statuses = [
                self.client.get("/api/business-processes").status_code
                for _ in range(3)
            ]
            # All under the limit are rejected only for lack of auth
            # (401), never for rate limiting - proves the limiter
            # isn't interfering below the threshold.
            self.assertTrue(all(s == 401 for s in statuses), statuses)

            over_limit = self.client.get("/api/business-processes")
            self.assertEqual(over_limit.status_code, 429, over_limit.text)
            self.assertIn("Too many requests", over_limit.json()["detail"])

    def test_health_endpoint_is_exempt_from_the_limit(self):
        with patch("app.middleware.rate_limit.RATE_LIMIT_ENABLED", True), \
             patch("app.middleware.rate_limit.RATE_LIMIT_PER_MINUTE", 2):

            for _ in range(10):
                r = self.client.get("/health")
                self.assertEqual(r.status_code, 200, r.text)

    def test_disabled_by_default_under_the_test_suite(self):
        # No patching here - relies on conftest.py's RATE_LIMIT_ENABLED=false.
        for _ in range(20):
            r = self.client.get("/health")
            self.assertEqual(r.status_code, 200, r.text)

    def test_forwarded_for_header_distinguishes_clients_behind_a_proxy(self):
        # Simulates two different real visitors both arriving through
        # the same reverse proxy (same TestClient "TCP peer"), the way
        # they would through website/nginx.conf in production -
        # X-Forwarded-For should keep their rate-limit buckets separate.
        with patch("app.middleware.rate_limit.RATE_LIMIT_ENABLED", True), \
             patch("app.middleware.rate_limit.RATE_LIMIT_PER_MINUTE", 2):

            for _ in range(2):
                r = self.client.get(
                    "/api/business-processes",
                    headers={"X-Forwarded-For": "203.0.113.10"},
                )
                self.assertEqual(r.status_code, 401, r.text)

            # A different forwarded client is unaffected by the first
            # one's budget being used up.
            r = self.client.get(
                "/api/business-processes",
                headers={"X-Forwarded-For": "203.0.113.99"},
            )
            self.assertEqual(r.status_code, 401, r.text)

            # But the first client, still over its own budget, is.
            r = self.client.get(
                "/api/business-processes",
                headers={"X-Forwarded-For": "203.0.113.10"},
            )
            self.assertEqual(r.status_code, 429, r.text)

    def test_response_carries_a_request_id_header(self):
        r = self.client.get("/health")
        self.assertIn("x-request-id", {k.lower() for k in r.headers.keys()})


if __name__ == "__main__":
    unittest.main()
