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

    # ---- prograde tactics --------------------------------------------------

    def try_have(self, binder_name: str, type_str: str) -> TacticResult:
        """Equivalent to ``have <binder_name> : <type_str> := ?``."""
        encoded, next_state = self._kernel._lib.leanpy_kernel_goal_try_have(
            self._handle, binder_name, type_str,
        )
        return TacticResult.parse(encoded, self._kernel, next_state)

    def try_let(self, binder_name: str, type_str: str) -> TacticResult:
        """Equivalent to ``let <binder_name> : <type_str> := ?``."""
        encoded, next_state = self._kernel._lib.leanpy_kernel_goal_try_let(
            self._handle, binder_name, type_str,
        )
        return TacticResult.parse(encoded, self._kernel, next_state)

    def try_define(self, binder_name: str, expr_str: str) -> TacticResult:
        """Equivalent to ``let <binder_name> := <expr_str>``."""
        encoded, next_state = self._kernel._lib.leanpy_kernel_goal_try_define(
            self._handle, binder_name, expr_str,
        )
        return TacticResult.parse(encoded, self._kernel, next_state)

    def try_draft(self, expr_str: str) -> TacticResult:
        """Substitute the goal with an expression that may contain sorrys,
        leaving the sorrys as fresh subgoals."""
        encoded, next_state = self._kernel._lib.leanpy_kernel_goal_try_draft(
            self._handle, expr_str,
        )
        return TacticResult.parse(encoded, self._kernel, next_state)

    # ---- introspection -----------------------------------------------------

    def goal_names(self) -> list[str]:
        return list(self._kernel._lib.leanpy_kernel_goal_state_goal_names(self._handle))

    def parent_names(self) -> list[str]:
        return list(self._kernel._lib.leanpy_kernel_goal_state_parent_names(self._handle))

    def root_name(self) -> str:
        return self._kernel._lib.leanpy_kernel_goal_state_root_name(self._handle)

    def diag(self) -> str:
        """Diagnostic dump of the GoalState's internal mvar table."""
        return self._kernel._lib.leanpy_kernel_goal_state_diag(self._handle)

    def serialize(self) -> str:
        return self._kernel._lib.leanpy_kernel_goal_serialize(self._handle)

    def print(self) -> str:  # noqa: A003 — mirrors pantograph's name
        return self._kernel._lib.leanpy_kernel_goal_print(self._handle)

    # ---- pickling ----------------------------------------------------------

    def pickle(self, path: str) -> None:
        """Serialise the goal state to disk via Lean's ``saveModuleData``.
        Round-trips with :meth:`Kernel.goal_unpickle`. Raises on error."""
        err = self._kernel._lib.leanpy_kernel_goal_pickle(self._handle, str(path))
        if err:
            raise RuntimeError(f"goal pickle failed: {err}")

    # ---- resume / continue / replay / subsume ------------------------------

    def resume(self, goal_names: list[str]) -> "GoalState":
        next_state, err = self._kernel._lib.leanpy_kernel_goal_resume(
            self._handle, goal_names,
        )
        if err:
            raise RuntimeError(f"resume failed: {err}")
        return GoalState(self._kernel, next_state)

    def continue_with(self, branch: "GoalState") -> "GoalState":
        next_state, err = self._kernel._lib.leanpy_kernel_goal_continue(
            self._handle, branch._handle,
        )
        if err:
            raise RuntimeError(f"continue failed: {err}")
        return GoalState(self._kernel, next_state)

    def replay(self, src: "GoalState", src_prime: "GoalState") -> "GoalState":
        """Merge differential ``src → src_prime`` onto ``self`` (the dst)."""
        next_state, err = self._kernel._lib.leanpy_kernel_goal_replay(
            self._handle, src._handle, src_prime._handle,
        )
        if err:
            raise RuntimeError(f"replay failed: {err}")
        return GoalState(self._kernel, next_state)

    def subsume(self, goal_name: str, candidate_names: list[str]
                ) -> tuple[str, "GoalState | None", str]:
        """Try to discharge ``goal_name`` using one of ``candidate_names``.
        Returns (``"none"|"subsumed"|"cycle"|"error"``, optional new state,
        optional name of the candidate that subsumed). """
        label, next_state, sub_name = self._kernel._lib.leanpy_kernel_goal_subsume(
            self._handle, goal_name, candidate_names,
        )
        next_gs = GoalState(self._kernel, next_state) if next_state is not None else None
        return label, next_gs, sub_name

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

    def goal_unpickle(self, path: str) -> GoalState:
        """Load a goal state previously serialised with :meth:`GoalState.pickle`."""
        handle, err = self._lib.leanpy_kernel_goal_unpickle(str(path))
        if err:
            raise RuntimeError(f"goal unpickle failed: {err}")
        return GoalState(self, handle)

    # -- environment serialisation ---------------------------------------

    def env_pickle(self, path: str) -> None:
        err = self._lib.leanpy_kernel_env_pickle(str(path))
        if err:
            raise RuntimeError(f"env pickle failed: {err}")

    def env_unpickle(self, path: str) -> None:
        err = self._lib.leanpy_kernel_env_unpickle(str(path))
        if err:
            raise RuntimeError(f"env unpickle failed: {err}")

    # -- frontend --------------------------------------------------------

    def find_source_path(self, module_name: str) -> str:
        """Locate the ``.lean`` source file for ``module_name``."""
        s = self._lib.leanpy_kernel_frontend_find_source_path(module_name)
        if s.startswith("<error:"):
            raise RuntimeError(s)
        return s

    def process(self, source: str) -> str:
        """Process Lean source code against the current environment.

        Returns a multi-line string of new constants per command, separated by
        ``\\n---\\n``."""
        return self._lib.leanpy_kernel_frontend_process(source)

    def collect_sorrys(self, source: str) -> tuple[GoalState | None, str]:
        """Extract all `sorry` placeholders in ``source`` as a draftable
        :class:`GoalState`. Returns ``(state, message)`` — state is ``None`` if
        no sorries were found."""
        handle, msg = self._lib.leanpy_kernel_frontend_collect_sorrys(source)
        return (GoalState(self, handle) if handle is not None else None, msg)

    # -- delab utilities -------------------------------------------------

    def unfold_aux_lemmas(self, src: str) -> str:
        return self._lib.leanpy_kernel_delab_unfold_aux_lemmas(src)

    def unfold_matchers(self, src: str) -> str:
        return self._lib.leanpy_kernel_delab_unfold_matchers(src)

    def instantiate_all(self, src: str) -> str:
        return self._lib.leanpy_kernel_delab_instantiate_all(src)

    def expr_proj_to_app(self, src: str) -> str:
        return self._lib.leanpy_kernel_delab_expr_proj_to_app(src)


__all__ = ["Kernel", "GoalState", "TacticResult"]
