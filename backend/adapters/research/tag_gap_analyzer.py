"""
Tag Gap Analyzer — pure logic, no HTTP calls.

Identifies the market gap between what buyers search for (autocomplete terms)
and what sellers optimize for (listing tags). This asymmetry is the most
actionable ranking opportunity on Etsy:

  If buyers search "minimalist dog mom mug" but zero top listings tag for
  "minimalist dog mom" — a new listing that adds that tag will rank easily
  because no established seller is competing for it directly.

This replicates EverBee's "tag audit" feature using only free public data.

Usage:
    from adapters.research.tag_gap_analyzer import TagGapAnalyzer, analyze_tags

    report = analyze_tags(
        keyword="dog mom mug",
        autocomplete_terms=["dog mom mug funny", "dog mom mug personalized", ...],
        listing_tag_sets=[["dog mom", "funny mug", "pet gift"], ...],
    )
    print(report.tag_gap_score)     # 0-100
    print(report.untagged_searches) # buyer terms with zero competition
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TagGapReport:
    keyword: str

    # Buyer-side signals (autocomplete)
    autocomplete_terms: list[str] = field(default_factory=list)

    # Seller-side signals (from listing tags)
    tag_frequency: dict[str, int] = field(default_factory=dict)  # tag -> count of listings using it
    dominant_cluster: str = ""              # tag appearing in >40% of listings
    dominant_cluster_pct: float = 0.0       # what fraction of listings use the dominant tag

    # Gap signals
    untagged_searches: list[str] = field(default_factory=list)   # buyer terms with NO seller tag match
    partial_tag_matches: list[str] = field(default_factory=list) # buyer terms with weak coverage (<30% sellers)

    # Gap scores (0-100; higher = more opportunity)
    tag_gap_score: float = 0.0      # how uncontested the buyer search terms are
    style_gap_score: float = 0.0    # how much one style dominates (= room for alternatives)
    composite_gap_score: float = 0.0

    # Entry-point recommendation
    recommended_tags: list[str] = field(default_factory=list)    # highest-value uncontested tags to add
    entry_angle: str = ""           # one-sentence niche angle


def analyze_tags(
    keyword: str,
    autocomplete_terms: list[str],
    listing_tag_sets: list[list[str]],
    min_listings: int = 3,
) -> TagGapReport:
    """
    Compute the tag gap between buyer search terms and seller tag coverage.

    Args:
        keyword: The root keyword being analyzed.
        autocomplete_terms: Suggestions from Etsy autocomplete (what buyers type).
        listing_tag_sets: Tags from each listing page fetched (list of tag lists).
        min_listings: Minimum listing tag sets required to produce a valid score.

    Returns:
        TagGapReport with all gap metrics computed.
    """
    report = TagGapReport(keyword=keyword, autocomplete_terms=autocomplete_terms)

    if not listing_tag_sets or len(listing_tag_sets) < min_listings:
        report.tag_gap_score = 50.0  # unknown, neutral
        report.entry_angle = f"Insufficient listing data to analyze tag coverage for '{keyword}'"
        return report

    n = len(listing_tag_sets)

    # ── Build tag frequency table ─────────────────────────────────────────────
    counter: Counter[str] = Counter()
    for tag_list in listing_tag_sets:
        for tag in tag_list:
            t = _normalize(tag)
            if t:
                counter[t] += 1

    report.tag_frequency = dict(counter.most_common(50))

    # ── Identify dominant cluster ─────────────────────────────────────────────
    if counter:
        top_tag, top_count = counter.most_common(1)[0]
        report.dominant_cluster = top_tag
        report.dominant_cluster_pct = round(top_count / n * 100, 1)

    # ── Measure buyer term coverage ───────────────────────────────────────────
    # A buyer term is "covered" if ≥30% of top listings use a tag that contains it
    all_tags_flat = [_normalize(t) for tags in listing_tag_sets for t in tags]

    untagged = []
    partial = []

    for term in autocomplete_terms:
        norm_term = _normalize(term)
        if not norm_term or norm_term == _normalize(keyword):
            continue
        # Check how many listings have a tag that overlaps with this term
        matching_count = 0
        for tag_list in listing_tag_sets:
            normalized_tags = [_normalize(t) for t in tag_list]
            if any(_terms_overlap(norm_term, nt) for nt in normalized_tags):
                matching_count += 1
        coverage_pct = matching_count / n * 100
        if coverage_pct == 0:
            untagged.append(term)
        elif coverage_pct < 30:
            partial.append(term)

    report.untagged_searches = untagged
    report.partial_tag_matches = partial

    # ── Compute tag_gap_score (0-100) ─────────────────────────────────────────
    # Score is based on:
    #   - % of autocomplete terms with zero coverage (0-60 pts)
    #   - % of autocomplete terms with <30% coverage (0-25 pts)
    #   - Average number of tags per listing < 10 (sellers under-tagging) (0-15 pts)
    n_terms = max(1, len(autocomplete_terms) - 1)  # exclude the root keyword
    zero_pct = len(untagged) / n_terms
    partial_pct = len(partial) / n_terms
    avg_tags_per_listing = sum(len(t) for t in listing_tag_sets) / n

    zero_pts = zero_pct * 60
    partial_pts = partial_pct * 25
    undertag_pts = max(0, (10 - avg_tags_per_listing) / 10 * 15)

    report.tag_gap_score = round(min(100.0, zero_pts + partial_pts + undertag_pts), 1)

    # ── Compute style_gap_score (0-100) ───────────────────────────────────────
    # If one style (dominant cluster) is used by >50% of listings,
    # the remaining buyers wanting a different style are unserved.
    # score = how concentrated the top listing style is
    # High score = most sellers look alike = easy to differentiate with a different style
    if report.dominant_cluster_pct >= 70:
        style_gap = 85.0   # near-monopoly style — huge opening for alternatives
    elif report.dominant_cluster_pct >= 50:
        style_gap = 65.0   # dominant style, still openings
    elif report.dominant_cluster_pct >= 30:
        style_gap = 40.0   # some clustering, moderate opportunity
    else:
        style_gap = 15.0   # diverse styles already, harder to differentiate
    report.style_gap_score = style_gap

    # ── Composite ─────────────────────────────────────────────────────────────
    report.composite_gap_score = round(
        report.tag_gap_score * 0.65 + report.style_gap_score * 0.35, 1
    )

    # ── Recommended tags ──────────────────────────────────────────────────────
    # Take the untagged buyer terms + add root keyword fragments not in top tags
    rec = list(untagged[:5])
    # Also include high-frequency partial matches that are still underused
    for t in partial[:3]:
        if t not in rec:
            rec.append(t)
    report.recommended_tags = rec[:8]

    # ── Entry angle ───────────────────────────────────────────────────────────
    report.entry_angle = _build_entry_angle(keyword, untagged, report.dominant_cluster, style_gap)

    return report


# ── Internal helpers ──────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    """Lowercase, remove punctuation, collapse whitespace."""
    t = text.lower()
    t = re.sub(r"[^\w\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _terms_overlap(buyer_term: str, seller_tag: str) -> bool:
    """
    True if the buyer term and seller tag share significant word overlap.
    A buyer term like "minimalist dog mom mug" overlaps with seller tag
    "dog mom mug" because all words of the seller tag appear in the buyer term.
    """
    if not buyer_term or not seller_tag:
        return False
    # Exact match
    if buyer_term == seller_tag:
        return True
    # Substring match
    if seller_tag in buyer_term or buyer_term in seller_tag:
        return True
    # Word overlap: all words of shorter string in longer string
    buyer_words = set(buyer_term.split())
    seller_words = set(seller_tag.split())
    shorter = buyer_words if len(buyer_words) <= len(seller_words) else seller_words
    longer = seller_words if shorter is buyer_words else buyer_words
    if len(shorter) >= 2 and shorter.issubset(longer):
        return True
    # Partial word overlap: ≥50% of seller tag words in buyer term
    if len(seller_words) > 0:
        overlap = seller_words & buyer_words
        if len(overlap) / len(seller_words) >= 0.5:
            return True
    return False


def _build_entry_angle(
    keyword: str,
    untagged: list[str],
    dominant_style: str,
    style_gap: float,
) -> str:
    if untagged:
        top = untagged[0]
        return (
            f"Tag for '{top}' — buyers search it but zero top sellers use it as a tag. "
            f"First-mover advantage in a proven demand segment."
        )
    if style_gap >= 65 and dominant_style:
        return (
            f"All top listings use the '{dominant_style}' style. "
            f"Differentiate with an alternative aesthetic to capture buyers who want something different."
        )
    return f"Moderate tag gap for '{keyword}' — focus on long-tail variations underused by top sellers."
