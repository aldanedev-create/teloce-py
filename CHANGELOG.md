# Changelog

All notable changes to Teloce-Py will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Added
- First-class MinifyJS production minifier and bundler, installed as a Python dependency.
- Native split bundles, hashed outputs, original .vel source map composition, metadata and build reporting.
- Adapter and bundler APIs, backend configuration, production browser tests and Node esbuild parity checks.
- Initial project setup
- .vel file parser (SFC)
- Template lexer and parser
- AST nodes for template elements
- Directive system (@click, :model, <for>, <if>)
- JavaScript code generator
- Scoped CSS support
- Component resolution
- Development server with auto-compilation
- CLI commands: dev, build, watch, debug, create
- Python web framework integration (Flask, Flaxon, Django, FastAPI)
- Human-friendly error messages
- Source map support
- Comprehensive test suite

### Changed
- N/A

### Deprecated
- N/A

### Removed
- N/A

### Fixed
- Authored import/export and lazy-import paths now resolve hashed copied assets.
- `jobs=0` correctly selects automatic worker count instead of matching `False`.

### Security
- N/A

---

## [0.1.0] - 2024-XX-XX

### Added
- Initial alpha release
- Basic .vel → JavaScript compilation
- Template interpolation ({{ }})
- Event handling (@click)
- Two-way binding (:model)
- Conditional rendering (<if>)
- Loop rendering (<for>)
- Component system
- Scoped CSS
- Python package structure
- Documentation