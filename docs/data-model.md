# Data model

The page (`site/app.js`) is a pure renderer over three JSON files in
`site/data/`. Two kinds of content are kept apart on purpose:

| File | What | Who edits it |
|---|---|---|
| `ballot.json` | Official facts: contests in ballot order, candidates, measure digests | **Generated.** Don't hand-edit; run `py tools/build_ballot.py` |
| `endorsements.json` | Other organizations' published picks | Hand-edited, each guide cited |
| `picks.json` | **Our** picks (Golden Goose Egg / Certified HONK) | Hand-edited, opinion |

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

Absent = the guide didn't address the contest. Picks render as small chips
on the matching ballot row, while no-positions and notes render as a muted
footnote. The page logs a console warning for any name that isn't on the
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

## Reader state

District choices, marked ovals and toggles live in `localStorage`
(`sf-voter-guide.2026-11`). Nothing is sent anywhere. URL parameters
`?cd=11&ad=17&sup=8&bart=8&picks=1` preselect a ballot, which is handy
for sharing a district-specific link.
