"""
The global, cross-entity search bar: GET /api/search?q=... ranks
across datasets, glossary terms, business processes, risks, controls,
and discussion threads via the shared TF-IDF retrieval in
app/services/catalog_search_service.py. Covers each entity type
showing up with a sensible type/url/subtitle, empty-query and
no-match behavior, and tenant isolation (org B never sees org A's
results for the same query text).
"""

import unittest
import uuid

from fastapi.testclient import TestClient

from app.main import app


class GlobalSearchTests(unittest.TestCase):

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

    def _seed_org(self, headers, tag):
        """
        Creates one of each searchable entity type, all mentioning
        `tag` somewhere in their searchable text, so a query for `tag`
        should return exactly one hit per type.
        """

        r = self.client.post("/api/business-processes", headers=headers, json={
            "name": f"{tag} Process",
            "description": f"Handles {tag} end to end",
        })
        self.assertEqual(r.status_code, 200, r.text)
        process_id = r.json()["id"]

        r = self.client.post("/api/risks", headers=headers, json={
            "title": f"{tag} exposure risk",
            "description": f"Risk related to {tag}",
            "category": "OPERATIONAL",
        })
        self.assertEqual(r.status_code, 200, r.text)
        risk_id = r.json()["id"]

        r = self.client.post("/api/controls", headers=headers, json={
            "name": f"{tag} control",
            "description": f"Mitigates {tag} exposure",
        })
        self.assertEqual(r.status_code, 200, r.text)
        control_id = r.json()["id"]

        r = self.client.post("/api/discussions", headers=headers, json={
            "thread_type": "QUESTION",
            "title": f"What about {tag}?",
            "body": f"Question concerning {tag}",
        })
        self.assertEqual(r.status_code, 200, r.text)
        thread_id = r.json()["id"]

        return {
            "process_id": process_id,
            "risk_id": risk_id,
            "control_id": control_id,
            "thread_id": thread_id,
        }

    def test_returns_a_result_per_entity_type(self):
        email = f"search{self._n}@a.com"
        headers = self._register_and_login(email, f"Search Org {self._n}")

        tag = f"widgetflow{self._n}"
        ids = self._seed_org(headers, tag)

        r = self.client.get(f"/api/search?q={tag}", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)

        results = r.json()["results"]
        self.assertTrue(len(results) >= 4)

        by_type = {item["type"]: item for item in results}
        self.assertEqual(by_type["process"]["id"], ids["process_id"])
        self.assertEqual(by_type["risk"]["id"], ids["risk_id"])
        self.assertEqual(by_type["control"]["id"], ids["control_id"])
        self.assertEqual(by_type["discussion_thread"]["id"], ids["thread_id"])

        self.assertEqual(by_type["process"]["url"], "/processes")
        self.assertEqual(by_type["risk"]["url"], "/risks")
        self.assertEqual(by_type["control"]["url"], "/risks")
        self.assertEqual(by_type["discussion_thread"]["url"], f"/discussions/{ids['thread_id']}")

        self.assertIn("Risk", by_type["risk"]["subtitle"])
        self.assertIn("Control", by_type["control"]["subtitle"])
        self.assertIn("Question", by_type["discussion_thread"]["subtitle"])

    def test_glossary_term_result(self):
        # Dataset search coverage lives in SemanticSearchServiceTests
        # (test_assistant.py) and _dataset_document()'s own inclusion
        # in build_corpus() - datasets aren't directly POST-able (they
        # come from a scan), so a dedicated dataset fixture here would
        # just duplicate that existing coverage. This test checks the
        # glossary_term shape specifically instead.
        email = f"searchdg{self._n}@a.com"
        headers = self._register_and_login(email, f"Search DG Org {self._n}")

        term_name = f"ChurnMetric{self._n}"
        r = self.client.post("/api/governance/glossary", headers=headers, json={
            "term": term_name,
            "definition": "Percentage of customers who stop using the product",
            "domain": "Growth",
        })
        self.assertEqual(r.status_code, 200, r.text)
        term_id = r.json()["id"]

        r = self.client.get(f"/api/search?q={term_name}", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)

        results = r.json()["results"]
        glossary_hits = [item for item in results if item["type"] == "glossary_term"]
        self.assertEqual(len(glossary_hits), 1)
        self.assertEqual(glossary_hits[0]["id"], term_id)
        self.assertEqual(glossary_hits[0]["url"], "/glossary")
        self.assertIn("Glossary term", glossary_hits[0]["subtitle"])
        self.assertIn("Growth", glossary_hits[0]["subtitle"])

    def test_empty_query_returns_no_results_without_error(self):
        email = f"searchempty{self._n}@a.com"
        headers = self._register_and_login(email, f"Search Empty Org {self._n}")

        r = self.client.get("/api/search?q=", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["results"], [])

        r = self.client.get("/api/search", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["results"], [])

    def test_nonsense_query_returns_no_results(self):
        email = f"searchnonsense{self._n}@a.com"
        headers = self._register_and_login(email, f"Search Nonsense Org {self._n}")

        self._seed_org(headers, f"realthing{self._n}")

        r = self.client.get("/api/search?q=zzzznonexistentqqq", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["results"], [])

    def test_results_are_tenant_scoped(self):
        tag = f"crosstenant{self._n}"

        headers_a = self._register_and_login(f"tenanta{self._n}@a.com", f"Tenant A {self._n}")
        self._seed_org(headers_a, tag)

        headers_b = self._register_and_login(f"tenantb{self._n}@a.com", f"Tenant B {self._n}")

        r = self.client.get(f"/api/search?q={tag}", headers=headers_b)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["results"], [])

    def test_unauthenticated_request_is_rejected(self):
        r = self.client.get("/api/search?q=anything")
        self.assertEqual(r.status_code, 401, r.text)

    def test_limit_is_respected(self):
        email = f"searchlimit{self._n}@a.com"
        headers = self._register_and_login(email, f"Search Limit Org {self._n}")

        tag = f"limitcase{self._n}"
        for i in range(3):
            r = self.client.post("/api/risks", headers=headers, json={
                "title": f"{tag} risk {i}",
                "description": f"Concerning {tag}",
            })
            self.assertEqual(r.status_code, 200, r.text)

        r = self.client.get(f"/api/search?q={tag}&limit=2", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(len(r.json()["results"]), 2)


if __name__ == "__main__":
    unittest.main()
