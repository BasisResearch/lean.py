"""
High-level Python interface to ``LeanPy.Kernel`` — the pantograph-equivalent
operations layer.

The underlying :mod:`LeanPy.Kernel` Lean module exposes ~30 ``@[python]``
functions named ``leanpy_kernel_*``. This module wraps them in idiomatic
Python:

.. code-block:: python

    from lean_py import LeanLibrary
    from lean_py.kernel import Kernel

    lib = LeanLibrary.from_lake("path/to/lake/project", "MyLib")
    k = Kernel(lib)
    k.load(["Init"])

    state = k.goal_create("∀ n : Nat, n + 0 = n")
    print(state.is_solved())          # False
    print(state.pretty())              # "⊢ ∀ (n : Nat), n + 0 = n"
    state2 = state.try_tactic("intro n").state
    print(state2.pretty())

The :class:`GoalState` class is a thin handle around the Lean ``LeanObj``
returned by :meth:`Kernel.goal_create`. Each method dispatches back into the
underlying ``LeanLibrary`` instance.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class TacticResult:
    """Result of running a tactic.

    Attributes:
        status: one of ``"success"``, ``"failure"``, ``"parseError"``,
                ``"invalidAction"``.
        messages: zero or more diagnostic / error messages.
        state: the new ``GoalState`` if ``status == "success"``, else ``None``.
    """

    status: str
    messages: list[str]
    state: "GoalState | None"

    @property
    def ok(self) -> bool:
        return self.status == "success"

    @classmethod
    def parse(cls, encoded: str, kernel: "Kernel",
              raw_state: Any) -> "TacticResult":
        """Parse the multi-line encoding produced by Lean's
        ``encodeTacticResult``."""
        if not encoded:
            return cls("failure", [], None)
        lines = encoded.split("\n")
        status = lines[0]
        messages = lines[1:] if len(lines) > 1 else []
        state = None
        if status == "success" and raw_state is not None:
            state = GoalState(kernel, raw_state)
        return cls(status, messages, state)


class GoalState:
    """Opaque handle to a Lean ``GoalState``. Methods dispatch back into the
    underlying Lean library."""

    __slots__ = ("_kernel", "_handle")

    def __init__(self, kernel: "Kernel", handle: Any) -> None:
        self._kernel = kernel
        self._handle = handle

    @property
    def handle(self) -> Any:
        return self._handle

    def is_solved(self) -> bool:
        return self._kernel._lib.leanpy_kernel_goal_is_solved(self._handle)

    def n_goals(self) -> int:
        return int(self._kernel._lib.leanpy_kernel_goal_n_goals(self._handle))

    def main_goal_name(self) -> str:
        return self._kernel._lib.leanpy_kernel_goal_main_goal_name(self._handle)

    def root_expr(self) -> str:
        return self._kernel._lib.leanpy_kernel_goal_root_expr(self._handle)

    def pretty(self) -> str:
        return self._kernel._lib.leanpy_kernel_goal_pretty(self._handle)

    def try_tactic(self, tactic: str) -> TacticResult:
        encoded, next_state = \
            self._kernel._lib.leanpy_kernel_goal_try_tactic(self._handle, tactic)
        return TacticResult.parse(encoded, self._kernel, next_state)

    def try_assign(self, expr: str) -> TacticResult:
        encoded, next_state = \
            self._kernel._lib.leanpy_kernel_goal_try_assign(self._handle, expr)
        return TacticResult.parse(encoded, self._kernel, next_state)

    def conv_enter(self) -> TacticResult:
        encoded, next_state = \
            self._kernel._lib.leanpy_kernel_goal_conv_enter(self._handle)
        return TacticResult.parse(encoded, self._kernel, next_state)

    def calc_enter(self) -> TacticResult:
        encoded, next_state = \
            self._kernel._lib.leanpy_kernel_goal_calc_enter(self._handle)
        return TacticResult.parse(encoded, self._kernel, next_state)

    def fragment_exit(self) -> TacticResult:
        encoded, next_state = \
            self._kernel._lib.leanpy_kernel_goal_fragment_exit(self._handle)
        return TacticResult.parse(encoded, self._kernel, next_state)

    def __repr__(self) -> str:
        try:
            return f"<GoalState n_goals={self.n_goals()} solved={self.is_solved()}>"
        except Exception:
            return "<GoalState (handle invalid)>"


class Kernel:
    """The kernel facade.

    Wraps a :class:`LeanLibrary` whose Lean source has imported
    ``LeanPy.Kernel`` and exposed the standard ``@[python]`` surface.

    Example:

    .. code-block:: python

        from lean_py import LeanLibrary
        from lean_py.kernel import Kernel

        lib = LeanLibrary.from_lake("path/to/project", "MyLib")
        k = Kernel(lib)
        k.init_search("")
        k.load(["Init"])
        s = k.goal_create("∀ n : Nat, n + 0 = n")
        print(s.pretty())
    """

    def __init__(self, lib: Any) -> None:
        self._lib = lib

    # -- env lifecycle ---------------------------------------------------

    def init_search(self, sp: str = "") -> None:
        self._lib.leanpy_kernel_init_search(sp)

    def load(self, modules: Iterable[str]) -> None:
        self._lib.leanpy_kernel_load_env(list(modules))

    def is_loaded(self) -> bool:
        return self._lib.leanpy_kernel_is_loaded(None)

    def clear(self) -> None:
        self._lib.leanpy_kernel_clear_env(None)

    # -- env introspection ----------------------------------------------

    def decl_count(self) -> int:
        return int(self._lib.leanpy_kernel_decl_count(None))

    def all_decls(self) -> list[str]:
        s = self._lib.leanpy_kernel_all_decls(None)
        return s.split("\n") if s else []

    def catalog(self) -> list[str]:
        s = self._lib.leanpy_kernel_catalog(None)
        return s.split("\n") if s else []

    def search(self, needle: str) -> list[str]:
        s = self._lib.leanpy_kernel_search(needle)
        return s.split("\n") if s else []

    def decl_exists(self, name: str) -> bool:
        return self._lib.leanpy_kernel_decl_exists(name)

    def decl_type(self, name: str) -> str:
        return self._lib.leanpy_kernel_decl_type(name)

    def decl_value(self, name: str) -> str:
        return self._lib.leanpy_kernel_decl_value(name)

    def module_of(self, name: str) -> str:
        return self._lib.leanpy_kernel_module_of_name_str(name)

    def is_internal_name(self, name: str) -> bool:
        return self._lib.leanpy_kernel_is_internal_name_str(name)

    def decl_axioms(self, name: str) -> list[str]:
        s = self._lib.leanpy_kernel_decl_axioms(name)
        return s.split("\n") if s else []

    # -- elaboration -----------------------------------------------------

    def infer_type(self, src: str) -> str:
        return self._lib.leanpy_kernel_infer_type(src)

    def pretty_print(self, src: str) -> str:
        return self._lib.leanpy_kernel_pretty_print(src)

    def whnf(self, src: str) -> str:
        return self._lib.leanpy_kernel_whnf(src)

    def expr_echo(self, src: str) -> tuple[str, str]:
        s = self._lib.leanpy_kernel_expr_echo(src)
        if "\n---\n" in s:
            expr, ty = s.split("\n---\n", 1)
            return expr, ty
        return s, ""

    def parse_type(self, src: str) -> str:
        return self._lib.leanpy_kernel_parse_type(src)

    def decide(self, src: str) -> str:
        """Returns ``"true"`` / ``"false"`` / ``"<undecided>"`` /
        ``"<elab: ...>"`` etc."""
        return self._lib.leanpy_kernel_decide(src)

    # -- goal state ------------------------------------------------------

    def goal_create(self, type_str: str) -> GoalState:
        """Create a new goal state from a type expression string. Raises
        ``LeanError`` on parse / elaboration failure."""
        handle = self._lib.leanpy_kernel_goal_create(type_str)
        return GoalState(self, handle)


__all__ = ["Kernel", "GoalState", "TacticResult"]
