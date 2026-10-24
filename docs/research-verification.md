# Verification of `california_ballot_guide_research_v2.md` (2026-10-24)

The owner supplied a research document (810 lines: local money, D8/D10
candidate profiles, statewide proposition finance) plus a funding-network map
(held for later). Nothing from it was published until it had been checked
against primary data. Results:

## Links (57 checked)

- 54 resolve. Two `campaign.sfethics.org/.../contributors/` and
  `/independent-expenditures/` URLs with a trailing slash return 404 (the
  no-slash forms work). `sfsocialhousing.org` rate-limited us (429), so
  San Franciscans for Social Housing endorsements are **unverified**.
- **`growdsasf.org` is a lookalike domain** that mirrors GrowSF pages. Its
  ownership is unknown. Cite only `growsf.org`.

## Local money: recomputed from SF Ethics raw data (DataSF `pitq-e56w`)

| Claim | Recomputed | Verdict |
|---|---|---|
| Prop H top donors: Visa, OpenAI, Ripple, Anthropic, Airbnb committee $500K each; SF Forward $499K; Lawson $350K | identical | ✅ |
| Yes on H committee ≈ $5.14M | $5.12M | ✅ (window) |
| D/E/F committee > $13M; Larsen + Lam ≈ $2.5M; Pritzker $1M | $13.07M; $1.49M + $1.0M; $1.0M | ✅ |
| Moritz "more than $3M" to D/E/F | $2.99M in this committee's filings ($3.47M is the dashboard's all-measure total) | ⚠ wording |
| SF Believes → Wong $409,908; Sherrill $233,231 | identical | ✅ |
| GrowSF → Yekutiel $125,244; vs McCoy $23,011; vs Eppler $3,200 | identical | ✅ |
| GrowSF → Ellington $219,663; Tung/Garibay/Kim; BWSF → McCoy $433,086 | higher now (+ later 24-hour reports after Oct 17) | ✅ superseded |
| Candidate totals (McCoy ≈ $360K, Ellington $490K, Yekutiel ≈ $790K) | contributions **+ public financing** ($239K / $255K / $255K) | ✅ once public funds are counted |
| Prop G ≈ $1.76M | $0.97M across the two committees we map | ⚠ dashboard likely counts another committee |

This check found and fixed two bugs in our own tools:
1. Candidate name matching missed nicknames and initials ("Manny", "JR"),
   which hid Yekutiel's and Eppler's outside spending.
2. The "Outside money" tag ignored **public financing**. Patel lost the tag
   once her $119K in public funds counted.

## Statewide money: Secretary of State official totals

Props 40/41/42 match the SoS to the dollar. For the other props the
document used **FPPC top-contributor aggregates**, which aren't comparable
(e.g. Prop 44 opposition $17.5M there vs **$38.6M** official). The guide uses
SoS totals for every prop (`tools/state_money.py`). They also show Prop 4 with
$985K in support, which the document's table omits.

## Candidate claims

- KQED (D8, D10, CD11, school board) supports most attributed positions and
  supporter lists.
- **Not on KQED's page, so not published:** "McCoy supports the Family
  Zoning Plan and lowering the inclusionary rate" and "Nguyen opposed" them.
- KQED lists two D10 candidates missing from our list (Ellsworth "Ell"
  Jennison Jr., Jamo Muhammad). Both are added and flagged as unconfirmed
  on a sample ballot. KQED omits Jessica Pessecow, who filed an official
  pamphlet statement.

## What the guide now uses

`tools/money_flows.py` → `site/data/money.json` (local committees and outside
spenders), `tools/state_money.py` → `site/data/state_money.json`,
`tools/funding_tags.py` (+ public funds, DataSF `5sxz-kk66`), and
`site/data/analysis.json` (plain-English tabs, written from official text
and KQED only).
