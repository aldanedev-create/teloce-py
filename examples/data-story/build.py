from pathlib import Path

from teloce.build import build_project


ROOT = Path(__file__).resolve().parent


if __name__ == "__main__":
    result = build_project(
        ROOT,
        out_dir=ROOT / "dist",
        options={
            "dev": True,
            "clean": True,
            "source_maps": True,
            "shared_runtime": True,
            "css_bundle": True,
        },
    )
    if result["failed"]:
        raise SystemExit(f"Build failed: {result['errors']}")
    print(f"Compiled {result['compiled']} .vel component(s)")
