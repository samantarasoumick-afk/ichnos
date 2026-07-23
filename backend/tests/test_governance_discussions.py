"""
Tests for governance discussion threads: any authenticated user can
open a QUESTION or PROPOSAL thread (dataset-scoped or global), reply
to it, and only the author or a steward/admin can resolve it.
Everything is tenant-scoped and audit logged.
"""

import unittest
import uuid

from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.main import app
from app.models.dataset import Dataset
from app.models.user import User


class GovernanceDiscussionTests(unittest.TestCase):

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

    def _invite(self, admin_headers, email, role):
        r = self.client.post("/api/users", headers=admin_headers, json={
            "email": email,
            "password": "password123",
            "role": role,
        })
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.post("/api/auth/login", json={
            "email": email,
            "password": "password123",
        })
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    def _create_dataset(self, email):
        db = SessionLocal()
        try:
            me = db.query(User).filter(User.email == email).first()

            r = self.client.post("/api/sources", headers=self._headers_cache[email], json={
                "name": f"Source {self._n}",
                "type": "postgresql",
                "connection_config": {"host": "x"},
            })
            source_id = r.json()["id"]

            dataset = Dataset(
                name="orders", schema_name="public",
                source_id=source_id, organization_id=me.organization_id,
            )
            db.add(dataset)
            db.commit()
            db.refresh(dataset)
            return dataset.id
        finally:
            db.close()

    def test_create_global_question_thread(self):
        headers = self._register_and_login(f"gd1{self._n}@a.com", f"Discuss Org 1 {self._n}")
        self._headers_cache = {f"gd1{self._n}@a.com": headers}

        r = self.client.post("/api/discussions", headers=headers, json={
            "thread_type": "question",
            "title": "What does the trust_score field actually mean?",
            "body": "Analysts keep asking me this.",
        })
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertIsNone(body["dataset_id"])
        self.assertEqual(body["thread_type"], "QUESTION")
        self.assertEqual(body["status"], "OPEN")
        self.assertEqual(body["reply_count"], 0)
        self.assertEqual(body["replies"], [])

    def test_create_dataset_scoped_proposal_thread(self):
        email = f"gd2{self._n}@a.com"
        headers = self._register_and_login(email, f"Discuss Org 2 {self._n}")
        self._headers_cache = {email: headers}
        dataset_id = self._create_dataset(email)

        r = self.client.post("/api/discussions", headers=headers, json={
            "dataset_id": dataset_id,
            "thread_type": "PROPOSAL",
            "title": "Deprecate this table in favor of clean_orders",
        })
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["dataset_id"], dataset_id)
        self.assertEqual(body["dataset_label"], "public.orders")
        self.assertEqual(body["thread_type"], "PROPOSAL")

    def test_invalid_thread_type_rejected(self):
        headers = self._register_and_login(f"gd3{self._n}@a.com", f"Discuss Org 3 {self._n}")

        r = self.client.post("/api/discussions", headers=headers, json={
            "thread_type": "RANT",
            "title": "This is not a valid type",
        })
        self.assertEqual(r.status_code, 400)

    def test_reply_and_list_and_filter(self):
        headers = self._register_and_login(f"gd4{self._n}@a.com", f"Discuss Org 4 {self._n}")

        r = self.client.post("/api/discussions", headers=headers, json={
            "thread_type": "QUESTION",
            "title": "Q1",
        })
        thread_id = r.json()["id"]

        r = self.client.post("/api/discussions", headers=headers, json={
            "thread_type": "PROPOSAL",
            "title": "P1",
        })

        r = self.client.post(f"/api/discussions/{thread_id}/replies", headers=headers, json={
            "body": "Here's an answer.",
        })
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["reply_count"], 1)
        self.assertEqual(len(r.json()["replies"]), 1)
        self.assertEqual(r.json()["replies"][0]["body"], "Here's an answer.")

        r = self.client.get("/api/discussions", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(len(r.json()), 2)

        r = self.client.get("/api/discussions?thread_type=proposal", headers=headers)
        self.assertEqual(len(r.json()), 1)
        self.assertEqual(r.json()[0]["title"], "P1")

        r = self.client.get(f"/api/discussions/{thread_id}", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(len(r.json()["replies"]), 1)

    def test_author_can_resolve_own_thread(self):
        email = f"gd5{self._n}@a.com"
        headers = self._register_and_login(email, f"Discuss Org 5 {self._n}")

        r = self.client.post("/api/discussions", headers=headers, json={
            "thread_type": "QUESTION",
            "title": "Q",
        })
        thread_id = r.json()["id"]

        r = self.client.post(f"/api/discussions/{thread_id}/resolve", headers=headers, json={
            "resolution_note": "Answered in thread.",
        })
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["status"], "RESOLVED")
        self.assertEqual(r.json()["resolution_note"], "Answered in thread.")

        r = self.client.post(f"/api/discussions/{thread_id}/resolve", headers=headers, json={})
        self.assertEqual(r.status_code, 400)

    def test_non_author_viewer_cannot_resolve_others_thread(self):
        admin_email = f"gd6a{self._n}@a.com"
        admin_headers = self._register_and_login(admin_email, f"Discuss Org 6 {self._n}")

        r = self.client.post("/api/discussions", headers=admin_headers, json={
            "thread_type": "QUESTION",
            "title": "Admin's question",
        })
        thread_id = r.json()["id"]

        viewer_headers = self._invite(admin_headers, f"gd6v{self._n}@a.com", "viewer")

        r = self.client.post(f"/api/discussions/{thread_id}/resolve", headers=viewer_headers, json={})
        self.assertEqual(r.status_code, 403)

    def test_steward_can_resolve_others_thread(self):
        admin_email = f"gd7a{self._n}@a.com"
        admin_headers = self._register_and_login(admin_email, f"Discuss Org 7 {self._n}")

        r = self.client.post("/api/discussions", headers=admin_headers, json={
            "thread_type": "PROPOSAL",
            "title": "Should we adopt this?",
        })
        thread_id = r.json()["id"]

        steward_headers = self._invite(admin_headers, f"gd7s{self._n}@a.com", "steward")

        r = self.client.post(f"/api/discussions/{thread_id}/resolve", headers=steward_headers, json={
            "resolution_note": "Accepted.",
        })
        self.assertEqual(r.status_code, 200, r.text)

    def test_viewer_can_open_and_reply_to_threads(self):
        """
        Discussions are meant to democratize governance conversation -
        an analyst (viewer role) should be able to ask a question or
        reply, even though they can't edit governance metadata
        directly.
        """
        admin_email = f"gd8a{self._n}@a.com"
        admin_headers = self._register_and_login(admin_email, f"Discuss Org 8 {self._n}")
        viewer_headers = self._invite(admin_headers, f"gd8v{self._n}@a.com", "viewer")

        r = self.client.post("/api/discussions", headers=viewer_headers, json={
            "thread_type": "QUESTION",
            "title": "What does this column mean?",
        })
        self.assertEqual(r.status_code, 200, r.text)
        thread_id = r.json()["id"]

        r = self.client.post(f"/api/discussions/{thread_id}/replies", headers=admin_headers, json={
            "body": "It's the total order amount in cents.",
        })
        self.assertEqual(r.status_code, 200, r.text)

    def test_threads_are_tenant_scoped(self):
        headers_a = self._register_and_login(f"gd9a{self._n}@a.com", f"Discuss Org 9a {self._n}")
        headers_b = self._register_and_login(f"gd9b{self._n}@a.com", f"Discuss Org 9b {self._n}")

        r = self.client.post("/api/discussions", headers=headers_a, json={
            "thread_type": "QUESTION",
            "title": "Org A's question",
        })
        thread_id = r.json()["id"]

        r = self.client.get("/api/discussions", headers=headers_b)
        self.assertEqual(r.json(), [])

        r = self.client.get(f"/api/discussions/{thread_id}", headers=headers_b)
        self.assertEqual(r.status_code, 404)

        r = self.client.post(f"/api/discussions/{thread_id}/replies", headers=headers_b, json={
            "body": "shouldn't work",
        })
        self.assertEqual(r.status_code, 404)

    def test_dataset_scoped_thread_requires_org_owned_dataset(self):
        headers_a = self._register_and_login(f"gd10a{self._n}@a.com", f"Discuss Org 10a {self._n}")
        email_b = f"gd10b{self._n}@a.com"
        headers_b = self._register_and_login(email_b, f"Discuss Org 10b {self._n}")
        self._headers_cache = {email_b: headers_b}
        dataset_id_b = self._create_dataset(email_b)

        r = self.client.post("/api/discussions", headers=headers_a, json={
            "dataset_id": dataset_id_b,
            "thread_type": "QUESTION",
            "title": "Trying to attach to someone else's dataset",
        })
        self.assertEqual(r.status_code, 404)

    def test_create_issue_thread_raised_for_stakeholder(self):
        admin_email = f"gd12a{self._n}@a.com"
        admin_headers = self._register_and_login(admin_email, f"Discuss Org 12 {self._n}")
        steward_email = f"gd12s{self._n}@a.com"
        self._invite(admin_headers, steward_email, "steward")

        db = SessionLocal()
        try:
            steward = db.query(User).filter(User.email == steward_email).first()
            steward_id = steward.id
        finally:
            db.close()

        r = self.client.post("/api/discussions", headers=admin_headers, json={
            "thread_type": "issue",
            "title": "Stale freshness on the orders table",
            "body": "Needs someone from data eng to look at the pipeline.",
            "raised_for_user_id": steward_id,
        })
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["thread_type"], "ISSUE")
        self.assertEqual(body["raised_for_user_id"], steward_id)
        self.assertEqual(body["raised_for_email"], steward_email)

        r = self.client.get("/api/discussions?thread_type=issue", headers=admin_headers)
        self.assertEqual(len(r.json()), 1)
        self.assertEqual(r.json()[0]["raised_for_email"], steward_email)

    def test_issue_thread_without_raised_for_is_optional(self):
        headers = self._register_and_login(f"gd13{self._n}@a.com", f"Discuss Org 13 {self._n}")

        r = self.client.post("/api/discussions", headers=headers, json={
            "thread_type": "ISSUE",
            "title": "Something's off but not sure who owns it",
        })
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIsNone(r.json()["raised_for_user_id"])
        self.assertIsNone(r.json()["raised_for_email"])

    def test_raised_for_user_must_be_in_same_org(self):
        headers_a = self._register_and_login(f"gd14a{self._n}@a.com", f"Discuss Org 14a {self._n}")
        self._register_and_login(f"gd14b{self._n}@a.com", f"Discuss Org 14b {self._n}")

        db = SessionLocal()
        try:
            outsider = db.query(User).filter(User.email == f"gd14b{self._n}@a.com").first()
            outsider_id = outsider.id
        finally:
            db.close()

        r = self.client.post("/api/discussions", headers=headers_a, json={
            "thread_type": "ISSUE",
            "title": "Trying to raise this for someone outside my org",
            "raised_for_user_id": outsider_id,
        })
        self.assertEqual(r.status_code, 404)

    def test_create_and_reply_and_resolve_are_audit_logged(self):
        headers = self._register_and_login(f"gd11{self._n}@a.com", f"Discuss Org 11 {self._n}")

        r = self.client.post("/api/discussions", headers=headers, json={
            "thread_type": "QUESTION",
            "title": "Audit me",
        })
        thread_id = r.json()["id"]

        self.client.post(f"/api/discussions/{thread_id}/replies", headers=headers, json={
            "body": "reply",
        })
        self.client.post(f"/api/discussions/{thread_id}/resolve", headers=headers, json={})

        r = self.client.get("/api/audit-log", headers=headers)
        actions = [entry["action"] for entry in r.json()]
        self.assertIn("discussion.create", actions)
        self.assertIn("discussion.reply", actions)
        self.assertIn("discussion.resolve", actions)


if __name__ == "__main__":
    unittest.main()
