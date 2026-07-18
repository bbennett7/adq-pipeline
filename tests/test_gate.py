from app.models.candidates import Agent, GeneratedCandidate
from app.services.gate import apply_gate

_A = "**Answer** text that is comfortably long enough to satisfy the model validation rules."


def _candidate(q: str) -> GeneratedCandidate:
    return GeneratedCandidate(agent=Agent.CLAUDE, question_md=q, answer_md=_A)


def _result(corpus=None, match=None, sib=None, sib_idx=None) -> dict:
    return {
        "corpusSimilarity": corpus,
        "corpusMatch": match,
        "corpusSource": "question" if match else None,
        "siblingSimilarity": sib,
        "siblingIndex": sib_idx,
    }


CANDIDATES = [
    _candidate("What is a **_token_** in AI, and why does everyone keep counting them?"),
    _candidate("Why does AI need so much **_water_** to keep its data centers running?"),
    _candidate("How do **_tokens_** decide what AI costs when you use it every day?"),
]


def test_fail_open_when_results_none():
    outcome = apply_gate(CANDIDATES, None, threshold=0.78, floor=3)
    assert len(outcome.kept) == 3
    assert outcome.dropped == 0
    assert all(k.near_repeat_of is None for k in outcome.kept)


def test_fail_open_on_length_mismatch():
    outcome = apply_gate(CANDIDATES, [_result()], threshold=0.78, floor=3)
    assert len(outcome.kept) == 3


def test_drops_corpus_repeats():
    results = [
        _result(corpus=0.85, match="What is a token?"),
        _result(corpus=0.30),
        _result(corpus=0.40),
    ]
    outcome = apply_gate(CANDIDATES, results, threshold=0.78, floor=1)
    assert len(outcome.kept) == 2
    assert outcome.dropped == 1
    kept_questions = [k.candidate.question_md for k in outcome.kept]
    assert CANDIDATES[0].question_md not in kept_questions


def test_sibling_pair_keeps_more_novel_member():
    # Candidates 0 and 2 converge; 0 is closer to the corpus, so 2 survives.
    results = [
        _result(corpus=0.60, sib=0.85, sib_idx=2),
        _result(corpus=0.30, sib=0.40, sib_idx=0),
        _result(corpus=0.45, sib=0.85, sib_idx=0),
    ]
    outcome = apply_gate(CANDIDATES, results, threshold=0.78, floor=1)
    kept_questions = [k.candidate.question_md for k in outcome.kept]
    assert CANDIDATES[0].question_md not in kept_questions
    assert CANDIDATES[2].question_md in kept_questions
    assert len(outcome.kept) == 2


def test_backfills_to_floor_with_flags():
    results = [
        _result(corpus=0.90, match="repeat one"),
        _result(corpus=0.80, match="repeat two"),
        _result(corpus=0.85, match="repeat three"),
    ]
    outcome = apply_gate(CANDIDATES, results, threshold=0.78, floor=3)
    assert len(outcome.kept) == 3
    # Backfilled in ascending similarity: 0.80 first, then 0.85, then 0.90.
    assert [k.near_repeat_of for k in outcome.kept] == [
        "repeat two",
        "repeat three",
        "repeat one",
    ]


def test_no_flags_when_under_floor_not_triggered():
    results = [
        _result(corpus=0.20),
        _result(corpus=0.90, match="a repeat"),
        _result(corpus=0.30),
    ]
    outcome = apply_gate(CANDIDATES, results, threshold=0.78, floor=2)
    assert len(outcome.kept) == 2
    assert all(k.near_repeat_of is None for k in outcome.kept)
