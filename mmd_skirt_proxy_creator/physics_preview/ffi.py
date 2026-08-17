import ctypes
import pathlib
import platform


ABI_VERSION = 4
DEFAULT_SOLVER_TARGET = "MMD"
SOLVER_FILENAMES = {
    "MMD": "mmd_physics_solver_mmd.dll",
    "PMX": "mmd_physics_solver.dll",
}


class Vec3(ctypes.Structure):
    _fields_ = (("x", ctypes.c_float), ("y", ctypes.c_float), ("z", ctypes.c_float))

    @classmethod
    def from_value(cls, value):
        return cls(float(value[0]), float(value[1]), float(value[2]))


class Quat(ctypes.Structure):
    _fields_ = (
        ("x", ctypes.c_float),
        ("y", ctypes.c_float),
        ("z", ctypes.c_float),
        ("w", ctypes.c_float),
    )

    @classmethod
    def from_value(cls, value):
        return cls(float(value.x), float(value.y), float(value.z), float(value.w))


class Transform(ctypes.Structure):
    _fields_ = (("position", Vec3), ("rotation", Quat))


class BodyDesc(ctypes.Structure):
    _fields_ = (
        ("mode", ctypes.c_uint32),
        ("shape", ctypes.c_uint32),
        ("transform", Transform),
        ("bone_transform", Transform),
        ("has_bone", ctypes.c_uint32),
        ("size", Vec3),
        ("mass", ctypes.c_float),
        ("linear_damping", ctypes.c_float),
        ("angular_damping", ctypes.c_float),
        ("restitution", ctypes.c_float),
        ("friction", ctypes.c_float),
        ("collision_group", ctypes.c_uint32),
        ("collision_mask", ctypes.c_uint32),
    )


class JointDesc(ctypes.Structure):
    _fields_ = (
        ("body_a", ctypes.c_uint32),
        ("body_b", ctypes.c_uint32),
        ("transform", Transform),
        ("linear_lower", Vec3),
        ("linear_upper", Vec3),
        ("angular_lower", Vec3),
        ("angular_upper", Vec3),
        ("linear_spring", Vec3),
        ("angular_spring", Vec3),
    )


class JointState(ctypes.Structure):
    _fields_ = (("frame_a", Transform), ("frame_b", Transform))


def matrix_to_transform(matrix):
    position, rotation, _scale = matrix.decompose()
    return Transform(Vec3.from_value(position), Quat.from_value(rotation))


def transform_to_components(value):
    return (
        (value.position.x, value.position.y, value.position.z),
        (value.rotation.w, value.rotation.x, value.rotation.y, value.rotation.z),
    )


def library_path(target=DEFAULT_SOLVER_TARGET):
    if platform.system() != "Windows" or platform.machine().lower() not in {
        "amd64",
        "x86_64",
    }:
        raise RuntimeError("当前物理预览 DLL 只构建了 Windows x64 版本")
    try:
        filename = SOLVER_FILENAMES[target]
    except KeyError as error:
        raise ValueError(f"未知物理对齐目标：{target}") from error
    return pathlib.Path(__file__).resolve().parent / "bin" / "win_amd64" / filename


class SolverLibrary:
    def __init__(self, path=None, target=DEFAULT_SOLVER_TARGET):
        path = pathlib.Path(path) if path else library_path(target)
        if not path.is_file():
            raise RuntimeError(f"找不到 Rust 物理求解器：{path}")
        self.path = path
        self.dll = ctypes.CDLL(str(path))
        self._bind()
        version = self.dll.mmd_solver_abi_version()
        if version != ABI_VERSION:
            raise RuntimeError(f"Rust 求解器 ABI 不匹配：需要 {ABI_VERSION}，实际 {version}")

    def _bind(self):
        dll = self.dll
        dll.mmd_solver_abi_version.argtypes = []
        dll.mmd_solver_abi_version.restype = ctypes.c_uint32
        dll.mmd_solver_pmx_euler_to_blender_quaternion.argtypes = (
            Vec3,
            ctypes.POINTER(Quat),
        )
        dll.mmd_solver_pmx_euler_to_blender_quaternion.restype = ctypes.c_int32
        dll.mmd_solver_create.argtypes = (
            ctypes.POINTER(BodyDesc),
            ctypes.c_uint32,
            ctypes.POINTER(JointDesc),
            ctypes.c_uint32,
            ctypes.c_float,
        )
        dll.mmd_solver_create.restype = ctypes.c_void_p
        dll.mmd_solver_destroy.argtypes = (ctypes.c_void_p,)
        dll.mmd_solver_destroy.restype = None
        dll.mmd_solver_set_gravity.argtypes = (ctypes.c_void_p, Vec3)
        dll.mmd_solver_set_gravity.restype = ctypes.c_int32
        dll.mmd_solver_set_iterations.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
        dll.mmd_solver_set_iterations.restype = ctypes.c_int32
        dll.mmd_solver_set_bone_target.argtypes = (
            ctypes.c_void_p,
            ctypes.c_uint32,
            Transform,
        )
        dll.mmd_solver_set_bone_target.restype = ctypes.c_int32
        dll.mmd_solver_step.argtypes = (ctypes.c_void_p, ctypes.c_float, ctypes.c_uint32)
        dll.mmd_solver_step.restype = ctypes.c_int32
        dll.mmd_solver_get_transforms.argtypes = (
            ctypes.c_void_p,
            ctypes.POINTER(Transform),
            ctypes.c_uint32,
        )
        dll.mmd_solver_get_transforms.restype = ctypes.c_uint32
        dll.mmd_solver_get_bone_transforms.argtypes = (
            ctypes.c_void_p,
            ctypes.POINTER(Transform),
            ctypes.c_uint32,
        )
        dll.mmd_solver_get_bone_transforms.restype = ctypes.c_uint32
        dll.mmd_solver_get_joint_states.argtypes = (
            ctypes.c_void_p,
            ctypes.POINTER(JointState),
            ctypes.c_uint32,
        )
        dll.mmd_solver_get_joint_states.restype = ctypes.c_uint32


_DEFAULT_LIBRARIES = {}


def default_library(target=DEFAULT_SOLVER_TARGET):
    library = _DEFAULT_LIBRARIES.get(target)
    if library is None:
        library = SolverLibrary(target=target)
        _DEFAULT_LIBRARIES[target] = library
    return library


def pmx_euler_to_blender_quaternion(value, library=None):
    library = library or default_library()
    output = Quat()
    result = library.dll.mmd_solver_pmx_euler_to_blender_quaternion(
        Vec3.from_value(value),
        ctypes.byref(output),
    )
    if result != 0:
        raise RuntimeError("PMX Euler 转换失败")
    return output


class Solver:
    def __init__(self, bodies, joints, world_scale, library=None):
        self.library = library or default_library()
        self.body_count = len(bodies)
        self.joint_count = len(joints)
        body_array = (BodyDesc * len(bodies))(*bodies)
        joint_array = (JointDesc * len(joints))(*joints) if joints else None
        self.handle = self.library.dll.mmd_solver_create(
            body_array,
            len(bodies),
            joint_array,
            len(joints),
            float(world_scale),
        )
        if not self.handle:
            raise RuntimeError("Rust 物理求解器初始化失败")

    def close(self):
        if self.handle:
            self.library.dll.mmd_solver_destroy(self.handle)
            self.handle = None

    def __del__(self):
        self.close()

    def set_gravity(self, value):
        if not self.library.dll.mmd_solver_set_gravity(self.handle, Vec3.from_value(value)):
            raise RuntimeError("设置重力失败")

    def set_iterations(self, value):
        if not self.library.dll.mmd_solver_set_iterations(self.handle, int(value)):
            raise RuntimeError("设置求解迭代次数失败")

    def set_bone_target(self, index, matrix):
        transform = matrix if isinstance(matrix, Transform) else matrix_to_transform(matrix)
        if not self.library.dll.mmd_solver_set_bone_target(
            self.handle,
            index,
            transform,
        ):
            raise RuntimeError(f"设置骨骼目标 {index} 失败")

    def step(self, dt, substeps):
        if not self.library.dll.mmd_solver_step(self.handle, float(dt), int(substeps)):
            raise RuntimeError("Rust 物理求解步骤失败")

    def transforms(self):
        output = (Transform * self.body_count)()
        count = self.library.dll.mmd_solver_get_transforms(
            self.handle,
            output,
            self.body_count,
        )
        if count != self.body_count:
            raise RuntimeError("读取 Rust 物理结果失败")
        return output

    def bone_transforms(self):
        output = (Transform * self.body_count)()
        count = self.library.dll.mmd_solver_get_bone_transforms(
            self.handle,
            output,
            self.body_count,
        )
        if count != self.body_count:
            raise RuntimeError("读取 Rust 骨骼结果失败")
        return output

    def joint_states(self):
        if self.joint_count == 0:
            return ()
        output = (JointState * self.joint_count)()
        count = self.library.dll.mmd_solver_get_joint_states(
            self.handle,
            output,
            self.joint_count,
        )
        if count != self.joint_count:
            raise RuntimeError("读取 Rust Joint 结果失败")
        return output
