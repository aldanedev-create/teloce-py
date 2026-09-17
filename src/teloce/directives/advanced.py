"""Built-in metadata directives for data-heavy and interactive pages.

The compiler lowers their markup metadata and the shared browser runtime owns
the behavior. These classes make the same names available to plugin authors
and the public directive registry.
"""

from __future__ import annotations

from teloce.directives.base import Directive, DirectiveContext, DirectiveType


class MetadataDirective(Directive):
    def validate(self, value: str, context: DirectiveContext) -> list[str]:
        if self.name in {"scrolly", "step", "use"}:
            return []
        return [] if value and value.strip() else [f"{self.name} directive cannot be empty"]

    def transform(self, value: str, context: DirectiveContext) -> str:
        return value.strip()


class VirtualForDirective(MetadataDirective):
    def __init__(self):
        super().__init__("virtual-for", DirectiveType.LOOP, 35, "Bounded DOM virtual list rendering")


class MemoDirective(MetadataDirective):
    def __init__(self):
        super().__init__("memo", DirectiveType.CUSTOM, 20, "Skip a subtree when memo keys are unchanged")


class ScrollyDirective(MetadataDirective):
    def __init__(self):
        super().__init__("scrolly", DirectiveType.CUSTOM, 20, "IntersectionObserver-driven story steps")


class StepDirective(MetadataDirective):
    def __init__(self):
        super().__init__("step", DirectiveType.CUSTOM, 20, "A scrollytelling step")


class AnnotationDirective(MetadataDirective):
    def __init__(self):
        super().__init__("chart-annotation", DirectiveType.CUSTOM, 20, "Library-independent chart annotation")


class PollDirective(MetadataDirective):
    def __init__(self):
        super().__init__("poll", DirectiveType.CUSTOM, 20, "Visibility-aware polling")


class LiveDirective(MetadataDirective):
    def __init__(self):
        super().__init__("live", DirectiveType.CUSTOM, 20, "WebSocket or adapter-backed live data")


class UseDirective(MetadataDirective):
    def __init__(self):
        super().__init__("use", DirectiveType.CUSTOM, 20, "DOM action with update and destroy hooks")
