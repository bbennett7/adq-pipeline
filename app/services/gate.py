import logging
from dataclasses import dataclass, field

from app.models.candidates import GeneratedCandidate

logger = logging.getLogger(__name__)


@dataclass
class GatedCandidate:
    """A candidate that survived the similarity gate.

    near_repeat_of is set when the candidate was over threshold but got
    backfilled to keep the slate at the floor — the owner should see the flag.
    """

    candidate: GeneratedCandidate
    near_repeat_of: str | None = None


@dataclass
class GateOutcome:
    kept: list[GatedCandidate] = field(default_factory=list)
    dropped: int = 0


def apply_gate(
    candidates: list[GeneratedCandidate],
    results: list[dict] | None,
    threshold: float,
    floor: int,
) -> GateOutcome:
    """Drop near-repeat candidates using Ground Ctrl similarity results.

    Two checks, both against `threshold`:
    - corpus: similarity to any already-published question or already-offered
      candidate;
    - sibling: similarity to a same-batch candidate (three models often
      converge on one question). For a sibling pair, the member with the
      higher corpus similarity is dropped — the more novel one survives.
      Processing in descending corpus order guarantees one survivor per pair.

    If fewer than `floor` survive, the least-similar dropped candidates are
    backfilled with a near-repeat flag rather than thinning the slate.

    `results` is None when the similarity check itself failed — fail open and
    keep everything.
    """
    if results is None or len(results) != len(candidates):
        if results is not None:
            logger.warning(
                "Similarity results length %d != candidates %d, skipping gate",
                len(results),
                len(candidates),
            )
        return GateOutcome(kept=[GatedCandidate(c) for c in candidates])

    corpus_sim = [r.get("corpusSimilarity") or 0.0 for r in results]
    dropped: dict[int, str] = {}  # index -> what it repeats

    # Corpus repeats first.
    for i, r in enumerate(results):
        if corpus_sim[i] > threshold:
            match = r.get("corpusMatch") or "an earlier question"
            dropped[i] = match
            logger.info(
                "Gate: dropping corpus repeat (%.3f): %r ~ %r",
                corpus_sim[i],
                candidates[i].question_md[:80],
                match[:80],
            )

    # Sibling convergence: worst corpus-similarity first, so the more novel
    # member of each pair is the one that survives.
    for i in sorted(range(len(candidates)), key=lambda k: -corpus_sim[k]):
        if i in dropped:
            continue
        r = results[i]
        sib_sim = r.get("siblingSimilarity")
        sib_idx = r.get("siblingIndex")
        if (
            sib_sim is not None
            and sib_sim > threshold
            and sib_idx is not None
            and sib_idx not in dropped
        ):
            dropped[i] = candidates[sib_idx].question_md
            logger.info(
                "Gate: dropping sibling repeat (%.3f): %r ~ %r",
                sib_sim,
                candidates[i].question_md[:80],
                candidates[sib_idx].question_md[:80],
            )

    kept = [GatedCandidate(c) for i, c in enumerate(candidates) if i not in dropped]

    # Backfill to the floor with the least-similar dropped candidates.
    if len(kept) < floor and dropped:
        backfill_order = sorted(dropped, key=lambda k: corpus_sim[k])
        for i in backfill_order:
            if len(kept) >= floor:
                break
            kept.append(GatedCandidate(candidates[i], near_repeat_of=dropped[i]))
            logger.info(
                "Gate: backfilling flagged near-repeat to reach floor: %r",
                candidates[i].question_md[:80],
            )

    outcome = GateOutcome(kept=kept, dropped=len(candidates) - len(kept))
    logger.info(
        "Gate: %d/%d candidates kept (%d dropped, %d flagged)",
        len(outcome.kept),
        len(candidates),
        outcome.dropped,
        sum(1 for k in outcome.kept if k.near_repeat_of),
    )
    return outcome
