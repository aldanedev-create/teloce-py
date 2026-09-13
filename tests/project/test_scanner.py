"""Project scanner determinism and pattern handling tests."""

from pathlib import Path

from teloce.project.scanner import ProjectScanner


def test_scan_returns_stable_posix_order_and_ignores_generated_directories(tmp_path: Path):
    (tmp_path / "z.vel").write_text("", encoding="utf-8")
    (tmp_path / "a" / "app.vel").parent.mkdir()
    (tmp_path / "a" / "app.vel").write_text("", encoding="utf-8")
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "old.vel").write_text("", encoding="utf-8")

    paths = ProjectScanner().scan(tmp_path)

    assert [path.relative_to(tmp_path).as_posix() for path in paths] == [
        "a/app.vel",
        "z.vel",
    ]


def test_scan_with_overlapping_patterns_deduplicates_and_relative_paths_are_portable(tmp_path: Path):
    (tmp_path / "pages").mkdir()
    (tmp_path / "pages" / "home.vel").write_text("", encoding="utf-8")
    scanner = ProjectScanner()

    scanner.scan_with_patterns(tmp_path, include=["**/*.vel", "pages/*.vel"])

    assert scanner.get_relative_paths(tmp_path) == ["pages/home.vel"]
