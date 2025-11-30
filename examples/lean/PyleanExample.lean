-- This module serves as the root of the `PyleanExample` library.
-- Import modules here that should be built as part of the library.
import LeanPy


@[python "py_bar"]
def bar(x: Int) : Int := x + 1


@[python "py_foo"]
def foo(x: Int) : IO Int := do
  println! "foo({x})"
  return x + 1
  
