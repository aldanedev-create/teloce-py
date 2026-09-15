"""
Component data structures.

Represents a parsed .vel component with all its parts.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List


@dataclass
class ComponentScript:
    """
    Parsed script section of a component.
    """
    data: Optional[str] = None
    # The object expression is kept for backwards compatibility, while the
    # complete function body preserves local variables used by ``return``.
    # Without this, compact data functions such as
    # ``data() { const defaults = ...; return { ...defaults }; }`` lose the
    # local declaration during code generation.
    data_body: Optional[str] = None
    methods: Dict[str, str] = field(default_factory=dict)
    method_params: Dict[str, str] = field(default_factory=dict)
    method_async: Dict[str, bool] = field(default_factory=dict)
    computed: Dict[str, str] = field(default_factory=dict)
    props: Dict[str, Any] = field(default_factory=dict)
    lifecycle: Dict[str, str] = field(default_factory=dict)
    lifecycle_params: Dict[str, str] = field(default_factory=dict)
    lifecycle_async: Dict[str, bool] = field(default_factory=dict)
    watch: Dict[str, str] = field(default_factory=dict)
    watch_params: Dict[str, str] = field(default_factory=dict)
    watch_async: Dict[str, bool] = field(default_factory=dict)
    emits: List[str] = field(default_factory=list)
    name: Optional[str] = None
    raw: str = ""
    module_code: str = ""
    imports: List[Any] = field(default_factory=list)
    line: int = 0
    lang: str = "js"
    setup: bool = False
    
    @property
    def has_data(self) -> bool:
        return self.data is not None and self.data.strip() != ""
    
    @property
    def has_methods(self) -> bool:
        return len(self.methods) > 0
    
    @property
    def has_computed(self) -> bool:
        return len(self.computed) > 0


@dataclass
class ComponentStyle:
    """
    Parsed style section of a component.
    """
    css: str = ""
    scoped: bool = False
    line: int = 0
    lang: str = "css"
    module: bool = False
    
    @property
    def has_css(self) -> bool:
        return self.css.strip() != ""


@dataclass
class Component:
    """
    Complete parsed component.
    """
    name: str
    template: Any  # AST nodes
    script: ComponentScript
    style: ComponentStyle
    styles: List[ComponentStyle] = field(default_factory=list)
    filename: str = ""
    raw_source: str = ""
    
    def __post_init__(self):
        if not self.name:
            self.name = "Component"
        if not self.styles:
            self.styles = [self.style] if self.style.has_css else []
    
    @property
    def script_data(self) -> Optional[str]:
        return self.script.data
    
    @property
    def script_methods(self) -> Dict[str, str]:
        return self.script.methods
    
    @property
    def script_computed(self) -> Dict[str, str]:
        return self.script.computed
    
    @property
    def has_style(self) -> bool:
        return self.style.has_css
