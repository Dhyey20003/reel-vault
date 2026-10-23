import json
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from tests.conftest import sync

FFMPEG = shutil.which("ffmpeg")
REEL = "https://www.instagram.com/reel/V2test123/"


def _idea(client, token, url=REEL):
    return sync(client, token, [{"capture_id": url, "url": url}]).json()["results"][0]["idea_id"]


def make_video(path: Path, seconds=2, audio=True, codec="libx264", ext=None):
    args = [FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc=size=160x120:rate=10:duration={seconds}"]
    if audio:
        args += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}"]
    args += ["-c:v", codec, "-pix_fmt", "yuv420p"]
    if audio:
        args += ["-c:a", "aac"]
    args += [str(path)]
    subprocess.run(args, check=True)
    return path


def make_audio(path: Path):
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-c:a", "aac", str(path)], check=True)
    return path


needs_ffmpeg = pytest.mark.skipif(not FFMPEG, reason="ffmpeg not installed")


@needs_ffmpeg
def test_probe_detects_audio_only_and_valid_video(tmp_path):
    from reelvault.services import media
    ffprobe = shutil.which("ffprobe")
    v = make_video(tmp_path / "v.mp4")
    a = make_audio(tmp_path / "a.m4a")
    assert media.probe(ffprobe, v)["status"] == "ok"
    assert media.probe(ffprobe, a)["status"] == "audio_only"
    assert media.probe(ffprobe, tmp_path / "missing.mp4")["status"] == "invalid"
    (tmp_path / "junk.mp4").write_bytes(b"not a video")
    assert media.probe(ffprobe, tmp_path / "junk.mp4")["status"] == "invalid"
    silent = make_video(tmp_path / "s.mp4", audio=False)
    info = media.probe(ffprobe, silent)
    assert info["status"] == "ok" and info["audio_codec"] is None  # genuinely silent video is still a video


@needs_ffmpeg
def test_download_marks_audio_only_as_failed_and_keeps_file(client, token, workspace, monkeypatch, tmp_path):
    from reelvault.services import downloader
    from reelvault.db import utcnow
    iid = _idea(client, token)
    out = make_audio(tmp_path / "General" / "abc - clip.m4a".replace("abc", iid[:8])) if (tmp_path / "General").mkdir(exist_ok=True) is None else None
    monkeypatch.setattr(downloader, "run_download", lambda **kw: out)
    with workspace.db.tx() as c:
        c.execute("INSERT INTO download_jobs(id, idea_id, status, created_at) VALUES ('j', ?, 'queued', ?)", (iid, utcnow()))
    workspace._run_download("j", iid, workspace.tools())
    i = client.get(f"/api/ideas/{iid}").json()
    assert i["download_status"] == "failed" and i["media_status"] == "audio_only" and "audio-only" in i["download_error"]
    assert Path(i["local_path"]).exists()
    assert i["playable"] is False
    assert client.get(f"/api/media/{iid}").status_code == 409
    rep = client.get("/api/repair").json()
    assert any(x["kind"] == "audio_only" and x["id"] == iid for x in rep["issues"])


@needs_ffmpeg
def test_download_success_validates_prepares_and_streams_with_range(client, token, workspace, monkeypatch, tmp_path):
    from reelvault.services import downloader
    from reelvault.db import utcnow
    iid = _idea(client, token)
    (tmp_path / "General").mkdir()
    out = make_video(tmp_path / "General" / f"{iid[:8]} - clip.mp4")
    monkeypatch.setattr(downloader, "run_download", lambda **kw: out)
    with workspace.db.tx() as c:
        c.execute("INSERT INTO download_jobs(id, idea_id, status, created_at) VALUES ('j', ?, 'queued', ?)", (iid, utcnow()))
    workspace._run_download("j", iid, workspace.tools())
    i = client.get(f"/api/ideas/{iid}").json()
    assert i["download_status"] == "downloaded" and i["media_status"] == "ok" and i["playable"] is True
    assert i["playback_path"] == str(out)  # mp4/h264/aac served as-is, no copy
    assert i["has_thumbnail"] is True  # generated from the video since no remote artwork
    assert client.get(f"/api/ideas/{iid}/cover").status_code == 200
    full = client.get(f"/api/media/{iid}")
    assert full.status_code == 200 and full.headers["content-type"] == "video/mp4"
    part = client.get(f"/api/media/{iid}", headers={"Range": "bytes=0-99"})
    assert part.status_code == 206 and len(part.content) == 100 and part.headers["content-range"].startswith("bytes 0-99/")
    # cover frame selection
    r = client.post(f"/api/ideas/{iid}/cover/frame", json={"t": 1.0})
    assert r.status_code == 200 and r.json()["cover_time"] == 1.0
    # file disappears -> honest state
    out.unlink()
    assert client.post(f"/api/ideas/{iid}/download/verify").json()["exists"] is False
    assert client.get(f"/api/media/{iid}").status_code == 409
    assert client.get(f"/api/ideas/{iid}").json()["playable"] is False


@needs_ffmpeg
def test_non_browser_codec_gets_playback_copy_original_kept(workspace, client, tmp_path):
    src = make_video(tmp_path / "old.avi", codec="mpeg4")
    idea, created = workspace.import_local(src, title="imported")
    assert created and idea["source"] == "local" and idea["media_status"] == "ok"
    assert idea["playback_path"].endswith(f"{idea['id']}.mp4") and Path(idea["local_path"]).suffix == ".avi"
    assert Path(idea["local_path"]).exists() and Path(idea["playback_path"]).exists()
    assert client.get(f"/api/media/{idea['id']}", headers={"Range": "bytes=0-9"}).status_code == 206


@needs_ffmpeg
def test_import_upload_and_dedup(client, tmp_path):
    v = make_video(tmp_path / "clip.mp4")
    r = client.post("/api/ideas/import", files={"file": ("clip.mp4", v.read_bytes(), "video/mp4")})
    assert r.status_code == 201 and r.json()["created"] is True
    r2 = client.post("/api/ideas/import", files={"file": ("clip-copy.mp4", v.read_bytes(), "video/mp4")})
    assert r2.json()["created"] is False and r2.json()["idea"]["id"] == r.json()["idea"]["id"]
    assert client.post("/api/ideas/import", files={"file": ("x.exe", b"MZ", "application/octet-stream")}).status_code == 400


def test_media_route_cannot_serve_arbitrary_files(client, token, workspace, tmp_path):
    iid = _idea(client, token)
    secret = tmp_path / "secret.txt"; secret.write_text("top secret")
    # Even if a row pointed at a non-video path, media_status gate + missing playback blocks it.
    workspace.repo.set_internal(iid, local_path=str(secret), playback_path=str(secret), media_status="invalid")
    assert client.get(f"/api/media/{iid}").status_code == 409
    assert client.get("/api/media/../../etc/passwd").status_code in (404, 409, 422)
    assert client.get("/api/media/doesnotexist").status_code == 404
    assert client.get("/api/attachments/../../../etc/passwd").status_code in (404, 422)


def test_bulk_links(client, token):
    text = "first https://www.instagram.com/reel/AAA111/?igsh=1\nnot a link\nhttps://youtu.be/dQw4w9WgXcQ\nhttps://instagram.com/reels/AAA111\n"
    r = client.post("/api/ideas/bulk", json={"text": text}).json()
    assert [x["result"] for x in r["results"]] == ["created", "invalid", "created", "duplicate"]
    assert r["created"] == 2
    assert client.get("/api/ideas").json()["count"] == 2


def test_tags_notes_and_quick_trip_assign(client, token):
    a = _idea(client, token, "https://instagram.com/reel/T1")
    b = _idea(client, token, "https://instagram.com/reel/T2")
    r = client.put(f"/api/ideas/{a}", json={"fields": {"tags": ["Hook", "lighting", "hook", " "]}})
    assert r.json()["tags"] == ["hook", "lighting"]
    assert client.put(f"/api/ideas/{a}", json={"fields": {"tags": "nope"}}).status_code == 400
    assert client.get("/api/ideas?tag=hook").json()["count"] == 1
    assert client.get("/api/tags").json()["tags"][0] == {"tag": "hook", "count": 1}
    n = client.post(f"/api/ideas/{a}/notes", json={"t": 12.5, "text": "whip pan here"})
    assert n.status_code == 201
    client.put(f"/api/notes/{n.json()['id']}", json={"text": "whip pan starts"})
    notes = client.get(f"/api/ideas/{a}").json()["timed_notes"]
    assert notes[0]["t"] == 12.5 and notes[0]["text"] == "whip pan starts"
    client.delete(f"/api/notes/{n.json()['id']}")
    assert client.get(f"/api/ideas/{a}").json()["timed_notes"] == []
    r = client.post("/api/trips/add-ideas", json={"idea_ids": [a, b], "new_trip_name": "Goa"}).json()
    assert r["added"] == 2
    tid = r["trip_id"]
    assert client.post("/api/trips/add-ideas", json={"idea_ids": [a], "trip_id": tid}).json()["added"] == 0
    assert client.get("/api/trips-recent").json()[0]["id"] == tid
    assert client.get(f"/api/ideas?trip_id={tid}").json()["count"] == 2
    client.delete(f"/api/trips/{tid}/ideas/{b}")
    assert client.get(f"/api/ideas?trip_id={tid}").json()["count"] == 1
    assert client.get(f"/api/ideas/{a}").json()["trips"][0]["name"] == "Goa"  # many-to-many kept
    client.put(f"/api/ideas/{a}", json={"fields": {"loop_start": 1.5, "loop_end": 4.0}})
    assert client.get(f"/api/ideas/{a}").json()["loop_end"] == 4.0


def test_manual_edits_survive_metadata_refresh(client, token, workspace, monkeypatch):
    from reelvault.services import metadata as m
    iid = _idea(client, token)
    client.put(f"/api/ideas/{iid}", json={"fields": {"title": "my title", "notes": "my note"}})
    monkeypatch.setattr(m, "fetch_metadata", lambda url, providers: (m.Metadata(title="remote", caption="cap", provider="fake"), []))
    workspace._fetch_metadata(iid)
    workspace._fetch_metadata(iid)
    i = client.get(f"/api/ideas/{iid}").json()
    assert i["title"] == "my title" and i["notes"] == "my note" and i["caption"] == "cap"


def test_pipeline_resume_after_restart(client, token, workspace, monkeypatch):
    from reelvault.db import utcnow
    iid = _idea(client, token)
    workspace.repo.set_internal(iid, download_status="downloading", pipeline_stage="downloading")
    with workspace.db.tx() as c:
        c.execute("INSERT INTO download_jobs(id, idea_id, status, created_at) VALUES ('j', ?, 'downloading', ?)", (iid, utcnow()))
    queued = []
    monkeypatch.setattr(workspace, "queue_download", lambda i, from_pipeline=False: (queued.append(i) or {"ok": True}))
    r = workspace.resume_pipeline()
    assert r["download"] == 1 and queued == [iid]
    assert workspace.jobs_for(iid)["download"]["status"] == "failed"
    workspace.db.set_setting("pipeline_paused", True)
    assert workspace.resume_pipeline() == {"download": 0, "analysis": 0, "metadata": 0}
    st = client.get("/api/pipeline").json()
    assert st["paused"] is True
    client.post("/api/pipeline/resume")
    assert client.get("/api/pipeline").json()["paused"] is False


def test_pipeline_auto_download_requires_tool_and_disk(client, token, workspace, monkeypatch):
    client.put("/api/settings", json={"values": {"auto_download": True, "min_free_gb": 999999}})
    iid = _idea(client, token, "https://instagram.com/reel/DISK")
    i = client.get(f"/api/ideas/{iid}").json()
    assert i["download_status"] == "not_downloaded"  # refused (no yt-dlp here and/or disk guard), never crashes sync


def test_analysis_cache_key_and_cancel(client, token, workspace):
    iid = _idea(client, token)
    idea = workspace.repo.idea(iid)
    k1 = workspace.analysis_cache_key(idea, "m", "ollama")
    client.put(f"/api/ideas/{iid}", json={"fields": {"notes": "changed"}})
    k2 = workspace.analysis_cache_key(workspace.repo.idea(iid), "m", "ollama")
    assert k1 != k2
    from reelvault.db import utcnow
    with workspace.db.tx() as c:
        c.execute("INSERT INTO analysis_jobs(id, idea_id, status, provider, model, created_at) VALUES ('a1', ?, 'queued', 'ollama', 'm', ?)", (iid, utcnow()))
    assert client.post(f"/api/ideas/{iid}/analyze/cancel").json()["cancelled"] is True


def test_local_ai_status_and_test_fail_gracefully(client):
    client.put("/api/settings", json={"values": {"ollama_url": "http://127.0.0.1:9"}})
    s = client.get("/api/ai/local").json()
    assert s["status"]["local"] is True and s["status"]["configured"] is False and s["recommended"]["name"]
    assert s["hardware"]["ram_gb"] is None or s["hardware"]["ram_gb"] > 0
    t = client.post("/api/ai/local/test").json()
    assert t["ok"] is False and "not reachable" in t["error"]
    # public endpoints are refused
    client.put("/api/settings", json={"values": {"ollama_url": "http://8.8.8.8:11434"}})
    assert "private network" in client.post("/api/ai/local/test").json()["error"]


def test_ollama_provider_parses_and_never_calls_external_hosts(monkeypatch, tmp_path):
    from reelvault.services import local_ai
    from reelvault.services.analysis import AnalysisInputs, NotConfigured
    calls = []

    class FakeResp:
        def __init__(self, body): self.body = body
        def read(self): return json.dumps(self.body).encode()
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake_urlopen(req, timeout=0):
        calls.append(req.full_url)
        body = json.loads(req.data)
        assert "images" not in body["messages"][1] or len(body["messages"][1]["images"]) == 1
        return FakeResp({"message": {"content": json.dumps({"core_idea": "x", "observed_facts": ["frame 1 shows a lake"], "shot_list": [{"shot": "wide"}]})}})
    monkeypatch.setattr(local_ai.urllib.request, "urlopen", fake_urlopen)
    frame = tmp_path / "f.jpg"; frame.write_bytes(b"\xff\xd8\xff\xd9")
    p = local_ai.OllamaProvider("http://127.0.0.1:11434")
    brief, usage = p.analyze(AnalysisInputs(url="u", frames=[frame], frame_times=[0.5]), "qwen2.5vl:7b")
    assert brief.core_idea == "x" and usage["images"] == 1
    assert all(u.startswith("http://127.0.0.1:11434/") for u in calls)
    with pytest.raises(NotConfigured):
        local_ai.OllamaProvider("http://example.com:11434")


def test_diagnostics_redact_secrets(client, token, workspace):
    workspace.db.set_setting("instagram_oembed_token", "SECRET-TOKEN-123")
    tok = workspace.db.pairing_token()
    text = client.get("/api/diagnostics").text
    assert "SECRET-TOKEN-123" not in text and tok not in text and "pairing_token" not in text
    assert client.get("/api/settings").text.find(tok) == -1


def test_pairing_reports_warnings_and_candidates(client):
    p = client.get("/api/pairing").json()
    assert "candidates" in p and any("LAN access is OFF" in w for w in p["warnings"])
    assert p["uri"].startswith("reelvault://pair?host=") and "&port=" in p["uri"] and "&token=" in p["uri"]
    client.put("/api/settings", json={"values": {"advertised_host": "192.168.50.7"}})
    p = client.get("/api/pairing").json()
    assert p["host"] == "192.168.50.7" and "host=192.168.50.7" in p["uri"]


@pytest.mark.parametrize("raw, expected", [
    ("https://www.youtube.com/watch?v=abc123XYZ&t=10s", "https://youtube.com/watch?v=abc123XYZ"),
    ("https://m.youtube.com/shorts/sh0rtID?feature=share", "https://youtube.com/shorts/sh0rtID"),
    ("https://youtube.com/shorts/sh0rtID/", "https://youtube.com/shorts/sh0rtID"),
    ("https://www.instagram.com/reels/C9x/?utm_source=ig_web_button_share_sheet&igsh=abc", "https://instagram.com/reel/C9x"),
    ("https://www.instagram.com/tv/ABC/", "https://instagram.com/tv/ABC"),
])
def test_more_url_variants(raw, expected):
    from reelvault.urlnorm import normalize_url
    assert normalize_url(raw) == expected


def test_trip_plan_requires_provider_and_validates(client, token, workspace, monkeypatch):
    iid = _idea(client, token)
    t = client.post("/api/trips", json={"name": "Spiti"}).json()
    client.put("/api/settings", json={"values": {"ollama_url": "http://127.0.0.1:9"}})
    r = client.post(f"/api/trips/{t['id']}/adapt", json={"idea_ids": [iid], "destination": "Spiti", "gear": "phone"}).json()
    assert r["ok"] is True
    for _ in range(50):
        plans = client.get(f"/api/trips/{t['id']}/plans").json()
        if plans and plans[0]["status"] == "failed":
            break
        time.sleep(0.1)
    assert plans[0]["status"] == "failed" and "not reachable" in plans[0]["error"]
    good = {"proposed_shots": [{"shot": "sunrise wide"}], "recreation_plan": "go early"}
    assert client.put(f"/api/plans/{plans[0]['id']}", json={"plan": good}).status_code == 200
    assert client.put(f"/api/plans/{plans[0]['id']}", json={"plan": {"proposed_shots": "x"}}).status_code == 400
