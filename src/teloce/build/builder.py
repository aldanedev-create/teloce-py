"""
Builder - builds the project.

Orchestrates the build process for .vel files.
"""

import hashlib
import inspect
import json
import os
import re
import shutil
import time
from importlib.resources import files as package_files
from pathlib import Path
from typing import Any, Dict, List, Optional

from teloce.build.assets import AssetManager
from teloce.build.bundler import ModuleBundler
from teloce.build.esbuild import EsbuildBundler
from teloce.build.manifest import ManifestGenerator
from teloce.build.writer import FileWriter
from teloce.compiler.compiler import Compiler
from teloce.compiler.generator import Generator, SAFE_EXPRESSION_RUNTIME, SHARED_DOM_RUNTIME
from teloce.compiler.minifier import minify_css, minify_js
from teloce.components.dependency_graph import DependencyGraph
from teloce.project.scanner import ProjectScanner
from teloce.ssr import to_jinax_template


class Builder:
    """
    Builds the project.
    
    Orchestrates compilation of .vel files.
    """
    
    def __init__(self, options: Optional[Dict[str, Any]] = None):
        requested = dict(options or {})
        mode = requested.get("mode") or ("development" if requested.get("dev") else "production")
        # Keep the programmatic Builder defaults backward compatible.  The
        # CLI passes ``production=True`` explicitly; applications that call
        # Builder directly opt into release defaults with ``mode=production``
        # or the boolean flag.
        production = bool(requested.get("production", False) or requested.get("mode") == "production")
        release_defaults = {
            "minify": True,
            "hash_assets": True,
            "extract_css": True,
            "tree_shake": True,
            "clean": True,
        } if production and mode == "production" and requested.get("dev") is not True else {}
        # A project build always emits one reusable browser runtime by default.
        # Consumers may explicitly opt out when they need a self-contained
        # single-file artifact, but ordinary Flask/FastAPI/Django/Flaxon builds
        # should not duplicate runtime helpers into every component module.
        self.options = {"shared_runtime": True, "mode": mode, **release_defaults, **requested}
        self.production = production and mode == "production" and not self.options.get("dev", False)
        self.compiler = Compiler(self.options)
        self.writer = FileWriter()
        self.manifest = ManifestGenerator()
        self.scanner = ProjectScanner()
        self.dependency_graph = DependencyGraph()
        self.clean_output = bool(self.options.get("clean", False))
        self.hash_assets = bool(self.options.get("hash_assets", False))
        self.extract_css = bool(self.options.get("extract_css", self.production))
        self.assets = AssetManager(self.hash_assets)
        self.max_asset_size = int(self.options.get("max_asset_size", 0) or 0)
        # Incremental output must be invalidated when compiler behavior
        # changes. Without a tool fingerprint, an editable installation can
        # serve stale JavaScript after a generator/runtime fix.
        self.compiler_signature = self._compiler_signature()
        
        self.root_dir: Optional[Path] = None
        self.out_dir: Optional[Path] = None
        self.stats: Dict[str, Any] = {}
    
    def build(self, root_dir: str | Path, out_dir: str | Path = None) -> Dict[str, Any]:
        """
        Build the project.
        
        Args:
            root_dir: The project root directory.
            out_dir: The output directory.
            
        Returns:
            Build statistics and results.
        """
        start_time = time.time()
        
        self.root_dir = Path(root_dir)
        self.out_dir = Path(out_dir) if out_dir else self.root_dir / 'dist'

        if self.clean_output:
            self._clean_generated_output()
        
        # Ensure output directory exists
        self.out_dir.mkdir(parents=True, exist_ok=True)
        
        # Scan for .vel files
        # The output directory is frequently inside the project (for example
        # ``public`` on Vercel).  Never treat generated .vel files there as
        # new source files on the same build.
        # The CLI passes the configured static source directory.  Keep the
        # programmatic API's historical root scan unless callers opt in, so
        # existing projects that keep components elsewhere remain compatible.
        source_root = self.root_dir
        static_dir = self.options.get("static_dir")
        if static_dir:
            configured_source = self.root_dir / str(static_dir)
            if configured_source.is_dir():
                source_root = configured_source
        vel_files = self.scanner.scan(source_root, exclude_paths=[self.out_dir])
        self._build_dependency_graph(vel_files)
        cache = self._load_build_cache()
        source_hashes = {
            # Hash the decoded source exactly as the compiler reads it. This
            # avoids false cache misses from Windows CRLF normalization.
            path.relative_to(self.root_dir).as_posix(): hashlib.sha256(path.read_text(encoding='utf-8').encode('utf-8')).hexdigest()
            for path in vel_files
        }
        changed_inputs = {
            name for name, digest in source_hashes.items()
            if cache.get(name, {}).get('source_hash') != digest
        }
        
        results = {
            'mode': ('development' if self.options.get('dev', False)
                     else 'static' if self.options.get('static', False)
                     else 'production'),
            'total': len(vel_files),
            'compiled': 0,
            'failed': 0,
            'errors': [],
            'files': [],
            'dependencies': {
                component: sorted(self.dependency_graph.get_dependencies(component))
                for component in sorted(self.dependency_graph._components)
            },
            'dependency_cycle': self.dependency_graph.has_cycle()[1],
            'cache_hits': 0,
            'cache_misses': 0,
            'build_signature': self.compiler_signature,
        }
        if self.options.get('shared_runtime'):
            # Generated browser modules live below dist/static. Keep the
            # shared runtime in that same public tree so Flask, Django,
            # FastAPI and other hosts that expose only ``dist/static`` can
            # resolve its relative ESM imports.
            runtime_source = self._shared_runtime_source()
            runtime_path = self._shared_runtime_path()
            runtime_path.parent.mkdir(parents=True, exist_ok=True)
            runtime_path.write_text(runtime_source, encoding='utf-8')
            results['runtime'] = runtime_path.relative_to(self.out_dir).as_posix()
            results['runtime_size'] = runtime_path.stat().st_size
            results['files'].append({
                'input': '<shared-runtime>',
                'output': results['runtime'],
                'size': results['runtime_size'],
            })
            # Signals are a first-class part of the shared runtime. Keep their
            # scheduler dependency beside the barrel so generated components
            # can use ``signal()``/``effect()`` without per-component setup.
            runtime_package = package_files("teloce.runtime")
            for runtime_name in ("scheduler.js", "signals.js"):
                runtime_module_path = runtime_path.parent / runtime_name
                runtime_module_source = runtime_package.joinpath(runtime_name).read_text(encoding="utf-8")
                if self.options.get('minify', False):
                    runtime_module_source = self._minify_generated_js(runtime_module_source)
                runtime_module_path.write_text(runtime_module_source, encoding="utf-8")
                results['files'].append({
                    'input': f'<shared-runtime>/{runtime_name}',
                    'output': runtime_module_path.relative_to(self.out_dir).as_posix(),
                    'size': runtime_module_path.stat().st_size,
                })
        
        # Compile each .vel file
        for vel_file in vel_files:
            try:
                input_name = vel_file.relative_to(self.root_dir).as_posix()
                cached = cache.get(input_name)
                dependencies = self.dependency_graph.get_dependencies(input_name)
                dependency_changed = any(dep in changed_inputs for dep in dependencies)
                can_reuse = bool(
                    self.options.get('incremental', self.options.get('dev', False))
                    and not self.clean_output
                    and cached
                    and cached.get('source_hash') == source_hashes[input_name]
                    and not dependency_changed
                    and cached.get('output')
                    and (self.out_dir / cached['output']).is_file()
                )
                if can_reuse:
                    result_info = {
                        'input': input_name,
                        'output': cached['output'],
                        'size': cached.get('size', (self.out_dir / cached['output']).stat().st_size),
                        'source_hash': cached['source_hash'],
                    }
                    results['cache_hits'] += 1
                else:
                    result = self._compile_file(vel_file)
                    result_info = {
                        'input': input_name,
                        'output': result['output'],
                        'size': result['size'],
                        'source_hash': result['source_hash'],
                    }
                    results['compiled'] += 1
                    results['cache_misses'] += 1
                results['files'].append(result_info)
                if self.options.get('ssr'):
                    ssr_output = cached.get('ssr_output') if can_reuse else None
                    if not ssr_output or not (self.out_dir / ssr_output).is_file():
                        ssr_output = self._write_ssr_file(vel_file, vel_file.read_text(encoding='utf-8'))
                    results['files'].append({
                        'input': input_name,
                        'output': ssr_output,
                        'size': (self.out_dir / ssr_output).stat().st_size,
                        'source_hash': source_hashes[input_name],
                    })
            except Exception as e:
                results['failed'] += 1
                results['errors'].append({
                    'file': str(vel_file),
                    'error': str(e),
                })
        
        # Copy assets
        assets_copied = self.assets.copy_assets(
            self.root_dir,
            self.out_dir,
            asset_directories=[self.options.get('static_dir', 'static')],
        )
        copied_asset_paths = self.assets.get_copied_assets()
        results['assets_copied'] = assets_copied
        results['asset_map'] = dict(self.assets.asset_map)
        self._write_hashed_aliases(results)
        self._rewrite_generated_asset_map(results)
        # Generated modules can already contain hashed imports.  Copied
        # application assets (images, fonts, user JS/CSS, etc.) need the same
        # rewrite pass so a production build never points at a filename that
        # was replaced by AssetManager.
        self._rewrite_generated_references(results)
        asset_files = []
        for copied in copied_asset_paths:
            copied_path = Path(copied)
            try:
                relative = copied_path.relative_to(self.out_dir).as_posix()
            except ValueError:
                continue
            if copied_path.is_file():
                asset_files.append({
                    'output': relative,
                    'size': copied_path.stat().st_size,
                })
        results['asset_files'] = asset_files
        results['asset_bytes'] = sum(int(item['size']) for item in asset_files)
        results['total_bytes'] = (
            sum(int(file_info.get('size', 0)) for file_info in results['files'])
            + results['asset_bytes']
        )
        results['size_warnings'] = [
            {
                'output': file_info.get('output'),
                'size': file_info.get('size'),
                'limit': self.max_asset_size,
                'message': f"Generated asset exceeds {self.max_asset_size} bytes",
            }
            for file_info in results['files']
            if self.max_asset_size and int(file_info.get('size', 0)) > self.max_asset_size
        ]
        if self.max_asset_size:
            results['size_warnings'].extend({
                'output': item['output'],
                'size': item['size'],
                'limit': self.max_asset_size,
                'message': f"Copied asset exceeds {self.max_asset_size} bytes",
            } for item in asset_files if int(item['size']) > self.max_asset_size)
        if self.options.get('bundle', False) and not results['failed']:
            try:
                entry = self.options.get('bundle_entry')
                if not entry:
                    default_entry = self.out_dir / 'static' / 'js' / 'App.js'
                    if default_entry.exists():
                        entry = default_entry
                    else:
                        generated_entries = [
                            self.out_dir / str(file_info['output'])
                            for file_info in results['files']
                            if str(file_info.get('input', '')).endswith('.vel')
                            and str(file_info.get('output', '')).endswith('.js')
                        ]
                        app_entries = [
                            path for path in generated_entries
                            if path.stem.split('.')[0].lower() == 'app'
                        ]
                        entry = (sorted(app_entries)[0] if app_entries
                                 else sorted(generated_entries)[0]
                                 if generated_entries else next(self.out_dir.rglob('*.js')))
                entry = self._resolve_bundle_entry(entry)
                output = self.options.get('bundle_output')
                if self.options.get('bundler', 'teloce') == 'esbuild':
                    bundle_path = EsbuildBundler(self.root_dir).bundle(
                        entry,
                        output,
                        splitting=bool(self.options.get('code_splitting', True)),
                        minify=bool(self.options.get('minify', False)),
                        sourcemap=bool(self.options.get('source_maps', False)),
                        metafile=(self.out_dir / 'esbuild-meta.json') if self.options.get('report') else None,
                        target=self.options.get('target'),
                        drop=self.options.get('drop'),
                        legal_comments=self.options.get('legal_comments'),
                        charset=self.options.get('charset'),
                        hash_assets=self.hash_assets,
                    )
                else:
                    bundle_path = ModuleBundler(self.out_dir).bundle(entry, output)
                    if self.options.get('minify', False):
                        bundle_path.write_text(
                            self._minify_generated_js(bundle_path.read_text(encoding='utf-8')),
                            encoding='utf-8',
                        )
                bundle_path = self._finalize_bundle_path(bundle_path)
                results['bundle'] = bundle_path.relative_to(self.out_dir).as_posix()
                self._map_bundle_entry(results, entry, results['bundle'])
                results['files'].append({
                    'input': str(entry),
                    'output': results['bundle'],
                    'size': bundle_path.stat().st_size,
                })
                results['total_bytes'] += bundle_path.stat().st_size
                if self.max_asset_size and bundle_path.stat().st_size > self.max_asset_size:
                    results['size_warnings'].append({
                        'output': results['bundle'],
                        'size': bundle_path.stat().st_size,
                        'limit': self.max_asset_size,
                        'message': f"Generated asset exceeds {self.max_asset_size} bytes",
                    })
            except Exception as error:
                results['failed'] += 1
                results['errors'].append({'file': str(entry), 'error': str(error)})

        # Write the host entrypoint after the final asset map is known. This
        # is what makes a template reference the hashed component or bundle,
        # and it also injects extracted component stylesheets exactly once.
        if self.options.get('dev', False) or (self.root_dir / 'templates' / 'index.html').exists():
            self._write_dev_entrypoint()

        # Generate the manifest after assets and optional bundling are complete.
        manifest = self.manifest.generate(results, self.out_dir)
        self.writer.write_json(self.out_dir / 'manifest.json', manifest)
        report_path = self.options.get('report')
        if report_path:
            report = {
                'mode': ('development' if self.options.get('dev', False)
                         else 'static' if self.options.get('static', False)
                         else 'production'),
                'duration_seconds': round(time.time() - start_time, 4),
                'total_bytes': results['total_bytes'],
                'asset_bytes': results.get('asset_bytes', 0),
                'files': results['files'],
                'asset_files': results.get('asset_files', []),
                'assets_copied': results.get('assets_copied', 0),
                'size_warnings': results['size_warnings'],
            }
            report_target = Path(report_path)
            if not report_target.is_absolute():
                report_target = self.out_dir / report_target
            self.writer.write_json(report_target, report)
            results['report'] = report_target.relative_to(self.out_dir).as_posix() if report_target.is_relative_to(self.out_dir) else str(report_target)
        
        results['duration'] = time.time() - start_time
        self.stats = results
        
        return results

    def _load_build_cache(self) -> Dict[str, Dict[str, Any]]:
        """Read prior component metadata for safe incremental development builds."""
        if not self.out_dir or self.clean_output:
            return {}
        manifest_path = self.out_dir / 'manifest.json'
        try:
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return {}
        if manifest.get('build_signature') != self.compiler_signature:
            return {}
        cache: Dict[str, Dict[str, Any]] = {}
        for item in manifest.get('files', []):
            input_name = item.get('input')
            output_name = str(item.get('output', ''))
            if not input_name or not str(input_name).endswith('.vel'):
                continue
            # SSR emits a second record for the same input; the JavaScript
            # record is the cache authority for incremental compilation.
            if input_name not in cache or output_name.endswith('.js'):
                cache[input_name] = item
        return cache

    def _compiler_signature(self) -> str:
        """Return a stable fingerprint for code and options used by this build.

        Incremental output is only safe when the compiler, build orchestration,
        runtime helpers, and output-affecting options are unchanged.  The old
        fingerprint only covered two Python modules, so an editable install
        could silently serve stale output after a builder/runtime change.
        """
        sources = [
            Path(inspect.getfile(Compiler)),
            Path(inspect.getfile(Generator)),
            Path(inspect.getfile(Builder)),
            Path(inspect.getfile(AssetManager)),
            Path(inspect.getfile(ManifestGenerator)),
        ]
        digest = hashlib.sha256()
        for source in sources:
            try:
                digest.update(source.resolve().read_bytes())
            except OSError:
                digest.update(str(source).encode('utf-8'))
        # Shared runtime modules are package data rather than Python source;
        # include them so an editable runtime fix invalidates component cache
        # entries on the next development build.
        try:
            runtime_package = package_files("teloce.runtime")
            for runtime_name in ("scheduler.js", "signals.js", "compiled.js"):
                digest.update(runtime_name.encode("utf-8"))
                digest.update(runtime_package.joinpath(runtime_name).read_bytes())
        except OSError:
            digest.update(b"runtime-unavailable")
        try:
            digest.update(Path(inspect.getfile(minify_js)).read_bytes())
        except OSError:
            digest.update(b"minifier-unavailable")

        # Options such as minification, hashing, source maps, and plugin
        # configuration change generated output.  Registries may contain
        # arbitrary objects, so represent those by stable type names rather
        # than memory-address-bearing repr() values.
        def serializable(value: Any) -> Any:
            if isinstance(value, dict):
                return {str(key): serializable(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
            if isinstance(value, set):
                return [serializable(item) for item in sorted(value, key=str)]
            if isinstance(value, (list, tuple)):
                return [serializable(item) for item in value]
            try:
                json.dumps(value)
            except (TypeError, ValueError):
                return f"<{type(value).__module__}.{type(value).__qualname__}>"
            return value

        digest.update(json.dumps(serializable(self.options), sort_keys=True, separators=(",", ":")).encode("utf-8"))
        return digest.hexdigest()

    def _shared_runtime_path(self) -> Path:
        """Return the public runtime path associated with the configured source tree."""
        static_dir = Path(str(self.options.get("static_dir", "static")))
        if static_dir.is_absolute() or ".." in static_dir.parts:
            raise ValueError("static_dir must be a relative path inside the build output")
        filename = "teloce-runtime.js"
        if self.hash_assets:
            digest = hashlib.sha256(self._shared_runtime_source().encode("utf-8")).hexdigest()[:8]
            filename = f"teloce-runtime.{digest}.js"
        return self.out_dir / static_dir / filename

    def _shared_runtime_source(self) -> str:
        """Build the single runtime barrel emitted for generated modules."""
        runtime_package = package_files("teloce.runtime")
        compiled_runtime = runtime_package.joinpath("compiled.js").read_text(encoding="utf-8")
        runtime_source = (
            "// Shared Teloce runtime helpers generated by Teloce-Py\n"
            + SAFE_EXPRESSION_RUNTIME
            + SHARED_DOM_RUNTIME
            + compiled_runtime
            # These helpers are intentionally exported from the barrel so
            # every generated component imports the same module instance.
            + '\nexport { __safeEvaluate, __runEventExpression, __setSafePath };\n'
            + 'export { createSignal, createComputed, createEffect, createMemo, batch, untracked, isSignal, isComputed, toSignal, getValue } from "./signals.js";\n'
            + 'export { createSignal as signal, createComputed as computed, createEffect as effect } from "./signals.js";\n'
        )
        return self._minify_generated_js(runtime_source) if self.options.get("minify", False) else runtime_source

    @staticmethod
    def _minify_generated_js(source: str) -> str:
        """Compact compiler-owned JavaScript without altering literals."""
        return minify_js(source)

    @staticmethod
    def _minify_generated_css(source: str) -> str:
        """Compact extracted component CSS without changing quoted values."""
        return minify_css(source)

    def _rewrite_generated_asset_map(self, results: Dict[str, Any]) -> None:
        """Add generated hashed outputs to the public asset map."""
        for file_info in results.get('files', []):
            input_name = str(file_info.get('input', ''))
            output_name = str(file_info.get('output', ''))
            if input_name.endswith('.vel') and output_name:
                self.assets.asset_map[input_name[:-4] + '.js'] = output_name
                css_output = output_name[:-3] + '.css'
                if (self.out_dir / css_output).exists():
                    self.assets.asset_map[css_output] = css_output
        results['asset_map'] = dict(self.assets.asset_map)

    def _rewrite_generated_references(self, results: Dict[str, Any]) -> None:
        """Rewrite generated module/CSS references to hashed static assets.

        Hashing copied JavaScript/CSS is only safe when imports and ``url()``
        references are updated as well.  Generated `.vel` modules are the
        only files that can reliably be rewritten without parsing arbitrary
        application JavaScript, so source-module references are handled here
        and page references are handled by ``_write_dev_entrypoint``.
        """
        if not self.hash_assets or not self.root_dir or not self.out_dir:
            return
        mappings = list(self.assets.asset_map.items())
        generated = [
            file_info for file_info in results.get('files', [])
            if str(file_info.get('input', '')).endswith('.vel')
            and str(file_info.get('output', '')).endswith('.js')
        ]
        for file_info in generated:
            output = self.out_dir / str(file_info['output'])
            if not output.is_file():
                continue
            content = output.read_text(encoding='utf-8')
            for source_name, target_name in mappings:
                source_path = self.out_dir / source_name
                target_path = self.out_dir / target_name
                if not target_path.exists() or source_name == target_name:
                    continue
                original = Path(os.path.relpath(source_path, output.parent)).as_posix()
                replacement = Path(os.path.relpath(target_path, output.parent)).as_posix()
                if not original.startswith('.'):
                    original = './' + original
                if not replacement.startswith('.'):
                    replacement = './' + replacement
                for quote in ('"', "'"):
                    content = content.replace(f'{quote}{original}{quote}', f'{quote}{replacement}{quote}')
            output.write_text(content, encoding='utf-8')
            file_info['size'] = output.stat().st_size

        # CSS url() references may point at images/fonts that were hashed by
        # AssetManager.  Use a relative replacement from each stylesheet.
        for css in self.out_dir.rglob('*.css'):
            content = css.read_text(encoding='utf-8')
            for source_name, target_name in mappings:
                source_path = self.out_dir / source_name
                target_path = self.out_dir / target_name
                if not target_path.exists() or source_name == target_name:
                    continue
                original = Path(os.path.relpath(source_path, css.parent)).as_posix()
                replacement = Path(os.path.relpath(target_path, css.parent)).as_posix()
                content = content.replace(f'url({original})', f'url({replacement})')
                content = content.replace(f'url("{original}")', f'url("{replacement}")')
                content = content.replace(f"url('{original}')", f"url('{replacement}')")
            css.write_text(content, encoding='utf-8')

    def _finalize_bundle_path(self, bundle_path: Path) -> Path:
        """Apply the production content hash to a single-file bundle.

        Esbuild handles hashes itself when splitting is enabled. The built-in
        dependency bundler, and esbuild's single-file mode, both produce one
        file that can safely be renamed after generation because it contains
        no relative chunk imports.
        """
        bundle_path = Path(bundle_path)
        if not self.hash_assets or not bundle_path.is_file():
            return bundle_path
        if re.search(r"\.[0-9a-f]{8}(?:-[0-9a-f]+)?\.js$", bundle_path.name):
            return bundle_path
        digest = hashlib.sha256(bundle_path.read_bytes()).hexdigest()[:8]
        hashed = bundle_path.with_name(f"{bundle_path.stem}.{digest}{bundle_path.suffix}")
        if hashed != bundle_path:
            if hashed.exists():
                hashed.unlink()
            bundle_path.replace(hashed)
        return hashed

    def _map_bundle_entry(self, results: Dict[str, Any], entry: str | Path,
                          bundle_output: str) -> None:
        """Point the public source entry at the final bundle when possible."""
        if not self.out_dir:
            return
        entry_path = Path(entry)
        if not entry_path.is_absolute():
            entry_path = self.out_dir / entry_path
        try:
            entry_name = entry_path.resolve().relative_to(self.out_dir.resolve()).as_posix()
        except ValueError:
            return
        asset_map = dict(self.assets.asset_map)
        for source_name, output_name in list(asset_map.items()):
            if output_name == entry_name or source_name == entry_name:
                asset_map[source_name] = bundle_output
        asset_map[entry_name] = bundle_output
        self.assets.asset_map = asset_map
        results['asset_map'] = asset_map
        # A stable logical alias is kept for framework templates that are
        # rendered by Flask/Django/FastAPI rather than by dist/index.html.
        for source_name, output_name in asset_map.items():
            if not source_name.endswith('.js') or output_name != bundle_output:
                continue
            alias = self.out_dir / source_name
            target = self.out_dir / output_name
            if alias == target or not target.is_file():
                continue
            relative = Path(os.path.relpath(target, alias.parent)).as_posix()
            if not relative.startswith('.'):
                relative = './' + relative
            alias.write_text(
                f'export * from "{relative}"; export {{ default }} from "{relative}";\n',
                encoding='utf-8',
            )

    def _write_hashed_aliases(self, results: Dict[str, Any]) -> None:
        """Emit stable logical module shims for hashed production outputs."""
        if not self.hash_assets or not self.out_dir:
            results['asset_aliases'] = []
            return
        aliases = []
        for file_info in results.get('files', []):
            input_name = str(file_info.get('input', ''))
            output_name = str(file_info.get('output', ''))
            if not input_name.endswith('.vel') or not output_name.endswith('.js'):
                continue
            logical_name = input_name[:-4] + '.js'
            if logical_name == output_name:
                continue
            alias = self.out_dir / logical_name
            target = self.out_dir / output_name
            if not target.is_file():
                continue
            relative = Path(os.path.relpath(target, alias.parent)).as_posix()
            if not relative.startswith('.'):
                relative = './' + relative
            content = f'export * from "{relative}"; export {{ default }} from "{relative}";\n'
            if self.options.get('minify', False):
                content = self._minify_generated_js(content)
            alias.parent.mkdir(parents=True, exist_ok=True)
            alias.write_text(content, encoding='utf-8')
            size = alias.stat().st_size
            aliases.append({'output': logical_name, 'target': output_name, 'size': size})
        results['asset_aliases'] = aliases

    def _resolve_bundle_entry(self, entry: str | Path) -> Path:
        """Resolve a logical or hashed bundle entry to an output file."""
        if not self.out_dir:
            return Path(entry)
        candidate = Path(entry)
        if not candidate.is_absolute():
            candidate = self.out_dir / candidate
        if candidate.is_file():
            return candidate
        try:
            logical_name = candidate.relative_to(self.out_dir).as_posix()
        except ValueError:
            logical_name = candidate.as_posix()
        mapped = self.assets.asset_map.get(logical_name)
        if mapped:
            mapped_path = self.out_dir / mapped
            if mapped_path.is_file():
                return mapped_path
        if candidate.suffix == '.js':
            candidates = sorted(candidate.parent.glob(f'{candidate.stem}.*.js'))
            if len(candidates) == 1:
                return candidates[0]
        return candidate

    def _generated_css_outputs(self) -> List[str]:
        """Return generated stylesheet paths for the build entrypoint."""
        if not self.out_dir:
            return []
        return sorted(
            path.relative_to(self.out_dir).as_posix()
            for path in self.out_dir.rglob('*.css')
            if path.is_file() and path.name != 'styles.css'
        )

    def _write_dev_entrypoint(self) -> None:
        """Create a framework-neutral entrypoint with rewritten assets."""
        template = self.root_dir / 'templates' / 'index.html'
        if not template.exists():
            return
        html = template.read_text(encoding='utf-8')
        # Resolve the static URL forms emitted by the Flask, Django, and
        # FastAPI scaffolds. Unknown server-side template syntax is preserved.
        html = re.sub(r"\{\{\s*url_for\(['\"]static['\"],\s*filename=['\"]([^'\"]+)['\"]\)\s*\}\}", r"/static/\1", html)
        html = re.sub(r"\{\%\s*static\s+['\"]([^'\"]+)['\"]\s*\%\}", r"/static/\1", html)
        html = re.sub(r"\{\{\s*url_for\(['\"]static['\"],\s*path=['\"]([^'\"]+)['\"]\)\s*\}\}", r"/static/\1", html)
        for source_name, output_name in sorted(self.assets.asset_map.items(), key=lambda item: len(item[0]), reverse=True):
            html = html.replace(f"/{source_name}", f"/{output_name}")
            html = html.replace(f"'{source_name}'", f"'{output_name}'").replace(f'"{source_name}"', f'"{output_name}"')
        if self.extract_css:
            links = []
            for css_path in self._generated_css_outputs():
                href = f'/{css_path}'
                if href not in html and f'"{css_path}"' not in html and f"'{css_path}'" not in html:
                    links.append(f'<link rel="stylesheet" href="{href}">')
            if links:
                injection = "\n".join(links)
                if re.search(r'</head\s*>', html, re.I):
                    html = re.sub(r'</head\s*>', injection + '\n</head>', html, count=1, flags=re.I)
                else:
                    html = injection + '\n' + html
        self.writer.write_html(self.out_dir / 'index.html', html)

    def _clean_generated_output(self) -> None:
        """Remove only the explicitly configured generated output directory."""
        root = self.root_dir.resolve()
        output = self.out_dir.resolve()
        if output in {root, root.parent}:
            raise ValueError("Refusing to clean a project root or its parent")
        if output.exists():
            shutil.rmtree(output)
    
    def _compile_file(self, vel_file: Path) -> Dict[str, Any]:
        """Compile a single .vel file."""
        source = vel_file.read_text(encoding='utf-8')
        output_path = self._output_path(vel_file)
        component_imports = self._resolve_component_imports(vel_file, source)
        compiler_options = dict(self.options)
        compiler_options["component_imports"] = component_imports
        compiler_options["inline_css"] = not self.extract_css
        if self.options.get('shared_runtime'):
            runtime_path = self._shared_runtime_path()
            compiler_options['shared_runtime_import'] = Path(os.path.relpath(runtime_path, output_path.parent)).as_posix()
            if not compiler_options['shared_runtime_import'].startswith('.'):
                compiler_options['shared_runtime_import'] = './' + compiler_options['shared_runtime_import']
        result = Compiler(compiler_options).compile(source, str(vel_file))
        
        if not result['success']:
            raise Exception(result['diagnostics']['errors'])
        
        # Write output
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        code = result['code']
        if self.options.get('minify', False):
            code = self._minify_generated_js(code)
        if result.get('map'):
            result['map']['file'] = output_path.name
            result['map']['sources'] = [vel_file.relative_to(self.root_dir).as_posix()]
            code += f"\n//# sourceMappingURL={output_path.name}.map"
        self.writer.write_js(output_path, code)

        if result.get('map'):
            self.writer.write_json(output_path.with_suffix('.js.map'), result['map'])
        
        # Write CSS
        if result.get('css'):
            css_path = output_path.with_suffix('.css')
            css = self._minify_generated_css(result['css']) if self.options.get('minify', False) else result['css']
            self.writer.write_css(css_path, css)
        
        return {
            'output': output_path.relative_to(self.out_dir).as_posix(),
            'size': output_path.stat().st_size,
            'source_hash': hashlib.sha256(source.encode('utf-8')).hexdigest(),
            'result': result,
        }

    def _write_ssr_file(self, vel_file: Path, source: str) -> str:
        """Emit a Jinax template artifact for a component template."""
        match = re.search(r'<template(?:\s[^>]*)?>([\s\S]*?)</template\s*>', source, re.I)
        if not match:
            raise ValueError(f"Cannot generate SSR output without a template: {vel_file}")
        output_path = self._output_path(vel_file).with_suffix('.html')
        self.writer.write_html(output_path, to_jinax_template(match.group(1).strip()))
        return output_path.relative_to(self.out_dir).as_posix()

    def _resolve_component_imports(self, vel_file: Path, source: str) -> Dict[str, str]:
        """Resolve local `.vel` imports to paths in the build output."""
        resolved: Dict[str, str] = {}
        script_match = re.search(r'<script(?:\s[^>]*)?>([\s\S]*?)</script\s*>', source, re.I)
        source = script_match.group(1) if script_match else source
        output_path = self._output_path(vel_file)
        pattern = re.compile(r'(?m)^\s*import\s+([A-Za-z_$][\w$]*)(?:\s*,\s*\{[^}]*\})?\s+from\s+[\'\"]([^\'\"]+\.vel)[\'\"]\s*;?')
        for match in pattern.finditer(source):
            name, import_path = match.groups()
            if not import_path.startswith('.'):
                continue
            requested = (vel_file.parent / import_path).resolve()
            candidates = [requested]
            if requested.suffix == '':
                candidates.extend([requested.with_suffix('.vel'), requested / 'index.vel'])
            elif requested.suffix != '.vel':
                candidates.append(requested.with_suffix('.vel'))
            child = next((candidate for candidate in candidates if candidate.is_file()), None)
            if child is None:
                raise FileNotFoundError(f"Component import not found: {import_path} in {vel_file}")
            child_output = self._output_path(child)
            specifier = Path(os.path.relpath(child_output, output_path.parent)).as_posix()
            if not specifier.startswith('.'):
                specifier = './' + specifier
            resolved[name] = specifier
        named_pattern = re.compile(r'(?m)^\s*import\s*\{([^}]+)\}\s*from\s+[\'\"]([^\'\"]+\.vel)[\'\"]\s*;?')
        for match in named_pattern.finditer(source):
            import_path = match.group(2)
            requested = (vel_file.parent / import_path).resolve()
            candidates = [requested]
            if requested.suffix == '':
                candidates.extend([requested.with_suffix('.vel'), requested / 'index.vel'])
            elif requested.suffix != '.vel':
                candidates.append(requested.with_suffix('.vel'))
            child = next((candidate for candidate in candidates if candidate.is_file()), None)
            if child is None:
                raise FileNotFoundError(f"Component import not found: {import_path} in {vel_file}")
            child_output = self._output_path(child)
            specifier = Path(os.path.relpath(child_output, output_path.parent)).as_posix()
            if not specifier.startswith('.'):
                specifier = './' + specifier
            for item in match.group(1).split(','):
                parts = re.split(r'\s+as\s+', item.strip())
                name = parts[-1].strip()
                if name:
                    resolved[name] = specifier
        return resolved

    def _build_dependency_graph(self, vel_files: List[Path]) -> None:
        """Build a stable graph of relative `.vel` component imports."""
        self.dependency_graph.clear()
        known = {path.resolve(): path.relative_to(self.root_dir).as_posix() for path in vel_files}
        pattern = re.compile(r'(?m)^\s*import\s+(?:[A-Za-z_$][\w$]*(?:\s*,\s*\{[^}]+\})?|\{[^}]+\}|\*\s+as\s+[A-Za-z_$][\w$]*)\s+from\s+[\'\"]([^\'\"]+)[\'\"]\s*;?')
        for vel_file in vel_files:
            component = vel_file.relative_to(self.root_dir).as_posix()
            self.dependency_graph.add_component(component)
            source = vel_file.read_text(encoding='utf-8')
            script_match = re.search(r'<script(?:\s[^>]*)?>([\s\S]*?)</script\s*>', source, re.I)
            source = script_match.group(1) if script_match else source
            for import_path in pattern.findall(source):
                if not import_path.startswith('.'):
                    continue
                requested = (vel_file.parent / import_path).resolve()
                candidates = [requested]
                if requested.suffix == '':
                    candidates.extend([requested.with_suffix('.vel'), requested / 'index.vel'])
                child = next((candidate for candidate in candidates if candidate in known), None)
                if child is not None:
                    self.dependency_graph.add_dependency(component, known[child])

    def _output_path(self, vel_file: Path) -> Path:
        """Return a stable or content-hashed output path for a component."""
        relative = vel_file.relative_to(self.root_dir)
        if not self.hash_assets:
            return (self.out_dir / relative).with_suffix('.js')
        digest = hashlib.sha256(vel_file.read_bytes()).hexdigest()[:8]
        return self.out_dir / relative.parent / f"{relative.stem}.{digest}.js"
    
    def get_stats(self) -> Dict[str, Any]:
        """Get build statistics."""
        return self.stats
    
    def clean(self) -> None:
        """Clean the build directory."""
        if self.out_dir and self.out_dir.exists():
            import shutil
            shutil.rmtree(self.out_dir)
