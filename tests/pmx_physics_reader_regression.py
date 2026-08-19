import sys
import time
from pathlib import Path


REPO = Path(r"D:\MOD\BlenderAddonProjects\MMD-Skirt-Proxy-Creator")
MMD_TOOLS_PARENT = Path(
    r"C:\Users\A\AppData\Roaming\Blender Foundation\Blender\4.4\extensions\blender_org"
)
PMX = Path(
    r"D:\MMD\MEGA\_Alicia模型\Endfield-Rossi\Endfield-RossiVer1.0_by_Alicia\Rossi Ver1.0.pmx"
)
sys.path[:0] = [str(MMD_TOOLS_PARENT), str(REPO)]

from mmd_tools.core import pmx
from mmd_skirt_proxy_creator.physics_preview.runtime import _read_pmx_physics


start = time.perf_counter()
actual_name, actual_rigids, actual_joints = _read_pmx_physics(PMX)
fast_seconds = time.perf_counter() - start
model = pmx.load(str(PMX))

expected_rigids = [
    (item.name, tuple(item.rotation), tuple(item.size), float(item.mass))
    for item in model.rigids
]
expected_joints = [
    (
        item.name,
        tuple(item.rotation),
        tuple(item.minimum_location),
        tuple(item.maximum_location),
        tuple(item.minimum_rotation),
        tuple(item.maximum_rotation),
        tuple(item.spring_constant),
        tuple(item.spring_rotation_constant),
    )
    for item in model.joints
]
assert actual_name == model.name
assert actual_rigids == expected_rigids
assert actual_joints == expected_joints
print(
    "PMX_PHYSICS_READER_REGRESSION_OK",
    f"rigids={len(actual_rigids)}",
    f"joints={len(actual_joints)}",
    f"fast_seconds={fast_seconds:.9g}",
)
