from __future__ import annotations

import logging

from app.config.logging import configure_logging
from app.config.settings import get_settings


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    logging.getLogger(__name__).info("weekly job scaffold is ready")


if __name__ == "__main__":
    main()
