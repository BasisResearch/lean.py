from lean_py.utils import run_command
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
EXAMPLES_LEAN_PATH = REPO_ROOT / "examples" / "lean"
        
def build_examples():
    run_command(["lake", "build"], cwd = EXAMPLES_LEAN_PATH)

def find_examples_dylib() -> Path:
    build_examples()
    for ext in [".so", ".dylib", ".dll"]:
        dll_files = EXAMPLES_LEAN_PATH.rglob(f"*{ext}")
        if (res := next(dll_files, None)):
            return res
    raise RuntimeError("dll file not found for examples")
