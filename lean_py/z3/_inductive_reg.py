"""Registration of Python datatypes as Lean inductives.

Separated from solver.py to break a circular import: core.py needs
_register_inductive, and solver.py imports from core.py.
"""

from __future__ import annotations

from typing import Any

from lean_py.z3._ast import (
    ArrowASTSort,
    InductiveASTSort,
    SeqASTSort,
    UninterpASTSort,
)

# Uninterpreted sort names that have been declared as Lean axioms.
# These should not be treated as free type variables in expressions.
_declared_uninterp_sorts: set[str] = set()


def _collect_uninterp_sorts(ast_sort: Any) -> set[str]:
    """Recursively collect uninterpreted sort names from an AST sort."""
    if isinstance(ast_sort, UninterpASTSort):
        return {ast_sort.name}
    if isinstance(ast_sort, ArrowASTSort):
        return _collect_uninterp_sorts(ast_sort.dom) | _collect_uninterp_sorts(ast_sort.cod)
    if isinstance(ast_sort, SeqASTSort):
        return _collect_uninterp_sorts(ast_sort.elem)
    return set()


def _register_inductive(name: str, ctors: list[tuple[str, Any]]) -> None:
    """Register a Lean inductive type in the kernel environment."""
    from lean_py.z3.solver import _get_kernel, _marshal_sort

    k = _get_kernel()
    lib = k._lib

    # Collect uninterpreted sorts used in constructor fields
    uninterp_names: set[str] = set()
    lean_ctors = []
    for ctor_name, fields in ctors:
        lean_fields = []
        for f_name, f_sort in fields:
            if hasattr(f_sort, "_ast_sort"):
                uninterp_names |= _collect_uninterp_sorts(f_sort._ast_sort)
                sort = _marshal_sort(lib, f_sort._ast_sort)
            else:
                # Self-referential: f_sort is a _DatatypeBuilder
                sort = _marshal_sort(lib, InductiveASTSort(f_sort._name))
            lean_fields.append(lib.Z3CtorField(f_name, sort))
        lean_ctors.append(lib.Z3CtorDesc(ctor_name, lean_fields))

    desc = lib.Z3InductiveDesc(name, lean_ctors)
    lib.z3_add_inductive(desc)

    # Track uninterpreted sorts that are now axioms in the Lean environment
    _declared_uninterp_sorts.update(uninterp_names)
