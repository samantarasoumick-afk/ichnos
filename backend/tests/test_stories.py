"""
Integration tests for /api/stories - the "stitch your own story"
feature: a user-authored guided tour, saved as an ordered sequence of
steps (each a path + optional dataset schema/table name + optional tab
+ optional query params + a narrative caption), mirroring the shape of
the hand-written scenarios in frontend/src/lib/tourScenarios.ts closely
enough that the frontend can play one back through the exact same
TourContext/TourStepper machinery once fetched.

Covers create/list/detail/delete, tenant scoping, role gating, empty-
steps rejection, and that step order + optional fields (dataset ref,
tab, query params) round-trip exactly as saved.
"""

import unittest
import uuid

from fastapi.testclient import TestClient

from app.main import app


class StoryTests(unittest.TestCase):

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
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    def _story_payload(self, title="My onboarding walkthrough"):
        return {
            "title": f"{title} {self._n}",
            "problem": "New hires don't know where to start.",
            "solution_summary": "A guided lap around the parts that matter.",
            "steps": [
                {
                    "title": "Search first",
                    "narrative": "Start with the catalog search.",
                    "path": "/",
                    "query": {"q": "customer"},
                },
                {
                    "title": "The authoritative table",
                    "narrative": "This is the one to trust.",
                    "path": "/datasets/[id]",
                    "dataset": {"schema_name": "public", "table_name": "customers"},
                    "tab": "business",
                },
            ],
        }

    def test_create_and_get_story_round_trips_steps_in_order(self):
        headers = self._register_and_login(f"story1{self._n}@a.com", f"Story Org 1 {self._n}")

        r = self.client.post("/api/stories", headers=headers, json=self._story_payload())
        self.assertEqual(r.status_code, 200, r.text)
        created = r.json()

        self.assertEqual(len(created["steps"]), 2)
        self.assertEqual(created["steps"][0]["order_index"], 0)
        self.assertEqual(created["steps"][1]["order_index"], 1)
        self.assertEqual(created["steps"][0]["query_params"], {"q": "customer"})
        self.assertEqual(created["steps"][1]["dataset_schema_name"], "public")
        self.assertEqual(created["steps"][1]["dataset_table_name"], "customers")
        self.assertEqual(created["steps"][1]["tab"], "business")
        self.assertIsNone(created["steps"][0]["dataset_schema_name"])

        r = self.client.get(f"/api/stories/{created['id']}", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        fetched = r.json()
        self.assertEqual(fetched["title"], created["title"])
        self.assertEqual([s["title"] for s in fetched["steps"]], ["Search first", "The authoritative table"])

    def test_create_rejects_a_story_with_no_steps(self):
        headers = self._register_and_login(f"story2{self._n}@a.com", f"Story Org 2 {self._n}")

        payload = self._story_payload()
        payload["steps"] = []

        r = self.client.post("/api/stories", headers=headers, json=payload)
        self.assertEqual(r.status_code, 400)

    def test_list_returns_summaries_with_step_count_but_not_steps(self):
        headers = self._register_and_login(f"story3{self._n}@a.com", f"Story Org 3 {self._n}")
        self.client.post("/api/stories", headers=headers, json=self._story_payload())

        r = self.client.get("/api/stories", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        summaries = r.json()

        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0]["step_count"], 2)
        self.assertNotIn("steps", summaries[0])

    def test_stories_are_tenant_scoped(self):
        headers_a = self._register_and_login(f"story4a{self._n}@a.com", f"Story Org 4A {self._n}")
        headers_b = self._register_and_login(f"story4b{self._n}@a.com", f"Story Org 4B {self._n}")

        r = self.client.post("/api/stories", headers=headers_a, json=self._story_payload())
        story_id = r.json()["id"]

        r = self.client.get("/api/stories", headers=headers_b)
        self.assertEqual(r.json(), [])

        r = self.client.get(f"/api/stories/{story_id}", headers=headers_b)
        self.assertEqual(r.status_code, 404)

    def test_delete_story_removes_it_and_its_steps(self):
        headers = self._register_and_login(f"story5{self._n}@a.com", f"Story Org 5 {self._n}")
        r = self.client.post("/api/stories", headers=headers, json=self._story_payload())
        story_id = r.json()["id"]

        r = self.client.delete(f"/api/stories/{story_id}", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.get(f"/api/stories/{story_id}", headers=headers)
        self.assertEqual(r.status_code, 404)

    def test_role_gating_viewer_cannot_create_or_delete(self):
        headers = self._register_and_login(f"story6{self._n}@a.com", f"Story Org 6 {self._n}")

        r = self.client.post("/api/users", headers=headers, json={
            "email": f"storyviewer{self._n}@a.com",
            "password": "password123",
            "role": "viewer",
        })
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.post("/api/auth/login", json={
            "email": f"storyviewer{self._n}@a.com",
            "password": "password123",
        })
        viewer_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

        r = self.client.post("/api/stories", headers=viewer_headers, json=self._story_payload())
        self.assertEqual(r.status_code, 403)

        # Viewers can still list/play existing stories - authoring is
        # gated, consuming isn't.
        r = self.client.get("/api/stories", headers=viewer_headers)
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.post("/api/stories", headers=headers, json=self._story_payload())
        story_id = r.json()["id"]

        r = self.client.delete(f"/api/stories/{story_id}", headers=viewer_headers)
        self.assertEqual(r.status_code, 403)


if __name__ == "__main__":
    unittest.main()
