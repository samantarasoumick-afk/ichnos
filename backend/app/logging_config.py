import json
import logging
import os
import sys

from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    """
    Minimal structured logging - one JSON object per line, no
    third-party dependency. Deliberately small: timestamp, level,
    logger name, message, request_id (when available, see
    app/middleware/request_id.py), and exception info if any.
    """

    def format(self, record: logging.LogRecord) -> str:

        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        request_id = getattr(record, "request_id", None)
        if request_id and request_id != "-":
            payload["request_id"] = request_id

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload)


def configure_logging() -> None:

    from app.middleware.request_id import RequestIdLogFilter

    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RequestIdLogFilter())

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(level)

    # uvicorn's own loggers install their own handlers by default,
    # which would otherwise print a second, differently-formatted copy
    # of every request line - route them through the same JSON handler
    # instead.
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(logger_name)
        uvicorn_logger.handlers = [handler]
        uvicorn_logger.propagate = False
