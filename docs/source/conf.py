# Configuration file for the Sphinx documentation builder.

import os
import sys

sys.path.insert(0, os.path.abspath("../../"))

# -- Project information -----------------------------------------------------

project = "lean-py"
copyright = "2025, Kiran Gopinathan"
author = "Kiran Gopinathan"

# -- General configuration ---------------------------------------------------

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
    "sphinx.ext.napoleon",
    "sphinx_autodoc_typehints",
]

typehints_use_signature = True
typehints_use_signature_return = True
autodoc_inherit_docstrings = True
autodoc_member_order = "bysource"

master_doc = "index"
templates_path = ["_templates"]
exclude_patterns: list[str] = []

# -- Options for HTML output -------------------------------------------------

html_theme = "sphinx_rtd_theme"

html_static_path = ["_static"]
html_style = "css/custom.css"

html_theme_options = {
    "navigation_depth": 3,
    "collapse_navigation": False,
}

# -- Intersphinx configuration -----------------------------------------------

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

# -- Doctest configuration ---------------------------------------------------

doctest_global_setup = ""
