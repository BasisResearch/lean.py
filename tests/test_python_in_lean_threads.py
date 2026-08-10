"""Concurrency hardening tests for the Python-in-Lean bridge.

The C bridge (`LeanPy/native/python_bridge.c`) acquires the GIL defensively
via `WITH_GIL()` around every entry point that touches the CPython C API.
`LeanLibrary` also loads the bridge with ctypes `PyDLL`, so the GIL is held
across the Lean call in the common path. These tests hammer the Python-in-Lean
entry points from many Python threads at once to guard against a regression
that drops the GIL handling (which would surface as a crash, deadlock, or
corrupted refcounts under load).
"""

from concurrent.futures import ThreadPoolExecutor

import pytest


def test_python_eval_int_concurrent(example_lib):
    """Many threads evaluating Python expressions through Lean concurrently."""

    def work(i: int) -> int:
        return example_lib.pythonEvalInt(f"{i} * {i}")

    n = 200
    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(work, range(n)))
    assert results == [i * i for i in range(n)]


def test_python_call_and_str_concurrent(example_lib):
    """Mix of C-API entry points (call, eval, str) hit from many threads."""

    def work(i: int):
        assert example_lib.pythonCall1Int("operator", "neg", i) == -i
        assert example_lib.pythonEvalStr(f"str({i}) + '!'") == f"{i}!"
        return True

    with ThreadPoolExecutor(max_workers=16) as pool:
        assert all(pool.map(work, range(200)))


def test_python_eval_errors_concurrent(example_lib):
    """Errors raised inside Lean callbacks stay isolated across threads."""

    def work(i: int) -> bool:
        with pytest.raises(RuntimeError):
            example_lib.pythonEvalInt("undefined_name")
        return True

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert all(pool.map(work, range(64)))
