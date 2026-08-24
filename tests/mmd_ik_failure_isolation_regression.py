import sys
from pathlib import Path

import bpy


REPO = Path(r"D:\MOD\BlenderAddonProjects\MMD-Skirt-Proxy-Creator")
sys.path.insert(0, str(REPO))

from mmd_skirt_proxy_creator.mmd_ik_runtime import evaluator
from mmd_skirt_proxy_creator.mmd_ik_runtime.ffi import NativeBoneSolver


class SentinelError(RuntimeError):
    pass


class FakeDll:
    def __init__(self):
        self.destroyed = []

    def spx_mmd_bone_destroy(self, instance):
        self.destroyed.append(instance)


class FakeSolver:
    def __init__(self, events=None, fail_close=False):
        self.close_calls = 0
        self.events = events
        self.fail_close = fail_close

    def close(self):
        self.close_calls += 1
        if self.events is not None:
            self.events.append("solver")
        if self.fail_close:
            raise SentinelError("solver")


def expect_sentinel(callable_object):
    try:
        callable_object()
    except SentinelError as error:
        return error
    raise AssertionError("Expected SentinelError")


reset_solver = type("ResetSolver", (), {})()
reset_solver._instance = object()
reset_solver._dll = FakeDll()
reset_solver._live_matrix_index_buffers = {}
reset_solver._create = lambda: (_ for _ in ()).throw(SentinelError("create"))
destroyed_instance = reset_solver._instance
expect_sentinel(lambda: NativeBoneSolver.reset(reset_solver))
assert reset_solver._instance is None
assert reset_solver._dll.destroyed == [destroyed_instance]
NativeBoneSolver.close(reset_solver)
assert reset_solver._dll.destroyed == [destroyed_instance]

close_events = []


class FailingAnimationData:
    @property
    def action(self):
        return None

    @action.setter
    def action(self, _value):
        close_events.append("action")
        raise SentinelError("action")


runtime = type("Runtime", (), {"animation_data": FailingAnimationData()})()
close_solver = FakeSolver(close_events, fail_close=True)
close_session = type("CloseSession", (), {})()
close_session.runtime_object = lambda: runtime
close_session.live = True


def fail_restore_input():
    close_events.append("input")
    raise SentinelError("input")


close_session.restore_input = fail_restore_input
close_session.muted_constraints = ()
close_session.original_action = None
close_session.solver = close_solver
original_restore_constraints = evaluator._restore_constraints


def fail_restore_constraints(*_args):
    close_events.append("constraints")
    raise SentinelError("constraints")


evaluator._restore_constraints = fail_restore_constraints
try:
    error = expect_sentinel(lambda: evaluator.Session.close(close_session))
finally:
    evaluator._restore_constraints = original_restore_constraints
assert str(error) == "input"
assert close_events == ["input", "constraints", "action", "solver"]
assert close_solver.close_calls == 1
assert evaluator.Session.close(close_session) is None
assert close_events == ["input", "constraints", "action", "solver"]
assert close_solver.close_calls == 1


class FakeSession:
    def __init__(self, name, fail_restore=False):
        self.name = name
        self.live = True
        self.suspended = False
        self.fail_restore = fail_restore
        self.restore_calls = []
        self.solver = FakeSolver()

    def restore_input(self, update=True):
        self.restore_calls.append(update)
        if self.fail_restore:
            raise SentinelError(self.name)

    def set_direct_input_isolated(self, enabled):
        self.direct_input_isolated = bool(enabled)
        return True


original_sessions = dict(evaluator._SESSIONS)
try:
    detach_first = FakeSession("detach first", fail_restore=True)
    detach_second = FakeSession("detach second")
    evaluator._SESSIONS.clear()
    evaluator._SESSIONS.update(
        {
            detach_first.name: detach_first,
            detach_second.name: detach_second,
        }
    )
    error = expect_sentinel(evaluator.detach_all_sessions)
    assert str(error) == detach_first.name
    assert detach_first.restore_calls == [True]
    assert detach_second.restore_calls == [True]
    assert detach_first.solver.close_calls == 1
    assert detach_second.solver.close_calls == 1
    assert not evaluator._SESSIONS

    suspend_first = FakeSession("suspend first", fail_restore=True)
    suspend_second = FakeSession("suspend second")
    evaluator._SESSIONS.update(
        {
            suspend_first.name: suspend_first,
            suspend_second.name: suspend_second,
        }
    )
    error = expect_sentinel(evaluator.suspend_sessions_for_undo_redo)
    assert str(error) == suspend_first.name
    assert suspend_first.suspended
    assert suspend_second.suspended
    assert suspend_first.restore_calls == [False]
    assert suspend_second.restore_calls == [False]
finally:
    evaluator._SESSIONS.clear()
    evaluator._SESSIONS.update(original_sessions)

print(
    "MMD_IK_FAILURE_ISOLATION_OK",
    f"reset_destroy_calls={len(reset_solver._dll.destroyed)}",
    f"session_close_calls={close_solver.close_calls}",
    f"detach_close_calls={detach_first.solver.close_calls + detach_second.solver.close_calls}",
    f"suspend_restore_calls={len(suspend_first.restore_calls) + len(suspend_second.restore_calls)}",
)
