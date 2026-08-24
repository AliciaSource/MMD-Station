import ctypes
from array import array
import math
import statistics
import sys
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace

import bpy
from mathutils import Matrix


REPO = Path(r"D:\MOD\BlenderAddonProjects\MMD-Skirt-Proxy-Creator")
sys.path.insert(0, str(REPO))

from mmd_skirt_proxy_creator.mmd_ik_runtime import evaluator
from mmd_skirt_proxy_creator.mmd_ik_runtime.ffi import NativeBoneSolver


def assert_runtime_error(callable_object):
    try:
        callable_object()
    except RuntimeError:
        return
    raise AssertionError("Expected RuntimeError")


def assert_error(error_type, callable_object):
    try:
        callable_object()
    except error_type:
        return
    raise AssertionError(f"Expected {error_type.__name__}")


def median_ms(callable_object, iterations=40):
    durations = []
    for _index in range(iterations):
        started = perf_counter()
        callable_object()
        durations.append((perf_counter() - started) * 1000.0)
    return statistics.median(durations)


def reference_direct_live_matrix_buffers(session):
    position_buffer = array("f")
    basis_buffer = array("f")
    inverse_scale = 1.0 / session.scale
    for _index, pose_bone, rest_orientation_inverse in session.direct_live_bindings:
        head_transform = pose_bone.matrix @ rest_orientation_inverse
        position = head_transform.translation
        position_buffer.extend(
            (
                position.x * inverse_scale,
                position.z * inverse_scale,
                position.y * inverse_scale,
            )
        )
        basis = evaluator._live_rotation_to_mmd_rows(head_transform)
        basis_buffer.extend(value for row in basis for value in row)
    return position_buffer, basis_buffer


def assert_direct_live_buffers_bit_exact(session, actual=None):
    expected = reference_direct_live_matrix_buffers(session)
    if actual is None:
        actual = evaluator._direct_live_matrix_buffers(session)
    assert actual[0].tobytes() == expected[0].tobytes()
    assert actual[1].tobytes() == expected[1].tobytes()
    return actual


def test_direct_live_buffer_reuse():
    pose_bones = [
        SimpleNamespace(
            matrix=(
                Matrix.Translation((0.25, -0.5, 0.75))
                @ Matrix.Rotation(0.17, 4, "X")
            )
        ),
        SimpleNamespace(
            matrix=(
                Matrix.Translation((-1.0, 0.375, 0.125))
                @ Matrix.Rotation(-0.31, 4, "Y")
            )
        ),
        SimpleNamespace(
            matrix=(
                Matrix.Translation((0.625, 1.25, -0.875))
                @ Matrix.Rotation(0.43, 4, "Z")
            )
        ),
    ]
    bindings = (
        (11, pose_bones[0], Matrix.Rotation(-0.09, 4, "Z")),
        (23, pose_bones[1], Matrix.Translation((0.1, -0.2, 0.3))),
        (47, pose_bones[2], Matrix.Rotation(0.22, 4, "X")),
    )
    session = SimpleNamespace(
        direct_live_bindings=bindings,
        scale=0.08,
    )

    first = assert_direct_live_buffers_bit_exact(session)
    first_bytes = (first[0].tobytes(), first[1].tobytes())
    repeated = assert_direct_live_buffers_bit_exact(session)
    assert repeated[0] is first[0]
    assert repeated[1] is first[1]

    session.scale = 0.125
    pose_bones[0].matrix = (
        Matrix.Translation((-0.75, 0.625, 1.5))
        @ Matrix.Rotation(-0.28, 4, "Y")
    )
    mutated = assert_direct_live_buffers_bit_exact(session)
    assert mutated[0] is first[0]
    assert mutated[1] is first[1]
    assert (mutated[0].tobytes(), mutated[1].tobytes()) != first_bytes

    rebound_bones = [
        SimpleNamespace(
            matrix=(
                Matrix.Translation((2.0, -1.0, 0.5))
                @ Matrix.Rotation(0.51, 4, "Z")
            )
        ),
        SimpleNamespace(
            matrix=(
                Matrix.Translation((-0.125, -0.25, -0.5))
                @ Matrix.Rotation(-0.37, 4, "X")
            )
        ),
        SimpleNamespace(
            matrix=(
                Matrix.Translation((0.875, 0.75, 0.625))
                @ Matrix.Rotation(0.19, 4, "Y")
            )
        ),
    ]
    session.direct_live_bindings = (
        (47, rebound_bones[2], Matrix.Translation((0.4, 0.3, 0.2))),
        (11, rebound_bones[0], Matrix.Rotation(-0.33, 4, "Y")),
        (23, rebound_bones[1], Matrix.Rotation(0.27, 4, "Z")),
    )
    first[0][:] = array("f", [12345.5]) * len(first[0])
    first[1][:] = array("f", [-23456.75]) * len(first[1])
    rebound = assert_direct_live_buffers_bit_exact(session)
    assert rebound[0] is first[0]
    assert rebound[1] is first[1]

    session.direct_live_bindings += (
        (
            59,
            SimpleNamespace(
                matrix=(
                    Matrix.Translation((-1.5, 2.25, -3.125))
                    @ Matrix.Rotation(0.63, 4, "X")
                )
            ),
            Matrix.Rotation(-0.41, 4, "Z"),
        ),
    )
    resized = assert_direct_live_buffers_bit_exact(session)
    assert resized[0] is not first[0]
    assert resized[1] is not first[1]
    assert len(resized[0]) == len(session.direct_live_bindings) * 3
    assert len(resized[1]) == len(session.direct_live_bindings) * 9
    resized_again = assert_direct_live_buffers_bit_exact(session)
    assert resized_again[0] is resized[0]
    assert resized_again[1] is resized[1]


test_direct_live_buffer_reuse()


root = bpy.data.objects["\u5408\u5e762"]
pmx_path = Path(root.get("spx_mmd_ik_source_pmx", ""))
if not pmx_path.is_file():
    pmx_path = Path(root["import_folder"]) / "\u5408\u5e762.pmx"
assert pmx_path.is_file(), pmx_path

solvers = [NativeBoneSolver(pmx_path) for _index in range(8)]
try:
    (
        single,
        batch,
        flat,
        flat_fallback,
        fallback,
        expected_empty,
        rejected,
        performance,
    ) = solvers
    assert batch._has_live_matrix_batch
    assert batch._has_bone_transform_batch
    assert batch._has_rigid_target_batch
    assert batch._has_external_rigid_matrix_mmd_batch

    entry_count = min(batch.count, 503)
    entries = []
    for index in range(entry_count):
        angle = (index % 29 - 14) * 0.0025
        cosine = math.cos(angle)
        sine = math.sin(angle)
        rest = batch.rest_positions[index]
        entries.append(
            (
                index,
                (
                    rest[0] + (index % 5) * 0.001,
                    rest[1] - (index % 7) * 0.001,
                    rest[2] + (index % 11) * 0.0005,
                ),
                (
                    (cosine, -sine, 0.0),
                    (sine, cosine, 0.0),
                    (0.0, 0.0, 1.0),
                ),
            )
        )

    flat_indices = tuple(entry[0] for entry in entries)
    flat_positions = array(
        "f",
        (value for _index, position, _basis in entries for value in position),
    )
    flat_bases = array(
        "f",
        (
            value
            for _index, _position, basis in entries
            for row in basis
            for value in row
        ),
    )
    prepared_flat_indices = flat.prepare_live_matrix_indices(flat_indices)
    assert (
        flat.prepare_live_matrix_indices(flat_indices)
        is prepared_flat_indices
    )
    empty_indices = flat.prepare_live_matrix_indices(())
    flat.set_live_matrix_buffers(empty_indices, array("f"), array("f"))

    assert_runtime_error(
        lambda: flat.prepare_live_matrix_indices((0, flat.count))
    )
    assert_error(
        TypeError,
        lambda: flat.prepare_live_matrix_indices((0, 1.5)),
    )
    assert_error(
        TypeError,
        lambda: flat.prepare_live_matrix_indices((0, "1")),
    )
    assert_error(
        ValueError,
        lambda: batch.set_live_matrix_buffers(
            prepared_flat_indices,
            flat_positions,
            flat_bases,
        ),
    )
    assert_error(
        ValueError,
        lambda: flat.set_live_matrix_buffers(
            prepared_flat_indices,
            flat_positions[:-1],
            flat_bases,
        ),
    )
    assert_error(
        ValueError,
        lambda: flat.set_live_matrix_buffers(
            prepared_flat_indices,
            flat_positions,
            flat_bases[:-1],
        ),
    )
    assert_error(
        TypeError,
        lambda: flat.set_live_matrix_buffers(
            prepared_flat_indices,
            array("d", flat_positions),
            flat_bases,
        ),
    )

    single.begin_live_input()
    for entry in entries:
        single.set_live_matrix(*entry)
    batch.begin_live_input()
    batch.set_live_matrices(entries)
    flat.begin_live_input()
    flat.set_live_matrix_buffers(
        prepared_flat_indices,
        flat_positions,
        flat_bases,
    )
    flat_fallback.begin_live_input()
    flat_fallback._has_live_matrix_batch = False
    flat_fallback.set_live_matrix_buffers(
        flat_fallback.prepare_live_matrix_indices(flat_indices),
        flat_positions,
        flat_bases,
    )
    fallback.begin_live_input()
    fallback._has_live_matrix_batch = False
    fallback.set_live_matrices(entries)
    single.evaluate(1.0)
    batch.evaluate(1.0)
    fallback.evaluate(1.0)
    flat.evaluate(1.0)
    flat_fallback.evaluate(1.0)
    assert bytes(single._output) == bytes(batch._output)
    assert bytes(single._output) == bytes(flat._output)
    assert bytes(single._output) == bytes(flat_fallback._output)
    assert bytes(single._output) == bytes(fallback._output)

    flat.reset()
    assert flat.prepare_live_matrix_indices(flat_indices) is prepared_flat_indices
    flat.begin_live_input()
    flat.set_live_matrix_buffers(
        prepared_flat_indices,
        flat_positions,
        flat_bases,
    )
    flat.evaluate(1.0)
    assert bytes(single._output) == bytes(flat._output)
    prepared_after_reset = flat.prepare_live_matrix_indices(flat_indices)
    assert prepared_after_reset is prepared_flat_indices
    assert flat.prepare_live_matrix_indices(flat_indices) is prepared_after_reset
    rebound_indices = tuple(reversed(flat_indices))
    rebound_prepared = flat.prepare_live_matrix_indices(rebound_indices)
    assert rebound_prepared.indices == rebound_indices
    flat.begin_live_input()
    flat.set_live_matrix_buffers(
        rebound_prepared,
        flat_positions,
        flat_bases,
    )
    flat.evaluate(1.0)

    performance.begin_live_input()
    performance_flat_indices = performance.prepare_live_matrix_indices(
        flat_indices
    )
    for _index in range(5):
        performance.set_live_matrices(entries)
        performance.set_live_matrix_buffers(
            performance_flat_indices,
            flat_positions,
            flat_bases,
        )
    live_entries_median = median_ms(
        lambda: performance.set_live_matrices(entries)
    )
    live_buffers_median = median_ms(
        lambda: performance.set_live_matrix_buffers(
            performance_flat_indices,
            flat_positions,
            flat_bases,
        )
    )

    rejected.begin_live_input()
    expected_empty.begin_live_input()
    indices = (ctypes.c_uint32 * 2)(0, rejected.count)
    positions = (ctypes.c_float * 6)(1.0, 2.0, 3.0, 4.0, 5.0, 6.0)
    bases = (ctypes.c_float * 18)(
        1.0,
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
        0.0,
        0.0,
        1.0,
        1.0,
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
        0.0,
        0.0,
        1.0,
    )
    assert not rejected._dll.spx_mmd_bone_set_live_matrices(
        rejected._instance,
        indices,
        positions,
        bases,
        2,
    )
    rejected.evaluate(1.0)
    expected_empty.evaluate(1.0)
    assert bytes(rejected._output) == bytes(expected_empty._output)
    assert_runtime_error(
        lambda: batch.set_live_matrices((entries[0], (batch.count, *entries[1][1:])))
    )
    assert_error(
        TypeError,
        lambda: batch.set_live_matrices((entries[0], (1.5, *entries[1][1:]))),
    )
    assert_error(
        TypeError,
        lambda: batch.set_live_matrices((entries[0], ("1", *entries[1][1:]))),
    )

    bone_indices = tuple(range(entry_count))
    single_bone_payload = tuple(single.transform(index) for index in bone_indices)
    batch_bone_payload = batch.transforms(bone_indices)
    fallback._has_bone_transform_batch = False
    fallback_bone_payload = fallback.transforms(bone_indices)
    assert batch_bone_payload == single_bone_payload
    assert fallback_bone_payload == single_bone_payload

    sentinel_bones = (ctypes.c_float * 14)(
        *(-91.25 + item * 0.125 for item in range(14))
    )
    sentinel_bones_before = bytes(sentinel_bones)
    invalid_bone_indices = (ctypes.c_uint32 * 2)(0, batch.count)
    assert not batch._dll.spx_mmd_bone_transforms(
        batch._instance,
        invalid_bone_indices,
        sentinel_bones,
        2,
    )
    assert bytes(sentinel_bones) == sentinel_bones_before
    assert_runtime_error(lambda: batch.transforms((0, batch.count)))
    assert_error(TypeError, lambda: batch.transforms((0, 1.5)))
    assert_error(TypeError, lambda: batch.transforms((0, "1")))

    rigid_indices = tuple(range(batch.rigid_count))
    single_rigid_payload = tuple(single.rigid_target(index) for index in rigid_indices)
    batch_rigid_payload = batch.rigid_targets(rigid_indices)
    fallback._has_rigid_target_batch = False
    fallback_rigid_payload = fallback.rigid_targets(rigid_indices)
    assert batch_rigid_payload == single_rigid_payload
    assert fallback_rigid_payload == single_rigid_payload

    sentinel_rigids = (ctypes.c_float * 14)(
        *(-72.5 + item * 0.25 for item in range(14))
    )
    sentinel_rigids_before = bytes(sentinel_rigids)
    invalid_rigid_indices = (ctypes.c_uint32 * 2)(0, batch.rigid_count)
    assert not batch._dll.spx_mmd_bone_rigid_targets(
        batch._instance,
        invalid_rigid_indices,
        sentinel_rigids,
        2,
    )
    assert bytes(sentinel_rigids) == sentinel_rigids_before
    assert_runtime_error(lambda: batch.rigid_targets((0, batch.rigid_count)))
    assert_error(TypeError, lambda: batch.rigid_targets((0, 1.5)))
    assert_error(TypeError, lambda: batch.rigid_targets((0, "1")))

    external_entries = []
    for rigid_index in rigid_indices:
        matrix = single.rigid_matrix(rigid_index)
        external_entries.append((rigid_index, matrix[:3], matrix[3:12]))
    assert_error(
        TypeError,
        lambda: batch.set_external_rigid_matrices_mmd(
            ((1.5, external_entries[0][1], external_entries[0][2]),)
        ),
    )
    assert_error(
        TypeError,
        lambda: batch.set_external_rigid_matrices_mmd(
            (("0", external_entries[0][1], external_entries[0][2]),)
        ),
    )
    single.clear_external_transforms()
    batch.clear_external_transforms()
    fallback.clear_external_transforms()
    for external_entry in external_entries:
        single.set_external_rigid_matrix_mmd(*external_entry)
    batch.set_external_rigid_matrices_mmd(external_entries)
    fallback._has_external_rigid_matrix_mmd_batch = False
    fallback.set_external_rigid_matrices_mmd(external_entries)
    single.evaluate_after_physics()
    batch.evaluate_after_physics()
    fallback.evaluate_after_physics()
    assert bytes(single._output) == bytes(batch._output)
    assert bytes(single._output) == bytes(fallback._output)

    dynamic_index = None
    performance.end_live_input()
    for rigid_index in rigid_indices:
        performance.clear_external_transforms()
        performance.evaluate(1.0)
        baseline_output = bytes(performance._output)
        matrix = performance.rigid_matrix(rigid_index)
        performance.set_external_rigid_matrix_mmd(
            rigid_index,
            (matrix[0] + 1.0, matrix[1] - 0.5, matrix[2] + 0.25),
            matrix[3:12],
        )
        performance.evaluate_after_physics()
        if bytes(performance._output) != baseline_output:
            dynamic_index = rigid_index
            break
    assert dynamic_index is not None

    expected_empty.clear_external_transforms()
    rejected.clear_external_transforms()
    expected_empty.end_live_input()
    rejected.end_live_input()
    expected_empty.evaluate(1.0)
    rejected.evaluate(1.0)
    dynamic_matrix = rejected.rigid_matrix(dynamic_index)
    invalid_external_indices = (ctypes.c_uint32 * 2)(
        dynamic_index,
        rejected.rigid_count,
    )
    invalid_external_positions = (ctypes.c_float * 6)(
        dynamic_matrix[0] + 1.0,
        dynamic_matrix[1] - 0.5,
        dynamic_matrix[2] + 0.25,
        0.0,
        0.0,
        0.0,
    )
    invalid_external_bases = (ctypes.c_float * 18)(
        *(dynamic_matrix[3:12] + (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0))
    )
    assert not rejected._dll.spx_mmd_bone_set_external_rigid_matrices_mmd(
        rejected._instance,
        invalid_external_indices,
        invalid_external_positions,
        invalid_external_bases,
        2,
    )
    rejected.evaluate_after_physics()
    expected_empty.evaluate_after_physics()
    assert bytes(rejected._output) == bytes(expected_empty._output)

    rejected.clear_external_transforms()
    expected_empty.clear_external_transforms()
    rejected.evaluate(1.0)
    expected_empty.evaluate(1.0)
    rejected._has_external_rigid_matrix_mmd_batch = False
    assert_runtime_error(
        lambda: rejected.set_external_rigid_matrices_mmd(
            (
                external_entries[dynamic_index],
                (rejected.rigid_count, (0.0, 0.0, 0.0), (1.0,) * 9),
            )
        )
    )
    rejected.evaluate_after_physics()
    expected_empty.evaluate_after_physics()
    assert bytes(rejected._output) == bytes(expected_empty._output)

    performance.clear_external_transforms()
    performance.evaluate(1.0)
    performance._has_bone_transform_batch = True
    performance._has_rigid_target_batch = True
    performance._has_external_rigid_matrix_mmd_batch = True
    for _index in range(5):
        performance.transforms(bone_indices)
        tuple(performance.transform(index) for index in bone_indices)
        performance.rigid_targets(rigid_indices)
        tuple(performance.rigid_target(index) for index in rigid_indices)
        performance.clear_external_transforms()
        performance.set_external_rigid_matrices_mmd(external_entries)
        performance.clear_external_transforms()
        for external_entry in external_entries:
            performance.set_external_rigid_matrix_mmd(*external_entry)

    bone_batch_median = median_ms(lambda: performance.transforms(bone_indices))
    bone_single_median = median_ms(
        lambda: tuple(performance.transform(index) for index in bone_indices)
    )
    rigid_batch_median = median_ms(lambda: performance.rigid_targets(rigid_indices))
    rigid_single_median = median_ms(
        lambda: tuple(performance.rigid_target(index) for index in rigid_indices)
    )

    external_batch_durations = []
    external_single_durations = []
    for _index in range(40):
        performance.clear_external_transforms()
        started = perf_counter()
        performance.set_external_rigid_matrices_mmd(external_entries)
        external_batch_durations.append((perf_counter() - started) * 1000.0)
        performance.clear_external_transforms()
        started = perf_counter()
        for external_entry in external_entries:
            performance.set_external_rigid_matrix_mmd(*external_entry)
        external_single_durations.append((perf_counter() - started) * 1000.0)
    external_batch_median = statistics.median(external_batch_durations)
    external_single_median = statistics.median(external_single_durations)

    print(
        "MMD_BONE_BATCH_FFI_OK",
        f"bones={len(bone_indices)}",
        f"rigids={len(rigid_indices)}",
        "equivalence=bit_exact",
        "invalid_batch=atomic",
        "fallback=bit_exact",
        "flat_reset_reuse=bit_exact",
        f"flat_rebind_count={len(rebound_indices)}",
        "direct_reuse=bit_exact",
        "direct_identity=stable",
        "direct_rebind_overwrite=bit_exact",
        "direct_count_realloc=ok",
        "direct_mutation=bit_exact",
        f"bone_single_ms={bone_single_median:.6f}",
        f"bone_batch_ms={bone_batch_median:.6f}",
        f"bone_speedup={bone_single_median / bone_batch_median:.3f}",
        f"rigid_single_ms={rigid_single_median:.6f}",
        f"rigid_batch_ms={rigid_batch_median:.6f}",
        f"rigid_speedup={rigid_single_median / rigid_batch_median:.3f}",
        f"external_single_ms={external_single_median:.6f}",
        f"external_batch_ms={external_batch_median:.6f}",
        f"external_speedup={external_single_median / external_batch_median:.3f}",
        f"live_entries_ms={live_entries_median:.6f}",
        f"live_buffers_ms={live_buffers_median:.6f}",
        f"live_buffer_speedup={live_entries_median / live_buffers_median:.3f}",
    )
finally:
    for solver in solvers:
        solver.close()
