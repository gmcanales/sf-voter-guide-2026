# Next cycle — plan and 2026 post-mortem

Written 2026-11-04, the day after the November 3 general. Everything here is
derived from the goosebase nginx access log (Oct 25 03:12 UTC → Nov 4 08:25
UTC) and from this repo's own source. Traffic figures exclude link-preview
bots and `curl`.

## 1. How 2026 actually went

**89 human page loads, 45 unique visitors, over 11 days.** 66% mobile (59
iPhone/Android vs 30 desktop).

| day | loads | visitors | share-preview scrapes |
|---|---|---|---|
| Oct 25 | **40** | **14** | **30** |
| Oct 26 | 17 | 9 | 1 |
| Oct 27 | 5 | 4 | — |
| Oct 28 | 3 | 3 | 1 |
| Oct 29 | 3 | 3 | — |
| Oct 30 | 2 | 2 | — |
| Oct 31 | 2 | 2 | — |
| Nov 1 | 0 | 0 | — |
| Nov 2 | 4 | 2 | — |
| **Nov 3 (election)** | **11** | **8** | 1 |
| Nov 4 | 2 | 2 | — |

Election day showed 2,880 raw requests — the biggest day in the log — but
2,502 of those were 404s from vulnerability scanners, 1,000 from a single IP.
Real human requests that day: ~370.

Referrers: 89 of 110 loads were `-` (a link someone was handed). The rest were
self-referrals from the county switcher. **Zero search referrers, zero social
referrers.** Every visitor arrived through a shared link.

### The diagnosis: the guide shipped 20 days into a 29-day voting window

California mails a ballot to every registered voter beginning **no later than
29 days before election day** (Elections Code § 3000.5, from AB 49 in 2019;
universal mail made permanent by AB 37 in 2021). Counties have 5 days to
finish the mailing.

| date | event |
|---|---|
| **Oct 5, 2026** | counties begin mailing ballots |
| Oct 19, 2026 | registration deadline |
| Oct 24, 2026 | first commit in this repo |
| **Oct 25, 2026 03:12 UTC** | guide live |
| Nov 3, 2026 | election day |

So the guide appeared with **9 days left in a 29-day window** — most of the
audience already had a ballot on the kitchen table, and a large share had
already returned it. For context, roughly 26% of California's November 2024
ballots arrived on or after election day, so there is a real late cohort (that
is who the 8 election-day visitors were), but the bulk votes earlier, and
earlier was before this site existed.

The traffic shape follows from that: one share burst, a ~2-day half-life, a
nine-day decay to zero, and a small election-day bump of mostly new visitors.
Nothing about it suggests the content underperformed. It suggests the content
arrived after the decision moment for most people who would have used it.

## 2. The next target

**There is no statewide California election in 2027, and no regular San
Francisco municipal election either.** SF Proposition H (November 2022) moved
Mayor, Sheriff, District Attorney, City Attorney and Treasurer from odd years
to even years on the presidential cycle. November 2, 2027 is California's
odd-year established election date and some local districts will use it, but
there is no SF ballot to guide.

The two real targets, both derived from the Elections Code formula (first
Tuesday after the first Monday) — **confirm against the Secretary of State
calendar once it is published:**

- **Tuesday, March 7, 2028** — statewide direct primary. In presidential
  years California's primary sits in March.
- **Tuesday, November 7, 2028** — general election. This is the big SF
  ballot: mayor, sheriff, DA, city attorney and treasurer all land here
  alongside the presidential race.

A statewide special election (a recall, an urgent bond) can appear on roughly
90 days' notice. Possible, not plannable.

**Recommendation: treat March 7, 2028 as the real build, not a warm-up.**
Primary ballots are where a guide earns the most — many candidates per race,
no party label to fall back on downballot, and local measures. It is also
where the incumbent guides (GrowSF, the Chronicle's endorsements) are
thinnest. November 2028 then reuses the whole apparatus against a much larger
audience.

### The 2028 calendar, worked backward from the mail date

| date | what |
|---|---|
| Dec 2027 | candidate filing closes — the ballot becomes knowable |
| Jan 2028 | content build |
| **Thu Feb 4, 2028** | **guide live and shareable. Hard deadline.** |
| **Mon Feb 7, 2028** | counties begin mailing ballots (29 days out) |
| Feb 7–17 | ballots physically arrive — allow 7–10 days for delivery |
| Mon Feb 21, 2028 | registration deadline (15 days out) |
| Feb 29 – Mar 6 | final week; the late-returner cohort |
| **Tue Mar 7, 2028** | election day |

**Two share pushes, not one.** The 2026 log is unambiguous on this: all 30
share-preview scrapes landed on a single day, and traffic was back to
single digits within 72 hours. One burst cannot cover a month-long voting
window.

- **Push 1 — Feb 8–12.** Ballots are arriving. This is the moment that was
  missed in 2026, and it is the single highest-value change in this document.
- **Push 2 — Mar 1–4.** For the quarter or so who vote in the last few days.

Being live by Feb 4 also gives search engines about four weeks to index the
site before anyone votes, which in 2026 was never possible.

## 3. Fix the channel that actually worked

Sharing was the *only* channel that delivered anyone. It was also completely
unoptimized.

**`site/index.html` has no Open Graph or Twitter card tags at all** —
`grep -c 'og:\|twitter:'` returns 0. There is no share image anywhere in the
repo. So every link pasted into Messenger, WhatsApp, iMessage or Signal
rendered as a bare URL. Thirteen `facebookexternalhit` scrapes and one
`WhatsApp/2.23.20.0` fetch hit a page with nothing for them to show.

Roughly twenty lines of `<meta>` plus one 1200×630 card image would multiply
the exact mechanism that produced all 45 visitors. Nothing else on this list
has that ratio.

Also missing: **`robots.txt` 404s** at the goosebase root, and there is no
sitemap. Neither blocks indexation, but neither invites it, and eleven days
produced zero search referrers for a page titled "SF Voter Guide 2026".

## 4. Feature audit — and why nothing should be cut yet

**The access log cannot measure feature engagement.** All fifteen data files
load in a single eager `Promise.all` at `site/app.js:1597`, before first
paint. Every file is requested on every page load whether or not the visitor
ever scrolls to the section it feeds. Request counts measure page loads, not
use.

The spread in the log is deploy timing and feature flags, not popularity:

| file(s) | requests | why |
|---|---|---|
| picks, topics, funding, endorsements, money, state_money, external_money, analysis | 114–121 | eager, present all window |
| ballot, zip_districts | 93–95 | eager; some served 304 |
| stances, police_money | 57 | **added Oct 25**, mid-window — earlier loads predate them |
| county_measure_money | 17 | `PREVIEW`-gated |
| counties/*/candidate_money | 7, 1 | `PREVIEW`-gated |

So: do not cut a feature on this evidence. Add measurement first, cut on real
data next cycle.

### What is structurally bulk, regardless of engagement

1. **The two `PREVIEW`-gated datasets.** `county_measure_money.json` (39 KB,
   third-largest file in the repo) and `candidate_money.json` load only when
   `COUNTIES[county].preview` is true — alameda, sanmateo and contracosta
   only (`site/app.js:8–13`). SF is not flagged, so the large majority of
   visitors never loaded either. Built, sourced and maintained for ~13% of
   visits. Either promote them to every county or drop them.

2. **The multi-county build.** 20 of 130 loads used `?county=` (alameda 10,
   contracosta 8, sanmateo 2), all during launch week. **On election day no
   `data/counties/*` file was fetched at all** — every one of the 8 visitors
   was on the SF default. That is 1.3 MB of `data/counties/` and three county
   datasets serving about twenty visits. It was a reasonable reach play, but
   it was the largest build cost against the smallest audience. For 2028
   either commit to the East Bay *with distribution there*, or go SF-only and
   go deeper.

3. **`ballot.json` at 94 KB**, the largest single file, loaded on every visit.

### The payload problem, independent of features

30.2 MB served for 130 page loads — **about 238 KB per load**, to an audience
that was two-thirds mobile.

- **gzip is off entirely.** `congress_trader/frontend/nginx.conf` contains no
  `gzip` directive, and a live request with `Accept-Encoding: gzip` comes back
  with no `Content-Encoding`. Measured: `data/*.json` compresses **369 KB →
  78 KB, 79% off**; `ballot.json` alone 94 KB → 21 KB. A four-line nginx
  change, and it benefits the whole goosebase site.
- **Nothing caches.** `fetch(path, { cache: 'no-cache' })` at
  `site/app.js:1592` plus a `Cache-Control: no-cache` response means every
  revisit revalidates. **828 of 1,366 data requests were full 200
  re-downloads**; only 538 were 304s.
- Fifteen parallel fetches before first paint.

### Instrumentation to add, so 2028 can cut features honestly

No third-party analytics, nothing that tracks a person:

- **Lazy-load the optional datasets** (stances, police money, external money,
  analysis) on first section expand. This alone converts the existing access
  log into an engagement log — for free, with zero tracking code, and it cuts
  the initial payload at the same time. Do this one regardless.
- Optionally a tiny beacon on section expand and pick-reveal, recording only
  `{section, county}`. The `/public_api/` prefix and its rate limiting already
  exist in `frontend/nginx.conf`.

## 5. Sequenced

**Now → Dec 2026** (cheap, durable, do it while the context is fresh)

1. Open Graph + Twitter card tags and a 1200×630 share image.
2. Enable gzip in `congress_trader/frontend/nginx.conf`.
3. Persist nginx logs to a host volume — this analysis was capped at 11 days
   only because that is how long the frontend container had been up.
4. Lazy-load the optional datasets behind section expand.
5. Decide the fate of the two `PREVIEW` datasets.
6. Freeze the 2026 data as an archived snapshot.

**2027** — dormant. Watch for a Nov 2, 2027 local ballot or a statewide
special; either would be a low-stakes rehearsal of the February playbook.

**Dec 2027 → Mar 2028**

7. Dec: filing closes, lock scope (SF-only vs multi-county).
8. Jan: build content.
9. **Feb 4: live.**
10. Feb 8–12: push 1, as ballots arrive.
11. Mar 1–4: push 2, for late returners.

## Sources

- [California Elections Code § 3000.5 (29-day mailing)](https://ebench-dev.greeninfo.org/state/california/statute/3000.5)
- [AB 49 (2019), the 29-day mailing requirement](https://www.legiscan.com/CA/text/AB49/2019)
- [AB 37 (2021), universal vote-by-mail made permanent](https://www.democracydocket.com/news-alerts/california-governor-signs-universal-vote-by-mail-into-law)
- [PPIC — late vote-by-mail ballots in California](https://www.ppic.org/publication/understanding-increases-in-late-vote-by-mail-ballots-in-california/)
- [California's vote count, explained (Protect Democracy)](https://protectdemocracy.org/work/californias-vote-count-explained/)
- [SF Proposition H, November 2022 — municipal elections to even years](https://ballotpedia.org/San_Francisco,_California,_Proposition_H,_Move_Local_Elections_to_Even-Numbered_Years_and_Change_Initiative_Petition_Signature_Requirements_Amendment_(November_2022))
- [SF Department of Elections — Prop H voter information](https://sfelections.sfgov.org/sites/default/files/Prop%20H%20-%20City%20Elections%20in%20Even%20Numbered%20Years%20-%20VIP.pdf)
- [California election calendar (Ballotpedia)](https://ballotpedia.org/California_election_calendar)
