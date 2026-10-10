"""
SFC Parser - Parses .vel Single File Components.

Extracts template, script, and style sections from .vel files.
"""

import re
from typing import Optional, Dict, Any, List
from pathlib import Path

from teloce.sfc.component import Component, ComponentScript, ComponentStyle
from teloce.sfc.sections import SFCSections
from teloce.sfc.script import ScriptParser
from teloce.sfc.template import TemplateParser
from teloce.sfc.style import StyleParser


class SFCParser:
    """
    Parses .vel Single File Components.
    
    Extracts and validates template, script, and style sections.
    """
    
    def __init__(self, options: Optional[Dict[str, Any]] = None):
        self.options = options or {}
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self._last_sections: Optional[SFCSections] = None
    
    def parse(self, source: str, filename: str = "<input>") -> Optional[Component]:
        """
        Parse a .vel file into a Component.
        
        Args:
            source: The .vel file content
            filename: The source filename
            
        Returns:
            A Component object or None if parsing failed.
        """
        self.errors = []
        self.warnings = []
        
        # Extract sections
        sections = self._extract_sections(source, filename)
        self._last_sections = sections
        if not sections:
            self.errors.append("No sections found in .vel file")
            return None
        
        # Parse template
        template_parser = TemplateParser()
        template_ast = template_parser.parse(sections.template, filename)
        if template_parser.errors:
            self.errors.extend(template_parser.errors)
        if template_parser.warnings:
            self.warnings.extend(template_parser.warnings)
        
        # Parse script
        script_parser = ScriptParser({**self.options, "lang": sections.script_lang})
        script = script_parser.parse(sections.script, filename)
        script.lang = sections.script_lang
        script.setup = sections.script_setup
        if script_parser.errors:
            self.errors.extend(script_parser.errors)
        if script_parser.warnings:
            self.warnings.extend(script_parser.warnings)
        
        # Parse each style block independently so scoped and unscoped blocks
        # retain their own semantics while the legacy ``component.style``
        # aggregate remains available to callers.
        styles: List[ComponentStyle] = []
        for block in sections.style_blocks or [{"css": sections.style, "scoped": sections.style_scoped, "lang": sections.style_lang, "module": sections.style_module, "line": sections.style_line}]:
            style_parser = StyleParser()
            block_style = style_parser.parse(str(block.get("css", "")), filename, bool(block.get("scoped", False)))
            block_style.lang = str(block.get("lang", "css"))
            block_style.module = bool(block.get("module", False))
            block_style.line = int(block.get("line", 0))
            styles.append(block_style)
            if style_parser.errors:
                self.errors.extend(style_parser.errors)
            if style_parser.warnings:
                self.warnings.extend(style_parser.warnings)
        style = ComponentStyle(
            css="\n".join(block.css for block in styles if block.css),
            scoped=any(block.scoped for block in styles),
            line=styles[0].line if styles else 0,
            lang=styles[0].lang if styles else "css",
            module=any(block.module for block in styles),
        )
        
        if self.errors:
            return None
        
        return Component(
            name=self._extract_component_name(script, filename),
            template=template_ast,
            script=script,
            style=style,
            styles=styles,
            filename=filename,
            raw_source=source,
        )
    
    def _extract_sections(self, source: str, filename: str) -> Optional[SFCSections]:
        """Extract template, script, and style sections from source."""
        sections = SFCSections()
        template_matches = self._find_sections(source, "template")
        if not template_matches:
            self.errors.append(f"Missing <template> section in {filename}")
            return None
        if len(template_matches) > 1:
            self.errors.append(f"Only one <template> section is allowed in {filename}")
        template_match = template_matches[0]
        sections.template = template_match["body"].strip()
        template_start = source.find(sections.template, template_match["start"]) if sections.template else template_match["start"]
        sections.template_line = source[:template_start].count('\n') + 1
        sections.template_column = template_start - source.rfind('\n', 0, template_start)
        sections.template_attrs = self._parse_attrs(template_match["attrs"])

        script_matches = self._find_sections(source, "script")
        if len(script_matches) > 1:
            self.errors.append(f"Only one <script> section is allowed in {filename}")
        if script_matches:
            script_match = script_matches[0]
            sections.script = script_match["body"].strip()
            sections.script_line = source[:script_match["start"]].count('\n') + 1
            sections.script_attrs = self._parse_attrs(script_match["attrs"])
            sections.script_lang = sections.script_attrs.get('lang', 'js')
            sections.script_setup = 'setup' in sections.script_attrs
        else:
            self.warnings.append(f"No <script> section found in {filename}")
            sections.script = "export default {}"

        style_matches = self._find_sections(source, "style")
        for style_match in style_matches:
            attrs = self._parse_attrs(style_match["attrs"])
            sections.style_attrs.append(attrs)
            body = style_match["body"].strip()
            sections.style_blocks.append({
                "css": body,
                "scoped": "scoped" in attrs,
                "lang": attrs.get("lang", "css"),
                "module": "module" in attrs,
                "line": source[:style_match["start"]].count("\n") + 1,
            })
            if body:
                sections.style = f"{sections.style}\n{body}".strip()
            sections.style_scoped = sections.style_scoped or ('scoped' in attrs)
            sections.style_lang = attrs.get('lang', sections.style_lang)
            sections.style_module = sections.style_module or ('module' in attrs)
            if not sections.style_line:
                sections.style_line = source[:style_match["start"]].count('\n') + 1
        if not style_matches:
            sections.style = ""
            sections.style_scoped = False
        if sections.style_module:
            self.warnings.append(f"CSS modules are preserved as regular CSS in {filename}")
        return sections

    def _find_sections(self, source: str, tag: str) -> List[Dict[str, Any]]:
        """Extract balanced SFC blocks while respecting quoted attributes."""
        token = re.compile(rf'<(?P<close>/)?{re.escape(tag)}(?=[\s>/])', re.IGNORECASE)
        results: List[Dict[str, Any]] = []
        cursor = 0
        while True:
            opening = next(
                (
                    match
                    for match in token.finditer(source, cursor)
                    if not match.group("close")
                    and not self._inside_opaque_section(source, match.start(), tag)
                ),
                None,
            )
            if opening is None:
                break
            open_end = self._tag_end(source, opening.start())
            if open_end < 0:
                break
            depth = 1
            scan = open_end + 1
            close_start = close_end = -1
            while depth:
                match = token.search(source, scan)
                if match is None:
                    break
                if tag.lower() == "script" and self._inside_js_literal(source, open_end + 1, match.start()):
                    scan = match.end()
                    continue
                end = self._tag_end(source, match.start())
                if end < 0:
                    break
                if match.group("close"):
                    depth -= 1
                    if depth == 0:
                        close_start, close_end = match.start(), end
                        break
                elif not source[match.start():end + 1].rstrip().endswith('/>'):
                    depth += 1
                scan = end + 1
            if depth or close_start < 0:
                break
            results.append({
                "attrs": source[opening.end():open_end],
                "body": source[open_end + 1:close_start],
                "start": opening.start(),
                "end": close_end + 1,
            })
            cursor = close_end + 1
        return results

    @staticmethod
    def _inside_js_literal(source: str, start: int, end: int) -> bool:
        """Return whether a candidate tag occurs inside a JS literal/comment.

        This scanner also recognizes regular-expression literals. Without it,
        a valid pattern such as ``/<\\/script>/`` prematurely ended the SFC's
        script block.
        """
        quote = None
        regex = False
        regex_class = False
        escaped = False
        line_comment = block_comment = False
        can_start_regex = True
        index = start
        while index < end:
            char = source[index]
            nxt = source[index + 1] if index + 1 < end else ""
            if line_comment:
                if char == "\n":
                    line_comment = False
            elif block_comment:
                if char == '*' and nxt == '/':
                    block_comment = False
                    index += 1
            elif regex:
                if escaped:
                    escaped = False
                elif char == '\\':
                    escaped = True
                elif char == '[':
                    regex_class = True
                elif char == ']':
                    regex_class = False
                elif char == '/' and not regex_class:
                    regex = False
                    can_start_regex = False
            elif quote:
                if escaped:
                    escaped = False
                elif char == '\\':
                    escaped = True
                elif char == quote:
                    quote = None
                    can_start_regex = False
            elif char in "'\"`":
                quote = char
            elif char == '/' and nxt == '/':
                line_comment = True
                index += 1
            elif char == '/' and nxt == '*':
                block_comment = True
                index += 1
            elif char == '/' and can_start_regex:
                regex = True
                regex_class = False
            elif char.isalpha() or char in '_$':
                token_start = index
                index += 1
                while index < end and (source[index].isalnum() or source[index] in '_$'):
                    index += 1
                word = source[token_start:index]
                can_start_regex = word in {
                    'return', 'throw', 'case', 'delete', 'void', 'typeof',
                    'new', 'in', 'of', 'yield', 'await', 'else', 'do',
                    'instanceof',
                }
                continue
            elif char.isdigit():
                can_start_regex = False
            elif char in '([{,;:?=':
                can_start_regex = True
            elif char in ')]}':
                can_start_regex = False
            elif char in '+-*%&|!<>^~':
                can_start_regex = True
            index += 1
        return bool(quote or regex or line_comment or block_comment)

    @staticmethod
    def _inside_opaque_section(source: str, position: int, target: str) -> bool:
        """Ignore SFC-looking tags embedded in another section.

        A documentation string or template literal can contain text such as
        ``<template>``. Section discovery must not mistake that text for a
        second top-level SFC block. Script/style bodies are opaque while a
        different section is being located.
        """
        if target.lower() in {"script", "style"}:
            return False
        pattern = re.compile(r"<(?P<tag>script|style)\b[^>]*>[\s\S]*?</(?P=tag)\s*>", re.IGNORECASE)
        return any(match.start() < position < match.end() for match in pattern.finditer(source))

    @staticmethod
    def _tag_end(source: str, start: int) -> int:
        """Find a tag's closing ``>`` without stopping inside quotes."""
        quote = None
        escaped = False
        for index in range(start, len(source)):
            char = source[index]
            if quote:
                if escaped:
                    escaped = False
                elif char == '\\':
                    escaped = True
                elif char == quote:
                    quote = None
            elif char in "'\"":
                quote = char
            elif char == '>':
                return index
        return -1

    def _parse_attrs(self, raw: str) -> Dict[str, str]:
        """Parse boolean, quoted, and unquoted SFC block attributes."""
        attrs: Dict[str, str] = {}
        pattern = re.compile(r'([:\w-]+)(?:\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|([^\s]+)))?')
        for match in pattern.finditer(raw or ""):
            attrs[match.group(1).lower()] = next((value for value in match.groups()[1:] if value is not None), "")
        return attrs

    def parse_result(self, source: str, filename: str = "<input>") -> Dict[str, Any]:
        """Return parse metadata in the shape expected by SFC tooling."""
        component = self.parse(source, filename)
        sections = self._last_sections
        return {
            "template": sections.template if sections else "",
            "script": sections.script if sections else "",
            "style": sections.style if sections else "",
            "name": component.name if component else Path(filename).stem,
            "component": component,
            "diagnostics": {"errors": list(self.errors), "warnings": list(self.warnings)},
        }
    
    def _extract_component_name(self, script: ComponentScript, filename: str) -> str:
        """Extract component name from script or filename."""
        if script.name:
            return script.name
        
        # Use filename without extension
        return Path(filename).stem


def parse_sfc(source: str, filename: str = "<input>") -> Optional[Component]:
    """Parse a single-file component using a fresh parser instance."""
    return SFCParser().parse(source, filename)


def parse_sfc_result(source: str, filename: str = "<input>") -> Dict[str, Any]:
    """Parse an SFC and return sections plus diagnostics for tooling."""
    return SFCParser().parse_result(source, filename)
