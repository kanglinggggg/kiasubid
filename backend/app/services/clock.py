from datetime import UTC, datetime

from app.config import settings
from app.demo.seed import DEMO_NOW


def now() -> datetime:
    """Keep the synthetic hackathon story stable while allowing real-time operation later."""
    return DEMO_NOW if settings.demo_mode else datetime.now(UTC).replace(tzinfo=None)
