# Data model

The page (`site/app.js`) is a pure renderer over ten JSON files in
`site/data/`. Two kinds of content are kept apart on purpose:

| File | What | Who edits it |
|---|---|---|
| `ballot.json` | Official facts: contests in ballot order, candidates, measure digests | **Generated.** Don't hand-edit; run `py tools/build_ballot.py` |
| `endorsements.json` | Other organizations' published picks | Hand-edited, each guide cited |
| `picks.json` | **Our** picks (Golden Goose Egg / Certified HONK) | Hand-edited, opinion |
| `zip_districts.json` | Which districts each SF ZIP overlaps | **Generated** by `tools/build_zip_districts.py` |
| `topics.json` | **Our** topic tags on measures (for browsing) | Hand-edited, editorial but factual |
| `funding.json` | Funding tags for groups and local candidates | **Generated** by `tools/funding_tags.py` |
| `money.json` | Local measure committees + top donors; outside spenders per candidate | **Generated** by `tools/money_flows.py` |
| `state_money.json` | State-prop support/oppose totals + committees (SoS official) | **Generated** by `tools/state_money.py` |
| `external_money.json` | State (Cal-Access) & federal (FEC) candidate money; judicial committees | **Generated** by `tools/candidate_money_external.py` |
| `analysis.json` | Plain-English tab text: measure "Average goose" + "TL;DR", candidate "Who?" + "Average goose" | Hand-written from official text / KQED only |

## Pipeline for `ballot.json`

```
official pamphlet PDF ──tools/extract_vip.py──────▶ data-src/vip_measures.json ─┐
voterguide.sos.ca.gov ──tools/extract_sos_props.py▶ data-src/sos_props.json ────┼─tools/build_ballot.py─▶ site/data/ballot.json
hand-curated ──────────────────────────────────────▶ data-src/ballot_skeleton.json ┘
```

- **`ballot_skeleton.json`** sets section and contest **order**, copied from the
  official Ballot Worksheet (pamphlet pp. 246–248). It also holds candidates
  (statewide: SoS Certified List; local: pamphlet statements) and the
  district a contest `applies` to (`{"sup": 8}`, `{"cd": 11}`, …).
- **Candidate order** is computed by `build_ballot.py` from the SoS
  randomized alphabet (`order: "statewide" | "sos_alphabet" | "county_draw"`).
  Each candidate needs a `surname` for sorting; set `surname_uncertain`
  when a compound name could sort either way.
- Re-run the extractors only when a source changes, then re-run the build.
- **Verifying against a real sample ballot:** `py tools/sample_ballot.py template
  --cd 11 --ad 17 --sup 8 --bart 8 > data-src/sample_ballots/<name>.csv`
  writes our current view of that ballot type as CSV
  (`id, contest, choice, designation, party`, top to bottom). Edit it to
  match the printed ballot exactly, then run `py tools/sample_ballot.py check
  <file>` to list differences and `--apply` to write them into the skeleton
  (`order: "verified"`; statewide offices get `verified_order_by_ad`
  because names rotate by Assembly District). Rebuild afterwards. The CSV
  lists what's *on* the ballot, never how anyone voted.

## `zip_districts.json`

Built by `.venv/Scripts/python tools/build_zip_districts.py` (needs `shapely`,
see `tools/requirements.txt`). It intersects Census ZCTA polygons with the
official district maps (DataSF Supervisor 2022, CA Assembly 2021 CRC, CA
Congressional AB 604 / Prop 50, BART 2022) and records, per ZIP, each
overlapping district and its share of the ZIP's in-SF area:
`{"94110": {"cd": [[11, 1.0]], "sup": [[9, 0.838], [8, 0.114], [10, 0.047]], …}}`.

The page auto-selects a district only when one holds ≥ 99.5% of the ZIP.
Otherwise it limits the picker to the overlapping districts and asks the
reader to choose, because area share says nothing about where a given voter
lives. Overlaps under 0.2% are dropped as digitizing slivers. Re-run if a
district map changes.

## `endorsements.json`

```jsonc
{
  "guides": [{ "id": "growsf", "name": "GrowSF", "short": "GrowSF", "kind": "Political club",
               "url": "…", "accessed": "2026-10-24", "about": "optional caveat" }],
  "positions": {
    "<contest id>": {
      "<guide id>": "yes" | "no"                          // measures, retention
                  | ["Name", …]                           // offices: names EXACTLY as on the ballot
                  | { "none": "No Recommendation" }        // explicit no-position, in their words
                  | { "picks": [...], "note": "…" }        // qualified pick
                  | { "vote": "yes", "note": "…" }
    }
  }
}
```

Each guide also carries `money` (a list of `{label, amount, period, source, note?}`,
or `{label, text}` when there's no number) and `members` (`{text, source?}`), both
rendered in the "Other groups included in this guide" panel, plus
`self_description` (`{text, source}`): the group describing itself, quoted
**verbatim** from its own site and shown as "In their words". Don't paraphrase
it or write one for them. If none can be found, set `self_description_missing`
to say why. Use public
records only (IRS 990s via ProPublica, SF Ethics, FEC, SoS registration) or
the group's own published claim, quoted. Never estimate.

Each guide has `tags` (`[{label, cat}]`) shown as colored pills on its card.
The first non-`scope` tag colors the card's edge and the dot on its ballot
chips. Categories and fixed hues: `environment` green, `labor` red, `business`
purple, `party` blue, `progressive` magenta, `growth` orange, `policy` teal,
`civic` gray, `scope` (e.g. "Statewide") outline only. Business is purple
because green, red, blue and amber are already spoken for (environment, labor,
party/Decrease, and Increase).

Absent = the guide didn't address the contest. Picks render as small chips
on the matching ballot row, and a pick's `note` renders as a muted footnote.
Explicit no-positions (`{"none": …}`) are recorded for completeness but not
displayed. The page logs a console warning for any name that isn't on the
ballot.

## `picks.json` — ours

Generated by `tools/import_picks.py` from **`data-src/picks_sf.csv`** (columns `id, contest, choice,
rating, position, source`), which is the file to edit. `rating` is `Golden Goose Egg`, `Certified HONK`
or blank. A blank rating becomes `"verdict": "note"`, an unrated **Goosebase take**; on a measure it gets
a `lean` (`yes`/`no`) read from its wording. Unrated text repeated across three or more candidates in a
contest becomes one contest-wide take with no `target`. `source` backs any factual claim in the text.
Every position was proofread and fact-checked against the guide's data before import (2026-10-24).

```jsonc
{ "picks": {
    "prop-h": [{ "verdict": "egg",  "reasoning": "…" }],                 // measure: egg = YES
    "prop-g": [{ "verdict": "honk", "reasoning": "…" }],                 // measure: honk = NO
    "sup-8":  [{ "verdict": "egg",  "target": "Darshini Patel", "reasoning": "…" },
               { "verdict": "honk", "target": "…", "reasoning": "…" }]  // offices: per candidate
} }
```

- **Golden Goose Egg** (`egg`) is positive and **Certified HONK** (`honk`) is
  negative. For measures and retention votes, egg means vote YES and honk
  means vote NO.
- Picks are hidden until the reader turns on "Show our picks". `reasoning`
  is required, and a pick may reference facts but never restate them as
  official.

## `topics.json` — our topic tags

```jsonc
{ "topics": [{ "id": "housing", "label": "Housing construction", "description": "…" }],
  "tags": { "prop-c": [{ "topic": "housing", "effect": "up", "why": "Raises the City's yearly…" }] } }
```

- Tags say what a vote **does**. Each one sits on the line of the vote that
  causes it (`on`: `"yes"`, the default, or `"no"`). `effect`: `up`
  raises/funds/expands, `down` cuts/limits, `stable` keeps an existing tax
  at today's level. They never say whether that's good.
- **Extending or making permanent an existing tax is `stable` on YES, not
  `up`.** The cut that happens if it lapses goes on the NO line as `down`.
  A brand-new tax is `up` on YES, and NO on it is just the status quo, so it gets
  no tag. A measure that only restricts *future* taxes is `limit`.
- **Tax tags** (`personal-tax`, `business-tax`) render as a neutral topic chip plus
  a colored effect chip (amber ↑ Increase, gray = Stable, blue ↓ Decrease, blue
  outline ⊘ Limits new taxes; deliberately not red/green). Below them is one quiet
  line built from `share` (roughly how many are affected, e.g. "Top ~2% of CA
  taxpayers", "~39% of SF households own their home") and `affects_if` (short,
  **single-filer** terms, e.g. "you're a single filer earning over ~$371K"). Both
  must come from the LAO analysis, the SF digest or Census figures. Every tag needs a factual `why` drawn from the
  official digest; readers see it on hover and in the measure's details.
- Keep it symmetric: taxes are tagged in both directions, and *Regressive tax*
  sits next to *Progressive tax*. A topic that only ever flags one side is
  a bias.
- Measures with no fitting topic stay untagged and drop out of filtered views.

## `funding.json` — evidence-based funding & housing tags

Built by `py tools/funding_tags.py [--since 2025-01-01]` from SF Ethics data
(DataSF `pitq-e56w`) for the committees mapped in `data-src/funding_entities.json`.
Only the latest version of each filing counts (no double-counted amendments),
and donors are aggregated by name + ZIP before sizing. Tags fire only past
published thresholds, and each one shows its number:

| Tag | Rule |
|---|---|
| Small-donor funded | ≥ 50% of money from donors totaling ≤ $100 (candidates) / ≤ $250 (groups), incl. unitemized |
| Big-donor funded (groups) | ≥ 50% from donors totaling ≥ $10,000 (candidates can't: SF caps gifts at $500) |
| Tech-funded | ≥ 25% from donors employed in tech/VC (explicit employer + occupation lists in the tool) |
| Outside money (candidates) | Other committees' supporting spending/giving (Sched. D + later Form 496) ≥ the candidate's own money and ≥ $10K |
| Pro-housing (YIMBY) | Candidate endorsed by YIMBY Action / SF YIMBY. Groups: housing is central to their own self-description |

There is deliberately no pejorative label. "Housing-skeptic" may only be applied
with a sourced position against new housing, and none has been applied yet.
Statewide and federal candidates aren't covered (their money isn't in SF Ethics data).

## Tabbed panels

Each measure has a **More about this measure** panel with four tabs: *What it
does* (official digest), *Money* (local: `money.json`; state:
`state_money.json`), *Average goose* and *Seriously TL;DR* (`analysis.json`,
plus the Goosebase position from `picks.json`, or "none yet").

Each candidate has a **More on …** panel with four tabs: *Who?*, *Money*
(`funding.json` contributions + public funds + `money.json` outside
spenders), *Average goose* and *Seriously TL;DR* (auto-built from the
description, the recommending groups and outside money, plus the Goosebase
position). Where we have no sourced text, the tab says so instead of
guessing.

`analysis.json` rules: measure text comes only from the digest, LAO analysis
and fiscal statements already cited on that measure. Candidate text is a
paraphrase of KQED's summaries, with a link. It stays neutral, and opinion
belongs in `picks.json`. Verification of outside research:
`docs/research-verification.md`.

## State & federal candidate money (`external_money.json`)

`py tools/candidate_money_external.py <dbwebexport.zip>` (or `--federal-only`):

- **State offices** come from the Secretary of State's Cal-Access **bulk export**
  (`https://campaignfinance.cdn.sos.ca.gov/dbwebexport.zip`, ~1.6 GB, updated
  daily). The Cal-Access website sits behind a bot wall, but the export is the
  sanctioned machine-readable copy. Each candidate's own committee is pinned in
  `data-src/state_committees.json`. Contributions = Form 460 Summary line 5
  (period column) summed over report periods since 2025-01-01, using the latest
  amendment and latest filing per period. Small-donor share = Schedule A
  unitemized ÷ total. Outside money = Form 496 independent expenditures naming the
  candidate, **grouped by the spender's filer ID** (committees vary their names).
- **Federal (House 11 & 15)**: FEC API totals and Schedule E independent
  expenditures for the 2025–26 cycle.
- **Judicial retention**: committees whose names pair a justice's surname with
  "justice", "court" or "retain". Common surnames make bare-name matches useless.
- `data-src/filing_notes.json` attaches a ⚠ note to a filing that looks wrong as
  filed (e.g. a support/oppose code that contradicts the filer's other reports).
  The data is never altered.

## Judges' tabs

Each retention contest has a **More about this justice** panel with four tabs:
*Who?* (official Court of Appeal biography or the state voter guide's statement),
*Money* (judicial committee scan), *Average goose* (what a retention vote does,
sourced to the voter guide and Cal. Const. art. VI §16) and *Seriously TL;DR*
(plus the Goosebase position).

## Reader state

District choices, marked ovals and toggles live in `localStorage`
(`sf-voter-guide.2026-11`). Nothing is sent anywhere. URL parameters
`?zip=94110` or `?cd=11&ad=17&sup=8&bart=8`, plus `&picks=1`, preselect a
ballot, which is handy for sharing a district-specific link. Section collapse
state is saved too.

## Other counties (early previews)

`?county=alameda` and `?county=sanmateo` load `site/data/counties/<id>/ballot.json`
(same schema as the SF ballot) and show an "early preview" banner whenever
`election.preview` is set. Everything else (`endorsements.json`, `analysis.json`,
`external_money.json`, `topics.json`) is shared and keyed by contest id, so the statewide
contests (offices, justices, propositions, RTM) and shared district ids (`us-rep-15`,
`assembly-19`) carry the SF guide's research automatically. County-only contests use a
`ala-` / `smc-` prefix and get no tabs until they are researched.

| Tool | Source | Output |
|---|---|---|
| `tools/county_alameda.py` | Registrar's candidate-list search (election 260, on ballot, filing completed) + the election page's measure list | `data-src/counties/alameda/{contests,measures}.json` |
| `tools/county_sanmateo.py <roster.pdf>` | Roster of Candidates PDF (smcacre.gov/media/8827; only `On Ballot: Yes` contests are used) + the election page's measure list | `data-src/counties/sanmateo/{roster,measures}.json` |
| `tools/build_county_ballot.py <county>` | the above + the SF build's statewide contests | `site/data/counties/<county>/ballot.json` |

Not verified yet: local candidate order (lists are in the county's list order), district
boundaries (no ZIP lookup; readers pick CD/AD/SD/city by hand), and local measure details
(titles only, linking the county's materials). Statewide offices get their Assembly-District
rotation recomputed for the county's ADs. Ranked-choice city contests (Oakland, Berkeley,
San Leandro, Albany) carry a note rather than an RCV grid. Guides appear in a county only if
their `covers` list includes it (statewide groups everywhere; Sierra Club SF Bay also
covers Alameda; the SF-only guides stay on the SF page).

### Deep dives (focus cities)

Focus cities: Oakland, Fremont, South San Francisco, San Mateo, Redwood City, and Richmond
(incl. Richmond Annex) in Contra Costa.

- `data-src/counties/<county>/measure_digests.json` holds hand-checked digests keyed by measure
  letter: exact ballot `question`, our `summary` of the impartial analysis, official `fiscal`
  estimate, `yes_means`/`no_means`, `threshold`, `args.for|against.{gist, signers}` (only legible,
  typed signer names) and `sources` (official PDFs). The builder merges them into the measure.
- `data-src/counties/<county>/candidate_profiles.json` holds `profiles[contest title][name]`, a
  neutral one-paragraph summary of the candidate's own statement in the official county guide,
  with `_sources`. It appears as the Who? line with a source link. `designations` fills ballot
  designations the county API lacks (Contra Costa).
- San Mateo County publishes candidate statements only in voters' personal sample-ballot
  pamphlets, so its focus-city races carry a `statement_note` saying so instead of profiles.
- Sources that are scans, or whose text layer is broken (Alameda's guide), are read with
  `tools/ocr_pdf.py`. Digests are written from that text and checked by hand; raw OCR is never
  published.

### Focus-city selectors

`election.focus` (from `FOCUS` in `tools/build_county_ballot.py`) gives each preview county
one-tap buttons for its focus cities. Picking one sets the city filter and hides that county's
school and special-district contests whose title/subtitle match none of the city's `serves`
patterns (the districts known to cover it). Ward-based districts stay in. A note says how many
were hidden, with a "Show them anyway" toggle (`state.trimDistricts`).

### County guides (third-party positions outside SF)

| Guide | Covers | Source | Tool |
|---|---|---|---|
| East Bay DSA (`ebdsa`) | Alameda, Contra Costa | vote.eastbaydsa.org race data (all local measures + its slate; statewide items credited to California DSA) | `tools/guide_eastbaydsa.py` → `data-src/guides/eastbaydsa_2026.json` |
| East Bay Young Democrats (`ebyd`) | Alameda, Contra Costa | ebyd.org/endorsements | hand transcription `data-src/guides/ebyd_2026.json` |
| YIMBY Action (`yimby`, county races) | all | endorsement data embedded in yimbyaction.org/endorsements | `data-src/guides/yimby_counties_2026.json` (`"mode": "merge"`) |
| Richmond Progressive Alliance (`rpa`) | Contra Costa | Richmondside report (no published slate) | `data-src/guides/rpa_2026.json` |
| LWV Oakland (`lwvoak`) | Alameda | ballot argument its president signed | `data-src/guides/lwvoak_2026.json` |

`tools/import_guides.py` merges every hand-transcribed file: contests by exact ballot title or id,
names matched to the ballot spelling, and any miss aborts the import. Group money comes from
`tools/group_money.py` (Cal-Access, committees listed in `data-src/group_committees.json`).
Statewide groups (`scope: "statewide"`) show in every county; local ones only where `covers` lists the county.

### Local measure money outside SF (`county_measure_money.json`)

Built by `tools/local_measure_money.py` from the Cal-Access bulk export. Local measure
committees file their reports with the city/county (NetFile: no open API, bot-challenged
portal; Oakland's open-data Form 460s lag to June 30), but every committee registers with
the Secretary of State and statewide committees report what they give them. Per measure:
the registered committees (matched on letter + place keyword across all registered name
variants; pins/excludes with reasons in `data-src/local_measure_committees.json`) and the
contributions state-filing committees report giving them (Schedule D + Form 497 part 2,
2025 on, latest amendments). Totals are floors and the page labels them "$X+" with a
caveat. Multi-measure committees appear under each measure, flagged as unsplittable.

Local amounts, best source first:
1. **NetFile "All Transactions" exports** (`efile_<AID>_2026.xlsx`, saved from the public portal;
   pass their paths to the tool): Form 460 line 5 per period (latest amendment) plus Form 497
   late contributions after the last period; donors from Schedule A. Exports so far: COAK, COA, CCC.
2. **NetFile's documented public API** (netfile.com/Connect2/api/swagger-ui): agency list, filer
   list (exact names by FPPC id), and transaction search with superseded amendments excluded.
   Gives itemized contributions only (Schedule A + C + 497 part 1, late reports deduped), so the
   page labels it "itemized; gifts under $100 aren't itemized". The yearly export endpoint is retired.
3. **Cal-Access** state-reported gifts as a floor ("$X+"). Gifts are deduped across Form 497 and
   the next 460 (Schedule D only), after a bug that double-counted them (e.g. CNA's $250K to Yes on EE).

South San Francisco and some small cities aren't on NetFile.

Focus cities also narrow the district pickers, like a ZIP in SF:
`tools/build_focus_districts.py` intersects each city's Census boundary with the official
Congressional (Prop 50), Assembly, Senate and BART maps and writes
`data-src/counties/focus_districts.json` (district + share of city area). The builder puts it in
`election.focus[].districts`; districts with no race this year fold into "Another district".
Picking a focus city auto-selects a district the city sits entirely inside, and hides races in
districts the city doesn't touch. San Mateo County's current supervisor map is private
(token-only; the public layer is the 2013 map), so Supervisor District 5 isn't narrowed.

### ZIP lookup in the counties

`tools/build_county_zips.py` writes `site/data/counties/<county>/zip_districts.json` (same shape as
SF's, plus `city` with 0 = unincorporated, and `schools`: the K-12 districts the ZIP touches) and
`site/data/zip_counties.json` (ZIP -> counties, so a ZIP typed on the wrong county's page links to
the right one). Sources: Census TIGERweb ZCTAs, counties, places and school districts, plus the
state district maps. K-12 school races (title or measure jurisdiction naming a school district)
are now filtered by the Census school districts a ZIP or focus city touches, matched on
distinctive words (`schoolKey`: "Redwood City School District" = "Redwood City Elementary School
District"; "high" is kept). This replaced the hand-written lists for K-12 and fixed a real miss:
part of South San Francisco is in the Jefferson Union High School District (Measure M). The
`serves` lists still cover community colleges and special districts.
