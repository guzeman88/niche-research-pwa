"""Tag coverage observations without heuristic opportunity scores."""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field


@dataclass
class TagGapReport:
    keyword: str
    autocomplete_terms: list[str] = field(default_factory=list)
    tag_frequency: dict[str, int] = field(default_factory=dict)
    dominant_cluster: str = ""
    dominant_cluster_pct: float | None = None
    untagged_searches: list[str] = field(default_factory=list)
    partial_tag_matches: list[str] = field(default_factory=list)
    tag_gap_score: float | None = None
    style_gap_score: float | None = None
    composite_gap_score: float | None = None
    recommended_tags: list[str] = field(default_factory=list)
    entry_angle: str = ""


def analyze_tags(
    keyword: str,
    autocomplete_terms: list[str],
    listing_tag_sets: list[list[str]],
) -> TagGapReport:
    """Record literal buyer-term/tag coverage; scoring requires a versioned model."""
    report = TagGapReport(keyword=keyword, autocomplete_terms=autocomplete_terms)
    if not listing_tag_sets:
        report.entry_angle = f"Tag coverage is TBD for '{keyword}' because no listing tags were observed."
        return report

    counter: Counter[str] = Counter()
    for tag_list in listing_tag_sets:
        for tag in tag_list:
            normalized = _normalize(tag)
            if normalized:
                counter[normalized] += 1
    report.tag_frequency = dict(counter.most_common())

    if counter:
        top_tag, top_count = counter.most_common(1)[0]
        report.dominant_cluster = top_tag
        report.dominant_cluster_pct = round(top_count / len(listing_tag_sets) * 100, 1)

    root = _normalize(keyword)
    untagged: list[str] = []
    for term in autocomplete_terms:
        normalized_term = _normalize(term)
        if not normalized_term or normalized_term == root:
            continue
        has_match = any(
            _terms_overlap(normalized_term, _normalize(tag))
            for tag_list in listing_tag_sets
            for tag in tag_list
        )
        if not has_match:
            untagged.append(term)

    report.untagged_searches = untagged
    report.recommended_tags = list(dict.fromkeys(untagged))
    if untagged:
        report.entry_angle = (
            f"Observed autocomplete term '{untagged[0]}' had no matching tag in "
            f"{len(listing_tag_sets)} sampled listing tag set(s)."
        )
    else:
        report.entry_angle = (
            f"No uncovered autocomplete terms were observed for '{keyword}' in "
            f"{len(listing_tag_sets)} sampled listing tag set(s)."
        )
    return report


def _normalize(text: str) -> str:
    normalized = re.sub(r"[^\w\s]", " ", text.lower())
    return re.sub(r"\s+", " ", normalized).strip()


def _terms_overlap(buyer_term: str, seller_tag: str) -> bool:
    if not buyer_term or not seller_tag:
        return False
    if buyer_term == seller_tag or seller_tag in buyer_term or buyer_term in seller_tag:
        return True
    buyer_words = set(buyer_term.split())
    seller_words = set(seller_tag.split())
    return bool(buyer_words and seller_words) and (
        buyer_words.issubset(seller_words) or seller_words.issubset(buyer_words)
    )
