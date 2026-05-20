"""Z3-style AST nodes matching the Lean Z3Sort/Z3BinOp/Z3UnOp/Z3Expr inductives.

Expression building is pure Python (no Lean calls). Marshalled to Lean
Z3Expr values only at proof time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union

# ---------------------------------------------------------------------------
# Sorts
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PropSort:
    pass


@dataclass(frozen=True)
class IntASTSort:
    pass


@dataclass(frozen=True)
class NatASTSort:
    pass


@dataclass(frozen=True)
class RealASTSort:
    pass


@dataclass(frozen=True)
class BitvecASTSort:
    width: int


@dataclass(frozen=True)
class TypeASTSort:
    """Lean's Type (Sort 1) — for quantifying over type-kinded variables."""
    pass


@dataclass(frozen=True)
class UninterpASTSort:
    name: str


@dataclass(frozen=True)
class ArrowASTSort:
    dom: ASTSort
    cod: ASTSort


ASTSort = Union[
    PropSort, IntASTSort, NatASTSort, RealASTSort,
    BitvecASTSort, TypeASTSort, UninterpASTSort, ArrowASTSort,
]

# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------


class BinOp:
    ADD = "add"
    SUB = "sub"
    MUL = "mul"
    DIV = "div"
    MOD = "mod"
    LT = "lt"
    LE = "le"
    GT = "gt"
    GE = "ge"
    EQ = "eq"
    NE = "ne"
    AND = "and"
    OR = "or"
    IMPLIES = "implies"
    XOR = "xor"
    BAND = "band"
    BOR = "bor"
    BXOR = "bxor"
    BSHL = "bshl"
    BSHR = "bshr"


class UnOp:
    NEG = "neg"
    NOT = "not"
    BNOT = "bnot"


# ---------------------------------------------------------------------------
# Expression nodes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Var:
    name: str


@dataclass(frozen=True)
class IntLit:
    val: int


@dataclass(frozen=True)
class NatLit:
    val: int


@dataclass(frozen=True)
class BoolLit:
    val: bool


@dataclass(frozen=True)
class BvLit:
    val: int
    width: int


@dataclass(frozen=True)
class BinOpNode:
    op: str
    lhs: ASTNode
    rhs: ASTNode


@dataclass(frozen=True)
class UnOpNode:
    op: str
    arg: ASTNode


@dataclass(frozen=True)
class IteNode:
    cond: ASTNode
    then_: ASTNode
    else_: ASTNode


@dataclass(frozen=True)
class ForAllNode:
    name: str
    sort: ASTSort
    body: ASTNode


@dataclass(frozen=True)
class ExistsNode:
    name: str
    sort: ASTSort
    body: ASTNode


@dataclass(frozen=True)
class AppNode:
    func: ASTNode
    args: tuple[ASTNode, ...]


@dataclass(frozen=True)
class DistinctNode:
    args: tuple[ASTNode, ...]


@dataclass(frozen=True)
class SelectNode:
    arr: ASTNode
    idx: ASTNode


@dataclass(frozen=True)
class StoreNode:
    arr: ASTNode
    idx: ASTNode
    val: ASTNode


@dataclass(frozen=True)
class ConstArrayNode:
    dom_sort: ASTSort
    val: ASTNode


ASTNode = Union[
    Var, IntLit, NatLit, BoolLit, BvLit,
    BinOpNode, UnOpNode, IteNode,
    ForAllNode, ExistsNode, AppNode,
    DistinctNode, SelectNode, StoreNode, ConstArrayNode,
]

__all__ = [
    # Sorts
    "PropSort", "IntASTSort", "NatASTSort", "RealASTSort",
    "BitvecASTSort", "UninterpASTSort", "ArrowASTSort", "ASTSort",
    # Ops
    "BinOp", "UnOp",
    # Nodes
    "Var", "IntLit", "NatLit", "BoolLit", "BvLit",
    "BinOpNode", "UnOpNode", "IteNode",
    "ForAllNode", "ExistsNode", "AppNode",
    "DistinctNode", "SelectNode", "StoreNode", "ConstArrayNode",
    "ASTNode",
]
