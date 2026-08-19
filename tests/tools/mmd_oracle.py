import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid
import ctypes
from ctypes import wintypes
from pathlib import Path

from .oracle_cache import file_sha256


class MMDOracleError(RuntimeError):
    pass


_ORACLE_SCRIPT = '''from mmdbridge import *
import json
import os
import struct
import traceback

output = os.environ["MMD_IK_ORACLE"]
arm_path = output + ".arm"
last_path = output + ".last"
frame = get_frame_number()
try:
    if os.path.exists(arm_path) and get_object_size() > 0:
        last = None
        if os.path.exists(last_path):
            with open(last_path, "r", encoding="ascii") as handle:
                last = int(handle.read().strip())
        if frame != last:
            objects = []
            for object_index in range(get_object_size()):
                bones = []
                for bone_index in range(get_bone_size(object_index)):
                    matrix = list(get_bone_matrix(object_index, bone_index))
                    bones.append([get_bone_name(object_index, bone_index), struct.pack("<16f", *matrix).hex()])
                objects.append([get_object_filename(object_index), bones])
            with open(output, "a", encoding="utf-8", newline="\\n") as handle:
                handle.write(json.dumps({"frame": frame, "objects": objects}, ensure_ascii=False, separators=(",", ":")) + "\\n")
            with open(last_path, "w", encoding="ascii", newline="\\n") as handle:
                handle.write(str(frame))
except Exception:
    with open(output + ".error", "a", encoding="utf-8", newline="\\n") as handle:
        handle.write(traceback.format_exc() + "\\n")
'''


def _binary(name):
    return Path(__file__).with_name("bin") / name


class _StartupInfoW(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("lpReserved", wintypes.LPWSTR),
        ("lpDesktop", wintypes.LPWSTR),
        ("lpTitle", wintypes.LPWSTR),
        ("dwX", wintypes.DWORD),
        ("dwY", wintypes.DWORD),
        ("dwXSize", wintypes.DWORD),
        ("dwYSize", wintypes.DWORD),
        ("dwXCountChars", wintypes.DWORD),
        ("dwYCountChars", wintypes.DWORD),
        ("dwFillAttribute", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("wShowWindow", wintypes.WORD),
        ("cbReserved2", wintypes.WORD),
        ("lpReserved2", ctypes.POINTER(wintypes.BYTE)),
        ("hStdInput", wintypes.HANDLE),
        ("hStdOutput", wintypes.HANDLE),
        ("hStdError", wintypes.HANDLE),
    ]


class _ProcessInformation(ctypes.Structure):
    _fields_ = [
        ("hProcess", wintypes.HANDLE),
        ("hThread", wintypes.HANDLE),
        ("dwProcessId", wintypes.DWORD),
        ("dwThreadId", wintypes.DWORD),
    ]


def _launch_injected(executable, working_directory, hook, environment):
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateProcessW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.LPWSTR,
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.BOOL,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.LPCWSTR,
        ctypes.POINTER(_StartupInfoW),
        ctypes.POINTER(_ProcessInformation),
    ]
    kernel32.VirtualAllocEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_size_t, wintypes.DWORD, wintypes.DWORD]
    kernel32.VirtualAllocEx.restype = ctypes.c_void_p
    kernel32.WriteProcessMemory.argtypes = [
        wintypes.HANDLE,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_size_t),
    ]
    kernel32.CreateRemoteThread.argtypes = [
        wintypes.HANDLE,
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.c_void_p,
    ]
    kernel32.CreateRemoteThread.restype = wintypes.HANDLE
    kernel32.VirtualFreeEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_size_t, wintypes.DWORD]
    startup = _StartupInfoW()
    startup.cb = ctypes.sizeof(startup)
    process = _ProcessInformation()
    command_line = ctypes.create_unicode_buffer(f'"{executable}"')
    environment_block = "\0".join(f"{key}={value}" for key, value in sorted(environment.items())) + "\0\0"
    environment_buffer = ctypes.create_unicode_buffer(environment_block)
    created = kernel32.CreateProcessW(
        str(executable),
        command_line,
        None,
        None,
        False,
        0x00000004 | 0x00000400 | 0x08000000,
        environment_buffer,
        str(working_directory),
        ctypes.byref(startup),
        ctypes.byref(process),
    )
    if not created:
        raise ctypes.WinError(ctypes.get_last_error())
    remote_memory = None
    remote_thread = None
    try:
        def inject_library(library):
            nonlocal remote_memory, remote_thread
            hook_buffer = (str(library) + "\0").encode("utf-16-le")
            remote_memory = kernel32.VirtualAllocEx(process.hProcess, None, len(hook_buffer), 0x3000, 0x04)
            if not remote_memory:
                raise ctypes.WinError(ctypes.get_last_error())
            written = ctypes.c_size_t()
            if not kernel32.WriteProcessMemory(process.hProcess, remote_memory, hook_buffer, len(hook_buffer), ctypes.byref(written)):
                raise ctypes.WinError(ctypes.get_last_error())
            load_library = ctypes.cast(kernel32.LoadLibraryW, ctypes.c_void_p).value
            remote_thread = kernel32.CreateRemoteThread(process.hProcess, None, 0, load_library, remote_memory, 0, None)
            if not remote_thread:
                raise ctypes.WinError(ctypes.get_last_error())
            if kernel32.WaitForSingleObject(remote_thread, 30000) != 0:
                raise MMDOracleError("MMD headless runtime injection timed out")
            module_handle = wintypes.DWORD()
            if not kernel32.GetExitCodeThread(remote_thread, ctypes.byref(module_handle)) or not module_handle.value:
                raise MMDOracleError("MMD headless runtime injection failed")
            kernel32.CloseHandle(remote_thread)
            remote_thread = None
            kernel32.VirtualFreeEx(process.hProcess, remote_memory, 0, 0x8000)
            remote_memory = None

        inject_library(hook)
        trace_hook = environment.get("MMD_IK_TRACE_HOOK")
        if trace_hook:
            inject_library(trace_hook)
        if kernel32.ResumeThread(process.hThread) == 0xFFFFFFFF:
            raise ctypes.WinError(ctypes.get_last_error())
        return int(process.dwProcessId)
    except Exception:
        kernel32.TerminateProcess(process.hProcess, 1)
        raise
    finally:
        if remote_thread:
            kernel32.CloseHandle(remote_thread)
        if remote_memory:
            kernel32.VirtualFreeEx(process.hProcess, remote_memory, 0, 0x8000)
        kernel32.CloseHandle(process.hThread)
        kernel32.CloseHandle(process.hProcess)


def _validate_mmd_directory(path):
    directory = Path(path)
    executable = directory / "MikuMikuDance.exe"
    if not executable.is_file():
        raise MMDOracleError("所选目录中找不到 MikuMikuDance.exe")
    if not (directory / "d3d9.dll").is_file():
        raise MMDOracleError("所选 MMD 缺少 MMDBridge，无法读取精确骨骼矩阵")
    return directory


def _read_frames(path):
    frames = set()
    if path.exists():
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    frames.add(int(json.loads(line)["frame"]))
    return frames


def _mmd_pids():
    output = subprocess.check_output(
        ["tasklist", "/FI", "IMAGENAME eq MikuMikuDance.exe", "/FO", "CSV", "/NH"],
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    result = set()
    for line in output.splitlines():
        if line.startswith('"MikuMikuDance.exe"'):
            result.add(int(line.split(",")[1].strip('"')))
    return result


def _find_main_window(pid, timeout=20):
    user32 = ctypes.windll.user32
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        matches = []

        @callback_type
        def callback(hwnd, _lparam):
            owner = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
            class_name = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, class_name, 256)
            if owner.value == pid and class_name.value == "Polygon Movie Maker":
                matches.append(hwnd)
            return True

        user32.EnumWindows(callback, 0)
        if matches:
            return matches[0]
        time.sleep(0.1)
    raise MMDOracleError("找不到隐藏的 MMD 主窗口")


def _run_mmd_commands(pid):
    user32 = ctypes.windll.user32
    user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.SendMessageW.restype = ctypes.c_ssize_t
    hwnd = _find_main_window(pid)
    if user32.IsWindowVisible(hwnd):
        raise MMDOracleError("MMD headless 窗口未保持隐藏")
    user32.SendMessageW(hwnd, 0x0111, 0x0110, 0)
    user32.SendMessageW(hwnd, 0x0111, 435, 0)
    combo = user32.GetDlgItem(hwnd, 436)
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        if user32.SendMessageW(combo, 0x0146, 0, 0) >= 2:
            break
        time.sleep(0.5)
    else:
        raise MMDOracleError("MMD 未能载入 PMX 模型")
    user32.SendMessageW(hwnd, 0x0111, 0x00D1, 0)
    time.sleep(8)
    user32.SendMessageW(hwnd, 0x0111, 0x03FC, 0)
    time.sleep(2)
    user32.SendMessageW(hwnd, 0x0111, 0x00DF, 0)


def bake(mmd_directory, pmx_path, vmd_path, output_path, start_frame, end_frame, fps=30, timeout=600):
    mmd_directory = _validate_mmd_directory(mmd_directory)
    pmx_path = Path(pmx_path)
    vmd_path = Path(vmd_path)
    output_path = Path(output_path)
    if not pmx_path.is_file() or pmx_path.suffix.lower() != ".pmx":
        raise MMDOracleError("请选择有效的 PMX 源文件")
    if not vmd_path.is_file() or vmd_path.suffix.lower() != ".vmd":
        raise MMDOracleError("请选择有效的 VMD 动作")
    start_frame = int(start_frame)
    end_frame = int(end_frame)
    if end_frame < start_frame:
        raise MMDOracleError("MMD 结束帧不能小于开始帧")
    hook = _binary("mmd_headless_hook.dll")
    if not hook.is_file():
        raise MMDOracleError("插件缺少 MMD headless runtime")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="spx-mmd-oracle-"))
    isolated = work / "mmd"
    mmd_pids = set()
    try:
        copy_result = subprocess.run(
            [
                "robocopy",
                str(mmd_directory),
                str(isolated),
                "/E",
                "/XD",
                "UserFile",
                "out",
                "__pycache__",
                "/XF",
                "*.avi",
                "/MT:16",
                "/NFL",
                "/NDL",
                "/NJH",
                "/NJS",
                "/NP",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if copy_result.returncode >= 8:
            raise MMDOracleError(f"无法创建隔离 MMD runtime：robocopy {copy_result.returncode}")
        (isolated / "mmdbridge_vmd.py").write_text(_ORACLE_SCRIPT, encoding="utf-8", newline="\n")
        shutil.rmtree(isolated / "__pycache__", ignore_errors=True)
        raw_output = work / "oracle.jsonl"
        raw_output.with_suffix(raw_output.suffix + ".arm").write_text("1", encoding="ascii")
        avi_path = work / "oracle.avi"
        log_path = work / "headless.log"
        env = os.environ.copy()
        env.update(
            {
                "MMD_IK_ORACLE": str(raw_output),
                "MMD_HEADLESS_START": str(start_frame),
                "MMD_HEADLESS_END": str(end_frame),
                "MMD_HEADLESS_FPS": str(int(fps)),
            }
        )
        env.update(
            {
                "MMD_HEADLESS_PMX": str(pmx_path),
                "MMD_HEADLESS_VMD": str(vmd_path),
                "MMD_HEADLESS_AVI": str(avi_path),
                "MMD_HEADLESS_LOG": str(log_path),
            }
        )
        pid = _launch_injected(isolated / "MikuMikuDance.exe", isolated, hook, env)
        mmd_pids = {pid}
        _run_mmd_commands(pid)
        deadline = time.monotonic() + timeout
        expected = set(range(start_frame, end_frame + 1))
        error_path = Path(str(raw_output) + ".error")
        while time.monotonic() < deadline:
            if error_path.exists():
                raise MMDOracleError(error_path.read_text(encoding="utf-8", errors="replace"))
            frames = _read_frames(raw_output)
            if expected.issubset(frames):
                break
            if not _mmd_pids().intersection(mmd_pids) and not raw_output.exists():
                raise MMDOracleError("MMD headless 进程提前退出，未生成缓存")
            time.sleep(0.25)
        else:
            raise MMDOracleError("MMD headless 精确缓存超时")
        records = {}
        with raw_output.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    record = json.loads(line)
                    frame = int(record["frame"])
                    if frame in expected:
                        records[frame] = record
        missing = sorted(expected.difference(records))
        if missing:
            raise MMDOracleError(f"MMD 精确缓存缺少帧：{missing[:8]}")
        temporary = output_path.with_name(f".{output_path.name}.{uuid.uuid4().hex}.tmp")
        metadata = {
            "schema": 1,
            "pmx_sha256": file_sha256(pmx_path),
            "vmd_sha256": file_sha256(vmd_path),
            "physics": "disabled",
        }
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            for frame in sorted(records):
                record = records[frame]
                record["spx_mmd_ik"] = metadata
                handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
        os.replace(temporary, output_path)
        return output_path, len(records)
    finally:
        for pid in mmd_pids:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        shutil.rmtree(work, ignore_errors=True)
