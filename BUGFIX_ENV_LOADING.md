# Bugfix — .env was never actually loaded

Date: 2026-07-22
Reported by: Soumick (alembic failed with "Could not parse SQLAlchemy
URL from given URL string" immediately after following the setup
instructions in the earlier handoff docs)

## Root cause

Every prior handoff doc said "copy `.env.example` to `.env` and fill
it in." That's necessary but not sufficient - `.env` files are not
automatically read by the shell, by `python`, by `uvicorn`, or by
`alembic`. Something has to explicitly parse the file and load its
contents into the process environment. Nothing in the delivered code
did that, so `os.getenv("DATABASE_URL")` returned `None` no matter
what was in `.env`, and `alembic/env.py`'s `if database_url:` guard
silently skipped setting the connection string, leaving
`alembic.ini`'s intentionally-empty `sqlalchemy.url =` in place -
which SQLAlchemy then failed to parse.

This wasn't a mistake in what you did; the instructions had a real
gap.

## Fix

Added `python-dotenv` to `requirements.txt`, and `load_dotenv()` as
the very first thing that runs in both `app/main.py` and
`alembic/env.py` - before any other import, since several modules
(`db/database.py`, `auth/jwt_handler.py`, `utils/crypto.py`) read
`os.getenv()` at *import time*, not inside a function, so loading
`.env` even slightly too late would still miss them.

## Verification

Reproduced the exact failure first: ran `alembic upgrade head` in a
completely clean environment (`env -i`, i.e. zero exported variables,
matching a fresh terminal that only has a `.env` file) - confirmed it
failed the same way. Applied the fix, re-ran the identical `env -i`
command - migrations ran successfully. Also confirmed the app itself
boots correctly under the same clean-environment condition, and the
full test suite (41/41) still passes unaffected, since the test
suite's `conftest.py` sets environment variables directly rather than
relying on a `.env` file, and `load_dotenv()` never overrides
variables that are already set.

## What this means for you

No change to your `.env` file or the steps you already ran - just
`pip install -r requirements.txt` again to pick up `python-dotenv`,
then re-run `alembic upgrade head` and `uvicorn app.main:app --reload`
as before. Both should work now with nothing manually exported.
