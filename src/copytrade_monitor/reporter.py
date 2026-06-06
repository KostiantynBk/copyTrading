from __future__ import annotations

from pathlib import Path

from .models import SignalReport


def render_terminal_report(report: SignalReport, report_path: Path) -> str:
    lines = [
        "=== Trade Signal Report ===",
        f"Source: @{report.source_post.handle}",
        f"Post: {report.source_post.url}",
        f"Action: {report.source_signal.action}",
        f"Ticker: {report.source_signal.ticker or 'n/a'}",
        f"Sector: {report.source_signal.sector or 'n/a'}",
        f"Confidence: {report.source_signal.confidence:.0%}",
        f"Summary: {report.summary}",
        f"Saved: {report_path}",
    ]
    if report.same_ticker_opinions:
        lines.append("Same ticker opinions:")
        for item in report.same_ticker_opinions:
            lines.append(
                f"  - @{item.handle}: {item.action} {item.ticker or 'n/a'} | {item.url}"
            )
    if report.same_sector_opinions:
        lines.append("Same sector opinions:")
        for item in report.same_sector_opinions:
            lines.append(
                f"  - @{item.handle}: {item.action} {item.sector or 'n/a'} | {item.url}"
            )
    return "\n".join(lines)
