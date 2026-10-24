# Data model — `site/data/ballot.json`

The page is a pure renderer: every word a voter reads about a race or measure
comes from this one file. Edit the JSON, reload, done — no build step.

## Top level

| Field | Type | Notes |
|---|---|---|
| `election` | object | `name`, `jurisdiction`, `date` (ISO), `official_sources[]` (`{label, url}`) |
| `updated` | ISO date \| null | Last content review. Shown in the page header. |
| `contests` | array | One entry per race or measure, in ballot order. |

## Contest

```jsonc
{
  "id": "sf-prop-a",               // stable slug, used as the URL #anchor
  "kind": "measure",               // "office" | "measure"
  "level": "city",                 // "federal" | "state" | "county" | "city" | "district"
  "title": "Proposition A",
  "subtitle": "…",                 // official short title, verbatim
  "district": null,                // e.g. "Supervisor District 4" — null = citywide
  "summary": "…",                  // neutral, plain-language, sourced
  "yes_means": "…",                // measures only
  "no_means": "…",                 // measures only
  "threshold": "majority",         // measures only: "majority" | "55%" | "two-thirds"
  "candidates": [                  // offices only
    { "name": "…", "party": "…", "incumbent": false,
      "ballot_designation": "…",   // verbatim from the official ballot
      "links": [{ "label": "Campaign site", "url": "…" }] }
  ],
  "arguments": {                   // steelman each side, attributed
    "for":     [{ "text": "…", "source": "S1" }],
    "against": [{ "text": "…", "source": "S2" }]
  },
  "money": [                       // committee totals, always with an as-of date
    { "side": "for", "committee": "…", "amount": 0, "as_of": "2026-10-24", "source": "S3" }
  ],
  "pick": null,                    // or { "choice": "Yes", "reasoning": "…", "sources": ["S1"] }
  "sources": [
    { "id": "S1", "label": "…", "url": "…", "accessed": "2026-10-24" }
  ]
}
```

## Rules the renderer enforces

- `pick` is **hidden by default**. It shows only when the reader turns on
  "Show our picks", and it is always drawn in a visually distinct, labeled box.
  The neutral content must stand on its own with picks off.
- Every `source` reference in `arguments`, `money` and `pick` must resolve to
  an entry in that contest's `sources[]`; unresolved refs are flagged in the
  browser console so they're caught in preview.
