"""Run the basic example after `lake build` in the sibling Lean project."""

from pathlib import Path

from lean_py import LeanLibrary


def main() -> None:
    lake_dir = Path(__file__).resolve().parent.parent / "lean"
    lib = LeanLibrary.from_lake(lake_dir, "Basic", build=True)

    print("py_increment(7)        =", lib.increment(7))
    print('py_greet("world")      =', lib.greet("world"))
    print("py_sum_array([1..10])  =", lib.sumArray(list(range(1, 11))))
    print("py_origin(())          =", lib.origin(None))
    print("py_norm_sq((3, 4))     =", lib.normSq(lib.Point(3, 4)))
    print("py_perimeter(circle 5) =", lib.perimeter(lib.Shape.circle(5)))
    print("py_perimeter(square 4) =", lib.perimeter(lib.Shape.square(4)))
    print("py_perimeter(rect 2 3) =", lib.perimeter(lib.Shape.rect(2, 3)))


if __name__ == "__main__":
    main()
