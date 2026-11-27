import json
import logging
import logging.config
from datetime import UTC, datetime


class StructuredJsonFormatter(logging.Formatter):
    structured_fields = (
        "request_id",
        "method",
        "path",
        "status_code",
        "duration_ms",
        "dependency",
        "error_type",
    )

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in self.structured_fields:
            value = getattr(record, field, None)
            if value is not None:
                entry[field] = value
        return json.dumps(entry, separators=(",", ":"), ensure_ascii=True)


def configure_logging(level: str) -> None:
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {"json": {"()": StructuredJsonFormatter}},
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "json",
                    "level": level,
                }
            },
            "root": {"handlers": ["console"], "level": level},
        }
    )
