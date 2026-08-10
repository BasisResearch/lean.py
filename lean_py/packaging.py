"""Bundle a compiled Lean library into a self-contained, installable wheel.

A `LeanLibrary` normally loads the Lake-built dylib and discovers the Lean
runtime shared libraries from the active toolchain (`lean --print-prefix`).
That requires every user to have `elan` and the matching toolchain installed.

This module vendors the dylib together with its Lean runtime dependency closure
into one directory, rewrites their install names / RPATHs so they resolve each
other via ``@loader_path`` (macOS) or ``$ORIGIN`` (Linux), and packages the
result as a wheel with a tiny loader. Installing that wheel needs no toolchain.

Note on wheel tags: lean.py binds through **ctypes**, not a CPython C
extension, so the wheel is ABI-independent — it is tagged ``py3-none-<platform>``
(pure-Python loader plus platform-specific data dylibs), not ``abi3``. The
platform-specific part is the vendored dylibs, not a compiled extension.

    python -m lean_py.packaging build path/to/project MyLib --version 0.1.0 -o dist/

or programmatically::

    from lean_py.packaging import build_wheel
    build_wheel("path/to/project", "MyLib", version="0.1.0", out_dir="dist")
"""

from __future__ import annotations

import base64
import hashlib
import os
import shutil
import subprocess
import sys
import sysconfig
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from lean_py.utils import all_lean_runtime_libs, find_lean_dynlib, shared_lib_extension

_LIBS_SUBDIR = "_lean_libs"


# ---------------------------------------------------------------------------
# Native-library relocation
# ---------------------------------------------------------------------------


def _run(args: list[str]) -> None:
    res = subprocess.run(args, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(
            f"command failed ({res.returncode}): {' '.join(args)}\n{res.stderr.strip()}"
        )


def _make_writable(path: Path) -> None:
    """Toolchain dylibs are often read-only; relocation needs write access."""
    mode = path.stat().st_mode
    os.chmod(path, mode | 0o200)


def _otool_deps(lib: Path) -> list[str]:
    """The install-name dependencies of a Mach-O dylib (excluding its own id)."""
    out = subprocess.run(
        ["otool", "-L", str(lib)], check=True, capture_output=True, text=True
    ).stdout
    lines = out.splitlines()[1:]  # first line is the file name
    deps = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        deps.append(line.split(" ", 1)[0])
    # The first dependency line is the library's own id; drop it.
    return deps[1:] if deps else deps


def _try_run(args: list[str]) -> bool:
    """Run a relocation command, tolerating "load commands don't fit" errors
    on toolchain libraries that were linked without header padding."""
    try:
        _run(args)
        return True
    except RuntimeError:
        return False


def _relocate_macos(dest: Path, leaves: set[str]) -> None:
    """Point every bundled dylib at its siblings without lengthening install
    names past the Mach-O header padding.

    The Lean runtime libs are linked without ``-headerpad``, so we must not
    grow their load commands: ids are left untouched, ``@rpath/leaf`` deps are
    resolved by adding a single (small) ``@loader_path`` RPATH, and only
    absolute toolchain paths (always longer than ``@loader_path/leaf``) are
    rewritten in place. install_name_tool invalidates the signature, so we
    re-sign ad-hoc afterwards (arm64 dyld rejects unsigned modified Mach-O).
    """
    for lib in sorted(dest.glob(f"*{shared_lib_extension()}")):
        needs_rpath = False
        for dep in _otool_deps(lib):
            leaf = Path(dep).name
            if leaf not in leaves or dep.startswith("@loader_path/"):
                continue
            if dep.startswith("/"):
                # Absolute toolchain path: rewrite to @loader_path (fits).
                _run(["install_name_tool", "-change", dep, f"@loader_path/{leaf}", str(lib)])
            else:
                # @rpath/leaf (or similar): resolve via an @loader_path RPATH.
                needs_rpath = True
        if needs_rpath:
            _try_run(["install_name_tool", "-add_rpath", "@loader_path", str(lib)])
        # Re-sign ad-hoc so the modified Mach-O loads on arm64.
        _try_run(["codesign", "--force", "--sign", "-", str(lib)])

    # Fail loudly if any absolute toolchain reference survived — that would
    # break a toolchain-less install.
    for lib in sorted(dest.glob(f"*{shared_lib_extension()}")):
        for dep in _otool_deps(lib):
            if dep.startswith("/") and Path(dep).name in leaves:
                raise RuntimeError(
                    f"{lib.name} still references {dep} by absolute path after "
                    f"relocation; the bundle would not load standalone."
                )


def _relocate_linux(dest: Path) -> None:
    """Point every bundled .so at its siblings via an ``$ORIGIN`` RPATH."""
    patchelf = shutil.which("patchelf")
    if not patchelf:
        raise RuntimeError(
            "patchelf is required to bundle a Lean library on Linux "
            "(install it via your package manager)."
        )
    for lib in sorted(dest.glob(f"*{shared_lib_extension()}")):
        _run([patchelf, "--set-rpath", "$ORIGIN", "--force-rpath", str(lib)])


def relocate_bundle(dest: Path) -> None:
    """Make every native library in ``dest`` reference its siblings relatively."""
    leaves = {p.name for p in dest.glob(f"*{shared_lib_extension()}")}
    if sys.platform == "darwin":
        _relocate_macos(dest, leaves)
    elif sys.platform.startswith("linux"):
        _relocate_linux(dest)
    else:
        raise RuntimeError(f"bundling is not supported on {sys.platform}")


@dataclass
class Bundle:
    """A relocated, self-contained set of native libraries."""

    dir: Path
    main_lib: Path  # the user's library dylib inside the bundle
    library_name: str
    runtime_libs: list[Path] = field(default_factory=list)


def bundle_native_libs(main_dylib: Path, library_name: str, dest: Path) -> Bundle:
    """Copy ``main_dylib`` plus the Lean runtime closure into ``dest`` and
    relocate them to load standalone. Returns the resulting :class:`Bundle`."""
    main_dylib = Path(main_dylib).resolve()
    if not main_dylib.exists():
        raise FileNotFoundError(main_dylib)
    dest.mkdir(parents=True, exist_ok=True)

    # The Lean runtime closure the loader preloads today; proven-sufficient set.
    runtime = list(all_lean_runtime_libs())
    lean_shared = find_lean_dynlib()
    if lean_shared not in runtime and lean_shared.exists():
        runtime.append(lean_shared)

    copied_runtime: list[Path] = []
    for lib in runtime:
        target = dest / lib.name
        if not target.exists():
            shutil.copy2(lib, target)
            _make_writable(target)
        copied_runtime.append(target)

    main_target = dest / main_dylib.name
    shutil.copy2(main_dylib, main_target)
    _make_writable(main_target)

    # Ship lean.h so a toolchain-less install can build its ctypes bindings.
    from lean_py._parse import find_lean_header

    try:
        header = find_lean_header()
        shutil.copy2(header, dest / "lean.h")
    except FileNotFoundError:
        pass

    relocate_bundle(dest)
    return Bundle(
        dir=dest,
        main_lib=main_target,
        library_name=library_name,
        runtime_libs=copied_runtime,
    )


# ---------------------------------------------------------------------------
# Wheel assembly
# ---------------------------------------------------------------------------

_LOADER_TEMPLATE = '''\
"""Auto-generated loader for the vendored Lean library ``{name}``.

Import and call :func:`load` to get a ready-to-use ``LeanLibrary`` backed by
the bundled Lean runtime — no elan / toolchain required.
"""

import os
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_LIBS = _HERE / "{libs_subdir}"
_MAIN = _LIBS / "{main_leaf}"

# Point toolchain discovery at the vendored runtime before importing lean_py.
os.environ.setdefault("LEANPY_BUNDLE_DIR", str(_LIBS))

from lean_py.library import LeanLibrary  # noqa: E402
from lean_py.utils import add_lean_lib_to_dyld_path  # noqa: E402

_cached: "LeanLibrary | None" = None


def load() -> LeanLibrary:
    """Load the vendored ``{name}`` library (cached per process)."""
    global _cached
    if _cached is None:
        add_lean_lib_to_dyld_path()
        _cached = LeanLibrary(str(_MAIN), "{name}")
    return _cached
'''


def _platform_tag() -> str:
    """A PEP 425 platform tag derived from the current interpreter."""
    return sysconfig.get_platform().replace("-", "_").replace(".", "_")


def _record_line(arc: str, data: bytes) -> str:
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=")
    return f"{arc},sha256={digest.decode()},{len(data)}"


def build_wheel(
    project_dir: str | os.PathLike,
    library_name: str,
    *,
    version: str = "0.0.0",
    out_dir: str | os.PathLike = "dist",
    package_name: str | None = None,
    build: bool = True,
    dist_name: str | None = None,
) -> Path:
    """Build a self-contained wheel for the Lean library ``library_name``.

    ``package_name`` is the importable Python package the wheel installs
    (default: ``library_name`` lower-cased). ``dist_name`` is the distribution
    name on PyPI (default: same as the package). Returns the wheel path.
    """
    from lean_py.library import LeanLibrary

    project = Path(project_dir).resolve()
    # Loading resolves (and optionally builds) the dylib and gives us its path.
    lib = LeanLibrary.from_lake(project, library_name, build=build)
    main_dylib = Path(lib.path)

    pkg = (package_name or library_name).replace("-", "_").lower()
    dist = (dist_name or pkg).replace("_", "-")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    staging = out / f"_build_{pkg}"
    if staging.exists():
        shutil.rmtree(staging)
    pkg_dir = staging / pkg
    libs_dir = pkg_dir / _LIBS_SUBDIR
    libs_dir.mkdir(parents=True)

    bundle = bundle_native_libs(main_dylib, library_name, libs_dir)

    (pkg_dir / "__init__.py").write_text(
        _LOADER_TEMPLATE.format(
            name=library_name, libs_subdir=_LIBS_SUBDIR, main_leaf=bundle.main_lib.name
        ),
        encoding="utf-8",
    )
    (pkg_dir / "py.typed").write_text("", encoding="utf-8")

    tag = f"py3-none-{_platform_tag()}"
    wheel_name = f"{dist.replace('-', '_')}-{version}-{tag}.whl"
    wheel_path = out / wheel_name
    distinfo = f"{dist.replace('-', '_')}-{version}.dist-info"

    metadata = (
        "Metadata-Version: 2.1\n"
        f"Name: {dist}\n"
        f"Version: {version}\n"
        "Summary: Self-contained Lean library bundled by lean_py.\n"
        "Requires-Dist: lean_py\n"
    )
    wheel_meta = (
        f"Wheel-Version: 1.0\nGenerator: lean_py.packaging\nRoot-Is-Purelib: false\nTag: {tag}\n"
    )

    # Assemble the zip and a RECORD.
    records: list[str] = []
    if wheel_path.exists():
        wheel_path.unlink()
    with zipfile.ZipFile(wheel_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(staging.rglob("*")):
            if path.is_dir():
                continue
            arc = str(path.relative_to(staging))
            data = path.read_bytes()
            zf.writestr(arc, data)
            records.append(_record_line(arc, data))
        for arc, text in (
            (f"{distinfo}/METADATA", metadata),
            (f"{distinfo}/WHEEL", wheel_meta),
        ):
            data = text.encode()
            zf.writestr(arc, data)
            records.append(_record_line(arc, data))
        record_arc = f"{distinfo}/RECORD"
        records.append(f"{record_arc},,")
        zf.writestr(record_arc, "\n".join(records) + "\n")

    shutil.rmtree(staging, ignore_errors=True)
    return wheel_path


def _main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m lean_py.packaging",
        description="Bundle a Lean library into a self-contained wheel.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="Build a self-contained wheel.")
    b.add_argument("project_dir")
    b.add_argument("library_name")
    b.add_argument("--version", default="0.0.0")
    b.add_argument("-o", "--out-dir", default="dist")
    b.add_argument("--package-name", default=None)
    b.add_argument("--dist-name", default=None)
    b.add_argument("--no-build", action="store_true")

    args = parser.parse_args(argv)
    if args.cmd == "build":
        wheel = build_wheel(
            args.project_dir,
            args.library_name,
            version=args.version,
            out_dir=args.out_dir,
            package_name=args.package_name,
            dist_name=args.dist_name,
            build=not args.no_build,
        )
        print(f"Wrote {wheel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
