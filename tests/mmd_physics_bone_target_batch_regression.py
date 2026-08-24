import ctypes
import math
import statistics
import sys
from pathlib import Path
from types import SimpleNamespace
from time import perf_counter


REPO = Path(r"D:\MOD\BlenderAddonProjects\MMD-Skirt-Proxy-Creator")
sys.path.insert(0, str(REPO))

from mmd_skirt_proxy_creator.physics_preview.ffi import (
    BodyDesc,
    Quat,
    Solver,
    SolverLibrary,
    Transform,
    Vec3,
    pmx_euler_to_blender_quaternion,
)


ENTRY_COUNT = 320


class _WithoutSymbols:
    def __init__(self, dll, *names):
        self._dll = dll
        self._names = frozenset(names)

    def __getattr__(self, name):
        if name in self._names:
            raise AttributeError(name)
        return getattr(self._dll, name)


def _transform(index, phase=0.0, identity_rotation=False):
    value = float(index) * 0.0025 + phase
    angle = (float(index % 17) - 8.0) * 0.015 + phase * 0.125
    rotation = (
        Quat(0.0, 0.0, 0.0, 1.0)
        if identity_rotation
        else Quat(0.0, 0.0, math.sin(angle * 0.5), math.cos(angle * 0.5))
    )
    return Transform(
        Vec3(value, -value * 0.5, value * 0.25),
        rotation,
    )


def _position(index, phase=0.0):
    value = float(index) * 0.003125 + phase
    return Vec3(value, -value * 0.375, value * 0.625)


def _pmx_euler(index, phase=0.0):
    return Vec3(
        (float(index % 19) - 9.0) * 0.0175 + phase * 0.125,
        (float(index % 13) - 6.0) * -0.021 + phase * 0.25,
        (float(index % 11) - 5.0) * 0.0275 - phase * 0.1875,
    )


def _pmx_transform(library, index, phase=0.0, euler_phase=None):
    euler = _pmx_euler(index, phase if euler_phase is None else euler_phase)
    return Transform(
        _position(index, phase),
        pmx_euler_to_blender_quaternion(
            (euler.x, euler.y, euler.z),
            library=library,
        ),
    )


def _body(library, index):
    transform = _pmx_transform(library, index)
    mode = index % 3
    return BodyDesc(
        mode,
        0,
        transform,
        transform,
        1,
        Vec3(0.05, 0.05, 0.05),
        0.0 if mode == 0 else 1.0,
        0.0,
        0.0,
        0.0,
        0.5,
        0,
        0,
    )


def _solver(library, target):
    bodies = [_body(library, index) for index in range(ENTRY_COUNT)]
    if target == "MMD":
        source_eulers = [_pmx_euler(index) for index in range(ENTRY_COUNT)]
        return Solver(
            bodies,
            [],
            1.0,
            library=library,
            body_source_eulers=source_eulers,
            joint_source_eulers=[],
        )
    return Solver(bodies, [], 1.0, library=library)


def _bytes(solver):
    return bytes(solver.transforms())


def _bone_bytes(solver):
    return bytes(solver.bone_transforms())


def _assert_raises(error_type, callable_object):
    try:
        callable_object()
    except error_type:
        return
    raise AssertionError(f"Expected {error_type.__name__}")


def _run(target):
    library = SolverLibrary(target=target)
    assert hasattr(library.dll, "mmd_solver_set_bone_targets")
    assert hasattr(library.dll, "mmd_solver_set_bone_targets_pmx_eulers")
    solvers = [_solver(library, target) for _index in range(10)]
    try:
        (
            single,
            batch,
            fallback,
            rejected,
            expected,
            performance,
            euler_single,
            euler_batch,
            euler_fallback,
            euler_scalar_fallback,
        ) = solvers
        entries = tuple(
            (index, _transform(index, 0.125)) for index in range(ENTRY_COUNT)
        )

        for index, transform in entries:
            single.set_bone_target(index, transform)
        batch.set_bone_targets(entries)
        fallback.library = SimpleNamespace(
            dll=_WithoutSymbols(library.dll, "mmd_solver_set_bone_targets")
        )
        fallback.set_bone_targets(entries)
        assert _bytes(single) == _bytes(batch)
        assert _bytes(single) == _bytes(fallback)
        assert _bone_bytes(single) == _bone_bytes(batch)
        assert _bone_bytes(single) == _bone_bytes(fallback)

        euler_indices = tuple(range(ENTRY_COUNT))
        euler_positions = tuple(
            _position(index, 0.375) for index in range(ENTRY_COUNT)
        )
        euler_values = tuple(
            _pmx_euler(index, 0.375) for index in range(ENTRY_COUNT)
        )
        euler_entries = tuple(
            (index, _pmx_transform(library, index, 0.375))
            for index in range(ENTRY_COUNT)
        )
        for index, transform in euler_entries:
            euler_single.set_bone_target(index, transform)
        euler_batch.set_bone_targets_pmx_eulers(
            euler_indices,
            euler_positions,
            euler_values,
        )
        euler_fallback.library = SimpleNamespace(
            dll=_WithoutSymbols(
                library.dll,
                "mmd_solver_set_bone_targets_pmx_eulers",
            )
        )
        euler_fallback.set_bone_targets_pmx_eulers(
            euler_indices,
            euler_positions,
            euler_values,
        )
        euler_scalar_fallback.library = SimpleNamespace(
            dll=_WithoutSymbols(
                library.dll,
                "mmd_solver_set_bone_targets_pmx_eulers",
                "mmd_solver_set_bone_targets",
            )
        )
        euler_scalar_fallback.set_bone_targets_pmx_eulers(
            euler_indices,
            euler_positions,
            euler_values,
        )
        assert _bytes(euler_single) == _bytes(euler_batch)
        assert _bytes(euler_single) == _bytes(euler_fallback)
        assert _bytes(euler_single) == _bytes(euler_scalar_fallback)
        assert _bone_bytes(euler_single) == _bone_bytes(euler_batch)
        assert _bone_bytes(euler_single) == _bone_bytes(euler_fallback)
        assert _bone_bytes(euler_single) == _bone_bytes(euler_scalar_fallback)

        cached_batch = euler_batch.bone_target_pmx_euler_batch(euler_indices)
        position_buffer = cached_batch.positions
        euler_buffer = cached_batch.pmx_eulers
        second_positions = tuple(
            _position(index, 0.625) for index in range(ENTRY_COUNT)
        )
        second_eulers = tuple(
            _pmx_euler(index) for index in range(ENTRY_COUNT)
        )
        second_entries = tuple(
            (index, _pmx_transform(library, index, 0.625, euler_phase=0.0))
            for index in range(ENTRY_COUNT)
        )
        cached_batch.set_targets(second_positions, second_eulers)
        cached_batch.submit()
        assert cached_batch.positions is position_buffer
        assert cached_batch.pmx_eulers is euler_buffer
        for index, transform in second_entries:
            euler_single.set_bone_target(index, transform)
        euler_fallback.set_bone_targets_pmx_eulers(
            euler_indices,
            second_positions,
            second_eulers,
        )
        euler_scalar_fallback.set_bone_targets_pmx_eulers(
            euler_indices,
            second_positions,
            second_eulers,
        )
        for solver in (
            euler_single,
            euler_batch,
            euler_fallback,
            euler_scalar_fallback,
        ):
            solver.step(1.0 / 60.0, 10)
        assert _bytes(euler_single) == _bytes(euler_batch)
        assert _bytes(euler_single) == _bytes(euler_fallback)
        assert _bytes(euler_single) == _bytes(euler_scalar_fallback)
        assert _bone_bytes(euler_single) == _bone_bytes(euler_batch)
        assert _bone_bytes(euler_single) == _bone_bytes(euler_fallback)
        assert _bone_bytes(euler_single) == _bone_bytes(euler_scalar_fallback)

        identity_entries = tuple(
            (index, _transform(index, 0.25, identity_rotation=True))
            for index in range(ENTRY_COUNT)
        )
        for index, transform in identity_entries:
            single.set_bone_target(index, transform)
        batch.set_bone_targets(identity_entries)
        fallback.set_bone_targets(identity_entries)
        for solver in (single, batch, fallback):
            solver.step(1.0 / 60.0, 10)
        assert _bytes(single) == _bytes(batch)
        assert _bytes(single) == _bytes(fallback)
        assert _bone_bytes(single) == _bone_bytes(batch)
        assert _bone_bytes(single) == _bone_bytes(fallback)

        rejected.set_bone_targets(entries)
        expected.set_bone_targets(entries)
        before = _bytes(rejected)
        indices = (ctypes.c_uint32 * 2)(0, ENTRY_COUNT)
        targets = (Transform * 2)(_transform(0, 2.0), _transform(1, 2.0))
        assert not library.dll.mmd_solver_set_bone_targets(
            rejected.handle,
            indices,
            targets,
            2,
        )
        assert _bytes(rejected) == before == _bytes(expected)

        invalid_indices = (ctypes.c_uint32 * 3)(0, 2, ENTRY_COUNT)
        pmx_positions = (Vec3 * 3)(
            _position(0, 2.5),
            _position(2, 2.5),
            _position(1, 2.5),
        )
        pmx_eulers = (Vec3 * 3)(
            _pmx_euler(0, 2.5),
            _pmx_euler(2, 2.5),
            _pmx_euler(1, 2.5),
        )
        before = _bytes(rejected)
        bone_before = _bone_bytes(rejected)
        assert not library.dll.mmd_solver_set_bone_targets_pmx_eulers(
            rejected.handle,
            invalid_indices,
            pmx_positions,
            pmx_eulers,
            3,
        )
        assert _bytes(rejected) == before == _bytes(expected)
        assert _bone_bytes(rejected) == bone_before == _bone_bytes(expected)
        assert not library.dll.mmd_solver_set_bone_targets_pmx_eulers(
            rejected.handle,
            None,
            pmx_positions,
            pmx_eulers,
            1,
        )
        assert not library.dll.mmd_solver_set_bone_targets_pmx_eulers(
            rejected.handle,
            invalid_indices,
            None,
            pmx_eulers,
            1,
        )
        assert not library.dll.mmd_solver_set_bone_targets_pmx_eulers(
            rejected.handle,
            invalid_indices,
            pmx_positions,
            None,
            1,
        )
        assert library.dll.mmd_solver_set_bone_targets_pmx_eulers(
            rejected.handle,
            None,
            None,
            None,
            0,
        )
        assert _bytes(rejected) == before == _bytes(expected)
        assert _bone_bytes(rejected) == bone_before == _bone_bytes(expected)

        try:
            batch.set_bone_targets((entries[0], (ENTRY_COUNT, entries[1][1])))
        except RuntimeError:
            pass
        else:
            raise AssertionError("Python batch validation accepted an invalid index")
        _assert_raises(
            TypeError,
            lambda: batch.set_bone_targets(((1.5, entries[0][1]),)),
        )
        _assert_raises(
            TypeError,
            lambda: batch.set_bone_targets((("0", entries[0][1]),)),
        )
        euler_before = _bytes(euler_batch)
        euler_bone_before = _bone_bytes(euler_batch)
        _assert_raises(
            RuntimeError,
            lambda: euler_batch.set_bone_targets_pmx_eulers(
                (0, ENTRY_COUNT),
                euler_positions[:2],
                euler_values[:2],
            ),
        )
        _assert_raises(
            TypeError,
            lambda: euler_batch.set_bone_targets_pmx_eulers(
                (1.5,),
                euler_positions[:1],
                euler_values[:1],
            ),
        )
        _assert_raises(
            TypeError,
            lambda: euler_batch.set_bone_targets_pmx_eulers(
                ("0",),
                euler_positions[:1],
                euler_values[:1],
            ),
        )
        _assert_raises(
            ValueError,
            lambda: euler_batch.set_bone_targets_pmx_eulers(
                (0, 1),
                euler_positions[:1],
                euler_values[:2],
            ),
        )
        assert _bytes(euler_batch) == euler_before
        assert _bone_bytes(euler_batch) == euler_bone_before

        for _index in range(5):
            performance.set_bone_targets(entries)
            for index, transform in entries:
                performance.set_bone_target(index, transform)
        batch_durations = []
        single_durations = []
        for _index in range(50):
            started = perf_counter()
            performance.set_bone_targets(entries)
            batch_durations.append((perf_counter() - started) * 1000.0)
            started = perf_counter()
            for index, transform in entries:
                performance.set_bone_target(index, transform)
            single_durations.append((perf_counter() - started) * 1000.0)
        batch_median = statistics.median(batch_durations)
        single_median = statistics.median(single_durations)
        assert batch_median < single_median

        performance_batch = performance.bone_target_pmx_euler_batch(euler_indices)
        performance_batch.set_targets(euler_positions, euler_values)
        for _index in range(5):
            performance_batch.submit()
            for index in range(ENTRY_COUNT):
                performance.set_bone_target(
                    index,
                    _pmx_transform(library, index, 0.375),
                )
        euler_batch_durations = []
        euler_single_durations = []
        for _index in range(50):
            started = perf_counter()
            performance_batch.submit()
            euler_batch_durations.append((perf_counter() - started) * 1000.0)
            started = perf_counter()
            for index in range(ENTRY_COUNT):
                performance.set_bone_target(
                    index,
                    _pmx_transform(library, index, 0.375),
                )
            euler_single_durations.append((perf_counter() - started) * 1000.0)
        euler_batch_median = statistics.median(euler_batch_durations)
        euler_single_median = statistics.median(euler_single_durations)
        assert euler_batch_median < euler_single_median
        print(
            "MMD_PHYSICS_BONE_TARGET_BATCH_OK",
            f"target={target}",
            f"entries={ENTRY_COUNT}",
            "equivalence=bit_exact",
            "fallback=bit_exact",
            "pmx_euler_batch=bit_exact",
            "pmx_euler_fallback=bit_exact",
            "invalid_input_validation=atomic",
            "strict_indices=ok",
            "rotated_modes=0/1/2",
            f"single_median_ms={single_median:.6f}",
            f"batch_median_ms={batch_median:.6f}",
            f"speedup={single_median / batch_median:.3f}",
            f"euler_single_median_ms={euler_single_median:.6f}",
            f"euler_batch_median_ms={euler_batch_median:.6f}",
            f"euler_speedup={euler_single_median / euler_batch_median:.3f}",
        )
    finally:
        for solver in solvers:
            solver.close()


for solver_target in ("MMD", "PMX"):
    _run(solver_target)
