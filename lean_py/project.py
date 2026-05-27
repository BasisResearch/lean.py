"""Managed Lake projects for zero-config Std/Mathlib loading.

:class:`ManagedProject` creates and caches a Lake project under
``~/.lean_py/managed/<hash>/`` so users can load Std or Mathlib without
manually creating a lakefile::

    from lean_py.project import ManagedProject

    mp = ManagedProject.get(deps=("batteries",))
    k = mp.kernel()
    k.load(["Batteries"])
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from importlib.metadata import distribution
from importlib.metadata import version as pkg_version
from pathlib import Path

from lean_py.kernel import Kernel
from lean_py.library import LeanLibrary
from lean_py.utils import lean_toolchain_version, run_command

_LEANPY_ROOT = Path(__file__).resolve().parent.parent
_LEANPY_GIT = "https://github.com/BasisResearch/lean.py"
_IS_DEV = (_LEANPY_ROOT / "lakefile.lean").exists()
_CACHE_ROOT = Path(
    os.environ.get(
        "LEANPY_MANAGED_DIR",
        Path.home() / ".lean_py" / "managed",
    )
)

# Well-known Lake packages: name -> (git, import_name, link_obj)
# The rev is auto-matched to the active lean-toolchain version.
# link_obj is the moreLinkObjs entry needed at runtime.
_KNOWN_DEPS: dict[str, tuple[str, str, str]] = {
    "batteries": (
        "https://github.com/leanprover-community/batteries",
        "Batteries",
        "batteries/Batteries:static",
    ),
    "mathlib": (
        "https://github.com/leanprover-community/mathlib4",
        "Mathlib",
        "mathlib/Mathlib:static",
    ),
    "aesop": (
        "https://github.com/leanprover-community/aesop",
        "Aesop",
        "aesop/Aesop:static",
    ),
    "proofwidgets": (
        "https://github.com/leanprover-community/ProofWidgets4",
        "ProofWidgets",
        "proofwidgets/ProofWidgets:static",
    ),
}


def _dep_rev(version: str) -> str:
    """Extract a tag like ``v4.29.1`` from the toolchain string."""
    # "leanprover/lean4:v4.29.1" -> "v4.29.1"
    if ":" in version:
        return version.split(":", 1)[1]
    return version


def _leanpy_version() -> str:
    """Return the installed lean_py package version."""
    return pkg_version("lean_py")


def _leanpy_git_rev() -> str:
    """Git rev for the LeanPy Lake dependency when pip-installed.

    Resolution order: LEANPY_GIT_REV env var, then the commit hash from
    direct_url.json (set by pip for git installs), then v{version} tag.
    """
    override = os.environ.get("LEANPY_GIT_REV")
    if override:
        return override
    try:
        dist = distribution("lean_py")
        raw = dist.read_text("direct_url.json")
        if raw:
            info = json.loads(raw)
            commit = info.get("vcs_info", {}).get("commit_id")
            if commit:
                return commit
    except Exception:
        pass
    return f"v{_leanpy_version()}"


def _cache_key(lean_version: str, deps: tuple[str, ...]) -> str:
    src_id = str(_LEANPY_ROOT) if _IS_DEV else f"git:{_leanpy_git_rev()}"
    blob = f"{lean_version}|{','.join(sorted(deps))}|{src_id}"
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


class ManagedProject:
    """A cached Lake project wired to LeanPy + user-specified dependencies."""

    _instances: dict[str, ManagedProject] = {}

    def __init__(self, project_dir: Path) -> None:
        self._dir = project_dir

    @classmethod
    def get(cls, deps: tuple[str, ...] = ()) -> ManagedProject:
        """Return a cached managed project, creating it if necessary."""
        version = lean_toolchain_version()
        key = _cache_key(version, deps)
        if key in cls._instances:
            return cls._instances[key]

        project_dir = _CACHE_ROOT / key
        if not (project_dir / "lakefile.toml").exists():
            _create_project(project_dir, version, deps)

        inst = cls(project_dir)
        cls._instances[key] = inst
        return inst

    def build(self) -> None:
        """Run ``lake build`` in the managed project."""
        run_command(["lake", "build"], cwd=str(self._dir))

    def library(self) -> LeanLibrary:
        """Build and return a :class:`LeanLibrary` for this project."""
        return LeanLibrary.from_lake(self._dir, "Managed", build=True)

    def kernel(self) -> Kernel:
        """Build and return a :class:`Kernel` backed by this project."""
        lib = self.library()
        k = Kernel(lib)
        sp = run_command(
            ["lake", "env", "printenv", "LEAN_PATH"],
            cwd=str(self._dir),
        )
        k.init_search(sp)
        k.load(["Init", "LeanPy.Z3"])
        return k

    @property
    def path(self) -> Path:
        return self._dir

    def clean(self) -> None:
        """Remove the cached project directory."""
        if self._dir.exists():
            shutil.rmtree(self._dir)
        key = next(
            (k for k, v in self._instances.items() if v is self),
            None,
        )
        if key:
            del self._instances[key]


def _create_project(
    project_dir: Path,
    lean_version: str,
    deps: tuple[str, ...],
) -> None:
    """Generate a minimal Lake project on disk."""
    project_dir.mkdir(parents=True, exist_ok=True)

    # lean-toolchain
    (project_dir / "lean-toolchain").write_text(f"{lean_version}\n")

    # lakefile.toml
    lakefile = _generate_lakefile(deps, lean_version)
    (project_dir / "lakefile.toml").write_text(lakefile)

    # Managed.lean
    imports = ["import LeanPy", "import LeanPy.Kernel"]
    for d in deps:
        import_name = _KNOWN_DEPS[d][1] if d in _KNOWN_DEPS else d
        imports.append(f"import {import_name}")
    lean_src = "\n".join(imports) + '\n\n#export_python_registry "Managed"\n'
    (project_dir / "Managed.lean").write_text(lean_src)


def _generate_lakefile(
    deps: tuple[str, ...],
    lean_version: str,
) -> str:
    rev = _dep_rev(lean_version)
    lines = [
        'name = "Managed"',
        'version = "0.1.0"',
        'defaultTargets = ["Managed"]',
        "",
        "[[require]]",
        'name = "LeanPy"',
    ]
    if _IS_DEV:
        lines.append(f'path = "{_LEANPY_ROOT}"')
    else:
        lines.append(f'git = "{_LEANPY_GIT}"')
        lines.append(f'rev = "{_leanpy_git_rev()}"')
    lines += [
        "",
    ]

    for dep in deps:
        lines.append("[[require]]")
        lines.append(f'name = "{dep}"')
        if dep in _KNOWN_DEPS:
            git, _, _ = _KNOWN_DEPS[dep]
            lines.append(f'git = "{git}"')
            lines.append(f'rev = "{rev}"')
        lines.append("")

    # Collect moreLinkObjs: base + known dep link objects
    link_objs = [
        '"LeanPy/LeanPy:static"',
        '"LeanPy/leanPyNative:static"',
        '"Pantograph/Pantograph:static"',
        '"Regex/Regex:static"',
    ]
    for dep in deps:
        if dep in _KNOWN_DEPS:
            _, _, link_obj = _KNOWN_DEPS[dep]
            link_objs.append(f'"{link_obj}"')

    lines.extend(
        [
            "[[lean_lib]]",
            'name = "Managed"',
            "moreLinkObjs = [" + ", ".join(link_objs) + "]",
            "precompileModules = true",
            'defaultFacets = ["shared"]',
            "moreLinkArgs = [",
            '  "-Wl,-headerpad_max_install_names",',
            "]",
            "",
        ]
    )

    return "\n".join(lines)


__all__ = ["ManagedProject"]
