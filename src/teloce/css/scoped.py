"""
CSS Scoper - scopes CSS selectors to components.

Adds unique scope attributes to CSS selectors for component isolation.
"""

import re
from typing import List, Optional
from teloce.css.parser import CSSParser, CSSAtRule, CSSDeclaration


class CSSScoper:
    """
    Scopes CSS selectors with a unique component ID.
    """
    
    def __init__(self):
        self.errors: List[str] = []
    
    def scope(self, css: str, scope_id: str) -> str:
        """
        Scope CSS with a unique component ID.
        
        Args:
            css: The CSS source
            scope_id: The unique scope ID (e.g., 'data-v-abc123')
            
        Returns:
            Scoped CSS.
        """
        self.errors = []
        
        if not css or not css.strip():
            return ""
        
        # Parse the CSS
        parser = CSSParser()
        stylesheet = parser.parse(css)
        
        if parser.errors:
            self.errors.extend(parser.errors)
            return css
        
        # Scope the rules
        scoped_rules = []
        
        for rule in stylesheet.rules:
            scoped_selector = self._scope_selector(rule.selector, scope_id)
            if scoped_selector:
                declarations = self._format_declarations(rule.declarations)
                scoped_rules.append(f"{scoped_selector} {{ {declarations} }}")
        
        for at_rule in stylesheet.at_rules:
            scoped_at_rule = self._scope_at_rule(at_rule, scope_id)
            if scoped_at_rule:
                scoped_rules.append(scoped_at_rule)
        
        return '\n'.join(scoped_rules)
    
    def _scope_selector(self, selector: str, scope_id: str) -> str:
        """Scope a single CSS selector."""
        if not selector or selector == '':
            return f"[{scope_id}]"
        
        # Handle keyframes (don't scope)
        if selector.startswith('@keyframes'):
            return selector
        
        # Split only on top-level commas. Commas inside functional pseudo
        # classes, attribute selectors, strings, or escaped text are part of
        # the selector and must not create a new rule.
        parts = self._split_selector_list(selector)
        scoped_parts = []
        
        for part in parts:
            part = part.strip()
            if not part:
                continue
            
            scoped_part = self._scope_selector_part(part, scope_id)
            if scoped_part:
                scoped_parts.append(scoped_part)
        
        return ', '.join(scoped_parts)

    def _split_selector_list(self, selector: str) -> List[str]:
        """Split a selector list while respecting CSS nesting syntax."""
        parts: List[str] = []
        start = 0
        depth = 0
        quote = ''
        escaped = False
        for index, character in enumerate(selector):
            if escaped:
                escaped = False
                continue
            if character == '\\':
                escaped = True
                continue
            if quote:
                if character == quote:
                    quote = ''
                continue
            if character in "'\"":
                quote = character
            elif character in '([':
                depth += 1
            elif character in ')]':
                depth = max(0, depth - 1)
            elif character == ',' and depth == 0:
                parts.append(selector[start:index].strip())
                start = index + 1
        parts.append(selector[start:].strip())
        return [part for part in parts if part]
    
    def _scope_selector_part(self, selector: str, scope_id: str) -> str:
        """Scope a single selector part."""
        # Vue/Teloce-compatible escape hatches.  Global and deep selectors
        # deliberately do not receive the component attribute themselves,
        # while the local prefix remains scoped.
        deep = re.search(r':deep\(([^()]*)\)', selector)
        if deep:
            prefix = selector[:deep.start()].strip()
            suffix = selector[deep.end():].strip()
            local = self._scope_selector_part(prefix, scope_id) if prefix else ""
            result = " ".join(part for part in (local, deep.group(1).strip(), suffix) if part)
            return result

        global_match = re.search(r':global\(([^()]*)\)', selector)
        if global_match:
            prefix = selector[:global_match.start()].strip()
            suffix = selector[global_match.end():].strip()
            local = self._scope_selector_part(prefix, scope_id) if prefix else ""
            if suffix:
                local_suffix = self._scope_selector_part(suffix, scope_id)
                return " ".join(part for part in (local, global_match.group(1).strip(), local_suffix) if part)
            return " ".join(part for part in (local, global_match.group(1).strip()) if part)

        slotted = re.fullmatch(r':slotted\(([^()]*)\)', selector.strip())
        if slotted:
            return f'[{scope_id}] > {slotted.group(1).strip()}'

        # Scope the *last* compound selector (the element the rule finally
        # targets), then insert the attribute before that compound's own
        # pseudo-classes/elements.  Splitting at the first pseudo-class of the
        # whole selector would mis-scope ``.a:hover .b`` as ``.a[id]:hover .b``
        # and leave ``.b`` unscoped.
        split_at = self._last_top_level_combinator(selector)
        prefix = selector[:split_at] if split_at is not None else ''
        compound = selector[split_at:] if split_at is not None else selector
        trailing = len(compound) - len(compound.rstrip())
        whitespace = compound[len(compound) - trailing:] if trailing else ''
        compound = compound.rstrip()

        pseudo_at = self._first_top_level_pseudo(compound)
        base = compound[:pseudo_at] if pseudo_at is not None else compound
        pseudo = compound[pseudo_at:] if pseudo_at is not None else ''
        return f"{prefix}{base}[{scope_id}]{pseudo}{whitespace}"

    @staticmethod
    def _first_top_level_pseudo(selector: str) -> Optional[int]:
        quote = ''
        escaped = False
        square = round_depth = 0
        for index, character in enumerate(selector):
            if escaped:
                escaped = False
                continue
            if character == '\\':
                escaped = True
                continue
            if quote:
                if character == quote:
                    quote = ''
                continue
            if character in "'\"":
                quote = character
            elif character == '[':
                square += 1
            elif character == ']':
                square = max(0, square - 1)
            elif character == '(':
                round_depth += 1
            elif character == ')':
                round_depth = max(0, round_depth - 1)
            elif character == ':' and square == 0 and round_depth == 0:
                return index
        return None

    @staticmethod
    def _last_top_level_combinator(selector: str) -> Optional[int]:
        quote = ''
        escaped = False
        square = round_depth = 0
        boundary: Optional[int] = None
        for index, character in enumerate(selector):
            if escaped:
                escaped = False
                continue
            if character == '\\':
                escaped = True
                continue
            if quote:
                if character == quote:
                    quote = ''
                continue
            if character in "'\"":
                quote = character
            elif character == '[':
                square += 1
            elif character == ']':
                square = max(0, square - 1)
            elif character == '(':
                round_depth += 1
            elif character == ')':
                round_depth = max(0, round_depth - 1)
            elif square == 0 and round_depth == 0 and (character.isspace() or character in '>+~'):
                boundary = index + 1
        return boundary
    
    def _scope_at_rule(self, at_rule: CSSAtRule, scope_id: str) -> Optional[str]:
        """Scope an at-rule."""
        if at_rule.name in ('import', 'charset', 'namespace', 'layer') and not at_rule.rules and not at_rule.declarations:
            return f"@{at_rule.name} {at_rule.value};"

        if at_rule.name in ('keyframes', '-webkit-keyframes', '-moz-keyframes'):
            # Keyframe selectors describe animation progress, not DOM nodes.
            frames = []
            for rule in at_rule.rules:
                frames.append(f"{rule.selector} {{ {self._format_declarations(rule.declarations)} }}")
            return f"@{at_rule.name} {at_rule.value} {{ {' '.join(frames)} }}"

        if at_rule.declarations:
            declarations = self._format_declarations(at_rule.declarations)
            return f"@{at_rule.name} {at_rule.value} {{ {declarations} }}"

        if at_rule.rules or at_rule.nested_at_rules:
            # Scope nested rules
            scoped_rules = []
            for rule in at_rule.rules:
                scoped_selector = self._scope_selector(rule.selector, scope_id)
                if scoped_selector:
                    declarations = self._format_declarations(rule.declarations)
                    scoped_rules.append(f"{scoped_selector} {{ {declarations} }}")

            for nested in at_rule.nested_at_rules:
                rendered = self._scope_at_rule(nested, scope_id)
                if rendered:
                    scoped_rules.append(rendered)
            
            if scoped_rules:
                scoped_body = '\n'.join(scoped_rules)
                return f"@{at_rule.name} {at_rule.value} {{ {scoped_body} }}"
        
        return None
    
    def _format_declarations(self, declarations: List[CSSDeclaration]) -> str:
        """Format declarations as a string."""
        if not declarations:
            return ""
        
        return '; '.join(f"{decl.property}: {decl.value}" for decl in declarations)
    
    def _get_scope_id(self, component_name: str, hashed: bool = True) -> str:
        """Generate a scope ID."""
        if hashed:
            import hashlib
            hash_val = hashlib.md5(component_name.encode()).hexdigest()[:8]
            return f"data-v-{hash_val}"
        return f"data-v-{component_name.lower()}"
