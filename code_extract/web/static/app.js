/* code-extract v0.3 web UI — vanilla JS */

const app = (() => {
  let currentScan = null;
  let allItems = [];
  let filteredItems = [];
  let selectedIds = new Set();
  let activeTab = 'scan';
  const tabLoaded = {};    // track which tabs have loaded data
  let catalogData = null;
  let tourData = null;
  let tourStep = 0;
  let docsWs = null;

  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  // --- Init mermaid ---
  if (window.mermaid) {
    mermaid.initialize({ startOnLoad: false, theme: 'dark', securityLevel: 'loose' });
  }

  // --- Badge colors by type ---
  const TYPE_COLORS = {
    function: 'bg-green-900/60 text-green-300',
    class: 'bg-yellow-900/60 text-yellow-300',
    component: 'bg-purple-900/60 text-purple-300',
    widget: 'bg-purple-900/60 text-purple-300',
    method: 'bg-blue-900/60 text-blue-300',
    mixin: 'bg-cyan-900/60 text-cyan-300',
    struct: 'bg-amber-900/60 text-amber-300',
    trait: 'bg-rose-900/60 text-rose-300',
    interface: 'bg-teal-900/60 text-teal-300',
    enum: 'bg-lime-900/60 text-lime-300',
    module: 'bg-sky-900/60 text-sky-300',
    table: 'bg-orange-900/60 text-orange-300',
    view: 'bg-teal-900/60 text-teal-300',
    sql_function: 'bg-pink-900/60 text-pink-300',
    trigger: 'bg-red-900/60 text-red-300',
    index: 'bg-gray-700/60 text-gray-300',
    migration: 'bg-violet-900/60 text-violet-300',
    policy: 'bg-fuchsia-900/60 text-fuchsia-300',
    provider: 'bg-indigo-900/60 text-indigo-300',
  };

  // ═══════════════════════════════════════════════
  // TAB SWITCHING
  // ═══════════════════════════════════════════════

  function switchTab(tabName) {
    activeTab = tabName;

    // Update tab buttons
    $$('.tab-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.tab === tabName);
    });

    // Update tab panels
    $$('.tab-panel').forEach(panel => {
      const isTarget = panel.id === `tab-${tabName}`;
      panel.classList.toggle('active', isTarget);
      panel.classList.toggle('hidden', !isTarget);
    });

    // Show/hide sidebar filters only for scan tab
    const filters = $('#sidebar-filters');
    if (filters) {
      filters.style.display = tabName === 'scan' ? '' : 'none';
    }

    // Lazy-load tab data if scan exists
    if (currentScan && !tabLoaded[tabName]) {
      loadTabData(tabName);
    }
  }

  function loadTabData(tabName) {
    const loaders = {
      catalog: loadCatalog,
      architecture: loadArchitecture,
      health: loadHealth,
      docs: loadDocs,
      deadcode: loadDeadCode,
      tour: loadTour,
    };
    const loader = loaders[tabName];
    if (loader) loader();
  }

  // ═══════════════════════════════════════════════
  // AUTOCOMPLETE
  // ═══════════════════════════════════════════════

  const pathInput = $('#path-input');
  const dropdown = $('#autocomplete-dropdown');
  let acTimeout = null;

  pathInput.addEventListener('input', () => {
    clearTimeout(acTimeout);
    acTimeout = setTimeout(async () => {
      const q = pathInput.value;
      if (q.length < 2) { dropdown.classList.add('hidden'); return; }
      try {
        const res = await fetch(`/api/autocomplete?q=${encodeURIComponent(q)}`);
        const data = await res.json();
        if (data.suggestions.length === 0) { dropdown.classList.add('hidden'); return; }
        dropdown.innerHTML = data.suggestions.map(s =>
          `<div class="ac-item px-3 py-1.5 hover:bg-surface-200 cursor-pointer text-xs truncate" data-path="${s}">${s}</div>`
        ).join('');
        dropdown.classList.remove('hidden');
        dropdown.querySelectorAll('.ac-item').forEach(el => {
          el.addEventListener('click', () => {
            pathInput.value = el.dataset.path;
            dropdown.classList.add('hidden');
          });
        });
      } catch { dropdown.classList.add('hidden'); }
    }, 200);
  });

  pathInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { dropdown.classList.add('hidden'); scan(); }
    if (e.key === 'Escape') dropdown.classList.add('hidden');
  });

  document.addEventListener('click', (e) => {
    if (!dropdown.contains(e.target) && e.target !== pathInput) dropdown.classList.add('hidden');
  });

  // ═══════════════════════════════════════════════
  // SCAN
  // ═══════════════════════════════════════════════

  async function waitForExtraction(scanId, maxWait = 60000) {
    const start = Date.now();
    while (Date.now() - start < maxWait) {
      try {
        const res = await fetch(`/api/scan/${scanId}/status`);
        if (res.ok) {
          const info = await res.json();
          if (info.status === 'ready') return;
        }
      } catch (_) { /* ignore network blips */ }
      await new Promise(r => setTimeout(r, 500));
    }
  }

  async function scan() {
    const path = pathInput.value.trim();
    if (!path) return;

    setStatus('Scanning...');
    $('#scan-btn').disabled = true;

    // Reset all tab loaded states
    Object.keys(tabLoaded).forEach(k => delete tabLoaded[k]);
    catalogData = null;
    tourData = null;

    try {
      const res = await fetch('/api/scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Scan failed');
      }
      const data = await res.json();
      currentScan = data;
      allItems = data.items;
      selectedIds.clear();

      saveRecentScan(path, data.scan_id, data.count);
      populateFilters();
      applyFilters();
      setStatus(`Found ${data.count} items — extracting blocks...`);
      $('#scan-dir').textContent = data.source_dir;

      // Wait for background extraction to finish
      await waitForExtraction(data.scan_id);
      setStatus(`Found ${data.count} items — ready`);

      // If on a non-scan tab, trigger its data load
      if (activeTab !== 'scan') {
        loadTabData(activeTab);
      }
    } catch (err) {
      setStatus(`Error: ${err.message}`);
    } finally {
      $('#scan-btn').disabled = false;
    }
  }

  // ═══════════════════════════════════════════════
  // FILTERS
  // ═══════════════════════════════════════════════

  function populateFilters() {
    const langs = new Set(allItems.map(i => i.language));
    const types = new Set(allItems.map(i => i.type));
    const langSel = $('#filter-language');
    const typeSel = $('#filter-type');
    langSel.innerHTML = '<option value="">All Languages</option>' +
      [...langs].sort().map(l => `<option value="${l}">${l}</option>`).join('');
    typeSel.innerHTML = '<option value="">All Types</option>' +
      [...types].sort().map(t => `<option value="${t}">${t}</option>`).join('');
  }

  function applyFilters() {
    const lang = $('#filter-language').value;
    const type = $('#filter-type').value;
    const search = $('#filter-search').value.toLowerCase();

    filteredItems = allItems.filter(item => {
      if (lang && item.language !== lang) return false;
      if (type && item.type !== type) return false;
      if (search && !item.name.toLowerCase().includes(search) && !item.qualified_name.toLowerCase().includes(search)) return false;
      return true;
    });

    renderResults();
  }

  // ═══════════════════════════════════════════════
  // RENDER SCAN RESULTS
  // ═══════════════════════════════════════════════

  function renderResults() {
    const tbody = $('#results-body');
    const table = $('#results-table');
    const empty = $('#empty-state');

    if (filteredItems.length === 0 && allItems.length === 0) {
      table.classList.add('hidden');
      empty.classList.remove('hidden');
      return;
    }

    empty.classList.add('hidden');
    table.classList.remove('hidden');

    const byFile = {};
    filteredItems.forEach(item => {
      (byFile[item.file] = byFile[item.file] || []).push(item);
    });

    let html = '';
    for (const [file, items] of Object.entries(byFile)) {
      const shortFile = file.replace(currentScan?.source_dir || '', '').replace(/^\//, '');
      html += `<tr class="bg-surface-100"><td colspan="5" class="px-4 py-1.5 text-xs text-gray-400 font-mono">${shortFile}</td></tr>`;

      for (const item of items) {
        const checked = selectedIds.has(item.id) ? 'checked' : '';
        const colors = TYPE_COLORS[item.type] || 'bg-gray-700 text-gray-300';
        html += `
          <tr class="result-row hover:bg-surface-200 cursor-pointer border-b border-gray-800/50" data-id="${item.id}">
            <td class="pl-4 pr-2 py-1.5 w-8">
              <input type="checkbox" class="item-check rounded bg-surface-200 border-gray-600" data-id="${item.id}" ${checked}>
            </td>
            <td class="px-2 py-1.5 w-24">
              <span class="text-xs px-1.5 py-0.5 rounded ${colors}">${item.type}</span>
            </td>
            <td class="px-2 py-1.5 font-medium text-sm">${item.qualified_name}</td>
            <td class="px-2 py-1.5 text-xs text-gray-500">${item.language}</td>
            <td class="pr-4 py-1.5 text-xs text-gray-600 text-right">L${item.line}${item.end_line ? '-' + item.end_line : ''}</td>
          </tr>`;
      }
    }

    tbody.innerHTML = html;
    $('#item-count').textContent = `${filteredItems.length} items`;

    tbody.querySelectorAll('.item-check').forEach(cb => {
      cb.addEventListener('change', (e) => {
        e.stopPropagation();
        if (cb.checked) selectedIds.add(cb.dataset.id);
        else selectedIds.delete(cb.dataset.id);
        updateSelection();
      });
    });

    tbody.querySelectorAll('.result-row').forEach(row => {
      row.addEventListener('click', (e) => {
        if (e.target.type === 'checkbox') return;
        showPreview(row.dataset.id);
      });
    });
  }

  // ═══════════════════════════════════════════════
  // SELECTION
  // ═══════════════════════════════════════════════

  function toggleAll(checked) {
    if (checked) filteredItems.forEach(i => selectedIds.add(i.id));
    else selectedIds.clear();
    renderResults();
    updateSelection();
  }

  function updateSelection() {
    const n = selectedIds.size;
    $('#selected-count').textContent = `${n} selected`;
    $('#extract-btn').disabled = n === 0;
    $('#smart-extract-btn').disabled = n === 0;
    $('#package-btn').disabled = n === 0;
  }

  // ═══════════════════════════════════════════════
  // PREVIEW
  // ═══════════════════════════════════════════════

  async function showPreview(itemId) {
    try {
      const res = await fetch(`/api/preview/${encodeURIComponent(itemId)}`);
      if (!res.ok) throw new Error('Preview failed');
      const data = await res.json();

      $('#preview-name').textContent = data.name;
      const badge = $('#preview-badge');
      const colors = TYPE_COLORS[data.type] || 'bg-gray-700 text-gray-300';
      badge.className = `ml-2 text-xs px-1.5 py-0.5 rounded ${colors}`;
      badge.textContent = data.type;

      const codeEl = $('#preview-code');
      codeEl.textContent = data.code;
      codeEl.className = `text-xs language-${data.language}`;
      hljs.highlightElement(codeEl);

      const panel = $('#preview-panel');
      panel.classList.remove('hidden');
      panel.classList.add('flex');
    } catch (err) {
      setStatus(`Preview error: ${err.message}`);
    }
  }

  function closePreview() {
    const panel = $('#preview-panel');
    panel.classList.add('hidden');
    panel.classList.remove('flex');
  }

  // ═══════════════════════════════════════════════
  // EXTRACT (original)
  // ═══════════════════════════════════════════════

  async function extract() {
    if (selectedIds.size === 0 || !currentScan) return;
    setStatus('Extracting...');
    showProgress();

    try {
      const res = await fetch('/api/extract', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scan_id: currentScan.scan_id,
          item_ids: [...selectedIds],
        }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || 'Extract failed');
      const data = await res.json();
      setStatus(`Extracted ${data.files_created} files`);
      showDownload(data.download_url);
    } catch (err) {
      setStatus(`Error: ${err.message}`);
    }
    hideProgress();
  }

  // ═══════════════════════════════════════════════
  // SMART EXTRACT (with dependencies)
  // ═══════════════════════════════════════════════

  async function smartExtract() {
    if (selectedIds.size === 0 || !currentScan) return;
    setStatus('Extracting with dependencies...');
    showProgress();

    try {
      const res = await fetch('/api/analysis/smart-extract', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scan_id: currentScan.scan_id,
          item_ids: [...selectedIds],
        }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || 'Smart extract failed');
      const data = await res.json();
      setStatus(`Extracted ${data.files_created} files (${data.total_items} items with deps)`);
      showDownload(data.download_url);
    } catch (err) {
      setStatus(`Error: ${err.message}`);
    }
    hideProgress();
  }

  // ═══════════════════════════════════════════════
  // CREATE PACKAGE
  // ═══════════════════════════════════════════════

  async function createPackage() {
    if (selectedIds.size === 0 || !currentScan) return;
    setStatus('Creating package...');
    showProgress();

    try {
      const res = await fetch('/api/tools/package', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scan_id: currentScan.scan_id,
          item_ids: [...selectedIds],
          package_name: 'extracted-package',
        }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || 'Package creation failed');
      const data = await res.json();
      setStatus(`Package created: ${data.files_created} files`);
      showDownload(data.download_url);
    } catch (err) {
      setStatus(`Error: ${err.message}`);
    }
    hideProgress();
  }

  // ═══════════════════════════════════════════════
  // TAB: CATALOG
  // ═══════════════════════════════════════════════

  async function loadCatalog() {
    if (!currentScan) return;
    setStatus('Building catalog...');

    try {
      const res = await fetch('/api/catalog/build', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scan_id: currentScan.scan_id }),
      });
      if (!res.ok) throw new Error('Failed to build catalog');
      catalogData = await res.json();
      tabLoaded.catalog = true;
      renderCatalog(catalogData.items);
      setStatus(`Catalog: ${catalogData.items.length} components`);
    } catch (err) {
      setStatus(`Catalog error: ${err.message}`);
    }
  }

  function renderCatalog(items) {
    $('#catalog-empty').classList.add('hidden');
    $('#catalog-content').classList.remove('hidden');

    // Populate language filter
    const langs = new Set(items.map(i => i.language));
    const sel = $('#catalog-lang-filter');
    sel.innerHTML = '<option value="">All Languages</option>' +
      [...langs].sort().map(l => `<option value="${l}">${l}</option>`).join('');

    renderCatalogCards(items);
  }

  function renderCatalogCards(items) {
    const grid = $('#catalog-grid');
    grid.innerHTML = items.map((item, idx) => {
      const colors = TYPE_COLORS[item.type] || 'bg-gray-700 text-gray-300';
      const params = (item.parameters || []).map(p =>
        `<dt>${esc(p.name)}${p.type_annotation ? ': ' + esc(p.type_annotation) : ''}${p.default_value ? ' = ' + esc(p.default_value) : ''}</dt>`
      ).join('');

      return `<div class="catalog-card">
        <div class="card-header">
          <span class="card-name">${esc(item.name)}</span>
          <div class="card-badges">
            <span class="card-badge ${colors}">${item.type}</span>
            <span class="card-badge bg-gray-700/60 text-gray-300">${item.language}</span>
          </div>
        </div>
        ${item.line_count ? `<div class="text-xs text-gray-600">${item.line_count} lines</div>` : ''}
        ${params ? `<dl class="card-params">${params}</dl>` : ''}
        <div class="card-code-toggle" onclick="this.nextElementSibling.classList.toggle('hidden')">Show code</div>
        <div class="card-code hidden"><pre><code class="text-xs">${esc(item.code || '')}</code></pre></div>
      </div>`;
    }).join('');
  }

  function filterCatalog() {
    if (!catalogData) return;
    const search = ($('#catalog-search').value || '').toLowerCase();
    const lang = $('#catalog-lang-filter').value;
    const filtered = catalogData.items.filter(i => {
      if (lang && i.language !== lang) return false;
      if (search && !i.name.toLowerCase().includes(search)) return false;
      return true;
    });
    renderCatalogCards(filtered);
  }

  function exportCatalogHTML() {
    if (!catalogData) return;
    const blob = new Blob([JSON.stringify(catalogData, null, 2)], { type: 'application/json' });
    downloadBlob(blob, 'catalog.json');
  }

  // ═══════════════════════════════════════════════
  // TAB: ARCHITECTURE
  // ═══════════════════════════════════════════════

  async function loadArchitecture() {
    if (!currentScan) return;
    setStatus('Analyzing architecture...');

    try {
      const res = await fetch('/api/analysis/architecture', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scan_id: currentScan.scan_id }),
      });
      if (!res.ok) throw new Error('Failed to analyze architecture');
      const data = await res.json();
      tabLoaded.architecture = true;
      renderArchitecture(data);
      setStatus('Architecture loaded');
    } catch (err) {
      setStatus(`Architecture error: ${err.message}`);
    }
  }

  function renderArchitecture(data) {
    $('#arch-empty').classList.add('hidden');
    $('#arch-content').classList.remove('hidden');

    // Render mermaid diagram
    const container = $('#arch-diagram');
    container.innerHTML = `<pre class="mermaid">${data.mermaid}</pre>`;
    if (window.mermaid) {
      mermaid.run({ nodes: container.querySelectorAll('.mermaid') });
    }

    // Render module list
    const modList = $('#arch-modules');
    modList.innerHTML = (data.modules || []).map(m => `
      <div class="module-item" onclick="this.classList.toggle('expanded')">
        <div class="module-item-header">
          <span>${esc(m.directory)}</span>
          <span class="module-item-count">${m.item_count} items</span>
        </div>
        <div class="module-item-body">
          ${(m.items || []).map(i => `<div class="py-0.5">${esc(i.name)} <span class="text-gray-600">(${i.type})</span></div>`).join('')}
        </div>
      </div>
    `).join('');
  }

  function exportArchSVG() {
    const svg = $('#arch-diagram svg');
    if (!svg) return;
    const blob = new Blob([svg.outerHTML], { type: 'image/svg+xml' });
    downloadBlob(blob, 'architecture.svg');
  }

  // ═══════════════════════════════════════════════
  // TAB: HEALTH
  // ═══════════════════════════════════════════════

  async function loadHealth() {
    if (!currentScan) return;
    setStatus('Analyzing health...');

    try {
      const res = await fetch('/api/analysis/health', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scan_id: currentScan.scan_id }),
      });
      if (!res.ok) throw new Error('Failed to analyze health');
      const data = await res.json();
      tabLoaded.health = true;
      renderHealth(data);
      setStatus('Health analysis loaded');
    } catch (err) {
      setStatus(`Health error: ${err.message}`);
    }
  }

  function renderHealth(data) {
    $('#health-empty').classList.add('hidden');
    $('#health-content').classList.remove('hidden');

    // Overall score
    const score = data.score || 0;
    const cls = score >= 70 ? 'health-green' : score >= 40 ? 'health-yellow' : 'health-red';
    $('#health-score').innerHTML = `<span class="${cls}">Health: ${score}/100</span>`;

    // Long functions
    const longFns = $('#health-long-fns');
    longFns.innerHTML = (data.long_functions || []).map(f => {
      const len = f.line_count || 0;
      const c = len < 30 ? 'health-green' : len < 60 ? 'health-yellow' : 'health-red';
      return `<div class="metric-card" onclick="app.showPreview('${esc(f.item_id || '')}')">
        <div class="metric-name">${esc(f.name)}</div>
        <div class="metric-value ${c}">${len} lines</div>
        <div class="text-xs text-gray-600 truncate">${esc(f.file || '')}</div>
      </div>`;
    }).join('') || '<div class="text-xs text-gray-600">No long functions found</div>';

    // Duplications
    const dups = $('#health-duplicates');
    dups.innerHTML = (data.duplications || []).map(d => {
      return `<div class="metric-card">
        <div class="metric-name">${esc(d.item_a)} &harr; ${esc(d.item_b)}</div>
        <div class="metric-value health-yellow">${Math.round(d.similarity * 100)}% similar</div>
      </div>`;
    }).join('') || '<div class="text-xs text-gray-600">No duplications found</div>';

    // Coupling
    const coupling = $('#health-coupling');
    coupling.innerHTML = (data.coupling || []).map(c => {
      return `<div class="metric-card" onclick="app.showPreview('${esc(c.item_id || '')}')">
        <div class="metric-name">${esc(c.name)}</div>
        <div class="metric-value">${c.score} connections</div>
      </div>`;
    }).join('') || '<div class="text-xs text-gray-600">No coupling data</div>';
  }

  // ═══════════════════════════════════════════════
  // TAB: DOCS
  // ═══════════════════════════════════════════════

  async function loadDocs() {
    if (!currentScan) return;
    setStatus('Generating docs...');

    try {
      const res = await fetch('/api/docs/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scan_id: currentScan.scan_id }),
      });
      if (!res.ok) throw new Error('Failed to generate docs');
      const data = await res.json();
      tabLoaded.docs = true;
      renderDocs(data);
      setStatus('Documentation generated');
    } catch (err) {
      setStatus(`Docs error: ${err.message}`);
    }
  }

  function renderDocs(data) {
    $('#docs-empty').classList.add('hidden');
    $('#docs-content').classList.remove('hidden');

    const body = $('#docs-body');
    body.innerHTML = (data.sections || []).map(s => {
      const members = (s.members || []).map(m => `<li>${esc(m)}</li>`).join('');
      return `<div class="docs-section">
        <h3>${esc(s.name)} <span class="text-xs text-gray-500">(${s.type})</span></h3>
        ${s.signature ? `<div class="docs-signature">${esc(s.signature)}</div>` : ''}
        ${s.description ? `<p class="text-xs text-gray-400 mb-2">${esc(s.description)}</p>` : ''}
        ${members ? `<ul class="docs-members">${members}</ul>` : ''}
      </div>`;
    }).join('');
  }

  function toggleDocsWatch(enabled) {
    if (enabled && currentScan) {
      const wsUrl = `ws://${location.host}/api/docs/ws/docs-watch`;
      docsWs = new WebSocket(wsUrl);
      docsWs.onopen = () => {
        docsWs.send(JSON.stringify({ scan_id: currentScan.scan_id }));
        $('#docs-live-indicator').classList.remove('hidden');
      };
      docsWs.onmessage = (e) => {
        const data = JSON.parse(e.data);
        if (data.sections) renderDocs(data);
      };
      docsWs.onclose = () => {
        $('#docs-live-indicator').classList.add('hidden');
      };
    } else if (docsWs) {
      docsWs.close();
      docsWs = null;
      $('#docs-live-indicator').classList.add('hidden');
    }
  }

  function exportDocsMarkdown() {
    if (!currentScan) return;
    window.open(`/api/docs/${currentScan.scan_id}/markdown`, '_blank');
  }

  // ═══════════════════════════════════════════════
  // TAB: COMPARE (DIFF)
  // ═══════════════════════════════════════════════

  async function runDiff() {
    const pathA = $('#diff-path-a').value.trim();
    const pathB = $('#diff-path-b').value.trim();
    if (!pathA || !pathB) return;

    setStatus('Comparing...');

    try {
      const res = await fetch('/api/diff', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path_a: pathA, path_b: pathB }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || 'Diff failed');
      const data = await res.json();
      renderDiff(data);
      setStatus('Comparison complete');
    } catch (err) {
      setStatus(`Diff error: ${err.message}`);
    }
  }

  function renderDiff(data) {
    const summaryEl = $('#diff-summary');
    summaryEl.classList.remove('hidden');
    summaryEl.innerHTML = `<div class="diff-summary">
      <span class="diff-stat diff-added">${data.added?.length || 0} added</span>
      <span class="diff-stat diff-removed">${data.removed?.length || 0} removed</span>
      <span class="diff-stat diff-modified">${data.modified?.length || 0} modified</span>
      <span class="diff-stat diff-unchanged">${data.unchanged || 0} unchanged</span>
    </div>`;

    const results = $('#diff-results');
    let html = '';

    (data.added || []).forEach(item => {
      html += `<div class="diff-item added">
        <span class="text-xs text-green-400">+ ADDED</span>
        <div class="text-sm font-medium">${esc(item.name)} <span class="text-xs text-gray-500">(${item.type})</span></div>
      </div>`;
    });

    (data.removed || []).forEach(item => {
      html += `<div class="diff-item removed">
        <span class="text-xs text-red-400">- REMOVED</span>
        <div class="text-sm font-medium">${esc(item.name)} <span class="text-xs text-gray-500">(${item.type})</span></div>
      </div>`;
    });

    (data.modified || []).forEach(item => {
      html += `<div class="diff-item modified">
        <span class="text-xs text-amber-400">~ MODIFIED</span>
        <div class="text-sm font-medium">${esc(item.name)} <span class="text-xs text-gray-500">(${item.type})</span></div>
        ${item.before && item.after ? `<div class="diff-side-by-side">
          <pre><code class="text-xs">${esc(item.before)}</code></pre>
          <pre><code class="text-xs">${esc(item.after)}</code></pre>
        </div>` : ''}
      </div>`;
    });

    results.innerHTML = html;
  }

  // ═══════════════════════════════════════════════
  // TAB: DEAD CODE
  // ═══════════════════════════════════════════════

  async function loadDeadCode() {
    if (!currentScan) return;
    setStatus('Detecting dead code...');

    try {
      const res = await fetch('/api/analysis/dead-code', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scan_id: currentScan.scan_id }),
      });
      if (!res.ok) throw new Error('Failed to detect dead code');
      const data = await res.json();
      tabLoaded.deadcode = true;
      renderDeadCode(data);
      setStatus(`Found ${data.items?.length || 0} potentially dead items`);
    } catch (err) {
      setStatus(`Dead code error: ${err.message}`);
    }
  }

  function renderDeadCode(data) {
    $('#deadcode-empty').classList.add('hidden');
    $('#deadcode-content').classList.remove('hidden');
    $('#deadcode-count').textContent = `${data.items?.length || 0} items`;

    const tbody = $('#deadcode-body');
    tbody.innerHTML = (data.items || []).map(item => {
      const confCls = item.confidence >= 0.8 ? 'health-red' : item.confidence >= 0.5 ? 'health-yellow' : 'health-green';
      const shortFile = (item.file || '').replace(currentScan?.source_dir || '', '').replace(/^\//, '');
      return `<tr class="result-row hover:bg-surface-200 cursor-pointer border-b border-gray-800/50" onclick="app.showPreview('${esc(item.item_id || '')}')">
        <td class="px-3 py-2 font-medium">${esc(item.name)}</td>
        <td class="px-3 py-2 text-xs">${item.type}</td>
        <td class="px-3 py-2 text-xs text-gray-500 truncate max-w-xs">${shortFile}</td>
        <td class="px-3 py-2 text-xs ${confCls}">${Math.round(item.confidence * 100)}%</td>
        <td class="px-3 py-2 text-xs text-gray-500">${esc(item.reason || '')}</td>
      </tr>`;
    }).join('');
  }

  // ═══════════════════════════════════════════════
  // TAB: TOUR
  // ═══════════════════════════════════════════════

  async function loadTour() {
    if (!currentScan) return;
    setStatus('Generating tour...');

    try {
      const res = await fetch('/api/tour/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scan_id: currentScan.scan_id }),
      });
      if (!res.ok) throw new Error('Failed to generate tour');
      tourData = await res.json();
      tourStep = 0;
      tabLoaded.tour = true;
      renderTour();
      setStatus(`Tour: ${tourData.steps?.length || 0} steps`);
    } catch (err) {
      setStatus(`Tour error: ${err.message}`);
    }
  }

  function renderTour() {
    if (!tourData || !tourData.steps?.length) return;

    $('#tour-empty').classList.add('hidden');
    $('#tour-content').classList.remove('hidden');

    // Step list
    const list = $('#tour-step-list');
    list.innerHTML = tourData.steps.map((s, i) => `
      <div class="tour-step-list-item ${i === tourStep ? 'active' : ''}" onclick="app.goToTourStep(${i})">
        ${i + 1}. ${esc(s.name)}
      </div>
    `).join('');

    // Step content
    renderTourStep();
  }

  function renderTourStep() {
    if (!tourData || !tourData.steps?.length) return;
    const step = tourData.steps[tourStep];
    const content = $('#tour-step-content');

    const deps = (step.dependencies || []).map(d =>
      `<span class="mr-2">${esc(d)}</span>`
    ).join('');

    content.innerHTML = `<div class="tour-step">
      <div class="flex items-center mb-2">
        <span class="tour-step-number">${tourStep + 1}</span>
        <span class="tour-step-title">${esc(step.name)}</span>
        <span class="ml-2 text-xs text-gray-500">${step.type || ''} &middot; ${step.language || ''}</span>
      </div>
      <div class="tour-step-desc">${esc(step.description || '')}</div>
      ${step.code ? `<div class="tour-step-code"><pre><code class="text-xs">${esc(step.code)}</code></pre></div>` : ''}
      ${deps ? `<div class="tour-step-deps">Dependencies: ${deps}</div>` : ''}
    </div>`;

    // Highlight code
    content.querySelectorAll('pre code').forEach(el => hljs.highlightElement(el));

    // Update nav buttons
    $('#tour-prev').disabled = tourStep === 0;
    $('#tour-next').disabled = tourStep >= tourData.steps.length - 1;

    // Update step list active state
    $$('.tour-step-list-item').forEach((el, i) => {
      el.classList.toggle('active', i === tourStep);
    });
  }

  function goToTourStep(i) {
    tourStep = i;
    renderTourStep();
  }

  function tourPrev() {
    if (tourStep > 0) { tourStep--; renderTourStep(); }
  }

  function tourNext() {
    if (tourData && tourStep < tourData.steps.length - 1) { tourStep++; renderTourStep(); }
  }

  function exportTourMarkdown() {
    if (!tourData) return;
    let md = `# Codebase Tour\n\n`;
    (tourData.steps || []).forEach((s, i) => {
      md += `## Step ${i + 1}: ${s.name}\n\n`;
      md += `${s.description || ''}\n\n`;
      if (s.code) md += '```\n' + s.code + '\n```\n\n';
    });
    const blob = new Blob([md], { type: 'text/markdown' });
    downloadBlob(blob, 'codebase-tour.md');
  }

  // ═══════════════════════════════════════════════
  // RECENT SCANS (localStorage)
  // ═══════════════════════════════════════════════

  function saveRecentScan(path, scanId, count) {
    let recent = JSON.parse(localStorage.getItem('ce_recent') || '[]');
    recent = recent.filter(r => r.path !== path);
    recent.unshift({ path, scanId, count, ts: Date.now() });
    if (recent.length > 10) recent = recent.slice(0, 10);
    localStorage.setItem('ce_recent', JSON.stringify(recent));
    renderRecentScans();
  }

  function renderRecentScans() {
    const recent = JSON.parse(localStorage.getItem('ce_recent') || '[]');
    const container = $('#recent-scans');
    container.innerHTML = recent.map(r => {
      const short = r.path.replace(/^\/Users\/\w+\//, '~/');
      return `<div class="recent-item px-2 py-1 rounded hover:bg-surface-200 cursor-pointer truncate text-gray-400" data-path="${r.path}">
        ${short} <span class="text-gray-600">(${r.count})</span>
      </div>`;
    }).join('');
    container.querySelectorAll('.recent-item').forEach(el => {
      el.addEventListener('click', () => {
        pathInput.value = el.dataset.path;
        scan();
      });
    });
  }

  // ═══════════════════════════════════════════════
  // UTILITY
  // ═══════════════════════════════════════════════

  function setStatus(text) {
    $('#status-text').textContent = text;
  }

  function esc(s) {
    if (!s) return '';
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function showProgress() {
    $('#progress-bar').classList.remove('hidden');
    $('#progress-fill').style.width = '30%';
    $('#progress-text').classList.remove('hidden');
    $('#progress-text').textContent = 'Processing...';
    $('#download-link').classList.add('hidden');
  }

  function hideProgress() {
    $('#progress-bar').classList.add('hidden');
    $('#progress-text').classList.add('hidden');
  }

  function showDownload(url) {
    const link = $('#download-link');
    link.href = url;
    link.classList.remove('hidden');
    $('#progress-fill').style.width = '100%';
  }

  function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  // ═══════════════════════════════════════════════
  // INIT
  // ═══════════════════════════════════════════════

  renderRecentScans();

  return {
    scan, applyFilters, toggleAll, closePreview, extract,
    switchTab, smartExtract, createPackage, showPreview,
    filterCatalog, exportCatalogHTML, exportArchSVG,
    toggleDocsWatch, exportDocsMarkdown,
    runDiff, loadDeadCode,
    goToTourStep, tourPrev, tourNext, exportTourMarkdown,
  };
})();
