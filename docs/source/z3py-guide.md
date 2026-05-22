# A Z3-style Symbolic Reasoning API for Python, backed by Lean 4

Lean 4 is a general-purpose symbolic reasoning engine. Its tactic library covers linear arithmetic (`omega`), congruence closure with E-matching (`grind`), propositional decidability (`decide`), and rewriting (`simp`), and the system is designed to be extended with new sorts, constructors, and decision procedures. Every proof is independently checked by a small trusted kernel, so the Python side never needs to trust the automation; it trusts the checker. The overhead of learning Lean's type theory and build system has kept most of this machinery out of reach for Python programmers.

`lean_py.z3` wraps Lean's tactic engine in the z3py API. Propositions are written in the familiar `Int`, `Bool`, `Function`, `ForAll` vocabulary. Under the hood, each expression compiles to a Lean 4 term, gets dispatched to the tactic engine, and the resulting proof is kernel-checked.

```bash
uv pip install "lean_py @ git+https://github.com/BasisResearch/lean.py"
```

You need [elan](https://github.com/leanprover/elan) so that `lean` is on your PATH. Then open Python.

```python
from lean_py.z3 import *

x, y = Ints('x y')
prove(Implies(And(x > 0, y > 0), x + y > 0))
# proved
```

On the first run the library builds and caches a managed Lake project under `~/.lean_py/managed/`, which takes a minute or two. Every subsequent run picks up the cache and starts instantly.


## Boolean Logic

The most natural starting point is propositional reasoning. Declare some boolean variables, state a claim, and ask Lean to prove it.

```python
p, q, r = Bools('p q r')

prove(Implies(Not(And(p, q)), Or(Not(p), Not(q))))  # De Morgan
prove(Implies(And(p, Implies(p, q)), q))              # modus ponens
prove(And(p, q) == And(q, p))                         # commutativity
```

`prove` negates the claim and checks whether Lean can derive a contradiction. If it can, the original claim is a theorem. The boolean connectives are `And`, `Or`, `Not`, `Implies`, `Xor`, and `If` (if-then-else). Python operators `&`, `|`, `~` also work on `BoolRef`.

```python
prove((p & q) == (q & p))
prove(~(~p) == p)
```

`BoolVal` constructs literal truth values, and `BoolVector` creates indexed lists of boolean variables.

```python
prove(And(BoolVal(True), p) == p)

xs = BoolVector('x', 5)  # [x__0, x__1, x__2, x__3, x__4]
prove(Implies(And(*xs), xs[0]))
```


## Solvers

Proving tautologies is useful, but most real problems involve checking whether a set of constraints is consistent. The `Solver` class handles this.

```python
x = Int('x')
s = Solver()
s.add(x > 0)
s.add(x < 0)
print(s.check())  # unsat
```

Lean is a proof checker, so the solver works by negating the conjunction of all assertions and trying to prove the negation. If the proof goes through, the constraints are contradictory and `check()` returns `unsat`. If the tactics cannot close the goal, it returns `unknown`. It will never return `sat`, because Lean proves theorems rather than searching for satisfying assignments.

Push/pop scoping lets you explore constraint spaces incrementally, adding constraints and then rolling them back.

```python
s = Solver()
x = Int('x')
s.add(x > 0)
s.push()
s.add(x < 0)
print(s.check())  # unsat
s.pop()
# x < 0 is gone, only x > 0 remains
```

Internally, `check()` tries `grind`, `omega`, `decide`, and `simp_all` in sequence, and the first tactic to discharge the goal wins. The `solve` function is shorthand for the common pattern of creating a solver, adding constraints, and checking.

```python
solve(x > 0, x < 0)  # unsat
```


## Arithmetic

Integer and real arithmetic both work, with all the Python operators you would expect.

```python
x, y, z = Ints('x y z')

prove(x + y == y + x)                                      # commutativity
prove((x + y) + z == x + (y + z))                          # associativity
prove(Implies(And(x > 0, y > 0), x + y > 0))               # monotonicity
prove(Implies(x * x == 4, Or(x == 2, x == -2)))            # factoring
```

The same operators work for reals, which are Lean's mathematical reals rather than floating-point approximations.

```python
a, b = Reals('a b')

prove(Implies(And(a > 0, b > 0), a + b > 0))
prove(a + b == b + a)
```

`IntVal`, `RealVal`, and `RatVal` (aliased as `Q`) construct literal values.

```python
prove(IntVal(3) + IntVal(4) == IntVal(7))
prove(RealVal(1) / RealVal(3) + RealVal(2) / RealVal(3) == RealVal(1))
prove(Q(1, 3) + Q(2, 3) == Q(1, 1))
```

Natural numbers compile to Lean's `Nat` type, which means `omega` can reason about them directly.

```python
n = Nat('n')
prove(n + NatVal(0) == n)
```

`Sum` and `Product` fold over lists, and `Abs` gives you absolute value. Other arithmetic utilities include `ToReal`, `ToInt`, and `IsInt`.

```python
xs = [Int(f'x_{i}') for i in range(4)]
prove(Sum(xs) == xs[0] + xs[1] + xs[2] + xs[3])

x = Int('x')
prove(Abs(x) >= 0)
prove(Implies(x >= 0, Abs(x) == x))
```


## Satisfiability and Validity

The distinction between these two concepts is worth making precise, because the Lean backend handles them differently from a classical SMT solver.

A formula is **valid** when it holds for every assignment to its free variables. A formula is **satisfiable** when at least one assignment makes it true. Validity is the dual of unsatisfiability: `F` is valid iff `Not(F)` is unsatisfiable.

`prove(F)` checks validity by trying to prove `Not(F)` contradictory. `Solver.check()` checks whether the conjunction of assertions is contradictory.

```python
p, q = Bools('p q')

# Valid: a tautology
prove(Or(p, Not(p)))

# Satisfiable but not valid
s = Solver()
s.add(And(p, q))
print(s.check())  # unknown (cannot prove contradiction, so constraints are consistent)
```

Because Lean is a proof checker rather than a model-finding solver, `check()` can only return `unsat` or `unknown`, and there is no way to extract a satisfying assignment. For problems where you need a model, you still want Z3 proper.


## Machine Arithmetic

Mathematical integers are clean, but real hardware computes with fixed-width registers. Bit-vectors model exactly this: a fixed width tracked in the type, with arithmetic that wraps on overflow just as it does on a CPU.

```python
x, y = BitVecs('x y', 32)

prove(BitVecVal(0xFFFFFFFF, 32) + BitVecVal(1, 32) == BitVecVal(0, 32))  # overflow wraps

prove((x & y) == (y & x))
prove((x | 0) == x)
prove((x ^ x) == BitVecVal(0, 32))
prove((~x) == (BitVecVal(-1, 32) ^ x))
```

Signed vs unsigned comparisons matter. The Python operators `<`, `<=`, `>`, `>=` are signed (matching z3py), which means `0xFF` on an 8-bit vector is `-1`. For unsigned comparisons, use `ULT`, `ULE`, `UGT`, `UGE`.

```python
x = BitVec('x', 8)

prove(BitVecVal(0xFF, 8) < BitVecVal(0, 8))     # signed: 0xFF is -1
prove(UGT(BitVecVal(0xFF, 8), BitVecVal(0, 8)))  # unsigned: 0xFF is 255
```

`Extract` pulls out bit ranges, `Concat` joins bit-vectors, and `ZeroExt`/`SignExt` widen them.

```python
x = BitVec('x', 16)
hi = Extract(15, 8, x)   # upper byte
lo = Extract(7, 0, x)    # lower byte
prove(Concat(hi, lo) == x)

y = BitVec('y', 8)
prove(ZeroExt(8, y) == Concat(BitVecVal(0, 8), y))
prove(SignExt(8, BitVecVal(0xFF, 8)) == BitVecVal(0xFFFF, 16))
```

`<<` and `>>` are built-in (arithmetic shift right, which sign-extends). `LShR` gives you the logical shift right that zero-fills.

```python
x = BitVec('x', 8)
prove(LShR(BitVecVal(0x80, 8), 1) == BitVecVal(0x40, 8))  # logical: 0 fill
prove((BitVecVal(0x80, 8) >> 1) == BitVecVal(0xC0, 8))     # arithmetic: sign fill
```

Division comes in signed (`SDiv`/`SRem`) and unsigned (`UDiv`/`URem`) variants.

```python
a, b = BitVecs('a b', 8)
prove(UDiv(BitVecVal(7, 8), BitVecVal(2, 8)) == BitVecVal(3, 8))
```

`BVRedAnd` and `BVRedOr` reduce all bits to a single-bit result. `RepeatBitVec` tiles a bit-vector. `BvNand`, `BvNor`, `BvXnor` are the compound bitwise operations.

```python
x = BitVec('x', 4)
prove(BVRedAnd(BitVecVal(0xF, 4)) == BitVecVal(1, 1))
prove(BVRedOr(BitVecVal(0, 4)) == BitVecVal(0, 1))
prove(RepeatBitVec(2, BitVecVal(0xA, 4)) == BitVecVal(0xAA, 8))
```

Overflow detection predicates are particularly useful for verifying C-style integer code, where undefined behaviour lurks in signed overflow.

```python
a, b = BitVecs('a b', 8)
prove(Implies(BVAddNoOverflow(a, b, signed=False), UGE(a + b, a)))
```

`BV2Int` and `Int2BV` bridge bit-vectors and mathematical integers.

```python
x = BitVec('x', 8)
prove(Implies(ULE(x, BitVecVal(10, 8)), BV2Int(x) <= 10))
```


## Functions

All the examples so far reason about concrete operations: addition, bitwise AND, comparison. Uninterpreted functions go a level up. You declare a function with a name and a signature, and the prover knows exactly one fact about it: equal inputs produce equal outputs. Everything else is left abstract.

```python
f = Function('f', IntSort(), IntSort())
x, y = Ints('x y')

prove(Implies(x == y, f(x) == f(y)))              # congruence
prove(Implies(And(f(x) == 0, f(y) == 1), x != y))  # different outputs, different inputs
```

Multi-argument functions take their domain sorts first and the range sort last.

```python
g = Function('g', IntSort(), IntSort(), BoolSort())
x, y = Ints('x y')
prove(Implies(g(x, y), g(x, y)))
```

When you do want a concrete implementation, `RecFunction` and `RecAddDefinition` let you define recursive functions that the prover can unfold.

```python
fac = RecFunction('fac', IntSort(), IntSort())
n = Int('n')
RecAddDefinition(fac, [n], If(n <= 0, IntVal(1), n * fac(n - 1)))
prove(fac(IntVal(5)) == IntVal(120))
```


## Uninterpreted Sorts

Uninterpreted functions abstract over implementations. Uninterpreted sorts abstract over types. `DeclareSort` creates an opaque type with no built-in structure, and combined with functions over that type, you can encode arbitrary first-order theories.

The classic example is the Socrates syllogism: all men are mortal, Socrates is a man, therefore Socrates is mortal.

```python
Entity = DeclareSort('Entity')
Man = Function('Man', Entity, BoolSort())
Mortal = Function('Mortal', Entity, BoolSort())
socrates = Const('socrates', Entity)
e = Const('e', Entity)

prove(Implies(
    And(ForAll([e], Implies(Man(e), Mortal(e))),
        Man(socrates)),
    Mortal(socrates),
))
```


## Quantifiers

The Socrates example above already used `ForAll`. Quantifiers let you make universal and existential claims over any sort.

```python
x = Int('x')
prove(ForAll([x], x + 0 == x))
prove(ForAll([x], Implies(x > 0, x >= 1)))
prove(Exists([x], x * x == 4))
```

They take a list of bound variables and a body, and you can bind several variables at once.

```python
x, y = Ints('x y')
prove(ForAll([x, y], x + y == y + x))
```

The `QuantifierRef` wrapper exposes the body, bound variable names, and sorts for programmatic inspection.

```python
x = Int('x')
q = ForAll([x], x >= 0)
print(q.body())        # x >= 0
print(q.num_vars())    # 1
print(q.var_name(0))   # x
print(q.is_forall())   # True
```


## Arrays

Program verification constantly needs to reason about memory, and the SMT encoding of memory is the array: a total map from an index sort to a value sort. `Select` reads, `Store` writes, and `K` creates a constant array where every index maps to the same value.

```python
A = Array('A', IntSort(), IntSort())
x, y = Ints('x y')

# Read-over-write: reading the index you just wrote gives back the value
prove(Select(Store(A, x, y), x) == y)

# Writing to one index does not affect a different index
prove(Implies(x != y, Select(Store(A, x, IntVal(10)), y) == Select(A, y)))

# Constant array: every index maps to zero
B = K(IntSort(), IntVal(0))
prove(Select(B, IntVal(42)) == IntVal(0))
```

`Map` applies a function element-wise across arrays, and `Lambda` constructs an array from a function body.

```python
f = Function('f', IntSort(), IntSort())
A = Array('A', IntSort(), IntSort())

mapped = Map(f, A)
x = Int('x')
prove(Select(mapped, x) == f(Select(A, x)))
```

The `[]` operator on `ArrayRef` is sugar for `Select`.

```python
A = Array('A', IntSort(), IntSort())
x = Int('x')
prove(A[x] == Select(A, x))
```


## Sets

Sets are arrays with boolean range. Where an array maps indices to values, a set maps elements to membership. `IsMember` checks membership, `SetAdd` inserts an element, `SetDel` removes one.

```python
S = Const('S', SetSort(IntSort()))
x = Int('x')

S2 = SetAdd(S, IntVal(3))
prove(IsMember(IntVal(3), S2))
prove(Implies(IsMember(x, S), IsMember(x, SetUnion(S, EmptySet(IntSort())))))
```

The standard set algebra is all here: `SetUnion`, `SetIntersect`, `SetComplement`, `SetDifference`, `IsSubset`.

```python
A = Const('A', SetSort(IntSort()))
B = Const('B', SetSort(IntSort()))
x = Int('x')

prove(Implies(IsSubset(A, B), Implies(IsMember(x, A), IsMember(x, B))))
```

`EmptySet` and `FullSet` are the identity elements for union and intersection. `Singleton` creates a one-element set.

```python
prove(IsMember(IntVal(5), Singleton(IntVal(5))))
```


## Algebraic Datatypes

All the sorts so far are built-in: integers, booleans, bit-vectors, arrays. Algebraic datatypes let you define your own. In z3py they are backed by Z3's internal datatype solver. In `lean_py.z3` they compile to real Lean 4 inductive types, which means the kernel gives you constructor injectivity, disjointness of constructors, and exhaustive case analysis for free.

### Enumerations

```python
Color, (red, green, blue) = EnumSort('Color', ['red', 'green', 'blue'])

prove(red != green)
prove(red != blue)
prove(green != blue)
```

### Records

```python
Pair = Datatype('Pair')
Pair.declare('mk_pair', ('fst', IntSort()), ('snd', IntSort()))
Pair = Pair.create()

x, y = Ints('x y')

# Injectivity: equal pairs have equal components
prove(Implies(
    Pair.mk_pair(x, y) == Pair.mk_pair(1, 2),
    And(x == 1, y == 2)
))

# Accessor projection
prove(Pair.fst(Pair.mk_pair(1, 2)) == IntVal(1))
prove(Pair.snd(Pair.mk_pair(1, 2)) == IntVal(2))
```

### Recursive Datatypes

For self-referential fields, pass the builder object itself as the sort. The library handles the circular reference when it registers the inductive in Lean's environment.

```python
Tree = Datatype('Tree')
Tree.declare('leaf', ('val', IntSort()))
Tree.declare('node', ('left', Tree), ('right', Tree))
Tree = Tree.create()

t1 = Tree.leaf(IntVal(1))
t2 = Tree.node(Tree.leaf(IntVal(1)), Tree.leaf(IntVal(2)))
prove(t1 != t2)  # different constructors are disjoint
```

### Recognisers

Every constructor gets an `is_<name>` predicate that tests whether a value was built with that constructor.

```python
prove(Tree.is_leaf(Tree.leaf(IntVal(1))))
prove(Not(Tree.is_leaf(t2)))
prove(Tree.is_node(t2))
```

### DatatypeSortRef API

The sort object exposes constructor, recogniser, and accessor metadata by index, which is useful for writing generic code over datatype definitions.

```python
print(Tree.num_constructors())  # 2
print(Tree.constructor(0))       # leaf constructor
print(Tree.recognizer(0))        # is_leaf recognizer
print(Tree.accessor(0, 0))       # val accessor (ctor 0, field 0)
print(Tree.accessor(1, 0))       # left accessor (ctor 1, field 0)
```

### Convenience Constructors

Declaring constructors field by field is explicit but verbose. `TupleSort` builds a named tuple type in one call, returning the sort, the constructor, and a list of accessor functions.

```python
Pair, mk_pair, [fst, snd] = TupleSort('Pair', [IntSort(), IntSort()])
prove(fst(mk_pair(IntVal(3), IntVal(4))) == IntVal(3))
```

`DisjointSum` builds a tagged union where each sort gets an injector and a projector.

```python
DS, injectors = DisjointSum('DS', [IntSort(), BoolSort()])
inject_int, project_int = injectors[0]
inject_bool, project_bool = injectors[1]
prove(project_int(inject_int(IntVal(42))) == IntVal(42))
```

`CreateDatatypes` registers multiple datatype builders at once, which is needed for mutual recursion.

```python
Fruit = Datatype('Fruit')
Fruit.declare('apple')
Fruit.declare('banana')
(Fruit,) = CreateDatatypes(Fruit)
prove(Fruit.apple != Fruit.banana)
```


## Strings

String constraints arise naturally in web security (input validation, injection attacks) and protocol verification. The string sort supports length, containment, prefix/suffix testing, and the rest of the standard SMT string theory.

```python
s = String('s')
t = String('t')

prove(Implies(s == StringVal("hello"), Length(s) == 5))
prove(Contains(StringVal("hello world"), StringVal("world")))
prove(PrefixOf(StringVal("he"), StringVal("hello")))
prove(SuffixOf(StringVal("lo"), StringVal("hello")))
```

Substrings, character indexing, and replacement all work as you would expect.

```python
prove(SubString(StringVal("abcdef"), 2, 3) == StringVal("cde"))
prove(At(StringVal("hello"), 0) == StringVal("h"))
prove(IndexOf(StringVal("hello"), StringVal("ll"), 0) == 2)
prove(Replace(StringVal("aab"), StringVal("a"), StringVal("x")) == StringVal("xab"))
```

Strings convert to and from integers and character codes.

```python
prove(StrToInt(StringVal("42")) == 42)
prove(IntToStr(IntVal(42)) == StringVal("42"))
prove(StrToCode(StringVal("A")) == 65)
prove(StrFromCode(IntVal(65)) == StringVal("A"))
```

`StrConcat` joins strings. The full set of string operations: `Length`, `Contains`, `PrefixOf`, `SuffixOf`, `Replace`, `SubString`, `IndexOf`, `LastIndexOf`, `StrConcat`, `StrToInt`, `IntToStr`, `At`, `StrToCode`, `StrFromCode`.

```python
prove(StrConcat(StringVal("he"), StringVal("llo")) == StringVal("hello"))
```


## Regular Expressions

String constraints often need pattern matching. The regex sort gives you a combinator library for building patterns and testing membership with `InRe`.

```python
s = String('s')
digit = Range('0', '9')
number = Plus(digit)

prove(Implies(InRe(s, number), Length(s) > 0))
```

The combinators follow the standard regex algebra: `Re` (literal), `Star` (Kleene star), `Plus` (one or more), `Option` (zero or one), `Union`, `Intersect`, `Complement`, `Range` (character range), `Loop` (bounded repetition), `AllChar`, and `Diff`.

```python
prove(InRe(StringVal("abc"), Re(StringVal("abc"))))

prove(InRe(StringVal(""), Star(Re(StringVal("a")))))
prove(InRe(StringVal("aaa"), Star(Re(StringVal("a")))))

prove(InRe(StringVal(""), Option(Re(StringVal("a")))))

ab = Union(Re(StringVal("a")), Re(StringVal("b")))
prove(InRe(StringVal("a"), ab))
prove(InRe(StringVal("b"), ab))

prove(InRe(StringVal("aaa"), Loop(Re(StringVal("a")), 2, 4)))
```


## Floating Point

IEEE 754 floating-point arithmetic is notoriously tricky to reason about. NaN is not equal to itself, positive and negative zero are distinct representations that compare equal, and rounding makes every operation approximate. The floating-point sort lets you state and prove properties about all of this.

Predefined sorts: `Float16()`, `Float32()`, `Float64()`, `Float128()`. Custom sorts via `FPSort(ebits, sbits)`.

```python
nan = fpNaN(Float64())
pinf = fpPlusInfinity(Float64())
pzero = fpPlusZero(Float64())
mzero = fpMinusZero(Float64())

prove(Not(fpEQ(nan, nan)))       # NaN != NaN
prove(fpEQ(pzero, mzero))        # +0.0 == -0.0
```

Every arithmetic operation takes a rounding mode as its first argument. The five IEEE rounding modes are `RNE()` (nearest ties to even), `RNA()` (nearest ties away), `RTP()` (toward positive), `RTN()` (toward negative), and `RTZ()` (toward zero).

```python
rm = RNE()
x = FPVal(1.5, Float64())
y = FPVal(2.5, Float64())
prove(fpEQ(fpAdd(rm, x, y), FPVal(4.0, Float64())))
```

Arithmetic: `fpAdd`, `fpSub`, `fpMul`, `fpDiv`, `fpNeg`, `fpAbs`, `fpSqrt`, `fpFMA`, `fpRem`, `fpMin`, `fpMax`, `fpRoundToIntegral`. Comparisons: `fpEQ`, `fpNEQ`, `fpLT`, `fpLEQ`, `fpGT`, `fpGEQ`. Classification: `fpIsNaN`, `fpIsInf`, `fpIsZero`, `fpIsNormal`, `fpIsSubnormal`, `fpIsNegative`, `fpIsPositive`. Conversions: `fpToReal`, `fpToSBV`, `fpToUBV`, `fpToFP`, `fpBVToFP`, `fpRealToFP`, `fpSignedToFP`, `fpUnsignedToFP`, `fpToIEEEBV`.

You can construct an FP value from its sign, exponent, and significand bit-vectors with `fpFP`.

```python
sgn = BitVecVal(0, 1)       # positive
exp = BitVecVal(127, 8)     # exponent for 1.0 in float32
sig = BitVecVal(0, 23)      # significand
val = fpFP(sgn, exp, sig)   # 1.0 as Float32
```


## Pseudo-Boolean Constraints

Some problems are naturally expressed as counting constraints over booleans: at most `k` of these flags can be true, or the weighted sum of these booleans must equal a target. `AtMost` and `AtLeast` handle the unweighted case.

```python
p, q, r = Bools('p q r')

prove(Implies(AtMost([p, q, r], 1), Not(And(p, q))))
prove(Implies(AtLeast([p, q, r], 3), And(p, And(q, r))))
```

`PbEq([(b, w), ...], k)` asserts that the weighted sum of booleans equals `k`, where each boolean contributes its weight when true. `PbLe` and `PbGe` give you the inequality variants.

```python
prove(Implies(PbEq([(p, 2), (q, 3)], 5), And(p, q)))
```


## Characters and Finite Domains

The character sort reasons about individual characters and their integer codes, and finite domain sorts have a fixed number of elements.

```python
prove(CharToInt(CharVal('A')) == 65)
prove(CharIsDigit(CharVal('7')))
prove(Not(CharIsDigit(CharVal('x'))))

FD = FiniteDomainSort('FD', 5)
prove(FiniteDomainVal(0, FD) == FiniteDomainVal(0, FD))
print(FiniteDomainSize(FD))  # 5
```


## Tactics and Goals

Everything so far uses `prove` and `Solver.check`, which run a fixed sequence of tactics internally. When the default sequence falls short, the tactic API gives you direct access to Lean's full tactic engine, which is substantially more powerful.

A `Goal` holds a list of propositions. A `Tactic` transforms a goal into zero or more subgoals. Zero subgoals means the proof is complete.

```python
g = Goal()
x = Int('x')
g.add(Implies(x > 0, x >= 1))

t = Tactic("omega")
result = t.apply(g)
print(len(result))  # 0 subgoals means proved
```

### Tactic Combinators

`Then` sequences tactics, `OrElse` tries alternatives, and `Repeat` loops until nothing changes.

```python
t = Then(Tactic("simp"), Tactic("omega"))
t = OrElse(Tactic("decide"), Tactic("grind"))
t = Repeat(Tactic("simp"))
```

`ParOr` runs tactics in parallel and takes the first success. `TryFor` sets a timeout. `With` passes parameters.

### Arbitrary Lean Tactics

You can pass any valid Lean tactic string directly. Consider proving exhaustiveness over an enum: the built-in tactics cannot handle this alone, but a custom tactic script with case analysis discharges all subgoals immediately.

```python
Color, (red, green, blue) = EnumSort('Color', ['red', 'green', 'blue'])
x = Const('x', Color)

g = Goal()
g.add(Or(x == red, x == green, x == blue))
t = Tactic("intro x; cases x <;> simp")
result = t.apply(g)
assert len(result) == 0  # all cases discharged
```

### Available Tactics

There are 34 registered tactics. `tactic_description(name)` gives a one-line description, and `describe_tactics()` prints them all.

```python
print(tactics())
# ['grind', 'omega', 'decide', 'simp', 'simp_all', 'norm_num',
#  'ring', 'linarith', 'positivity', 'polyrith', 'field_simp',
#  'aesop', 'tauto', 'trivial', 'assumption', 'contradiction',
#  'exact?', 'apply?', 'rfl', 'ext', 'funext', 'congr',
#  'constructor', 'cases', 'induction', 'rcases', 'obtain',
#  'use', 'existsi', 'left', 'right', 'exfalso', 'push_neg']
```

### Probes

Probes measure properties of goals and can be combined with `Cond` to select tactics based on goal structure.

```python
t = Cond(Probe("is-qflia"), Tactic("omega"), Tactic("grind"))
```

```python
print(probes())
# ['num-consts', 'num-exprs', 'size', 'depth', 'arity',
#  'is-propositional', 'is-qflia', 'is-qfbv', 'is-qfaufbv', ...]
```

### The Simplifier

The `Simplifier` class wraps `simp` and related normalisation tactics as an `ApplyResult`-returning interface.

```python
simp = Simplifier("simp")
g = Goal()
g.add(And(BoolVal(True), p))
result = simp.apply(g)
```


## SMT-LIB2 Parsing

Many verification tools emit constraints in SMT-LIB2 format. `parse_smt2_string` parses this format directly into z3py expressions, so you can feed constraints from other tools into lean_py's prover.

```python
assertions = parse_smt2_string('''
    (declare-const x Int)
    (declare-const y Int)
    (assert (> x 0))
    (assert (< y 10))
''')
print(len(assertions))  # 2
```

You can pass in pre-declared symbols and sort aliases so the parser can reference variables you have already created.

```python
x, y = Ints('x y')
f = Function('f', IntSort(), IntSort())

assertions = parse_smt2_string(
    '(assert (> (+ foo (g bar)) 0))',
    decls={'foo': x, 'bar': y, 'g': f}
)

assertions = parse_smt2_string(
    '(declare-const a U) (assert (> a 0))',
    sorts={'U': IntSort()}
)
```

`parse_smt2_file` does the same from a file path.

```python
assertions = parse_smt2_file('constraints.smt2')
```

The parser handles `declare-const`, `declare-fun`, `declare-sort`, `define-sort`, `define-fun`, `assert`, `let` bindings, `forall`/`exists`, and all arithmetic, boolean, bit-vector, array, and quantifier operations.


## Fixedpoint (Datalog)

The `Fixedpoint` class encodes Datalog-style rules as universally quantified implications and proves queries via the tactic engine. You declare relations, add facts and rules, then query whether a relation holds for specific values.

```python
fp = Fixedpoint()
Edge = Function('Edge', IntSort(), IntSort(), BoolSort())
Path = Function('Path', IntSort(), IntSort(), BoolSort())
a, b, c = Ints('a b c')

fp.register_relation(Edge, Path)
fp.declare_var(a, b, c)

fp.fact(Edge(1, 2))
fp.fact(Edge(2, 3))
fp.rule(Path(a, b), Edge(a, b))
fp.rule(Path(a, c), [Edge(a, b), Path(b, c)])

print(fp.query(Path(1, 3)))  # sat (the path exists)
print(fp.query(Path(1, 4)))  # unknown (cannot prove it)
```


## List Comprehensions

Python's list comprehensions work naturally for building constraint sets programmatically. This is particularly useful for problems with regular structure, like grid puzzles or scheduling constraints.

```python
xs = [Int(f'x_{i}') for i in range(5)]
distinct = [xs[i] != xs[j] for i in range(5) for j in range(i+1, 5)]
prove(Implies(And(*distinct), xs[0] != xs[4]))

bounded = [And(x >= 0, x < 10) for x in xs]
```

`IntVector`, `BoolVector`, and `RealVector` are shortcuts for creating indexed variable lists, and the `Fresh*` family generates variables with unique names for use in loops.

```python
xs = IntVector('x', 10)     # [x__0, x__1, ..., x__9]
bs = BoolVector('b', 5)     # [b__0, b__1, ..., b__4]
rs = RealVector('r', 3)     # [r__0, r__1, r__2]

ys = [FreshInt() for _ in range(5)]  # x!0, x!1, x!2, ...
```


## Substitution and Lambdas

`substitute` replaces subexpressions in a term by matching on identity.

```python
x, y, z = Ints('x y z')
e = x + y + z
e2 = substitute(e, (x, IntVal(1)), (y, IntVal(2)))
prove(e2 == 1 + 2 + z)
```

`Lambda` constructs an anonymous function represented as an array. `Distinct` asserts that all arguments are pairwise different, and works on any sort.

```python
x = Int('x')
f = Lambda([x], x + 1)
prove(Select(f, IntVal(5)) == IntVal(6))

x, y, z = Ints('x y z')
prove(Implies(Distinct(x, y, z), And(x != y, x != z, y != z)))
```


## Puzzles

### Eight Queens

One integer variable per row encodes the column placement. We cannot extract a solution from Lean, but we can prove that forcing two queens into the same column makes the constraints contradictory.

```python
Q = [Int(f'Q_{i}') for i in range(8)]
s = Solver()

for i in range(8):
    s.add(And(Q[i] >= 1, Q[i] <= 8))

for i in range(8):
    for j in range(i+1, 8):
        s.add(Q[i] != Q[j])
        s.add(Q[i] - Q[j] != i - j)
        s.add(Q[i] - Q[j] != j - i)

print(s.check())  # unknown (consistent)

s.push()
s.add(Q[0] == Q[1])
print(s.check())   # unsat (contradictory)
s.pop()
```

### Dog, Cat, and Mouse

Spend exactly 100 dollars buying exactly 100 animals. Dogs cost 15, cats cost 1, mice cost 0.25. We cannot search for a solution, but given one we can verify it.

```python
dog, cat, mouse = Ints('dog cat mouse')
prove(Implies(
    And(dog == 3, cat == 41, mouse == 56),
    And(dog + cat + mouse == 100,
        15 * dog + cat + mouse * Q(1, 4) == 100)
))
```


## Expression Introspection

Expressions expose their structure for programmatic analysis: sort, child nodes, head declaration, and S-expression representation. The `is_*` predicates let you pattern-match on expression structure.

```python
x, y = Ints('x y')
e = x + y * 2

print(e.sort())        # Int
print(e.num_args())    # 2
print(e.arg(0))        # x
print(e.arg(1))        # y * 2
print(e.decl().name()) # HAdd.hAdd
print(e.sexpr())       # S-expression

print(is_add(e))       # True
print(is_int(x))       # True
print(is_bool(x > 0))  # True
print(is_const(x))     # True
```


## Serialisation

`.sexpr()` prints S-expressions for expressions, and `.to_smt2()` exports the solver's full state as SMT-LIB2.

```python
x = Int('x')
s = Solver()
s.add(x > 0)
print(s.sexpr())    # (declare-const x Int)\n(assert (> x 0))
print(s.to_smt2())  # full SMT-LIB2 with check-sat
```


## Advanced Setup

The kernel initialises lazily from a `ManagedProject` the first time you call `prove` or `Solver.check`, so the examples above all work without any explicit setup. If you want to pull in additional Lean libraries like Batteries or Mathlib, or point the kernel at your own Lake project, you can initialise it yourself.

```python
from lean_py.project import ManagedProject
from lean_py.z3 import *

mp = ManagedProject.get(deps=("batteries",))
set_kernel(mp.kernel())
```

If you already have a Lake project, point the kernel at it directly.

```python
from lean_py import LeanLibrary
from lean_py.kernel import Kernel
from lean_py.z3 import *

lib = LeanLibrary.from_lake("path/to/project", "MyLib", build=True)
k = Kernel(lib)
k.init_search("")
k.load(["Init"])
set_kernel(k)
```


## What Works

Lean's `grind`, `omega`, `decide`, `simp`, and the other 30+ registered tactics cover a broad range of automated reasoning: (1) propositional logic, complete via `decide`, (2) linear integer and natural number arithmetic, complete via `omega`, (3) congruence closure with uninterpreted functions via `grind`, (4) datatype reasoning including constructor injectivity, disjointness, and exhaustive case splits, (5) quantified formulas that `grind` can instantiate, (6) bit-vector reasoning when reducible to bounded arithmetic, and (7) string and regex membership proofs.

Lean proves theorems rather than finding satisfying assignments. `Solver.model()` raises `NotImplementedError`, `check()` returns `unsat` or `unknown` (never `sat`), and `Optimize` is a placeholder. Nonlinear arithmetic involving products of two variables may time out. Mutually recursive datatypes are not yet supported. For constraint satisfaction and model finding, you still want Z3 proper.


## Comparison with z3py

| Feature | z3py | lean_py.z3 |
|---|---|---|
| Backend | Z3 SMT solver | Lean 4 kernel + grind |
| `check()` results | sat, unsat, unknown | unsat, unknown |
| Model generation | Yes | No |
| Proof certificates | No | Yes (Lean kernel) |
| Datatypes | Interpreted in Z3 | Real Lean inductives |
| Custom tactics | No | Yes (any Lean tactic) |
| `parse_smt2_string` | Via Z3 C API | Pure Python parser |
| Install | `pip install z3-solver` | `uv pip install lean_py` + elan |
