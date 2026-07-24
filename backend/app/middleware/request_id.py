import logging
import uuid

from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware


# Read by JsonFormatter (app/logging_config.py) via RequestIdLogFilter
# below, so every log line emitted while handling a request - from any
# module, not just the one that received the request - can be tied
# back to that one request.
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdLogFilter(logging.Filter):

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class RequestIdMiddleware(BaseHTTPMiddleware):
    """
    Assigns each request a request ID (reusing an incoming X-Request-ID
    header if the caller already set one, e.g. a reverse proxy),
    exposes it to the logging layer for the duration of the request,
    and echoes it back as a response header - the standard trick for
    tying a user-reported error to the exact log lines it produced.
    """

    async def dispatch(self, request, call_next):

        incoming = request.headers.get("X-Request-ID")
        request_id = incoming or str(uuid.uuid4())

        token = request_id_var.set(request_id)

        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)

        response.headers["X-Request-ID"] = request_id

        return response
