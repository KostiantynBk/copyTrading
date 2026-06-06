from __future__ import annotations

import json
from pathlib import Path

from .models import AnalysisRecord, CacheState, SignalReport


def ensure_directories(cache_path: Path, reports_dir: Path, analyses_path: Path) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    analyses_path.parent.mkdir(parents=True, exist_ok=True)


def load_cache(cache_path: Path) -> CacheState:
    if not cache_path.exists():
        return CacheState()
    raw = json.loads(cache_path.read_text(encoding="utf-8"))
    return CacheState.model_validate(raw)


def save_cache(cache_path: Path, cache: CacheState) -> None:
    cache_path.write_text(
        json.dumps(cache.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )


def write_report(reports_dir: Path, report: SignalReport) -> Path:
    filename = (
        f"{report.generated_at.strftime('%Y%m%dT%H%M%S')}"
        f"_{report.source_post.handle}_{report.source_post.post_id}.json"
    )
    path = reports_dir / filename
    path.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )
    return path


def append_analysis_record(analyses_path: Path, record: AnalysisRecord) -> None:
    with analyses_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record.model_dump(mode="json")))
        fh.write("\n")
