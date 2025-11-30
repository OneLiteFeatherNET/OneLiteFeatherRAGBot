#!/usr/bin/env python3
import sys
from pathlib import Path

def bump_pyproject(version: str) -> None:
    try:
        import tomlkit  # type: ignore
    except Exception as e:
        print("tomlkit not available; please install tomlkit", file=sys.stderr)
        raise

    p = Path("pyproject.toml")
    if not p.exists():
        return
    data = tomlkit.parse(p.read_text(encoding="utf-8"))
    if "project" in data and isinstance(data["project"], dict):
        data["project"]["version"] = version
    p.write_text(tomlkit.dumps(data), encoding="utf-8")

def bump_chart_yaml(version: str) -> None:
    try:
        import yaml  # type: ignore
    except Exception as e:
        print("pyyaml not available; please install pyyaml", file=sys.stderr)
        raise

    chart = Path("charts/discord-rag-bot/Chart.yaml")
    if not chart.exists():
        return
    data = yaml.safe_load(chart.read_text(encoding="utf-8")) or {}
    data["version"] = str(version)
    data["appVersion"] = str(version)
    chart.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: bump_version.py <version>", file=sys.stderr)
        return 2
    version = sys.argv[1]
    bump_pyproject(version)
    bump_chart_yaml(version)
    print(f"Bumped versions to {version}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

