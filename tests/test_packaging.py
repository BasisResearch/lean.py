"""Tests for the self-contained bundler / wheel builder (`lean_py.packaging`).

The key guarantee: a bundled library loads and runs with **no Lean toolchain**
on PATH (no elan, no `DYLD_LIBRARY_PATH`). We prove it by relocating the dylib
closure and then loading it from a subprocess whose environment has the
toolchain stripped out.
"""

import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from lean_py.library import LeanLibrary
from lean_py.packaging import bundle_native_libs, build_wheel

TESTLEAN = Path(__file__).parent / "lean"

pytestmark = pytest.mark.skipif(
    not (sys.platform == "darwin" or sys.platform.startswith("linux")),
    reason="bundling is only supported on macOS and Linux",
)


def _toolchainless_env(bundle_dir: Path) -> dict:
    """A subprocess env with the Lean toolchain removed, pointing only at the
    vendored bundle."""
    import os

    env = dict(os.environ)
    # Drop elan / toolchain dirs from PATH.
    env["PATH"] = ":".join(
        p for p in env.get("PATH", "").split(":") if ".elan" not in p and p
    )
    for var in ("DYLD_LIBRARY_PATH", "LD_LIBRARY_PATH", "LEANPY_LIBLEAN"):
        env.pop(var, None)
    env["LEANPY_BUNDLE_DIR"] = str(bundle_dir)
    return env


def test_bundle_loads_and_runs_without_toolchain(tmp_path):
    lib = LeanLibrary.from_lake(TESTLEAN, "TestLib", build=True)
    bundle = bundle_native_libs(Path(lib.path), "TestLib", tmp_path / "_lean_libs")

    # lean.h and libleanshared must be vendored for a toolchain-less load.
    assert (bundle.dir / "lean.h").exists()
    assert list(bundle.dir.glob("libleanshared*"))

    prog = f"""
from lean_py.library import LeanLibrary
from lean_py.utils import add_lean_lib_to_dyld_path
add_lean_lib_to_dyld_path()
lib = LeanLibrary(r"{bundle.main_lib}", "TestLib")
assert lib.bar(21) == 22, lib.bar(21)
assert lib.sumList([1, 2, 3, 4, 5]) == 15, lib.sumList([1, 2, 3, 4, 5])
print("STANDALONE_OK")
"""
    res = subprocess.run(
        [sys.executable, "-c", prog],
        env=_toolchainless_env(bundle.dir),
        capture_output=True,
        text=True,
    )
    assert "STANDALONE_OK" in res.stdout, (
        f"standalone load failed\nstdout:\n{res.stdout}\nstderr:\n{res.stderr}"
    )


def test_build_wheel_structure(tmp_path):
    wheel = build_wheel(
        TESTLEAN,
        "TestLib",
        version="0.1.0",
        out_dir=tmp_path,
        package_name="testlib_bundled",
        build=True,
    )
    assert wheel.exists()
    assert wheel.suffix == ".whl"
    assert wheel.name.startswith("testlib_bundled-0.1.0-py3-none-")

    with zipfile.ZipFile(wheel) as zf:
        names = zf.namelist()
    # Loader package + vendored libs + metadata.
    assert "testlib_bundled/__init__.py" in names
    assert any(n.endswith("lean.h") for n in names)
    assert any("_lean_libs/libleanshared" in n for n in names)
    assert any(n.endswith(".dist-info/WHEEL") for n in names)
    assert any(n.endswith(".dist-info/RECORD") for n in names)


def test_installed_wheel_loads_without_toolchain(tmp_path):
    """Extract the built wheel into a throwaway dir and load it through the
    generated loader, with the toolchain stripped from the environment.

    (Extraction rather than ``pip install`` because the loader package + its
    ``_lean_libs`` land at import-root either way, and uv venvs often ship no
    pip.)"""
    import os

    wheel = build_wheel(
        TESTLEAN, "TestLib", version="0.1.0", out_dir=tmp_path,
        package_name="testlib_bundled", build=True,
    )
    target = tmp_path / "site"
    with zipfile.ZipFile(wheel) as zf:
        zf.extractall(target)

    libs_dir = target / "testlib_bundled" / "_lean_libs"
    prog = """
from testlib_bundled import load
lib = load()
assert lib.bar(41) == 42, lib.bar(41)
assert lib.powInt(2, 10) == 1024, lib.powInt(2, 10)
print("WHEEL_OK")
"""
    env = _toolchainless_env(libs_dir)
    env["PYTHONPATH"] = str(target) + os.pathsep + env.get("PYTHONPATH", "")
    res = subprocess.run(
        [sys.executable, "-c", prog], env=env, capture_output=True, text=True,
    )
    assert "WHEEL_OK" in res.stdout, (
        f"installed-wheel load failed\nstdout:\n{res.stdout}\nstderr:\n{res.stderr}"
    )
