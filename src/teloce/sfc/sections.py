"""
SFC sections data structure.

Represents the extracted sections from a .vel file.
"""

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class SFCSections:
    """
    Extracted sections from a .vel file.
    """
    template: str = ""
    script: str = ""
    style: str = ""
    template_line: int = 0
    template_column: int = 1
    script_line: int = 0
    style_line: int = 0
    style_scoped: bool = False
    template_attrs: Dict[str, str] = field(default_factory=dict)
    script_attrs: Dict[str, str] = field(default_factory=dict)
    style_attrs: List[Dict[str, str]] = field(default_factory=list)
    style_blocks: List[Dict[str, object]] = field(default_factory=list)
    script_lang: str = "js"
    script_setup: bool = False
    style_lang: str = "css"
    style_module: bool = False
    
    @property
    def has_template(self) -> bool:
        return bool(self.template.strip())
    
    @property
    def has_script(self) -> bool:
        return bool(self.script.strip())
    
    @property
    def has_style(self) -> bool:
        return bool(self.style.strip())
    
    @property
    def is_valid(self) -> bool:
        return self.has_template
