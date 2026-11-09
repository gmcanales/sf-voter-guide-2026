# sf_voter_guide

A sourced, plain-language guide to the **November 3, 2026** general election
ballot for San Francisco and three neighbouring Bay Area counties. It was
served at `goosebase.org/sf-2026/` through the
[congress_trader](https://github.com/gmcanales/congress-trader) app.

Neutral explainers by default. The authors' own picks are opt-in behind a
"Show our picks" toggle and always labelled as opinion.

> ## ⚠ That election is over
>
> **This is an archive of a guide for an election held on 2026-11-03. It is
> not voting advice, and nothing in it should be relied on for any later
> ballot.** Candidates, measures, endorsements and money figures were accurate
> to late October 2026 and are now historical.

## Why this might be interesting to read

The hard part of a voter guide is not the page — it is that the inputs are
four counties' worth of PDFs, scanned measure digests, a JSONP election API,
a POST-form candidate search, and **four unrelated campaign-finance systems**
(SF Ethics via Socrata, Cal-Access as a 1.6 GB bulk export, the FEC API, and
NetFile's API plus manual portal exports). `tools/` is 28 scripts that turn
that into one ballot-ordered page, and `docs/STATUS.md §5` is the list of
things that went wrong on the way — including a double-counting bug that
showed one committee at $865K instead of $475K.

It also shipped to a deadline and then got measured:

- [`docs/next-cycle-plan.md`](docs/next-cycle-plan.md) — what the traffic
  actually showed (89 human page loads, 45 unique visitors, 66% mobile) and
  the finding that matters: the guide went live **20 days into a 29-day
  vote-by-mail window**, which explains the traffic shape better than
  anything about the content. Includes the distribution calendar for the next
  California election.
- [`docs/build-postmortem.md`](docs/build-postmortem.md) — where the ~14 hours
  went, from commit timestamps. Money data 29% and candidate descriptions 15%.
  Candidate-description coverage turned out to be a property of each county
  (Alameda 77%, Contra Costa 68%, San Mateo 0%) rather than a function of
  effort spent.

## Sourcing

Tier-1 sources only; nothing is fabricated. Unverifiable claims were cut.
Figures taken from ballot arguments are labelled as that side's claim. OCR was
used for reading scanned documents, never published raw — only hand-checked
digests. The full rules are in [`docs/sourcing.md`](docs/sourcing.md), and
`docs/STATUS.md §4` lists every source and how it was accessed.

Several official sites block automated access. Those were **not** routed
around — the pages were saved by hand instead, and `docs/STATUS.md` names
which sites and why.

Candidate contact emails have been removed from the otherwise-verbatim
candidate statements; see [`tools/redact.py`](tools/redact.py) for the
reasoning.

## Layout

```
site/                     ← everything served at /sf-2026/ (bind-mounted read-only)
  index.html, app.js      ← page shell + renderer (no framework, no build)
  style.css               ← ballot-style layout on goosebase design tokens
  data/ballot.json        ← GENERATED official facts, in ballot order
  data/endorsements.json  ← other groups' picks (hand-edited, cited)
  data/picks.json         ← OUR picks: GOOSEBASED / Certified HONK
  data/zip_districts.json ← GENERATED ZIP → district overlaps
  css/, js/               ← site-shell assets copied from congress_trader/frontend
data-src/                 ← build inputs (skeleton + extracted official text)
  sample_ballots/         ← transcribed sample ballots (CSV) used to verify lists/order
tools/                    ← extract_vip.py, extract_sos_props.py, build_ballot.py,
                            build_zip_districts.py (needs .venv with tools/requirements.txt),
                            sample_ballot.py (verify against a transcribed sample ballot)
docs/
  data-model.md           ← schemas + pipeline
  sourcing.md             ← sourcing rules (read before adding content)
```

Rebuild official data: `py tools/build_ballot.py` (extractors only when a
source changes; see docs/data-model.md).

## Local preview

```
python -m http.server 8080 -d site
# → http://localhost:8080/
```

## How it was deployed

Kept for reference — these are the specifics of the original deployment, not
steps you need. Nothing to build. `congress_trader/docker-compose.yml` bind-mounts
`../sf_voter_guide/site` into nginx at `/sf-2026/`, so a `git pull` on the
NUC is live immediately (nginx serves `*.js`/`*.css`/`*.json` with
`no-cache`). Purge the Cloudflare cache after content updates.

**Public access** requires a Cloudflare Access **Bypass** policy:
Zero Trust → Access → Applications → goosebase → Policies → add Bypass →
Include → Path → `/sf-2026/*`.

## Shell assets

`site/css/{tokens,landing,subpage}.css` and `site/js/palette.js` are copies
from `congress_trader/frontend/` (same convention as goose_snake and
oiligarchy). Re-copy them if the goosebase design system changes.
