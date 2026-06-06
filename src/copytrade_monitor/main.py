from __future__ import annotations

import argparse
import time
from datetime import UTC, datetime

from .ai_analyzer import AIAnalyzer
from .config import load_profiles, load_settings
from .correlation import build_report
from .models import AnalysisRecord
from .reporter import render_terminal_report
from .storage import append_analysis_record, ensure_directories, load_cache, save_cache, write_report
from .models import SignalRecord
from .x_monitor import XMonitor


def main() -> None:
    parser = argparse.ArgumentParser(description="Monitor X profiles for trade signals.")
    parser.add_argument("command", choices=["login", "run"])
    args = parser.parse_args()

    if args.command == "login":
        settings = load_settings(require_api_key=False)
        ensure_directories(settings.cache_path, settings.reports_dir, settings.analyses_path)
        monitor = XMonitor(
            storage_state_path=str(settings.x_storage_state_path),
            headless=False,
            browser_channel=settings.x_browser_channel,
            navigation_timeout_ms=settings.x_navigation_timeout_ms,
            post_load_wait_ms=settings.x_post_load_wait_ms,
            debug=settings.x_debug,
        )
        monitor.login()
        return

    settings = load_settings()
    ensure_directories(settings.cache_path, settings.reports_dir, settings.analyses_path)

    monitor = XMonitor(
        storage_state_path=str(settings.x_storage_state_path),
        headless=settings.headless,
        browser_channel=settings.x_browser_channel,
        navigation_timeout_ms=settings.x_navigation_timeout_ms,
        post_load_wait_ms=settings.x_post_load_wait_ms,
        debug=settings.x_debug,
    )

    if not settings.profiles_path.exists():
        raise FileNotFoundError(
            f"Missing profiles file at {settings.profiles_path}. Copy profiles.example.json to profiles.json first."
        )

    profiles = load_profiles(settings.profiles_path)
    analyzer = AIAnalyzer(settings.openai_api_key, settings.openai_model)

    while True:
        cache = load_cache(settings.cache_path)
        seen_post_ids = set(cache.seen_post_ids)
        try:
            new_posts = monitor.fetch_new_posts(profiles, seen_post_ids)
        except Exception as exc:
            print(f"Monitor error: {exc}", flush=True)
            time.sleep(settings.poll_interval_seconds)
            continue

        if not new_posts:
            time.sleep(settings.poll_interval_seconds)
            continue

        for post in new_posts:
            analyzed_at = datetime.now(UTC)
            try:
                signal = analyzer.analyze_post(post)
            except Exception as exc:
                print(f"AI analysis failed for {post.url}: {exc}", flush=True)
                append_analysis_record(
                    settings.analyses_path,
                    AnalysisRecord(
                        post=post,
                        analyzed_at=analyzed_at,
                        analysis_error=str(exc),
                    ),
                )
                cache.seen_post_ids.append(post.post_id)
                save_cache(settings.cache_path, cache)
                continue

            record = SignalRecord(
                post=post,
                signal=signal,
                analyzed_at=analyzed_at,
            )
            append_analysis_record(
                settings.analyses_path,
                AnalysisRecord(
                    post=post,
                    signal=signal,
                    analyzed_at=analyzed_at,
                ),
            )
            cache.signals.append(record)
            cache.seen_post_ids.append(post.post_id)

            if signal.is_trade_signal:
                report = build_report(
                    source=record,
                    history=cache.signals,
                    lookback_hours=settings.lookback_hours,
                )
                report_path = write_report(settings.reports_dir, report)
                print(render_terminal_report(report, report_path), flush=True)

            save_cache(settings.cache_path, cache)

        time.sleep(settings.poll_interval_seconds)


if __name__ == "__main__":
    main()
