# sf_voter_guide

A sourced, plain-language guide to San Francisco's **November 3, 2026**
general election ballot, served at **https://goosebase.org/sf-2026/** via the
[congress_trader](https://github.com/gmcanales/congress_trader) app.

Neutral explainers by default. Our own picks are opt-in behind a
"Show our picks" toggle and always labeled as opinion.

## Layout

```
site/                 ← everything served at /sf-2026/ (bind-mounted read-only)
  index.html          ← Goosebase page shell
  app.js              ← renders data/ballot.json → DOM (no framework, no build)
  style.css           ← page styles (uses goosebase design tokens)
  data/ballot.json    ← ALL guide content — the only file most edits touch
  css/, js/           ← site-shell assets copied from congress_trader/frontend
docs/
  data-model.md       ← ballot.json schema
  sourcing.md         ← sourcing rules (read before adding content)
```

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
