"""Tests for `Kernel.elaborate` and the frontend fixes: Lean's messages kept,
`inherit_env` persisting declarations across calls, a source header skipped
(or refused, naming the missing modules), names returned unescaped, and
`lean_prefix` independent of the current directory."""

from __future__ import annotations

import os

import pytest

from lean_py import utils
from lean_py.kernel import Kernel, ProcessResult


@pytest.fixture(scope="module")
def kernel(example_lib) -> Kernel:
    k = Kernel(example_lib)
    if not k.is_loaded():
        k.init_search("")
        k.load(["Init"])
    return k


# ----------------------------------------------------------------------
# (a) messages and inherit_env
# ----------------------------------------------------------------------


def test_elaborate_reports_constants_per_command(kernel):
    r = kernel.elaborate("def kpA : Nat := 1\ntheorem kpB : kpA = 1 := rfl\n")
    assert isinstance(r, ProcessResult)
    assert r.ok and r.error is None and r.errors == []
    assert [c.constants for c in r.commands] == [["kpA"], ["kpB"]]
    assert [c.line for c in r.commands] == [1, 2]


def test_elaborate_keeps_error_messages_with_positions(kernel):
    r = kernel.elaborate('def kpC : Nat := 1\ndef kpD : Nat := "no"\n')
    assert not r.ok
    (err,) = r.errors
    assert err.severity == "error" and err.line == 2
    assert "String" in err.text or "mismatch" in err.text
    # the failed declaration is still added (with sorryAx), as before
    assert "kpD" in r.constants


def test_elaborate_keeps_information_messages(kernel):
    r = kernel.elaborate("#check (1 : Nat)\n")
    assert r.ok
    (m,) = r.messages
    assert m.severity == "information" and "Nat" in m.text


def test_without_inherit_env_declarations_do_not_persist(kernel):
    r = kernel.elaborate("def kpTransient : Nat := 5\n")
    assert r.ok
    assert not kernel.decl_exists("kpTransient")


def test_inherit_env_persists_declarations_across_calls(kernel):
    r = kernel.elaborate("def kpKept : Nat := 7\n", inherit_env=True)
    assert r.ok
    assert kernel.decl_exists("kpKept")
    assert "Nat" in kernel.decl_type("kpKept")
    r2 = kernel.elaborate("theorem kpKeptEq : kpKept = 7 := rfl\n", inherit_env=True)
    assert r2.ok, r2.errors
    assert kernel.decl_axioms("kpKeptEq") == []  # rfl: no axioms, no sorry
    assert kernel.elaborate("example : kpKept = 7 := kpKeptEq\n").ok


def test_inherit_env_with_errors_still_persists_what_elaborated(kernel):
    r = kernel.elaborate("def kpGood : Nat := 1\ndef kpBad : Nat := true\n", inherit_env=True)
    assert not r.ok
    assert kernel.decl_exists("kpGood")


# ----------------------------------------------------------------------
# (b) the header
# ----------------------------------------------------------------------


def test_a_header_of_loaded_imports_is_skipped(kernel):
    r = kernel.elaborate("import Init\n\ndef kpH : Nat := 2\n")
    assert r.ok and r.constants == ["kpH"]
    assert "kpH2" in kernel.process("import Init\ndef kpH2 : Nat := 3\n")


def test_a_module_header_is_skipped(kernel):
    r = kernel.elaborate("module\nimport Init\n\ndef kpM : Nat := 4\n")
    assert r.ok and r.constants == ["kpM"]


def test_a_header_importing_an_unloaded_module_is_an_error(kernel):
    r = kernel.elaborate("import Definitely.Not.Loaded\ndef kpX : Nat := 1\n")
    assert not r.ok and r.commands == []
    assert r.error is not None and "Definitely.Not.Loaded" in r.error
    out = kernel.process("import Definitely.Not.Loaded\ndef kpX : Nat := 1\n")
    assert out.startswith("<error:") and "Definitely.Not.Loaded" in out


# ----------------------------------------------------------------------
# (d) unescaped names
# ----------------------------------------------------------------------


def test_names_come_back_unescaped(kernel):
    r = kernel.elaborate("def «kp spaced» : Nat := 1\n", inherit_env=True)
    assert r.ok
    assert r.constants == ["kp spaced"]
    assert "kp spaced" in kernel.search("kp spaced")
    assert not any("«" in n for n in kernel.search("kp spaced"))
    out = kernel.process("def «kp other» : Nat := 1\n")
    assert out.strip() == "kp other"


# ----------------------------------------------------------------------
# (c) lean_prefix independent of the cwd
# ----------------------------------------------------------------------


@pytest.fixture
def fresh_prefix():
    """Clear lean_prefix's cache around a test, restoring the pin after."""
    pinned = utils._pinned
    utils.lean_prefix.cache_clear()
    yield
    utils._pinned = pinned
    utils.lean_prefix.cache_clear()


def test_lean_prefix_ignores_the_cwds_toolchain(tmp_path, monkeypatch, fresh_prefix):
    want = utils.lean_prefix()
    (tmp_path / "lean-toolchain").write_text("leanprover/lean4:v0.0.0-not-a-toolchain\n")
    monkeypatch.chdir(tmp_path)
    utils.lean_prefix.cache_clear()
    assert utils.lean_prefix() == want


def test_lean_prefix_honours_an_explicit_prefix(tmp_path, monkeypatch, fresh_prefix):
    monkeypatch.setenv(utils.PREFIX_ENV, str(tmp_path))
    assert utils.lean_prefix() == tmp_path


def test_set_toolchain_reads_a_projects_toolchain_file(tmp_path, monkeypatch, fresh_prefix):
    repo = utils.toolchain_of(os.path.join(os.path.dirname(__file__), ".."))
    (tmp_path / "lean-toolchain").write_text(f"{repo}\n")
    utils.set_toolchain(tmp_path)
    assert utils.pinned_toolchain() == repo
    assert (utils.lean_prefix() / "include" / "lean" / "lean.h").exists()
