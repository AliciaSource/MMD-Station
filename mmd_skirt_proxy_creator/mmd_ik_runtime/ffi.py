import ctypes
from pathlib import Path


ABI_VERSION = 1


class NativeBoneSolver:
    def __init__(self, pmx_path, vmd_path):
        self.pmx_path = str(Path(pmx_path).resolve())
        self.vmd_path = str(Path(vmd_path).resolve())
        self._dll = self._load_dll()
        self._configure_abi()
        if self._dll.spx_mmd_bone_abi_version() != ABI_VERSION:
            raise RuntimeError("mmd_bone_solver.dll ABI 版本不匹配")
        self._pmx_bytes = Path(self.pmx_path).read_bytes()
        self._vmd_bytes = Path(self.vmd_path).read_bytes()
        self._pmx_buffer = ctypes.create_string_buffer(self._pmx_bytes)
        self._vmd_buffer = ctypes.create_string_buffer(self._vmd_bytes)
        self._instance = self._create()
        self.count = int(self._dll.spx_mmd_bone_count(self._instance))
        self._output = (ctypes.c_float * (self.count * 16))()
        self.names = tuple(self._bone_name(index) for index in range(self.count))
        self.rest_positions = tuple(self._rest_position(index) for index in range(self.count))
        self.rigid_count = int(self._dll.spx_mmd_bone_rigid_count(self._instance))
        self.rigid_positions = tuple(
            self._rigid_position(index) for index in range(self.rigid_count)
        )

    @staticmethod
    def _load_dll():
        path = Path(__file__).with_name("bin") / "win_amd64" / "mmd_bone_solver.dll"
        if not path.is_file():
            raise RuntimeError(f"找不到独立骨骼求值器 DLL：{path}")
        return ctypes.CDLL(str(path))

    def _configure_abi(self):
        dll = self._dll
        dll.spx_mmd_bone_abi_version.restype = ctypes.c_uint32
        dll.spx_mmd_bone_create.argtypes = (
            ctypes.c_void_p,
            ctypes.c_size_t,
            ctypes.c_void_p,
            ctypes.c_size_t,
        )
        dll.spx_mmd_bone_create.restype = ctypes.c_void_p
        dll.spx_mmd_bone_destroy.argtypes = (ctypes.c_void_p,)
        dll.spx_mmd_bone_count.argtypes = (ctypes.c_void_p,)
        dll.spx_mmd_bone_count.restype = ctypes.c_uint32
        dll.spx_mmd_bone_rigid_count.argtypes = (ctypes.c_void_p,)
        dll.spx_mmd_bone_rigid_count.restype = ctypes.c_uint32
        dll.spx_mmd_bone_rigid_position.argtypes = (
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_float),
            ctypes.c_size_t,
        )
        dll.spx_mmd_bone_rigid_position.restype = ctypes.c_int
        dll.spx_mmd_bone_name_utf8.argtypes = (
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_char_p,
            ctypes.c_size_t,
        )
        dll.spx_mmd_bone_name_utf8.restype = ctypes.c_int
        dll.spx_mmd_bone_rest_position.argtypes = (
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_float),
            ctypes.c_size_t,
        )
        dll.spx_mmd_bone_rest_position.restype = ctypes.c_int
        dll.spx_mmd_bone_transform.argtypes = (
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_float),
            ctypes.c_size_t,
        )
        dll.spx_mmd_bone_transform.restype = ctypes.c_int
        dll.spx_mmd_bone_rigid_target.argtypes = (
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_float),
            ctypes.c_size_t,
        )
        dll.spx_mmd_bone_rigid_target.restype = ctypes.c_int
        dll.spx_mmd_bone_set_external_transform.argtypes = (
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_float),
            ctypes.POINTER(ctypes.c_float),
            ctypes.c_size_t,
        )
        dll.spx_mmd_bone_set_external_transform.restype = ctypes.c_int
        dll.spx_mmd_bone_set_external_physical_transform.argtypes = (
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_float),
            ctypes.POINTER(ctypes.c_float),
            ctypes.c_size_t,
        )
        dll.spx_mmd_bone_set_external_physical_transform.restype = ctypes.c_int
        dll.spx_mmd_bone_set_external_physical_pose.argtypes = (
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_float),
            ctypes.POINTER(ctypes.c_float),
            ctypes.c_size_t,
        )
        dll.spx_mmd_bone_set_external_physical_pose.restype = ctypes.c_int
        dll.spx_mmd_bone_set_external_physical_matrix.argtypes = (
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_float),
            ctypes.POINTER(ctypes.c_float),
            ctypes.c_size_t,
        )
        dll.spx_mmd_bone_set_external_physical_matrix.restype = ctypes.c_int
        dll.spx_mmd_bone_set_external_rigid_transform.argtypes = (
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_float),
            ctypes.POINTER(ctypes.c_float),
            ctypes.c_size_t,
        )
        dll.spx_mmd_bone_set_external_rigid_transform.restype = ctypes.c_int
        dll.spx_mmd_bone_rigid_matrix.argtypes = (
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_float),
            ctypes.c_size_t,
        )
        dll.spx_mmd_bone_rigid_matrix.restype = ctypes.c_int
        dll.spx_mmd_bone_set_external_rigid_matrix.argtypes = (
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_float),
            ctypes.POINTER(ctypes.c_float),
            ctypes.c_size_t,
        )
        dll.spx_mmd_bone_set_external_rigid_matrix.restype = ctypes.c_int
        dll.spx_mmd_bone_set_external_rigid_matrix_mmd.argtypes = (
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_float),
            ctypes.POINTER(ctypes.c_float),
            ctypes.c_size_t,
        )
        dll.spx_mmd_bone_set_external_rigid_matrix_mmd.restype = ctypes.c_int
        dll.spx_mmd_bone_clear_external_transforms.argtypes = (ctypes.c_void_p,)
        dll.spx_mmd_bone_commit_external.argtypes = (ctypes.c_void_p,)
        dll.spx_mmd_bone_commit_external.restype = ctypes.c_int
        dll.spx_mmd_bone_evaluate.argtypes = (
            ctypes.c_void_p,
            ctypes.c_float,
            ctypes.POINTER(ctypes.c_float),
            ctypes.c_size_t,
        )
        dll.spx_mmd_bone_evaluate.restype = ctypes.c_int
        dll.spx_mmd_bone_evaluate_before_physics.argtypes = (
            ctypes.c_void_p,
            ctypes.c_float,
            ctypes.POINTER(ctypes.c_float),
            ctypes.c_size_t,
        )
        dll.spx_mmd_bone_evaluate_before_physics.restype = ctypes.c_int
        dll.spx_mmd_bone_evaluate_after_physics.argtypes = (
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_float),
            ctypes.c_size_t,
        )
        dll.spx_mmd_bone_evaluate_after_physics.restype = ctypes.c_int
        dll.spx_mmd_bone_last_error.restype = ctypes.c_char_p

    def _error(self):
        raw = self._dll.spx_mmd_bone_last_error()
        return raw.decode("utf-8", errors="replace") if raw else "未知 native 错误"

    def _create(self):
        instance = self._dll.spx_mmd_bone_create(
            self._pmx_buffer,
            len(self._pmx_bytes),
            self._vmd_buffer,
            len(self._vmd_bytes),
        )
        if not instance:
            raise RuntimeError(self._error())
        return instance

    def _bone_name(self, index):
        size = self._dll.spx_mmd_bone_name_utf8(self._instance, index, None, 0)
        buffer = ctypes.create_string_buffer(size + 1)
        self._dll.spx_mmd_bone_name_utf8(self._instance, index, buffer, len(buffer))
        return buffer.value.decode("utf-8")

    def _rest_position(self, index):
        values = (ctypes.c_float * 3)()
        if not self._dll.spx_mmd_bone_rest_position(self._instance, index, values, 3):
            raise RuntimeError(f"无法读取第 {index} 根骨骼的 PMX 静止位置")
        return tuple(float(value) for value in values)

    def _rigid_position(self, index):
        values = (ctypes.c_float * 3)()
        if not self._dll.spx_mmd_bone_rigid_position(
            self._instance, index, values, 3
        ):
            raise RuntimeError(f"Failed to read PMX rigid body position {index}")
        return tuple(float(value) for value in values)

    def evaluate(self, frame):
        if not self._instance:
            raise RuntimeError("骨骼求值器已关闭")
        if not self._dll.spx_mmd_bone_evaluate(
            self._instance, ctypes.c_float(frame), self._output, len(self._output)
        ):
            raise RuntimeError(self._error())
        return self._output

    def evaluate_before_physics(self, frame):
        if not self._instance:
            raise RuntimeError("骨骼求值器已关闭")
        if not self._dll.spx_mmd_bone_evaluate_before_physics(
            self._instance, ctypes.c_float(frame), self._output, len(self._output)
        ):
            raise RuntimeError(self._error())
        return self._output

    def evaluate_after_physics(self):
        if not self._instance:
            raise RuntimeError("骨骼求值器已关闭")
        if not self._dll.spx_mmd_bone_evaluate_after_physics(
            self._instance, self._output, len(self._output)
        ):
            raise RuntimeError(self._error())
        return self._output

    def matrix(self, index):
        offset = index * 16
        return tuple(float(self._output[offset + item]) for item in range(16))

    def transform(self, index):
        values = (ctypes.c_float * 7)()
        if not self._dll.spx_mmd_bone_transform(self._instance, index, values, 7):
            raise RuntimeError(f"无法读取第 {index} 根骨骼的 MMD 世界变换")
        return tuple(float(value) for value in values)

    def set_external_transform(self, index, position, rotation):
        position_values = (ctypes.c_float * 3)(*position)
        rotation_values = (ctypes.c_float * 4)(*rotation)
        if not self._dll.spx_mmd_bone_set_external_transform(
            self._instance,
            index,
            position_values,
            rotation_values,
            4,
        ):
            raise RuntimeError(f"无法提交第 {index} 根骨骼的物理反馈")

    def rigid_target(self, rigid_index):
        values = (ctypes.c_float * 7)()
        if not self._dll.spx_mmd_bone_rigid_target(
            self._instance, rigid_index, values, 7
        ):
            raise RuntimeError(f"无法读取第 {rigid_index} 个刚体的 MMD 目标变换")
        return tuple(float(value) for value in values)

    def clear_external_transforms(self):
        self._dll.spx_mmd_bone_clear_external_transforms(self._instance)

    def commit_external(self):
        if not self._dll.spx_mmd_bone_commit_external(self._instance):
            raise RuntimeError("Failed to commit external physical transforms")

    def rigid_matrix(self, rigid_index):
        values = (ctypes.c_float * 12)()
        if not self._dll.spx_mmd_bone_rigid_matrix(
            self._instance, rigid_index, values, 12
        ):
            raise RuntimeError(f"Failed to read rigid body {rigid_index} matrix")
        return tuple(float(value) for value in values)

    def set_external_rigid_transform(self, rigid_index, position, rotation):
        position_values = (ctypes.c_float * 3)(*position)
        rotation_values = (ctypes.c_float * 4)(*rotation)
        if not self._dll.spx_mmd_bone_set_external_rigid_transform(
            self._instance,
            rigid_index,
            position_values,
            rotation_values,
            4,
        ):
            raise RuntimeError(f"无法提交第 {rigid_index} 个刚体的物理反馈")

    def set_external_rigid_matrix(self, rigid_index, position, basis_row_major):
        position_values = (ctypes.c_float * 3)(*position)
        basis_values = (ctypes.c_float * 9)(*basis_row_major)
        if not self._dll.spx_mmd_bone_set_external_rigid_matrix(
            self._instance, rigid_index, position_values, basis_values, 9
        ):
            raise RuntimeError(f"Failed to submit rigid body {rigid_index} matrix")

    def set_external_rigid_matrix_mmd(self, rigid_index, position, basis_row_major):
        position_values = (ctypes.c_float * 3)(*position)
        basis_values = (ctypes.c_float * 9)(*basis_row_major)
        if not self._dll.spx_mmd_bone_set_external_rigid_matrix_mmd(
            self._instance, rigid_index, position_values, basis_values, 9
        ):
            raise RuntimeError(f"Failed to submit MMD rigid body {rigid_index} matrix")

    def set_external_physical_transform(self, index, mode, position, rotation):
        position_values = (ctypes.c_float * 3)(*position)
        rotation_values = (ctypes.c_float * 4)(*rotation)
        if not self._dll.spx_mmd_bone_set_external_physical_transform(
            self._instance, index, mode, position_values, rotation_values, 4
        ):
            raise RuntimeError(f"无法提交第 {index} 根骨骼的物理反馈")

    def set_external_physical_pose(self, index, mode, initial, current):
        initial_values = (ctypes.c_float * 7)(*initial)
        current_values = (ctypes.c_float * 7)(*current)
        if not self._dll.spx_mmd_bone_set_external_physical_pose(
            self._instance, index, mode, initial_values, current_values, 7
        ):
            raise RuntimeError(f"无法提交第 {index} 根骨骼的物理姿态")

    def set_external_physical_matrix(self, index, mode, initial, current):
        initial_values = (ctypes.c_float * 7)(*initial)
        current_values = (ctypes.c_float * 7)(*current)
        if not self._dll.spx_mmd_bone_set_external_physical_matrix(
            self._instance, index, mode, initial_values, current_values, 7
        ):
            raise RuntimeError(f"无法提交第 {index} 根骨骼的物理矩阵")

    def reset(self):
        if self._instance:
            self._dll.spx_mmd_bone_destroy(self._instance)
        self._instance = self._create()

    def close(self):
        if self._instance:
            self._dll.spx_mmd_bone_destroy(self._instance)
            self._instance = None

    def __enter__(self):
        return self

    def __exit__(self, _kind, _value, _traceback):
        self.close()
