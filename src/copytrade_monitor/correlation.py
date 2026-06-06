from __future__ import annotations

from datetime import UTC, datetime, timedelta

from .models import RelatedOpinion, SignalRecord, SignalReport


def build_report(
    source: SignalRecord,
    history: list[SignalRecord],
    lookback_hours: int,
) -> SignalReport:
    cutoff = source.analyzed_at - timedelta(hours=lookback_hours)
    same_ticker: list[RelatedOpinion] = []
    same_sector: list[RelatedOpinion] = []

    for record in history:
        if record.post.post_id == source.post.post_id:
            continue
        if record.analyzed_at < cutoff:
            continue
        if not record.signal.is_trade_signal:
            continue
        if record.post.handle == source.post.handle:
            continue

        relation = None
        if (
            source.signal.ticker
            and record.signal.ticker
            and source.signal.ticker.upper() == record.signal.ticker.upper()
        ):
            relation = "same_ticker"
        elif (
            source.signal.sector
            and record.signal.sector
            and source.signal.sector.strip().lower() == record.signal.sector.strip().lower()
        ):
            relation = "same_sector"

        if not relation:
            continue

        opinion = RelatedOpinion(
            handle=record.post.handle,
            post_id=record.post.post_id,
            relation=relation,
            action=record.signal.action,
            sentiment=record.signal.sentiment,
            ticker=record.signal.ticker,
            sector=record.signal.sector,
            rationale=record.signal.rationale,
            url=record.post.url,
            posted_at=record.post.posted_at,
        )
        if relation == "same_ticker":
            same_ticker.append(opinion)
        else:
            same_sector.append(opinion)

    summary = _build_summary(source, same_ticker, same_sector)
    return SignalReport(
        generated_at=datetime.now(UTC),
        source_post=source.post,
        source_signal=source.signal,
        same_ticker_opinions=same_ticker,
        same_sector_opinions=same_sector,
        summary=summary,
    )


def _build_summary(
    source: SignalRecord,
    same_ticker: list[RelatedOpinion],
    same_sector: list[RelatedOpinion],
) -> str:
    ticker = source.signal.ticker or source.signal.company_name or "unknown asset"
    opening = (
        f"@{source.post.handle} posted a {source.signal.action} view on {ticker} "
        f"with {source.signal.confidence:.0%} confidence."
    )
    if same_ticker or same_sector:
        return (
            f"{opening} Found {len(same_ticker)} same-ticker opinions and "
            f"{len(same_sector)} same-sector opinions from other watched accounts."
        )
    return f"{opening} No corroborating posts were found in the configured lookback window."
