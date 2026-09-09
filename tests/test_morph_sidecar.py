import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "morph_sidecar", Path(__file__).resolve().parents[1] / "mmd_station" / "morph_sidecar.py"
)
sidecar = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sidecar)


def entry(scale=(1.2, 0.8, 1.0)):
    return {"morph": {"name": "Size", "name_e": "Size", "index": 1},
            "bone": {"name": "Root", "name_e": "Root", "index": 0}, "scale": list(scale)}


def test_naming_overwrite_and_cleanup(tmp_path):
    pmx = tmp_path / "Body.pmx"
    target = tmp_path / "Body.Morph.json"
    assert sidecar.sidecar_path(pmx) == target
    sidecar.write_payload(pmx, [])
    assert not target.exists()
    sidecar.write_payload(pmx, [entry()])
    sidecar.write_payload(pmx, [entry((2, 1, 0))])
    assert sidecar.read_payload(target)["entries"] == [entry((2, 1, 0))]
    assert list(tmp_path.iterdir()) == [target]
    sidecar.write_payload(pmx, [])
    assert not target.exists()


@pytest.mark.parametrize("value", [[1, 2], [True, 1, 1], [float("nan"), 1, 1], [float("inf"), 1, 1], ["2", 1, 1]])
def test_invalid_scale_rejected(tmp_path, value):
    target = tmp_path / "arbitrary.json"
    target.write_text(json.dumps({"format": sidecar.FORMAT, "version": 1, "entries": [entry(value)]}), encoding="utf-8")
    with pytest.raises(ValueError):
        sidecar.read_payload(target)


def test_failed_replace_preserves_old_file_and_removes_temporary(tmp_path, monkeypatch):
    path = tmp_path / "Body.pmx"
    sidecar.write_payload(path, [entry()])
    old = sidecar.sidecar_path(path).read_bytes()
    def fail(*args):
        raise OSError("fixture write failure")
    monkeypatch.setattr(sidecar.os, "replace", fail)
    with pytest.raises(OSError):
        sidecar.write_payload(path, [entry((2, 2, 2))])
    assert sidecar.sidecar_path(path).read_bytes() == old
    assert len(list(tmp_path.iterdir())) == 1


def test_cleanup_does_not_delete_unrelated_json(tmp_path):
    pmx = tmp_path / "Body.pmx"
    target = sidecar.sidecar_path(pmx)
    target.write_text('{"unrelated": true}', encoding="utf-8")
    with pytest.raises(ValueError):
        sidecar.write_payload(pmx, [])
    assert target.exists()
