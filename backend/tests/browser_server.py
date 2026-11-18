"""Browser-test harness: short rounds with a test store, never used by Docker."""

import os

from app.config import Settings
from app.main import create_app
from tests.fakes import MemoryStore

humans = int(os.getenv("TEST_HUMANS", "1"))
app = create_app(
    Settings(
        participants=["human"] * humans + ["ai"] * (3 - humans),
        discussion_seconds=8,
        voting_seconds=8,
        feedback_seconds=2,
    ),
    MemoryStore(),
)
