import struct
from pathlib import Path


def _text(value):
    raw = value.encode("utf-16-le")
    return struct.pack("<i", len(raw)) + raw


def write_chain_pmx(path, bones):
    header = bytes((0, 0, 1, 1, 1, 1, 1, 1))
    data = bytearray(b"PMX " + struct.pack("<fB", 2.0, len(header)) + header)
    for value in ("SPX fixture", "SPX fixture", "", ""):
        data += _text(value)
    vertices = ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
    data += struct.pack("<i", len(vertices))
    for position in vertices:
        data += struct.pack("<3f3f2fBb f", *position, 0.0, 0.0, 1.0, 0.0, 0.0, 0, 0, 1.0)
    data += struct.pack("<i3B", 3, 0, 1, 2)
    data += struct.pack("<i", 0)  # textures
    data += struct.pack("<i", 1)
    data += _text("material") + _text("material")
    data += struct.pack("<4f3ff3fB4ffbbBBB", 1.0, 1.0, 1.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.5, 0.5, 0.5, 0, 0.0, 0.0, 0.0, 1.0, 1.0, -1, -1, 0, 1, 0)
    data += _text("") + struct.pack("<i", 3)
    data += struct.pack("<i", len(bones))
    for bone in bones:
        data += _text(bone["name"]) + _text(bone["name"])
        data += struct.pack("<3fb i H", *bone["position"], bone.get("parent", -1), bone.get("level", 0), bone.get("flags", 0x001E))
        data += struct.pack("<3f", 0.0, 1.0, 0.0)
    data += struct.pack("<iiii", 0, 0, 0, 0)
    Path(path).write_bytes(data)


def _vmd_name(value, size):
    raw = value.encode("cp932")
    if len(raw) > size:
        raise ValueError(f"VMD name is longer than {size} bytes")
    return raw + b"\0" * (size - len(raw))


def _linear_interpolation():
    block = bytes((20, 20, 20, 20, 20, 20, 20, 20, 107, 107, 107, 107, 107, 107, 107, 107))
    return block * 4


def write_vmd(path, bone_keys, morph_keys=()):
    signature = b"Vocaloid Motion Data 0002".ljust(30, b"\0")
    data = bytearray(signature + _vmd_name("SPX fixture", 20) + struct.pack("<I", len(bone_keys)))
    for key in bone_keys:
        data += _vmd_name(key["name"], 15)
        data += struct.pack("<I3f4f", key["frame"], *key["position"], *key["rotation"])
        data += key.get("interpolation", _linear_interpolation())
    data += struct.pack("<I", len(morph_keys))
    for key in morph_keys:
        data += _vmd_name(key["name"], 15)
        data += struct.pack("<If", key["frame"], key["weight"])
    data += struct.pack("<IIIII", 0, 0, 0, 0, 0)
    Path(path).write_bytes(data)
