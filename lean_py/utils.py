import subprocess
from pathlib import Path

def run_command(args: list[str], **kwargs) -> str:
    """Run command specified by `args` and return the result as a string"""
    res = subprocess.run(args, capture_output=True, **kwargs)
    if res.returncode != 0:
        raise RuntimeError(f"Command {args} returned non-zero exit code: {res.returncode}")
    return bytes.decode(res.stdout).strip()

def _lean_paths() -> list[Path]:
    """Return list of paths to search for lean libraries."""
    lean_path = run_command(['lake', 'env','printenv', 'LEAN_PATH'])
    return [Path(path) for path in lean_path.split(':')]

def find_lean_dynlib() -> Path:
    """
    Find the path to the lean dynlib.
    """
    lean_paths = _lean_paths()
    # Try different extensions based on platform
    for lean_path in lean_paths:
        for ext in [".dylib", ".so", ".dll"]:
            lib_file = lean_path / f"libleanshared{ext}"
            if lib_file.exists():
                return lib_file
    raise RuntimeError(f"Could not find libleanshared in {lean_path}")

