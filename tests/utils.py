import os
import subprocess
from pathlib import Path

from lean_py.utils import run_command

REPO_ROOT = Path(__file__).parent.parent
EXAMPLES_LEAN_PATH = REPO_ROOT / "examples" / "lean"


def _ensure_lean_lib_path():
    """Ensure DYLD_LIBRARY_PATH/LD_LIBRARY_PATH includes Lean's lib directory."""
    try:
        lean_prefix = subprocess.run(
            ["lean", "--print-prefix"],
            capture_output=True, text=True
        ).stdout.strip()
    except FileNotFoundError:
        return
    lib_dir = os.path.join(lean_prefix, "lib", "lean")
    import sys
    if sys.platform == "darwin":
        key = "DYLD_LIBRARY_PATH"
    else:
        key = "LD_LIBRARY_PATH"
    existing = os.environ.get(key, "")
    if lib_dir not in existing:
        os.environ[key] = f"{lib_dir}:{existing}" if existing else lib_dir


def build_examples():
    run_command(["lake", "build"], cwd=EXAMPLES_LEAN_PATH)


def find_examples_dylib() -> Path:
    _ensure_lean_lib_path()
    build_examples()
    for ext in [".so", ".dylib", ".dll"]:
        dll_files = EXAMPLES_LEAN_PATH.rglob(f"*{ext}")
        if (res := next(dll_files, None)):
            return res
    raise RuntimeError("dll file not found for examples")
