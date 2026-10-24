# sf_voter_guide

A sourced, plain-language guide to San Francisco's **November 3, 2026**
general election ballot, served at **https://goosebase.org/sf-2026/** via the
[congress_trader](https://github.com/gmcanales/congress_trader) app.

Neutral explainers by default. Our own picks are opt-in behind a
"Show our picks" toggle and always labeled as opinion.

## Layout

```
site/                     ← everything served at /sf-2026/ (bind-mounted read-only)
  index.html, app.js      ← page shell + renderer (no framework, no build)
  style.css               ← ballot-style layout on goosebase design tokens
  data/ballot.json        ← GENERATED official facts, in ballot order
  data/endorsements.json  ← other groups' picks (hand-edited, cited)
  data/picks.json         ← OUR picks: Golden Goose Egg / Certified HONK
  data/zip_districts.json ← GENERATED ZIP → district overlaps
  css/, js/               ← site-shell assets copied from congress_trader/frontend
data-src/                 ← build inputs (skeleton + extracted official text)
tools/                    ← extract_vip.py, extract_sos_props.py, build_ballot.py,
                            build_zip_districts.py (needs .venv with tools/requirements.txt)
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

## Deploying

Nothing to build. `congress_trader/docker-compose.yml` bind-mounts
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
