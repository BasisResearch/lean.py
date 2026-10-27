"""Inspect compiled Lean declarations without linking the project's libraries."""

import argparse
import json
import os
import subprocess
from pathlib import Path

from lean_py import LeanLibrary
from lean_py.kernel import Kernel


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("--module", action="append", required=True)
    parser.add_argument("--declaration", action="append", default=[])
    args = parser.parse_args()
    project = args.project.resolve()
    paths = subprocess.check_output(
        ["lake", "env", "printenv", "LEAN_PATH"], cwd=project, text=True
    ).strip()
    search_path = os.pathsep.join(
        str((project / entry).resolve()) for entry in paths.split(os.pathsep) if entry
    )
    bridge = Path(__file__).parent / "lean"
    kernel = Kernel(LeanLibrary.from_lake(bridge, "KernelBridge"))
    kernel.init_search(search_path)
    kernel.load(args.module)
    declarations = []
    for name in args.declaration:
        if not kernel.decl_exists(name):
            raise ValueError(f"Declaration not found: {name}")
        declarations.append(
            {"name": name, "type": kernel.decl_type(name), "axioms": kernel.decl_axioms(name)}
        )
    print(json.dumps({"loaded": kernel.is_loaded(), "declarations": declarations}, indent=2))


if __name__ == "__main__":
    main()
