# Investigation Engine 4.0 — audit and first implementation

Baseline: 3669d83739ac6f2ebaee044f15ffd15d3bc3dc14, Ghost Letters 3.1.0 / bots 3.7.0. The human archive supplied for diagnosis predates this baseline (last game 2.14.1 / bots 3.6.0). Across 11 archived games, 28/33 clues were solved, but only 3/11 killers arrested. These are observations, not a controlled comparison.

## Decisions
- Preserve card IDs, rules, role knowledge boundaries, saves and current UI. Easy retains simpler decisions, but shares the improved deck associations.
- Association: distinguish functional relations, discount common tags, collapse correlated tags, keep symmetry and a bounded scale. Explicit links are general deck semantics, not seed-specific rules. No external LLM or network.
- Public evidence: no arbitrary age decay at adaptive difficulty. Unopened mail remains inconclusive. Ghost coverage is the gap after accumulating evidence, not the sum of per-letter worst gaps.
- Ghost: evaluate leading rival and log-odds of the whole row, penalize dangerous cross-category regressions, prevent a social correction or confirmation bonus from masking a loss, recycle a stale hand if stuck. No new mid-game deck access.
- Mail: prefer distinctive associations in uncertain categories, penalize stronger cross-category distraction.
- Social: distinguish tentative statements from endorsed versions; use stable small tie-break noise; consensus is not evidence; constructive revision can mitigate at most half of soft penalties and never offset verified contradictions. Discourse contrasts competing public theories; bot stance follows evidence. Public dossier must not present agreement as proof of innocence.
- Keep game victory rules unchanged; report clue-solving and arrest metrics independently.
- Existing initial-deal balancing is retained and should be separately benchmarked for fairness. A full blind information-set model, structured follow-up dialogue and complete manual review of every card artwork are future work, not claimed by this patch.

## Validation
Regression tests for association contrast, combined evidence, tentative leads, non-expiring public evidence and no immunity from revision. Existing tests still run. CI compares 500 matched seeds for base and candidate and uploads raw results. All-bot benchmark is not an estimate of human win rates; evaluate difficulty, seat count, marks, and both investigation outcomes. Never tune to one seed.

## Social evidence extension
- Symmetric disputed mail claims are now visible in the public dossier; observer's own receipt can verify a conflict, without revealing other receipts.
- Repeated confident opposition followed by a visible adoption of that theory is a capped weak lead, never proof of causality or guilt; tests and tentative statements are excluded.
- Discussion asks for specific grounds when theories diverge. Witness can cautiously express suspicion without fabricating evidence. Counter-accusation weighs correct expert guesses before they become obvious.
- Benchmark includes explicit special-role modes, incorrect unanimous theories, arrest-vote accuracy, and reasoned accusation counts.
