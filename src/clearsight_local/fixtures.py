from __future__ import annotations

from pathlib import Path

from clearsight_local.models import FixtureSet, project_root


def fixture_path() -> Path:
    return project_root() / "fixtures" / "requests.json"


def load_fixtures(path: Path | None = None) -> FixtureSet:
    return FixtureSet.model_validate_json((path or fixture_path()).read_text(encoding="utf-8"))

