from __future__ import annotations

import re
from typing import Any

from openai import OpenAI

from .models import ObservedPost, TradeSignal, TradeSignalVerification


EXTRACTION_PROMPT = """You read X posts from traders and investors.
Return structured JSON deciding whether the post contains a real investment or trading call.

A trade signal includes either:
- an actionable directional opinion on a stock or equity-like instrument
- an explicit trade execution or position-management update

Explicit trade execution updates count as signals. Posts about buying, selling, adding, trimming,
reducing, covering, stopping out, or exiting a position are actionable even if they are written as
portfolio updates instead of advice.

Not trade signals:
- general market commentary
- vague excitement
- memes
- news reposts
- pure performance recap without a current or recent trade action

Use attached image alt text and images when they identify the asset, ticker, or directional view.
If the post text implies a trade but the asset is only visible in an image, treat the image as valid evidence.

Populate evidence_text with a short exact snippet from the post or image alt text that best supports your decision.
If the post does not clearly contain a directional view or position change, set is_trade_signal=false and action=none.
If the ticker is implied but not certain, leave ticker null and explain uncertainty in rationale.
Sector should be a concise industry label like 'semiconductors', 'software', 'banks', or 'oil and gas'.
Confidence must be between 0 and 1.
Set detection_method='llm'.
"""

VERIFICATION_PROMPT = """You validate whether a first-pass extraction from an X post is actually supported by the evidence.

A trade signal includes:
- entering a position
- adding to a position
- reducing or trimming a position
- selling or exiting a position
- covering a short
- stopping out
- a clear actionable directional opinion on a named asset

Not a trade signal:
- general market commentary
- performance recap without a concrete trade action
- vague interest or watchlist comments
- memes or reposted news

You are given the original post and the first-pass structured extraction.
Your task is to verify whether the extraction is supported by the text and attached evidence.

If the first pass is wrong or unsupported, correct it.
Be conservative about unsupported fields, but do not reject explicit execution statements like
'Sold some more XLE at $60.'
"""

BUY_PATTERNS = (
    r"\bbought\b",
    r"\bbuying\b",
    r"\badded\b",
    r"\badding\b",
    r"\bstarted\b",
    r"\bstarting\b",
    r"\bopened\b",
    r"\bopening\b",
    r"\blong(?:ed|ing)?\b",
    r"\baccumulat(?:e|ed|ing)\b",
    r"\bre-?enter(?:ed|ing)?\b",
    r"\bback in\b",
    r"\bnibbl(?:e|ed|ing)\b",
    r"\bpicked up\b",
    r"\bload(?:ed|ing)? up on\b",
    r"\bstarter\b",
    r"\brotating into\b",
)

SELL_PATTERNS = (
    r"\bsold\b",
    r"\bselling\b",
    r"\btrim(?:med|ming)?\b",
    r"\breduc(?:e|ed|ing)\b",
    r"\bcut\b",
    r"\bcutting\b",
    r"\bclosed\b",
    r"\bclosing\b",
    r"\bexit(?:ed|ing)?\b",
    r"\bshort(?:ed|ing)?\b",
    r"\bcover(?:ed|ing)?\b",
    r"\btook profits?\b",
    r"\bstopped out\b",
    r"\blighten(?:ed|ing)? up\b",
    r"\bde-?risk(?:ed|ing)?\b",
    r"\brotating out of\b",
)

TICKER_PATTERN = re.compile(r"(?<![A-Z0-9])\$?([A-Z]{2,5})(?![A-Z])")
PRICE_PATTERN = re.compile(r"\$\d+(?:\.\d+)?")
TRADE_NOISE = {
    "A",
    "AI",
    "ALL",
    "CEO",
    "ETF",
    "EV",
    "FYI",
    "GDP",
    "IMO",
    "LOL",
    "NYSE",
    "SEC",
    "USD",
    "US",
    "USA",
}

TRADE_FILLER_WORDS = {
    "a",
    "an",
    "any",
    "my",
    "our",
    "some",
    "more",
    "of",
    "in",
    "into",
    "shares",
    "share",
    "stock",
    "position",
    "stake",
    "common",
}
COMPANY_STOP_WORDS = {
    "because",
    "but",
    "for",
    "if",
    "since",
    "so",
    "that",
    "though",
    "when",
    "while",
    "with",
}
COMPANY_NAME_CONNECTORS = {"&", "and", "of"}

VERIFICATION_MIN_CONFIDENCE = 0.35
VERIFICATION_MAX_CONFIDENCE = 0.85


class AIAnalyzer:
    def __init__(self, api_key: str, model: str) -> None:
        self._client = OpenAI(api_key=api_key)
        self._model = model

    def analyze_post(self, post: ObservedPost) -> TradeSignal:
        heuristic_signal = _infer_explicit_trade_signal(post.text)
        if heuristic_signal is not None:
            return heuristic_signal

        user_content = _build_post_content(post)
        extracted = self._extract_signal(user_content)
        if not _should_verify(post.text, extracted):
            return extracted

        verified = self._verify_signal(post, extracted, user_content)
        return _merge_verified_signal(extracted, verified)

    def _extract_signal(self, user_content: list[dict[str, Any]]) -> TradeSignal:
        response = self._client.responses.parse(
            model=self._model,
            input=[
                {"role": "system", "content": EXTRACTION_PROMPT},
                {"role": "user", "content": user_content},
            ],
            text_format=TradeSignal,
        )
        signal = response.output_parsed
        if signal.detection_method is None:
            signal.detection_method = "llm"
        return signal

    def _verify_signal(
        self,
        post: ObservedPost,
        extracted: TradeSignal,
        user_content: list[dict[str, Any]],
    ) -> TradeSignalVerification:
        verification_payload = [
            {
                "type": "input_text",
                "text": (
                    "First-pass extraction:\n"
                    f"{extracted.model_dump_json(indent=2)}"
                ),
            }
        ]
        verification_payload.extend(user_content)
        response = self._client.responses.parse(
            model=self._model,
            input=[
                {"role": "system", "content": VERIFICATION_PROMPT},
                {"role": "user", "content": verification_payload},
            ],
            text_format=TradeSignalVerification,
        )
        return response.output_parsed


def _build_post_content(post: ObservedPost) -> list[dict[str, Any]]:
    user_content: list[dict[str, Any]] = [
        {
            "type": "input_text",
            "text": (
                f"Handle: @{post.handle}\n"
                f"URL: {post.url}\n"
                f"Posted at: {post.posted_at.isoformat() if post.posted_at else 'unknown'}\n"
                f"Post text:\n{post.text}"
            ),
        }
    ]
    if post.image_alts:
        user_content.append(
            {
                "type": "input_text",
                "text": "Attached image alt text:\n" + "\n".join(f"- {alt}" for alt in post.image_alts),
            }
        )
    for image_url in post.image_urls[:4]:
        user_content.append({"type": "input_image", "image_url": image_url})
    return user_content


def _infer_explicit_trade_signal(text: str) -> TradeSignal | None:
    normalized = " ".join(text.split())
    lowered = normalized.lower()

    action_match = _detect_action_match(lowered)
    if action_match is None:
        return None
    action, action_end = action_match

    ticker = _extract_ticker(normalized)
    company_name = _extract_company_name(normalized, action_end)
    if ticker is None and company_name is None and not PRICE_PATTERN.search(normalized):
        return None

    sentiment = "bullish" if action == "buy" else "bearish"
    evidence_text = _pick_evidence_text(normalized, ticker, company_name)
    rationale = (
        "Detected an explicit position-management update in the post text"
        + (
            f" mentioning {ticker}."
            if ticker
            else f" mentioning {company_name}."
            if company_name
            else "."
        )
    )
    return TradeSignal(
        is_trade_signal=True,
        action=action,
        sentiment=sentiment,
        ticker=ticker,
        company_name=company_name,
        asset_type="equity" if ticker or company_name else None,
        confidence=0.91 if ticker else 0.88 if company_name else 0.8,
        rationale=rationale,
        evidence_text=evidence_text,
        detection_method="heuristic",
    )


def _detect_action_match(lowered_text: str) -> tuple[str, int] | None:
    for pattern in SELL_PATTERNS:
        match = re.search(pattern, lowered_text)
        if match:
            return "sell", match.end()
    for pattern in BUY_PATTERNS:
        match = re.search(pattern, lowered_text)
        if match:
            return "buy", match.end()
    return None


def _extract_ticker(text: str) -> str | None:
    for match in TICKER_PATTERN.finditer(text):
        ticker = match.group(1).upper()
        if ticker in TRADE_NOISE:
            continue
        return ticker
    return None


def _extract_company_name(text: str, action_end: int) -> str | None:
    tail = text[action_end:]
    tokens = re.findall(r"[A-Za-z][A-Za-z.&'-]*|&", tail)

    collecting = False
    company_tokens: list[str] = []
    for token in tokens:
        lowered = token.lower()
        is_title_case = token[0].isupper() and not token.isupper()

        if not collecting and lowered in TRADE_FILLER_WORDS:
            continue
        if not collecting and not is_title_case:
            continue

        if lowered in COMPANY_STOP_WORDS:
            break
        if collecting and lowered in COMPANY_NAME_CONNECTORS:
            company_tokens.append(token)
            continue
        if is_title_case:
            collecting = True
            company_tokens.append(token)
            continue
        if collecting:
            break

    if not company_tokens:
        return None
    return " ".join(company_tokens[:4])


def _pick_evidence_text(text: str, ticker: str | None, company_name: str | None) -> str:
    for fragment in re.split(r"(?<=[.!?])\s+", text):
        candidate = fragment.strip()
        if not candidate:
            continue
        if ticker and ticker in candidate.upper():
            return candidate
        if company_name and company_name in candidate:
            return candidate
        if PRICE_PATTERN.search(candidate):
            return candidate
    return text[:160]


def _contains_trade_language(text: str) -> bool:
    lowered = text.lower()
    return any(re.search(pattern, lowered) for pattern in BUY_PATTERNS + SELL_PATTERNS)


def _should_verify(text: str, signal: TradeSignal) -> bool:
    has_trade_language = _contains_trade_language(text)

    if signal.detection_method == "heuristic":
        return False
    if signal.evidence_text is None or not signal.evidence_text.strip():
        return True
    if signal.action == "none" and signal.is_trade_signal:
        return True
    if signal.action != "none" and not signal.is_trade_signal:
        return True
    if signal.is_trade_signal and not any([signal.ticker, signal.company_name, signal.sector]):
        return True
    if has_trade_language and not signal.is_trade_signal:
        return True
    if VERIFICATION_MIN_CONFIDENCE <= signal.confidence <= VERIFICATION_MAX_CONFIDENCE:
        return True
    return False


def _merge_verified_signal(
    extracted: TradeSignal,
    verified: TradeSignalVerification,
) -> TradeSignal:
    if verified.confirmed:
        return TradeSignal(
            is_trade_signal=extracted.is_trade_signal,
            action=extracted.action,
            sentiment=extracted.sentiment,
            ticker=extracted.ticker,
            company_name=extracted.company_name,
            sector=extracted.sector,
            asset_type=extracted.asset_type,
            time_horizon=extracted.time_horizon,
            confidence=extracted.confidence,
            rationale=extracted.rationale,
            evidence_text=extracted.evidence_text,
            detection_method="llm_verified",
            verification_notes=verified.verification_notes,
            risk_notes=_merge_risk_notes(extracted.risk_notes, verified.risk_notes),
        )

    return TradeSignal(
        is_trade_signal=verified.corrected_is_trade_signal,
        action=verified.corrected_action,
        sentiment=verified.corrected_sentiment,
        ticker=verified.corrected_ticker,
        company_name=verified.corrected_company_name,
        sector=verified.corrected_sector,
        asset_type=verified.corrected_asset_type,
        time_horizon=verified.corrected_time_horizon,
        confidence=verified.corrected_confidence,
        rationale=verified.corrected_rationale,
        evidence_text=verified.corrected_evidence_text,
        detection_method="llm_verified",
        verification_notes=verified.verification_notes,
        risk_notes=_merge_risk_notes(extracted.risk_notes, verified.risk_notes),
    )


def _merge_risk_notes(primary: list[str], secondary: list[str]) -> list[str]:
    merged: list[str] = []
    for note in primary + secondary:
        if note and note not in merged:
            merged.append(note)
    return merged
