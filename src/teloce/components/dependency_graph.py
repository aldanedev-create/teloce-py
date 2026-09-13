"""
Dependency graph - manages component dependencies.

Builds and analyzes dependency graphs between components.
"""

from typing import Dict, List, Set, Optional, Tuple
from collections import defaultdict, deque


class DependencyGraph:
    """
    Manages component dependency graphs.
    
    Builds and analyzes dependencies between components.
    """
    
    def __init__(self):
        self._graph: Dict[str, Set[str]] = defaultdict(set)
        self._reverse_graph: Dict[str, Set[str]] = defaultdict(set)
        self._components: Set[str] = set()
    
    def add_component(self, name: str) -> None:
        """Add a component to the graph."""
        self._components.add(name)
        if name not in self._graph:
            self._graph[name] = set()
        if name not in self._reverse_graph:
            self._reverse_graph[name] = set()
    
    def add_dependency(self, component: str, dependency: str) -> None:
        """
        Add a dependency between components.
        
        Args:
            component: The component that depends on dependency
            dependency: The dependency component
        """
        self.add_component(component)
        self.add_component(dependency)
        
        self._graph[component].add(dependency)
        self._reverse_graph[dependency].add(component)
    
    def get_dependencies(self, component: str) -> Set[str]:
        """Get all direct dependencies of a component."""
        return self._graph.get(component, set()).copy()
    
    def get_dependents(self, component: str) -> Set[str]:
        """Get all components that depend on a component."""
        return self._reverse_graph.get(component, set()).copy()
    
    def get_all_dependencies(self, component: str) -> Set[str]:
        """
        Get all transitive dependencies of a component.
        
        Uses BFS to find all dependencies.
        """
        visited = set()
        queue = deque([component])
        
        while queue:
            current = queue.popleft()
            for dep in self._graph.get(current, set()):
                if dep not in visited:
                    visited.add(dep)
                    queue.append(dep)
        
        # Remove the component itself
        visited.discard(component)
        return visited
    
    def get_all_dependents(self, component: str) -> Set[str]:
        """
        Get all transitive dependents of a component.
        
        Uses BFS to find all dependents.
        """
        visited = set()
        queue = deque([component])
        
        while queue:
            current = queue.popleft()
            for dep in self._reverse_graph.get(current, set()):
                if dep not in visited:
                    visited.add(dep)
                    queue.append(dep)
        
        visited.discard(component)
        return visited
    
    def get_topological_order(self) -> List[str]:
        """
        Get components in topological order (dependencies first).
        
        Returns:
            A list of component names in dependency order.
        """
        # `_graph` stores component -> dependency, so the number of
        # unresolved dependencies belongs to the component itself.
        in_degree = {component: len(self._graph.get(component, set()))
                     for component in self._components}
        
        # Start with components with no incoming edges
        queue = deque()
        for comp in sorted(self._components):
            if in_degree[comp] == 0:
                queue.append(comp)
        
        result = []
        while queue:
            comp = queue.popleft()
            result.append(comp)
            
            for dependent in sorted(self._reverse_graph.get(comp, set())):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)
        
        # If there are remaining components, there's a cycle
        if len(result) < len(self._components):
            # Add remaining components in any order
            remaining = sorted(self._components - set(result))
            result.extend(remaining)
        
        return result
    
    def has_cycle(self) -> Tuple[bool, Optional[List[str]]]:
        """
        Check if the dependency graph has a cycle.
        
        Returns:
            A tuple of (has_cycle, cycle_path).
        """
        visited = set()
        stack = set()
        
        def dfs(node: str, path: List[str]) -> Optional[List[str]]:
            visited.add(node)
            stack.add(node)
            path.append(node)
            
            for neighbor in sorted(self._graph.get(node, set())):
                if neighbor not in visited:
                    result = dfs(neighbor, path)
                    if result is not None:
                        return result
                elif neighbor in stack:
                    # Found a cycle
                    cycle_start = path.index(neighbor)
                    return path[cycle_start:] + [neighbor]
            
            stack.remove(node)
            path.pop()
            return None
        
        for comp in sorted(self._components):
            if comp not in visited:
                result = dfs(comp, [])
                if result is not None:
                    return (True, result)
        
        return (False, None)
    
    def get_component_count(self) -> int:
        """Get the number of components in the graph."""
        return len(self._components)
    
    def get_edge_count(self) -> int:
        """Get the number of dependency edges."""
        return sum(len(deps) for deps in self._graph.values())
    
    def clear(self) -> None:
        """Clear the dependency graph."""
        self._graph.clear()
        self._reverse_graph.clear()
        self._components.clear()
