"""Generate portable, validated SSR instructions from Teloce's canonical AST."""

from __future__ import annotations


from teloce.ast.nodes import (
    ElementNode,
    TextNode,
    InterpolationNode,
    ForNode,
    IfNode,
    ComponentNode,
    SlotNode,
)
from teloce.server.expressions import compile_expression
from teloce.sfc.parser import SFCParser
from teloce.css.hashing import HashGenerator

VERSION = 1


class SSRCompileError(ValueError):
    def __init__(self, message, *, filename, line=1, column=1):
        self.diagnostic = {
            "category": "compile",
            "code": "SSR_UNSUPPORTED",
            "message": message,
            "component": filename,
            "line": line,
            "column": column,
        }
        super().__init__(f"{filename}:{line}:{column}: {message}")


def compile_program(source, filename="<input>", *, components=None):
    parser = SFCParser({"html_mode": True})
    component = parser.parse(source, filename)
    if component is None:
        raise SSRCompileError("; ".join(parser.errors), filename=filename)
    offset = parser._last_sections.template_line - 1
    imports = components or {}
    scope = (
        HashGenerator().generate_scope_id(component.name)
        if component.style.scoped
        else None
    )

    def column(node):
        return (node.column or 1) + (
            parser._last_sections.template_column - 1 if (node.line or 1) == 1 else 0
        )

    def expression(value, node):
        try:
            return compile_expression(value)
        except ValueError as error:
            raise SSRCompileError(
                str(error),
                filename=filename,
                line=(node.line or 1) + offset,
                column=column(node),
            ) from error

    def encode(node):
        location = {"line": (node.line or 1) + offset, "column": column(node)}
        record = {"location": location}
        children = lambda nodes: [encode(item) for item in nodes]
        if isinstance(node, TextNode):
            return {**record, "op": "text", "value": node.value}
        if isinstance(node, InterpolationNode):
            return {
                **record,
                "op": "expression",
                "value": expression(node.expression, node),
            }
        if isinstance(node, IfNode):
            return {
                **record,
                "op": "if",
                "value": expression(node.condition, node),
                "children": children(node.children),
                "else": children(node.else_children),
            }
        if isinstance(node, ForNode):
            if node.virtual:
                raise SSRCompileError(
                    "Virtual lists are browser-only", filename=filename, **location
                )
            rows = children(node.children)
            key_source = (
                node.key
                if not node.key
                or not node.key.isidentifier()
                or node.key == node.item
                or node.key in {"index", getattr(node, "index", "index")}
                else f"{node.item}.{node.key}"
            )
            key = expression(key_source, node) if key_source and node.key != "index" else None
            if key and rows and rows[0]["op"] == "element":
                rows[0]["bindings"]["data-teloce-key"] = key
            return {
                **record,
                "op": "for",
                "item": node.item,
                "index": getattr(node, "index", "index"),
                "value": expression(node.collection, node),
                "key": key,
                "children": rows,
            }
        if isinstance(node, SlotNode):
            return {
                **record,
                "op": "slot",
                "name": node.name,
                "children": children(node.children),
            }
        if isinstance(node, (ComponentNode, ElementNode)):
            tag = node.name if isinstance(node, ComponentNode) else node.tag
            attributes = dict(
                node.props if isinstance(node, ComponentNode) else node.attributes
            )
            if tag == "slot":
                return {
                    **record,
                    "op": "slot",
                    "name": attributes.get("name", "default"),
                    "children": children(node.children),
                }
            if tag == "component":
                raise SSRCompileError(
                    "Dynamic components are not supported in SSR",
                    filename=filename,
                    **location,
                )
            bindings = {
                binding.name: expression(binding.value, binding)
                for binding in getattr(node, "bindings", [])
            }
            for name, value in list(attributes.items()):
                if name.startswith(":"):
                    bindings[name[1:]] = expression(value, node)
                    del attributes[name]
                elif name.startswith("@") or name.startswith("v-on:"):
                    del attributes[name]
                elif name.startswith("v-") or name.startswith("use:"):
                    raise SSRCompileError(
                        f"Unsupported SSR directive: {name}",
                        filename=filename,
                        **location,
                    )
            if any(
                name in {"html", "model", "bind", "is"} or name.startswith("on")
                for name in bindings
            ):
                raise SSRCompileError(
                    "Raw HTML, model directives, spreads and dynamic components are not supported in SSR",
                    filename=filename,
                    **location,
                )
            if tag in imports:
                return {
                    **record,
                    "op": "component",
                    "tag": tag,
                    "entry": imports[tag],
                    "attributes": attributes,
                    "bindings": bindings,
                    "children": children(node.children),
                }
            if isinstance(node, ComponentNode) or tag[:1].isupper():
                raise SSRCompileError(
                    f"Component {tag} needs a manifest import",
                    filename=filename,
                    **location,
                )
            if tag.lower() in {"script", "iframe", "object", "embed"}:
                raise SSRCompileError(
                    f"Unsafe SSR element: {tag}", filename=filename, **location
                )
            if scope:
                attributes[scope] = ""
            return {
                **record,
                "op": "element",
                "tag": tag,
                "attributes": attributes,
                "bindings": bindings,
                "children": children(node.children),
            }
        raise SSRCompileError(
            f"Unsupported SSR node: {type(node).__name__}",
            filename=filename,
            **location,
        )

    return {
        "version": VERSION,
        "component": filename,
        "nodes": [encode(node) for node in component.template],
        "imports": imports,
    }
