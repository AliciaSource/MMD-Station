"""Versioned, filename-independent bone scale payloads beside standard PMX files."""

import json
import math
import os
from pathlib import Path
import tempfile

FORMAT = "bone-morph-scale"
VERSION = 1


def sidecar_path(filepath):
    return Path(filepath).with_suffix(".Morph.json")


def non_unit(scale):
    return any(abs(v - 1.0) > 1.0e-6 for v in scale)


def read_payload(filepath):
    path = Path(filepath)
    if path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("Morph JSON exceeds 16 MiB")
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict) or payload.get("format") != FORMAT or payload.get("version") != VERSION:
        raise ValueError("Unsupported Morph JSON format/version")
    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise ValueError("Morph JSON entries must be a list")
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Invalid Morph JSON entry")
        for key in ("morph", "bone"):
            identity = entry.get(key)
            if not isinstance(identity, dict) or not all(isinstance(identity.get(k), str) for k in ("name", "name_e")):
                raise ValueError("Invalid Morph JSON identity")
        scale = entry.get("scale")
        if not isinstance(scale, list) or len(scale) != 3 or not all(
            type(v) in (float, int) and math.isfinite(v) and abs(v) <= 1.0e6 for v in scale
        ):
            raise ValueError("Invalid Morph JSON scale")
    return payload


def write_payload(filepath, entries):
    target = sidecar_path(filepath)
    if not entries:
        if target.exists():
            # Never delete an unrelated or malformed user file.
            read_payload(target)
            target.unlink()
        return
    payload = {"format": FORMAT, "version": VERSION, "entries": entries}
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent,
                                         prefix=target.name + ".", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(payload, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
        os.replace(temporary, target)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
