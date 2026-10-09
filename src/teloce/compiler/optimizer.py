"""
Optimizer for the AST.

Applies optimization passes to the AST for better performance.
"""

from typing import List, Optional, Any, Set
import re

from teloce.ast.nodes import (
    ASTNode, ElementNode, TextNode, InterpolationNode, ForNode, IfNode,
    ComponentNode, SlotNode, FragmentNode,
)


class Optimizer:
    """
    Optimizes the AST for better performance.
    """
    
    def __init__(self, options: Optional[dict] = None):
        self.options = options or {}
        self.static_nodes: Set[int] = set()
        self.direct_plan = {
            "version": 1,
            "enabled": bool(self.options.get("direct_dom_updates", False)),
            "structural": False,
            "fallback": False,
            "refreshIntegrations": False,
            "bindings": [],
            "blocks": [],
            "components": [],
            "events": [],
            "static_nodes": [],
            "unsupported": [],
        }
    
    def optimize(self, nodes: List[ASTNode], computed: Optional[dict] = None) -> List[ASTNode]:
        """Optimize the AST."""
        # First pass: mark static nodes
        self._mark_static_nodes(nodes)

        # Keep the analysis separate from code generation. The generator uses
        # these records to emit stable DOM markers, while the runtime uses the
        # dependency roots to skip unrelated updates.
        if self.direct_plan["enabled"]:
            self._collect_direct_plan(nodes)
            self._add_computed_dependencies(computed or {})
            self.direct_plan["static_nodes"] = self._static_node_records(nodes)
        
        # Second pass: optimize
        return self._optimize_nodes(nodes)

    _IDENTIFIER_RE = re.compile(r"(?<![.$\w])([A-Za-z_$][\w$]*)")
    _NON_STATE_NAMES = {
        "true", "false", "null", "undefined", "this", "Math", "Number",
        "String", "Boolean", "Array", "Object", "JSON", "Date", "parseInt",
        "parseFloat", "isNaN", "Infinity", "NaN", "event", "$event",
        "return", "typeof", "instanceof", "in", "of", "let", "const",
        "var", "if", "else", "switch", "case", "default", "this",
    }

    _UNSUPPORTED_DIRECT_RE = re.compile(
        r"(?:=>|\b(?:await|yield|new|function|class)\b|`|;|\.\.\.)"
    )

    @classmethod
    def _direct_expression_supported(cls, expression: str) -> bool:
        """Return whether the shared safe evaluator can handle an expression.

        This is deliberately conservative. A false positive only uses the
        compatibility renderer for one component; a false negative could make
        a direct binding stale. The full authored JavaScript still goes
        through the JavaScript parser used by the script compiler.
        """
        return not cls._UNSUPPORTED_DIRECT_RE.search(str(expression or ""))

    @classmethod
    def _dependencies(cls, expression: str) -> list[str]:
        """Return conservative root dependencies for a template expression.

        This is intentionally conservative: a false positive causes one extra
        binding to update, while a false negative could leave stale DOM. The
        JavaScript parser validates the authored script; this pass only builds
        a safe dependency index for template expressions.
        """
        raw_source = str(expression or "")
        source = raw_source
        # Identifiers inside string literals are values, not state reads. Keep
        # the character positions stable so diagnostics still use the same
        # source offsets when this analysis is extended.
        source = re.sub(
            r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"",
            lambda match: " " * len(match.group(0)),
            source,
        )
        names: list[str] = []
        # The normal identifier expression intentionally ignores member names
        # after a dot. Handle the component state form separately so
        # `this.firstName` contributes the root `firstName` dependency.
        for pattern, search_source in (
            (r"\bthis\.([A-Za-z_$][\w$]*)", source),
            (r"\bthis\?\.([A-Za-z_$][\w$]*)", source),
            (r"\bthis\s*\[\s*['\"]([A-Za-z_$][\w$]*)['\"]\s*\]", raw_source),
        ):
            for match in re.finditer(pattern, search_source):
                name = match.group(1)
                if name not in names:
                    names.append(name)
        for match in cls._IDENTIFIER_RE.finditer(source):
            name = match.group(1)
            if name in cls._NON_STATE_NAMES or name in names:
                continue
            before = source[:match.start()].rstrip()
            if before.endswith("?"):
                continue
            if before.endswith("."):
                # `this.user.name` is a state read rooted at `user`; ordinary
                # member names such as `name` are not separate dependencies.
                if before[:-1].rstrip().endswith("this"):
                    names.append(name)
                continue
            # Object-literal keys and arrow parameters are not state reads.
            after = source[match.end():].lstrip()
            if after.startswith(":") and not before.endswith("?"):
                continue
            if before.endswith("=>"):
                continue
            names.append(name)
        return names

    def _collect_direct_plan(self, nodes: List[ASTNode]) -> None:
        """Collect direct-update metadata in the same order as generation."""
        counters = {"text": 0, "binding": 0}

        def add(kind: str, expression: str, node: ASTNode, name: str = "") -> None:
            index = counters[kind]
            counters[kind] += 1
            record = {
                "id": f"{kind[0]}{index}",
                "kind": kind,
                "name": name,
                "expression": str(expression or ""),
                "dependencies": self._dependencies(expression),
                "line": getattr(node, "line", None),
                "column": getattr(node, "column", None),
                "safe": self._direct_expression_supported(expression),
            }
            if "(" in record["expression"] or "|" in record["expression"]:
                record["dependencies"].append("*")
            self.direct_plan["bindings"].append(record)
            if not record["safe"]:
                self.direct_plan["fallback"] = True
                self.direct_plan["unsupported"].append(record.copy())

        def visit(node: ASTNode) -> None:
            if isinstance(node, InterpolationNode):
                add("text", node.expression, node)
                return
            if isinstance(node, ElementNode):
                if any(
                    name.startswith("use:")
                    or name in {"poll", "live", "v-scrolly", "v-chart-annotation", "v-data-table"}
                    for name in node.attributes
                ):
                    self.direct_plan["refreshIntegrations"] = True
                for binding in node.bindings:
                    # `$attrs` is applied as a forwarded object and cannot be
                    # reduced to one DOM property. It remains on the normal
                    # compatibility/directive path.
                    if binding.name != "attrs":
                        add("binding", binding.value, binding, binding.name)
                for event in node.events:
                    self.direct_plan["events"].append({
                        "name": event.name,
                        "expression": str(event.handler or ""),
                        "line": getattr(event, "line", None),
                        "column": getattr(event, "column", None),
                    })
                for child in node.children:
                    visit(child)
                return
            if isinstance(node, (ForNode, IfNode, ComponentNode, SlotNode, FragmentNode)):
                if isinstance(node, ForNode):
                    self.direct_plan["structural"] = True
                    self.direct_plan["blocks"].append({
                        "kind": "KeyedLoop" if node.key else "Loop",
                        "item": node.item,
                        "collection": node.collection,
                        "key": node.key or "index",
                        "line": getattr(node, "line", None),
                        "column": getattr(node, "column", None),
                    })
                elif isinstance(node, IfNode):
                    self.direct_plan["structural"] = True
                    self.direct_plan["blocks"].append({
                        "kind": "IfBlock",
                        "expression": node.condition,
                        "line": getattr(node, "line", None),
                        "column": getattr(node, "column", None),
                    })
                elif isinstance(node, ComponentNode):
                    self.direct_plan["components"].append({
                        "name": node.name,
                        "props": dict(node.props or {}),
                        "line": getattr(node, "line", None),
                        "column": getattr(node, "column", None),
                    })
                for child in getattr(node, "children", []) or []:
                    visit(child)
                if isinstance(node, IfNode):
                    for child in node.else_children:
                        visit(child)

        for node in nodes:
            visit(node)

    def _add_computed_dependencies(self, computed: dict) -> None:
        """Expand template dependencies through computed properties.

        A binding such as ``{{ displayName }}`` depends on the fields read by
        ``displayName()`` even though the template itself only contains the
        computed name. The runtime does not execute a dependency tracker for
        arbitrary getters, so carrying these roots in the compiler plan is the
        safe invalidation strategy.
        """
        if not computed:
            return
        computed_roots = {
            str(name): self._dependencies(str(body or ""))
            for name, body in computed.items()
        }
        for record in self.direct_plan["bindings"]:
            expanded = list(record.get("dependencies") or [])
            pending = list(expanded)
            while pending:
                dependency = pending.pop()
                for root in computed_roots.get(dependency, []):
                    if root not in expanded:
                        expanded.append(root)
                        pending.append(root)
            record["dependencies"] = expanded

    def _static_node_records(self, nodes: List[ASTNode]) -> list[dict]:
        """Serialize deterministic static-node metadata for tooling.

        Python object ids are useful inside an optimization pass but are not a
        stable IR and should never leak into generated manifests or reports.
        """
        records: list[dict] = []

        def visit(node: ASTNode) -> None:
            if id(node) in self.static_nodes:
                records.append({
                    "kind": getattr(node.type, "name", "node").lower(),
                    "tag": getattr(node, "tag", None),
                    "line": getattr(node, "line", None),
                    "column": getattr(node, "column", None),
                })
            for child in getattr(node, "children", []) or []:
                visit(child)
            if isinstance(node, IfNode):
                for child in node.else_children:
                    visit(child)

        for node in nodes:
            visit(node)
        return records
    
    def _mark_static_nodes(self, nodes: List[ASTNode]):
        """Mark static nodes that don't need reactivity."""
        for node in nodes:
            self._mark_static_node(node)
    
    def _mark_static_node(self, node: ASTNode):
        """Mark a single node as static or dynamic."""
        if isinstance(node, InterpolationNode):
            # Interpolations are dynamic
            return
        
        if isinstance(node, ElementNode):
            # Check for dynamic attributes
            has_dynamic = False
            
            # Events are dynamic
            if node.events:
                has_dynamic = True
            
            # Bindings are dynamic
            if node.bindings:
                has_dynamic = True
            
            # A parent is dynamic when any descendant is dynamic.
            child_static = all(self._mark_static_node(child) for child in node.children)
            if not has_dynamic and child_static:
                # If no dynamic content, it's static
                self.static_nodes.add(id(node))
                return True
            return False
        if isinstance(node, (ForNode, IfNode, ComponentNode, SlotNode, FragmentNode)):
            children = list(getattr(node, 'children', []))
            if isinstance(node, IfNode):
                children += node.else_children
            return all(self._mark_static_node(child) for child in children)
        return True
    
    def _optimize_nodes(self, nodes: List[ASTNode]) -> List[ASTNode]:
        """Optimize a list of nodes."""
        result = []
        for node in nodes:
            optimized = self._optimize_node(node)
            if optimized:
                if isinstance(optimized, TextNode) and result and isinstance(result[-1], TextNode):
                    result[-1] = TextNode(
                        result[-1].value + optimized.value,
                        result[-1].line,
                        result[-1].column,
                    )
                else:
                    result.append(optimized)
        return result
    
    def _optimize_node(self, node: ASTNode) -> Optional[ASTNode]:
        """Optimize a single node."""
        if isinstance(node, ElementNode):
            return self._optimize_element(node)
        if isinstance(node, ForNode):
            node.children = self._optimize_nodes(node.children)
        elif isinstance(node, IfNode):
            node.children = self._optimize_nodes(node.children)
            node.else_children = self._optimize_nodes(node.else_children)
        elif isinstance(node, (ComponentNode, SlotNode, FragmentNode)):
            node.children = self._optimize_nodes(node.children)
        return node
    
    def _optimize_element(self, node: ElementNode) -> ElementNode:
        """Optimize an element node."""
        # Optimize children
        optimized_children = []
        for child in node.children:
            optimized = self._optimize_node(child)
            if optimized:
                optimized_children.append(optimized)
        
        element = ElementNode(
            node.tag,
            node.attributes,
            node.events,
            node.bindings,
            optimized_children,
            node.line,
            node.column
        )
        element.transitions = node.transitions
        return element
