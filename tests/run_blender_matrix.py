"""Run the self-contained Blender regressions with isolated user profiles.

Pass --blender repeatedly for the runtimes to test and --extensions for a
directory containing mmd_tools. No user preferences or input assets are saved.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
CASES = (
    "blender_compat_regression", "blender_optional_dependency_smoke",
    "bone_conversion_isolation_blender", "bone_morph_scale_blender",
    "bone_physics_creator_smoke", "collection_organization_regression",
    "headless_smoke", "i18n_blender_smoke",
    "locked_vertex_group_quick_select_smoke", "locked_vertex_group_weight_merge_smoke",
    "material_identity_blender", "mirror_underscore_suffix_regression",
    "mirror_vertex_group_conversion_smoke", "mmd_coordinate_adapter_test",
    "mmd_display_frame_regression", "mmd_export_profile_regression",
    "mmd_io_regression", "mmd_material_order_regression", "mmd_morph_editor_regression",
    "mmd_ordering_user_control_regression", "mmd_rigid_scale_diagnostic_regression",
    "mmd_shadow_regression", "physics_bake_regression", "physics_pose_alignment_regression",
    "proxy_creation_no_overwrite_smoke", "time_driver_unit",
    "type2_chain_translation_regression", "updater_blender_smoke",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blender", action="append", required=True, type=Path)
    parser.add_argument("--extensions", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--case", action="append")
    parser.add_argument("--manifest", type=Path,
                        help="Optional JSON cases with script, blend, env, args and result fields")
    parser.add_argument("--timeout", type=int, default=360)
    parser.add_argument("--jobs", type=int, help="Concurrent runtimes; use 1 for timing assertions")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    (ROOT / "_temporary_cleanup").mkdir(exist_ok=True)
    cases = json.loads(args.manifest.read_text(encoding="utf-8")) if args.manifest else [
        {"script": case} for case in (args.case or CASES)]

    def run_version(executable):
        version = subprocess.check_output([str(executable), "--version"],
                                          text=True, encoding="utf-8").splitlines()[0]
        directory = output / version.replace(" ", "_")
        directory.mkdir(exist_ok=True)
        results = []
        for spec in cases:
            case = spec.get("name", spec["script"])
            # Keep generated cache paths below the Windows legacy path limit.
            with tempfile.TemporaryDirectory(prefix="matrix-", dir=ROOT / "_temporary_cleanup") as temporary:
                env = os.environ.copy()
                env.update(PYTHONUTF8="1", PYTHONUNBUFFERED="1", TEMP=temporary, TMP=temporary,
                           BLENDER_USER_CONFIG=str(directory / "config"),
                           BLENDER_USER_SCRIPTS=str(directory / "scripts"),
                           BLENDER_USER_EXTENSIONS=str(directory / "extensions"),
                           MMD_TEST_SCRIPT=str(ROOT / "tests" / (spec["script"] + ".py")),
                           MMD_TEST_EXTENSIONS=str(args.extensions.resolve()))
                substitutions = {"temporary": temporary, "version_dir": str(directory)}
                env.update({key: value.format(**substitutions) for key, value in spec.get("env", {}).items()})
                if spec.get("blend"):
                    env["MMD_TEST_BLEND"] = spec["blend"].format(**substitutions)
                command = [str(executable), "--background", "--factory-startup",
                           "--python-exit-code", "1", "--python",
                           str(ROOT / "tests" / "blender_test_bootstrap.py")]
                if spec.get("args"):
                    command += ["--", *(value.format(**substitutions) for value in spec["args"])]
                started = time.monotonic()
                log_path = directory / (case + ".log")
                try:
                    with log_path.open("w", encoding="utf-8") as capture:
                        result = subprocess.run(command, env=env, cwd=ROOT,
                                                stdout=capture, stderr=subprocess.STDOUT,
                                                timeout=args.timeout)
                    log = log_path.read_text(encoding="utf-8", errors="replace")
                    passed = result.returncode == 0 and "MATRIX_CASE_OK" in log
                    code = result.returncode
                    if passed and spec.get("result"):
                        result_file = Path(spec["result"].format(**substitutions))
                        report = json.loads(result_file.read_text(encoding="utf-8"))
                        passed = report.get("ok") is True
                        if not passed:
                            log += "\n" + json.dumps(report, ensure_ascii=False)
                except subprocess.TimeoutExpired as error:
                    log = log_path.read_text(encoding="utf-8", errors="replace") + "\n" + str(error)
                    passed, code = False, "timeout"
                except (OSError, ValueError) as error:
                    log = f"Test infrastructure error: {error}"
                    passed, code = False, "infrastructure"
                row = dict(version=version, case=case, passed=passed, code=code,
                           seconds=round(time.monotonic() - started, 2))
                log_path.write_text(log, encoding="utf-8")
                results.append(row)
                print(json.dumps(row), flush=True)
                (directory / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        return results

    with ThreadPoolExecutor(max_workers=args.jobs or len(args.blender)) as executor:
        results = [row for group in executor.map(run_version, args.blender) for row in group]
    (output / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    raise SystemExit(0 if all(row["passed"] for row in results) else 1)


if __name__ == "__main__":
    main()
