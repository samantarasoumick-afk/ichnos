"""
Website visitor tracking (app/api/marketing.py, marketing_service.py):
the public /api/marketing/track beacon, its deliberately-quiet
rejection of bad input, and link_anon_id_to_signup retroactively
tagging a visitor's earlier events with the org their signup created
once register() runs - see app/api/auth.py's register_user().
"""

import unittest
import uuid

from fastapi.testclient import TestClient

from app.main import app
from app.db.database import SessionLocal
from app.models.marketing_event import MarketingEvent


class MarketingTrackingTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        self._n = uuid.uuid4().hex[:8]

    def _events_for(self, anon_id):
        db = SessionLocal()
        try:
            return (
                db.query(MarketingEvent)
                .filter(MarketingEvent.anon_id == anon_id)
                .order_by(MarketingEvent.created_at.asc())
                .all()
            )
        finally:
            db.close()

    def test_pageview_event_is_recorded(self):
        anon_id = f"anon-{self._n}"

        r = self.client.post("/api/marketing/track", json={
            "event_type": "pageview",
            "anon_id": anon_id,
            "path": "/",
            "utm_source": "google",
        })
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json(), {"ok": True})

        events = self._events_for(anon_id)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, "pageview")
        self.assertEqual(events[0].utm_source, "google")
        self.assertIsNone(events[0].organization_id)

    def test_unrecognized_event_type_is_silently_dropped(self):
        anon_id = f"anon-bad-{self._n}"

        r = self.client.post("/api/marketing/track", json={
            "event_type": "not_a_real_event",
            "anon_id": anon_id,
        })
        # Still 200/ok - a tracking call failing should never surface
        # an error to a visitor who hasn't signed up yet.
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json(), {"ok": True})

        self.assertEqual(self._events_for(anon_id), [])

    def test_missing_anon_id_is_rejected_by_schema(self):
        r = self.client.post("/api/marketing/track", json={
            "event_type": "pageview",
        })
        # anon_id is a required field on TrackEventRequest.
        self.assertEqual(r.status_code, 422)

    def test_blank_anon_id_is_silently_dropped(self):
        r = self.client.post("/api/marketing/track", json={
            "event_type": "pageview",
            "anon_id": "   ",
        })
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self._events_for("   "), [])

    def test_signup_links_prior_events_to_the_new_org(self):
        anon_id = f"anon-convert-{self._n}"

        self.client.post("/api/marketing/track", json={
            "event_type": "pageview",
            "anon_id": anon_id,
            "path": "/",
        })
        self.client.post("/api/marketing/track", json={
            "event_type": "signup_started",
            "anon_id": anon_id,
            "path": "/register",
        })

        r = self.client.post("/api/auth/register", json={
            "email": f"conv{self._n}@a.com",
            "password": "password123",
            "organization_name": f"Conv Org {self._n}",
            "anon_id": anon_id,
        })
        self.assertEqual(r.status_code, 200, r.text)
        organization_id = r.json()["organization_id"]

        events = self._events_for(anon_id)
        # pageview, signup_started, and the signup_completed event
        # record_event/link_anon_id_to_signup adds itself.
        self.assertEqual(len(events), 3)

        event_types = {event.event_type for event in events}
        self.assertIn("signup_completed", event_types)

        # Every prior event for this visitor should now be tagged with
        # the organization their signup created.
        for event in events:
            self.assertEqual(event.organization_id, organization_id)

    def test_signup_without_anon_id_is_a_harmless_no_op(self):
        r = self.client.post("/api/auth/register", json={
            "email": f"noanon{self._n}@a.com",
            "password": "password123",
            "organization_name": f"No Anon Org {self._n}",
        })
        self.assertEqual(r.status_code, 200, r.text)


if __name__ == "__main__":
    unittest.main()
