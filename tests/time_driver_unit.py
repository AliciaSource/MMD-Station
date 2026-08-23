import importlib.util
import pathlib
import struct
import tempfile


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = (
    PROJECT_ROOT
    / "mmd_skirt_proxy_creator"
    / "physics_preview"
    / "time_driver.py"
)


def load_time_driver_module():
    spec = importlib.util.spec_from_file_location("physics_preview_time_driver", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_test_vmd(path):
    header = b"Vocaloid Motion Data 0002".ljust(30, b"\0")
    model_name = "TimeDriverFixture".encode("shift_jis").ljust(20, b"\0")
    frames = (
        (0, (0.0, 0.0, 0.0)),
        (1, (0.2, 0.0, 0.0)),
        (3, (0.8, 0.0, 0.0)),
        (6, (0.8, 0.0, 0.0)),
        (10, (-0.4, 0.0, 0.0)),
    )
    payload = bytearray(header + model_name + struct.pack("<I", len(frames)))
    interpolation = bytes((20, 20, 107, 107)) * 16
    for frame, location in frames:
        payload.extend("センター".encode("shift_jis").ljust(15, b"\0"))
        payload.extend(struct.pack("<I3f4f", frame, *location, 0.0, 0.0, 0.0, 1.0))
        payload.extend(interpolation)
    payload.extend(struct.pack("<I", 0))
    payload.extend(struct.pack("<I", 0))
    payload.extend(struct.pack("<I", 0))
    payload.extend(struct.pack("<I", 0))
    payload.extend(struct.pack("<I", 0))
    path.write_bytes(payload)
    return frames


def read_test_vmd_frames(path):
    data = memoryview(path.read_bytes())
    offset = 50
    count = struct.unpack_from("<I", data, offset)[0]
    offset += 4
    frames = []
    for _index in range(count):
        frame = struct.unpack_from("<I", data, offset + 15)[0]
        location = struct.unpack_from("<3f", data, offset + 19)
        frames.append((frame, location))
        offset += 111
    return tuple(frames)


time_driver = load_time_driver_module()
PreviewTimeDriver = time_driver.PreviewTimeDriver
PreviewDeadlineScheduler = time_driver.PreviewDeadlineScheduler

deadline = PreviewDeadlineScheduler(minimum_delay=0.001)
first_delay = deadline.next_delay(
    started=0.0,
    finished=0.020,
    interval=1.0 / 60.0,
)
assert first_delay == 0.001
second_started = 0.021
second_finished = 0.025
second_delay = deadline.next_delay(
    started=second_started,
    finished=second_finished,
    interval=1.0 / 60.0,
)
assert abs(second_finished + second_delay - 2.0 / 60.0) < 1.0e-12
deadline.next_delay(started=0.2, finished=0.3, interval=1.0 / 60.0)
assert deadline.deadline == 0.3
deadline.reset()
assert deadline.deadline is None

with tempfile.TemporaryDirectory(prefix="mmd-time-driver-") as temporary_directory:
    vmd_path = pathlib.Path(temporary_directory) / "time_driver_fixture.vmd"
    expected_frames = write_test_vmd(vmd_path)
    parsed_frames = read_test_vmd_frames(vmd_path)
    assert tuple(frame for frame, _location in parsed_frames) == tuple(
        frame for frame, _location in expected_frames
    )

    driver = PreviewTimeDriver(fixed_hz=60, max_substeps=10)
    first = driver.sample(scene_seconds=0.0, wall_seconds=100.0, playing=True)
    assert abs(first.step_seconds - 1.0 / 60.0) < 1.0e-12

    playback_steps = []
    jittered_wall_times = (100.004, 100.041, 100.045, 100.120)
    for (frame, _location), wall_seconds in zip(parsed_frames[1:], jittered_wall_times):
        decision = driver.sample(
            scene_seconds=frame / 30.0,
            wall_seconds=wall_seconds,
            playing=True,
        )
        playback_steps.append(decision.step_seconds)
    assert all(
        abs(actual - expected) < 1.0e-12
        for actual, expected in zip(
            playback_steps,
            (1.0 / 30.0, 2.0 / 30.0, 3.0 / 30.0, 4.0 / 30.0),
        )
    )

    alternate_driver = PreviewTimeDriver(fixed_hz=60, max_substeps=10)
    alternate_steps = []
    for (frame, _location), wall_seconds in zip(
        parsed_frames,
        (200.000, 200.030, 200.031, 200.140, 200.141),
    ):
        alternate_steps.append(
            alternate_driver.sample(
                scene_seconds=frame / 30.0,
                wall_seconds=wall_seconds,
                playing=True,
            ).step_seconds
        )
    assert all(
        abs(actual - expected) < 1.0e-12
        for actual, expected in zip(
            alternate_steps,
            (1.0 / 60.0, *playback_steps),
        )
    )

    mode_switch = driver.sample(
        scene_seconds=10.0 / 30.0,
        wall_seconds=100.130,
        playing=False,
    )
    assert mode_switch.step_seconds == 0.0

    manual_steps = []
    for wall_seconds in (100.146, 100.179, 100.187):
        decision = driver.sample(
            scene_seconds=10.0 / 30.0,
            wall_seconds=wall_seconds,
            playing=False,
        )
        manual_steps.append(decision.step_seconds)
    assert all(
        abs(actual - expected) < 1.0e-12
        for actual, expected in zip(manual_steps, (0.016, 0.033, 0.008))
    )

    stalled = driver.sample(
        scene_seconds=10.0 / 30.0,
        wall_seconds=102.187,
        playing=False,
    )
    assert abs(stalled.step_seconds - 10.0 / 60.0) < 1.0e-12

    seek = driver.sample(
        scene_seconds=2.0 / 30.0,
        wall_seconds=100.200,
        playing=False,
    )
    assert seek.reset_required
    assert seek.step_seconds == 0.0

assert not vmd_path.exists()
print("MMD_TIME_DRIVER_UNIT_OK")
