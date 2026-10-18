"""A rerun must keep the map that is already there.

Rerunning a conversion rewrites the dataset's protocol (and may rewrite its profile) even when the new conversion fails, and the viewer
reads those files. Without a guard, a failed rerun would leave the viewer pointing at a broken new archive while the good old one sat
unused next to it. The rerun therefore snapshots both files when the conversion starts and puts them back unless the job completes.

It also refuses to start when the source file no longer exists (sources were once deleted after every conversion), before anything is
touched, instead of queueing a job that is bound to fail.
"""

import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import src.api as api

OLD_PROTOCOL = b'{"dataset": {"name": "demo"}, "outputs": {"mvt": "demo_mvt.pmtiles"}}'
NEW_PROTOCOL = b'{"dataset": {"name": "demo"}, "outputs": {"mvt": "demo_mvt_1.pmtiles", "broken": true}}'
OLD_PROFILE = b"dataset:\n  id: demo\n"


def _job(name="demo"):
    return {
        "name": name, "url": "/data/sources/demo/demo.zip", "status": "queued", "stage": "queued", "progress": [],
        "created_at": "2026-10-01T00:00:00Z", "updated_at": "2026-10-01T00:00:00Z", "error": None,
        "cancel_requested": False, "cancel_event": threading.Event(),
    }


def _setup(tmp_path, monkeypatch):
    protocols, profiles = tmp_path / "protocols", tmp_path / "profiles"
    protocols.mkdir()
    profiles.mkdir()
    monkeypatch.setattr(api, "PROTOCOLS_DIR", protocols)
    monkeypatch.setattr(api, "PROFILES_DIR", profiles)
    (protocols / "demo.json").write_bytes(OLD_PROTOCOL)
    (profiles / "demo.yaml").write_bytes(OLD_PROFILE)
    api._jobs.clear()
    return protocols / "demo.json", profiles / "demo.yaml"


def _pipeline_that_rewrites_files(protocol, profile, result):
    """What the real pipeline does on any run: rewrite the protocol and profile, then report how it went."""
    def run(**_kwargs):
        protocol.write_bytes(NEW_PROTOCOL)
        profile.write_bytes(b"dataset:\n  id: rewritten\n")
        return result
    return run


# ── the rerun keeps the current map ─────────────────────────────────────────────────────────────────────────────────────────────

def test_a_failed_rerun_puts_the_previous_protocol_and_profile_back(tmp_path, monkeypatch):
    protocol, profile = _setup(tmp_path, monkeypatch)
    api._store_job(_job())
    monkeypatch.setattr(api, "run_conversion_pipeline", _pipeline_that_rewrites_files(protocol, profile, {"status": "failed", "conversions": {}}))

    api._run_import_job("demo", "/data/sources/demo/demo.zip", threading.Event(), True)

    assert api._get_job("demo")["status"] == "failed"
    assert protocol.read_bytes() == OLD_PROTOCOL
    assert profile.read_bytes() == OLD_PROFILE
    assert any(step["stage"] == "restored" for step in api._get_job("demo")["progress"])


def test_a_pipeline_that_raises_also_restores(tmp_path, monkeypatch):
    protocol, profile = _setup(tmp_path, monkeypatch)
    api._store_job(_job())

    def explode(**_kwargs):
        protocol.write_bytes(NEW_PROTOCOL)
        raise RuntimeError("planetiler died")

    monkeypatch.setattr(api, "run_conversion_pipeline", explode)

    api._run_import_job("demo", "/data/sources/demo/demo.zip", threading.Event(), True)

    assert api._get_job("demo")["status"] == "failed"
    assert protocol.read_bytes() == OLD_PROTOCOL


def test_a_cancelled_rerun_restores(tmp_path, monkeypatch):
    protocol, profile = _setup(tmp_path, monkeypatch)
    api._store_job(_job())
    monkeypatch.setattr(api, "run_conversion_pipeline", _pipeline_that_rewrites_files(protocol, profile, {"status": "canceled"}))

    api._run_import_job("demo", "/data/sources/demo/demo.zip", threading.Event(), True)

    assert api._get_job("demo")["status"] == "canceled"
    assert protocol.read_bytes() == OLD_PROTOCOL
    assert profile.read_bytes() == OLD_PROFILE


def test_a_profile_created_by_a_failed_rerun_is_removed(tmp_path, monkeypatch):
    protocol, profile = _setup(tmp_path, monkeypatch)
    profile.unlink()                                  # the dataset had no saved profile before the rerun
    api._store_job(_job())
    monkeypatch.setattr(api, "run_conversion_pipeline", _pipeline_that_rewrites_files(protocol, profile, {"status": "failed", "conversions": {}}))

    api._run_import_job("demo", "/data/sources/demo/demo.zip", threading.Event(), True)

    assert not profile.exists()


def test_a_completed_rerun_keeps_the_new_files(tmp_path, monkeypatch):
    protocol, profile = _setup(tmp_path, monkeypatch)
    api._store_job(_job())
    monkeypatch.setattr(api, "run_conversion_pipeline", _pipeline_that_rewrites_files(protocol, profile, {"status": "completed"}))

    api._run_import_job("demo", "/data/sources/demo/demo.zip", threading.Event(), True)

    assert api._get_job("demo")["status"] == "completed"
    assert protocol.read_bytes() == NEW_PROTOCOL
    assert not any(step["stage"] == "restored" for step in api._get_job("demo")["progress"])


def test_an_ordinary_import_is_not_rolled_back(tmp_path, monkeypatch):
    protocol, profile = _setup(tmp_path, monkeypatch)
    api._store_job(_job())
    monkeypatch.setattr(api, "run_conversion_pipeline", _pipeline_that_rewrites_files(protocol, profile, {"status": "failed", "conversions": {}}))

    api._run_import_job("demo", "/data/sources/demo/demo.zip", threading.Event())     # keep_existing defaults to off

    assert protocol.read_bytes() == NEW_PROTOCOL


# ── the endpoint ────────────────────────────────────────────────────────────────────────────────────────────────────────────────

def _post(name="demo"):
    return api.app.test_client().post(f"/api/datasets/{name}/reconvert")


def test_reconvert_refuses_a_missing_source_before_touching_anything(tmp_path, monkeypatch):
    protocol, profile = _setup(tmp_path, monkeypatch)
    started = []
    monkeypatch.setattr(api, "_run_import_job", lambda *a, **k: started.append(a))
    monkeypatch.setattr(api, "load_dataset_profile", lambda path: {"dataset": {"source_path": str(tmp_path / "gone" / "demo.zip")}})
    monkeypatch.setattr(api, "_load_legacy_protocol", lambda name: {"dataset": {"name": name}})

    response = _post()

    assert response.status_code == 400
    assert "missing" in response.get_json()["error"]
    assert "has not been touched" in response.get_json()["error"]
    assert started == [] and api._get_job("demo") is None          # no job was queued
    assert protocol.read_bytes() == OLD_PROTOCOL and profile.read_bytes() == OLD_PROFILE


def test_reconvert_starts_a_keep_existing_job_when_the_source_exists(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    source = tmp_path / "demo.zip"
    source.write_bytes(b"zip")
    started = []
    monkeypatch.setattr(api, "_run_import_job", lambda *a, **k: started.append(a))
    monkeypatch.setattr(api, "load_dataset_profile", lambda path: {"dataset": {"source_path": str(source)}})
    monkeypatch.setattr(api, "_load_legacy_protocol", lambda name: {"dataset": {"name": name}})

    response = _post()

    assert response.status_code == 202
    assert response.get_json()["job"]["name"] == "demo"
    assert len(started) == 1 and started[0][3] is True              # keep_existing
    api._jobs.clear()


def test_reconvert_while_a_job_is_active_is_a_conflict(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    source = tmp_path / "demo.zip"
    source.write_bytes(b"zip")
    monkeypatch.setattr(api, "load_dataset_profile", lambda path: {"dataset": {"source_path": str(source)}})
    monkeypatch.setattr(api, "_load_legacy_protocol", lambda name: {"dataset": {"name": name}})
    api._store_job({**_job(), "status": "running"})

    assert _post().status_code == 409
    api._jobs.clear()


def test_remote_sources_are_never_reported_missing():
    assert api._local_source_missing("https://example.org/data.zip") is False
    assert api._local_source_missing("/definitely/not/here.zip") is True
    assert api._local_source_missing("upload://file.zip") is True
    assert api._local_source_missing("") is True
