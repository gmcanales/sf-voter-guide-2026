# SF Voter Guide

Static voter guide for San Francisco's 2026-11-03 general election. It's a
sister repo of `../congress_trader` (goosebase), which bind-mounts `site/`
read-only into its nginx container at `/sf-2026/`. See README.md for the
layout and deploy path.

## Ground rules

- **Content lives only in `site/data/ballot.json`.** `app.js` is a pure
  renderer. Schema: `docs/data-model.md`.
- **Follow `docs/sourcing.md` without exception.** Never write a candidate
  name, ballot designation, measure title, dollar figure or date from
  memory. Each one comes from a cited source with an access date, and
  ballot facts come from Tier-1 official sources (SF Dept. of Elections,
  CA SoS, SF Ethics, Cal-Access). If a fact can't be confirmed, leave it
  out and say so.
- **Neutral content and picks stay separate.** `summary`, `yes_means`,
  `no_means` and `arguments` are neutral and steelman both sides. Opinion
  goes only in `pick`, which the UI hides by default.
- **Public page.** It's exempt from Cloudflare Access, so never put
  anything private in this repo.
- No build step, no framework, no external JS. Styling uses goosebase
  tokens from `site/css/tokens.css`; don't hardcode colors.

## Timeline

Election Day is **2026-11-03**. Prioritize coverage over polish: an
accurate entry for every contest beats a beautiful page that covers half
the ballot.
