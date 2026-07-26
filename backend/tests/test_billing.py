"""
Stripe billing: self-serve checkout/portal URL creation (mocked at
the Stripe HTTP boundary - app.services.billing_service._stripe_post,
same approach test_assistant.py uses for the Anthropic API), the
webhook's manual signature verification, and the plan/status update
each webhook event type is supposed to make. Nothing here calls the
real Stripe API.
"""

import hashlib
import hmac
import json
import os
import time
import unittest
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.db.database import SessionLocal
from app.models.organization import Organization
from app.services import billing_service


class BillingTestsBase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        self._n = uuid.uuid4().hex[:8]

    def _register_and_login(self, email, org_name):
        r = self.client.post("/api/auth/register", json={
            "email": email,
            "password": "password123",
            "organization_name": org_name,
        })
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.post("/api/auth/login", json={
            "email": email,
            "password": "password123",
        })
        self.assertEqual(r.status_code, 200, r.text)

        headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
        me = self.client.get("/api/auth/me", headers=headers).json()

        return headers, me["organization_id"]

    def _get_org(self, organization_id):
        db = SessionLocal()
        try:
            return db.query(Organization).filter(Organization.id == organization_id).first()
        finally:
            db.close()


class BillingStatusTests(BillingTestsBase):

    def test_new_org_defaults_to_open_trial_entitlements(self):
        headers, _ = self._register_and_login(f"admin{self._n}@a.com", f"Org {self._n}")

        r = self.client.get("/api/billing/status", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)

        body = r.json()
        self.assertEqual(body["plan"], "starter")
        self.assertEqual(body["plan_status"], "trialing")
        self.assertFalse(body["has_stripe_customer"])
        # Trial entitlements are open (see entitlements.py's "trial"
        # profile) even though the underlying plan is still "starter" -
        # a brand-new signup shouldn't be capped to 1 source.
        self.assertIsNone(body["entitlements"]["max_sources"])
        self.assertEqual(body["entitlements"]["ask_daily_limit"], 50)


class BillingCheckoutTests(BillingTestsBase):

    def test_non_admin_cannot_start_checkout(self):
        admin_headers, _ = self._register_and_login(f"admin2{self._n}@a.com", f"Org2 {self._n}")

        self.client.post("/api/users", headers=admin_headers, json={
            "email": f"viewer{self._n}@a.com",
            "password": "password123",
            "role": "viewer",
        })
        r = self.client.post("/api/auth/login", json={
            "email": f"viewer{self._n}@a.com",
            "password": "password123",
        })
        viewer_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

        r = self.client.post(
            "/api/billing/checkout",
            headers=viewer_headers,
            json={"plan": "team", "billing_cycle": "monthly"},
        )
        self.assertEqual(r.status_code, 403)

    def test_checkout_without_stripe_configured_returns_503(self):
        headers, _ = self._register_and_login(f"admin3{self._n}@a.com", f"Org3 {self._n}")

        # STRIPE_SECRET_KEY is unset in the test environment (conftest.py
        # never sets it) - self-serve checkout should fail clearly
        # rather than raise an unhandled error.
        r = self.client.post(
            "/api/billing/checkout",
            headers=headers,
            json={"plan": "team", "billing_cycle": "monthly"},
        )
        self.assertEqual(r.status_code, 503, r.text)
        self.assertIn("STRIPE_SECRET_KEY", r.json()["detail"])

    def test_checkout_success_creates_customer_and_returns_url(self):
        headers, organization_id = self._register_and_login(
            f"admin4{self._n}@a.com", f"Org4 {self._n}"
        )

        fake_responses = iter([
            {"id": "cus_fake123"},          # customers
            {"url": "https://checkout.stripe.com/pay/cs_fake123"},  # checkout/sessions
        ])

        with patch.dict(os.environ, {
            "STRIPE_SECRET_KEY": "sk_test_fake",
            "STRIPE_PRICE_TEAM_MONTHLY": "price_fake_team_monthly",
        }):
            with patch.object(billing_service, "_stripe_post", side_effect=lambda path, data: next(fake_responses)):
                r = self.client.post(
                    "/api/billing/checkout",
                    headers=headers,
                    json={"plan": "team", "billing_cycle": "monthly"},
                )

        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["checkout_url"], "https://checkout.stripe.com/pay/cs_fake123")

        org = self._get_org(organization_id)
        self.assertEqual(org.stripe_customer_id, "cus_fake123")

    def test_checkout_unknown_plan_cycle_returns_503(self):
        headers, _ = self._register_and_login(f"admin5{self._n}@a.com", f"Org5 {self._n}")

        with patch.dict(os.environ, {"STRIPE_SECRET_KEY": "sk_test_fake"}):
            r = self.client.post(
                "/api/billing/checkout",
                headers=headers,
                json={"plan": "enterprise", "billing_cycle": "monthly"},
            )

        self.assertEqual(r.status_code, 503, r.text)
        self.assertIn("Enterprise", r.json()["detail"])


class BillingPortalTests(BillingTestsBase):

    def test_portal_without_stripe_customer_returns_400(self):
        headers, _ = self._register_and_login(f"admin6{self._n}@a.com", f"Org6 {self._n}")

        with patch.dict(os.environ, {"STRIPE_SECRET_KEY": "sk_test_fake"}):
            r = self.client.post("/api/billing/portal", headers=headers)

        self.assertEqual(r.status_code, 400, r.text)
        self.assertIn("Stripe customer", r.json()["detail"])

    def test_portal_without_stripe_configured_returns_503(self):
        headers, _ = self._register_and_login(f"admin7{self._n}@a.com", f"Org7 {self._n}")

        r = self.client.post("/api/billing/portal", headers=headers)
        self.assertEqual(r.status_code, 503, r.text)


class BillingWebhookTests(BillingTestsBase):

    def _signed_request(self, event: dict, secret: str = "whsec_test_secret"):
        raw_body = json.dumps(event).encode("utf-8")
        timestamp = str(int(time.time()))
        signed_payload = f"{timestamp}.{raw_body.decode('utf-8')}"
        signature = hmac.new(
            secret.encode("utf-8"), signed_payload.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        header = f"t={timestamp},v1={signature}"

        return raw_body, header

    def test_webhook_rejects_invalid_signature(self):
        event = {"type": "checkout.session.completed", "data": {"object": {}}}
        raw_body = json.dumps(event).encode("utf-8")

        with patch.dict(os.environ, {"STRIPE_WEBHOOK_SECRET": "whsec_test_secret"}):
            r = self.client.post(
                "/api/billing/webhook",
                content=raw_body,
                headers={
                    "content-type": "application/json",
                    "stripe-signature": "t=1,v1=not-a-real-signature",
                },
            )

        self.assertEqual(r.status_code, 400)

    def test_webhook_rejects_when_secret_not_configured(self):
        event = {"type": "checkout.session.completed", "data": {"object": {}}}
        raw_body, header = self._signed_request(event)

        # STRIPE_WEBHOOK_SECRET deliberately left unset here.
        r = self.client.post(
            "/api/billing/webhook",
            content=raw_body,
            headers={"content-type": "application/json", "stripe-signature": header},
        )
        self.assertEqual(r.status_code, 400)

    def test_checkout_completed_event_activates_plan(self):
        _, organization_id = self._register_and_login(
            f"admin8{self._n}@a.com", f"Org8 {self._n}"
        )

        event = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "subscription": "sub_fake123",
                    "metadata": {
                        "organization_id": organization_id,
                        "plan": "team",
                        "billing_cycle": "monthly",
                    },
                }
            },
        }
        raw_body, header = self._signed_request(event)

        with patch.dict(os.environ, {"STRIPE_WEBHOOK_SECRET": "whsec_test_secret"}):
            r = self.client.post(
                "/api/billing/webhook",
                content=raw_body,
                headers={"content-type": "application/json", "stripe-signature": header},
            )

        self.assertEqual(r.status_code, 200, r.text)

        org = self._get_org(organization_id)
        self.assertEqual(org.plan, "team")
        self.assertEqual(org.billing_cycle, "monthly")
        self.assertEqual(org.plan_status, "active")
        self.assertEqual(org.stripe_subscription_id, "sub_fake123")

    def test_subscription_deleted_event_cancels_plan(self):
        _, organization_id = self._register_and_login(
            f"admin9{self._n}@a.com", f"Org9 {self._n}"
        )

        # First get the org onto a paid, active subscription via the
        # same checkout.session.completed path as the test above.
        activate_event = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "subscription": "sub_fake456",
                    "metadata": {
                        "organization_id": organization_id,
                        "plan": "business",
                        "billing_cycle": "yearly",
                    },
                }
            },
        }
        raw_body, header = self._signed_request(activate_event)
        with patch.dict(os.environ, {"STRIPE_WEBHOOK_SECRET": "whsec_test_secret"}):
            self.client.post(
                "/api/billing/webhook",
                content=raw_body,
                headers={"content-type": "application/json", "stripe-signature": header},
            )

        delete_event = {
            "type": "customer.subscription.deleted",
            "data": {"object": {"id": "sub_fake456", "status": "canceled"}},
        }
        raw_body, header = self._signed_request(delete_event)
        with patch.dict(os.environ, {"STRIPE_WEBHOOK_SECRET": "whsec_test_secret"}):
            r = self.client.post(
                "/api/billing/webhook",
                content=raw_body,
                headers={"content-type": "application/json", "stripe-signature": header},
            )

        self.assertEqual(r.status_code, 200, r.text)

        org = self._get_org(organization_id)
        self.assertEqual(org.plan_status, "canceled")
        # Plan/cycle stay as they were - only status flips, so a
        # reactivated subscription later doesn't need those re-sent.
        self.assertEqual(org.plan, "business")

    def test_unrecognized_event_type_is_a_harmless_no_op(self):
        event = {"type": "invoice.paid", "data": {"object": {}}}
        raw_body, header = self._signed_request(event)

        with patch.dict(os.environ, {"STRIPE_WEBHOOK_SECRET": "whsec_test_secret"}):
            r = self.client.post(
                "/api/billing/webhook",
                content=raw_body,
                headers={"content-type": "application/json", "stripe-signature": header},
            )

        self.assertEqual(r.status_code, 200, r.text)


class BillingServiceUnitTests(unittest.TestCase):

    def test_price_id_for_unmapped_plan_raises(self):
        with self.assertRaises(billing_service.BillingNotConfiguredError):
            billing_service._price_id_for("enterprise", "monthly")

    def test_price_id_for_missing_env_var_raises(self):
        with patch.dict(os.environ, {"STRIPE_PRICE_TEAM_MONTHLY": ""}, clear=False):
            os.environ.pop("STRIPE_PRICE_TEAM_MONTHLY", None)
            with self.assertRaises(billing_service.BillingNotConfiguredError):
                billing_service._price_id_for("team", "monthly")

    def test_verify_webhook_signature_rejects_stale_timestamp(self):
        secret = "whsec_stale_test"
        raw_body = b'{"type": "x"}'
        old_timestamp = str(int(time.time()) - 10_000)
        signed_payload = f"{old_timestamp}.{raw_body.decode('utf-8')}"
        signature = hmac.new(
            secret.encode("utf-8"), signed_payload.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        header = f"t={old_timestamp},v1={signature}"

        with patch.dict(os.environ, {"STRIPE_WEBHOOK_SECRET": secret}):
            self.assertFalse(billing_service.verify_webhook_signature(raw_body, header))

    def test_verify_webhook_signature_accepts_valid_signature(self):
        secret = "whsec_valid_test"
        raw_body = b'{"type": "x"}'
        timestamp = str(int(time.time()))
        signed_payload = f"{timestamp}.{raw_body.decode('utf-8')}"
        signature = hmac.new(
            secret.encode("utf-8"), signed_payload.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        header = f"t={timestamp},v1={signature}"

        with patch.dict(os.environ, {"STRIPE_WEBHOOK_SECRET": secret}):
            self.assertTrue(billing_service.verify_webhook_signature(raw_body, header))


if __name__ == "__main__":
    unittest.main()
