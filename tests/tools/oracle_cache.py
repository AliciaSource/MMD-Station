import json
import hashlib
import struct
from pathlib import Path


class OracleCacheError(RuntimeError):
    pass


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def decode_matrix(hex_value):
    raw = bytes.fromhex(hex_value)
    if len(raw) != 64:
        raise OracleCacheError("MMD 缓存中的矩阵长度无效")
    return struct.unpack("<16f", raw)


class OracleCache:
    def __init__(self, path):
        self.path = Path(path)
        self.frames = {}
        self.raw_hex = {}
        self.object_filename = ""
        self.bone_names = []
        self.metadata = {}
        self._load()

    def _load(self):
        if not self.path.is_file():
            raise OracleCacheError("请选择有效的 MMD 精确缓存文件")
        with self.path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                    frame = int(record["frame"])
                    objects = record["objects"]
                    if not objects:
                        continue
                    filename, bones = objects[0]
                    names = [str(item[0]) for item in bones]
                    values = tuple(decode_matrix(item[1]) for item in bones)
                except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
                    raise OracleCacheError(f"MMD 缓存第 {line_number} 行无效") from error
                if self.bone_names and names != self.bone_names:
                    raise OracleCacheError("MMD 缓存各帧的骨骼顺序不一致")
                self.object_filename = str(filename)
                self.bone_names = names
                metadata = record.get("spx_mmd_ik", {})
                if metadata:
                    if self.metadata and metadata != self.metadata:
                        raise OracleCacheError("MMD 缓存各帧的来源元数据不一致")
                    self.metadata = metadata
                self.frames[frame] = values
                self.raw_hex[frame] = tuple(str(item[1]).lower() for item in bones)
        if not self.frames:
            raise OracleCacheError("MMD 精确缓存不包含任何骨骼帧")

    @property
    def first_frame(self):
        return min(self.frames)

    @property
    def last_frame(self):
        return max(self.frames)

    def matrices(self, frame):
        try:
            return self.frames[int(frame)]
        except KeyError as error:
            raise OracleCacheError(f"MMD 精确缓存缺少第 {int(frame)} 帧") from error

    def validate_sources(self, pmx_path, vmd_path):
        if not self.metadata:
            return
        for label, path in (("pmx", Path(pmx_path)), ("vmd", Path(vmd_path))):
            expected = self.metadata.get(f"{label}_sha256")
            if not path.is_file() or not expected:
                raise OracleCacheError(f"MMD 缓存缺少有效的 {label.upper()} 来源")
            digest = file_sha256(path)
            if digest != expected:
                raise OracleCacheError(f"MMD 缓存与当前 {label.upper()} 文件不匹配")
