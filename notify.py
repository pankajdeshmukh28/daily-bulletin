"""Deliver the daily report to Telegram (same bot/chat as the video pipeline).

Uses the plain Bot HTTP API via requests — no python-telegram-bot dependency
needed for two simple calls. Sends a compact picks summary message, then the
full markdown report as an attached document.
"""

import html
import os
from pathlib import Path

import requests

_API = "https://api.telegram.org/bot{token}/{method}"
_STARS = {n: "★" * n + "☆" * (5 - n) for n in range(1, 6)}


def telegram_configured() -> bool:
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))


def _call(method: str, *, data: dict, files: dict | None = None):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    resp = requests.post(
        _API.format(token=token, method=method),
        data={"chat_id": os.environ["TELEGRAM_CHAT_ID"], **data},
        files=files,
        timeout=60,
    )
    payload = resp.json()
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram {method} failed: {payload}")
    return payload


def _summary_text(market_label: str, context: dict, analysis: dict) -> str:
    """Compact summary: tickers + stars only. Plain-English "why" lives in
    the attached report, per user feedback."""
    lines = [f"📈 <b>Daily Signal — {html.escape(market_label)} — {context['date']}</b>", ""]
    idx = context.get("index")
    if idx:
        lines.append(f"Index: {idx['close']} ({idx['pct_1d']:+.2f}% 1d)")
        lines.append("")
    lines.append("<b>Buy candidates</b>")
    for i, p in enumerate(analysis["picks"], 1):
        stars = _STARS.get(int(p["conviction"]), "?")
        lines.append(f"{i}. <b>{html.escape(p['ticker'])}</b> {stars} — {html.escape(p['name'])}")
    if analysis.get("etf_picks"):
        lines += ["", "<b>Fund ideas (ETFs)</b>"]
        for p in analysis["etf_picks"]:
            stars = _STARS.get(int(p["conviction"]), "?")
            lines.append(f"• <b>{html.escape(p['ticker'])}</b> {stars} — {html.escape(p['name'])}")
    if analysis.get("avoid"):
        avoid = ", ".join(html.escape(a["ticker"]) for a in analysis["avoid"])
        lines.append(f"\n⛔ Avoid: {avoid}")
    lines.append("\nWhy each pick (in plain words) + risks: attached report.")
    lines.append("<i>Informational only — not financial advice.</i>")
    return "\n".join(lines)


def send_report(market_label: str, context: dict, analysis: dict, md_path: str):
    text = _summary_text(market_label, context, analysis)
    if len(text) > 4000:  # Telegram hard limit is 4096 chars per message
        text = text[:3980].rsplit("\n", 1)[0] + "\n…(see attached report)"
    _call("sendMessage", data={"text": text, "parse_mode": "HTML"})
    with open(md_path, "rb") as f:
        _call(
            "sendDocument",
            data={"caption": f"Daily Signal — {market_label} — {context['date']}"},
            files={"document": (Path(md_path).name, f)},
        )
