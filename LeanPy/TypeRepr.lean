/-
TypeRepr: a structural description of a Lean type, suitable for transmission
to Python. We deliberately keep this as a small, JSON-serializable inductive
so the Python side can reconstruct corresponding wrappers without needing
to know about Lean expressions.

The mapping between Lean types and `TypeRepr`:

  Nat                 ↦ .nat
  Int                 ↦ .int
  Bool                ↦ .bool
  String              ↦ .string
  Float / Float32     ↦ .float / .float32
  UInt8 .. UInt64     ↦ .uint <bits>
  Unit / PUnit        ↦ .unit
  Char                ↦ .char
  Array α             ↦ .array <repr α>
  List α              ↦ .list <repr α>
  Option α            ↦ .option <repr α>
  Prod α β            ↦ .prod <repr α> <repr β>
  Sum α β             ↦ .sum <repr α> <repr β>
  IO α                ↦ .io <repr α>
  Except ε α          ↦ .except <repr ε> <repr α>
  PyObject            ↦ .pyobject
  <named user type>   ↦ .named <fqname>

Anything else falls back to `.opaque <fqname>` and is exposed to Python as
an opaque handle (still ref-counted, but with no field accessors).
-/
import Lean.Data.Json

open Lean

namespace LeanPy

/-- Structural description of a Lean type that the Python side can reconstruct. -/
inductive TypeRepr where
  | unit
  | bool
  | nat
  | int
  | float
  | float32
  | uint   (bits : Nat)        -- 8, 16, 32, 64
  | sint   (bits : Nat)        -- 8, 16, 32, 64
  | char
  | string
  | array  (elem : TypeRepr)
  | list   (elem : TypeRepr)
  | option (elem : TypeRepr)
  | prod   (a b : TypeRepr)
  | sum    (a b : TypeRepr)
  | io     (elem : TypeRepr)
  | except (e a : TypeRepr)
  | pyobject
  | named  (n : Name)          -- a registered user type
  | opaque (n : Name)          -- an unknown / unsupported type
  deriving Inhabited, Repr, BEq

partial def TypeRepr.toJson : TypeRepr → Json
  | .unit         => Json.mkObj [("kind", "unit")]
  | .bool         => Json.mkObj [("kind", "bool")]
  | .nat          => Json.mkObj [("kind", "nat")]
  | .int          => Json.mkObj [("kind", "int")]
  | .float        => Json.mkObj [("kind", "float")]
  | .float32      => Json.mkObj [("kind", "float32")]
  | .uint b       => Json.mkObj [("kind", "uint"), ("bits", Json.num b)]
  | .sint b       => Json.mkObj [("kind", "sint"), ("bits", Json.num b)]
  | .char         => Json.mkObj [("kind", "char")]
  | .string       => Json.mkObj [("kind", "string")]
  | .array a      => Json.mkObj [("kind", "array"),  ("elem", a.toJson)]
  | .list  a      => Json.mkObj [("kind", "list"),   ("elem", a.toJson)]
  | .option a     => Json.mkObj [("kind", "option"), ("elem", a.toJson)]
  | .prod a b     => Json.mkObj [("kind", "prod"),   ("a", a.toJson), ("b", b.toJson)]
  | .sum a b      => Json.mkObj [("kind", "sum"),    ("a", a.toJson), ("b", b.toJson)]
  | .io a         => Json.mkObj [("kind", "io"),     ("elem", a.toJson)]
  | .except e a   => Json.mkObj [("kind", "except"), ("e", e.toJson), ("a", a.toJson)]
  | .pyobject     => Json.mkObj [("kind", "pyobject")]
  | .named n      => Json.mkObj [("kind", "named"),  ("name", toString n)]
  | .opaque n     => Json.mkObj [("kind", "opaque"), ("name", toString n)]

instance : ToJson TypeRepr := ⟨TypeRepr.toJson⟩

/-- Description of a single constructor of an inductive type. -/
structure CtorInfo where
  /-- Unqualified constructor name -/
  name   : String
  /-- Tag used by Lean's runtime (cidx) -/
  tag    : Nat
  /-- Field types in declaration order. -/
  fields : Array TypeRepr
  deriving Inhabited

def CtorInfo.toJson (c : CtorInfo) : Json :=
  Json.mkObj [
    ("name",   Json.str c.name),
    ("tag",    Json.num c.tag),
    ("fields", Json.arr (c.fields.map (fun t => t.toJson)))
  ]

instance : ToJson CtorInfo := ⟨CtorInfo.toJson⟩

/-- Structural description of a Lean inductive type. -/
structure TypeInfo where
  /-- Fully-qualified declaration name -/
  name        : Name
  /-- Whether the type was declared as `structure` or `inductive` -/
  isStructure : Bool := false
  /-- Whether at least one constructor has any fields. Enum-likes have all-empty ctors. -/
  isEnum      : Bool := false
  /-- Constructors, indexed by tag. -/
  ctors       : Array CtorInfo := #[]
  deriving Inhabited

def TypeInfo.toJson (t : TypeInfo) : Json :=
  Json.mkObj [
    ("name",        Json.str (toString t.name)),
    ("isStructure", Json.bool t.isStructure),
    ("isEnum",      Json.bool t.isEnum),
    ("ctors",       Json.arr (t.ctors.map (fun c => c.toJson)))
  ]

instance : ToJson TypeInfo := ⟨TypeInfo.toJson⟩

/-- Description of a Lean function exposed to Python. -/
structure FuncInfo where
  /-- Declaration name in Lean. -/
  declName    : Name
  /-- Symbol name used by `@[export]`; this is what Python looks up via dlsym. -/
  exportName  : String
  /-- Parameter types in order. -/
  params      : Array TypeRepr := #[]
  /-- Return type. -/
  returnType  : TypeRepr := .unit
  deriving Inhabited

def FuncInfo.toJson (f : FuncInfo) : Json :=
  Json.mkObj [
    ("declName",   Json.str (toString f.declName)),
    ("exportName", Json.str f.exportName),
    ("params",     Json.arr (f.params.map (fun t => t.toJson))),
    ("returnType", f.returnType.toJson)
  ]

instance : ToJson FuncInfo := ⟨FuncInfo.toJson⟩

end LeanPy
