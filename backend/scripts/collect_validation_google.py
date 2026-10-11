"""Collect a focused Google shortlist without requiring the old cloud database."""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapters.research.google_ads_keyword_planner import GoogleAdsKeywordPlannerAdapter
from services.product_validation import digest


def collect(keywords, output):
    normalized = list(dict.fromkeys(" ".join(value.lower().split()) for value in keywords if value.strip()))
    if not 1 <= len(normalized) <= 15:
        raise ValueError("Provide 1–15 focused buyer keywords")
    if output.exists():
        raise FileExistsError("Preserve previous evidence; choose a new output file")
    adapter = GoogleAdsKeywordPlannerAdapter()
    if not adapter.is_configured():
        raise ValueError("Existing Google Ads authorization is not configured")
    signals = adapter.bulk_search(normalized)
    payload = {"schema_version": 1, "source": "google_ads_keyword_planner",
        "collected_at": datetime.now(timezone.utc).isoformat(), "geography": adapter._geography_label(),
        "requested_keywords": normalized, "signals": [asdict(signal) for signal in signals],
        "notes": ["Close variants share a demand measure; do not sum them as independent demand.",
                  "Competition describes Google advertisers, not Etsy sellers."]}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"payload": payload, "sha256": digest(payload)}, indent=2), encoding="utf-8")
    print(json.dumps({"requested": len(normalized), "results": len(signals), "output": str(output), "sha256": digest(payload)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keywords", required=True, help="Comma-separated buyer keywords")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        collect(args.keywords.split(","), args.output)
    except Exception as exc:
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__,
            "http_status": getattr(exc, "http_status", None), "provider_codes": getattr(exc, "provider_codes", [])}), file=sys.stderr)
        sys.exit(1)
