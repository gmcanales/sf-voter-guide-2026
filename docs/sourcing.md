# Sourcing rules

A voter guide that's wrong about a fact is worse than no guide. These rules
apply to every line in `site/data/ballot.json`.

## Tier 1 — authoritative (use for ballot facts)

- **SF Department of Elections** — official candidate list, ballot
  designations, measure text, Voter Information Pamphlet (VIP), the
  Ballot Simplification Committee digests, the official proponent and
  opponent arguments, and the Controller's financial analysis.
- **CA Secretary of State** — statewide propositions, the Official Voter
  Information Guide, and the Legislative Analyst's (LAO) analyses.
- **SF Ethics Commission** and **Cal-Access / SoS Power Search** — campaign
  finance. Always record an `as_of` date; totals move daily before an
  election.

## Tier 2 — context (attribute it, don't state it as fact)

Local journalism (SF Standard, Mission Local, SF Chronicle, KQED, CalMatters)
and endorsement slates. Use these for context and for arguments, always
attributed. Never use them as the source for a ballot fact.

## Hard rules

1. **No unsourced claims.** A contest without `sources[]` doesn't ship.
2. **Verbatim where it's official.** Candidate names, ballot designations and
   measure titles are copied exactly from the official ballot, never
   paraphrased.
3. **Steelman both sides.** Each `arguments.for` / `against` should be the
   strongest honest version of that side, ideally drawn from the official
   VIP arguments.
4. **Picks are separate.** Reasoning in `pick` may be opinionated; `summary`,
   `yes_means`, `no_means` and `arguments` may not.
5. **Don't guess.** If a fact can't be confirmed yet (late filings, recount,
   litigation), say so in the text instead of filling the gap.
