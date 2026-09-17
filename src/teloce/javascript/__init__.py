"""
JavaScript Generator package.

Generates JavaScript code from AST nodes.
"""

from teloce.javascript.dom import DOMGenerator
from teloce.javascript.exports import ExportGenerator
from teloce.javascript.generator import JavaScriptGenerator
from teloce.javascript.helpers import HelperGenerator
from teloce.javascript.imports import ImportGenerator
from teloce.javascript.module import ModuleGenerator
from teloce.javascript.parser import (
    JavaScriptLanguageParser,
    JavaScriptLexer,
    JavaScriptParser,
    JavaScriptSyntaxError,
    JSNode,
    JSProgram,
    JSToken,
    parse_javascript,
    parse_javascript_language,
    tokenize_javascript,
)
from teloce.javascript.tree_sitter_backend import (
    TREE_SITTER_AVAILABLE,
    TreeSitterProgram,
    TreeSitterUnavailable,
    default_export_object_source,
    parse_tree,
    parse_valid_tree,
)
from teloce.javascript.tree_sitter_backend import (
    is_available as tree_sitter_available,
)

__all__ = [
    "JavaScriptGenerator",
    "ModuleGenerator",
    "ImportGenerator",
    "ExportGenerator",
    "DOMGenerator",
    "HelperGenerator",
    "JSToken",
    "JSNode",
    "JSProgram",
    "JavaScriptLexer",
    "JavaScriptParser",
    "JavaScriptSyntaxError",
    "JavaScriptLanguageParser",
    "parse_javascript",
    "parse_javascript_language",
    "tokenize_javascript",
    "TREE_SITTER_AVAILABLE",
    "TreeSitterProgram",
    "TreeSitterUnavailable",
    "default_export_object_source",
    "tree_sitter_available",
    "parse_tree",
    "parse_valid_tree",
]
