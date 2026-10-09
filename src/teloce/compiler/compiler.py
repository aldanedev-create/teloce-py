"""
Main compiler orchestrator.

This module coordinates the entire compilation pipeline:
1. Lexical analysis (Lexer)
2. Parsing (Parser)
3. Transformation (Transformer)
4. Optimization (Optimizer)
5. JavaScript generation (Generator)
"""

from pathlib import Path
from typing import Optional, Dict, Any
import re
import inspect

from teloce.compiler.transformer import Transformer
from teloce.compiler.optimizer import Optimizer
from teloce.compiler.generator import Generator
from teloce.compiler.diagnostics import Diagnostics, DiagnosticLevel
from teloce.compiler.source_map import SourceMapGenerator
from teloce.sfc.parser import SFCParser
from teloce.sfc.component import Component


class Compiler:
    """
    Main compiler class that orchestrates the compilation pipeline.
    """

    def __init__(self, options: Optional[Dict[str, Any]] = None):
        self.options = options or {}
        self.plugin_registry = self.options.get("plugin_registry")
        self.diagnostics = Diagnostics()

        # Accept both spellings used by the CLI and public API.
        self.source_map_enabled = self.options.get(
            "source_map",
            self.options.get("source_maps", True),
        )
        self.minify = self.options.get("minify", False)
        self.dev = self.options.get("dev", True)

    def compile(self, source: str, filename: str = "<input>") -> Dict[str, Any]:
        """Compile source and convert unexpected compiler failures to diagnostics.

        A malformed component must never bring down a dev server or a batch
        build.  Expected syntax errors are already reported by the individual
        pipeline stages; this boundary also protects callers from an internal
        parser/generator exception and returns the same stable result shape.
        """
        try:
            return self._compile(source, filename)
        except Exception as exc:  # pragma: no cover - exercised by integration smoke tests
            self.diagnostics = Diagnostics()
            self.diagnostics.add(
                DiagnosticLevel.ERROR,
                f"Compilation failed: {exc}",
                filename=filename,
                line=getattr(exc, "lineno", None),
                column=getattr(exc, "offset", None),
                code="E1000",
            )
            return self._empty_result()

    _CDN_IMPORT_RE = re.compile(
        r"""import\s*(?:[\w${},\s*]+\s+from\s+)?['"](https?://[^'"]+)['"]"""
        r"""|import\(\s*['"](https?://[^'"]+)['"]\s*\)"""
    )
    _KNOWN_CDN_HOSTS = (
        "cdn.jsdelivr.net", "unpkg.com", "cdnjs.cloudflare.com",
        "esm.sh", "esm.run", "cdn.skypack.dev", "jspm.dev",
    )

    def _check_cdn_imports(self, source: str, filename: str) -> None:
        """Warn on module imports fetched from a remote URL that are either
        unencrypted (http://, interceptable via MITM injection) or, for
        known CDN hosts, missing an explicit version pin (an unpinned URL
        silently changes behavior whenever the package publishes an
        update). This is a warning, not an error -- CDN imports themselves
        are a legitimate, documented pattern in this compiler (see the
        Three.js lesson), the goal is just to flag the two ways they
        commonly go wrong."""
        script_match = re.search(r"<script[^>]*>(.*?)</script>", source, re.DOTALL)
        script_text = script_match.group(1) if script_match else source
        script_offset = script_match.start(1) if script_match else 0

        for match in self._CDN_IMPORT_RE.finditer(script_text):
            url = match.group(1) or match.group(2)
            line = source.count("\n", 0, script_offset + match.start()) + 1

            if url.startswith("http://"):
                self.diagnostics.add(
                    DiagnosticLevel.WARNING,
                    f"Module imported over an insecure http:// URL: {url}. "
                    "An attacker on the network path could inject arbitrary "
                    "JavaScript into this response. Use https:// instead.",
                    filename=filename,
                    line=line,
                    code="W1010",
                    suggestions=[f"Change to https://{url[len('http://'):]}"],
                )

            host_match = re.match(r"https?://([^/]+)/", url)
            host = host_match.group(1) if host_match else ""
            if host in self._KNOWN_CDN_HOSTS and not re.search(r"@\d", url):
                self.diagnostics.add(
                    DiagnosticLevel.WARNING,
                    f"CDN import has no pinned version: {url}. An unpinned "
                    "URL can silently change behavior when the package "
                    "publishes a new release. Pin an exact version, e.g. "
                    "package@1.2.3.",
                    filename=filename,
                    line=line,
                    code="W1011",
                )

    def _compile(self, source: str, filename: str = "<input>") -> Dict[str, Any]:
        """
        Compile a .vel file from source string.
        
        Args:
            source: The .vel file content
            filename: The source filename (for error reporting)
            
        Returns:
            Dict containing:
                - code: Generated JavaScript
                - css: Extracted CSS
                - map: Source map (if enabled)
                - diagnostics: Compilation messages
                - ast: Abstract Syntax Tree
        """
        self.diagnostics = Diagnostics()
        source = self._run_preprocessors(source, filename)
        if source is None:
            return self._empty_result()
        source = self._run_plugin_hooks("before_compile", source)

        # Step 1: Parse SFC
        parser_options = dict(self.options)
        if "source_extensions" not in parser_options and Path(filename).suffix.lower() == ".html":
            parser_options["html_mode"] = True
        sfc_parser = SFCParser(parser_options)
        component = sfc_parser.parse(source, filename)
        if component:
            self._check_cdn_imports(source, filename)

        for warning in sfc_parser.warnings:
            line, column = self._message_location(warning)
            self.diagnostics.add(
                DiagnosticLevel.WARNING,
                warning,
                filename=filename,
                line=line,
                column=column,
                code="W1001",
            )
        
        if not component:
            for error in sfc_parser.errors:
                line, column = self._message_location(error)
                suggestions = []
                if "Unclosed delimiter" in error:
                    suggestions.append("Close the reported JavaScript delimiter before compiling again.")
                elif "Missing <template>" in error:
                    suggestions.append("Add one <template>...</template> block to the component.")
                elif "Only one <" in error:
                    suggestions.append("Keep one block of this type and merge or remove the duplicate.")
                self.diagnostics.add(
                    DiagnosticLevel.ERROR,
                    error,
                    filename=filename,
                    line=line,
                    column=column,
                    code="E1001",
                    suggestions=suggestions,
                )
            if not sfc_parser.errors:
                self.diagnostics.add(
                    DiagnosticLevel.ERROR,
                    "Failed to parse SFC",
                    filename=filename,
                    code="E1001",
                )
            return self._empty_result()

        # SFCParser already lexes and parses the template. Keeping one
        # canonical template AST avoids parsing the AST as if it were text.
        ast = component.template

        self._validate_runtime_features(ast, filename)

        ast = self._run_plugin_hooks("before_transform", ast)

        # Step 2: Transformation
        transformer = Transformer()
        transformed_ast = transformer.transform(ast)
        
        if transformer.has_errors:
            for error in transformer.errors:
                self.diagnostics.add(
                    DiagnosticLevel.ERROR,
                    error,
                    filename=filename
                )
            return self._empty_result()

        # Step 3: Optimization
        optimizer = Optimizer(self.options)
        optimized_ast = optimizer.optimize(transformed_ast, computed=component.script_computed)
        for record in optimizer.direct_plan.get("unsupported", []):
            strict_direct = bool(self.options.get("strict_dependency_analysis", False))
            self.diagnostics.add(
                DiagnosticLevel.ERROR if strict_direct else DiagnosticLevel.WARNING,
                "Expression cannot be analyzed safely for direct DOM updates; the compatibility renderer will be used for this component: "
                + str(record.get("expression", "")),
                filename=filename,
                line=record.get("line"),
                column=record.get("column"),
                code="E3001" if strict_direct else "W3001",
                suggestions=[
                    "Move complex logic into a computed value or method, or disable direct_dom_updates for this component."
                ],
            )
        if optimizer.direct_plan.get("enabled") and optimizer.direct_plan.get("structural"):
            self.diagnostics.add(
                DiagnosticLevel.INFO,
                "Structural blocks use keyed reconciliation inside targeted regions when supported; other layouts use compatibility rendering.",
                filename=filename,
                code="I3001",
                suggestions=[
                    "Keep a stable :key on v-for items to preserve row identity during updates."
                ],
            )

        # Step 4: Code generation
        generator_options = dict(self.options)
        if "source_extensions" not in generator_options and Path(filename).suffix.lower() == ".html":
            generator_options["html_mode"] = True
        filter_registry = generator_options.get("filter_registry")
        if filter_registry and hasattr(filter_registry, "get_js_filters"):
            generator_options["filter_js"] = filter_registry.get_js_filters()
        if self.plugin_registry and hasattr(self.plugin_registry, "get_api"):
            plugin_api = self.plugin_registry.get_api()
            if plugin_api and hasattr(plugin_api, "get_js_filters"):
                generator_options["filter_js"] = {
                    **generator_options.get("filter_js", {}),
                    **plugin_api.get_js_filters(),
                }
        generator_options["direct_plan"] = optimizer.direct_plan
        generator = Generator(generator_options)
        js_code = generator.generate(optimized_ast, component)
        optimizer.direct_plan.update({key: generator._direct_plan.get(key) for key in ("version", "fallback", "regions", "targetedStructural")})
        js_code = self._run_plugin_hooks("after_compile", js_code)
        css_code = self._generate_css(component)

        # Step 5: Source map generation
        source_map = None
        if self.source_map_enabled:
            source_map_generator = SourceMapGenerator()
            line_hints = {}
            for record in optimizer.direct_plan.get("bindings", []):
                marker = f"teloce-text:{record.get('id')}"
                if marker not in js_code:
                    marker = f"data-teloce-direct-bindings=\\\"{record.get('id')}"
                generated_line = next(
                    (index for index, line in enumerate(js_code.splitlines()) if marker in line),
                    None,
                )
                if generated_line is not None and record.get("line"):
                    line_hints[generated_line] = (
                        max(0, int(record["line"]) - 1),
                        max(0, int(record.get("column") or 1) - 1),
                    )
            source_map = source_map_generator.generate(js_code, filename, source, line_hints=line_hints)
            source_map.setdefault("x_teloce", {})["direct_plan"] = {
                "version": optimizer.direct_plan.get("version", 1),
                "bindings": [
                    {
                        "id": record.get("id"),
                        "expression": record.get("expression"),
                        "source": {
                            "line": record.get("line"),
                            "column": record.get("column"),
                        },
                    }
                    for record in optimizer.direct_plan.get("bindings", [])
                ],
            }

        return {
            "code": js_code,
            "css": css_code,
            "map": source_map,
            "diagnostics": self.diagnostics.to_dict(),
            "ast": optimized_ast,
            "component": component,
            "direct_plan": optimizer.direct_plan,
            "success": not self.diagnostics.has_errors(),
        }

    def _validate_runtime_features(self, nodes: list[Any], filename: str) -> None:
        """Emit actionable warnings for opt-in runtime features."""
        from teloce.ast.nodes import ForNode, IfNode, ElementNode

        def visit(node: Any) -> None:
            if isinstance(node, ForNode) and node.virtual and not node.key:
                self.diagnostics.add(
                    DiagnosticLevel.WARNING,
                    "virtual-for works best with a stable :key; index identity can lose focus and input state when rows change.",
                    filename=filename,
                    line=node.line,
                    column=node.column,
                    code="W2001",
                    suggestions=["Add :key=\"item.id\" (or another stable unique key) to the virtual loop."],
                )
            if isinstance(node, ForNode) and not node.key:
                self.diagnostics.add(
                    DiagnosticLevel.WARNING,
                    "v-for has no stable key; item identity, input focus, and component state may be lost when the collection changes.",
                    filename=filename,
                    line=node.line,
                    column=node.column,
                    code="W2002",
                    suggestions=["Add :key=\"item.id\" (or another stable unique key) to the loop."],
                )
            if isinstance(node, ElementNode) and node.attributes.get("live") and not str(node.attributes.get("live", "")).lower().startswith(("ws:", "wss:")):
                self.diagnostics.add(
                    DiagnosticLevel.INFO,
                    "live uses a named adapter unless its value is a ws:// or wss:// URL.",
                    filename=filename,
                    line=node.line,
                    column=node.column,
                    code="I2001",
                )
            if isinstance(node, ElementNode):
                for attribute in node.attributes:
                    if attribute.startswith("use:") and not re.fullmatch(r"use:[A-Za-z_$][\w$]*", attribute):
                        self.diagnostics.add(
                            DiagnosticLevel.WARNING,
                            f"Action name {attribute[4:]!r} is not a JavaScript identifier and cannot be registered from the component script.",
                            filename=filename,
                            line=node.line,
                            column=node.column,
                            code="W2002",
                            suggestions=["Rename it to use:actionName or expose it through globalThis."],
                        )
            for child in getattr(node, "children", []) or []:
                visit(child)
            if isinstance(node, IfNode):
                for child in node.else_children:
                    visit(child)

        for node in nodes:
            visit(node)

    def _run_plugin_hooks(self, name: str, value: Any) -> Any:
        """Run optional plugin hooks without making plugins mandatory."""
        registry = self.plugin_registry
        api = registry.get_api() if registry and hasattr(registry, "get_api") else None
        if not api or not hasattr(api, "get_hooks"):
            return value
        for hook in api.get_hooks(name):
            result = hook(value)
            if result is not None:
                value = result
        return value

    def _run_preprocessors(self, source: str, filename: str) -> Optional[str]:
        """Run optional source preprocessors before SFC parsing.

        A preprocessor may be a callable, an object exposing ``process`` or
        ``transform``, or a mapping containing one of those callables. It may
        return a string, ``(source, metadata)``, or ``{"code": source}`` /
        ``{"source": source}``. The hook is intentionally optional so normal
        JavaScript/CSS projects remain dependency-free.
        """
        preprocessors = self.options.get("preprocessors") or []
        if callable(preprocessors) or hasattr(preprocessors, "process") or hasattr(preprocessors, "transform"):
            preprocessors = [preprocessors]
        for index, preprocessor in enumerate(preprocessors):
            name = getattr(preprocessor, "name", None) or f"preprocessor-{index + 1}"
            callback = preprocessor
            if isinstance(preprocessor, dict):
                name = preprocessor.get("name") or name
                callback = preprocessor.get("process") or preprocessor.get("transform")
            elif not callable(callback):
                callback = getattr(preprocessor, "process", None) or getattr(preprocessor, "transform", None)
            if not callable(callback):
                self.diagnostics.add(
                    DiagnosticLevel.ERROR,
                    f"Invalid {name}: expected a callable or an object with process()/transform().",
                    filename=filename,
                    code="E1100",
                    suggestions=["Pass a preprocessor callable or remove it from the compiler options."],
                )
                return None
            try:
                signature = inspect.signature(callback)
                accepts_filename = "filename" in signature.parameters or any(
                    parameter.kind == inspect.Parameter.VAR_KEYWORD
                    for parameter in signature.parameters.values()
                )
                result = callback(source, filename=filename) if accepts_filename else callback(source)
                if isinstance(result, dict):
                    result = result.get("code", result.get("source", source))
                elif isinstance(result, tuple):
                    result = result[0]
                if result is None:
                    raise TypeError("returned None; preprocessors must return source text")
                source = str(result)
            except Exception as error:
                self.diagnostics.add(
                    DiagnosticLevel.ERROR,
                    f"{name} failed: {error}",
                    filename=filename,
                    code="E1101",
                    suggestions=["Fix the preprocessor error or remove the optional preprocessor."],
                )
                return None
        return source

    @staticmethod
    def _message_location(message: str) -> tuple[Optional[int], Optional[int]]:
        """Extract source coordinates emitted by the JS/template parsers."""
        match = re.search(r"\bline\s+(\d+)(?:,\s*column\s+(\d+))?", message, re.IGNORECASE)
        if not match:
            return None, None
        return int(match.group(1)), int(match.group(2)) if match.group(2) else None

    def _generate_css(self, component: Component) -> str:
        """Generate CSS from component styles."""
        if not component.style:
            return ""

        from teloce.css.generator import CSSGenerator
        blocks = getattr(component, "styles", None) or [component.style]
        generated = []
        for style in blocks:
            css_options = dict(self.options)
            css_options["scoped"] = style.scoped
            css_options["module"] = style.module
            generated.append(CSSGenerator(css_options).generate(style.css, component.name))
        css = "\n".join(css for css in generated if css)
        if self.minify:
            from teloce.compiler.minifier import minify_css
            css = minify_css(css)
        return css

    def _empty_result(self) -> Dict[str, Any]:
        """Return an empty compilation result."""
        return {
            "code": "",
            "css": "",
            "map": None,
            "diagnostics": self.diagnostics.to_dict(),
            "ast": None,
            "component": None,
            "direct_plan": None,
            "success": False,
        }


def compile(source: str, filename: str = "<input>", **options) -> Dict[str, Any]:
    """
    Compile a .vel file from source string.
    
    Args:
        source: The .vel file content
        filename: The source filename (for error reporting)
        **options: Compiler options
        
    Returns:
        Compilation result dictionary.
    """
    compiler = Compiler(options)
    return compiler.compile(source, filename)


def compile_file(filepath: str | Path, **options) -> Dict[str, Any]:
    """
    Compile a .vel file from disk.
    
    Args:
        filepath: Path to the .vel file
        **options: Compiler options
        
    Returns:
        Compilation result dictionary.
    """
    filepath = Path(filepath)
    if not filepath.exists():
        return {
            "code": "",
            "css": "",
            "map": None,
            "diagnostics": {
                "errors": [{
                    "message": f"File not found: {filepath}",
                    "filename": str(filepath),
                    "line": None,
                    "column": None,
                    "code": "E0001",
                    "suggestions": ["Check the path and make sure the .vel file exists."],
                    "notes": [],
                }],
                "warnings": [],
                "info": [],
                "hints": [],
            },
            "ast": None,
            "component": None,
            "success": False,
        }

    source = filepath.read_text(encoding="utf-8")
    return compile(source, str(filepath), **options)


def compile_project(root_dir: str | Path, **options) -> Dict[str, Any]:
    """
    Compile all .vel files in a project.
    
    Args:
        root_dir: Project root directory
        **options: Compiler options
        
    Returns:
        Compilation results for all files.
    """
    root_dir = Path(root_dir)
    results = {}
    
    # Use the same project boundary rules as the build pipeline so generated
    # output (dist/build/.venv/etc.) is never compiled as source on a second
    # invocation.
    from teloce.project.scanner import ProjectScanner
    vel_files = ProjectScanner().scan(root_dir)
    
    for vel_file in vel_files:
        rel_path = vel_file.relative_to(root_dir)
        result = compile_file(vel_file, **options)
        # Use stable POSIX-style keys on every platform for manifests and
        # reproducible project results.
        results[rel_path.as_posix()] = result
    
    return results
