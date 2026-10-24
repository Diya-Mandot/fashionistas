import os
import tempfile

# Isolate tests from the dev DB and from real keys/network.
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["OPENAI_API_KEY"] = ""
os.environ["GOOGLE_VISION_API_KEY"] = ""
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/nonexistent/tests-disable-adc.json"
os.environ["DECISIONS_MODE"] = "mock"
os.environ["AGENTS_MODE"] = "mock"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture()
def client():
    from app.main import app

    with TestClient(app) as c:
        c.post("/api/dev/reset")
        yield c
