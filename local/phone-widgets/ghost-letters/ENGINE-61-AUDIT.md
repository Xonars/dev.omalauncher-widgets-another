# Investigation Intelligence 6.1

Base: Ghost Letters 3.6.0 / engine 6.0.0. The latest supplied case was played with engine 5.2; this change deliberately retains v6 seat order, public follow-ups and runoff rules.

## Public evidence and conversation
- Repeated claims and cards publicly revealed in incompatible rounds remain valid contradictions. No third-party private receipt is read.
- A newly discovered contradiction is reviewed after the last speaker and before voting. A local player's answer is never fabricated.
- Questions are remembered per target, category and competing cards. A substantially new distinguishing hint may reopen the question.
- Two unsupported changes after a prior public question are a bounded inquiry signal, not proof. Testimony-only statements and evidence-supported revisions do not count.
- A hostile bot will not reuse an already publicly claimed card when choosing a false account.

## Ghost and associations
- When public opinions are empty, consider the strongest evidence-based rival in the safe complementary-hint fallback.
- Keep the existing collateral-harm check and legal one-card discard; do not force a misleading hint or search the hidden deck.
- Track no-safe-hint situations in analytics.
- 83 explicit semantic links added, with stable card IDs, and selected cultural tags corrected. All 131 names reviewed for obvious associations; this is a targeted precision pass, not a validated exhaustive semantic taxonomy or a balance guarantee.

## Verification
Added regression tests for public claim review, memory, unsupported switches and semantic precision.
The resource bundle must be regenerated before merge. Run full CI and test multiple human games; evaluate false accusations, ghost stalls and discussion diversity. No win-condition changes.
