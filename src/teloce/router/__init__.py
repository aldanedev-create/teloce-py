"""
Router package for Teloce.

Provides router compilation and generation for client-side routing.
"""

from teloce.router.compiler import RouterCompiler
from teloce.router.generator import RouterGenerator
from teloce.router.facade import generate_router, generate_spa_router

__all__ = [
    "RouterCompiler",
    "RouterGenerator",
    "generate_router",
    "generate_spa_router",
]
