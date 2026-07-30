"""
Side-by-side comparison of TF-IDF vs. Voyage dense-embedding search,
run against a real organization's real catalog data. This is a
one-time local evaluation tool, not something exposed over HTTP -
same convention as scripts/seed_demo_data.py.

Why this has to run locally rather than from wherever this was
written: Voyage's API isn't reachable from every environment (e.g. an
egress-restricted sandbox), so this script needs to run somewhere
with real internet access and your real VOYAGE_API_KEY in
backend/.env.

What it does, for each query in QUERIES below:
  1. Runs catalog_search_service.semantic_search() - the free, local
     TF-IDF ranking (works with no API key).
  2. Runs embedding_service.semantic_search() - real Voyage embeddings
     if VOYAGE_API_KEY is set and reachable, otherwise this silently
     falls back to the same TF-IDF result (see embedding_service.py's
     docstring) - so a second identical column is a sign the key
     isn't being picked up, not a sign Voyage found nothing.
  3. Prints both ranked lists side by side with scores, plus timing.

What to look for:
  - Do the two rankings actually differ? If every query returns an
    identical order, something's wrong with the Voyage path (check
    VOYAGE_API_KEY is set, and stderr for request errors - Voyage
    calls never raise, they just fall back silently).
  - For the "unrelated_terms" query specifically: TF-IDF is expected
    to return an empty or near-empty list (no term overlap = 0 score).
    If Voyage returns results with non-trivial scores here, that's the
    known behavior difference flagged in review - dense cosine
    similarity for short texts is rarely exactly 0 even for unrelated
    pairs, so "no relevant results" may need an explicit similarity
    threshold rather than today's `score > 0` cutoff. Worth judging by
    eye whether those low-scoring results still look reasonable or
    look like noise.
  - Timing: the first query pays for embedding the whole corpus
    (cold-start); every query after that should be much faster
    (corpus vectors are cached in entity_embeddings, only the query
    text itself gets embedded fresh each time).

Usage (from the backend/ directory, with the venv active and
VOYAGE_API_KEY set in backend/.env):
    python3 scripts/eval_semantic_search.py --email you@example.com
    python3 scripts/eval_semantic_search.py --email you@example.com --top-k 5
    python3 scripts/eval_semantic_search.py --email you@example.com \
        --query "who owns the customer data" --query "late shipments"
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app.main  # noqa: E402  (loads .env, registers every model on Base.metadata)

from app.db.database import SessionLocal  # noqa: E402
from app.models.organization import Organization  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services import catalog_search_service  # noqa: E402
from app.services import embedding_service  # noqa: E402


# A deliberately mixed set: some that should have an obvious best
# match, some phrased as a human question rather than keywords (where
# semantic search should have the bigger edge over TF-IDF), and one
# intentionally unrelated to anything in a typical catalog, to see how
# each approach handles "there's nothing relevant here."
DEFAULT_QUERIES = [
    "customer contact information",
    "who is responsible for data quality issues",
    "revenue and payments",
    "where does personal data get stored",
    "things that are broken or need review",
    "unrelated_terms: giraffe migration patterns in the Serengeti",
]


def run_query(db, org_id: str, query: str, top_k: int):
    t0 = time.perf_counter()
    tfidf_results = catalog_search_service.semantic_search(db, org_id, query, top_k=top_k)
    t1 = time.perf_counter()
    embed_results = embedding_service.semantic_search(db, org_id, query, top_k=top_k)
    t2 = time.perf_counter()

    print(f"\n=== Query: {query!r} ===")
    print(f"  TF-IDF   ({(t1 - t0) * 1000:6.1f} ms):")
    if not tfidf_results:
        print("    (no results)")
    for r in tfidf_results:
        print(f"    {r.score:.4f}  [{r.document.doc_type}] {r.document.label}")

    print(f"  Voyage   ({(t2 - t1) * 1000:6.1f} ms):")
    if not embed_results:
        print("    (no results)")
    for r in embed_results:
        print(f"    {r.score:.4f}  [{r.document.doc_type}] {r.document.label}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--email", required=True, help="Existing user - search runs against their organization's catalog")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--query", action="append", dest="queries", help="Repeatable. Overrides the default query set entirely.")
    args = parser.parse_args()

    if not os.getenv("VOYAGE_API_KEY"):
        print("WARNING: VOYAGE_API_KEY is not set in this process's environment.")
        print("Every 'Voyage' column below will just be TF-IDF again via fallback.")
        print("Check backend/.env has a real key and you're running this from backend/.\n")

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == args.email).first()
        if not user:
            print(f"No user found with email {args.email!r}. Register that account first.")
            sys.exit(1)

        organization = db.query(Organization).filter(Organization.id == user.organization_id).first()
        print(f"Evaluating search over organization {organization.name!r} ({organization.id})")

        queries = args.queries or DEFAULT_QUERIES
        for query in queries:
            run_query(db, organization.id, query, args.top_k)

    finally:
        db.close()


if __name__ == "__main__":
    main()
