# SF Voter Guide

Static voter guide for San Francisco's 2026-11-03 general election. It's a
sister repo of `../congress_trader` (goosebase), which bind-mounts `site/`
read-only into its nginx container at `/sf-2026/`. See README.md for the
layout and deploy path.

## Ground rules

- **`site/data/ballot.json` is generated**: edit `data-src/` and run
  `py tools/build_ballot.py`. Other groups' picks go in
  `site/data/endorsements.json` and ours in `site/data/picks.json`. `app.js`
  is a pure renderer. Schemas and pipeline: `docs/data-model.md`.
- **Ballot order is sacred.** Section/contest order comes from the official
  Ballot Worksheet; candidate order is computed from the SoS randomized
  alphabet. Never reorder by hand.
- **Never invent our picks.** `picks.json` holds the owner's opinions; only
  add a pick the user has stated.
- **Follow `docs/sourcing.md` without exception.** Never write a candidate
  name, ballot designation, measure title, dollar figure or date from
  memory. Each one comes from a cited source with an access date, and
  ballot facts come from Tier-1 official sources (SF Dept. of Elections,
  CA SoS, SF Ethics, Cal-Access). If a fact can't be confirmed, leave it
  out and say so.
- **Neutral content and picks stay separate.** Official text stays verbatim.
  Opinion goes only in `picks.json`, which the UI hides by default. Other
  groups' picks are visually quieter than ours.
- **Public page.** It's exempt from Cloudflare Access, so never put
  anything private in this repo.
- The site has no build step, framework or external JS (the data build in `tools/` runs offline). Styling uses goosebase
  tokens from `site/css/tokens.css`; don't hardcode colors.

## Timeline

Election Day is **2026-11-03**. Prioritize coverage over polish: an
accurate entry for every contest beats a beautiful page that covers half
the ballot.
