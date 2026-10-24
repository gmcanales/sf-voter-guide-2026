// SF Voter Guide renderer. Content lives in data/*.json (schema:
// docs/data-model.md); this file only turns it into DOM and keeps the reader's
// district choices + marked ovals in localStorage. Text is always set via
// textContent, never innerHTML.

const STORE_KEY = 'sf-voter-guide.2026-11';
const RCV_MAX_RANKS = 10;            // SF ballots allow up to 10 rankings
const RANK_LABEL = ['1st', '2nd', '3rd', '4th', '5th', '6th', '7th', '8th', '9th', '10th'];

const SOLE_SHARE = 0.995;            // a ZIP this much inside one district counts as "only that one"
const DIMS = ['cd', 'ad', 'sup', 'bart'];

const state = loadState();
let BALLOT, GUIDES, PICKS, ZIPS, TOPICS;

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
  for (const c of children.flat()) {
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
  const label = { cd: 'Congressional District', ad: 'Assembly District', sup: 'Supervisor District', bart: 'BART District' }[dim];
  return `${label} ${n} only`;
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
    who.map(g => el('span', { class: 'vg-chip', title: g.name }, g.short)));
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
        c.designation ? el('div', { class: 'vg-desig' }, c.designation) : null,
        c.note ? el('div', { class: 'vg-cand-note' }, c.note,
          c.note_source ? [' (', el('a', { href: c.note_source.url, target: '_blank', rel: 'noopener' }, 'source'), ')'] : null) : null,
        guideChipsForRow(contest, c.name)));
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
        c.designation ? el('div', { class: 'vg-desig' }, c.designation) : null,
        c.note ? el('div', { class: 'vg-cand-note' }, c.note) : null,
        guideChipsForRow(contest, c.name)),
      el('div', { class: 'vg-rcv-ovals' }, Array.from({ length: nRanks }, (_, r) =>
        oval(ranks[r] === c.name, `${RANK_LABEL[r]} choice: ${c.name}`, () => toggleRank(contest, c.name, r)))));
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
          // Topic tags describe what a YES vote does, so they live on the YES line only.
          v === 'yes' ? renderTopicTags(contest) : null,
          state.showPicks ? rowVerdicts(contest, v).map(p => badge(p.verdict)) : null),
        guideChipsForRow(contest, v)));
  }));
}

// ── guide footnote under each contest (muted) ─────────────────────────────
// The picks themselves show as chips on the ballot rows; this line only adds
// what a chip can't carry: explicit no-positions and qualifying notes.
function renderGuideLine(contest) {
  if (!state.showGuides) return null;
  const pos = BALLOT_POSITIONS[contest.id];
  if (!pos) return null;
  const parts = [];
  for (const g of GUIDES.guides) {
    if (!pos[g.id]) continue;
    const p = normPosition(pos[g.id]);
    if (p.kind !== 'none' && !p.note) continue;
    parts.push(el('li', {},
      el('a', { href: g.url, target: '_blank', rel: 'noopener' }, g.short), ': ',
      p.kind === 'none' ? p.value : p.note));
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

function renderDetails(contest) {
  const blocks = [];
  if (contest.kind === 'measure') {
    blocks.push(
      para('On the ballot', contest.question),
      para('Summary', contest.summary),
      para('The way it is now', contest.way_it_is_now),
      para('The proposal', contest.proposal),
      contest.yes_means || contest.no_means ? el('div', { class: 'vg-meaning' },
        el('div', {}, el('strong', {}, 'A YES vote means: '), contest.yes_means || '—'),
        el('div', {}, el('strong', {}, 'A NO vote means: '), contest.no_means || '—')) : null,
      para('Fiscal impact', contest.fiscal),
      contest.official_args ? el('div', { class: 'vg-args' },
        el('div', {}, el('h4', {}, 'Official argument for'), el('p', {}, contest.official_args.for || '—')),
        el('div', {}, el('h4', {}, 'Official argument against'), el('p', {}, contest.official_args.against || '—'))) : null,
      para('Listed supporters', contest.listed_supporters),
      para('Listed opponents', contest.listed_opponents),
      para('How it got on the ballot', contest.how_placed || contest.placed_by),
      topicTags(contest).length ? el('div', { class: 'vg-detail' }, el('h4', {}, 'Why these topic tags (our labels)'),
        el('ul', {}, topicTags(contest).map(t => el('li', {},
          el('strong', {}, topicLabel(t.topic) + (t.effect ? ` ${ARROW[t.effect]}` : '') + ': '), t.why)))) : null,
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
  const label = contest.kind === 'measure' ? 'What it does' : 'About this list';
  return el('details', { class: 'vg-details' }, el('summary', {}, label), body);
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
    renderDetails(contest));
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
  for (const dim of DIMS) out[dim] = z[dim] || [];
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
      : `${state.zip} isn't a San Francisco ZIP. This guide covers San Francisco County only. Other counties are coming.`;
    state.zip = null;
  } else {
    const opts = zipOptions();
    const unresolved = [];
    for (const dim of DIMS) {
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
        share != null && allowed.length > 1 ? `${n} (${Math.max(1, Math.round(share * 100))}% of ZIP area)` : String(n))));
    box.append(el('label', { class: 'vg-district' },
      el('span', { class: 'vg-district-label' }, spec.label), sel,
      spec.note ? el('span', { class: 'vg-district-note' }, spec.note) : null));
    if (state.districts[dim] != null) summary.push(`${{ cd: 'CD', ad: 'AD', sup: 'Sup.', bart: 'BART' }[dim]} ${state.districts[dim]}`);
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

const ARROW = { up: '↑', down: '↓' };

function renderTopicTags(contest) {
  const tags = topicTags(contest);
  if (!tags.length) return null;
  return el('ul', { class: 'vg-topic-tags', 'aria-label': 'Topics' }, tags.map(t =>
    el('li', { class: 'vg-topic-tag' + (state.topics.includes(t.topic) ? ' is-active' : ''), title: t.why },
      topicLabel(t.topic), t.effect ? el('span', { class: 'vg-arrow' }, ` ${ARROW[t.effect]}`) : null)));
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

// ── "Other groups included" panel ─────────────────────────────────────────
function money(m) {
  if (m.text) return m.text;
  const n = m.amount;
  const amt = n >= 1e6 ? `$${(n / 1e6).toFixed(2)}M` : `$${Math.round(n / 1e3)}K`;
  return `${amt} · ${m.period}`;
}

function renderGroups() {
  const body = document.getElementById('groups-body');
  body.replaceChildren(
    el('p', { class: 'vg-setup-hint' },
      'These are the published guides we track. Their picks appear as small tags on each ballot line. Money and membership figures are rough public-record numbers.'),
    el('div', { class: 'vg-group-cards' }, GUIDES.guides.map(g => el('article', { class: 'vg-group-card' },
      el('header', {},
        el('a', { href: g.url, target: '_blank', rel: 'noopener', class: 'vg-group-name' }, g.name),
        el('span', { class: 'vg-group-kind' }, g.kind)),
      g.self_description
        ? el('blockquote', { class: 'vg-self' },
            el('span', { class: 'vg-self-label' }, 'In their words'),
            el('p', {}, `“${g.self_description.text}”`),
            el('a', { href: g.self_description.source, target: '_blank', rel: 'noopener', class: 'vg-src-link' }, 'source'))
        : g.self_description_missing ? el('p', { class: 'vg-fineprint' }, g.self_description_missing) : null,
      g.about ? el('p', { class: 'vg-group-about' }, g.about) : null,
      el('dl', {},
        el('dt', {}, 'Money'),
        el('dd', {}, el('ul', {}, (g.money || []).map(m => el('li', {},
          m.label ? el('span', { class: 'vg-money-label' }, `${m.label}: `) : null, money(m),
          m.note ? el('span', { class: 'vg-money-note' }, ` ${m.note}`) : null,
          m.source ? [' ', el('a', { href: m.source.url, target: '_blank', rel: 'noopener', class: 'vg-src-link' }, 'source')] : null)))),
        el('dt', {}, 'Members'),
        el('dd', {}, g.members?.text || 'Not published.',
          g.members?.source ? [' ', el('a', { href: g.members.source.url, target: '_blank', rel: 'noopener', class: 'vg-src-link' }, 'source')] : null)),
      el('p', { class: 'vg-fineprint' }, `Guide checked ${formatDate(g.accessed)}`)))),
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
    if (!hit) { console.warn(`[voter-guide] endorsements: unknown contest "${id}"`); continue; }
    const names = new Set((hit.contest.candidates || []).map(c => c.name));
    for (const [g, p] of Object.entries(byGuide)) {
      const n = normPosition(p);
      if (n.kind === 'picks') for (const v of n.value) if (!names.has(v)) console.warn(`[voter-guide] ${g} on ${id}: "${v}" is not on the ballot list`);
    }
  }
  for (const [id, list] of Object.entries(PICKS.picks || {})) {
    if (!CONTEST_INDEX[id]) console.warn(`[voter-guide] picks: unknown contest "${id}"`);
    for (const p of list) if (!p.reasoning) console.warn(`[voter-guide] picks: ${id} has no reasoning`);
  }
}

async function main() {
  initToggles();
  const get = path => fetch(path, { cache: 'no-cache' }).then(r => {
    if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
    return r.json();
  });
  try {
    [BALLOT, GUIDES, PICKS, ZIPS, TOPICS] = await Promise.all([
      get('./data/ballot.json'), get('./data/endorsements.json'), get('./data/picks.json'),
      get('./data/zip_districts.json'), get('./data/topics.json')]);
  } catch (err) {
    console.error('[voter-guide] failed to load data', err);
    document.getElementById('ballot').replaceChildren(
      el('p', { class: 'vg-empty' }, 'Could not load the ballot data. Please try again shortly.'));
    return;
  }
  BALLOT_POSITIONS = GUIDES.positions || {};
  for (const s of BALLOT.sections) for (const c of s.contests) CONTEST_INDEX[c.id] = { contest: c, section: s };
  validate();

  document.getElementById('election-date').textContent = formatDate(BALLOT.election.date);
  const official = document.getElementById('official-sources');
  for (const s of BALLOT.election.official_sources || []) {
    official.append(el('li', {}, el('a', { href: s.url, target: '_blank', rel: 'noopener' }, s.label)));
  }
  document.getElementById('fineprint').textContent =
    `Ballot order follows the official Ballot Worksheet in the Voter Information Pamphlet. ` +
    `Candidate order is computed from the Secretary of State's randomized alphabet ` +
    `(${BALLOT.randomized_alphabet.letters.split('').join(' ')}) and may differ from your printed ballot. ` +
    `Your sample ballot is the authority. Data built ${formatDate(BALLOT.built)}.`;

  renderGroups();
  renderTopicBar();
  initZip();
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
