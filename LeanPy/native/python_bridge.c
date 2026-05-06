/*
 * LeanPy: C side of the Python-in-Lean bridge.
 *
 * We dlopen libpython at runtime (rather than linking against it) so the
 * library can be built without Python headers and only loads Python when
 * `LeanPy.Python.initialize` is called.
 *
 * All `lean_py_*` functions exposed here are referenced by `@[extern]`
 * declarations in `LeanPy/Python.lean`.
 *
 * Convention for IO entry points: signature
 *   lean_obj_res lean_py_<name>(<args>, lean_obj_arg world);
 * returns `lean_io_result_mk_ok(value)` or `lean_io_result_mk_error(err)`.
 */
#include <lean/lean.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dlfcn.h>

/* ------------------------------------------------------------------ */
/*  Forward-declared opaque CPython types                              */
/* ------------------------------------------------------------------ */

typedef struct PyObject_s PyObject;
typedef ssize_t           Py_ssize_t;

/* ------------------------------------------------------------------ */
/*  CPython entry points loaded by dlsym                               */
/* ------------------------------------------------------------------ */

static int          py_initialized = 0;
static void        *py_handle      = NULL;

/* PyGILState_STATE is an enum (int). */
typedef int PyGILState_STATE;

#define PYSYMS \
    X(void,        Py_Initialize,            (void)) \
    X(void,        Py_Finalize,              (void)) \
    X(int,         Py_IsInitialized,         (void)) \
    X(PyGILState_STATE, PyGILState_Ensure,   (void)) \
    X(void,        PyGILState_Release,       (PyGILState_STATE)) \
    X(void,        Py_IncRef,                (PyObject *)) \
    X(void,        Py_DecRef,                (PyObject *)) \
    X(int,         PyErr_Occurred,           (void)) \
    X(void,        PyErr_Clear,              (void)) \
    X(void,        PyErr_Fetch,              (PyObject **, PyObject **, PyObject **)) \
    X(void,        PyErr_NormalizeException, (PyObject **, PyObject **, PyObject **)) \
    X(PyObject *,  PyObject_Str,             (PyObject *)) \
    X(PyObject *,  PyObject_Repr,            (PyObject *)) \
    X(const char *, PyUnicode_AsUTF8,        (PyObject *)) \
    X(PyObject *,  PyUnicode_FromStringAndSize, (const char *, Py_ssize_t)) \
    X(PyObject *,  PyUnicode_DecodeUTF8,     (const char *, Py_ssize_t, const char *)) \
    X(PyObject *,  PyBool_FromLong,          (long)) \
    X(int,         PyObject_IsTrue,          (PyObject *)) \
    X(PyObject *,  PyLong_FromLongLong,      (long long)) \
    X(long long,   PyLong_AsLongLong,        (PyObject *)) \
    X(PyObject *,  PyFloat_FromDouble,       (double)) \
    X(double,      PyFloat_AsDouble,         (PyObject *)) \
    X(PyObject *,  PyBytes_FromStringAndSize,(const char *, Py_ssize_t)) \
    X(PyObject *,  PyImport_ImportModule,    (const char *)) \
    X(PyObject *,  PyObject_GetAttrString,   (PyObject *, const char *)) \
    X(int,         PyObject_SetAttrString,   (PyObject *, const char *, PyObject *)) \
    X(int,         PyObject_HasAttrString,   (PyObject *, const char *)) \
    X(PyObject *,  PyObject_GetItem,         (PyObject *, PyObject *)) \
    X(int,         PyObject_SetItem,         (PyObject *, PyObject *, PyObject *)) \
    X(Py_ssize_t,  PyObject_Length,          (PyObject *)) \
    X(PyObject *,  PyObject_Call,            (PyObject *, PyObject *, PyObject *)) \
    X(PyObject *,  PyObject_CallObject,      (PyObject *, PyObject *)) \
    X(int,         PyObject_RichCompareBool, (PyObject *, PyObject *, int)) \
    X(PyObject *,  PyObject_Type,            (PyObject *)) \
    X(PyObject *,  PyTuple_New,              (Py_ssize_t)) \
    X(int,         PyTuple_SetItem,          (PyObject *, Py_ssize_t, PyObject *)) \
    X(PyObject *,  PyList_New,               (Py_ssize_t)) \
    X(int,         PyList_SetItem,           (PyObject *, Py_ssize_t, PyObject *)) \
    X(PyObject *,  PyDict_New,               (void)) \
    X(int,         PyDict_SetItem,           (PyObject *, PyObject *, PyObject *)) \
    X(int,         PyDict_SetItemString,     (PyObject *, const char *, PyObject *)) \
    X(PyObject *,  PyImport_AddModule,       (const char *)) \
    X(PyObject *,  PyModule_GetDict,         (PyObject *)) \
    X(PyObject *,  PyEval_GetBuiltins,       (void)) \
    X(PyObject *,  PyRun_StringFlags,        (const char *, int, PyObject *, PyObject *, void *)) \
    X(PyObject *,  PyNumber_Add,             (PyObject *, PyObject *)) \
    X(PyObject *,  PyNumber_Subtract,        (PyObject *, PyObject *)) \
    X(PyObject *,  PyNumber_Multiply,        (PyObject *, PyObject *)) \
    X(PyObject *,  PyNumber_TrueDivide,      (PyObject *, PyObject *)) \
    X(PyObject *,  PyNumber_Power,           (PyObject *, PyObject *, PyObject *)) \
    X(PyObject *,  PyNumber_Negative,        (PyObject *)) \

/* ssize_t is signed; mark equality opcodes from object.h */
#define Py_EQ 2
/* compile mode for PyRun_String */
#define Py_eval_input  258
#define Py_file_input  257
#define Py_single_input 256

/* Statically declare function pointers. */
#define X(ret, name, args) static ret (*p_##name) args = NULL;
PYSYMS
#undef X

/* These globals are looked up by name via dlsym after we know py_handle. */
static PyObject *p_Py_None  = NULL;
static PyObject *p_Py_True  = NULL;
static PyObject *p_Py_False = NULL;

/* ------------------------------------------------------------------ */
/*  Helpers for Python-side use (allocator + refcount + boxing)        */
/*                                                                    */
/*  These are exported as `leanpy_*` so the Python ctypes binding can  */
/*  invoke the static-inline versions in `lean.h` without depending on */
/*  Lean-runtime allocator details (LEAN_SMALL_ALLOCATOR / mimalloc).  */
/* ------------------------------------------------------------------ */

LEAN_EXPORT lean_object * leanpy_alloc_ctor(unsigned tag, unsigned num_objs, unsigned scalar_sz) {
    return lean_alloc_ctor(tag, num_objs, scalar_sz);
}

LEAN_EXPORT void leanpy_ctor_set(b_lean_obj_arg o, unsigned i, lean_obj_arg v) {
    lean_ctor_set(o, i, v);
}

LEAN_EXPORT lean_object * leanpy_ctor_get(b_lean_obj_arg o, unsigned i) {
    return lean_ctor_get(o, i);
}

LEAN_EXPORT lean_object * leanpy_alloc_array(size_t size, size_t capacity) {
    return lean_alloc_array(size, capacity);
}

LEAN_EXPORT void leanpy_array_set_core(b_lean_obj_arg o, size_t i, lean_obj_arg v) {
    lean_array_set_core(o, i, v);
}

LEAN_EXPORT void leanpy_inc(b_lean_obj_arg o) { lean_inc(o); }
LEAN_EXPORT void leanpy_dec(lean_obj_arg o)   { lean_dec(o); }
LEAN_EXPORT void leanpy_inc_ref(b_lean_obj_arg o) { lean_inc_ref(o); }
LEAN_EXPORT void leanpy_dec_ref(lean_obj_arg o)   { lean_dec_ref(o); }
LEAN_EXPORT void leanpy_inc_ref_n(b_lean_obj_arg o, size_t n) { lean_inc_ref_n(o, n); }

LEAN_EXPORT lean_object * leanpy_box(size_t v) { return lean_box(v); }
LEAN_EXPORT size_t        leanpy_unbox(b_lean_obj_arg o) { return lean_unbox(o); }
LEAN_EXPORT lean_object * leanpy_box_uint64(uint64_t v) { return lean_box_uint64(v); }
LEAN_EXPORT uint64_t      leanpy_unbox_uint64(b_lean_obj_arg o) { return lean_unbox_uint64(o); }
LEAN_EXPORT lean_object * leanpy_box_float(double v) { return lean_box_float(v); }
LEAN_EXPORT double        leanpy_unbox_float(b_lean_obj_arg o) { return lean_unbox_float(o); }

LEAN_EXPORT lean_object * leanpy_int_to_int(int n) { return lean_int_to_int(n); }
LEAN_EXPORT lean_object * leanpy_int64_to_int(int64_t n) { return lean_int64_to_int(n); }
LEAN_EXPORT int64_t       leanpy_int64_of_int(b_lean_obj_arg o) { return lean_int64_of_int(o); }
LEAN_EXPORT lean_object * leanpy_uint64_to_nat(uint64_t n) { return lean_uint64_to_nat(n); }
LEAN_EXPORT uint64_t      leanpy_uint64_of_nat(b_lean_obj_arg o) { return lean_uint64_of_nat(o); }

/* IO result helpers */
LEAN_EXPORT lean_object * leanpy_io_result_mk_ok(lean_obj_arg v) {
    return lean_io_result_mk_ok(v);
}

/* External object access (lazy creation of the Py class is done in
 * get_py_class above; these helpers are for general external objects). */

/* ------------------------------------------------------------------ */
/*  Lean external class for PyObject*                                  */
/* ------------------------------------------------------------------ */

static lean_external_class *g_py_class = NULL;

static void py_finalize(void *p) {
    if (p_Py_DecRef && p) p_Py_DecRef((PyObject *)p);
}
static void py_foreach(void *p, b_lean_obj_arg f) {
    (void)p;
    (void)f;
}

static lean_external_class *get_py_class(void) {
    if (!g_py_class) {
        g_py_class = lean_register_external_class(py_finalize, py_foreach);
    }
    return g_py_class;
}

static lean_object *wrap_pyobject(PyObject *o) {
    return lean_alloc_external(get_py_class(), o);
}

static PyObject *unwrap_pyobject(b_lean_obj_arg obj) {
    return (PyObject *)lean_get_external_data(obj);
}

/* Python-side helper: extract the wrapped `PyObject*` from a Lean
 * external-class handle. Bumps the Python refcount so the caller
 * receives an owned reference. The Lean handle's own reference is
 * untouched. Returns NULL if `obj` is not a wrapped PyObject (e.g.
 * a different external class, or initialisation hasn't happened).
 *
 * Used by `lean_py.marshal` to convert a `Py` handle returned from
 * Lean into a live Python object the caller can use directly. */
LEAN_EXPORT void * leanpy_unwrap_pyobject(b_lean_obj_arg obj) {
    if (!py_initialized) return NULL;
    if (!lean_is_external(obj)) return NULL;
    PyObject *o = unwrap_pyobject(obj);
    if (!o) return NULL;
    p_Py_IncRef(o);
    return (void *)o;
}

/* ------------------------------------------------------------------ */
/*  Error mapping                                                      */
/* ------------------------------------------------------------------ */

static lean_object *raise_io_error(const char *msg) {
    return lean_io_result_mk_error(
        lean_mk_io_user_error(lean_mk_string(msg)));
}

/* If a Python exception is set, fetch a string for it, clear, and return
 * a Lean IO error result. Caller transfers ownership. */
static lean_object *raise_py_error(void) {
    PyObject *etype = NULL, *evalue = NULL, *etb = NULL;
    p_PyErr_Fetch(&etype, &evalue, &etb);
    p_PyErr_NormalizeException(&etype, &evalue, &etb);
    char buf[1024];
    const char *etname = "PythonError";
    const char *emsg = "";
    if (evalue) {
        PyObject *s = p_PyObject_Str(evalue);
        if (s) {
            const char *cs = p_PyUnicode_AsUTF8(s);
            if (cs) emsg = cs;
        }
        if (etype) {
            PyObject *tn = p_PyObject_GetAttrString(etype, "__name__");
            if (tn) {
                const char *cn = p_PyUnicode_AsUTF8(tn);
                if (cn) etname = cn;
            }
        }
        snprintf(buf, sizeof(buf), "%s: %s", etname, emsg);
        if (s) p_Py_DecRef(s);
    } else {
        snprintf(buf, sizeof(buf), "Python error (no value)");
    }
    if (etype)  p_Py_DecRef(etype);
    if (evalue) p_Py_DecRef(evalue);
    if (etb)    p_Py_DecRef(etb);
    return raise_io_error(buf);
}

/* Wrap an owned PyObject as IO Py; if NULL, propagate any pending Py error. */
static lean_object *ok_owned_or_err(PyObject *o) {
    if (!o) return raise_py_error();
    return lean_io_result_mk_ok(wrap_pyobject(o));
}

/* ------------------------------------------------------------------ */
/*  initialize                                                         */
/* ------------------------------------------------------------------ */

/* Try a list of candidate sonames for libpython. */
static const char *const PY_CANDIDATES[] = {
#if defined(__APPLE__)
    "libpython3.13.dylib",
    "libpython3.12.dylib",
    "libpython3.11.dylib",
    "libpython3.10.dylib",
    "libpython3.9.dylib",
    "libpython3.dylib",
#else
    "libpython3.13.so.1.0",
    "libpython3.12.so.1.0",
    "libpython3.11.so.1.0",
    "libpython3.10.so.1.0",
    "libpython3.9.so.1.0",
    "libpython3.so",
#endif
    NULL
};

/* Ask `python3` (or `python`) on PATH where its own libpython lives.
 * This handles pyenv / uv-managed / framework Pythons whose libdir
 * isn't on the dyld search path. The call is one-shot and only runs
 * during the first `LeanPy.Python.init`. */
static int try_python_subprocess(const char *python_exe) {
    char cmd[512];
    int n = snprintf(cmd, sizeof(cmd),
        "%s -c 'import os, sysconfig; "
        "libdir = sysconfig.get_config_var(\"LIBDIR\"); "
        "soname = sysconfig.get_config_var(\"INSTSONAME\") "
                 "or sysconfig.get_config_var(\"LDLIBRARY\"); "
        "print(os.path.join(libdir, soname) "
              "if libdir and soname else \"\")' 2>/dev/null",
        python_exe);
    if (n <= 0 || (size_t)n >= sizeof(cmd)) return 0;
    FILE *fp = popen(cmd, "r");
    if (!fp) return 0;
    char buf[4096];
    char *line = fgets(buf, sizeof(buf), fp);
    pclose(fp);
    if (!line) return 0;
    size_t len = strlen(line);
    while (len > 0 && (line[len-1] == '\n' || line[len-1] == '\r')) line[--len] = '\0';
    if (len == 0) return 0;
    py_handle = dlopen(line, RTLD_NOW | RTLD_GLOBAL);
    return py_handle != NULL;
}

static int try_load_python(void) {
    /* 1. Prefer libpython already loaded into the process (this is
     *    the typical case when LeanPy runs inside a Python host —
     *    using a different libpython would cause two independent
     *    CPython VMs and immediate crashes). */
    py_handle = dlopen(NULL, RTLD_LAZY);
    if (py_handle && dlsym(py_handle, "Py_Initialize")) return 1;
    py_handle = NULL;

    /* 2. Honour LEANPY_LIBPYTHON if set. */
    const char *override = getenv("LEANPY_LIBPYTHON");
    if (override && *override) {
        py_handle = dlopen(override, RTLD_NOW | RTLD_GLOBAL);
        if (py_handle) return 1;
    }

    /* 3. Ask python3 / python on PATH for its libpython. Catches
     *    pyenv, uv, and framework installs whose lib dir isn't in
     *    the dyld search path. */
    if (try_python_subprocess("python3")) return 1;
    if (try_python_subprocess("python")) return 1;

    /* 4. Fall back to common sonames (relies on dyld search path). */
    for (int i = 0; PY_CANDIDATES[i]; i++) {
        py_handle = dlopen(PY_CANDIDATES[i], RTLD_NOW | RTLD_GLOBAL);
        if (py_handle) return 1;
    }
    return 0;
}

LEAN_EXPORT lean_obj_res lean_py_initialize(lean_obj_arg unit, lean_obj_arg world) {
    (void)world;
    if (py_initialized) {
        return lean_io_result_mk_ok(lean_box(0));
    }
    if (!try_load_python()) {
        return raise_io_error("LeanPy: could not load libpython (set LEANPY_LIBPYTHON to override)");
    }
#define X(ret, name, args)                                          \
    p_##name = (ret (*) args) dlsym(py_handle, #name);              \
    if (!p_##name) {                                                \
        return raise_io_error("LeanPy: dlsym failed for " #name);   \
    }
    PYSYMS
#undef X
    /* Singletons. */
    p_Py_None  = (PyObject *) dlsym(py_handle, "_Py_NoneStruct");
    p_Py_True  = (PyObject *) dlsym(py_handle, "_Py_TrueStruct");
    p_Py_False = (PyObject *) dlsym(py_handle, "_Py_FalseStruct");
    if (!p_Py_None || !p_Py_True || !p_Py_False) {
        return raise_io_error("LeanPy: failed to resolve Py_None/True/False");
    }
    if (!p_Py_IsInitialized()) {
        p_Py_Initialize();
    }
    py_initialized = 1;
    return lean_io_result_mk_ok(lean_box(0));
}

LEAN_EXPORT lean_obj_res lean_py_is_initialized(lean_obj_arg unit, lean_obj_arg world) {
    (void)world;
    uint8_t v = py_initialized ? 1 : 0;
    return lean_io_result_mk_ok(lean_box(v));
}

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

#define ENSURE_INIT()                                                  \
    do {                                                               \
        if (!py_initialized) {                                         \
            return raise_io_error("LeanPy: Python not initialized; call LeanPy.Python.initialize"); \
        }                                                              \
    } while (0)

/* Acquire the GIL for the duration of a Python C API call. The macro
 * declares a `_gil_state` variable and releases it on `WITH_GIL_END`. */
#define WITH_GIL_BEGIN() \
    PyGILState_STATE _gil_state = p_PyGILState_Ensure();
#define WITH_GIL_END() \
    p_PyGILState_Release(_gil_state);

/* ------------------------------------------------------------------ */
/*  Singletons                                                         */
/* ------------------------------------------------------------------ */

LEAN_EXPORT lean_obj_res lean_py_none(lean_obj_arg unit, lean_obj_arg world) {
    (void)world; ENSURE_INIT();
    p_Py_IncRef(p_Py_None);
    return lean_io_result_mk_ok(wrap_pyobject(p_Py_None));
}
LEAN_EXPORT lean_obj_res lean_py_true(lean_obj_arg unit, lean_obj_arg world) {
    (void)world; ENSURE_INIT();
    p_Py_IncRef(p_Py_True);
    return lean_io_result_mk_ok(wrap_pyobject(p_Py_True));
}
LEAN_EXPORT lean_obj_res lean_py_false(lean_obj_arg unit, lean_obj_arg world) {
    (void)world; ENSURE_INIT();
    p_Py_IncRef(p_Py_False);
    return lean_io_result_mk_ok(wrap_pyobject(p_Py_False));
}

/* ------------------------------------------------------------------ */
/*  Conversions: Lean → Python                                         */
/* ------------------------------------------------------------------ */

LEAN_EXPORT lean_obj_res lean_py_of_bool(uint8_t b, lean_obj_arg world) {
    (void)world; ENSURE_INIT();
    return ok_owned_or_err(p_PyBool_FromLong(b ? 1 : 0));
}

/* Lean's `Int` may be a small scalar or a big integer (mpz). For now we
 * support the int64 range and error otherwise; this is what 99% of API
 * surface needs. Callers needing arbitrary precision can stringify. */
LEAN_EXPORT lean_obj_res lean_py_of_int64(b_lean_obj_arg n, lean_obj_arg world) {
    (void)world; ENSURE_INIT();
    long long v;
    if (lean_is_scalar(n)) {
        v = (long long) lean_scalar_to_int64(n);
    } else {
        /* big int: stringify via Lean would be ideal; for now reject. */
        return raise_io_error("LeanPy: Int out of int64 range not supported");
    }
    return ok_owned_or_err(p_PyLong_FromLongLong(v));
}

LEAN_EXPORT lean_obj_res lean_py_of_float(double f, lean_obj_arg world) {
    (void)world; ENSURE_INIT();
    return ok_owned_or_err(p_PyFloat_FromDouble(f));
}

LEAN_EXPORT lean_obj_res lean_py_of_string(b_lean_obj_arg s, lean_obj_arg world) {
    (void)world; ENSURE_INIT();
    const char *cs = lean_string_cstr(s);
    size_t n = lean_string_size(s) - 1; /* size includes terminating NUL */
    return ok_owned_or_err(p_PyUnicode_DecodeUTF8(cs, (Py_ssize_t)n, NULL));
}

LEAN_EXPORT lean_obj_res lean_py_of_bytes(b_lean_obj_arg ba, lean_obj_arg world) {
    (void)world; ENSURE_INIT();
    Py_ssize_t n = (Py_ssize_t) lean_sarray_size(ba);
    const char *p = (const char *) lean_sarray_cptr(ba);
    return ok_owned_or_err(p_PyBytes_FromStringAndSize(p, n));
}

LEAN_EXPORT lean_obj_res lean_py_of_list(b_lean_obj_arg arr, lean_obj_arg world) {
    (void)world; ENSURE_INIT();
    size_t n = lean_array_size(arr);
    PyObject *list = p_PyList_New((Py_ssize_t)n);
    if (!list) return raise_py_error();
    for (size_t i = 0; i < n; i++) {
        lean_object *elem = lean_array_get_core(arr, i);
        PyObject *po = unwrap_pyobject(elem);
        p_Py_IncRef(po);                         /* PyList_SetItem steals */
        p_PyList_SetItem(list, (Py_ssize_t)i, po);
    }
    return lean_io_result_mk_ok(wrap_pyobject(list));
}

LEAN_EXPORT lean_obj_res lean_py_of_tuple(b_lean_obj_arg arr, lean_obj_arg world) {
    (void)world; ENSURE_INIT();
    size_t n = lean_array_size(arr);
    PyObject *tup = p_PyTuple_New((Py_ssize_t)n);
    if (!tup) return raise_py_error();
    for (size_t i = 0; i < n; i++) {
        lean_object *elem = lean_array_get_core(arr, i);
        PyObject *po = unwrap_pyobject(elem);
        p_Py_IncRef(po);
        p_PyTuple_SetItem(tup, (Py_ssize_t)i, po);
    }
    return lean_io_result_mk_ok(wrap_pyobject(tup));
}

LEAN_EXPORT lean_obj_res lean_py_of_dict(b_lean_obj_arg arr, lean_obj_arg world) {
    (void)world; ENSURE_INIT();
    PyObject *d = p_PyDict_New();
    if (!d) return raise_py_error();
    size_t n = lean_array_size(arr);
    for (size_t i = 0; i < n; i++) {
        /* Each element is a Prod Py Py — a 2-arg ctor object. */
        lean_object *kv = lean_array_get_core(arr, i);
        lean_object *kobj = lean_ctor_get(kv, 0);
        lean_object *vobj = lean_ctor_get(kv, 1);
        PyObject *k = unwrap_pyobject(kobj);
        PyObject *v = unwrap_pyobject(vobj);
        if (p_PyDict_SetItem(d, k, v) != 0) {
            p_Py_DecRef(d);
            return raise_py_error();
        }
    }
    return lean_io_result_mk_ok(wrap_pyobject(d));
}

/* ------------------------------------------------------------------ */
/*  Conversions: Python → Lean                                         */
/* ------------------------------------------------------------------ */

LEAN_EXPORT lean_obj_res lean_py_to_bool(b_lean_obj_arg p, lean_obj_arg world) {
    (void)world; ENSURE_INIT();
    int r = p_PyObject_IsTrue(unwrap_pyobject(p));
    if (r < 0) return raise_py_error();
    return lean_io_result_mk_ok(lean_box(r ? 1 : 0));
}

LEAN_EXPORT lean_obj_res lean_py_to_int64(b_lean_obj_arg p, lean_obj_arg world) {
    (void)world; ENSURE_INIT();
    long long v = p_PyLong_AsLongLong(unwrap_pyobject(p));
    if (v == -1 && p_PyErr_Occurred()) return raise_py_error();
    return lean_io_result_mk_ok(lean_int64_to_int((int64_t) v));
}

LEAN_EXPORT lean_obj_res lean_py_to_float(b_lean_obj_arg p, lean_obj_arg world) {
    (void)world; ENSURE_INIT();
    double d = p_PyFloat_AsDouble(unwrap_pyobject(p));
    if (d == -1.0 && p_PyErr_Occurred()) return raise_py_error();
    return lean_io_result_mk_ok(lean_box_float(d));
}

static lean_object *py_obj_to_lean_string(PyObject *s) {
    if (!s) return raise_py_error();
    const char *cs = p_PyUnicode_AsUTF8(s);
    if (!cs) {
        p_Py_DecRef(s);
        return raise_py_error();
    }
    lean_object *out = lean_mk_string(cs);
    p_Py_DecRef(s);
    return lean_io_result_mk_ok(out);
}

LEAN_EXPORT lean_obj_res lean_py_to_string(b_lean_obj_arg p, lean_obj_arg world) {
    (void)world; ENSURE_INIT();
    return py_obj_to_lean_string(p_PyObject_Str(unwrap_pyobject(p)));
}

LEAN_EXPORT lean_obj_res lean_py_repr(b_lean_obj_arg p, lean_obj_arg world) {
    (void)world; ENSURE_INIT();
    return py_obj_to_lean_string(p_PyObject_Repr(unwrap_pyobject(p)));
}

LEAN_EXPORT lean_obj_res lean_py_str(b_lean_obj_arg p, lean_obj_arg world) {
    (void)world; ENSURE_INIT();
    return py_obj_to_lean_string(p_PyObject_Str(unwrap_pyobject(p)));
}

LEAN_EXPORT lean_obj_res lean_py_type_name(b_lean_obj_arg p, lean_obj_arg world) {
    (void)world; ENSURE_INIT();
    PyObject *ty = p_PyObject_Type(unwrap_pyobject(p));
    if (!ty) return raise_py_error();
    PyObject *nm = p_PyObject_GetAttrString(ty, "__name__");
    p_Py_DecRef(ty);
    return py_obj_to_lean_string(nm);
}

/* ------------------------------------------------------------------ */
/*  Object access                                                      */
/* ------------------------------------------------------------------ */

LEAN_EXPORT lean_obj_res lean_py_getattr(b_lean_obj_arg p, b_lean_obj_arg name, lean_obj_arg world) {
    (void)world; ENSURE_INIT();
    return ok_owned_or_err(p_PyObject_GetAttrString(unwrap_pyobject(p), lean_string_cstr(name)));
}

LEAN_EXPORT lean_obj_res lean_py_setattr(b_lean_obj_arg p, b_lean_obj_arg name, b_lean_obj_arg v, lean_obj_arg world) {
    (void)world; ENSURE_INIT();
    int r = p_PyObject_SetAttrString(unwrap_pyobject(p), lean_string_cstr(name), unwrap_pyobject(v));
    if (r != 0) return raise_py_error();
    return lean_io_result_mk_ok(lean_box(0));
}

LEAN_EXPORT lean_obj_res lean_py_hasattr(b_lean_obj_arg p, b_lean_obj_arg name, lean_obj_arg world) {
    (void)world; ENSURE_INIT();
    int r = p_PyObject_HasAttrString(unwrap_pyobject(p), lean_string_cstr(name));
    return lean_io_result_mk_ok(lean_box(r ? 1 : 0));
}

LEAN_EXPORT lean_obj_res lean_py_getitem(b_lean_obj_arg p, b_lean_obj_arg k, lean_obj_arg world) {
    (void)world; ENSURE_INIT();
    return ok_owned_or_err(p_PyObject_GetItem(unwrap_pyobject(p), unwrap_pyobject(k)));
}

LEAN_EXPORT lean_obj_res lean_py_setitem(b_lean_obj_arg p, b_lean_obj_arg k, b_lean_obj_arg v, lean_obj_arg world) {
    (void)world; ENSURE_INIT();
    int r = p_PyObject_SetItem(unwrap_pyobject(p), unwrap_pyobject(k), unwrap_pyobject(v));
    if (r != 0) return raise_py_error();
    return lean_io_result_mk_ok(lean_box(0));
}

LEAN_EXPORT lean_obj_res lean_py_length(b_lean_obj_arg p, lean_obj_arg world) {
    (void)world; ENSURE_INIT();
    Py_ssize_t r = p_PyObject_Length(unwrap_pyobject(p));
    if (r < 0) return raise_py_error();
    return lean_io_result_mk_ok(lean_int64_to_int((int64_t) r));
}

LEAN_EXPORT lean_obj_res lean_py_eq(b_lean_obj_arg a, b_lean_obj_arg b, lean_obj_arg world) {
    (void)world; ENSURE_INIT();
    int r = p_PyObject_RichCompareBool(unwrap_pyobject(a), unwrap_pyobject(b), Py_EQ);
    if (r < 0) return raise_py_error();
    return lean_io_result_mk_ok(lean_box(r ? 1 : 0));
}

LEAN_EXPORT lean_obj_res lean_py_is(b_lean_obj_arg a, b_lean_obj_arg b, lean_obj_arg world) {
    (void)world; ENSURE_INIT();
    return lean_io_result_mk_ok(lean_box(unwrap_pyobject(a) == unwrap_pyobject(b) ? 1 : 0));
}

/* ------------------------------------------------------------------ */
/*  Calling                                                            */
/* ------------------------------------------------------------------ */

LEAN_EXPORT lean_obj_res lean_py_call(b_lean_obj_arg f, b_lean_obj_arg args, lean_obj_arg world) {
    (void)world; ENSURE_INIT();
    size_t n = lean_array_size(args);
    PyObject *tup = p_PyTuple_New((Py_ssize_t)n);
    if (!tup) return raise_py_error();
    for (size_t i = 0; i < n; i++) {
        PyObject *po = unwrap_pyobject(lean_array_get_core(args, i));
        p_Py_IncRef(po);
        p_PyTuple_SetItem(tup, (Py_ssize_t)i, po);
    }
    PyObject *r = p_PyObject_CallObject(unwrap_pyobject(f), tup);
    p_Py_DecRef(tup);
    return ok_owned_or_err(r);
}

LEAN_EXPORT lean_obj_res lean_py_call_kw(b_lean_obj_arg f, b_lean_obj_arg args, b_lean_obj_arg kwargs, lean_obj_arg world) {
    (void)world; ENSURE_INIT();
    size_t n = lean_array_size(args);
    PyObject *tup = p_PyTuple_New((Py_ssize_t)n);
    if (!tup) return raise_py_error();
    for (size_t i = 0; i < n; i++) {
        PyObject *po = unwrap_pyobject(lean_array_get_core(args, i));
        p_Py_IncRef(po);
        p_PyTuple_SetItem(tup, (Py_ssize_t)i, po);
    }
    size_t kn = lean_array_size(kwargs);
    PyObject *d = p_PyDict_New();
    if (!d) { p_Py_DecRef(tup); return raise_py_error(); }
    for (size_t i = 0; i < kn; i++) {
        lean_object *kv = lean_array_get_core(kwargs, i);
        lean_object *key = lean_ctor_get(kv, 0);
        lean_object *val = lean_ctor_get(kv, 1);
        if (p_PyDict_SetItemString(d, lean_string_cstr(key), unwrap_pyobject(val)) != 0) {
            p_Py_DecRef(d); p_Py_DecRef(tup);
            return raise_py_error();
        }
    }
    PyObject *r = p_PyObject_Call(unwrap_pyobject(f), tup, d);
    p_Py_DecRef(tup);
    p_Py_DecRef(d);
    return ok_owned_or_err(r);
}

/* ------------------------------------------------------------------ */
/*  Modules and globals                                                */
/* ------------------------------------------------------------------ */

LEAN_EXPORT lean_obj_res lean_py_import(b_lean_obj_arg name, lean_obj_arg world) {
    (void)world; ENSURE_INIT();
    return ok_owned_or_err(p_PyImport_ImportModule(lean_string_cstr(name)));
}

static PyObject *get_main_globals(void) {
    PyObject *m = p_PyImport_AddModule("__main__"); /* borrowed */
    if (!m) return NULL;
    return p_PyModule_GetDict(m);                   /* borrowed */
}

LEAN_EXPORT lean_obj_res lean_py_eval(b_lean_obj_arg src, lean_obj_arg world) {
    (void)world; ENSURE_INIT();
    PyObject *g = get_main_globals();
    if (!g) return raise_py_error();
    PyObject *r = p_PyRun_StringFlags(lean_string_cstr(src), Py_eval_input, g, g, NULL);
    return ok_owned_or_err(r);
}

LEAN_EXPORT lean_obj_res lean_py_exec(b_lean_obj_arg src, lean_obj_arg world) {
    (void)world; ENSURE_INIT();
    PyObject *g = get_main_globals();
    if (!g) return raise_py_error();
    PyObject *r = p_PyRun_StringFlags(lean_string_cstr(src), Py_file_input, g, g, NULL);
    if (!r) return raise_py_error();
    p_Py_DecRef(r);
    return lean_io_result_mk_ok(lean_box(0));
}

/* ------------------------------------------------------------------ */
/*  Numeric ops                                                        */
/* ------------------------------------------------------------------ */

#define BINOP(name, fn)                                                 \
LEAN_EXPORT lean_obj_res name(b_lean_obj_arg a, b_lean_obj_arg b, lean_obj_arg world) { \
    (void)world; ENSURE_INIT();                                         \
    return ok_owned_or_err(fn(unwrap_pyobject(a), unwrap_pyobject(b))); \
}

BINOP(lean_py_add, p_PyNumber_Add)
BINOP(lean_py_sub, p_PyNumber_Subtract)
BINOP(lean_py_mul, p_PyNumber_Multiply)
BINOP(lean_py_div, p_PyNumber_TrueDivide)

LEAN_EXPORT lean_obj_res lean_py_pow(b_lean_obj_arg a, b_lean_obj_arg b, lean_obj_arg world) {
    (void)world; ENSURE_INIT();
    p_Py_IncRef(p_Py_None);
    return ok_owned_or_err(p_PyNumber_Power(unwrap_pyobject(a), unwrap_pyobject(b), p_Py_None));
}

LEAN_EXPORT lean_obj_res lean_py_neg(b_lean_obj_arg a, lean_obj_arg world) {
    (void)world; ENSURE_INIT();
    return ok_owned_or_err(p_PyNumber_Negative(unwrap_pyobject(a)));
}

/* ------------------------------------------------------------------ */
/*  Lean closures as Python callables                                   */
/*                                                                    */
/*  The full implementation builds a Python heap type whose tp_call    */
/*  trampolines into a stored Lean closure. Until that's wired (see   */
/*  Phase 3c of the plan), these stubs return a clear runtime error.   */
/* ------------------------------------------------------------------ */

LEAN_EXPORT lean_obj_res leanpy_make_callable(lean_obj_arg closure, lean_obj_arg world) {
    (void)world;
    lean_dec(closure);
    return raise_io_error(
        "LeanPy.Python.Py.fromLeanCallable: not yet implemented "
        "(see plan phase 3c)");
}

LEAN_EXPORT lean_obj_res leanpy_make_callable_kw(lean_obj_arg closure, lean_obj_arg world) {
    (void)world;
    lean_dec(closure);
    return raise_io_error(
        "LeanPy.Python.Py.fromLeanCallableKw: not yet implemented "
        "(see plan phase 3c)");
}
