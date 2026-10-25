# Status: 2026 Bay Area voter guide

_Last updated 2026-10-25 (election: Tuesday, Nov 3, 2026). Live at https://goosebase.org/sf-2026/._

Read this first when picking the project up. Schemas live in `docs/data-model.md`; sourcing
rules in `docs/sourcing.md`.

---

## 1. Where things stand

| | SF | Alameda | San Mateo | Contra Costa |
|---|---|---|---|---|
| Depth | **Full guide** | Preview + focus cities | Preview + focus cities | Preview + focus city |
| Focus cities | — | Oakland, Fremont | South SF, San Mateo, Redwood City | Richmond (incl. Richmond Annex) |
| Contests | 62 | 158 | 132 | 114 |
| Candidates with money data | 100% | 50% | 60% | 43% |
| Candidates with a profile or statement | 47% (KQED + pamphlet) | 77% (official statements) | 0% | 68% (official statements) |
| Local measures with official text | all | 2 of 27 | 4 of 28 | 12 of 12 |
| Local measures with any money / full local totals | all / all | 21 / 14 of 27 | 14 / 8 of 28 | 7 / 4 of 12 |
| Contests with 3rd-party positions | 62 | 103 | 46 | 53 |
| Contests with Goosebase picks | 56 | 52 | 37 | 37 |

**Shared everywhere:** statewide offices, 13 justices, 14 state props (with SoS money), RTM. These
are copied from the SF build, so their research and picks apply to every county.

**Features done:** official ballot order (SF), ZIP lookup in all four counties (districts, city,
K-12 school districts), focus-city buttons that narrow districts and trim local races, collapsible
sections, topic filter, tax-effect chips, funding tags, tabbed panels (What it does / Money /
Average goose / Seriously TL;DR), header toggles "Show Goosebase bias" / "Show 3rd party positions",
recommendation highlight boxes (gold = rated pick, gray = unrated lean), group panel with
county/statewide dividers.

**Picks:** 81 total (10 GOOSEBASED, 20 Certified HONKs, 51 Goosebase takes), all proofread
and fact-checked. SF sheet `data-src/picks_sf.csv`, Alameda sheet `data-src/picks_alameda.csv`.

**Groups (17):** SF Dems, GrowSF, DSA SF, SF Labor Council, SF Chamber, SPUR, UESF, LWV SF, Pissed
Off Voters, Sierra Club SF Bay, CA Nurses, CalChamber, YIMBY Action (statewide + county locals),
East Bay DSA, East Bay Young Dems, Richmond Progressive Alliance, LWV Oakland.

---

## 2. Next steps (priority order)

1. **Local candidate money gaps.** Done 2026-10-25 for what NetFile holds: state legislators
   (Cal-Access; `tools/find_state_committees.py` proposes ids, checked against the cover-page
   district), Congress (FEC ids in `tools/candidate_money_external.py`), and local races
   (`tools/local_candidate_money.py`: 222 committees across ~30 city and county NetFile agencies,
   itemized gifts since 2025, written to `site/data/counties/<county>/candidate_money.json`).
   Remaining: candidates whose committee name lacks their surname (e.g. "vipin4fremont"), cities
   not on NetFile (South San Francisco), special
   districts filing with another county, and outside (IE) money for local races.
2. **RTM money:** its committees likely register with the state. Add them to `state_money.py` or
   `local_measure_money.py`; the Money tab still says "not covered" in every county.
3. **More NetFile exports** (user downloads from the portal; complete Form 460 totals): Redwood City
   (RWC), City of San Mateo (MTO), San Mateo County (MAT), Richmond (RICH), Berkeley (BRK), Fremont
   (FRE). Rerun `local_measure_money.py` with all export paths.
4. **San Mateo candidate statements.** The county doesn't post city-race statements (the page
   says so). Contra Costa (`tools/county_statements_contracosta.py`, 139) and Alameda
   (`tools/county_statements_alameda.py`, 206 from the VIG PDF's pages 632-757) are done. Alameda's
   pages set candidates in two justified columns; text is rebuilt from poppler word boxes (the
   local xpdf `pdftotext` can't separate them), and same-surname candidates in other races are
   kept apart by requiring a first-name match outside the page's own contest.
5. **Measure digests** for larger non-focus cities (Berkeley's 7, Albany's 6, Hayward, San Bruno,
   Menlo Park P, Half Moon Bay I/Q).
6. **Local groups for San Mateo:** SM County Democrats (Cloudflare challenge) and Sierra Club Loma
   Prieta (bot-walled). Ask the user to save the pages; transcribe with `tools/import_guides.py`.
7. **Ward maps** for AC Transit, EBMUD, EBRPD, water/sanitary districts, and the 2021 San Mateo
   supervisor map (the county's layer is token-only), to narrow ward races from a ZIP.
8. Optional: Alameda County Dems / labor councils (sites unreachable; need correct URLs or saved
   pages).

---

## 3. Tools (all re-runnable; run from the repo root)

| Tool | What it does |
|---|---|
| `tools/build_ballot.py` | SF ballot from skeleton + pamphlet + SoS props; randomized-alphabet order |
| `tools/extract_vip.py`, `extract_sos_props.py` | SF pamphlet / state prop digests |
| `tools/sample_ballot.py` | Check/apply a transcribed sample ballot (verified order) |
| `tools/build_zip_districts.py` | SF ZIP → districts (shapely; `.venv`) |
| `tools/funding_tags.py`, `money_flows.py` | SF Ethics money: candidate tags, measure committees |
| `tools/state_money.py` | State prop committee totals (SoS) |
| `tools/candidate_money_external.py <dbwebexport.zip>` | State candidates (Cal-Access) + federal (FEC) + judicial committees |
| `tools/county_alameda.py` | Alameda contests (Registrar search) + measures |
| `tools/county_sanmateo.py <roster.pdf>` | San Mateo roster PDF + measure list |
| `tools/county_contracosta.py` | Contra Costa election API: contests, measures with official text |
| `tools/build_county_ballot.py <county>` | County preview ballot; merges digests, profiles, focus districts |
| `tools/build_focus_districts.py` | Focus city × district maps + K-12 school districts |
| `tools/build_county_zips.py` | County ZIP data + `zip_counties.json` |
| `tools/local_measure_money.py <zip> [netfile .xlsx…]` | County measure money: Cal-Access floor + NetFile exports + NetFile API |
| `tools/group_money.py <zip>` | Group PAC receipts from Cal-Access |
| `tools/guide_eastbaydsa.py` | Imports East Bay DSA's guide data (Node loads their JS module) |
| `tools/import_guides.py` | Merges hand-transcribed guides (`data-src/guides/*.json`), validates names |
| `tools/import_picks.py` | Builds `picks.json` from `data-src/picks_*.csv`; rejects names not on a ballot |
| `tools/ocr_pdf.py` | Text from PDFs; Tesseract OCR via the congress_trader backend image if needed |

Hand-checked inputs: `data-src/counties/<county>/measure_digests.json`, `candidate_profiles.json`,
`data-src/local_measure_committees.json` (pins with reasons), `data-src/filing_notes.json`.

**Rebuild after data changes:** `build_county_ballot.py` for each county, then
`import_guides.py`, `guide_eastbaydsa.py`, `import_picks.py` (the ballot rebuild doesn't touch
endorsements or picks, but guide imports validate against the rebuilt ballots).

**Deploy:** push to GitHub, then on the NUC `git -C /root/sf_voter_guide pull`. The site folder is
bind-mounted read-only into goosebase nginx at `/sf-2026/`, so there's no rebuild for content. nginx
or compose changes need `./scripts/deploy.sh frontend` in congress_trader. Purge the Cloudflare cache
if a browser shows stale files. (The user normally deploys; SSH only when asked.)

---

## 4. Data sources and APIs

| Source | Access | Notes |
|---|---|---|
| SF Ethics (DataSF `pitq-e56w`, public funds `5sxz-kk66`) | Socrata API | Use latest filing versions only |
| Cal-Access bulk export `campaignfinance.cdn.sos.ca.gov/dbwebexport.zip` | Download (1.6 GB) | The website is bot-walled; the export isn't |
| FEC API | `FEC_API_KEY` env var (api.data.gov key, kept outside the repo) | DEMO_KEY rate-limits fast |
| CA SoS voter guide / candidate list | Direct | Official text for props |
| Alameda Registrar candidate search `alamedacountyca.gov/rov_app/candidatelist/` | POST form (session cookie) | Page renders every contest twice (desktop + mobile); parse "FIRST LOOP" only |
| Alameda VIG PDF | Download | **Text layer garbled** (shifted glyphs, no spaces): OCR pages with `ocr_pdf.py --ocr --pages` |
| San Mateo `smcacre.gov` | Direct | Roster PDF `/media/8827`; measure docs are mostly scans (OCR); statements only in personal pamphlets |
| Contra Costa `contracostavote.gov/ce/mobile/seam/resource/rest/election/getElection?eid=66` | JSONP API | Offices, candidates, measure pages with full official text |
| NetFile public portal `public.netfile.com/pub2/?AID=…` | **Cloudflare Turnstile, don't automate** | User can export "All Transactions" .xlsx |
| NetFile public API `netfile.com/Connect2/api` (Swagger at `/swagger-ui/`, spec `/openapi`) | Open JSON (send `Accept: application/json`) | Works: `public/campaign/agencies`, `public/campaign/list/filer?AID=`, `public/campaign/search/transaction/query?Agency=<id>&QueryString=<exact filer name>&ShowSuperceded=false`, `public/filing/info/{id}`. Retired: yearly export, `list/filing`, efile download. Avoid `search/transaction/recent` (shows other people's searches) |
| Oakland open data (Socrata `rsxe-vvuw`, `3xq4-ermg`, 497/496 sets) | Socrata API | Lags (460s to June 30 only) |
| Census TIGERweb (ZCTAs, counties, places, school districts) | ArcGIS REST | Places use `BASENAME`; school layers 0/1/2 = unified/secondary/elementary |
| State district maps (data.ca.gov ArcGIS org `uknczv4rpevve42E`) | ArcGIS REST | CD = Prop 50 map; AD/SD = 2021 CRC |
| BART districts | ArcGIS REST | |
| East Bay DSA `vote.eastbaydsa.org` | Their JS data module | Loaded with Node; statewide items are California DSA's positions |
| YIMBY Action endorsements page | Embedded JSON | Covers local races in all our counties |

**Bot-walled, don't route around (user saves pages instead):** sfelections.gov / sf.gov, Sierra
Club, theleaguesf, Cal-Access website, SM County Dems, NetFile portal, ProPublica PDFs.

---

## 5. Learnings and gotchas

**Data correctness**
- **Cal-Access double counting:** one gift appears on the giver's Form 497 *and* its next 460 as
  Schedule D *and* E. Count Schedule D + 497 part 2 only, deduped by (giver, recipient, date,
  amount). Caught after Yes on EE showed $865K instead of $475K.
- Amendments: keep the latest filing per period (and latest `AMEND_ID` / `Report_Num`).
- Committees get reused across campaigns; Cal-Access may keep an old name ("Yes on T" for a 2026 W
  committee). Pin names in `local_measure_committees.json`.
- Local measure committees register with the SoS but file money locally. Cal-Access gives who's
  behind each side plus a floor from state-filer gifts; full totals need NetFile.
- Hand-written district lists miss real overlaps. Use maps: part of South SF is in Jefferson Union
  HSD (Measure M was wrongly hidden).
- County lists are in list order, not printed-ballot order; say so.
- Title-casing loses internal capitals (LeAna, DeSaulnier, "Jr."). Keep `NAME_FIXES`.
- Every pick, guide transcription and profile is validated against ballot names; keep it that way.

**Sourcing and voice**
- Tier-1 sources only; never fabricate. Unverifiable claims are cut, or the user supplies a
  source. Figures from ballot arguments are labeled as that side's claim.
- OCR is for reading. Publish hand-checked digests, never raw OCR text.
- No pronouns unless stated (use names or they/them).
- Misconduct: report formal findings / credible on-record allegations neutrally with the denial
  (Yekutiel, Joel Young). The user declined a jokey tag; opinion lives in the picks.
- Opinions only in picks (opt-in); tags and explainers stay neutral and data-backed.

**Code**
- Native `replaceChildren()` doesn't flatten arrays or skip `null`; use `setKids()` (it printed
  "[object HTMLHeadingElement]" twice).
- Bash heredocs mangle `\n`, `\b`, `\s` in Python patch strings (backspace characters ended up in
  files). Write patch scripts to the scratchpad with the Write tool, or use Edit.
- ArcGIS/urllib responses can be wrapped (`{"agencies": [...]}`) where curl showed a list.
- Alameda candidate cells: split on `<br\s*/?>`, not `"<br"` (left "/> Democratic Party").
- Read untrusted downloads with `python -I` from their own folder.

---

## 6. Open questions for the user

- More local groups for San Mateo / Oakland / Richmond (party, labor, chamber): which ones, and
  saved pages for the bot-walled sites.
- Whether to extend Goosebase picks to Oakland, South SF, San Mateo, Redwood City and Richmond races
  (Fremont is done).
- Funding network map (`sf_2026_funding_network_map.png`): still on hold for the groups panel.
