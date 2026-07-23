# Developer Guide

## Backend

Install dependencies from `backend/requirements.txt`.

Run the backend from `backend`:

```bash
uvicorn app.main:app --reload
```

The frontend expects the backend at:

```text
http://127.0.0.1:8000
```

## Frontend

Run from `frontend`:

```bash
npm run dev
```

Build and lint:

```bash
npm run lint
npm run build
```

## Verification

Recommended checks after changes:

```bash
python3 -m py_compile $(find backend/app -name '*.py')
npm run lint
npm run build
```

## Development Rules

- Build milestone capabilities, not random endpoints.
- Keep docs updated with implementation changes.
- Prefer small, coherent domain modules.
- Add tests around scanner, schema responses, and frontend routes as the platform matures.
