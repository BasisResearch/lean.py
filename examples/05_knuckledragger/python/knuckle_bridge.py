"""Python module imported by the Lean side of the knuckle tactic.

The Lean code does `LeanPy.Python.import_ "knuckle_bridge"` and then
calls `accept(prop_string)` / `eq_accept(lhs, rhs)`. We delegate the
actual SMT call to Knuckledragger if it's installed, falling back to
plain `z3` otherwise so the demo runs without the upstream package.

In a real integration you'd parse the Lean-rendered string into a
proper `kdr.Predicate` and feed it to `kdr.lemma`/`kdr.prove`. The
parsing layer is the part that warrants the most engineering care; we
keep it deliberately simple here so the wiring is what's visible.
"""

from __future__ import annotations

try:
    import kdrag as kdr  # Knuckledragger's package name
    HAS_KDR = True
except ImportError:  # pragma: no cover
    kdr = None
    HAS_KDR = False

import z3


_VAR_CACHE: dict[str, z3.ArithRef] = {}


def _var(name: str) -> z3.ArithRef:
    if name not in _VAR_CACHE:
        _VAR_CACHE[name] = z3.Real(name)
    return _VAR_CACHE[name]


class _AutoVars(dict):
    """Resolve any unknown identifier as a fresh `z3.Real`."""
    def __missing__(self, key: str):
        v = _var(key)
        self[key] = v
        return v


def _eval(expr: str):
    """Evaluate a Python-syntax expression against `z3.Real` symbols."""
    env = _AutoVars()
    env["Eq"] = lambda a, b: a == b
    return eval(compile(expr, "<knuckle>", "eval"), {"__builtins__": {}}, env)


def _parse_term(s: str) -> z3.ArithRef:
    return _eval(s.strip())


def _parse(prop: str) -> z3.BoolRef:
    """Translate a Lean-rendered proposition into a Z3 BoolRef.

    Accepts Python-syntax expressions including `Eq(lhs, rhs)` and the
    standard comparison operators. Free identifiers become fresh
    `z3.Real` variables.
    """
    s = prop.strip()
    return _eval(s)


def _z3_proves(prop: z3.BoolRef) -> bool:
    s = z3.Solver()
    s.add(z3.Not(prop))
    return s.check() == z3.unsat


def accept(prop: str) -> bool:
    """Return True iff Knuckledragger / Z3 discharges `prop`."""
    try:
        z3p = _parse(prop)
    except Exception:
        return False
    if HAS_KDR:
        try:
            kdr.lemma(z3p)
            return True
        except Exception:
            return False
    return _z3_proves(z3p)


def eq_accept(lhs: str, rhs: str) -> bool:
    """Return True iff `lhs == rhs` is discharged."""
    try:
        l = _parse_term(lhs)
        r = _parse_term(rhs)
    except Exception:
        return False
    return _z3_proves(l == r)
