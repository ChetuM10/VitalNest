"""Small, pure metric helpers for the retrieval evaluation."""
import re


def first_rank(ranked_titles: list[str], expected: set[str]) -> int | None:
    """1-based position of the first retrieved chunk whose page is an expected one, else None."""
    for position, title in enumerate(ranked_titles, start=1):
        if title in expected:
            return position
    return None


def hit_rate(ranks: list[int | None], k: int) -> float:
    """Share of questions whose first expected page appears within the top k chunks."""
    if not ranks:
        return 0.0
    return sum(1 for r in ranks if r is not None and r <= k) / len(ranks)


def mean_reciprocal_rank(ranks: list[int | None]) -> float:
    if not ranks:
        return 0.0
    return sum(1.0 / r for r in ranks if r is not None) / len(ranks)


def fact_coverage(texts: list[str], facts: list[str]) -> float:
    """Share of key facts found in the retrieved text. A fact may list alternatives with '|'."""
    if not facts:
        return 1.0
    blob = "\n".join(texts).casefold()
    found = sum(1 for fact in facts if re.search("|".join(re.escape(p.strip().casefold()) for p in fact.split("|")), blob))
    return found / len(facts)


def threshold_report(answerable: list[float], unanswerable: list[float]) -> dict:
    """How well a single score cutoff separates answerable from unanswerable questions."""
    low, high = min(answerable), max(unanswerable)
    separable = low > high
    suggested = round((low + high) / 2, 3) if separable else round(low - 0.005, 3)
    return {
        "lowest_answerable": low,
        "highest_unanswerable": high,
        "separable": separable,
        "suggested": suggested,
        "false_refusals_at_suggested": sum(1 for s in answerable if s < suggested),
        "false_answers_at_suggested": sum(1 for s in unanswerable if s >= suggested),
    }
