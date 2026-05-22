"""Parse lean.h and extract declarations for runtime binding."""

import hashlib
import pickle
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import pycparser
from pycparser.c_parser import ParseError
import pycparser.c_ast as c_ast


# ============================================================================
# Data model
# ============================================================================

@dataclass
class StructField:
    name: str
    c_type: str
    is_pointer: bool = False
    bitfield: int | None = None


@dataclass
class StructDef:
    name: str
    fields: list[StructField]


@dataclass
class FuncParam:
    name: str
    c_type: str


@dataclass
class FuncDecl:
    name: str
    return_type: str
    params: list[FuncParam]
    is_variadic: bool = False


@dataclass
class TypedefDef:
    name: str
    underlying_type: str


@dataclass
class HeaderModel:
    structs: list[StructDef] = field(default_factory=list)
    constants: dict[str, int] = field(default_factory=dict)
    exported_functions: list[FuncDecl] = field(default_factory=list)
    inline_functions: list[FuncDecl] = field(default_factory=list)
    typedefs: list[TypedefDef] = field(default_factory=list)


# ============================================================================
# Header location
# ============================================================================

def find_lean_header() -> Path:
    """Locate lean.h via the active Lean toolchain.

    Strategy:
      1. Ask `lean --print-prefix` for the toolchain sysroot, look for
         `<prefix>/include/lean/lean.h`. This is the canonical location
         and works regardless of whether elan, lakefile, or a manual
         install picked the toolchain.
      2. Fall back to constructing the elan path from the project's
         `lean-toolchain` file, for callers who don't have `lean` on PATH.
    """
    try:
        prefix = subprocess.check_output(
            ["lean", "--print-prefix"], text=True
        ).strip()
        header = Path(prefix) / "include" / "lean" / "lean.h"
        if header.exists():
            return header
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass

    toolchain_file = Path(__file__).parent.parent / "lean-toolchain"
    if toolchain_file.exists():
        toolchain = toolchain_file.read_text().strip()
        toolchain_dir = toolchain.replace("/", "--").replace(":", "---")
        header = Path.home() / ".elan" / "toolchains" / toolchain_dir / "include" / "lean" / "lean.h"
        if header.exists():
            return header

    raise FileNotFoundError(
        "lean.h not found: ensure `lean` is on PATH (try `elan default <toolchain>`)"
    )


# ============================================================================
# Extraction
# ============================================================================

def extract_defines(header_path: Path) -> dict[str, int]:
    """Extract integer #define constants from raw header."""
    text = header_path.read_text()
    defines = {}
    pattern = re.compile(
        r"^\s*#define\s+((?:Lean|LEAN_)[A-Za-z_][A-Za-z0-9_]*)\s+(\d+)\s*$",
        re.MULTILINE,
    )
    for m in pattern.finditer(text):
        defines[m.group(1)] = int(m.group(2))
    return defines


def _preprocess(header_path: Path) -> Path:
    """Run cc -E and clean output for pycparser."""
    include_dir = header_path.parent.parent

    # -D flags strip GCC/Clang constructs that pycparser can't handle
    result = subprocess.run(
        [
            "cc", "-E",
            "-D__STDC_VERSION__=201112L",
            "-DNDEBUG",
            "-D__attribute__(x)=",
            "-D__attribute(x)=",
            "-D__extension__=",
            "-D__asm__(x)=",
            "-D__asm(x)=",
            "-D__restrict=",
            "-D__restrict__=",
            "-D__inline=",
            "-D__inline__=",
            "-D__volatile__=",
            "-D_Noreturn=",
            "-D__builtin_va_list=void*",
            "-D__builtin_offsetof(t,m)=0",
            "-D__signed__=signed",
            "-D_Bool=int",
            f"-I{include_dir}",
            str(header_path),
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"C preprocessor failed: {result.stderr}")

    text = result.stdout
    # Remove # line directives
    text = re.sub(r"^#\s*\d+\s+.*$", "", text, flags=re.MULTILINE)
    # Remove any remaining __attribute__ that slipped through (nested parens)
    text = re.sub(r"__attribute__\s*\(\(.*?\)\)", "", text, flags=re.DOTALL)
    # _Atomic(T) -> T
    text = re.sub(r"_Atomic\s*\(([^)]+)\)", r"\1", text)
    # Remove __asm__ volatile blocks
    text = re.sub(r"__asm__?\s+volatile\s*\([^)]*\)", "", text)
    text = re.sub(r"__asm__?\s*\([^)]*\)", "", text)
    text = re.sub(r"\basm\s*\([^)]*\)", "", text)
    # Remove remaining GCC-isms
    text = text.replace("__extension__", "")
    text = re.sub(r"\b__restrict\b", "", text)
    text = re.sub(r"\brestrict\b", "", text)
    text = re.sub(r"\b__inline__?\b", "", text)
    text = text.replace("__signed__", "signed")
    text = text.replace("_Noreturn", "")
    text = re.sub(r"\b__builtin_va_list\b", "void *", text)
    text = re.sub(r'extern\s+"C"\s*\{', "", text)
    text = re.sub(r"__typeof__\s*\([^)]*\)", "int", text)
    text = text.replace("LEAN_ALWAYS_INLINE", "")
    text = re.sub(r"\b_Bool\b", "int", text)

    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".h", delete=False)
    tmp.write(text)
    tmp.close()
    return Path(tmp.name)


# ============================================================================
# AST helpers
# ============================================================================

def _type_to_str(node) -> str:
    if node is None:
        return "void"
    if isinstance(node, c_ast.IdentifierType):
        return " ".join(node.names)
    if isinstance(node, c_ast.PtrDecl):
        return f"{_type_to_str(node.type)} *"
    if isinstance(node, c_ast.ArrayDecl):
        return f"{_type_to_str(node.type)} *"
    if isinstance(node, c_ast.TypeDecl):
        return _type_to_str(node.type)
    if isinstance(node, c_ast.Struct):
        return f"struct {node.name}" if node.name else "struct"
    if isinstance(node, c_ast.FuncDecl):
        return "void *"
    if isinstance(node, c_ast.Enum):
        return "int"
    return "void"


def _decl_type_to_str(decl) -> str:
    if isinstance(decl, (c_ast.PtrDecl, c_ast.ArrayDecl)):
        return _type_to_str(decl)
    if isinstance(decl, c_ast.TypeDecl):
        return _type_to_str(decl.type)
    if isinstance(decl, c_ast.FuncDecl):
        return "void *"
    return _type_to_str(decl)


def _extract_struct(node: c_ast.Struct) -> StructDef | None:
    if not node.decls:
        return None
    fields = []
    for decl in node.decls:
        fname = decl.name or ""
        ftype = _decl_type_to_str(decl.type)
        is_ptr = isinstance(decl.type, c_ast.PtrDecl)
        bitfield = None
        if decl.bitsize and isinstance(decl.bitsize, c_ast.Constant):
            bitfield = int(decl.bitsize.value)
        fields.append(StructField(name=fname, c_type=ftype, is_pointer=is_ptr, bitfield=bitfield))
    return StructDef(name=node.name or "", fields=fields)


def _extract_func_params(func_decl: c_ast.FuncDecl) -> tuple[list[FuncParam], bool]:
    params: list[FuncParam] = []
    is_variadic = False
    if func_decl.args is None:
        return params, False
    for param in func_decl.args.params or []:
        if isinstance(param, c_ast.EllipsisParam):
            is_variadic = True
            continue
        if isinstance(param, c_ast.Typename):
            ptype = _decl_type_to_str(param.type)
            if ptype == "void":
                continue
            params.append(FuncParam(name="", c_type=ptype))
        elif isinstance(param, c_ast.Decl):
            pname = param.name or ""
            ptype = _decl_type_to_str(param.type)
            if ptype == "void" and not pname:
                continue
            params.append(FuncParam(name=pname, c_type=ptype))
    return params, is_variadic


def _extract_export_names(header_path: Path) -> set[str]:
    text = header_path.read_text()
    pattern = re.compile(r"LEAN_EXPORT\s+(?:LEAN_NORETURN\s+)?[\w\s*]+\s+(\w+)\s*\(")
    return {m.group(1) for m in pattern.finditer(text)}


def _extract_inline_names(header_path: Path) -> set[str]:
    text = header_path.read_text()
    pattern = re.compile(r"static\s+inline\s+(?:LEAN_ALWAYS_INLINE\s+)?[\w\s*]+\s+(\w+)\s*\(")
    return {m.group(1) for m in pattern.finditer(text)}


# ============================================================================
# Classification
# ============================================================================

def _classify(ast: c_ast.FileAST, defines: dict[str, int], header_path: Path) -> HeaderModel:
    model = HeaderModel()
    model.constants = defines

    export_names = _extract_export_names(header_path)
    inline_names = _extract_inline_names(header_path)

    for node in ast.ext:
        if isinstance(node, c_ast.Typedef):
            if isinstance(node.type, c_ast.TypeDecl) and isinstance(node.type.type, c_ast.Struct):
                struct = _extract_struct(node.type.type)
                if struct:
                    struct.name = node.name
                    model.structs.append(struct)
                    continue
            typedef_type = _decl_type_to_str(node.type)
            model.typedefs.append(TypedefDef(name=node.name, underlying_type=typedef_type))

        elif isinstance(node, c_ast.Decl):
            if isinstance(node.type, c_ast.FuncDecl):
                func_decl = node.type
                ret_type = _decl_type_to_str(func_decl.type)
                params, is_variadic = _extract_func_params(func_decl)
                fname = node.name or ""
                func = FuncDecl(name=fname, return_type=ret_type, params=params, is_variadic=is_variadic)
                if fname in export_names:
                    model.exported_functions.append(func)
                elif fname in inline_names:
                    model.inline_functions.append(func)

        elif isinstance(node, c_ast.FuncDef):
            decl = node.decl
            if isinstance(decl.type, c_ast.FuncDecl):
                func_decl = decl.type
                ret_type = _decl_type_to_str(func_decl.type)
                params, is_variadic = _extract_func_params(func_decl)
                fname = decl.name or ""
                func = FuncDecl(name=fname, return_type=ret_type, params=params, is_variadic=is_variadic)
                if fname in inline_names:
                    model.inline_functions.append(func)
                elif fname in export_names:
                    model.exported_functions.append(func)

    return model


# ============================================================================
# Public API
# ============================================================================

_CACHE_DIR = Path(__file__).parent.parent / ".cache"


def get_header_model() -> HeaderModel:
    """Parse lean.h and return the HeaderModel, using a disk cache for speed."""
    header_path = find_lean_header()
    header_hash = hashlib.md5(header_path.read_bytes()).hexdigest()

    cache_file = _CACHE_DIR / f"lean_h_{header_hash}.pickle"
    if cache_file.exists():
        try:
            return pickle.loads(cache_file.read_bytes())
        except Exception:
            pass

    # Parse fresh
    preprocessed = _preprocess(header_path)
    parser = pycparser.CParser()
    with open(preprocessed) as f:
        source = f.read()
    try:
        ast = parser.parse(source, filename=str(preprocessed))
    except ParseError as e:
        raise RuntimeError(f"Failed to parse lean.h: {e}") from e
    finally:
        preprocessed.unlink(missing_ok=True)

    defines = extract_defines(header_path)
    model = _classify(ast, defines, header_path)

    # Cache
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file.write_bytes(pickle.dumps(model))

    return model
