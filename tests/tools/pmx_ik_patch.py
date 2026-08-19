import struct
from pathlib import Path


class _Reader:
    def __init__(self, data):
        self.data = data
        self.offset = 0

    def skip(self, size):
        self.offset += size

    def u8(self):
        value = self.data[self.offset]
        self.offset += 1
        return value

    def i32(self):
        value = struct.unpack_from("<i", self.data, self.offset)[0]
        self.offset += 4
        return value

    def text(self):
        self.skip(4 + self.i32_at(self.offset))

    def i32_at(self, offset):
        return struct.unpack_from("<i", self.data, offset)[0]

    def index(self, size):
        self.skip(size)


def strip_ik_payloads(source, destination):
    return strip_ik_payloads_except(source, destination, ())


def strip_ik_payloads_except(source, destination, keep_bone_indices):
    keep_bone_indices = set(keep_bone_indices)
    data = bytearray(Path(source).read_bytes())
    r = _Reader(data)
    if data[:4] != b"PMX ":
        raise ValueError("not a PMX file")
    r.skip(8)
    header_size = r.u8()
    header = data[r.offset:r.offset + header_size]
    r.skip(header_size)
    additional_uv = header[1]
    vertex_index_size = header[2]
    texture_index_size = header[3]
    material_index_size = header[4]
    bone_index_size = header[5]
    for _ in range(4):
        r.text()
    vertex_count = r.i32()
    for _ in range(vertex_count):
        r.skip(32 + additional_uv * 16)
        deform = r.u8()
        if deform == 0:
            r.skip(bone_index_size)
        elif deform == 1:
            r.skip(bone_index_size * 2 + 4)
        elif deform in (2, 4):
            r.skip(bone_index_size * 4 + 16)
        elif deform == 3:
            r.skip(bone_index_size * 2 + 40)
        else:
            raise ValueError(f"unknown deform {deform}")
        r.skip(4)
    r.skip(r.i32() * vertex_index_size)
    for _ in range(r.i32()):
        r.text()
    for _ in range(r.i32()):
        r.text()
        r.text()
        r.skip(66 + texture_index_size * 2)
        shared_toon = r.u8()
        r.skip(1 if shared_toon else texture_index_size)
        r.text()
        r.skip(4)
    patched = 0
    removals = []
    for bone_index in range(r.i32()):
        r.text()
        r.text()
        r.skip(12 + bone_index_size + 4)
        flags = struct.unpack_from("<H", data, r.offset)[0]
        flags_offset = r.offset
        r.skip(2)
        r.skip(bone_index_size if flags & 0x0001 else 12)
        if flags & 0x0300:
            r.skip(bone_index_size + 4)
        if flags & 0x0400:
            r.skip(12)
        if flags & 0x0800:
            r.skip(24)
        if flags & 0x2000:
            r.skip(4)
        if flags & 0x0020:
            start = r.offset
            r.skip(bone_index_size + 8)
            for _ in range(r.i32()):
                r.skip(bone_index_size)
                limited = r.u8()
                if limited:
                    r.skip(24)
            if bone_index not in keep_bone_indices:
                patched += 1
                removals.append((start, r.offset))
                struct.pack_into("<H", data, flags_offset, flags & ~0x0020)
    for start, end in reversed(removals):
        del data[start:end]
    Path(destination).write_bytes(data)
    return patched
