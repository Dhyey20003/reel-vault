import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from reelvault.app import create_app  # noqa: E402
from reelvault.workspace import Workspace  # noqa: E402


@pytest.fixture
def workspace(tmp_path):
    ws = Workspace(tmp_path / "data", workers=1)
    # Disable automatic metadata jobs in tests so results are deterministic.
    ws.db.set_setting("metadata_auto", False)
    yield ws
    ws.close()


@pytest.fixture
def client(workspace, tmp_path):
    app = create_app(tmp_path / "data", port=8765, workspace=workspace)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def token(workspace):
    return workspace.db.pairing_token()


def sync(client, token, captures, device="phone-1"):
    return client.post("/api/sync/captures", json={"device_id": device, "device_name": "Pixel", "captures": captures},
                       headers={"X-ReelVault-Token": token})
