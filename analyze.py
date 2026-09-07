"""Claude analysis: digest headlines + price action into directional picks."""

import json
import os

from anthropic import Anthropic

from config import CLAUDE_MODEL, MARKETS, NUM_ETF_PICKS, NUM_PICKS

SYSTEM_PROMPT = """\
You are an equity research assistant producing a DAILY DIRECTIONAL DIGEST for a
personal research tool. You are given today's macro headlines, an index
snapshot, and the day's biggest movers in the universe with their recent price
action and stock-specific headlines.

Your job: an educated, clearly-reasoned estimate of which stocks in this
universe look most attractive to BUY over the next few weeks, grounded ONLY in
the evidence provided. Do not invent news or figures not present in the input.
If the evidence is thin for a name, say so via a lower conviction score.

Respond with ONLY a JSON object (no markdown fences, no prose) shaped exactly:
{
  "market_summary": "2-4 sentences on the day's tape and macro backdrop",
  "market_summary_plain": "1-2 sentences for a total beginner: what happened and why it matters, zero jargon",
  "picks": [
    {
      "ticker": "...",
      "name": "...",
      "conviction": 1-5,
      "signal_type": "momentum | dip_buy | catalyst | relative_strength | other",
      "thesis": "2-3 sentences: why buy, citing specific headlines/price action",
      "plain_english": "ONE sentence for someone who knows nothing about stocks: what the company does (if not obvious) and why it looks good right now",
      "catalysts": "what could push it up",
      "risks": "what could go wrong",
      "time_horizon": "e.g. '2-6 weeks'"
    }
  ],
  "etf_picks": [
    {
      "ticker": "...",
      "name": "...",
      "conviction": 1-5,
      "thesis": "why this fund/theme looks attractive given the macro headlines and sector price action",
      "plain_english": "ONE beginner-friendly sentence: what this fund holds and why now",
      "risks": "what could go wrong"
    }
  ],
  "watchlist": [ {"ticker": "...", "name": "...", "reason": "..."} ],
  "avoid": [
    {
      "ticker": "...",
      "name": "...",
      "reason": "analyst version: the specific evidence for staying away",
      "plain_english": "1-2 accessible sentences: what went wrong and why it's not a dip worth buying"
    }
  ]
}

Rules:
- Exactly %(num_picks)d picks, ordered by conviction (highest first).
- Picks must come from the provided universe/movers data.
- Exactly %(num_etf_picks)d etf_picks, chosen from the provided ETF snapshot.
  ETFs are theme/sector calls: reason from the macro headlines and the sector
  price action, not company news. These are the steadier, diversified ideas.
- plain_english fields are for a casual investor, not a professional:
  everyday language, but common investment terms are fine ("earnings",
  "guidance", "valuation", "interest rates", "sector"). Avoid dense pro
  shorthand ("re-rating", "multiple compression", "alpha", "capex cycle",
  "tape"). Don't dumb it down to baby talk — respect the reader. E.g. "They
  make the memory chips AI data centers need, and earnings keep coming in
  ahead of expectations."
- avoid entries matter as much as picks: the plain_english there should teach
  the reader WHY it's a trap — e.g. distinguish "the stock fell because the
  business is genuinely broken" from "it fell but might recover" so they
  understand the reasoning, not just the verdict.
- A stock that dropped on overdone panic can be a pick; a stock that spiked on
  hype can belong in "avoid". Think, don't just chase gainers.
- 2-4 watchlist names, 1-3 avoid names.
- Be concrete: reference the actual headline or move that drives each thesis.
- signal_type taxonomy: "momentum" = riding a strength continuation;
  "dip_buy" = buying an overdone selloff; "catalyst" = a specific upcoming or
  just-landed event; "relative_strength" = holding up better than the tape;
  "other" = anything else.
- If a TRACK RECORD section is provided, use it to calibrate: lean toward the
  signal types and conviction levels that have actually been producing alpha,
  be more skeptical of the ones that haven't, and when re-picking a name from
  the recent-picks list, say so in the thesis and account for how the earlier
  call has gone. Small sample sizes deserve only gentle weight — don't
  overreact to a handful of picks.
"""


def _build_user_prompt(market: str, context: dict) -> str:
    cfg = MARKETS[market]
    lines = [f"Market: {cfg['label']}", f"Date: {context['date']}"]
    idx = context.get("index")
    if idx:
        lines.append(
            f"{cfg['index_name']}: close {idx['close']}, "
            f"1d {idx['pct_1d']:+.2f}%, 5d {idx['pct_5d']:+.2f}%"
        )
    lines.append("\n== MACRO / MARKET HEADLINES (last ~2 days) ==")
    for h in context["macro_headlines"]:
        lines.append(f"- {h['title']} [{h['source']}]")
    lines.append("\n== BIGGEST MOVERS (yesterday's session) ==")
    for m in context["movers"]:
        lines.append(
            f"\n{m['ticker']} ({m['name']}): close {m['close']}, "
            f"1d {m['pct_1d']:+.2f}%, 5d {m['pct_5d']:+.2f}%"
        )
        for h in m["headlines"]:
            lines.append(f"  - {h['title']} [{h['source']}]")
        if not m["headlines"]:
            lines.append("  (no stock-specific headlines found)")
    if context.get("etfs"):
        lines.append("\n== ETF / FUND SNAPSHOT (pick etf_picks from these) ==")
        for e in context["etfs"]:
            lines.append(
                f"- {e['ticker']} ({e['name']}, theme: {e['theme']}): "
                f"close {e['close']}, 1d {e['pct_1d']:+.2f}%, 5d {e['pct_5d']:+.2f}%"
            )
    if context.get("track_record"):
        lines.append(
            "\n== TRACK RECORD (this tool's own past picks, graded at current prices) =="
        )
        lines.append(context["track_record"])
    return "\n".join(lines)


def _extract_text(response) -> str:
    # claude-sonnet-5 may emit a ThinkingBlock before the text block —
    # never assume content[0] is the text (same gotcha as the video pipeline).
    for block in response.content:
        if block.type == "text":
            return block.text
    raise RuntimeError("No text block in Claude response")


def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        text = text.removeprefix("json").strip()
    return json.loads(text)


def analyze(market: str, context: dict) -> dict:
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=12000,  # generous: 10 picks + ETFs, and thinking tokens eat into this
        system=SYSTEM_PROMPT % {"num_picks": NUM_PICKS, "num_etf_picks": NUM_ETF_PICKS},
        messages=[{"role": "user", "content": _build_user_prompt(market, context)}],
    )
    if response.stop_reason == "max_tokens":
        raise RuntimeError("Claude response truncated (max_tokens) — raise the budget")
    return _parse_json(_extract_text(response))
