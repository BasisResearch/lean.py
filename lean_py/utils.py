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
        raise RuntimeError(f"Command {args} exited with {res.returncode}: {stderr}")
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


PREFIX_ENV = "LEANPY_LEAN_PREFIX"
"""An explicit toolchain sysroot (what ``lean --print-prefix`` prints)."""

TOOLCHAIN_ENV = "LEANPY_TOOLCHAIN"
"""An explicit toolchain, e.g. ``leanprover/lean4:v4.35.0``, for elan."""

_pinned: str | None = None


def toolchain_of(path: str | os.PathLike) -> str | None:
    """The toolchain a ``lean-toolchain`` file names, given the file or the
    directory holding it; ``None`` if there is none."""
    p = Path(path)
    f = p / "lean-toolchain" if p.is_dir() else p
    return f.read_text().strip() if f.is_file() else None


def set_toolchain(toolchain: str | os.PathLike | None) -> None:
    """Pin the toolchain :func:`lean_prefix` resolves: a toolchain name, or a
    ``lean-toolchain`` file or the directory holding one (``None`` unpins).

    Takes effect for the runtime only if it has not been loaded yet (the
    first :class:`~lean_py.LeanLibrary` loads it, and it cannot change in a
    process)."""
    global _pinned
    if toolchain is None:
        _pinned = None
    else:
        p = Path(toolchain)
        _pinned = toolchain_of(p) if p.exists() else str(toolchain)
    lean_prefix.cache_clear()


def pinned_toolchain() -> str | None:
    """The toolchain pinned by :func:`set_toolchain` or ``LEANPY_TOOLCHAIN``."""
    return _pinned or os.environ.get(TOOLCHAIN_ENV) or None


@lru_cache(maxsize=1)
def lean_prefix() -> Path:
    """The Lean toolchain's sysroot, independent of the current directory.

    In order: ``LEANPY_LEAN_PREFIX``; the toolchain pinned by
    :func:`set_toolchain` or ``LEANPY_TOOLCHAIN`` (or elan's own
    ``ELAN_TOOLCHAIN``); lean.py's own ``lean-toolchain`` when it runs from a
    checkout; else ``lean --print-prefix`` as elan resolves it from the
    current directory (the old behaviour). A toolchain is resolved by
    running ``lean --print-prefix`` with ``ELAN_TOOLCHAIN`` set, which elan
    honours over any ``lean-toolchain`` file.
    """
    if explicit := os.environ.get(PREFIX_ENV):
        return Path(explicit)
    toolchain = (
        pinned_toolchain()
        or os.environ.get("ELAN_TOOLCHAIN")
        or toolchain_of(Path(__file__).resolve().parent.parent)
    )
    env = None if toolchain is None else {**os.environ, "ELAN_TOOLCHAIN": toolchain}
    return Path(run_command(["lean", "--print-prefix"], env=env))


def bundle_dir() -> Path | None:
    """Directory of a self-contained library bundle, if one is active.

    When ``LEANPY_BUNDLE_DIR`` is set (e.g. by a wheel-installed library's
    loader), the Lean runtime shared libraries and the user dylib have been
    vendored and relocated there, so we can resolve everything without an
    installed toolchain. See :mod:`lean_py.packaging`.
    """
    d = os.environ.get("LEANPY_BUNDLE_DIR")
    return Path(d) if d else None


def lean_lib_dir() -> Path:
    """Where Lean's own shared libraries live."""
    if b := bundle_dir():
        return b
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
    if bundle_dir():
        # In a bundle we must not fall through to a toolchain lookup.
        raise RuntimeError(f"libleanshared{ext} not found in bundle {lean_lib_dir()}")
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
