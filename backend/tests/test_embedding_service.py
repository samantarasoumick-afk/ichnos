"""
Tests for app/services/embedding_service.py - the dense-embeddings
upgrade to catalog_search_service's TF-IDF retrieval. Voyage's HTTP
API is mocked throughout (patch requests.post) rather than hitting a
real network. VOYAGE_API_KEY is set via patch.dict(os.environ, ...)
scoped to individual tests, restored automatically afterward - the
rest of the suite never sets it, so every other test file keeps
exercising the TF-IDF fallback path exactly as before this feature
existed.
"""

import os
import unittest
import uuid
from unittest.mock import MagicMock, patch

from app.db.database import SessionLocal
from app.models.dataset import Dataset
from app.models.entity_embedding import EntityEmbedding
from app.models.organization import Organization
from app.models.source import DataSource
from app.services import embedding_service
from app.services.catalog_search_service import build_corpus


def _fake_voyage_response(vectors: list[list[float]]) -> MagicMock:
    """A MagicMock standing in for requests.post's return value, shaped
    like Voyage's real embeddings response (data items carry their own
    `index`, not assumed to arrive in request order)."""

    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "object": "list",
        "data": [{"object": "embedding", "index": i, "embedding": v} for i, v in enumerate(vectors)],
        "model": "voyage-4-lite",
        "usage": {"total_tokens": 10},
    }
    return mock_response


class EmbeddingServiceTests(unittest.TestCase):

    def setUp(self):
        self._n = uuid.uuid4().hex[:8]
        self.db = SessionLocal()

    def tearDown(self):
        self.db.close()

    def _make_org_and_datasets(self):
        org = Organization(name=f"Embed Org {self._n}", slug=self._n)
        self.db.add(org)
        self.db.flush()

        source = DataSource(name="src", type="postgresql", connection_config={}, organization_id=org.id)
        self.db.add(source)
        self.db.flush()

        relevant = Dataset(
            name="customer_transactions", schema_name="public",
            description="Financial transaction records for customer purchases",
            source_id=source.id, organization_id=org.id,
        )
        irrelevant = Dataset(
            name="server_logs", schema_name="public",
            description="Raw web server access logs",
            source_id=source.id, organization_id=org.id,
        )
        self.db.add_all([relevant, irrelevant])
        self.db.commit()
        return org, relevant, irrelevant

    def test_no_api_key_falls_back_to_tfidf_without_calling_voyage(self):
        # VOYAGE_API_KEY deliberately not set - this is the default
        # state for every other test file in the suite too.
        org, relevant, irrelevant = self._make_org_and_datasets()

        with patch("app.services.embedding_service.requests.post") as mock_post:
            results = embedding_service.semantic_search(
                self.db, org.id, "customer financial transaction data", top_k=5
            )
            mock_post.assert_not_called()

        self.assertTrue(len(results) >= 1)
        self.assertEqual(results[0].document.id, relevant.id)

    @patch.dict(os.environ, {"VOYAGE_API_KEY": "test-voyage-key"})
    def test_ranks_by_cosine_similarity_not_term_overlap(self):
        """
        The query text shares no vocabulary with either dataset's
        description on purpose - if this ranks the "right" dataset
        first anyway, it's proof the ranking came from the mocked
        embedding vectors (real semantic similarity), not from TF-IDF
        term overlap sneaking back in as a fallback.
        """

        org, relevant, irrelevant = self._make_org_and_datasets()

        def fake_post(url, headers=None, json=None, timeout=None):
            if json["input_type"] == "query":
                return _fake_voyage_response([[0.9, 0.1, 0.0]])

            vectors = []
            for text in json["input"]:
                if "Financial transaction" in text:
                    vectors.append([1.0, 0.0, 0.0])  # near the query vector
                else:
                    vectors.append([0.0, -1.0, 0.0])  # far from the query vector
            return _fake_voyage_response(vectors)

        with patch("app.services.embedding_service.requests.post", side_effect=fake_post):
            results = embedding_service.semantic_search(
                self.db, org.id,
                "totally unrelated words chosen to share zero vocabulary with either row",
                top_k=5, doc_types=("dataset",),
            )

        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0].document.id, relevant.id)

    @patch.dict(os.environ, {"VOYAGE_API_KEY": "test-voyage-key"})
    def test_caches_document_embeddings_across_searches(self):
        org, relevant, irrelevant = self._make_org_and_datasets()

        def fake_post(url, headers=None, json=None, timeout=None):
            if json["input_type"] == "query":
                return _fake_voyage_response([[1.0, 0.0]])
            return _fake_voyage_response([[1.0, 0.0] for _ in json["input"]])

        with patch("app.services.embedding_service.requests.post", side_effect=fake_post) as mock_post:
            embedding_service.semantic_search(self.db, org.id, "first query", top_k=5, doc_types=("dataset",))
            first_call_count = mock_post.call_count

        self.assertEqual(first_call_count, 2)  # one document batch + one query

        stored = self.db.query(EntityEmbedding).filter(EntityEmbedding.entity_type == "dataset").all()
        self.assertEqual(len(stored), 2)

        with patch("app.services.embedding_service.requests.post", side_effect=fake_post) as mock_post:
            embedding_service.semantic_search(self.db, org.id, "second query", top_k=5, doc_types=("dataset",))
            # Documents already cached from the first search - only the
            # (never-cached) query text should trigger a new call.
            self.assertEqual(mock_post.call_count, 1)

    @patch.dict(os.environ, {"VOYAGE_API_KEY": "test-voyage-key"})
    def test_editing_a_dataset_invalidates_its_cached_embedding(self):
        org, relevant, irrelevant = self._make_org_and_datasets()

        with patch("app.services.embedding_service.requests.post") as mock_post:
            mock_post.return_value = _fake_voyage_response([[1.0, 0.0], [0.0, 1.0]])
            corpus = build_corpus(self.db, org.id, doc_types=("dataset",))
            embedding_service.get_or_create_embeddings(self.db, corpus)
            self.assertEqual(mock_post.call_count, 1)

        before = (
            self.db.query(EntityEmbedding)
            .filter(EntityEmbedding.entity_id == relevant.id)
            .first()
        )
        original_hash = before.text_hash

        relevant.description = "A completely different description than before"
        self.db.commit()

        with patch("app.services.embedding_service.requests.post") as mock_post:
            # Only the edited dataset needs re-embedding this time -
            # the untouched one is served from cache - so the batch is
            # one document, not two.
            mock_post.return_value = _fake_voyage_response([[1.0, 0.0]])
            corpus = build_corpus(self.db, org.id, doc_types=("dataset",))
            embedding_service.get_or_create_embeddings(self.db, corpus)
            self.assertEqual(mock_post.call_count, 1)

        after = (
            self.db.query(EntityEmbedding)
            .filter(EntityEmbedding.entity_id == relevant.id)
            .first()
        )
        self.assertNotEqual(after.text_hash, original_hash)

    @patch.dict(os.environ, {"VOYAGE_API_KEY": "test-voyage-key"})
    def test_voyage_failure_falls_back_to_tfidf_gracefully(self):
        org, relevant, irrelevant = self._make_org_and_datasets()

        with patch("app.services.embedding_service.requests.post", side_effect=Exception("network down")):
            results = embedding_service.semantic_search(
                self.db, org.id, "customer financial transaction data", top_k=5
            )

        # Same result TF-IDF alone would give - the failure degrades
        # search, it doesn't break it.
        self.assertTrue(len(results) >= 1)
        self.assertEqual(results[0].document.id, relevant.id)


if __name__ == "__main__":
    unittest.main()
