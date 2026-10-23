from tests.conftest import sync

REEL = "https://www.instagram.com/reel/Cx1Yz2Ab3/?igsh=MTIzNDU2"


def test_token_required(client):
    r = client.post("/api/sync/captures", json={"device_id": "d", "captures": []})
    assert r.status_code == 401
    r = client.post("/api/sync/captures", json={"device_id": "d", "captures": []}, headers={"X-ReelVault-Token": "wrong"})
    assert r.status_code == 401
    r = client.get("/api/sync/ping", headers={"X-ReelVault-Token": "wrong"})
    assert r.status_code == 401


def test_ping(client, token):
    r = client.get("/api/sync/ping", headers={"X-ReelVault-Token": token})
    assert r.status_code == 200 and r.json()["ok"] and r.json()["app"] == "ReelVault"


def test_capture_creates_idea_in_inbox(client, token):
    r = sync(client, token, [{"capture_id": "cap-1", "shared_text": f"Look at this {REEL}", "captured_at": "2026-10-20T10:00:00Z"}])
    assert r.status_code == 200
    res = r.json()["results"][0]
    assert res["result"] == "created"
    inbox = client.get("/api/ideas?inbox=true").json()
    assert inbox["count"] == 1
    idea = inbox["items"][0]
    assert idea["original_url"] == REEL
    assert idea["normalized_url"] == "https://instagram.com/reel/Cx1Yz2Ab3"
    assert idea["captured_at"] == "2026-10-20T10:00:00Z"
    assert idea["source"] == "android"
    assert idea["status"] == "To Make"
    assert idea["metadata_status"] == "pending"


def test_dedup_by_normalized_url_and_capture_replay(client, token):
    r1 = sync(client, token, [{"capture_id": "a", "url": REEL}])
    r2 = sync(client, token, [{"capture_id": "b", "url": "https://instagram.com/reels/Cx1Yz2Ab3"}])
    r3 = sync(client, token, [{"capture_id": "a", "url": REEL}])  # same capture retried after lost response
    assert r1.json()["results"][0]["result"] == "created"
    assert r2.json()["results"][0]["result"] == "duplicate"
    assert r2.json()["results"][0]["idea_id"] == r1.json()["results"][0]["idea_id"]
    assert r3.json()["results"][0]["replayed"] is True
    assert r3.json()["results"][0]["result"] == "created"
    assert client.get("/api/ideas").json()["count"] == 1


def test_invalid_capture_does_not_break_batch(client, token):
    r = sync(client, token, [{"capture_id": "x", "shared_text": "no link at all"},
                             {"capture_id": "y", "shared_text": "javascript:alert(1)"},
                             {"capture_id": "z", "url": REEL}])
    results = {x["capture_id"]: x["result"] for x in r.json()["results"]}
    assert results == {"x": "invalid", "y": "invalid", "z": "created"}


def test_intentional_duplicate_from_pc(client, token):
    sync(client, token, [{"capture_id": "a", "url": REEL}])
    r = client.post("/api/ideas", json={"url": REEL})
    assert r.json()["created"] is False
    r = client.post("/api/ideas", json={"url": REEL, "allow_duplicate": True})
    assert r.json()["created"] is True
    assert r.json()["idea"]["duplicate_of"]
    assert client.get("/api/ideas").json()["count"] == 2


def test_devices_recorded(client, token):
    sync(client, token, [{"capture_id": "a", "url": REEL}])
    d = client.get("/api/devices").json()
    assert d[0]["device_id"] == "phone-1" and d[0]["captures_received"] == 1


def test_non_private_client_rejected(workspace, tmp_path):
    from reelvault.netutil import is_private_client
    assert is_private_client("127.0.0.1") and is_private_client("192.168.1.20") and is_private_client("10.0.0.5")
    assert is_private_client("172.16.4.4") and is_private_client("::1") and is_private_client("100.64.1.1")
    assert not is_private_client("8.8.8.8") and not is_private_client("2001:4860::8888")
