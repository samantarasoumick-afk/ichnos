import os
import time

from threading import Lock

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "300"))

# The login endpoint already has its own tighter, account-specific
# lockout (see api/auth.py) that's more useful than a generic IP
# limit for brute-force protection; health checks are exempted so an
# uptime monitor polling every few seconds can't trip this.
_EXEMPT_PATHS = {"/", "/health"}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    A simple fixed-window rate limiter keyed by client IP: at most
    RATE_LIMIT_PER_MINUTE requests per rolling 60-second window across
    the whole API (today, only /api/auth/login has any request
    throttling at all - everything else is unlimited).

    In-process and in-memory by design, sized for a single self-hosted
    instance (see docs/SELF_HOSTING.md) rather than a multi-replica
    deployment - if this ever runs behind a load balancer with more
    than one backend process, move the counters to Redis or similar so
    the limit is shared across instances instead of being per-process.
    """

    def __init__(self, app):
        super().__init__(app)
        self._counts: dict[str, tuple[int, int]] = {}
        self._lock = Lock()

    async def dispatch(self, request: Request, call_next):

        if not RATE_LIMIT_ENABLED or request.url.path in _EXEMPT_PATHS:
            return await call_next(request)

        # Behind the website's nginx reverse proxy (see
        # website/nginx.conf), every request's direct TCP peer is the
        # frontend container, not the real visitor - nginx sets
        # X-Forwarded-For, so prefer that (leftmost entry = original
        # client) when present. This backend is never exposed
        # directly to the internet (bound to 127.0.0.1 / the Docker
        # network only), so trusting this header here doesn't open a
        # spoofing hole the way it would on a directly-internet-facing
        # service.
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()
        else:
            client_ip = request.client.host if request.client else "unknown"
        window = int(time.time() // 60)
        key = f"{client_ip}:{window}"

        with self._lock:
            count, _ = self._counts.get(key, (0, window))
            count += 1
            self._counts[key] = (count, window)

            # Opportunistic cleanup so this dict doesn't grow
            # unbounded on a long-running process - only runs once the
            # table gets big enough to matter.
            if len(self._counts) > 10000:
                self._counts = {
                    k: v for k, v in self._counts.items() if v[1] >= window - 1
                }

        if count > RATE_LIMIT_PER_MINUTE:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please slow down and try again shortly."},
            )

        return await call_next(request)
