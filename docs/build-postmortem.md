# Build post-mortem — where the 13 hours went

Written 2026-11-04. Companion to [`next-cycle-plan.md`](next-cycle-plan.md),
which covers distribution timing. This one is about production cost: what was
expensive to build, why, and what to pre-build so the next cycle is faster.

`STATUS.md §5` already records the *correctness* gotchas and they are not
repeated here. This is the time-and-effort layer.

## Method, and its limits

54 commits, 2026-10-24 11:28 → 2026-10-26 00:06. Wall-clock span 36.6 hours.
Capping any single inter-commit gap at 45 minutes — so overnight and meal
breaks don't get attributed to whatever happened to be open — gives **14.2
attributable hours**, which lines up with the ~13-hour estimate.

Commit gaps undercount thinking that produced no commit and overcount
whatever was in flight when a break started. Directionally right, not precise.

## Where it went

| category | commits | hours | share |
|---|---|---|---|
| **Money data** | 10 | **4.1** | **29%** |
| Editorial picks | 8 | 2.6 | 18% |
| **Candidate descriptions** | 6 | **2.1** | **15%** |
| Ballot structure | 4 | 1.7 | 12% |
| County expansion | 6 | 1.5 | 10% |
| Stance tags | 1 | 0.8 | 5% |
| Frontend / UI | 8 | 0.7 | 5% |
| Endorsement groups | 7 | 0.6 | 4% |
| Docs | 4 | 0.2 | 1% |
| **total** | **54** | **14.2** | |

Three things stand out before any detail:

**Money and candidate descriptions together are 44% of the build — 6.2
hours.** Those are exactly the two the next cycle should attack.

**Frontend was 5%, 42 minutes.** Inheriting goosebase's design system
(`css/tokens.css`, `landing.css`, `subpage.css`) made the entire presentation
layer nearly free. Whatever else changes, keep that.

**Editorial picks were 18%, 2.6 hours — do not optimize this away.** 81 picks,
proofread and fact-checked, are the only thing the guide has that GrowSF and
the Chronicle's endorsement page do not. It is the product. It should probably
get a *larger* share of a faster build, not a smaller one.

## Money data — 4.1 hours, and the expensive part recurs

Four unrelated systems, one per jurisdiction level:

| level | system | access |
|---|---|---|
| SF local | SF Ethics (DataSF Socrata) | open API |
| state | Cal-Access bulk export | 1.6 GB download; the website is bot-walled, the export is not |
| federal | FEC API | needs `FEC_API_KEY` |
| county/city local | NetFile | open JSON API, **plus manual `.xlsx` exports** because the portal is Turnstile-walled |

What now exists and carries forward to 2028:

- the Cal-Access double-count rule (Schedule D + 497 part 2 only, deduped by
  giver/recipient/date/amount — the bug that showed Yes on EE at $865K instead
  of $475K)
- the amendment rule (latest filing per period, latest `AMEND_ID`)
- working clients for all four systems
- the output schemas

What has to be redone from scratch every cycle, and is where the hours
actually went:

- **committee ID discovery** — finding which committee belongs to which
  candidate or measure
- **committee name pinning** — committees get reused across campaigns and
  Cal-Access keeps the stale name ("Yes on T" for a 2026 W committee), so
  `data-src/local_measure_committees.json` has to be hand-pinned with reasons

That is the target. `tools/find_state_committees.py` already shows the right
pattern for one class — it *proposes* ids and checks them against the
cover-page district, so a human reviews a diff instead of searching. Generalize
that to local measure committees, local candidate committees and group PACs,
and the single largest line item becomes a review queue rather than a
scavenger hunt.

Two smaller, concrete carry-forwards:

- **Pre-request the NetFile exports in January.** `STATUS.md §2` item 3 still
  lists six agencies whose Form 460 totals need a manual portal download
  (Redwood City, City of San Mateo, San Mateo County, Richmond, Berkeley,
  Fremont). Each one blocks a Money tab. They are a dependency with human
  latency, so they belong at the *start* of the build, not the middle.
- **RTM money was never covered** (`STATUS.md §2` item 2) — every county's
  Money tab still says "not covered" for it.

## Candidate descriptions — coverage was decided by the county, not by effort

This is the clearest finding in the whole post-mortem. From `STATUS.md §1`:

| county | candidates with a profile or statement | where it came from |
|---|---|---|
| Alameda | **77%** | official county statements |
| Contra Costa | **68%** | official county statements |
| SF | 47% | KQED + the pamphlet |
| San Mateo | **0%** | the county publishes none |

Alameda and Contra Costa reached 77% and 68% from **one script each**
(`tools/county_statements_alameda.py`,
`tools/county_statements_contracosta.py`). San Mateo returned zero — and not
for lack of trying. Every fallback is closed: San Mateo Daily Journal 403,
cityofsanmateo.org TLS refusal, ssfca.gov 403, Inquirer USA 403, and
Hoodline's local coverage is AI-assisted so it doesn't qualify as a source.
One race (Sequoia Union HSD, 4 candidates) got done from The Almanac.

So candidate-description coverage is a **property of the county**, not a
function of hours spent. Where the county publishes statements, one script
gets ~70%. Where it doesn't, no amount of work produces anything publishable
without the user hand-saving pages one at a time.

### The fix: a one-hour source pre-flight decides scope

Before committing to include a county, answer two questions:

1. **Does the county publish candidate statements online, in bulk?**
2. **Is there a contest/measure API, or only PDFs and scans?**

Scored against 2026:

| county | statements? | contests? | verdict |
|---|---|---|---|
| Contra Costa | yes | JSONP API with full official measure text | **cheap** |
| Alameda | yes | POST-form candidate search; VIG PDF text layer is garbled, needs OCR | **moderate** |
| SF | partial | skeleton + pamphlet | **moderate** (it's the home county; include regardless) |
| San Mateo | **no** | roster is a PDF, measure docs are mostly scans | **expensive, low yield** |

San Mateo failed both tests and should have been scoped out — or included
measures-only, with no candidate tab at all, which is an honest product rather
than a 0% column. Run this audit in December 2027 when filing closes, and let
it pick the county list.

## The per-county scaling cost is script duplication

28 scripts, 207 KB of Python. Six of them are one-per-source scrapers, so
**each new county costs roughly two new scripts.**

All three contest scrapers have the identical shape — `fetch_candidates()` and
`fetch_measures()` writing `contests.json` + `measures.json` into
`data-src/counties/<county>/` — and differ only in transport: Alameda a POST
form with a session cookie, San Mateo a roster PDF, Contra Costa a JSONP API.

The duplication has already caused a live divergence. `titlecase_name` is
defined twice, differently, and `NAME_FIXES` lives in a third file
(`build_county_ballot.py`) that neither scraper imports. Running both on the
same inputs:

| input | `county_alameda.py` | `county_sanmateo.py` |
|---|---|---|
| `SUE "SUSIE" WONG` | `Sue "Susie" Wong` | **`Sue "susie" Wong`** |
| `ROBERT (BOB) LEE` | `Robert (Bob) Lee` | `Robert (Bob) Lee` |
| `JOHN SMITH JR.` | `John Smith JR.` | `John Smith JR.` |

Alameda's version grew a quoted-nickname branch (commit `Alameda: fix party
labels and quoted nicknames`); San Mateo's grew a `JR./SR.` branch instead.
Neither has both, so a quoted nickname on a San Mateo ballot renders
lowercase. Neither produces `Jr.` either — that is patched downstream by
`NAME_FIXES`, name by name.

**Recommendation:** extract a `county_source` protocol — two functions,
`fetch_candidates()` and `fetch_measures()` — with name normalization,
`NAME_FIXES` and the JSON writer in one shared module that every adapter and
`build_county_ballot.py` imports. A new county then becomes one ~60-line
adapter instead of a ~130-line standalone script with its own drifting copy of
the shared helpers.

## What to pre-build, before any 2028 data exists

Ordered by hours saved per hour spent. All of it can be done now, while the
context is fresh, and none of it depends on knowing the ballot.

1. **Source pre-flight checklist**, run per county, output is a go/no-go on
   inclusion. Cheapest item here and it governs everything else.
2. **`county_source` protocol + shared normalization module.** Collapses the
   duplication and kills the title-casing divergence.
3. **Committee-ID proposer for all committee classes**, following
   `find_state_committees.py`. Attacks the single largest line item.
4. **Pre-request the six outstanding NetFile exports** so they aren't a
   mid-build blocker.
5. **Freeze the 2026 build as a regression fixture** — the data is correct and
   fact-checked today, and it is the only test case the pipeline will ever have
   until the next ballot exists. This expires: do it before the county portals
   roll over.

## Rough target for 2028

Baseline: 14.2 hours for 4 counties and 466 contests.

| category | 2026 | plausible 2028 | how |
|---|---|---|---|
| Money data | 4.1 | ~2.0 | committee-ID proposer; exports pre-requested |
| Candidate descriptions | 2.1 | ~1.0 | pre-flight scopes out the 0% counties |
| County expansion | 1.5 | ~0.7 | shared adapter protocol |
| Ballot structure | 1.7 | ~1.2 | adapters reused |
| Editorial picks | 2.6 | **2.6** | unchanged, deliberately — this is the product |
| everything else | 2.2 | ~1.5 | |
| **total** | **14.2** | **~9** | |

But the hours are the secondary prize. The real change is *when* they get
spent: `next-cycle-plan.md` puts the live deadline at **Feb 4, 2028**, three
days before ballots mail. A 9-hour build that starts in January comfortably
makes that date. A 14-hour build started the week before does not — which is
precisely what happened in 2026.
