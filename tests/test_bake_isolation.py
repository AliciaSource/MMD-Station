"""Offline contracts for native-bake isolation and lazy native loading."""

import ast
import importlib.util
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "mmd_station"


def test_registration_does_not_preload_solver():
    tree = ast.parse((PACKAGE / "__init__.py").read_text(encoding="utf-8"))
    register = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "register")
    assert not any(isinstance(n, ast.Name) and n.id == "preload_physics_libraries" for n in ast.walk(register))


def test_scene_guard_never_touches_bpy_from_worker(monkeypatch):
    class ForbiddenBpy:
        __spec__ = None

        def __getattr__(self, name):
            raise AssertionError("Worker accessed bpy: " + name)

    monkeypatch.setitem(sys.modules, "bpy", ForbiddenBpy())
    spec = importlib.util.spec_from_file_location("bake_guard_probe", PACKAGE / "execution_guard.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    results = []
    worker = threading.Thread(target=lambda: results.append(module.scene_access_allowed()))
    worker.start()
    worker.join()
    assert results == [False]


def test_scene_guard_defers_locked_jobs(monkeypatch):
    wm = SimpleNamespace(is_interface_locked=True)
    bpy = SimpleNamespace(context=SimpleNamespace(window_manager=wm))
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    spec = importlib.util.spec_from_file_location("bake_guard_probe", PACKAGE / "execution_guard.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert not module.scene_access_allowed()
    wm.is_interface_locked = False
    assert module.scene_access_allowed()


def test_preview_and_frame_callbacks_check_guard():
    for file, names in {
        "physics_preview/runtime.py": ["_timer_tick"],
        "mmd_ik_runtime/evaluator.py": ["_frame_change_pre", "_frame_change_post", "_depsgraph_update_post"],
        "mmd_morph_editor.py": ["_morph_frame_change", "_migrate_existing_vmd_morph_animations_timer"],
        "sync.py": ["_run_pending_sync", "_sync_on_proxy_mode_exit", "_depsgraph_proxy_update"],
    }.items():
        tree = ast.parse((PACKAGE / file).read_text(encoding="utf-8"))
        for name in names:
            node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
            assert any(isinstance(n, ast.Name) and n.id == "scene_access_allowed" for n in ast.walk(node)), (file, name)


def test_parallel_solver_step_does_not_read_rna():
    tree = ast.parse((PACKAGE / "physics_preview/runtime.py").read_text(encoding="utf-8"))
    world = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "PreviewWorld")
    step = next(n for n in world.body if isinstance(n, ast.FunctionDef) and n.name == "step")
    namespace = {}
    exec(compile(ast.Module(body=[step], type_ignores=[]), "<world-step>", "exec"), namespace)
    calls = []

    class World:
        pending_step_seconds = 1 / 60
        solver = SimpleNamespace(step=lambda *args: calls.append(args))

        @property
        def sessions(self):
            raise AssertionError("Worker read RNA-backed settings")

    worker = threading.Thread(target=namespace["step"], args=(World(), 5))
    worker.start()
    worker.join()
    assert calls == [(1 / 60, 5)]


def test_frame_morph_setup_is_deferred():
    tree = ast.parse((PACKAGE / "mmd_morph_editor.py").read_text(encoding="utf-8"))
    evaluate = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "evaluate_morph_root")
    prepared = []
    namespace = {
        "_EVALUATING": False, "_STRUCTURE_ALLOWED": True,
        "_PENDING_RUNTIME_ROOTS": set(), "_DeferredMorphSetup": type("Deferred", (Exception,), {}),
        "scene_access_allowed": lambda: True,
        "_morph_states_are_current": lambda root: False,
        "ensure_morph_states": lambda root: prepared.append(root),
    }
    exec(compile(ast.Module(body=[evaluate], type_ignores=[]), "<morph-evaluate>", "exec"), namespace)
    namespace["evaluate_morph_root"](SimpleNamespace(name="Model"), allow_structure=False)
    assert not prepared
    assert namespace["_PENDING_RUNTIME_ROOTS"] == {"Model"}
    assert namespace["_STRUCTURE_ALLOWED"] is True
