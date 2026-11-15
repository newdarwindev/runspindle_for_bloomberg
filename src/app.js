const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const assetHref = name => `assets/${encodeURIComponent(name)}`;
const idLabel = id => String(id).padStart(2, '0');
let cases = [];
let filter = 'all';

function sourceLinks(record) {
  const urls = [record.terminal_and_method_source_urls, record.software_source_urls].filter(Boolean).flatMap(s => s.split('|').map(x => x.trim()).filter(Boolean));
  return [...new Set(urls)].map((url, i) => {
    try { const parsed = new URL(url); if (!['http:', 'https:'].includes(parsed.protocol)) return ''; return `<a href="${esc(parsed.href)}" target="_blank" rel="noopener noreferrer">Source ${i + 1} ↗</a>`; } catch { return ''; }
  }).join('');
}

function renderWorkflows() {
  const query = document.querySelector('#search').value.trim().toLowerCase();
  const matches = cases.filter(c => (filter === 'all' || (filter === 'business' ? c.slice === '1' : c.slice !== '1')) && (!query || [c.example,c.business_payoff,c.step_1_terminal_check,c.step_2_action_or_pause,c.step_3_verification].join(' ').toLowerCase().includes(query)));
  document.querySelector('#result-count').textContent = `${matches.length} of 40 workflows shown · priority order`;
  document.querySelector('#empty').hidden = matches.length > 0;
  document.querySelector('#workflow-list').innerHTML = matches.map(c => `<article class="workflow-card" id="case-${esc(c.example_id)}"><div class="card-top"><span>Rank ${idLabel(c.rank)} / Case ${idLabel(c.example_id)}</span><span>${c.slice === '1' ? 'Business workflow' : 'Terminal-only paper'}</span></div><h3>${esc(c.example)}</h3><p class="summary">${esc(c.step_1_terminal_check)}</p><details><summary>Inspect workflow and sources</summary><div class="detail-body"><h4>Terminal check</h4><p>${esc(c.step_1_terminal_check)}</p><h4>Action or pause</h4><p>${esc(c.step_2_action_or_pause)}</p><h4>Verification</h4><p>${esc(c.step_3_verification)}</p><h4>Supplied payoff / outcome</h4><p>${esc(c.business_payoff)}</p><h4>Ranking rationale</h4><p>${esc(c.rationale)}</p><h4>Assumptions</h4><p>${esc(c.assumptions)}</p><div class="source-pills">${sourceLinks(c)}<a href="${assetHref('runspindle_bloomberg_workflows.csv')}">Full CSV ↗</a></div></div></details></article>`).join('');
}

function renderAssets(records) {
  const byName = Object.fromEntries(records.map(r => [r.name, r]));
  document.querySelector('#asset-list').innerHTML = records.map((r, i) => `<article class="asset-card" id="asset-${i}"><header><span>${esc(r.kind)}</span><small>${(r.bytes / 1048576).toFixed(1)} MB</small></header><h3><a href="${esc(r.url)}">${esc(r.name)} ↗</a></h3><p>${esc(r.description)}</p><div class="related">Related: ${r.related.map(name => { const index = records.indexOf(byName[name]); return `<a href="#asset-${index}">${esc(name)}</a>`; }).join('')}</div></article>`).join('');
}

function renderGallery(all = false) {
  const count = all ? 37 : 6;
  document.querySelector('#gallery-strip').innerHTML = Array.from({length: count}, (_, n) => { const i = n + 1; return `<a class="gallery-item" href="assets/Runspindle_Revised_Gallery.pdf#page=${i}"><img src="gallery/${idLabel(i)}.webp" alt="Runspindle conceptual gallery page ${i}" loading="lazy"><div><span>PAGE ${idLabel(i)} · ${i <= 29 ? 'ORIGINAL SEQUENCE' : 'ADDED CASE'}</span><b>↗</b></div></a>`; }).join('');
  const button = document.querySelector('#show-gallery');
  button.textContent = all ? 'Show fewer pages ↑' : 'Show all 37 pages ↓';
  button.setAttribute('aria-expanded', all ? 'true' : 'false');
}

async function init() {
  try {
    const [workflowResponse, assetResponse] = await Promise.all([fetch('workflows.json'), fetch('asset-catalog.json')]);
    if (!workflowResponse.ok || !assetResponse.ok) throw new Error('Source data unavailable');
    cases = await workflowResponse.json();
    renderWorkflows();
    renderAssets(await assetResponse.json());
  } catch (error) {
    document.querySelector('#workflow-list').innerHTML = '<p>Catalog data could not be loaded. <a href="assets/runspindle_bloomberg_workflows.csv">Open the source CSV</a>.</p>';
    document.querySelector('#asset-list').innerHTML = '<p>Asset catalog could not be loaded. <a href="assets/Runspindle_Gallery_Index.html">Open the gallery index</a>.</p>';
  }
  renderGallery();
  document.querySelector('#search').addEventListener('input', renderWorkflows);
  document.querySelectorAll('[data-filter]').forEach(button => button.addEventListener('click', () => { filter = button.dataset.filter; document.querySelectorAll('[data-filter]').forEach(b => { b.classList.toggle('active', b === button); b.setAttribute('aria-pressed', b === button ? 'true' : 'false'); }); renderWorkflows(); }));
  let expanded = false;
  document.querySelector('#show-gallery').addEventListener('click', () => { expanded = !expanded; renderGallery(expanded); });
}
init();
