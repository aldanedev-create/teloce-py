"""First-class native JavaScript build integration (no Node.js required)."""
from __future__ import annotations

import base64
import json
from pathlib import Path

from minifyjs import Adapter, Result, bundle, minify


class TeloceMinifyJSAdapter(Adapter):
    """Minify compiler-owned modules without changing their public paths.

    Teloce owns asset names, CSS, manifests and source map composition. The
    inherited file/directory methods remain available for application assets.
    """
    def output_name(self, path: Path) -> Path:
        return Path(path)

    def transform(self, source: str, *, source_name: str = 'generated.js',
                  source_map: dict | None = None) -> Result:
        opts = self.default_options
        if source_map:
            encoded = base64.b64encode(json.dumps(source_map).encode()).decode()
            source += '\n//# sourceMappingURL=data:application/json;base64,' + encoded
        return minify(source, compress=opts.compress, mangle=opts.mangle,
                      target=opts.target, format=opts.format,
                      sourcemap='external' if source_map else opts.sourcemap,
                      legal_comments=opts.legal_comments, source_name=source_name)


class MinifyJSBundler:
    """Adapt MinifyJS's dependency-aware build API to Teloce artifacts."""
    def __init__(self, project_root: str | Path):
        self.project_root = Path(project_root).resolve()
        self.result: Result | None = None

    def bundle(self, entry: str | Path, output: str | Path | None = None, *,
               splitting: bool = True, minify: bool = False,
               sourcemap: bool = False, metafile: str | Path | None = None,
               target: str | None = None, drop: list[str] | None = None,
               legal_comments: str | None = None, charset: str | None = None,
               hash_assets: bool = False, external: list[str] | None = None,
               packages: str = 'bundle', define: dict[str, str] | None = None,
               tree_shaking: bool = True) -> Path:
        entry = Path(entry).resolve()
        output = Path(output).resolve() if output else entry.with_name(entry.stem + '.bundle.js')
        if output.suffix != '.js':
            raise ValueError('MinifyJS bundle output must end in .js')
        output.parent.mkdir(parents=True, exist_ok=True)
        self.result = bundle([str(entry)], working_dir=str(self.project_root),
            outdir=str(output.parent), format='esm', platform='browser',
            splitting=splitting, compress=minify, mangle=minify,
            sourcemap='both' if sourcemap else None,
            target=target or 'es2020', charset=charset or 'utf8',
            legal_comments=legal_comments, drop=drop, define=define,
            tree_shaking=tree_shaking, external=external, packages=packages,
            entry_names=output.stem + ('-[hash]' if hash_assets else ''),
            chunk_names='chunks/[name]-[hash]', asset_names='assets/[name]-[hash]',
            metafile=str(Path(metafile).resolve()) if metafile else None)
        for path, info in self.result.metafile.get('outputs', {}).items():
            source = info.get('entryPoint')
            if source and (self.project_root / source).resolve() == entry:
                emitted = (self.project_root / path).resolve()
                if emitted.suffix == '.js':
                    return emitted
        raise RuntimeError('MinifyJS did not report the requested entry output')


def rewrite_module_paths(source: str, replacements: dict[str, str]) -> str:
    """Rewrite literal module specifiers, leaving ordinary string values intact."""
    from teloce.javascript.tree_sitter_backend import parse_tree
    data = source.encode('utf-8')
    root = parse_tree(source).root_node
    changes = []
    stack = [root]
    while stack:
        node = stack.pop()
        literal = None
        if node.type in ('import_statement', 'export_statement'):
            literal = node.child_by_field_name('source')
        elif node.type == 'call_expression':
            function = node.child_by_field_name('function')
            arguments = node.child_by_field_name('arguments')
            if function and arguments and function.text in (b'import', b'require'):
                children = arguments.named_children
                if len(children) == 1 and children[0].type == 'string':
                    literal = children[0]
        if literal:
            name = data[literal.start_byte + 1:literal.end_byte - 1].decode('utf-8')
            if name in replacements:
                changes.append((literal.start_byte, literal.end_byte,
                                json.dumps(replacements[name]).encode('utf-8')))
        stack.extend(node.named_children)
    for start, end, replacement in sorted(changes, reverse=True):
        data = data[:start] + replacement + data[end:]
    return data.decode('utf-8')
