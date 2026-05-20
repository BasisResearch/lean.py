"""Utility helpers for finding the active Lean toolchain and shared libraries."""

from __future__ import annotations

import os
import subprocess
import sys
from functools import lru_cache
from pathlib import Path


def run_command(args: list[str], **kwargs) -> str:
    """Run a command and return the trimmed stdout."""
    res = subprocess.run(args, capture_output=True, **kwargs)
    if res.returncode != 0:
        stderr = res.stderr.decode(errors="replace") if res.stderr else ""
        raise RuntimeError(
            f"Command {args} exited with {res.returncode}: {stderr}"
        )
    return res.stdout.decode().strip()


@lru_cache(maxsize=1)
def lean_toolchain_version() -> str:
    """Return the lean-toolchain string (e.g. ``leanprover/lean4:v4.29.1``).

    Reads from the repo-root ``lean-toolchain`` file if available,
    otherwise falls back to parsing ``lean --version``.
    """
    tc = Path(__file__).resolve().parent.parent / "lean-toolchain"
    if tc.exists():
        return tc.read_text().strip()
    # Fallback: parse "Lean (version 4.x.y, ...)"
    out = run_command(["lean", "--version"])
    # Extract "leanprover/lean4:vX.Y.Z" from version string
    for part in out.split():
        if part.startswith("4.") or part.startswith("v4."):
            v = part.rstrip(",").lstrip("v")
            return f"leanprover/lean4:v{v}"
    return out


@lru_cache(maxsize=1)
def lean_prefix() -> Path:
    """Return the path printed by `lean --print-prefix`."""
    return Path(run_command(["lean", "--print-prefix"]))


def lean_lib_dir() -> Path:
    """Where Lean's own shared libraries live."""
    return lean_prefix() / "lib" / "lean"


def lean_include_dir() -> Path:
    """Directory containing `lean/lean.h`."""
    return lean_prefix() / "include"


@lru_cache(maxsize=1)
def shared_lib_extension() -> str:
    if sys.platform == "darwin":
        return ".dylib"
    if sys.platform == "win32":
        return ".dll"
    return ".so"


def find_lean_dynlib() -> Path:
    """Locate `libleanshared.<ext>` in the active toolchain's `lib/lean`.

    Set ``LEANPY_LIBLEAN`` to override — useful for pointing at an
    ASAN-instrumented ``libleanshared.so`` on a debug box.
    """
    if env := os.environ.get("LEANPY_LIBLEAN"):
        return Path(env)
    ext = shared_lib_extension()
    lib = lean_lib_dir() / f"libleanshared{ext}"
    if lib.exists():
        return lib
    # Fallback: scan LEAN_PATH (less reliable, retained for back-compat).
    try:
        out = run_command(["lake", "env", "printenv", "LEAN_PATH"])
        for d in out.split(":"):
            cand = Path(d) / f"libleanshared{ext}"
            if cand.exists():
                return cand
    except Exception:
        pass
    raise RuntimeError(f"libleanshared{ext} not found in {lean_lib_dir()}")


def all_lean_runtime_libs() -> list[Path]:
    """All shared libs in `lib/lean` that are likely needed at load time.

    Includes `libleanshared`, `libleanshared_*`, `libLake_shared`, and any
    other `lib*shared.<ext>` siblings.
    """
    ext = shared_lib_extension()
    d = lean_lib_dir()
    if not d.exists():
        return []
    libs = sorted(d.glob(f"lib*shared*{ext}"))
    # `libleanshared` should typically be loaded *after* `libleanshared_1/2`
    # because it depends on them; sorting alphabetically achieves this.
    return libs


def add_lean_lib_to_dyld_path() -> None:
    """Add Lean's `lib/lean` to the OS-level dynamic-loader search path
    for the current process. Useful before constructing a `LeanLibrary`
    when the dylib has unresolved `@rpath` references to Lean's runtime.
    """
    d = str(lean_lib_dir())
    key = "DYLD_LIBRARY_PATH" if sys.platform == "darwin" else "LD_LIBRARY_PATH"
    existing = os.environ.get(key, "")
    if d not in existing.split(":"):
        os.environ[key] = f"{d}:{existing}" if existing else d
