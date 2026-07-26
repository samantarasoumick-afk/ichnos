"""
GET /api/mentions - name-prefix autocomplete backing the "@" mention
picker in Ask and the global search bar. Different algorithm from
/api/search's TF-IDF relevance ranking (see
catalog_search_service.list_mentionable()'s docstring): plain
case-insensitive substring matching, prefix matches ranked above
mid-string matches, empty query returns an alphabetical starting list
rather than nothing.
"""

import unittest
import uuid

from fastapi.testclient import TestClient

from app.main import app


class MentionsTests(unittest.TestCase):

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

    def test_prefix_match_ranked_above_midstring_match(self):
        email = f"mention{self._n}@a.com"
        headers = self._register_and_login(email, f"Mention Org {self._n}")

        tag = f"wid{self._n}"

        # "Customer Widget" contains the tag mid-string; "WidgetFlow"
        # starts with it - the latter should rank first even though
        # both are valid substring matches.
        r = self.client.post("/api/business-processes", headers=headers, json={
            "name": f"Customer {tag}",
        })
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.post("/api/business-processes", headers=headers, json={
            "name": f"{tag}Flow",
        })
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.get(f"/api/mentions?q={tag}", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)

        labels = [item["label"] for item in r.json()["results"]]
        self.assertEqual(len(labels), 2)
        self.assertTrue(labels[0].lower().startswith(tag))

    def test_case_insensitive_substring_match(self):
        email = f"mentioncase{self._n}@a.com"
        headers = self._register_and_login(email, f"Mention Case Org {self._n}")

        r = self.client.post("/api/risks", headers=headers, json={
            "title": f"UPPERCASE{self._n} risk",
        })
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.get(f"/api/mentions?q=uppercase{self._n}", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(len(r.json()["results"]), 1)
        self.assertIn("UPPERCASE", r.json()["results"][0]["label"])

    def test_empty_query_returns_alphabetical_starting_list(self):
        email = f"mentionempty{self._n}@a.com"
        headers = self._register_and_login(email, f"Mention Empty Org {self._n}")

        for name in [f"Zebra{self._n}", f"Apple{self._n}", f"Mango{self._n}"]:
            r = self.client.post("/api/controls", headers=headers, json={"name": name})
            self.assertEqual(r.status_code, 200, r.text)

        r = self.client.get("/api/mentions", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)

        labels = [item["label"] for item in r.json()["results"]]
        self.assertEqual(labels, sorted(labels, key=str.lower))

    def test_no_match_returns_empty_list(self):
        email = f"mentionnomatch{self._n}@a.com"
        headers = self._register_and_login(email, f"Mention NoMatch Org {self._n}")

        r = self.client.get("/api/mentions?q=zzzznonexistentqqq", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["results"], [])

    def test_results_are_tenant_scoped(self):
        tag = f"crosstenantmention{self._n}"

        headers_a = self._register_and_login(f"mtenanta{self._n}@a.com", f"Mention Tenant A {self._n}")
        r = self.client.post("/api/risks", headers=headers_a, json={"title": tag})
        self.assertEqual(r.status_code, 200, r.text)

        headers_b = self._register_and_login(f"mtenantb{self._n}@a.com", f"Mention Tenant B {self._n}")

        r = self.client.get(f"/api/mentions?q={tag}", headers=headers_b)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["results"], [])

    def test_unauthenticated_request_is_rejected(self):
        r = self.client.get("/api/mentions?q=anything")
        self.assertEqual(r.status_code, 401, r.text)

    def test_limit_is_respected(self):
        email = f"mentionlimit{self._n}@a.com"
        headers = self._register_and_login(email, f"Mention Limit Org {self._n}")

        tag = f"limitmention{self._n}"
        for i in range(4):
            r = self.client.post("/api/controls", headers=headers, json={"name": f"{tag} {i}"})
            self.assertEqual(r.status_code, 200, r.text)

        r = self.client.get(f"/api/mentions?q={tag}&limit=2", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(len(r.json()["results"]), 2)

    def test_returns_subtitle_matching_search_endpoint_shape(self):
        email = f"mentionsubtitle{self._n}@a.com"
        headers = self._register_and_login(email, f"Mention Subtitle Org {self._n}")

        term = f"MentionTerm{self._n}"
        r = self.client.post("/api/governance/glossary", headers=headers, json={
            "term": term,
            "definition": "A term for testing mention subtitles",
            "domain": "Testing",
        })
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.get(f"/api/mentions?q={term}", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)

        result = r.json()["results"][0]
        self.assertEqual(result["type"], "glossary_term")
        self.assertIn("Glossary term", result["subtitle"])
        self.assertIn("Testing", result["subtitle"])


if __name__ == "__main__":
    unittest.main()
