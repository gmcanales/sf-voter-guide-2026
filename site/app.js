// SF Voter Guide renderer. Content lives in data/*.json (schema:
// docs/data-model.md); this file only turns it into DOM and keeps the reader's
// district choices + marked ovals in localStorage. Text is always set via
// textContent, never innerHTML.

// ?county= picks the ballot. SF is the full guide; the others are shallow
// previews built by tools/build_county_ballot.py into data/counties/<id>/.
const COUNTIES = {
  sf: { name: 'San Francisco', title: 'SF Voter Guide 2026' },
  alameda: { name: 'Alameda County', title: 'Alameda County Ballot 2026', preview: true },
  sanmateo: { name: 'San Mateo County', title: 'San Mateo County Ballot 2026', preview: true },
  contracosta: { name: 'Contra Costa County', title: 'Contra Costa County Ballot 2026', preview: true },
};
const COUNTY = (() => {
  const c = new URLSearchParams(location.search).get('county');
  return c && COUNTIES[c] ? c : 'sf';
})();
const PREVIEW = !!COUNTIES[COUNTY].preview;
const DATA_BASE = COUNTY === 'sf' ? './data/' : `./data/counties/${COUNTY}/`;
const STORE_KEY = 'sf-voter-guide.2026-11' + (COUNTY === 'sf' ? '' : `.${COUNTY}`);
const RCV_MAX_RANKS = 10;            // SF ballots allow up to 10 rankings
const RANK_LABEL = ['1st', '2nd', '3rd', '4th', '5th', '6th', '7th', '8th', '9th', '10th'];

const SOLE_SHARE = 0.995;            // a ZIP this much inside one district counts as "only that one"
const DIMS = ['cd', 'ad', 'sd', 'sup', 'bart', 'city'];
const DIM_NAMES = { cd: 'Congressional District', ad: 'Assembly District', sd: 'State Senate District',
  sup: 'Supervisor District', bart: 'BART District' };
const DIM_SHORT = { cd: 'CD', ad: 'AD', sd: 'SD', sup: 'Sup.', bart: 'BART' };

// Picker label for one option: a number, or a name from the ballot's labels map (cities, "Another district").
function optionLabel(dim, n) {
  return BALLOT.districts[dim]?.labels?.[n] ?? String(n);
}

const state = loadState();
let BALLOT, GUIDES, PICKS, ZIPS, TOPICS, FUNDING, MONEY, STATE_MONEY, ANALYSIS, EXTERNAL;

// ── persistence ────────────────────────────────────────────────────────────
function loadState() {
  const blank = { zip: null, districts: {}, marks: {}, collapsed: {}, topics: [], showGuides: true, showPicks: false };
  let s;
  try { s = { ...blank, ...JSON.parse(localStorage.getItem(STORE_KEY) || '{}') }; }
  catch { s = blank; }
  // Shareable links: ?zip=94110 or ?sup=8&ad=17 preselect a ballot; ?picks=1 turns picks on;
  // ?topic=housing,transit filters measures by topic.
  const q = new URLSearchParams(location.search);
  if (/^\d{5}$/.test(q.get('zip') || '')) s.zip = q.get('zip');
  for (const dim of DIMS) {
    if (q.has(dim) && /^\d+$/.test(q.get(dim))) s.districts = { ...s.districts, [dim]: Number(q.get(dim)) };
  }
  if (q.has('picks')) s.showPicks = q.get('picks') === '1';
  if (q.has('topic')) s.topics = q.get('topic').split(',').filter(Boolean);
  return s;
}
function saveState() {
  try { localStorage.setItem(STORE_KEY, JSON.stringify(state)); } catch { /* storage blocked */ }
}

// ── tiny DOM helper ────────────────────────────────────────────────────────
function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === 'class') node.className = v;
    else if (k.startsWith('on')) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v === true ? '' : v);
  }
  for (const c of children.flat(Infinity)) {
    if (c == null || c === false) continue;
    node.append(typeof c === 'string' ? document.createTextNode(c) : c);
  }
  return node;
}

function formatDate(iso) {
  // Local calendar date; `new Date('2026-11-03')` is UTC midnight → Nov 2 in PT.
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, m - 1, d).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });
}

// ── data helpers ───────────────────────────────────────────────────────────
function appliesToReader(contest) {
  const zopts = zipOptions();
  for (const [dim, want] of Object.entries(contest.applies || {})) {
    const have = state.districts[dim];
    if (have != null && have !== want) return false;
    // District not chosen yet, but the ZIP rules some out: hide the impossible ones.
    if (have == null && zopts && !zopts[dim].some(([n]) => n === want)) return false;
  }
  return true;
}

function districtTag(contest) {
  const a = contest.applies;
  if (!a) return null;
  const [dim, n] = Object.entries(a)[0];
  if (dim === 'city') return `${optionLabel(dim, n)} only`;
  return `${DIM_NAMES[dim]} ${n} only`;
}

function candidateOrder(contest) {
  const ad = state.districts.ad;
  if (contest.order_by_ad && ad != null && contest.order_by_ad[ad]) {
    const byName = Object.fromEntries(contest.candidates.map(c => [c.name, c]));
    return contest.order_by_ad[ad].map(n => byName[n]);
  }
  return contest.candidates;
}

function voteFor(contest) {
  if (contest.kind !== 'office') return 1;
  return contest.vote_for || 1;
}

function rcvRanks(contest) {
  return Math.min(contest.candidates.length, RCV_MAX_RANKS);
}

function picksFor(contestId) {
  return (PICKS.picks && PICKS.picks[contestId]) || [];
}

// Normalise a guide position into { kind: 'vote'|'picks'|'none', value, note }.
function normPosition(p) {
  if (typeof p === 'string') return { kind: 'vote', value: p };
  if (Array.isArray(p)) return { kind: 'picks', value: p };
  if (p.none) return { kind: 'none', value: p.none };
  if (p.picks) return { kind: 'picks', value: p.picks, note: p.note };
  return { kind: 'vote', value: p.vote, note: p.note };
}

// ── marks (the reader's own choices) ───────────────────────────────────────
function getMark(id) { return state.marks[id]; }

function toggleChoice(contest, name) {
  const cur = new Set(getMark(contest.id) || []);
  if (cur.has(name)) cur.delete(name);
  else {
    const n = voteFor(contest);
    if (n === 1) cur.clear();
    else if (cur.size >= n) { flash(contest.id, `You can vote for no more than ${n}. Clear one first.`); return; }
    cur.add(name);
  }
  setMark(contest.id, cur.size ? [...cur] : null);
}

function toggleRank(contest, name, rank) {
  // marks[id] = array indexed by rank (0-based) → candidate name or null.
  const ranks = [...(getMark(contest.id) || [])];
  if (ranks[rank] === name) ranks[rank] = null;
  else {
    const prev = ranks.indexOf(name);
    if (prev >= 0) ranks[prev] = null;             // one rank per candidate
    ranks[rank] = name;                            // one candidate per rank
  }
  while (ranks.length && ranks[ranks.length - 1] == null) ranks.pop();
  setMark(contest.id, ranks.length ? ranks : null);
}

function toggleYesNo(contest, value) {
  setMark(contest.id, getMark(contest.id) === value ? null : value);
}

function setMark(id, value) {
  if (value == null) delete state.marks[id];
  else state.marks[id] = value;
  saveState();
  rerenderContest(id);
  refreshSectionStatus(CONTEST_INDEX[id]?.section.id);
  renderProgress();
}

function flash(id, msg) {
  const box = document.querySelector(`[data-contest="${id}"] .vg-flash`);
  if (!box) return;
  box.textContent = msg;
  box.hidden = false;
  clearTimeout(box._t);
  box._t = setTimeout(() => { box.hidden = true; }, 3500);
}

// ── badges ────────────────────────────────────────────────────────────────
function badge(verdict) {
  if (verdict === 'egg') {
    return el('span', { class: 'vg-badge vg-badge-egg', title: 'Golden Goose Egg: our pick' },
      eggIcon(), 'Golden Goose Egg');
  }
  return el('span', { class: 'vg-badge vg-badge-honk', title: 'Certified HONK: we’d steer clear' }, 'Certified HONK');
}
function eggIcon() {
  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('viewBox', '0 0 20 26');
  svg.setAttribute('aria-hidden', 'true');
  const path = document.createElementNS(ns, 'path');
  path.setAttribute('d', 'M10 1C5 1 1 9 1 15.5 1 21 5 25 10 25s9-4 9-9.5C19 9 15 1 10 1Z');
  svg.append(path);
  return svg;
}

// Verdict for a ballot row: for measures/retention the row is "yes"/"no";
// for offices the row is a candidate name.
function rowVerdicts(contest, row) {
  return picksFor(contest.id).filter(p => {
    if (contest.kind === 'office') return p.target === row;
    return (p.verdict === 'egg' && row === 'yes') || (p.verdict === 'honk' && row === 'no');
  });
}

// ── ballot rows ────────────────────────────────────────────────────────────
function oval(pressed, label, onclick) {
  return el('button', {
    type: 'button', class: 'vg-oval' + (pressed ? ' is-marked' : ''),
    'aria-pressed': pressed ? 'true' : 'false', 'aria-label': label, onclick,
  });
}

function guideChipsForRow(contest, row) {
  if (!state.showGuides) return null;
  const pos = BALLOT_POSITIONS[contest.id] || {};
  const who = [];
  for (const g of GUIDES.guides) {
    if (!pos[g.id]) continue;
    const p = normPosition(pos[g.id]);
    const hit = p.kind === 'picks' ? p.value.includes(row) : (p.kind === 'vote' && p.value === row);
    if (hit) who.push(g);
  }
  if (!who.length) return null;
  return el('span', { class: 'vg-row-guides' },
    who.map(g => el('span', { class: `vg-chip vg-cat-${primaryCat(g)}`, title: g.name }, g.short)));
}

function renderOfficeRows(contest) {
  const marked = new Set(getMark(contest.id) || []);
  const rows = candidateOrder(contest).map(c => {
    const pressed = marked.has(c.name);
    return el('div', { class: 'vg-row' + (pressed ? ' is-marked' : '') },
      oval(pressed, `Vote for ${c.name}`, () => toggleChoice(contest, c.name)),
      el('div', { class: 'vg-row-main' },
        el('div', { class: 'vg-cand' },
          el('span', { class: 'vg-cand-name' }, c.name),
          c.party ? el('span', { class: 'vg-party' }, `Party Preference: ${c.party}`) : null,
          state.showPicks ? rowVerdicts(contest, c.name).map(p => badge(p.verdict)) : null),
        renderCandidateTags(contest, c.name),
        c.designation ? el('div', { class: 'vg-desig' }, c.designation) : null,
        c.note ? el('div', { class: 'vg-cand-note' }, c.note,
          c.note_source ? [' (', el('a', { href: c.note_source.url, target: '_blank', rel: 'noopener' }, 'source'), ')'] : null) : null,
        guideChipsForRow(contest, c.name),
        renderCandidateMore(contest, c)));
  });
  rows.push(el('div', { class: 'vg-row vg-writein' }, el('span', { class: 'vg-oval is-static', 'aria-hidden': 'true' }),
    el('div', { class: 'vg-row-main vg-desig' }, 'Write-in (qualified write-in candidates only)')));
  return el('div', { class: 'vg-rows' }, rows);
}

function renderRcvGrid(contest) {
  const ranks = getMark(contest.id) || [];
  const nRanks = rcvRanks(contest);
  const head = el('div', { class: 'vg-rcv-head', 'aria-hidden': 'true' },
    el('span', {}), ...Array.from({ length: nRanks }, (_, i) => el('span', {}, RANK_LABEL[i])));
  const rows = candidateOrder(contest).map(c => {
    const myRank = ranks.indexOf(c.name);
    return el('div', { class: 'vg-rcv-row' + (myRank >= 0 ? ' is-marked' : '') },
      el('div', { class: 'vg-row-main' },
        el('div', { class: 'vg-cand' },
          el('span', { class: 'vg-cand-name' }, c.name),
          state.showPicks ? rowVerdicts(contest, c.name).map(p => badge(p.verdict)) : null),
        renderCandidateTags(contest, c.name),
        c.designation ? el('div', { class: 'vg-desig' }, c.designation) : null,
        c.note ? el('div', { class: 'vg-cand-note' }, c.note) : null,
        guideChipsForRow(contest, c.name)),
      el('div', { class: 'vg-rcv-ovals' }, Array.from({ length: nRanks }, (_, r) =>
        oval(ranks[r] === c.name, `${RANK_LABEL[r]} choice: ${c.name}`, () => toggleRank(contest, c.name, r)))),
      // Full-width row under the ovals so the tabs aren't squeezed into the name column.
      renderCandidateMore(contest, c));
  });
  return el('div', { class: 'vg-rcv', style: `--ranks:${nRanks}` }, head, rows);
}

function renderYesNo(contest, yesLabel = 'YES', noLabel = 'NO') {
  const mark = getMark(contest.id);
  return el('div', { class: 'vg-rows vg-yesno' }, ['yes', 'no'].map(v => {
    const pressed = mark === v;
    return el('div', { class: 'vg-row' + (pressed ? ' is-marked' : '') },
      oval(pressed, `${v.toUpperCase()} on ${contest.title}`, () => toggleYesNo(contest, v)),
      el('div', { class: 'vg-row-main' },
        el('div', { class: 'vg-cand' },
          el('span', { class: 'vg-cand-name' }, v === 'yes' ? yesLabel : noLabel),
          renderTopicTags(contest, v),
          state.showPicks ? rowVerdicts(contest, v).map(p => badge(p.verdict)) : null),
        renderTopicImpact(contest, v),
        guideChipsForRow(contest, v)));
  }));
}

// ── guide footnote under each contest (muted) ─────────────────────────────
// The picks themselves show as chips on the ballot rows; this line only adds
// what a chip can't carry: qualifying notes on a pick. Explicit no-positions
// stay in the data but aren't shown.
function renderGuideLine(contest) {
  if (!state.showGuides) return null;
  const pos = BALLOT_POSITIONS[contest.id];
  if (!pos) return null;
  const parts = [];
  for (const g of GUIDES.guides) {
    if (!pos[g.id]) continue;
    const p = normPosition(pos[g.id]);
    if (p.kind === 'none' || !p.note) continue;
    parts.push(el('li', {},
      el('a', { href: g.url, target: '_blank', rel: 'noopener' }, g.short), ': ', p.note));
  }
  if (!parts.length) return null;
  return el('ul', { class: 'vg-guides' }, parts);
}

// ── our pick box (opinion) ────────────────────────────────────────────────
function renderPickBox(contest) {
  if (!state.showPicks) return null;
  const picks = picksFor(contest.id);
  if (!picks.length) return null;
  return el('div', { class: 'vg-pick' }, picks.map(p =>
    el('div', { class: 'vg-pick-item' }, badge(p.verdict),
      p.target ? el('strong', {}, ` ${p.target}`) : null,
      el('p', {}, p.reasoning))));
}

// ── details (neutral, official) ───────────────────────────────────────────
function para(label, text) {
  if (!text) return null;
  const lines = text.split('\n');
  return el('div', { class: 'vg-detail' }, el('h4', {}, label),
    lines.length > 1 && lines.slice(1).every(l => l.startsWith('• '))
      ? [el('p', {}, lines[0]), el('ul', {}, lines.slice(1).map(l => el('li', {}, l.slice(2))))]
      : lines.map(l => el('p', {}, l.replace(/^• /, '• '))));
}

function renderDetails(contest, asBlocks = false) {
  const blocks = [];
  if (contest.kind === 'measure') {
    blocks.push(
      para('On the ballot', contest.question),
      para(contest.summary_label || 'Summary', contest.summary),
      para('The way it is now', contest.way_it_is_now),
      para('The proposal', contest.proposal),
      contest.yes_means || contest.no_means ? el('div', { class: 'vg-meaning' },
        el('div', {}, el('strong', {}, 'A YES vote means: '), contest.yes_means || '—'),
        el('div', {}, el('strong', {}, 'A NO vote means: '), contest.no_means || '—')) : null,
      para('Fiscal impact', contest.fiscal),
      contest.official_args ? el('div', { class: 'vg-args' },
        el('div', {}, el('h4', {}, contest.official_args_label === 'digest' ? 'Argument for (our digest)' : 'Official argument for'), el('p', {}, contest.official_args.for || 'None filed.')),
        el('div', {}, el('h4', {}, contest.official_args_label === 'digest' ? 'Argument against (our digest)' : 'Official argument against'), el('p', {}, contest.official_args.against || 'None filed.'))) : null,
      para('Listed supporters', contest.listed_supporters),
      para('Listed opponents', contest.listed_opponents),
      para('How it got on the ballot', contest.how_placed || contest.placed_by),
      contest.note ? el('p', { class: 'vg-fineprint' }, contest.note) : null,
      contest.source ? el('p', { class: 'vg-fineprint' }, 'Source: ',
        el('a', { href: contest.source.url, target: '_blank', rel: 'noopener' }, contest.source.label)) : null,
      contest.sources?.length ? el('p', { class: 'vg-fineprint' }, 'Official documents: ',
        contest.sources.map((x, i) => [i ? ' · ' : '', el('a', { href: x.url, target: '_blank', rel: 'noopener' }, x.label)])) : null,
      topicTags(contest).length ? el('div', { class: 'vg-detail' }, el('h4', {}, 'Why these topic tags (our labels)'),
        el('ul', {}, topicTags(contest).map(t => el('li', {},
          el('strong', {}, `${t.on === 'no' ? 'If NO: ' : ''}${topicLabel(t.topic)}${t.effect ? ` ${ARROW[t.effect]}` : ''}: `), t.why)))) : null,
      contest.threshold ? el('p', { class: 'vg-fineprint' }, `Passes with: ${contest.threshold}`) : null);
  }
  if (contest.list_note) blocks.push(el('p', { class: 'vg-fineprint' }, contest.list_note));
  if (contest.order_note) blocks.push(el('p', { class: 'vg-fineprint' }, contest.order_note));
  if (contest.sources?.length) {
    blocks.push(el('div', { class: 'vg-detail' }, el('h4', {}, 'Sources'),
      el('ul', { class: 'vg-sources' }, contest.sources.map(s =>
        el('li', {}, el('a', { href: s.url, target: '_blank', rel: 'noopener' }, s.label),
          s.accessed ? ` (accessed ${formatDate(s.accessed)})` : '')))));
  }
  const body = blocks.filter(Boolean);
  if (!body.length) return null;
  if (asBlocks) return body;
  const label = contest.kind === 'measure' ? 'What it does' : 'About this list';
  return el('details', { class: 'vg-details' }, el('summary', {}, label), body);
}

// ── tabbed "more" panels ──────────────────────────────────────────────────
// One <details> per measure / candidate; tabs swap the panel body in place.
const TAB_STATE = {};

function renderTabs(id, tabs) {
  const active = TAB_STATE[id] && tabs.some(t => t.key === TAB_STATE[id]) ? TAB_STATE[id] : tabs[0].key;
  const panel = el('div', { class: 'vg-tab-panel', role: 'tabpanel' });
  const bar = el('div', { class: 'vg-tab-bar', role: 'tablist' });
  const show = key => {
    TAB_STATE[id] = key;
    bar.querySelectorAll('button').forEach(b => {
      const on = b.dataset.key === key;
      b.classList.toggle('is-active', on);
      b.setAttribute('aria-selected', String(on));
    });
    panel.replaceChildren(...[].concat(tabs.find(t => t.key === key).render() || []).flat(Infinity).filter(Boolean));
  };
  for (const t of tabs) {
    bar.append(el('button', { type: 'button', role: 'tab', class: 'vg-tab', 'data-key': t.key, onclick: () => show(t.key) }, t.label));
  }
  const wrap = el('div', { class: 'vg-tabs' }, bar, panel);
  show(active);
  return wrap;
}

function emptyNote(text) { return el('p', { class: 'vg-empty-note' }, text); }

function sourceLine(label, url, extra) {
  return el('p', { class: 'vg-fineprint' }, 'Source: ', el('a', { href: url, target: '_blank', rel: 'noopener' }, label), extra ? ` ${extra}` : '');
}

function goosebasePosition(contest, candidateName) {
  const picks = picksFor(contest.id).filter(p => contest.kind !== 'office' || !candidateName || p.target === candidateName);
  if (!picks.length) {
    return el('p', { class: 'vg-position' }, el('strong', {}, 'Goosebase position: '), 'none yet.');
  }
  return picks.map(p => el('div', { class: 'vg-position' }, el('strong', {}, 'Goosebase position: '), badge(p.verdict),
    p.target && contest.kind === 'office' ? ` ${p.target}` : contest.kind !== 'office' ? ` (vote ${p.verdict === 'egg' ? 'YES' : 'NO'})` : '',
    el('p', {}, p.reasoning)));
}

// Measures ---------------------------------------------------------------
function measureMoney(contest) {
  const local = MONEY?.measures?.[contest.id];
  if (local) {
    const sides = ['yes', 'no'].map(side => {
      const comms = local.filter(c => c.side === side && c.total > 0);
      return el('div', { class: 'vg-money-side' }, el('h4', {}, side === 'yes' ? 'Committees for YES' : 'Committees for NO'),
        comms.length ? comms.map(c => el('div', { class: 'vg-money-comm' },
          el('div', { class: 'vg-money-head' }, el('span', {}, c.name), el('strong', { class: 'vg-num' }, shortMoney(c.total))),
          el('p', { class: 'vg-fineprint' }, `${c.donors} itemized donors; the top ${c.top.length} gave ${floorPct(c.top_share)}.`),
          el('ol', { class: 'vg-donors' }, c.top.slice(0, 5).map(t => el('li', {}, `${t.name} `, el('strong', {}, shortMoney(t.amount))))),
          Object.values(MONEY.measures).filter(list => list.some(x => x.nid === c.nid)).length > 1
            ? el('p', { class: 'vg-fineprint' }, 'This committee campaigns on several measures, so its money can’t be split between them.') : null))
        : emptyNote('No committee with money reported.'));
    });
    return [el('div', { class: 'vg-money-sides' }, sides),
      sourceLine('SF Ethics Commission filings (DataSF)', MONEY.source.url, `since ${sinceLabel()}; latest filing versions only.`)];
  }
  const st = STATE_MONEY?.props?.[contest.id];
  if (st) {
    if (!st.support && !st.oppose) {
      return [emptyNote('No committee has reported contributions for or against this measure.'), sourceLine(STATE_MONEY.source.label, st.url)];
    }
    const sides = [['support', 'Committees for YES'], ['oppose', 'Committees for NO']].map(([k, label]) =>
      el('div', { class: 'vg-money-side' }, el('h4', {}, label),
        st[k] ? [el('p', {}, el('strong', { class: 'vg-num vg-big' }, shortMoney(st[k].total)), ' reported'),
          el('ul', { class: 'vg-donors' }, [...st[k].committees].sort((a, b) => b.total - a.total).slice(0, 5).map(c =>
            el('li', {}, `${c.name} `, el('strong', {}, shortMoney(c.total)))))]
          : emptyNote('No committee reported.')));
    return [el('div', { class: 'vg-money-sides' }, sides),
      sourceLine(STATE_MONEY.source.label, st.url, `through ${st.as_of}. Committees active on several props appear under each one.`)];
  }
  if (contest.id === 'rtm') return emptyNote('The regional committees report outside SF’s system, so this guide doesn’t cover their money yet.');
  return emptyNote('No money data for this measure yet.');
}

function renderMeasureMore(contest) {
  if (!hasDepth(contest)) {
    const src = BALLOT.election.official_sources?.[0];
    return el('p', { class: 'vg-fineprint vg-preview-note' },
      'Early preview: title only. Full text, the impartial analysis and arguments are in the ',
      src ? el('a', { href: src.url, target: '_blank', rel: 'noopener' }, 'county’s official materials') : 'county voter guide', '.');
  }
  const a = ANALYSIS?.measures?.[contest.id];
  return el('details', { class: 'vg-details vg-more' }, el('summary', {}, 'More about this measure'),
    renderTabs(contest.id, [
      { key: 'does', label: 'What it does', render: () => renderDetails(contest, true) || emptyNote('No official summary.') },
      { key: 'money', label: 'Money', render: () => measureMoney(contest) },
      { key: 'goose', label: 'Average goose', render: () => a?.goose
          ? [el('p', {}, a.goose), el('p', { class: 'vg-fineprint' }, 'Our plain-English read of the official digest and fiscal analysis. ', ANALYSIS.renter_share_note)]
          : emptyNote('Coming soon.') },
      { key: 'tldr', label: 'Seriously TL;DR', render: () => [a?.tldr ? el('p', { class: 'vg-tldr' }, a.tldr) : emptyNote('Coming soon.'), goosebasePosition(contest)] },
    ]));
}

// Candidates -------------------------------------------------------------
function backingGroups(contestId, name) {
  const pos = BALLOT_POSITIONS[contestId] || {};
  return GUIDES.guides.filter(g => pos[g.id] && normPosition(pos[g.id]).kind === 'picks' && normPosition(pos[g.id]).value.includes(name));
}

function candidateMoney(contest, c) {
  const f = FUNDING?.candidates?.[contest.id]?.[c.name];
  const outside = MONEY?.candidates?.[contest.id]?.[c.name]?.outside || [];
  if (!f) return externalCandidateMoney(contest, c);
  if (f.no_committee && !outside.length) return emptyNote('No SF campaign committee on file. Candidates who raise under $2,000 don’t have to form one.');
  const own = (f.total || 0) + (f.public_funds || 0);
  return [
    el('div', { class: 'vg-money-sides' },
      el('div', { class: 'vg-money-side' }, el('h4', {}, 'The campaign’s own money'),
        el('p', {}, el('strong', { class: 'vg-num vg-big' }, shortMoney(own))),
        el('ul', { class: 'vg-donors' },
          el('li', {}, `Contributions: ${shortMoney(f.total || 0)}${f.donors ? ` from ${f.donors} donors` : ''}`),
          f.public_funds ? el('li', {}, `Public financing: ${shortMoney(f.public_funds)}`) : null,
          f.total ? el('li', {}, `Small donors (≤$${FUNDING.rules.small_candidate}): `, el('strong', {}, floorPct(f.small_pct))) : null,
          f.total ? el('li', {}, 'Tech / VC donors: ', el('strong', {}, floorPct(f.tech_pct))) : null)),
      el('div', { class: 'vg-money-side' }, el('h4', {}, 'Outside committees'),
        outside.length ? el('ul', { class: 'vg-donors' }, outside.slice(0, 6).map(o => el('li', {}, `${o.committee} `,
          o.support ? el('strong', { class: 'vg-for' }, `+${shortMoney(o.support)} for`) : null,
          o.support && o.oppose ? ' · ' : null,
          o.oppose ? el('strong', { class: 'vg-against' }, `${shortMoney(o.oppose)} against`) : null)))
          : emptyNote('None reported.'))),
    sourceLine('SF Ethics Commission filings (DataSF)', MONEY?.source?.url || FUNDING.source.url,
      `since ${sinceLabel()}. Public funds: SF Ethics “Total Public Funds Approved”. Outside spending isn’t coordinated with the campaign.`)];
}

function candidateWho(contest, c) {
  const a = ANALYSIS?.candidates?.[contest.id]?.[c.name];
  const groups = backingGroups(contest.id, c.name);
  const basics = [c.designation, c.party ? `${c.party} Party preference` : null, c.incumbent ? 'Incumbent' : null].filter(Boolean).join(' · ');
  return [
    el('p', {}, a?.who || c.who || basics || 'No sourced description yet.'),
    !a?.who && c.who && basics ? el('p', { class: 'vg-fineprint' }, `On the ballot: ${basics}`) : null,
    !a?.who && !c.who && contest.statement_note ? el('p', { class: 'vg-fineprint' }, contest.statement_note) : null,
    groups.length ? el('p', { class: 'vg-who-groups' }, 'Recommended by: ', groups.map(g => el('span', { class: `vg-chip vg-cat-${primaryCat(g)}` }, g.short))) : null,
    a?.source ? sourceLine('KQED voter guide', a.source, '(candidate interviews, questionnaires and debates).')
      : c.who_source?.url ? sourceLine(c.who_source.label, c.who_source.url, '(our summary; claims are the candidate’s own).') : null];
}

function candidateTldr(contest, c) {
  const a = ANALYSIS?.candidates?.[contest.id]?.[c.name];
  const f = FUNDING?.candidates?.[contest.id]?.[c.name];
  const groups = backingGroups(contest.id, c.name);
  // First sentence of the description; a sentence must end on a word with 3+ lowercase letters,
  // so abbreviations like "Rep." or "Jr." don't cut it short.
  const firstSentence = t => (t.match(/^.*?[a-z]{3,}[.!?](?=\s|$)/) || [t])[0];
  const who = a?.who || c.who;
  const first = who ? firstSentence(who) : `${c.designation || 'Candidate'}${c.incumbent ? ' (incumbent)' : ''}.`;
  const outsideTag = f?.tags?.find(t => t.tag === 'outside-backed');
  const second = groups.length
    ? `Recommended by ${groups.slice(0, 3).map(g => g.short).join(', ')}${groups.length > 3 ? ` and ${groups.length - 3} more` : ''}${outsideTag ? `, with ${shortMoney(outsideTag.amount)} in outside support` : ''}.`
    : outsideTag ? `Backed by ${shortMoney(outsideTag.amount)} in outside support.` : 'None of the groups we track recommends this candidate.';
  return [el('p', { class: 'vg-tldr' }, `${first} ${second}`), goosebasePosition(contest, c.name)];
}

function hasDepth(contest) {
  if (!PREVIEW) return true;
  const id = contest.id;
  return !!(ANALYSIS?.candidates?.[id] || EXTERNAL?.candidates?.[id] || FUNDING?.candidates?.[id]
    || ANALYSIS?.measures?.[id] || contest.summary || contest.statement_note
    || (contest.candidates || []).some(c => c.who));
}

function renderCandidateMore(contest, c) {
  if (!hasDepth(contest)) return null;
  const a = ANALYSIS?.candidates?.[contest.id]?.[c.name];
  const firstName = c.name.replace(/[“"(].*?[”")]/g, ' ').trim().split(/\s+/)[0];
  return el('details', { class: 'vg-cand-more' }, el('summary', {}, `More on ${firstName}`),
    renderTabs(`${contest.id}::${c.name}`, [
      { key: 'who', label: 'Who?', render: () => candidateWho(contest, c) },
      { key: 'money', label: 'Money', render: () => candidateMoney(contest, c) },
      { key: 'goose', label: 'Average goose', render: () => a?.goose
          ? [el('p', {}, a.goose), sourceLine('KQED voter guide', a.source, '(our summary).')]
          : emptyNote('We don’t have a sourced summary of this candidate’s positions yet.') },
      { key: 'tldr', label: 'Seriously TL;DR', render: () => candidateTldr(contest, c) },
    ]));
}


// State (Cal-Access) and federal (FEC) candidates --------------------------
function outsideList(rows) {
  return rows.length ? el('ul', { class: 'vg-donors' }, rows.slice(0, 6).map(o => el('li', {}, `${o.committee} `,
    o.support ? el('strong', { class: 'vg-for' }, `+${shortMoney(o.support)} for`) : null,
    o.support && o.oppose ? ' · ' : null,
    o.oppose ? el('strong', { class: 'vg-against' }, `${shortMoney(o.oppose)} against`) : null,
    (o.notes || []).map(n => el('div', { class: 'vg-filing-note' }, '⚠ ', n)))))
    : emptyNote('None reported.');
}

function externalCandidateMoney(contest, c) {
  const x = EXTERNAL?.candidates?.[contest.id]?.[c.name];
  if (!x) return emptyNote(contest.id.startsWith('us-rep')
    ? 'FEC figures for this race haven’t been loaded into this build yet.'
    : 'No campaign-finance data found for this candidate.');
  const federal = contest.id.startsWith('us-rep');
  const src = federal ? EXTERNAL.sources.federal : EXTERNAL.sources.state;
  if (x.no_committee && !(x.outside || []).length) {
    return [emptyNote(x.note || 'No 2026 campaign committee found for this candidate.'), sourceLine(src.label, src.url)];
  }
  return [
    el('div', { class: 'vg-money-sides' },
      el('div', { class: 'vg-money-side' }, el('h4', {}, 'The campaign’s own money'),
        el('p', {}, el('strong', { class: 'vg-num vg-big' }, shortMoney(x.total || 0)), federal ? ' raised this cycle' : ' raised since Jan 2025'),
        el('ul', { class: 'vg-donors' },
          x.small_pct != null ? el('li', {}, `Small donors (under $${federal ? 200 : 100}): `, el('strong', {}, floorPct(x.small_pct))) : null,
          x.pac ? el('li', {}, `From PACs and other committees: ${shortMoney(x.pac)}`) : null,
          x.through ? el('li', {}, `Reports through ${formatDate(x.through)}`) : null)),
      el('div', { class: 'vg-money-side' }, el('h4', {}, 'Outside committees'), outsideList(x.outside || []))),
    sourceLine(src.label, x.fec_url || src.url,
      federal ? 'Independent expenditures from FEC Schedule E.' : 'Outside money: Form 496 independent expenditures (filed in the 90 days before an election).')];
}

// Judicial retention ------------------------------------------------------
function renderRetentionMore(contest) {
  const r = ANALYSIS?.retention?.[contest.id];
  const how = ANALYSIS?.retention?._how;
  const groups = GUIDES.guides.filter(g => {
    const v = BALLOT_POSITIONS[contest.id]?.[g.id];
    return v && normPosition(v).kind === 'vote' && normPosition(v).value === 'yes';
  });
  const jm = EXTERNAL?.judicial?.[contest.id];
  return el('details', { class: 'vg-details vg-more' }, el('summary', {}, 'More about this justice'),
    renderTabs(contest.id, [
      { key: 'who', label: 'Who?', render: () => [
          el('p', {}, r?.who || 'No sourced biography yet.'),
          groups.length ? el('p', { class: 'vg-who-groups' }, 'Recommend YES: ', groups.map(g => el('span', { class: `vg-chip vg-cat-${primaryCat(g)}` }, g.short))) : null,
          r?.source ? sourceLine(r.source.includes('vig.cdn') ? 'CA Official Voter Information Guide' : 'Court of Appeal biography (official)', r.source) : null] },
      { key: 'money', label: 'Money', render: () => jm
          ? [jm.committees?.length ? outsideList(jm.committees) : emptyNote('No campaign committee or independent expenditure in Cal-Access names this justice (2025–26).'),
             sourceLine(EXTERNAL.sources.state.label, EXTERNAL.sources.state.url, 'Judicial retention campaigns rarely raise money.')]
          : emptyNote('No money data yet.') },
      { key: 'goose', label: 'Average goose', render: () => how ? [el('p', {}, how.goose),
          el('p', { class: 'vg-fineprint' }, 'Sources: ', how.sources.map((s, i) => [i ? ' · ' : '', el('a', { href: s.url, target: '_blank', rel: 'noopener' }, s.label)]))] : emptyNote('Coming soon.') },
      { key: 'tldr', label: 'Seriously TL;DR', render: () => {
          const first = r?.who ? (r.who.match(/^.*?[a-z]{3,}[.!?](?=\s|$)/) || [r.who])[0] : `${contest.justice}.`;
          const second = groups.length ? `${groups.map(g => g.short).join(', ')} recommend${groups.length === 1 ? 's' : ''} keeping ${contest.justice.split(' ').slice(-1)[0]}; no group we track recommends NO.` : 'None of the groups we track takes a position.';
          return [el('p', { class: 'vg-tldr' }, `${first} ${second}`), goosebasePosition(contest)];
        } },
    ]));
}

// ── contest card ──────────────────────────────────────────────────────────
function instructionFor(contest, section) {
  if (contest.kind === 'retention') return null;
  if (contest.rcv) return `Rank up to ${rcvRanks(contest)} choice${rcvRanks(contest) > 1 ? 's' : ''}`;
  if (contest.kind === 'office') {
    const n = voteFor(contest);
    if (n > 1) return `Vote for no more than ${['', 'One', 'Two', 'Three'][n] || n}`;
    if (!section.instruction) return 'Vote for One';
  }
  return null;
}

function renderContest(contest, section) {
  let body;
  if (contest.kind === 'office') body = contest.rcv ? renderRcvGrid(contest) : renderOfficeRows(contest);
  else if (contest.kind === 'retention') body = renderYesNo(contest);
  else body = renderYesNo(contest);

  const isMeasure = contest.kind === 'measure';
  const title = isMeasure
    ? el('h3', { class: 'vg-contest-title' },
        el('span', { class: 'vg-letter' }, contest.letter), contest.title)
    : el('h3', { class: 'vg-contest-title' }, contest.title);

  return el('article', {
    class: `vg-contest vg-kind-${contest.kind}` + (getMark(contest.id) ? ' is-done' : ''),
    id: contest.id, 'data-contest': contest.id,
  },
    el('header', { class: 'vg-contest-head' },
      title,
      contest.kind === 'retention'
        ? el('p', { class: 'vg-sub' }, `Shall ${contest.title.startsWith('Presiding') ? 'Presiding' : 'Associate'} Justice `,
            el('strong', {}, contest.justice), ' be elected to the office for the term provided by law?')
        : null,
      contest.subtitle ? el('p', { class: 'vg-sub' }, contest.subtitle) : null,
      instructionFor(contest, section) ? el('p', { class: 'vg-instr' }, instructionFor(contest, section)) : null,
      // Tag district-only contests unless the reader already picked that district.
      contest.applies && state.districts[Object.keys(contest.applies)[0]] == null
        ? el('span', { class: 'vg-tag' }, districtTag(contest)) : null),
    body,
    el('p', { class: 'vg-flash', role: 'status', hidden: true }),
    renderPickBox(contest),
    renderGuideLine(contest),
    isMeasure ? renderMeasureMore(contest)
      : contest.kind === 'retention' ? renderRetentionMore(contest) : renderDetails(contest));
}

const CONTEST_INDEX = {};        // id → { contest, section }
let BALLOT_POSITIONS = {};

function rerenderContest(id) {
  const node = document.querySelector(`[data-contest="${id}"]`);
  const hit = CONTEST_INDEX[id];
  if (!node || !hit) return;
  const wasOpen = node.querySelector('details')?.open;
  const fresh = renderContest(hit.contest, hit.section);
  if (wasOpen) fresh.querySelector('details')?.setAttribute('open', '');
  node.replaceWith(fresh);
}

// ── page sections ─────────────────────────────────────────────────────────
function visibleContests() {
  const out = [];
  for (const s of BALLOT.sections) for (const c of s.contests) if (appliesToReader(c)) out.push([c, s]);
  return out;
}

// ── collapsible sections ──────────────────────────────────────────────────
// Each ballot section folds away so a phone reader can work through the
// ballot one section at a time. By default only the first section is open.
function visibleSections() {
  return BALLOT.sections.filter(s => s.contests.some(shown));
}

// Ballot + topic filter. Progress counts ignore the topic filter on purpose:
// filtering is a way to browse, not a smaller ballot.
function shown(contest) {
  return appliesToReader(contest) && matchesTopics(contest);
}

function isCollapsed(section) {
  if (state.topics.length) return false;          // filtered view: everything open
  if (section.id in state.collapsed) return state.collapsed[section.id];
  return visibleSections()[0]?.id !== section.id;
}

function sectionCounts(section) {
  const contests = section.contests.filter(appliesToReader);
  return { done: contests.filter(c => getMark(c.id)).length, total: contests.length };
}

function setCollapsed(sectionId, collapsed) {
  state.collapsed[sectionId] = collapsed;
  saveState();
  const node = document.querySelector(`[data-section="${sectionId}"]`);
  if (!node) return;
  node.classList.toggle('is-collapsed', collapsed);
  node.querySelector('.vg-section-bar').setAttribute('aria-expanded', String(!collapsed));
}

function finishSection(section) {
  const order = visibleSections();
  const next = order[order.findIndex(s => s.id === section.id) + 1];
  setCollapsed(section.id, true);
  if (next) {
    setCollapsed(next.id, false);
    document.querySelector(`[data-section="${next.id}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  } else {
    document.getElementById('progress').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
}

function sectionStatus(section) {
  const { done, total } = sectionCounts(section);
  return el('span', { class: 'vg-section-status' + (done === total ? ' is-complete' : '') },
    done === total ? `✓ ${done}/${total}` : `${done}/${total}`);
}

function renderSection(section) {
  const contests = section.contests.filter(shown);
  const collapsed = isCollapsed(section);
  const order = visibleSections();
  const isLast = order[order.length - 1]?.id === section.id;
  return el('section', {
    class: 'vg-section' + (collapsed ? ' is-collapsed' : ''), 'data-section': section.id,
    'aria-label': section.heading,
  },
    el('button', {
      type: 'button', class: 'vg-section-bar', 'aria-expanded': String(!collapsed),
      onclick: () => setCollapsed(section.id, !isCollapsed(section)),
    },
      el('span', { class: 'vg-section-name' }, section.heading),
      el('span', { class: 'vg-section-meta' },
        section.instruction ? el('span', { class: 'vg-section-instr' }, section.instruction) : null,
        sectionStatus(section),
        el('span', { class: 'vg-chevron', 'aria-hidden': 'true' }))),
    el('div', { class: 'vg-section-body' },
      section.note ? el('p', { class: 'vg-section-note' }, section.note) : null,
      contests.map(c => renderContest(c, section)),
      el('div', { class: 'vg-section-foot' },
        el('button', { type: 'button', class: 'btn-ghost vg-btn', onclick: () => finishSection(section) },
          isLast ? 'Done with this section ✓' : 'Done, next section ↓'))));
}

function refreshSectionStatus(sectionId) {
  const section = BALLOT.sections.find(s => s.id === sectionId);
  const old = document.querySelector(`[data-section="${sectionId}"] .vg-section-status`);
  if (section && old) old.replaceWith(sectionStatus(section));
}

function renderBallot() {
  const root = document.getElementById('ballot');
  root.replaceChildren();
  let lastGroup = null;
  for (const section of visibleSections()) {
    if (section.group !== lastGroup) {
      root.append(el('h2', { class: 'vg-group' }, section.group === 'offices' ? 'Offices' : 'Measures'));
      lastGroup = section.group;
    }
    root.append(renderSection(section));
  }
}

// ── ZIP → districts ───────────────────────────────────────────────────────
// A ZIP narrows each district picker to the districts it overlaps. It only
// auto-selects when the ZIP sits (almost) entirely inside one district;
// otherwise the reader picks, because area share isn't where *they* live.
function zipOptions() {
  const z = state.zip && ZIPS?.zips[state.zip];
  if (!z) return null;
  const out = {};
  for (const dim of Object.keys(BALLOT.districts)) out[dim] = z[dim] || [];
  return out;
}

function applyZip(zip) {
  const msg = document.getElementById('zip-msg');
  const clearBtn = document.getElementById('zip-clear');
  state.zip = zip || null;
  clearBtn.hidden = !state.zip;
  if (!state.zip) {
    msg.textContent = '';
    msg.className = 'vg-zip-msg';
  } else if (!ZIPS.zips[state.zip]) {
    msg.className = 'vg-zip-msg is-warn';
    msg.textContent = state.zip.startsWith('941')
      ? `We don't have boundary data for ${state.zip} (PO-box ZIPs have none). Choose your districts below.`
      : `${state.zip} isn't a San Francisco ZIP. Alameda and San Mateo County previews are linked above; other counties aren't covered yet.`;
    state.zip = null;
  } else {
    const opts = zipOptions();
    const unresolved = [];
    for (const dim of Object.keys(BALLOT.districts)) {
      const list = opts[dim];
      const sole = list.length === 1 || (list[0] && list[0][1] >= SOLE_SHARE);
      if (sole) state.districts[dim] = list[0][0];
      else {
        if (!list.some(([n]) => n === state.districts[dim])) delete state.districts[dim];
        if (state.districts[dim] == null) unresolved.push(BALLOT.districts[dim].label);
      }
    }
    msg.className = 'vg-zip-msg' + (unresolved.length ? ' is-warn' : ' is-ok');
    msg.textContent = unresolved.length
      ? `${state.zip} crosses district lines for: ${unresolved.join(', ')}. Pick yours below, using your sample ballot or the Voter Portal.`
      : `Ballot filtered for ${state.zip}.`;
    if (unresolved.length) document.getElementById('districts-box').open = true;
  }
  saveState();
  renderDistricts();
  renderBallot();
  renderProgress();
}

function initZip() {
  const form = document.getElementById('zip-form');
  const input = document.getElementById('zip');
  input.value = state.zip || '';
  form.addEventListener('submit', e => {
    e.preventDefault();
    const v = input.value.trim();
    if (v && !/^\d{5}$/.test(v)) {
      const msg = document.getElementById('zip-msg');
      msg.className = 'vg-zip-msg is-warn';
      msg.textContent = 'Enter a 5-digit ZIP code.';
      return;
    }
    applyZip(v);
  });
  document.getElementById('zip-clear').addEventListener('click', () => {
    input.value = '';
    state.districts = {};
    applyZip('');
  });
}

function renderDistricts() {
  const box = document.getElementById('districts');
  box.replaceChildren();
  const zopts = zipOptions();
  const summary = [];
  for (const [dim, spec] of Object.entries(BALLOT.districts)) {
    const allowed = zopts ? zopts[dim] : spec.options.map(n => [n, null]);
    const sel = el('select', {
      id: `d-${dim}`, onchange: e => {
        const v = e.target.value;
        if (v === '') delete state.districts[dim]; else state.districts[dim] = Number(v);
        saveState(); renderDistricts(); renderBallot(); renderProgress();
      },
    }, el('option', { value: '' }, zopts && allowed.length > 1 ? 'Choose…' : 'Show all'),
      allowed.map(([n, share]) => el('option', { value: n, selected: state.districts[dim] === n },
        share != null && allowed.length > 1 ? `${n} (${Math.max(1, Math.round(share * 100))}% of ZIP area)` : optionLabel(dim, n))));
    box.append(el('label', { class: 'vg-district' },
      el('span', { class: 'vg-district-label' }, spec.label), sel,
      spec.note ? el('span', { class: 'vg-district-note' }, spec.note) : null));
    const v = state.districts[dim];
    if (v != null) summary.push(dim === 'city' || v === 0 ? optionLabel(dim, v) : `${DIM_SHORT[dim]} ${v}`);
  }
  document.getElementById('districts-summary').textContent = summary.length ? `· ${summary.join(' · ')}` : '· showing all';
}

function renderProgress() {
  const total = visibleContests().length;
  const done = visibleContests().filter(([c]) => getMark(c.id)).length;
  const bar = document.getElementById('progress');
  bar.hidden = false;
  document.getElementById('progress-text').textContent =
    done ? `${done} of ${total} contests marked` : `${total} contests on your ballot`;
}

// ── topics (our editorial tags on measures) ───────────────────────────────
function topicTags(contest) {
  return (TOPICS?.tags || {})[contest.id] || [];
}

function matchesTopics(contest) {
  if (!state.topics.length) return true;
  return topicTags(contest).some(t => state.topics.includes(t.topic));
}

function topicLabel(id) {
  return TOPICS.topics.find(t => t.id === id)?.label || id;
}

const ARROW = { up: '↑', down: '↓', stable: '=', limit: '⊘' };

// Tags sit on the line of the vote that causes them: most on YES, but e.g.
// voting NO on extending a tax lets it lapse, so that tag goes on NO.
const TAX_TOPICS = new Set(['personal-tax', 'business-tax']);
const TAX_EFFECT = {
  up: '↑ Increase', stable: '= Stable', down: '↓ Decrease', limit: '⊘ Limits new taxes',
};

function tagsForVote(contest, vote) {
  return topicTags(contest).filter(t => (t.on || 'yes') === vote);
}

// Tax tags render as two chips: a neutral topic chip and a colored effect
// chip. Other topics keep a single chip with an arrow.
function renderTopicTags(contest, vote = 'yes') {
  const tags = tagsForVote(contest, vote);
  if (!tags.length) return null;
  return el('ul', { class: 'vg-topic-tags', 'aria-label': 'Topics' }, tags.flatMap(t => {
    const active = state.topics.includes(t.topic) ? ' is-active' : '';
    if (TAX_TOPICS.has(t.topic) && t.effect) {
      return [el('li', { class: 'vg-topic-tag vg-tax-pair' + active, title: t.why },
        el('span', { class: 'vg-tax-topic' }, topicLabel(t.topic)),
        el('span', { class: `vg-effect vg-effect-${t.effect}` }, TAX_EFFECT[t.effect]))];
    }
    return [el('li', { class: 'vg-topic-tag' + active, title: t.why },
      topicLabel(t.topic), t.effect ? el('span', { class: 'vg-arrow' }, ` ${ARROW[t.effect]}`) : null)];
  }));
}

// One quiet line per tax tag: how many it touches and who, in plain terms.
function renderTopicImpact(contest, vote = 'yes') {
  const seen = new Set();
  const lines = tagsForVote(contest, vote).filter(t => {
    const key = `${t.share || ''}|${t.affects_if || ''}`;
    if (!(t.share || t.affects_if) || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  if (!lines.length) return null;
  return el('div', { class: 'vg-impact' }, lines.map(t => el('p', {},
    lines.length > 1 ? el('span', { class: 'vg-impact-topic' }, `${topicLabel(t.topic)}: `) : null,
    t.share ? el('span', { class: 'vg-impact-share' }, highlightNumbers(t.share)) : null,
    t.share && t.affects_if ? ' · ' : null,
    t.affects_if ? (t.affects_if.startsWith('No one') ? t.affects_if
      : [el('span', { class: 'vg-impact-label' }, 'Affects you if '), highlightNumbers(t.affects_if)]) : null)));
}

function renderTopicBar() {
  const box = document.getElementById('topics');
  if (!TOPICS?.topics?.length) return;
  box.hidden = false;
  const counts = {};
  for (const [cid, tags] of Object.entries(TOPICS.tags)) {
    if (!CONTEST_INDEX[cid] || !appliesToReader(CONTEST_INDEX[cid].contest)) continue;
    for (const t of new Set(tags.map(t => t.topic))) counts[t] = (counts[t] || 0) + 1;
  }
  const toggle = id => {
    state.topics = state.topics.includes(id) ? state.topics.filter(t => t !== id) : [...state.topics, id];
    saveState(); renderTopicBar(); renderBallot();
  };
  box.replaceChildren(
    el('div', { class: 'vg-topics-head' },
      el('span', { class: 'vg-topics-title' }, 'Browse measures by topic'),
      state.topics.length
        ? el('button', { type: 'button', class: 'vg-topics-clear', onclick: () => { state.topics = []; saveState(); renderTopicBar(); renderBallot(); } }, 'Show everything')
        : null),
    el('div', { class: 'vg-topic-chips' }, TOPICS.topics.map(t => el('button', {
      type: 'button', class: 'vg-topic-chip' + (state.topics.includes(t.id) ? ' is-active' : ''),
      'aria-pressed': String(state.topics.includes(t.id)), title: t.description, onclick: () => toggle(t.id),
    }, t.label, el('span', { class: 'vg-topic-count' }, String(counts[t.id] || 0))))),
    state.topics.length
      ? el('p', { class: 'vg-fineprint' }, `Showing only measures tagged ${state.topics.map(topicLabel).join(' or ')}. Offices are hidden while a topic is selected.`)
      : el('p', { class: 'vg-fineprint' }, 'Topic tags are our own labels: what a measure is about and which way a YES vote moves it, not whether it’s good. Hover or long-press a tag for the reason.'));
}

// Wrap money and percentages ("~2%", "$371K", "$1 billion", "$129+") so they stand out.
const NUM_RE = /(~?\$\d[\d,.]*(?:K|M|B)?\+?(?: (?:billion|million))?|~?\d[\d,.]*%)/g;  // money or percent only, not dates/ages
function highlightNumbers(text) {
  return text.split(NUM_RE).map((part, i) => i % 2 ? el('strong', { class: 'vg-num' }, part) : part);
}

function primaryCat(guide) {
  return guide.tags?.find(t => t.cat !== 'scope')?.cat || 'none';
}

// ── funding & housing tags (evidence-based; rules in tools/funding_tags.py) ──
const FUNDING_LABEL = {
  'small-donor': 'Small-donor funded', 'big-donor': 'Big-donor funded',
  'tech-funded': 'Tech-funded', 'outside-backed': 'Outside money',
};

function shortMoney(n) {
  return n >= 1e6 ? `$${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `$${Math.round(n / 1e3)}K` : `$${Math.round(n)}`;
}

function fundingRuleText(tag) {
  const r = FUNDING?.rules || {};
  const pct = k => `${Math.round((r.thresholds?.[k] || 0) * 100)}%`;
  return {
    'small-donor': `At least ${pct('small-donor')} of the money came from donors giving $${r.small_candidate} or less in total (candidates) or $${r.small_guide} or less (groups), counting unitemized gifts.`,
    'big-donor': `At least ${pct('big-donor')} of the money came from donors giving $${(r.big || 0).toLocaleString()}+ in total.`,
    'tech-funded': `At least ${pct('tech-funded')} of the money came from donors employed in tech or venture capital (by employer/occupation).`,
    'outside-backed': 'Other committees spent or gave more supporting this candidate than the candidate raised (and at least $10K).',
  }[tag] + ` SF Ethics data since ${sinceLabel()}.`;
}

// Round DOWN so 99.6% never reads as "100%".
function floorPct(x) { return `${Math.floor((x || 0) * 100)}%`; }
function sinceLabel() {
  const [y, m] = (FUNDING?.since || '').split('-').map(Number);
  return y ? new Date(y, m - 1, 1).toLocaleDateString('en-US', { month: 'short', year: 'numeric' }) : '';
}

function fundingPills(m) {
  if (!m?.tags?.length) return [];
  return m.tags.map(t => el('span', { class: `vg-fund-pill vg-fund-${t.tag}`, title: fundingRuleText(t.tag) },
    FUNDING_LABEL[t.tag], ' ', el('strong', {}, t.pct != null ? floorPct(t.pct) : shortMoney(t.amount))));
}

function fundingMix(m) {
  if (!m?.total) return null;
  const pct = floorPct;
  return el('dd', { class: 'vg-fund-mix' },
    `Funding mix (SF committees since ${sinceLabel()}, ${shortMoney(m.total)}): `,
    el('strong', {}, pct(m.small_pct)), ' small donors · ',
    m.big_pct != null ? [el('strong', {}, pct(m.big_pct)), ' $10K+ donors · '] : null,
    el('strong', {}, pct(m.tech_pct)), ' tech/VC.');
}

function yimbyEndorses(contestId, name) {
  const v = BALLOT_POSITIONS[contestId]?.yimby;
  return v && normPosition(v).kind === 'picks' && normPosition(v).value.includes(name);
}

function renderCandidateTags(contest, name) {
  const pills = [];
  if (yimbyEndorses(contest.id, name)) {
    pills.push(el('span', { class: 'vg-cand-tag vg-cat-housing', title: 'Endorsed by YIMBY Action / SF YIMBY, whose members back candidates "for making more homes possible."' },
      'Pro-housing (YIMBY)'));
  }
  const m = FUNDING?.candidates?.[contest.id]?.[name];
  if (m) pills.push(...fundingPills(m));
  if (m?.no_committee) {
    pills.push(el('span', { class: 'vg-fund-pill vg-fund-none', title: 'No SF campaign committee on file. Candidates who raise under $2,000 don’t have to form one.' }, 'No campaign committee'));
  }
  return pills.length ? el('div', { class: 'vg-cand-tags' }, pills) : null;
}

// ── "Other groups included" panel ─────────────────────────────────────────
function money(m) {
  if (m.text) return m.text;
  const n = m.amount;
  const amt = n >= 1e6 ? `$${(n / 1e6).toFixed(2)}M` : `$${Math.round(n / 1e3)}K`;
  return `${amt} · ${m.period}`;
}

// Local (county/city) groups and statewide groups, in that order, each under its own label.
function groupBlocks() {
  const local = GUIDES.guides.filter(g => g.scope !== 'statewide');
  const state = GUIDES.guides.filter(g => g.scope === 'statewide');
  const where = COUNTY === 'sf' ? 'San Francisco' : COUNTIES[COUNTY].name;
  return [[`${where} groups`, local], ['Statewide groups', state]].filter(([, list]) => list.length);
}

function renderGroups() {
  const body = document.getElementById('groups-body');
  body.replaceChildren(
    el('p', { class: 'vg-setup-hint' },
      'These are the published guides we track. Their picks appear as small tags on each ballot line. Money and membership figures are rough public-record numbers.'),
    groupBlocks().map(([label, list]) => [
      el('h4', { class: 'vg-group-divider' }, el('span', {}, label)),
      el('div', { class: 'vg-group-cards' }, list.map(g => el('article', { class: `vg-group-card vg-cat-${primaryCat(g)}` },
      el('header', {},
        el('a', { href: g.url, target: '_blank', rel: 'noopener', class: 'vg-group-name' }, g.name),
        el('span', { class: 'vg-group-tags' }, (g.tags || []).map(t =>
          el('span', { class: `vg-group-tag vg-cat-${t.cat}` }, t.label)),
          fundingPills(FUNDING?.guides?.[g.id]))),
      g.self_description
        ? el('blockquote', { class: 'vg-self' },
            el('span', { class: 'vg-self-label' }, 'In their words'),
            el('p', {}, `“${g.self_description.text}”`),
            el('a', { href: g.self_description.source, target: '_blank', rel: 'noopener', class: 'vg-src-link' }, 'source'))
        : g.self_description_missing ? el('p', { class: 'vg-fineprint' }, g.self_description_missing) : null,
      g.about ? el('p', { class: 'vg-group-about' }, g.about) : null,
      g.sources ? el('ul', { class: 'vg-group-sources' }, g.sources.map(s =>
        el('li', {}, el('a', { href: s.url, target: '_blank', rel: 'noopener', class: 'vg-src-link' }, s.label)))) : null,
      el('dl', {},
        el('dt', {}, 'Money'),
        fundingMix(FUNDING?.guides?.[g.id]),
        el('dd', {}, el('ul', {}, (g.money || []).map(m => el('li', {},
          m.label ? el('span', { class: 'vg-money-label' }, `${m.label}: `) : null, money(m),
          m.note ? el('span', { class: 'vg-money-note' }, ` ${m.note}`) : null,
          m.source ? [' ', el('a', { href: m.source.url, target: '_blank', rel: 'noopener', class: 'vg-src-link' }, 'source')] : null)))),
        el('dt', {}, 'Members'),
        el('dd', {}, g.members?.text || 'Not published.',
          g.members?.source ? [' ', el('a', { href: g.members.source.url, target: '_blank', rel: 'noopener', class: 'vg-src-link' }, 'source')] : null)),
      el('p', { class: 'vg-fineprint' }, `Guide checked ${formatDate(g.accessed)}`))))]),
    GUIDES.money_note ? el('p', { class: 'vg-fineprint' }, GUIDES.money_note) : null);
}

function summaryText(contest) {
  const m = getMark(contest.id);
  if (!m) return null;
  if (contest.kind === 'office' && contest.rcv) {
    return m.map((n, i) => n ? `${RANK_LABEL[i]}: ${n}` : null).filter(Boolean).join(' · ');
  }
  if (Array.isArray(m)) return m.join(', ');
  return m.toUpperCase();
}

function renderSummary() {
  const list = document.getElementById('summary-list');
  list.replaceChildren();
  for (const [c] of visibleContests()) {
    const text = summaryText(c);
    const label = c.kind === 'measure' ? `Prop ${c.letter}` : c.kind === 'retention' ? `${c.justice} (retain?)` : c.title;
    list.append(el('li', { class: text ? '' : 'is-blank' },
      el('a', { href: `#${c.id}`, onclick: () => showSummary(false) }, label),
      el('span', { class: 'vg-summary-choice' }, text || 'not marked')));
  }
}

function showSummary(on) {
  document.getElementById('summary').hidden = !on;
  document.getElementById('ballot').hidden = on;
  document.getElementById('progress').hidden = on;
  if (on) { renderSummary(); document.getElementById('summary').scrollIntoView({ block: 'start' }); }
}

function initToggles() {
  const guides = document.getElementById('show-guides');
  const picks = document.getElementById('show-picks');
  guides.checked = state.showGuides;
  picks.checked = state.showPicks;
  const legend = document.getElementById('legend');
  legend.hidden = !state.showPicks;
  guides.addEventListener('change', () => { state.showGuides = guides.checked; saveState(); renderBallot(); });
  picks.addEventListener('change', () => {
    state.showPicks = picks.checked; legend.hidden = !picks.checked; saveState(); renderBallot();
  });
  document.getElementById('open-summary').addEventListener('click', () => showSummary(true));
  document.getElementById('close-summary').addEventListener('click', () => showSummary(false));
  const clear = document.getElementById('clear-marks');
  clear.addEventListener('click', () => {
    // Two-step confirm (no confirm() dialogs): first click arms, second clears.
    if (!clear.dataset.armed) {
      clear.dataset.armed = '1'; clear.textContent = 'Click again to clear everything';
      setTimeout(() => { delete clear.dataset.armed; clear.textContent = 'Clear all'; }, 4000);
      return;
    }
    state.marks = {}; saveState(); renderSummary(); renderBallot(); renderProgress();
    delete clear.dataset.armed; clear.textContent = 'Clear all';
  });
}

function validate() {
  // Catch transcription slips in preview: guide picks must name real candidates.
  for (const [id, byGuide] of Object.entries(BALLOT_POSITIONS)) {
    const hit = CONTEST_INDEX[id];
    if (!hit) { if (!PREVIEW) console.warn(`[voter-guide] endorsements: unknown contest "${id}"`); continue; }
    const names = new Set((hit.contest.candidates || []).map(c => c.name));
    for (const [g, p] of Object.entries(byGuide)) {
      const n = normPosition(p);
      if (n.kind === 'picks') for (const v of n.value) if (!names.has(v)) console.warn(`[voter-guide] ${g} on ${id}: "${v}" is not on the ballot list`);
    }
  }
  for (const [id, list] of Object.entries(PICKS.picks || {})) {
    if (!CONTEST_INDEX[id] && !PREVIEW) console.warn(`[voter-guide] picks: unknown contest "${id}"`);
    for (const p of list) if (!p.reasoning) console.warn(`[voter-guide] picks: ${id} has no reasoning`);
  }
}

// How much of the local measure text this preview carries, for the banner.
function localMeasureDepth() {
  const local = BALLOT.sections.flatMap(sec => sec.contests).filter(c => c.kind === 'measure' && c.level === 'local');
  const deep = local.filter(c => c.summary).length;
  if (!deep) return ', and local measures show titles only.';
  if (deep === local.length) return '. Local measures include the official question, impartial analysis and arguments.';
  return `. ${deep} of ${local.length} local measures include the official text so far; the rest show titles only.`;
}

function renderCountyChrome() {
  const info = COUNTIES[COUNTY];
  document.getElementById('county-name').textContent = info.name;
  document.getElementById('guide-title').textContent = info.title;
  document.title = `${info.title} · Goosebase`;
  const nav = document.getElementById('county-nav');
  nav.replaceChildren(el('span', { class: 'vg-county-label' }, 'County:'),
    ...Object.entries(COUNTIES).map(([id, c]) => id === COUNTY
      ? el('strong', { class: 'vg-county-opt is-current', 'aria-current': 'page' }, c.name, c.preview ? el('span', { class: 'vg-preview-pill' }, 'preview') : null)
      : el('a', { class: 'vg-county-opt', href: id === 'sf' ? './' : `./?county=${id}` }, c.name, c.preview ? el('span', { class: 'vg-preview-pill' }, 'preview') : null)));
  if (PREVIEW) document.querySelector('.subpage-lead').textContent =
    'Your ballot, contest by contest. Fill in the ovals as you go, see what statewide groups recommend, ' +
    'and take your finished list with you to mark the real thing.';
  if (PREVIEW) {
    // The lookup link in the district hint points at the county's own elections site.
    const link = document.getElementById('lookup-link');
    const src = BALLOT.election.official_sources?.[0];
    if (link && src) { link.href = src.url; link.textContent = `${info.name} elections site`; }
  }
  const banner = document.getElementById('preview-banner');
  banner.hidden = !PREVIEW;
  if (PREVIEW) banner.replaceChildren(el('strong', {}, 'Early preview. '),
    `Every contest and measure here is from ${info.name}'s official lists, but we haven't verified candidate order or ` +
    `district boundaries${localMeasureDepth()} Statewide races carry the same research as the San Francisco guide. ` +
    'Pick your districts and city below to trim the list, and check your official sample ballot.');
}

async function main() {
  initToggles();
  const get = path => fetch(path, { cache: 'no-cache' }).then(r => {
    if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
    return r.json();
  });
  try {
    [BALLOT, GUIDES, PICKS, ZIPS, TOPICS, FUNDING, MONEY, STATE_MONEY, ANALYSIS, EXTERNAL] = await Promise.all([
      get(DATA_BASE + 'ballot.json'), get('./data/endorsements.json'), get('./data/picks.json'),
      COUNTY === 'sf' ? get('./data/zip_districts.json') : null, get('./data/topics.json'),
      get('./data/funding.json').catch(() => null), get('./data/money.json').catch(() => null),
      get('./data/state_money.json').catch(() => null), get('./data/analysis.json').catch(() => null),
      get('./data/external_money.json').catch(() => null)]);
  } catch (err) {
    console.error('[voter-guide] failed to load data', err);
    document.getElementById('ballot').replaceChildren(
      el('p', { class: 'vg-empty' }, 'Could not load the ballot data. Please try again shortly.'));
    return;
  }
  BALLOT_POSITIONS = GUIDES.positions || {};
  // Only groups whose recommendations cover this county (statewide groups, plus SF-only ones on the SF guide).
  GUIDES = { ...GUIDES, guides: GUIDES.guides.filter(g => (g.covers || ['sf']).includes(COUNTY)) };
  renderCountyChrome();
  for (const s of BALLOT.sections) for (const c of s.contests) CONTEST_INDEX[c.id] = { contest: c, section: s };
  validate();

  document.getElementById('election-date').textContent = formatDate(BALLOT.election.date);
  const official = document.getElementById('official-sources');
  for (const s of BALLOT.election.official_sources || []) {
    official.append(el('li', {}, el('a', { href: s.url, target: '_blank', rel: 'noopener' }, s.label)));
  }
  document.getElementById('fineprint').textContent = PREVIEW
    ? `Contest lists come from ${BALLOT.election.jurisdiction}'s official candidate and measure lists. ` +
      `Statewide offices, propositions, the Regional Transit Measure and judicial retention are shared with the full ` +
      `San Francisco guide. Local candidate order, district boundaries and measure details are not verified yet. ` +
      `Your sample ballot is the authority. Data built ${formatDate(BALLOT.built)}.`
    : `Ballot order follows the official Ballot Worksheet in the Voter Information Pamphlet. ` +
    `Candidate order is computed from the Secretary of State's randomized alphabet ` +
    `(${BALLOT.randomized_alphabet.letters.split('').join(' ')}) and may differ from your printed ballot. ` +
    `Your sample ballot is the authority. Data built ${formatDate(BALLOT.built)}.`;

  renderGroups();
  renderTopicBar();
  if (COUNTY === 'sf') initZip();
  else { document.getElementById('zip-form').hidden = true; state.zip = null; }
  if (state.zip) applyZip(state.zip);      // re-narrow pickers; keeps choices that still fit
  else { renderDistricts(); renderBallot(); renderProgress(); }
  if (location.hash) {
    // Deep link to a contest: open its section first.
    const hit = CONTEST_INDEX[location.hash.slice(1)];
    if (hit) setCollapsed(hit.section.id, false);
    document.getElementById(location.hash.slice(1))?.scrollIntoView();
  }
}

main();
