from tests.conftest import sync

REEL = "https://www.instagram.com/reel/AbCdEf123/"


def _idea(client, token, url=REEL):
    r = sync(client, token, [{"capture_id": url, "url": url}])
    return r.json()["results"][0]["idea_id"]


def test_edit_persists(client, token):
    iid = _idea(client, token)
    cat = client.get("/api/categories").json()[0]
    r = client.put(f"/api/ideas/{iid}", json={"fields": {"title": "Sunset timelapse", "notes": "shoot at 6pm", "priority": "High",
                                                        "status": "In Progress", "category_id": cat["id"], "follow_up_date": "2026-01-01"}})
    assert r.status_code == 200, r.text
    i = client.get(f"/api/ideas/{iid}").json()
    assert i["title"] == "Sunset timelapse" and i["priority"] == "High" and i["status"] == "In Progress"
    assert i["category_name"] == cat["name"]
    assert client.put(f"/api/ideas/{iid}", json={"fields": {"status": "Done"}}).status_code == 400
    assert client.put(f"/api/ideas/{iid}", json={"fields": {"finished_video_url": "ftp://x"}}).status_code == 400


def test_conflict_detection(client, token):
    iid = _idea(client, token)
    stale = client.get(f"/api/ideas/{iid}").json()["updated_at"]
    client.put(f"/api/ideas/{iid}", json={"fields": {"title": "first"}})
    r = client.put(f"/api/ideas/{iid}", json={"fields": {"title": "second"}, "expected_updated_at": stale})
    assert r.status_code == 409


def test_search_and_filters(client, token):
    a = _idea(client, token, "https://instagram.com/reel/AAA")
    b = _idea(client, token, "https://instagram.com/reel/BBB")
    client.put(f"/api/ideas/{a}", json={"fields": {"title": "Udaipur lake drone", "priority": "High"}})
    client.put(f"/api/ideas/{b}", json={"fields": {"creator": "mountainguy", "status": "Published"}})
    assert client.get("/api/ideas?q=udaipur").json()["count"] == 1
    assert client.get("/api/ideas?q=mountain").json()["count"] == 1
    assert client.get("/api/ideas?priority=High").json()["count"] == 1
    assert client.get("/api/ideas?status=Published").json()["items"][0]["id"] == b
    assert client.get("/api/ideas?download_status=downloaded").json()["count"] == 0
    assert client.get("/api/ideas?download_status=not_downloaded").json()["count"] == 2


def test_trips_assign_and_inbox_semantics(client, token):
    iid = _idea(client, token)
    t = client.post("/api/trips", json={"name": "Kedarnath", "location": "Uttarakhand"}).json()
    assert client.get("/api/ideas?inbox=true").json()["count"] == 1
    r = client.put(f"/api/ideas/{iid}/trips", json={"trip_ids": [t["id"]]})
    assert [x["name"] for x in r.json()["trips"]] == ["Kedarnath"]
    assert client.get("/api/ideas?inbox=true").json()["count"] == 0
    assert client.get(f"/api/ideas?trip_id={t['id']}").json()["count"] == 1
    t2 = client.post("/api/trips", json={"name": "Tungnath"}).json()
    r = client.put(f"/api/ideas/{iid}/trips", json={"trip_ids": [t["id"], t2["id"]]})
    assert len(r.json()["trips"]) == 2
    client.put(f"/api/trips/{t['id']}", json={"fields": {"archived": True, "checklist": [{"text": "charge batteries", "done": False}]}})
    assert client.get(f"/api/trips/{t['id']}").json()["checklist"][0]["text"] == "charge batteries"
    assert len(client.get("/api/trips").json()) == 1
    client.delete(f"/api/trips/{t2['id']}")
    client.delete(f"/api/trips/{t['id']}")
    assert client.get("/api/ideas?inbox=true").json()["count"] == 1  # idea survives trip deletion


def test_trip_suggestions_never_assign(client, token):
    iid = _idea(client, token)
    client.put(f"/api/ideas/{iid}", json={"fields": {"notes": "would be great in Udaipur"}})
    t = client.post("/api/trips", json={"name": "Udaipur"}).json()
    s = client.get(f"/api/trips/{t['id']}/suggestions").json()
    assert [x["id"] for x in s] == [iid]
    assert client.get(f"/api/ideas/{iid}").json()["trips"] == []


def test_categories_crud(client):
    c = client.post("/api/categories", json={"name": "Drone"}).json()
    assert client.post("/api/categories", json={"name": "drone"}).json()["id"] == c["id"]
    assert client.put(f"/api/categories/{c['id']}", json={"name": "Aerial"}).json()["name"] == "Aerial"
    travel = next(x for x in client.get("/api/categories").json() if x["name"] == "Travel")
    r = client.delete(f"/api/categories/{c['id']}?reassign_to={travel['id']}")
    assert r.json()["ok"]


def test_metadata_failure_keeps_link_and_allows_manual_title(client, token, workspace):
    iid = _idea(client, token)
    workspace._fetch_metadata(iid)  # no yt-dlp, no oEmbed for Instagram without token -> unavailable
    i = client.get(f"/api/ideas/{iid}").json()
    assert i["metadata_status"] == "unavailable"
    assert "not applicable" in i["metadata_error"]
    assert i["original_url"] == REEL
    client.put(f"/api/ideas/{iid}", json={"fields": {"title": "manual title"}})
    assert client.get(f"/api/ideas/{iid}").json()["title"] == "manual title"
    assert client.post(f"/api/ideas/{iid}/metadata/retry").json()["queued"] in (True, False)


def test_metadata_does_not_overwrite_user_edits(client, token, workspace, monkeypatch):
    from reelvault.services import metadata as m
    iid = _idea(client, token)
    client.put(f"/api/ideas/{iid}", json={"fields": {"title": "mine"}})
    monkeypatch.setattr(m, "fetch_metadata", lambda url, providers: (m.Metadata(title="theirs", creator="creator1", provider="fake"), []))
    workspace._fetch_metadata(iid)
    i = client.get(f"/api/ideas/{iid}").json()
    assert i["title"] == "mine" and i["creator"] == "creator1" and i["metadata_status"] == "ok"


def test_download_requires_ytdlp(client, token, workspace, monkeypatch):
    iid = _idea(client, token)
    monkeypatch.setattr(workspace, "tools", lambda: {"ytdlp": {"found": False, "path": None, "install_hint": "install it"}, "ffmpeg": {"found": False, "path": None}, "ffprobe": {"found": False, "path": None}})
    r = client.post(f"/api/ideas/{iid}/download").json()
    assert r["ok"] is False and "yt-dlp" in r["error"]
    assert client.get(f"/api/ideas/{iid}").json()["download_status"] == "not_downloaded"


def test_download_state_machine_success_and_failure(client, token, workspace, monkeypatch, tmp_path):
    from reelvault.services import downloader
    iid = _idea(client, token)
    fake_tools = {"ytdlp": {"found": True, "path": "/fake/yt-dlp"}, "ffmpeg": {"found": False, "path": None}, "ffprobe": {"found": False, "path": None}}
    out = tmp_path / "General" / "abc - clip.mp4"

    def fake_run(**kw):
        kw["on_progress"](50.0, "[download]  50.0%")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"video")
        return out
    monkeypatch.setattr(downloader, "run_download", fake_run)
    # Run the real job body synchronously:
    from reelvault.db import utcnow
    with workspace.db.tx() as conn:
        conn.execute("INSERT INTO download_jobs(id, idea_id, status, created_at) VALUES ('job1', ?, 'queued', ?)", (iid, utcnow()))
    workspace._run_download("job1", iid, fake_tools)
    i = client.get(f"/api/ideas/{iid}").json()
    assert i["download_status"] == "downloaded" and i["local_path"] == str(out)
    assert i["jobs"]["download"]["status"] == "downloaded" and i["jobs"]["download"]["progress"] == 100.0
    assert client.post(f"/api/ideas/{iid}/download/verify").json()["exists"] is True
    # file vanishes -> verify resets state honestly
    out.unlink()
    assert client.post(f"/api/ideas/{iid}/download/verify").json()["exists"] is False
    assert client.get(f"/api/ideas/{iid}").json()["download_status"] == "not_downloaded"

    def failing(**kw):
        raise downloader.DownloadError("ERROR: unsupported URL")
    monkeypatch.setattr(downloader, "run_download", failing)
    with workspace.db.tx() as conn:
        conn.execute("INSERT INTO download_jobs(id, idea_id, status, created_at) VALUES ('job2', ?, 'queued', ?)", (iid, utcnow()))
    workspace._run_download("job2", iid, fake_tools)
    i = client.get(f"/api/ideas/{iid}").json()
    assert i["download_status"] == "failed" and "unsupported" in i["download_error"]
    assert i["original_url"] == REEL


def test_download_never_marks_missing_file(monkeypatch, tmp_path):
    from reelvault.services import downloader
    import subprocess

    class P:
        returncode = 0
        def __init__(self):
            self.stdout = iter(["[download] 100%\n"])
        def wait(self, timeout=None): return 0
        def kill(self): pass
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: P())
    try:
        downloader.run_download(ytdlp_path="x", ffmpeg_path=None, url="https://a.b/c", target_dir=tmp_path, idea_id="abcdefgh")
    except downloader.DownloadError as e:
        assert "no output file" in str(e)
    else:
        raise AssertionError("must fail when no file exists")


def test_analysis_requires_key_and_validates_edits(client, token, monkeypatch):
    monkeypatch.delenv("REELVAULT_AI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    iid = _idea(client, token)
    # Local provider (default) with Ollama unreachable at a closed port: queued job fails gracefully, no external call.
    client.put("/api/settings", json={"values": {"ollama_url": "http://127.0.0.1:9"}})
    r = client.post(f"/api/ideas/{iid}/analyze").json()
    assert r["ok"] is True
    import time
    for _ in range(50):
        st = client.get(f"/api/ideas/{iid}").json()
        if st["analysis_status"] == "failed":
            break
        time.sleep(0.1)
    assert st["analysis_status"] == "failed" and "not reachable" in st["analysis_error"]
    # Cloud provider is opt-in: without opt-in it is refused even if a key were present.
    client.put("/api/settings", json={"values": {"ai_provider": "anthropic"}})
    r = client.post(f"/api/ideas/{iid}/analyze").json()
    assert r["ok"] is False and r["configured"] is False and "opt-in" in r["error"]
    client.put("/api/settings", json={"values": {"cloud_ai_opt_in": True}})
    r = client.post(f"/api/ideas/{iid}/analyze").json()
    assert r["ok"] is False and "REELVAULT_AI_API_KEY" in r["error"]
    client.put("/api/settings", json={"values": {"ai_provider": "ollama", "cloud_ai_opt_in": False}})
    good = {"core_idea": "x", "shot_list": [{"shot": "wide", "duration_seconds": 2}], "observed_facts": ["caption mentions lake"]}
    r = client.put(f"/api/ideas/{iid}/analysis", json={"brief": good})
    assert r.status_code == 200 and r.json()["analysis"]["edited"] is True
    assert client.put(f"/api/ideas/{iid}/analysis", json={"brief": {"shot_list": "nope"}}).status_code == 400
    md = client.get(f"/api/ideas/{iid}/analysis.md").text
    assert "Observed facts" in md and "wide" in md


def test_analysis_job_success_and_failure(client, token, workspace, monkeypatch):
    from reelvault.services import analysis as a
    iid = _idea(client, token)

    class Fake:
        name = "fake"
        def __init__(self, fail): self.fail = fail
        def analyze(self, inputs, model):
            if self.fail:
                raise a.AnalysisError("provider down")
            return a.CreativeBrief(core_idea="recreate", opening_hook="hook", shot_list=[a.Shot(shot="s1")]), {"input_tokens": 1}
    from reelvault.db import utcnow
    with workspace.db.tx() as conn:
        conn.execute("INSERT INTO analysis_jobs(id, idea_id, status, provider, model, created_at) VALUES ('j1', ?, 'queued', 'fake', 'm', ?)", (iid, utcnow()))
    workspace._run_analysis("j1", iid, Fake(fail=True), "fake", "m", "k1")
    i = client.get(f"/api/ideas/{iid}").json()
    assert i["analysis_status"] == "failed" and i["analysis_error"] == "provider down"
    with workspace.db.tx() as conn:
        conn.execute("INSERT INTO analysis_jobs(id, idea_id, status, provider, model, created_at) VALUES ('j2', ?, 'queued', 'fake', 'm', ?)", (iid, utcnow()))
    workspace._run_analysis("j2", iid, Fake(fail=False), "fake", "m", "k1")
    i = client.get(f"/api/ideas/{iid}").json()
    assert i["analysis_status"] == "done"
    assert i["analysis"]["brief"]["core_idea"] == "recreate"
    assert i["analysis"]["inputs"]["video_watched"] is False and i["analysis"]["inputs"]["frames"] == 0


def test_parse_brief_rejects_bad_json():
    from reelvault.services.analysis import AnalysisError, parse_brief
    import pytest
    with pytest.raises(AnalysisError):
        parse_brief("not json")
    b = parse_brief('```json\n{"core_idea": "a"}\n```')
    assert b.core_idea == "a"


def test_exports(client, token, workspace, tmp_path):
    iid = _idea(client, token)
    client.put(f"/api/ideas/{iid}", json={"fields": {"title": "Lake shot", "shooting_notes": "golden hour"}})
    ref = tmp_path / "ref.mp4"; ref.write_bytes(b"x")
    workspace.repo.set_internal(iid, download_status="downloaded", local_path=str(ref))
    t = client.post("/api/trips", json={"name": "Udaipur"}).json()
    client.put(f"/api/ideas/{iid}/trips", json={"trip_ids": [t["id"]]})
    md = client.post("/api/exports/shotlist", json={"idea_ids": [iid], "format": "md"}).text
    assert "## Lake shot" in md and "golden hour" in md
    txt = client.post("/api/exports/shotlist", json={"idea_ids": [iid], "format": "txt"}).text
    assert "##" not in txt and "Lake shot" in txt
    r = client.post(f"/api/trips/{t['id']}/export").json()
    from pathlib import Path
    folder = Path(r["folder"])
    assert (folder / "trip.md").exists() and (folder / "shotlist.md").exists() and (folder / "trip.json").exists()
    assert (folder / "references" / "ref.mp4").exists()
    assert ref.exists()  # original never moved


def test_reminders(client, token, workspace):
    iid = _idea(client, token)
    client.put(f"/api/ideas/{iid}", json={"fields": {"priority": "High", "follow_up_date": "2000-01-01"}})
    assert client.get("/api/reminders/due").json() == {"enabled": False, "due": []}
    client.put("/api/settings", json={"values": {"reminders_enabled": True}})
    due = client.get("/api/reminders/due").json()["due"]
    assert [d["id"] for d in due] == [iid]
    client.post("/api/reminders/ack", json={"idea_ids": [iid]})
    assert client.get("/api/reminders/due").json()["due"] == []  # unchanged item is not re-reminded
    client.put(f"/api/ideas/{iid}", json={"fields": {"priority": "Normal"}})
    assert client.get("/api/reminders/due").json()["due"] == []


def test_settings_and_pairing(client):
    s = client.get("/api/settings").json()["settings"]
    assert s["lan_enabled"] is False and "pairing_token" not in s
    assert client.put("/api/settings", json={"values": {"port": 80}}).status_code == 400
    assert client.put("/api/settings", json={"values": {"bogus": 1}}).status_code == 400
    r = client.put("/api/settings", json={"values": {"lan_enabled": True, "priorities": ["Low", "Normal", "High", "Urgent"]}})
    assert r.json()["settings"]["lan_enabled"] is True
    p = client.get("/api/pairing").json()
    assert p["uri"].startswith("reelvault://pair?host=") and "<svg" in p["qr_svg"]
    new = client.post("/api/pairing/rotate").json()
    assert new["token"] != p["token"]
    assert client.get("/api/status").json()["counts"]["all"] == 0


def test_index_and_static_served(client):
    assert client.get("/").status_code == 200 and "ReelVault" in client.get("/").text
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/health").json()["ok"]


def test_attachment_upload(client, token):
    iid = _idea(client, token)
    r = client.post(f"/api/ideas/{iid}/attachments", files={"file": ("shot.png", b"\x89PNG....", "image/png")})
    assert r.status_code == 201
    att = r.json()
    assert client.get(f"/api/attachments/{att['id']}").status_code == 200
    assert client.post(f"/api/ideas/{iid}/attachments", files={"file": ("x.exe", b"MZ", "application/octet-stream")}).status_code == 400
    assert client.delete(f"/api/attachments/{att['id']}").json()["ok"]


def test_backup(client, token):
    _idea(client, token)
    r = client.post("/api/backup").json()
    from pathlib import Path
    assert Path(r["path"]).stat().st_size > 0
