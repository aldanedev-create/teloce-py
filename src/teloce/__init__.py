"""
Teloce-Py - A Python compiler for Teloce .vel Single File Components

Teloce-Py transforms .vel files into self-contained vanilla JavaScript
without requiring Node.js, npm, or a CDN.
"""

from teloce.version import __version__

__all__ = [
    "__version__",
    "compile",
    "compile_file",
    "compile_project",
]

from teloce.compiler.compiler import compile, compile_file, compile_project
from teloce.ssr import render_ssr, render_static_component, render_static, to_jinax_template
from teloce.data import DataShapeError, frontend_json, to_frontend_data

__all__ = [
    "__version__",
    "compile",
    "compile_file",
    "compile_project",
    "render_ssr",
    "to_jinax_template",
    "render_static_component",
    "render_static",
    "DataShapeError",
    "to_frontend_data",
    "frontend_json",
]
