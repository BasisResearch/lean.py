"""
Effectful refinement-type verifier demo.

Combines effectful's algebraic effects (symbolic arithmetic) with lean-py's
Lean 4 kernel access to verify refinement-type properties via ``omega``.

Three test programs:
  1. positive_increment — 2 VCs, both verified
  2. bounded_sum        — 2 VCs, both verified
  3. failing            — 1 VC, correctly rejected
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from lean_py import LeanLibrary
from lean_py.kernel import Kernel

from refine import Gt, Ge, assert_refined, verify_function

lake_dir = Path(__file__).resolve().parent.parent / "lean"
lib = LeanLibrary.from_lake(lake_dir, "EffectfulVerifier", build=True)

kernel = Kernel(lib)
kernel.init_search("")
kernel.load(["Init"])

def verify(fn):
    all_ok = True
    for msg, ok in verify_function(fn, lib, kernel):
        if not ok:
            print(f"  REJECTED: {msg}")
            all_ok = False
        else:
            print(f"  VERIFIED: {msg}")
    return all_ok


# ---------------------------------------------------------------------------
#  Programs under verification
# ---------------------------------------------------------------------------

def positive_increment(x: Annotated[int, Gt(0)]):
    y = x + 3
    assert_refined(y, Gt(3))      # x > 0 → x + 3 > 3   ✓
    z = x + 10
    assert_refined(z, Gt(10))     # x > 0 → x + 10 > 10  ✓
assert verify(positive_increment)

def bounded_sum(x: Annotated[int, Gt(0)], y: Annotated[int, Gt(0)]):
    s = x + y
    assert_refined(s, Gt(1))      # x > 0 ∧ y > 0 → x + y > 1   ✓
    assert_refined(s, Ge(2))      # x > 0 ∧ y > 0 → x + y >= 2  ✓
assert verify(bounded_sum)


def failing(x: Annotated[int, Gt(0)]):
    y = x + 1
    assert_refined(y, Gt(10))     # x > 0 → x + 1 > 10  ✗
assert not verify(failing)

