// SF Voter Guide renderer. All content lives in data/ballot.json (schema:
// docs/data-model.md); this file only turns it into DOM. Text is always set
// via textContent, never innerHTML.

const LEVELS = ['federal', 'state', 'county', 'city', 'district'];
const LEVEL_LABEL = {
  federal: 'Federal', state: 'State', county: 'County',
  city: 'City & County', district: 'District',
};
const PICKS_KEY = 'sf-voter-guide.show-picks';

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') node.className = v;
    else node.setAttribute(k, v);
  }
  for (const c of children) {
    if (c == null) continue;
    node.append(typeof c === 'string' ? document.createTextNode(c) : c);
  }
  return node;
}

function formatDate(iso) {
  // Parse as a local calendar date; `new Date('2026-11-03')` would be UTC
  // midnight and render as Nov 2 in Pacific time.
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, m - 1, d).toLocaleDateString('en-US',
    { year: 'numeric', month: 'long', day: 'numeric' });
}

function sourceRef(contest, id) {
  if (!id) return null;
  const idx = (contest.sources || []).findIndex(s => s.id === id);
  if (idx < 0) {
    console.warn(`[voter-guide] ${contest.id}: unresolved source "${id}"`);
    return el('sup', { class: 'vg-src' }, '[?]');
  }
  return el('sup', { class: 'vg-src' },
    el('a', { href: `#${contest.id}-src-${id}` }, `[${idx + 1}]`));
}

function renderContest(c) {
  const card = el('article', { class: 'vg-contest', id: c.id });
  card.append(el('h3', {}, c.title));
  if (c.subtitle || c.district) {
    card.append(el('p', { class: 'vg-sub' },
      [c.subtitle, c.district].filter(Boolean).join(' · ')));
  }
  if (c.summary) card.append(el('p', {}, c.summary));

  if (c.kind === 'measure' && (c.yes_means || c.no_means)) {
    card.append(el('div', { class: 'vg-meaning' },
      el('div', {}, el('strong', {}, 'A YES vote means: '), c.yes_means || '—'),
      el('div', {}, el('strong', {}, 'A NO vote means: '), c.no_means || '—')));
    if (c.threshold) card.append(el('p', { class: 'vg-sub' }, `Passes with: ${c.threshold}`));
  }

  if (c.kind === 'office' && c.candidates?.length) {
    card.append(el('h4', {}, 'Candidates'));
    const ul = el('ul', { class: 'vg-cands' });
    for (const cand of c.candidates) {
      const li = el('li', {}, el('strong', {}, cand.name));
      if (cand.party) li.append(` (${cand.party})`);
      if (cand.incumbent) li.append(' · incumbent');
      if (cand.ballot_designation) {
        li.append(el('div', { class: 'vg-desig' }, cand.ballot_designation));
      }
      for (const link of cand.links || []) {
        li.append(' ', el('a', { href: link.url, rel: 'noopener', target: '_blank' }, link.label));
      }
      ul.append(li);
    }
    card.append(ul);
  }

  const args = c.arguments || {};
  if (args.for?.length || args.against?.length) {
    const col = (label, items = []) => el('div', {},
      el('h4', {}, label),
      el('ul', {}, ...items.map(a => el('li', {}, a.text, sourceRef(c, a.source)))));
    const [forLabel, againstLabel] = c.kind === 'measure'
      ? ['Case for', 'Case against'] : ['Supporters say', 'Critics say'];
    card.append(el('div', { class: 'vg-args' },
      col(forLabel, args.for), col(againstLabel, args.against)));
  }

  if (c.money?.length) {
    card.append(el('h4', {}, 'Money'));
    const table = el('table', { class: 'vg-money' });
    for (const m of c.money) {
      table.append(el('tr', {},
        el('td', {}, `${m.side === 'against' ? 'Against' : 'For'}: ${m.committee}`, sourceRef(c, m.source)),
        el('td', { class: 'num' }, `$${Number(m.amount).toLocaleString('en-US')}`),
        el('td', { class: 'num' }, m.as_of ? `as of ${formatDate(m.as_of)}` : '')));
    }
    card.append(table);
  }

  if (c.pick) {
    card.append(el('div', { class: 'vg-pick' },
      el('div', { class: 'vg-pick-label' }, 'Our pick (opinion)'),
      el('p', {}, el('strong', {}, c.pick.choice), c.pick.reasoning ? ` — ${c.pick.reasoning}` : '',
        ...(c.pick.sources || []).map(id => sourceRef(c, id)))));
  }

  if (c.sources?.length) {
    card.append(el('h4', {}, 'Sources'));
    card.append(el('ol', { class: 'vg-sources' }, ...c.sources.map(s =>
      el('li', { id: `${c.id}-src-${s.id}` },
        el('a', { href: s.url, rel: 'noopener', target: '_blank' }, s.label),
        s.accessed ? ` (accessed ${formatDate(s.accessed)})` : ''))));
  } else {
    console.warn(`[voter-guide] ${c.id}: no sources — this contest should not ship`);
  }
  return card;
}

function render(data) {
  const { election, contests = [] } = data;
  document.getElementById('election-date').textContent = formatDate(election.date);
  document.getElementById('updated').textContent =
    data.updated ? `Last reviewed ${formatDate(data.updated)}` : '';

  const official = document.getElementById('official-sources');
  for (const s of election.official_sources || []) {
    official.append(el('li', {}, el('a', { href: s.url, rel: 'noopener', target: '_blank' }, s.label)));
  }

  const root = document.getElementById('contests');
  const toc = document.getElementById('toc');
  root.replaceChildren();
  if (!contests.length) {
    root.append(el('p', { class: 'vg-empty' },
      'The guide is being written. Until it is ready, see the official sources below.'));
    return;
  }
  for (const level of LEVELS) {
    const group = contests.filter(c => c.level === level);
    if (!group.length) continue;
    root.append(el('h2', { class: 'vg-level-head' }, LEVEL_LABEL[level]));
    for (const c of group) {
      root.append(renderContest(c));
      toc.append(el('a', { href: `#${c.id}` }, c.title));
    }
  }
}

function initPicksToggle() {
  const box = document.getElementById('show-picks');
  try { box.checked = localStorage.getItem(PICKS_KEY) === '1'; } catch { /* storage blocked */ }
  const apply = () => document.body.classList.toggle('show-picks', box.checked);
  box.addEventListener('change', () => {
    apply();
    try { localStorage.setItem(PICKS_KEY, box.checked ? '1' : '0'); } catch { /* storage blocked */ }
  });
  apply();
}

initPicksToggle();
fetch('./data/ballot.json', { cache: 'no-cache' })
  .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
  .then(render)
  .catch(err => {
    console.error('[voter-guide] failed to load ballot data', err);
    document.getElementById('contests').replaceChildren(
      el('p', { class: 'vg-empty' }, 'Could not load the ballot data. Please try again shortly.'));
  });
