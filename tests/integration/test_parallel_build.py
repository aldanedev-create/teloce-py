"""Parallel (`jobs`) builds must be indistinguishable from sequential builds."""

import hashlib
from pathlib import Path

import pytest

import teloce.build.builder as builder_module
from teloce.build import Builder


def _component(i: int) -> str:
    return (
        f'<template><div class="c{i}">{{{{ v }}}}</div></template>\n'
        f'<script>export default {{ data() {{ return {{ v: {i} }}; }} }};</script>\n'
        f'<style scoped>.c{i} {{ color: red; }}</style>\n'
    )


def _project(root: Path, count: int = 24, broken: tuple[int, ...] = ()) -> Path:
    js = root / "static" / "js"
    js.mkdir(parents=True)
    for i in range(count):
        text = "<template><div>{{ }}</template><script>export default {</script>" if i in broken else _component(i)
        (js / f"C{i}.vel").write_text(text)
    return root


def _tree_hash(out: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(out.rglob("*")):
        if path.is_file() and path.name != "manifest.json":  # manifest holds timings
            digest.update(str(path.relative_to(out)).encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def _build(root: Path, **options):
    out = root / "dist"
    result = Builder({"clean": True, "spa": False, **options}).build(root, out)
    return result, out


def test_parallel_output_is_identical_to_sequential(tmp_path):
    root = _project(tmp_path)
    seq, seq_out = _build(root, jobs=1)
    par, par_out = _build(root, jobs=2, parallel_min_files=1)
    assert seq["failed"] == par["failed"] == 0
    assert [f["input"] for f in seq["files"]] == [f["input"] for f in par["files"]]
    assert _tree_hash(seq_out) == _tree_hash(par_out)


def test_parallel_reports_the_same_errors_and_still_builds_the_rest(tmp_path):
    root = _project(tmp_path, count=24, broken=(3, 11))
    seq, _ = _build(root, jobs=1)
    par, _ = _build(root, jobs=2, parallel_min_files=1)
    names = lambda r: sorted((Path(e["file"]).name, e["error"]) for e in r["errors"])
    assert seq["failed"] == par["failed"] == 2
    assert names(seq) == names(par)
    assert par["compiled"] == seq["compiled"] == 22


def test_parallel_cooperates_with_incremental_builds(tmp_path):
    root = _project(tmp_path, count=24)
    options = {"jobs": 2, "parallel_min_files": 1, "incremental": True, "clean": False, "spa": False}

    def run():
        return Builder(options).build(root, root / "dist")

    assert run()["compiled"] == 24
    again = run()
    assert again["compiled"] == 0 and again["cache_hits"] == 24
    target = root / "static" / "js" / "C7.vel"
    target.write_text(target.read_text() + "\n<!-- edited -->\n")
    edited = run()
    assert edited["compiled"] == 1 and edited["cache_hits"] == 23


def test_broken_process_pool_falls_back_to_sequential(tmp_path, monkeypatch):
    class Unavailable:
        def __init__(self, *args, **kwargs):
            raise OSError("process pool unavailable")

    monkeypatch.setattr(builder_module, "ProcessPoolExecutor", Unavailable)
    result, out = _build(_project(tmp_path), jobs=4, parallel_min_files=1)
    assert result["compiled"] == 24 and result["failed"] == 0
    assert (out / "static" / "js" / "C0.js").is_file()


@pytest.mark.parametrize("jobs, expected", [(1, 1), (None, 1), ("auto", None), (0, None), ("bad", 1)])
def test_job_count_resolution(jobs, expected):
    import os
    resolved = Builder({"jobs": jobs, "parallel_min_files": 1})._resolve_jobs(10_000)
    assert resolved == (expected if expected is not None else (os.cpu_count() or 1))


def test_small_builds_do_not_start_a_pool(tmp_path, monkeypatch):
    started = []

    class Spy(builder_module.ProcessPoolExecutor):
        def __init__(self, *args, **kwargs):
            started.append(1)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(builder_module, "ProcessPoolExecutor", Spy)
    _build(_project(tmp_path, count=10), jobs=4)          # below default threshold of 32
    assert started == []
