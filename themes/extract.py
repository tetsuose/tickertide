"""M4.5 LLM theme extraction: EDGAR 10-K business/segment text -> candidate memberships.

WHY this shape (C6, PRD §8.3)
-----------------------------
The LLM is a CANDIDATE GENERATOR + revenue extractor, never the authority: output goes
to themes/candidates/<TICKER>.json for a human to review (themes/review.py). Exposure is
revenue-anchored (estimated share of total revenue attributable to the theme, grounded in
the filing's segment/market disclosures); when the filing's segmentation is too coarse to
support a number, the candidate must carry confidence='low' — partial/approximate is fine,
fabricated precision is not.

LLM backend = the `claude` CLI in print mode (subscription plan quota — the decision was
to NOT wire an API key; see ROADMAP M4.5). This makes extraction an OPERATOR-RUN step on
a logged-in machine, never part of nightly CI — which matches the human-in-loop design:
candidates without review are worthless to the pipeline anyway.

Usage:
    python3 themes/extract.py --ticker NVDA [--model MODEL] [--out PATH]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ingest.edgar import UA, fetch_cik_map  # noqa: E402  (descriptive UA + ticker->CIK)
from themes.seed import load_themes  # noqa: E402

CANDIDATES_DIR = ROOT / "themes" / "candidates"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc}/{doc}"
MAX_PROMPT_CHARS = 36_000   # filing-text budget for the prompt (Item 1 head + segment windows)
SEGMENT_WINDOW = 3_000      # chars kept around each segment/revenue-disclosure match


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def latest_10k(cik: str) -> dict:
    """Latest 10-K filing meta for a zero-padded CIK -> {form, accession, filed, doc, url}."""
    sub = json.loads(_get(SUBMISSIONS_URL.format(cik=cik)))
    recent = sub["filings"]["recent"]
    for form, acc, doc, filed in zip(recent["form"], recent["accessionNumber"],
                                     recent["primaryDocument"], recent["filingDate"]):
        if form == "10-K":
            url = ARCHIVES_URL.format(cik_int=int(cik), acc=acc.replace("-", ""), doc=doc)
            return {"form": form, "accession": acc, "filed": filed, "doc": doc, "url": url,
                    "company": sub.get("name", "")}
    raise SystemExit(f"[extract] no 10-K found for CIK {cik}")


def html_to_text(html: str) -> str:
    """Crude-but-sufficient HTML -> text for prompt assembly (no external deps)."""
    html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?i)</(p|div|tr|li|h[1-6]|table)>", "\n", html)
    text = re.sub(r"<[^>]+>", " ", html)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&#8217;", "'")
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n", text).strip()


def select_chunks(text: str) -> str:
    """Item 1 (business) head + windows around segment/revenue-disclosure mentions,
    capped at MAX_PROMPT_CHARS. A 10-K is ~1MB of text; the theme-relevant evidence
    (what the business is + how revenue splits) concentrates in these regions."""
    chunks: list[str] = []
    m = re.search(r"(?i)item\s*1\s*[.:—-]?\s*business", text)
    start = m.start() if m else 0
    chunks.append(text[start:start + 14_000])

    pat = re.compile(r"(?i)(reportable segment|operating segment|revenue by (market|segment|platform|end market)|disaggregat\w+ of revenue)")
    seen_spans: list[tuple[int, int]] = []
    for m in pat.finditer(text):
        lo, hi = max(0, m.start() - 500), m.start() + SEGMENT_WINDOW
        if seen_spans and lo < seen_spans[-1][1]:        # merge overlapping windows
            seen_spans[-1] = (seen_spans[-1][0], hi)
        else:
            seen_spans.append((lo, hi))
    for lo, hi in seen_spans[:12]:
        chunks.append(f"\n--- segment/revenue disclosure (offset {lo}) ---\n" + text[lo:hi])

    out = "\n".join(chunks)
    return out[:MAX_PROMPT_CHARS]


def build_prompt(ticker: str, company: str, filing: dict, filing_text: str,
                 themes: list[dict]) -> str:
    theme_lines = "\n".join(
        f"- {t['key']}: {t['description']} (keywords: {', '.join(t['keywords'])})"
        for t in themes
    )
    return f"""You are a revenue-exposure extractor for an equity-theme classifier.

Company: {company} ({ticker}) — {filing['form']} filed {filing['filed']} (accession {filing['accession']}).

Theme universe (use ONLY these keys):
{theme_lines}

Task: from the filing excerpts below, propose which themes this company belongs to and
estimate each theme's `exposure` = the share of TOTAL revenue attributable to that theme,
as a number in [0,1].

Hard rules:
1. REVENUE-ANCHORED: ground every exposure in the segment / end-market revenue figures
   disclosed in the excerpts. Quote the figures you used in `basis` (numbers + segment
   names + fiscal period).
2. Themes overlap (many-to-many, never MECE): the same revenue dollar may support two
   themes (e.g. a datacenter GPU dollar is both AI and SEMI). Do NOT force exposures to
   sum to 1.
3. If the disclosed segmentation is too coarse to support a number, still propose the
   theme if the business description warrants it, but set confidence to "low" and say
   what is missing in `basis`. NEVER fabricate revenue figures.
4. Only include themes with exposure >= 0.05. Confidence is "high" | "medium" | "low".

Answer with STRICT JSON only (no prose, no markdown fences):
{{"candidates": [{{"theme": "KEY", "exposure": 0.0, "basis": "revenue figures + segments used",
  "rationale": "1-2 sentences", "confidence": "high|medium|low"}}],
 "notes": "anything material about data quality / segmentation granularity"}}

Filing excerpts:
{filing_text}"""


def call_claude(prompt: str, model: str | None) -> tuple[dict, str]:
    """Run `claude -p` (print mode, subscription quota) and parse the strict-JSON answer.
    Returns (parsed, model_used). Raises SystemExit with the raw output on parse failure."""
    cmd = ["claude", "-p", "--output-format", "json"]
    if model:
        cmd += ["--model", model]
    proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        raise SystemExit(f"[extract] claude CLI failed ({proc.returncode}): {proc.stderr[:500]}")
    envelope = json.loads(proc.stdout)
    answer = envelope.get("result", "")
    body = re.sub(r"^```(?:json)?\s*|\s*```$", "", answer.strip())
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", body, re.S)          # salvage the outermost JSON object
        if not m:
            raise SystemExit(f"[extract] LLM answer is not JSON:\n{answer[:1000]}")
        parsed = json.loads(m.group(0))
    return parsed, envelope.get("modelUsage") and next(iter(envelope["modelUsage"])) or (model or "claude")


def validate(parsed: dict, valid_keys: set[str]) -> list[dict]:
    out = []
    for c in parsed.get("candidates", []):
        theme, exp = c.get("theme"), c.get("exposure")
        if theme not in valid_keys:
            print(f"[extract] WARNING dropping unknown theme key: {theme}")
            continue
        if not isinstance(exp, (int, float)) or not (0 <= exp <= 1):
            print(f"[extract] WARNING dropping {theme}: exposure {exp} outside [0,1]")
            continue
        if c.get("confidence") not in ("high", "medium", "low"):
            c["confidence"] = "low"
        out.append({k: c.get(k, "") for k in ("theme", "exposure", "basis", "rationale", "confidence")})
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="TickerTide M4.5: EDGAR 10-K -> LLM theme candidates.")
    ap.add_argument("--ticker", required=True, help="US ticker, e.g. NVDA")
    ap.add_argument("--model", default=None, help="claude CLI model override (default: CLI default)")
    ap.add_argument("--out", default=None, help="output path (default themes/candidates/<TICKER>.json)")
    args = ap.parse_args(argv)
    ticker = args.ticker.upper()

    cik = fetch_cik_map().get(ticker)
    if not cik:
        raise SystemExit(f"[extract] {ticker} not in SEC company_tickers.json")
    filing = latest_10k(cik)
    print(f"[extract] {ticker} CIK {cik} — {filing['form']} filed {filing['filed']} ({filing['url']})")

    text = html_to_text(_get(filing["url"]).decode("utf-8", errors="replace"))
    excerpts = select_chunks(text)
    print(f"[extract] filing text {len(text):,} chars -> prompt excerpts {len(excerpts):,} chars")

    themes = load_themes()
    parsed, model_used = call_claude(build_prompt(ticker, filing["company"], filing, excerpts, themes), args.model)
    candidates = validate(parsed, {t["key"] for t in themes})
    if not candidates:
        raise SystemExit("[extract] LLM returned no valid candidates")

    out = Path(args.out) if args.out else CANDIDATES_DIR / f"{ticker}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "ticker": ticker, "cik": cik,
        "filing": {k: filing[k] for k in ("form", "accession", "filed", "url")},
        "generated_on": date.today().isoformat(), "model": model_used, "source": "llm",
        "candidates": candidates, "notes": parsed.get("notes", ""),
    }
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n")

    print(f"[extract] {len(candidates)} candidate(s) -> {out}")
    for c in candidates:
        print(f"    {c['theme']:6} exposure={c['exposure']:.2f} [{c['confidence']}] {c['rationale'][:90]}")
    print(f"[extract] next: python3 themes/review.py --ticker {ticker}   (human approval, C6)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
