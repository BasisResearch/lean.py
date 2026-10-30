"""Fetch Lake dependencies and apply the checked Lean 4.35 Regex workaround."""

import argparse
import hashlib
import subprocess
from pathlib import Path

ORIGINAL = "2f2c23ed8bf07339194bf6feec94a97eca44d858ef1ad58afcab752a01039c05"
PATCHED = "eaf853049bd9837d0bb51c2763707942eb6b54cd3f8e64f0a7608a626181a7ae"


def prepare(project: Path) -> None:
    subprocess.run(["lake", "update"], cwd=project, check=True)
    source = project / ".lake/packages/Regex/regex/Regex/Data/SparseSet/Bijection.lean"
    data = source.read_bytes()
    fingerprint = hashlib.sha256(data).hexdigest()
    if fingerprint == PATCHED:
        print(f"Regex workaround already applied: {source}")
        return
    if fingerprint != ORIGINAL:
        raise RuntimeError(f"Refusing to patch unexpected Regex source: {source}")
    data = data.replace(
        b"      grind\n    have surj",
        b"      apply Fin.ext\n      grind -hom [Fin.ext_iff]\n    have surj",
    )
    if hashlib.sha256(data).hexdigest() != PATCHED:
        raise RuntimeError("Regex patch did not produce the expected source")
    source.write_bytes(data)
    print(f"Applied Lean 4.35 Regex proof workaround: {source}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", nargs="?", type=Path, default=Path.cwd())
    prepare(parser.parse_args().project.resolve())
