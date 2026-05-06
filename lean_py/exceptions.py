"""
Typed exceptions raised by lean-py at the Python ↔ Lean boundary.

The Lean runtime can fail in two distinct ways from Python's vantage:

1. **Lean IO error.** A `@[python]`-annotated function returning `IO α`
   ran but produced an `IO.Error`. `_format_io_error` in `marshal.py`
   decodes the error ctor and raises `LeanError`.

2. **Python error caught inside Lean.** A `@[python]` function called
   back into Python (via `LeanPy.Python.*`) and CPython raised. The
   bridge translates this into a Lean `IO.userError` whose payload
   carries the Python exception type and message. When that propagates
   back across the boundary the Python wrapper re-raises it as
   `LeanPyCallbackError` so the *original* Python exception type is
   visible at the call site.

Both inherit from `LeanError` so user code can `except LeanError:`
catch either.
"""

from __future__ import annotations


class LeanError(RuntimeError):
    """Base class for any error raised by lean-py at the FFI boundary.

    Attributes:
        kind: short tag identifying the Lean `IO.Error` constructor
              (`userError`, `fileNotFound`, `unsupportedOperation`,
              `invalidArgument`, `permissionDenied`, `interrupted`,
              `noFileOrDirectory`, `inappropriateType`, `unexpected`,
              `otherError`, `python`, ...). The set is open-ended;
              new Lean toolchains may add ctors.
        message: human-readable description.
        context: optional dict of extra fields decoded from the ctor
                 (e.g. `path` for `fileNotFound`).
    """

    __slots__ = ("kind", "message", "context")

    def __init__(self, kind: str, message: str,
                 context: dict | None = None) -> None:
        self.kind = kind
        self.message = message
        self.context = context or {}
        # Build a useful str() — RuntimeError uses the first arg.
        super().__init__(self._format())

    def _format(self) -> str:
        if self.context:
            ctx = ", ".join(f"{k}={v!r}" for k, v in self.context.items())
            return f"[{self.kind}] {self.message}  ({ctx})"
        return f"[{self.kind}] {self.message}"


class LeanPyCallbackError(LeanError):
    """Raised when a Python exception was thrown inside a Python callback
    that Lean was driving (`LeanPy.Python.eval`/`call`/...).

    The original Python exception's type name and message are preserved.

    Attributes:
        python_type: e.g. `"ZeroDivisionError"`, `"KeyError"`. This is
                     the *name* of the original Python exception class.
        python_message: the original `str(exc)`.
    """

    __slots__ = ("python_type", "python_message")

    def __init__(self, python_type: str, python_message: str) -> None:
        self.python_type = python_type
        self.python_message = python_message
        super().__init__(
            kind="python",
            message=f"{python_type}: {python_message}",
            context={"python_type": python_type, "python_message": python_message},
        )


def parse_io_error_message(raw: str) -> tuple[str, str]:
    """Parse a Lean `IO.userError` string produced by `raise_py_error`.

    The C bridge formats Python errors as `"<TypeName>: <message>"`. If
    `raw` matches that shape, return `(typeName, message)`. Otherwise
    return `("", raw)` and let the caller wrap it as a generic LeanError.
    """
    if not raw:
        return "", ""
    sep = raw.find(": ")
    if sep <= 0:
        return "", raw
    typename = raw[:sep]
    # Heuristic: Python exception type names are CamelCase identifiers,
    # no whitespace. Anything else is probably not a Python error.
    if not typename.replace("_", "").isalnum() or not typename:
        return "", raw
    if not typename[0].isupper():
        return "", raw
    return typename, raw[sep + 2:]


__all__ = [
    "LeanError",
    "LeanPyCallbackError",
    "parse_io_error_message",
]
