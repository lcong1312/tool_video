from logging.config import dictConfig
from typing import Optional
import logging
import os

class RelativePathFormatter(logging.Formatter):
    def __init__(self, *args, project_root: Optional[str] = None, **kwargs):
        super().__init__(*args, **kwargs)
        # 把项目根目录传进来
        self.project_root = project_root or os.getcwd()

    def format(self, record: logging.LogRecord) -> str:
        # On Windows, os.path.relpath raises ValueError when record.pathname
        # lives on a different drive than project_root (e.g. project on D:
        # but uvicorn/site-packages on C:). When that happens the logger
        # crashes mid-response write and corrupts the HTTP stream — the Go
        # client then sees "unexpected EOF". Fall back to the bare pathname.
        try:
            record.rel_path = os.path.relpath(record.pathname, self.project_root)
        except (ValueError, TypeError):
            record.rel_path = record.pathname or "?"
        return super().format(record)

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "()": RelativePathFormatter,
            "fmt": "%(asctime)s.%(msecs)03d | %(levelname)s | %(name)s | %(rel_path)s:%(lineno)d | %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "default": {
            "formatter": "default",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
        },
    },
    "loggers": {
        "uvicorn": {"handlers": ["default"], "level": "INFO", "propagate": False},
        "uvicorn.error": {"level": "INFO"},
        "uvicorn.access": {"handlers": ["default"], "level": "INFO", "propagate": False},
        "src.utils.logger": {"handlers": ["default"], "level": "INFO", "propagate": False}
    },
}

dictConfig(LOGGING_CONFIG)

logger = logging.getLogger(__name__)
