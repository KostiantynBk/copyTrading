from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


TradeAction = Literal["buy", "sell", "hold", "none"]
Sentiment = Literal["bullish", "bearish", "neutral", "mixed"]


class Profile(BaseModel):
    handle: str
    display_name: str | None = None


class ObservedPost(BaseModel):
    post_id: str
    handle: str
    display_name: str | None = None
    text: str
    image_urls: list[str] = Field(default_factory=list)
    image_alts: list[str] = Field(default_factory=list)
    posted_at: datetime | None = None
    url: str
    captured_at: datetime


class TradeSignal(BaseModel):
    is_trade_signal: bool = Field(
        description="Whether the post contains a real directional investment or trading view."
    )
    action: TradeAction = "none"
    sentiment: Sentiment = "neutral"
    ticker: str | None = None
    company_name: str | None = None
    sector: str | None = None
    asset_type: str | None = None
    time_horizon: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale: str
    evidence_text: str | None = None
    detection_method: Literal["heuristic", "llm", "llm_verified"] | None = None
    verification_notes: str | None = None
    risk_notes: list[str] = Field(default_factory=list)


class TradeSignalVerification(BaseModel):
    confirmed: bool
    corrected_is_trade_signal: bool
    corrected_action: TradeAction = "none"
    corrected_sentiment: Sentiment = "neutral"
    corrected_ticker: str | None = None
    corrected_company_name: str | None = None
    corrected_sector: str | None = None
    corrected_asset_type: str | None = None
    corrected_time_horizon: str | None = None
    corrected_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    corrected_rationale: str
    corrected_evidence_text: str | None = None
    verification_notes: str
    risk_notes: list[str] = Field(default_factory=list)


class SignalRecord(BaseModel):
    post: ObservedPost
    signal: TradeSignal
    analyzed_at: datetime


class AnalysisRecord(BaseModel):
    post: ObservedPost
    signal: TradeSignal | None = None
    analyzed_at: datetime
    analysis_error: str | None = None


class RelatedOpinion(BaseModel):
    handle: str
    post_id: str
    relation: Literal["same_ticker", "same_sector"]
    action: TradeAction
    sentiment: Sentiment
    ticker: str | None = None
    sector: str | None = None
    rationale: str
    url: str
    posted_at: datetime | None = None


class SignalReport(BaseModel):
    generated_at: datetime
    source_post: ObservedPost
    source_signal: TradeSignal
    same_ticker_opinions: list[RelatedOpinion] = Field(default_factory=list)
    same_sector_opinions: list[RelatedOpinion] = Field(default_factory=list)
    summary: str


class CacheState(BaseModel):
    seen_post_ids: list[str] = Field(default_factory=list)
    signals: list[SignalRecord] = Field(default_factory=list)
