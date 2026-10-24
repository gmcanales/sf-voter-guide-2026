# Data model

The page (`site/app.js`) is a pure renderer over five JSON files in
`site/data/`. Two kinds of content are kept apart on purpose:

| File | What | Who edits it |
|---|---|---|
| `ballot.json` | Official facts: contests in ballot order, candidates, measure digests | **Generated.** Don't hand-edit; run `py tools/build_ballot.py` |
| `endorsements.json` | Other organizations' published picks | Hand-edited, each guide cited |
| `picks.json` | **Our** picks (Golden Goose Egg / Certified HONK) | Hand-edited, opinion |
| `zip_districts.json` | Which districts each SF ZIP overlaps | **Generated** by `tools/build_zip_districts.py` |
| `topics.json` | **Our** topic tags on measures (for browsing) | Hand-edited, editorial but factual |

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

Absent = the guide didn't address the contest. Picks render as small chips
on the matching ballot row, and a pick's `note` renders as a muted footnote.
Explicit no-positions (`{"none": …}`) are recorded for completeness but not
displayed. The page logs a console warning for any name that isn't on the
ballot.

## `picks.json` — ours

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

## Reader state

District choices, marked ovals and toggles live in `localStorage`
(`sf-voter-guide.2026-11`). Nothing is sent anywhere. URL parameters
`?zip=94110` or `?cd=11&ad=17&sup=8&bart=8`, plus `&picks=1`, preselect a
ballot, which is handy for sharing a district-specific link. Section collapse
state is saved too.
