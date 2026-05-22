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


@dataclass(frozen=True)
class StringASTSort:
    pass


@dataclass(frozen=True)
class FpASTSort:
    ebits: int
    sbits: int


@dataclass(frozen=True)
class FinDomainASTSort:
    size: int


@dataclass(frozen=True)
class InductiveASTSort:
    name: str


ASTSort = Union[
    PropSort,
    IntASTSort,
    NatASTSort,
    RealASTSort,
    BitvecASTSort,
    TypeASTSort,
    UninterpASTSort,
    ArrowASTSort,
    StringASTSort,
    FpASTSort,
    FinDomainASTSort,
    InductiveASTSort,
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
    POW = "pow"
    CONCAT = "concat"
    ROTL = "rotl"
    ROTR = "rotr"
    SDIV = "sdiv"
    SREM = "srem"
    ASHR = "ashr"
    SLT = "slt"
    SLE = "sle"
    SGT = "sgt"
    SGE = "sge"
    SMOD = "smod"
    EDIV = "ediv"
    EMOD = "emod"


class UnOp:
    NEG = "neg"
    NOT = "not"
    BNOT = "bnot"
    BV2INT = "bv2int"
    BV2NAT = "bv2nat"


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


@dataclass(frozen=True)
class ExtractNode:
    hi: int
    lo: int
    arg: ASTNode


@dataclass(frozen=True)
class ZeroExtNode:
    bits: int
    arg: ASTNode


@dataclass(frozen=True)
class SignExtNode:
    bits: int
    arg: ASTNode


@dataclass(frozen=True)
class Int2BvNode:
    width: int
    arg: ASTNode


@dataclass(frozen=True)
class ToRealNode:
    arg: ASTNode


@dataclass(frozen=True)
class ToIntNode:
    arg: ASTNode


@dataclass(frozen=True)
class LambdaNode:
    name: str
    sort: ASTSort
    body: ASTNode


# ---------------------------------------------------------------------------
# String expression nodes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StringLit:
    val: str


@dataclass(frozen=True)
class StrLenNode:
    arg: ASTNode


@dataclass(frozen=True)
class StrContainsNode:
    haystack: ASTNode
    needle: ASTNode


@dataclass(frozen=True)
class StrPrefixOfNode:
    prefix_: ASTNode
    s: ASTNode


@dataclass(frozen=True)
class StrSuffixOfNode:
    suffix_: ASTNode
    s: ASTNode


@dataclass(frozen=True)
class StrReplaceNode:
    s: ASTNode
    old: ASTNode
    new_: ASTNode


@dataclass(frozen=True)
class StrConcatNode:
    lhs: ASTNode
    rhs: ASTNode


@dataclass(frozen=True)
class StrSubstrNode:
    s: ASTNode
    offset: ASTNode
    length: ASTNode


@dataclass(frozen=True)
class StrIndexOfNode:
    s: ASTNode
    substr: ASTNode
    offset: ASTNode


@dataclass(frozen=True)
class StrToIntNode:
    arg: ASTNode


@dataclass(frozen=True)
class IntToStrNode:
    arg: ASTNode


# ---------------------------------------------------------------------------
# Regex expression nodes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReStarNode:
    arg: ASTNode


@dataclass(frozen=True)
class RePlusNode:
    arg: ASTNode


@dataclass(frozen=True)
class ReOptionNode:
    arg: ASTNode


@dataclass(frozen=True)
class ReUnionNode:
    a: ASTNode
    b: ASTNode


@dataclass(frozen=True)
class ReIntersectNode:
    a: ASTNode
    b: ASTNode


@dataclass(frozen=True)
class ReConcatNode:
    a: ASTNode
    b: ASTNode


@dataclass(frozen=True)
class ReRangeNode:
    lo: str
    hi: str


@dataclass(frozen=True)
class ReComplementNode:
    arg: ASTNode


@dataclass(frozen=True)
class ReLoopNode:
    arg: ASTNode
    lo: int
    hi: int


@dataclass(frozen=True)
class InReNode:
    s: ASTNode
    re: ASTNode


# ---------------------------------------------------------------------------
# Floating-point expression nodes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FpLitNode:
    """FP value encoded as IEEE 754 bit pattern (always a non-negative int)."""

    bits: int  # IEEE 754 bit pattern as uint64
    ebits: int
    sbits: int


@dataclass(frozen=True)
class FpOpNode:
    """Named FP operation with pre-compiled args (RM already stripped)."""

    op: str  # e.g. "fpAdd", "fpIsNaN", "fpLT"
    args: tuple[ASTNode, ...]


@dataclass(frozen=True)
class FinDomainLit:
    val: int
    size: int


@dataclass(frozen=True)
class InductiveCtorNode:
    type_name: str
    ctor_name: str
    args: tuple[ASTNode, ...]


@dataclass(frozen=True)
class InductiveAccessorNode:
    type_name: str
    accessor_name: str
    arg: ASTNode


@dataclass(frozen=True)
class InductiveRecognizerNode:
    type_name: str
    recognizer_name: str
    arg: ASTNode


ASTNode = Union[
    Var,
    IntLit,
    NatLit,
    BoolLit,
    BvLit,
    BinOpNode,
    UnOpNode,
    IteNode,
    ForAllNode,
    ExistsNode,
    AppNode,
    DistinctNode,
    SelectNode,
    StoreNode,
    ConstArrayNode,
    ExtractNode,
    ZeroExtNode,
    SignExtNode,
    Int2BvNode,
    ToRealNode,
    ToIntNode,
    LambdaNode,
    StringLit,
    StrLenNode,
    StrContainsNode,
    StrPrefixOfNode,
    StrSuffixOfNode,
    StrReplaceNode,
    StrConcatNode,
    StrSubstrNode,
    StrIndexOfNode,
    StrToIntNode,
    IntToStrNode,
    ReStarNode,
    RePlusNode,
    ReOptionNode,
    ReUnionNode,
    ReIntersectNode,
    ReConcatNode,
    ReRangeNode,
    ReComplementNode,
    ReLoopNode,
    InReNode,
    FpLitNode,
    FpOpNode,
    FinDomainLit,
    InductiveCtorNode,
    InductiveAccessorNode,
    InductiveRecognizerNode,
]

__all__ = [
    # Sorts
    "PropSort",
    "IntASTSort",
    "NatASTSort",
    "RealASTSort",
    "BitvecASTSort",
    "UninterpASTSort",
    "ArrowASTSort",
    "StringASTSort",
    "FpASTSort",
    "FinDomainASTSort",
    "InductiveASTSort",
    "ASTSort",
    # Ops
    "BinOp",
    "UnOp",
    # Nodes
    "Var",
    "IntLit",
    "NatLit",
    "BoolLit",
    "BvLit",
    "BinOpNode",
    "UnOpNode",
    "IteNode",
    "ForAllNode",
    "ExistsNode",
    "AppNode",
    "DistinctNode",
    "SelectNode",
    "StoreNode",
    "ConstArrayNode",
    "ExtractNode",
    "ZeroExtNode",
    "SignExtNode",
    "Int2BvNode",
    "ToRealNode",
    "ToIntNode",
    "LambdaNode",
    # String nodes
    "StringLit",
    "StrLenNode",
    "StrContainsNode",
    "StrPrefixOfNode",
    "StrSuffixOfNode",
    "StrReplaceNode",
    "StrConcatNode",
    "StrSubstrNode",
    "StrIndexOfNode",
    "StrToIntNode",
    "IntToStrNode",
    # Regex nodes
    "ReStarNode",
    "RePlusNode",
    "ReOptionNode",
    "ReUnionNode",
    "ReIntersectNode",
    "ReConcatNode",
    "ReRangeNode",
    "ReComplementNode",
    "ReLoopNode",
    "InReNode",
    # Floating-point nodes
    "FpLitNode",
    "FpOpNode",
    # Finite domain nodes
    "FinDomainLit",
    # Inductive nodes
    "InductiveCtorNode",
    "InductiveAccessorNode",
    "InductiveRecognizerNode",
    "ASTNode",
]
