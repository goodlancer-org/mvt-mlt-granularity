import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import src.api as api


def test_normalized_metadata_endpoint_distinguishes_gpkg_and_manifest(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "NORMALIZED_DIR", tmp_path)
    dataset_dir = tmp_path / "demo"
    dataset_dir.mkdir()
    (dataset_dir / "demo.gpkg").write_bytes(b"gpkg")
    (dataset_dir / "demo.normalization.json").write_text(
        json.dumps({"artifact_status": "generated", "normalized_crs": "EPSG:3857"}),
        encoding="utf-8",
    )

    client = api.app.test_client()
    response = client.get("/api/datasets/demo/normalized")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["gpkg"]["exists"] is True
    assert payload["manifest"]["exists"] is True
    assert payload["manifest"]["data"]["normalized_crs"] == "EPSG:3857"
