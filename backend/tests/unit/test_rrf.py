"""T6 tests: Reciprocal Rank Fusion. score(d) = sum over lists of 1 / (k + rank), rank starting at 1."""
import pytest

from app.retrieval.rrf import reciprocal_rank_fusion
from app.retrieval.types import RetrievedChunk


def chunk(chunk_id: str, score: float = 0.0, text: str = "") -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id, doc_id=chunk_id, source_name="MedlinePlus", title=chunk_id.upper(),
        url=f"https://medlineplus.gov/{chunk_id}.html", text=text or f"text {chunk_id}",
        retrieved_at="2026-10-31", licence="Public domain", attribution="Courtesy of MedlinePlus",
        score=score,
    )


def ids(chunks: list[RetrievedChunk]) -> list[str]:
    return [c.chunk_id for c in chunks]


def test_single_list_keeps_its_order_and_gets_rrf_scores():
    fused = reciprocal_rank_fusion([[chunk("a"), chunk("b"), chunk("c")]])
    assert ids(fused) == ["a", "b", "c"]
    assert [c.score for c in fused] == pytest.approx([1 / 61, 1 / 62, 1 / 63])


def test_a_chunk_found_by_both_retrievers_beats_one_found_by_one():
    bm25 = [chunk("x"), chunk("shared")]
    dense = [chunk("y"), chunk("shared")]
    fused = reciprocal_rank_fusion([bm25, dense])
    assert fused[0].chunk_id == "shared"
    assert fused[0].score == pytest.approx(2 / 62)


def test_known_example_with_ties_broken_by_first_appearance():
    first = [chunk("a"), chunk("b"), chunk("c")]
    second = [chunk("c"), chunk("d"), chunk("a")]
    fused = reciprocal_rank_fusion([first, second])
    # a = 1/61 + 1/63 = c; b = 1/62 = d. Ties keep the order chunks first appeared in.
    assert ids(fused) == ["a", "c", "b", "d"]
    assert fused[0].score == pytest.approx(1 / 61 + 1 / 63)
    assert fused[2].score == pytest.approx(1 / 62)


def test_k_is_configurable():
    fused = reciprocal_rank_fusion([[chunk("a"), chunk("b")]], k=1)
    assert [c.score for c in fused] == pytest.approx([1 / 2, 1 / 3])


def test_original_scores_are_ignored_because_bm25_and_cosine_are_not_comparable():
    bm25 = [chunk("a", score=17.4), chunk("b", score=3.0)]
    dense = [chunk("b", score=0.91), chunk("a", score=0.12)]
    fused = reciprocal_rank_fusion([bm25, dense])
    assert fused[0].score == pytest.approx(fused[1].score)


def test_chunk_data_is_kept_and_each_chunk_appears_once():
    fused = reciprocal_rank_fusion([[chunk("a", text="from bm25")], [chunk("a", text="from dense")]])
    assert len(fused) == 1
    assert fused[0].text == "from bm25"
    assert fused[0].title == "A" and fused[0].attribution == "Courtesy of MedlinePlus"


def test_a_chunk_repeated_inside_one_list_counts_once_at_its_best_rank():
    fused = reciprocal_rank_fusion([[chunk("a"), chunk("b"), chunk("a")]])
    assert ids(fused) == ["a", "b"]
    assert fused[0].score == pytest.approx(1 / 61)


def test_chunks_found_by_only_one_retriever_are_included():
    fused = reciprocal_rank_fusion([[chunk("a")], []])
    assert ids(fused) == ["a"]


def test_empty_input_gives_empty_output():
    assert reciprocal_rank_fusion([]) == []
    assert reciprocal_rank_fusion([[], []]) == []


def test_top_n_limits_the_result():
    fused = reciprocal_rank_fusion([[chunk("a"), chunk("b"), chunk("c")]], top_n=2)
    assert ids(fused) == ["a", "b"]


def test_input_lists_are_not_modified():
    original = [chunk("a", score=5.0), chunk("b", score=4.0)]
    reciprocal_rank_fusion([original])
    assert [c.score for c in original] == [5.0, 4.0]


@pytest.mark.parametrize("k", [0, -1])
def test_k_must_be_positive(k):
    with pytest.raises(ValueError):
        reciprocal_rank_fusion([[chunk("a")]], k=k)


@pytest.mark.parametrize("top_n", [0, -3])
def test_top_n_must_be_positive(top_n):
    with pytest.raises(ValueError):
        reciprocal_rank_fusion([[chunk("a")]], top_n=top_n)
