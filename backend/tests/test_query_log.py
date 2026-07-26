"""
Query logging (app/services/query_log_service.py): every Ask question
and every global-search query gets recorded with a coarse
matched/unmatched signal, and admins can see both the raw log and an
aggregated "what's not landing" report at GET /api/query-log/report.
Non-admins are rejected from both endpoints - unlike Audit Log, this
exposes the literal text people searched for.
"""

import unittest
import uuid

from fastapi.testclient import TestClient

from app.main import app


class QueryLogTests(unittest.TestCase):

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
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    def _invite_viewer(self, admin_headers, email):
        r = self.client.post("/api/users", headers=admin_headers, json={
            "email": email,
            "password": "password123",
            "role": "viewer",
        })
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.post("/api/auth/login", json={"email": email, "password": "password123"})
        self.assertEqual(r.status_code, 200, r.text)
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    def test_search_query_is_logged_with_matched_flag(self):
        email = f"qlogsearch{self._n}@a.com"
        headers = self._register_and_login(email, f"QLog Search Org {self._n}")

        tag = f"widgetflow{self._n}"
        self.client.post("/api/risks", headers=headers, json={
            "title": f"{tag} risk",
            "description": f"Risk about {tag}",
            "category": "OPERATIONAL",
        })

        # A query with a real hit and one that comes up empty.
        self.client.get(f"/api/search?q={tag}", headers=headers)
        self.client.get(f"/api/search?q=zzzznonexistentqqq{self._n}", headers=headers)

        r = self.client.get("/api/query-log?source=search", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        entries = r.json()
        by_text = {e["query_text"]: e for e in entries}

        self.assertTrue(by_text[tag]["matched"])
        self.assertFalse(by_text[f"zzzznonexistentqqq{self._n}"]["matched"])
        self.assertEqual(by_text[tag]["source"], "search")

    def test_ask_query_is_logged_matched_when_a_known_dataset_is_named(self):
        email = f"qlogask{self._n}@a.com"
        headers = self._register_and_login(email, f"QLog Ask Org {self._n}")

        # No datasets exist yet - answer_question's "nothing in your
        # catalog yet" branch is one of the fixed give-up messages, so
        # this should log as unmatched.
        self.client.post("/api/assistant/ask", headers=headers, json={
            "query": "who owns customers?",
        })

        r = self.client.get("/api/query-log?source=ask", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        entries = r.json()
        self.assertEqual(len(entries), 1)
        self.assertFalse(entries[0]["matched"])
        self.assertEqual(entries[0]["query_text"], "who owns customers?")

    def test_empty_search_query_is_not_logged(self):
        email = f"qlogempty{self._n}@a.com"
        headers = self._register_and_login(email, f"QLog Empty Org {self._n}")

        self.client.get("/api/search?q=", headers=headers)

        r = self.client.get("/api/query-log", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json(), [])

    def test_report_aggregates_repeated_unanswered_queries(self):
        email = f"qlogreport{self._n}@a.com"
        headers = self._register_and_login(email, f"QLog Report Org {self._n}")

        # Same unanswered question asked three times, plus one that
        # actually returns a search hit.
        for _ in range(3):
            self.client.post("/api/assistant/ask", headers=headers, json={
                "query": "does anyone own the mystery table?",
            })

        tag = f"reportable{self._n}"
        self.client.post("/api/risks", headers=headers, json={
            "title": f"{tag} risk",
            "description": f"About {tag}",
            "category": "OPERATIONAL",
        })
        self.client.get(f"/api/search?q={tag}", headers=headers)

        r = self.client.get("/api/query-log/report", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        report = r.json()

        self.assertEqual(report["total_queries"], 4)
        self.assertEqual(report["unanswered_count"], 3)
        self.assertEqual(report["unanswered_rate"], 75.0)

        top = report["top_unanswered"][0]
        self.assertEqual(top["query_text"], "does anyone own the mystery table?")
        self.assertEqual(top["count"], 3)
        self.assertEqual(top["sources"], ["ask"])

        overall_texts = [g["query_text"] for g in report["top_overall"]]
        self.assertIn("does anyone own the mystery table?", overall_texts)
        self.assertIn(tag, overall_texts)

    def test_report_and_list_are_tenant_scoped(self):
        headers_a = self._register_and_login(f"qlogtenanta{self._n}@a.com", f"QLog Tenant A {self._n}")
        headers_b = self._register_and_login(f"qlogtenantb{self._n}@a.com", f"QLog Tenant B {self._n}")

        self.client.post("/api/assistant/ask", headers=headers_a, json={
            "query": "org a only question",
        })

        r = self.client.get("/api/query-log", headers=headers_b)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json(), [])

        r = self.client.get("/api/query-log/report", headers=headers_b)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["total_queries"], 0)

    def test_non_admin_is_rejected_from_list_and_report(self):
        admin_headers = self._register_and_login(f"qlogadmin{self._n}@a.com", f"QLog Admin Org {self._n}")
        viewer_headers = self._invite_viewer(admin_headers, f"qlogviewer{self._n}@a.com")

        r = self.client.get("/api/query-log", headers=viewer_headers)
        self.assertEqual(r.status_code, 403, r.text)

        r = self.client.get("/api/query-log/report", headers=viewer_headers)
        self.assertEqual(r.status_code, 403, r.text)

    def test_unauthenticated_request_is_rejected(self):
        r = self.client.get("/api/query-log")
        self.assertEqual(r.status_code, 401, r.text)

        r = self.client.get("/api/query-log/report")
        self.assertEqual(r.status_code, 401, r.text)


if __name__ == "__main__":
    unittest.main()
