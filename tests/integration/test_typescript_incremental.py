"""`.ts` modules take part in incremental builds and the parallel pool."""

import hashlib
from pathlib import Path

from teloce.build import Builder


def _project(root: Path, vel_count: int = 6, ts_count: int = 4) -> Path:
    js = root / "static" / "js"
    js.mkdir(parents=True)
    for i in range(vel_count):
        (js / f"C{i}.vel").write_text(
            f'<template><div>{i}</div></template>\n<script>export default {{}};</script>\n'
        )
    for i in range(ts_count):
        (js / f"m{i}.ts").write_text(f"export const v{i}: number = {i};\n")
    return root


def _opts(**extra):
    return {"incremental": True, "clean": False, "spa": False, **extra}


def _build(root: Path, **extra):
    return Builder(_opts(**extra)).build(root, root / "dist")


def _tree_hash(out: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(out.rglob("*")):
        if path.is_file() and path.name != "manifest.json":
            digest.update(str(path.relative_to(out)).encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def test_unchanged_ts_files_are_cache_hits(tmp_path):
    root = _project(tmp_path)
    first = _build(root)
    assert first["compiled"] == 10 and first["cache_hits"] == 0
    second = _build(root)
    assert second["compiled"] == 0 and second["cache_hits"] == 10
    assert second["failed"] == 0
    assert (root / "dist" / "static" / "js" / "m0.js").is_file()


def test_editing_one_ts_file_recompiles_only_that_file(tmp_path):
    root = _project(tmp_path)
    _build(root)
    target = root / "static" / "js" / "m2.ts"
    target.write_text("export const v2: string = 'edited';\n")
    result = _build(root)
    assert result["compiled"] == 1 and result["cache_hits"] == 9
    assert "'edited'" in (root / "dist" / "static" / "js" / "m2.js").read_text()


def test_missing_ts_output_is_rebuilt_even_if_source_unchanged(tmp_path):
    root = _project(tmp_path)
    _build(root)
    (root / "dist" / "static" / "js" / "m1.js").unlink()
    result = _build(root)
    assert result["compiled"] == 1
    assert (root / "dist" / "static" / "js" / "m1.js").is_file()


def test_ts_cache_not_used_without_incremental(tmp_path):
    root = _project(tmp_path)
    _build(root)
    result = _build(root, incremental=False)
    assert result["compiled"] == 10 and result["cache_hits"] == 0


def test_ts_in_the_pool_matches_sequential_output(tmp_path):
    seq_root = _project(tmp_path / "seq", vel_count=20, ts_count=20)
    par_root = _project(tmp_path / "par", vel_count=20, ts_count=20)
    seq = Builder({"clean": True, "spa": False, "jobs": 1}).build(seq_root, seq_root / "dist")
    par = Builder({"clean": True, "spa": False, "jobs": 2, "parallel_min_files": 1}).build(
        par_root, par_root / "dist")
    assert seq["failed"] == par["failed"] == 0 and seq["compiled"] == par["compiled"] == 40
    assert [f["input"] for f in seq["files"]] == [f["input"] for f in par["files"]]
    assert _tree_hash(seq_root / "dist") == _tree_hash(par_root / "dist")


def test_broken_ts_is_reported_and_never_cached_as_success(tmp_path):
    root = _project(tmp_path)
    bad = root / "static" / "js" / "m0.ts"
    bad.write_text("enum E { A }\n")                      # unsupported -> clear error
    first = _build(root, jobs=2, parallel_min_files=1)
    assert first["failed"] == 1 and "enum" in first["errors"][0]["error"]
    assert first["compiled"] == 9
    again = _build(root, jobs=2, parallel_min_files=1)
    assert again["failed"] == 1                           # still failing, not a stale hit
    assert again["cache_hits"] == 9
    bad.write_text("export const fixed: number = 1;\n")
    healed = _build(root)
    assert healed["failed"] == 0 and healed["compiled"] == 1


def test_ts_does_not_leak_into_component_logic(tmp_path):
    """Widening the cache loader to .ts must not make .ts count as a component."""
    root = _project(tmp_path)
    result = _build(root)
    assert sorted(result["components"]) == [f"C{i}" for i in range(6)]


def test_changing_jobs_does_not_invalidate_the_incremental_cache(tmp_path):
    root = _project(tmp_path)
    _build(root, jobs=1)
    result = _build(root, jobs=4, parallel_min_files=1)
    assert result["compiled"] == 0 and result["cache_hits"] == 10
    result = _build(root)                                   # jobs option removed entirely
    assert result["compiled"] == 0 and result["cache_hits"] == 10
