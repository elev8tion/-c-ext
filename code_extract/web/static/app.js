/* code-extract v0.3 web UI — Liquid Glass Neon */

const app = (() => {
  let currentScan = null;
  let allItems = [];
  let filteredItems = [];
  let selectedIds = new Set();
  let activeTab = 'scan';
  const tabLoaded = {};
  let catalogData = null;
  let tourData = null;
  let tourStep = 0;
  let docsWs = null;
  let itemStats = {};       // Phase 5: per-item stats
  let healthData = null;     // Phase 4: global health
  let langBreakdown = null;  // Phase 4: language breakdown

  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  // --- Init mermaid ---
  if (window.mermaid) {
    mermaid.initialize({ startOnLoad: false, theme: 'dark', securityLevel: 'loose' });
  }

  // --- Badge colors by type (inline style objects) ---
  const TYPE_COLORS = {
    function:     { bg: 'rgba(0,255,157,0.12)',  text: '#00ff9d' },
    class:        { bg: 'rgba(255,184,0,0.12)',  text: '#ffb800' },
    component:    { bg: 'rgba(167,139,250,0.12)', text: '#a78bfa' },
    widget:       { bg: 'rgba(167,139,250,0.12)', text: '#a78bfa' },
    method:       { bg: 'rgba(0,240,255,0.12)',  text: '#00f0ff' },
    mixin:        { bg: 'rgba(0,240,255,0.08)',  text: '#67e8f9' },
    struct:       { bg: 'rgba(255,184,0,0.08)',  text: '#fbbf24' },
    trait:        { bg: 'rgba(255,51,102,0.12)', text: '#ff3366' },
    interface:    { bg: 'rgba(45,212,191,0.12)', text: '#2dd4bf' },
    enum:         { bg: 'rgba(163,230,53,0.12)', text: '#a3e635' },
    module:       { bg: 'rgba(56,189,248,0.12)', text: '#38bdf8' },
    table:        { bg: 'rgba(251,146,60,0.12)', text: '#fb923c' },
    view:         { bg: 'rgba(45,212,191,0.08)', text: '#5eead4' },
    sql_function: { bg: 'rgba(244,114,182,0.12)', text: '#f472b6' },
    trigger:      { bg: 'rgba(255,51,102,0.08)', text: '#fb7185' },
    index:        { bg: 'rgba(255,255,255,0.05)', text: 'rgba(255,255,255,0.55)' },
    migration:    { bg: 'rgba(139,92,246,0.12)', text: '#8b5cf6' },
    policy:       { bg: 'rgba(232,121,249,0.12)', text: '#e879f9' },
    provider:     { bg: 'rgba(99,102,241,0.12)', text: '#818cf8' },
  };

  // --- Language colors ---
  const LANG_COLORS = {
    TypeScript: '#00f0ff',
    JavaScript: '#ffb800',
    Python:     '#a78bfa',
    Go:         '#00ff9d',
    Rust:       '#fb923c',
    Java:       '#ff3366',
    Dart:       '#38bdf8',
    Ruby:       '#f472b6',
    CSS:        '#e879f9',
    HTML:       '#fbbf24',
    SQL:        '#2dd4bf',
    Swift:      '#fb7185',
    Kotlin:     '#818cf8',
    C:          '#67e8f9',
    'C++':      '#5eead4',
    PHP:        '#a3e635',
  };

  function typeBadgeStyle(type) {
    const c = TYPE_COLORS[type] || { bg: 'rgba(255,255,255,0.05)', text: 'rgba(255,255,255,0.55)' };
    return `background:${c.bg}; color:${c.text};`;
  }

  // ═══════════════════════════════════════════════
  // TAB / NAV SWITCHING
  // ═══════════════════════════════════════════════

  function switchTab(tabName) {
    activeTab = tabName;

    // Update nav items
    $$('.nav-item').forEach(item => {
      item.classList.toggle('active', item.dataset.tab === tabName);
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
    if (currentScan && (!tabLoaded[tabName] || tabLoaded[tabName] === 'cached')) {
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
        dropdown.innerHTML = data.suggestions.map(s => {
          const name = s.split('/').filter(Boolean).pop() || s;
          return `<div class="ac-item px-3 py-1.5 cursor-pointer text-sm truncate" style="color: var(--text-secondary)" onmouseover="this.style.background='var(--glass-bg-hover)'" onmouseout="this.style.background=''" data-path="${s}" title="${s}">&#x1F4C1; ${name}</div>`;
        }).join('');
        const rect = pathInput.getBoundingClientRect();
        dropdown.style.left = (rect.right + 6) + 'px';
        dropdown.style.top = rect.top + 'px';
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

  let _pollTimer = null;

  function pollScanProgress(scanId) {
    if (_pollTimer) clearTimeout(_pollTimer);

    let interval = 800;
    const pollStart = Date.now();

    function doPoll() {
      _pollTimer = setTimeout(async () => {
        try {
          const res = await fetch(`/api/scan/${scanId}/status`);
          if (!res.ok) { doPoll(); return; }
          const info = await res.json();

          const total = info.items_count;
          const done = info.blocks_extracted;
          const analyses = info.analyses_ready || [];

          // Show progress bar during extraction
          const progressBar = $('#progress-bar');
          const progressFill = $('#progress-fill');
          const progressText = $('#progress-text');

          if (info.status === 'extracting') {
            const pct = total > 0 ? Math.round((done / total) * 100) : 0;
            setStatus(`Extracting blocks... ${done}/${total}`);
            if (progressBar) { progressBar.classList.remove('hidden'); }
            if (progressFill) { progressFill.style.width = pct + '%'; }
            if (progressText) { progressText.classList.remove('hidden'); progressText.textContent = pct + '%'; }
          } else if (info.status === 'analyzing') {
            setStatus(`Analyzing... (${analyses.length}/6 complete)`);
            if (progressFill) { progressFill.style.width = (50 + analyses.length * 8) + '%'; }
            analyses.forEach(a => { tabLoaded[a] = 'cached'; });
          } else if (info.status === 'ready') {
            _pollTimer = null;
            setStatus(`${total} items — all analyses ready`);
            if (progressBar) { progressBar.classList.add('hidden'); }
            if (progressText) { progressText.classList.add('hidden'); }
            analyses.forEach(a => { tabLoaded[a] = 'cached'; });

            fetchItemStats(scanId);
            loadDetailCards();
            ['catalog', 'architecture', 'health', 'docs', 'deadcode', 'tour'].forEach(tab => {
              loadTabData(tab);
            });
            return; // stop polling
          }
        } catch (_) { /* ignore network blips */ }

        // Adaptive backoff: 800ms → 2s after 30s → 4s after 2min
        const elapsed = Date.now() - pollStart;
        if (elapsed > 120000) interval = 4000;
        else if (elapsed > 30000) interval = 2000;

        doPoll();
      }, interval);
    }

    doPoll();
  }

  async function scan() {
    const path = pathInput.value.trim();
    if (!path) return;

    setStatus('Scanning...');
    $('#scan-btn').disabled = true;

    Object.keys(tabLoaded).forEach(k => delete tabLoaded[k]);
    catalogData = null;
    tourData = null;
    itemStats = {};
    healthData = null;
    langBreakdown = null;

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
      setStatus(`Found ${data.count} items — processing...`);
      $('#scan-dir').textContent = data.source_dir;

      pollScanProgress(data.scan_id);

    } catch (err) {
      setStatus(`Error: ${err.message}`);
    } finally {
      $('#scan-btn').disabled = false;
    }
  }

  // ═══════════════════════════════════════════════
  // ITEM STATS (Phase 5)
  // ═══════════════════════════════════════════════

  async function fetchItemStats(scanId) {
    try {
      const res = await fetch(`/api/analysis/item-stats/${scanId}`);
      if (!res.ok) return;
      const data = await res.json();
      itemStats = data.stats || {};
      renderResults(); // re-render with stats
    } catch (_) { /* endpoint may not exist yet */ }
  }

  // ═══════════════════════════════════════════════
  // DETAIL CARDS (Phase 4)
  // ═══════════════════════════════════════════════

  async function loadDetailCards() {
    // Compute language breakdown from allItems
    const langCounts = {};
    allItems.forEach(item => {
      langCounts[item.language] = (langCounts[item.language] || 0) + 1;
    });
    const total = allItems.length || 1;
    langBreakdown = Object.entries(langCounts)
      .sort((a, b) => b[1] - a[1])
      .map(([lang, count]) => ({
        language: lang,
        count,
        pct: Math.round((count / total) * 100),
        color: LANG_COLORS[lang] || 'rgba(255,255,255,0.3)',
      }));

    // Fetch health data if available
    if (currentScan) {
      try {
        const res = await fetch('/api/analysis/health', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ scan_id: currentScan.scan_id }),
        });
        if (res.ok) {
          healthData = await res.json();
        }
      } catch (_) {}
    }
  }

  function renderDetailCards() {
    // Health card
    const healthCard = $('#detail-health-card');
    const healthContent = $('#detail-health-content');
    if (healthData && healthCard) {
      const score = healthData.score || 0;
      const color = score >= 70 ? 'var(--success)' : score >= 40 ? 'var(--warning)' : 'var(--error)';
      healthContent.innerHTML = `
        <div class="flex items-center gap-3 mb-2">
          <span class="text-xl font-bold" style="color: ${color}">${score}</span>
          <span class="text-xs" style="color: var(--text-muted)">/100</span>
        </div>
        <div class="health-bar">
          <div class="health-bar-fill" style="width: ${score}%; background: ${color}"></div>
        </div>
        <div class="grid grid-cols-2 gap-2 mt-3 text-[0.6875rem]">
          <div style="color: var(--text-muted)">Complexity <span style="color: var(--text-secondary)">${healthData.long_functions?.length || 0}</span></div>
          <div style="color: var(--text-muted)">Coupling <span style="color: var(--text-secondary)">${healthData.coupling?.length || 0}</span></div>
          <div style="color: var(--text-muted)">Duplications <span style="color: var(--text-secondary)">${healthData.duplications?.length || 0}</span></div>
          <div style="color: var(--text-muted)">Circular <span style="color: var(--text-secondary)">0</span></div>
        </div>`;
      healthCard.classList.remove('hidden');
    }

    // Language breakdown card
    const langCard = $('#detail-lang-card');
    const langContent = $('#detail-lang-content');
    if (langBreakdown && langBreakdown.length > 0 && langCard) {
      const rows = langBreakdown.slice(0, 6).map(l => `
        <div class="flex items-center gap-2 py-0.5">
          <span class="w-2 h-2 rounded-full shrink-0" style="background: ${l.color}"></span>
          <span class="flex-1 text-[0.6875rem]" style="color: var(--text-secondary)">${esc(l.language)}</span>
          <span class="text-[0.6875rem]" style="color: var(--text-muted)">${l.count}</span>
        </div>`).join('');

      const barSegments = langBreakdown.map(l =>
        `<div class="lang-bar-segment" style="width: ${l.pct}%; background: ${l.color}"></div>`
      ).join('');

      langContent.innerHTML = `${rows}<div class="lang-bar mt-2">${barSegments}</div>`;
      langCard.classList.remove('hidden');
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
  // RENDER SCAN RESULTS (with enriched columns)
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
      html += `<tr class="file-group-header" style="background: var(--canvas-raised)"><td colspan="8" class="px-4 py-1.5 text-xs font-mono" style="color: var(--text-muted)">${shortFile}</td></tr>`;

      for (const item of items) {
        const checked = selectedIds.has(item.id) ? 'checked' : '';
        const badgeStyle = typeBadgeStyle(item.type);
        const stats = itemStats[item.id];

        // DEPS column
        const depsVal = stats ? stats.deps : '-';
        // SIZE column
        const sizeVal = stats && stats.size_bytes != null ? (stats.size_bytes < 1024 ? stats.size_bytes + 'B' : Math.round(stats.size_bytes / 1024) + 'kb') : '-';
        // HEALTH column
        let healthCol = '<span style="color: var(--text-muted)">-</span>';
        if (stats && stats.health_score != null) {
          const hs = stats.health_score;
          const hColor = hs >= 70 ? 'var(--success)' : hs >= 40 ? 'var(--warning)' : 'var(--error)';
          healthCol = `<span class="inline-flex items-center gap-1"><span class="mini-health-bar"><span class="mini-health-bar-fill" style="width:${hs}%; background:${hColor}"></span></span><span style="color:${hColor}">${hs}</span></span>`;
        }

        html += `
          <tr class="result-row cursor-pointer" style="border-bottom: 1px solid var(--border-default)" data-id="${item.id}">
            <td class="pl-4 pr-2 py-1.5 w-8">
              <input type="checkbox" class="item-check" data-id="${item.id}" ${checked}>
            </td>
            <td class="px-2 py-1.5 w-24">
              <span class="text-xs px-1.5 py-0.5 rounded" style="${badgeStyle}">${item.type}</span>
            </td>
            <td class="px-2 py-1.5 font-medium text-sm" style="color: var(--text-primary)">${item.qualified_name}</td>
            <td class="px-2 py-1.5 text-xs" style="color: var(--text-muted)">${item.language}</td>
            <td class="px-2 py-1.5 text-xs" style="color: var(--text-secondary)">${depsVal}</td>
            <td class="px-2 py-1.5 text-xs" style="color: var(--text-secondary)">${sizeVal}</td>
            <td class="px-2 py-1.5 text-xs">${healthCol}</td>
            <td class="pr-4 py-1.5 text-xs text-right" style="color: var(--text-muted)">L${item.line}${item.end_line ? '-' + item.end_line : ''}</td>
          </tr>`;
      }
    }

    tbody.innerHTML = html;
    const countEl = $('#item-count');
    if (countEl) countEl.textContent = `${filteredItems.length} items`;
    const selInfo = $('#selected-count-info');
    if (selInfo) selInfo.textContent = `${selectedIds.size} selected`;

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
    const selInfo = $('#selected-count-info');
    if (selInfo) selInfo.textContent = `${n} selected`;
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
      badge.setAttribute('style', typeBadgeStyle(data.type));
      badge.textContent = data.type;

      const codeEl = $('#preview-code');
      codeEl.textContent = data.code;
      codeEl.className = `text-xs language-${data.language}`;
      hljs.highlightElement(codeEl);

      // Stats line
      const statsEl = $('#preview-stats');
      if (statsEl) {
        const lineCount = data.code ? data.code.split('\n').length : 0;
        statsEl.textContent = `${lineCount} lines · ${data.language} · ${data.type}`;
        statsEl.classList.remove('hidden');
      }

      const panel = $('#preview-panel');
      panel.classList.remove('hidden');
      panel.classList.add('flex');

      // Render detail cards
      renderDetailCards();
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

    const langs = new Set(items.map(i => i.language));
    const sel = $('#catalog-lang-filter');
    sel.innerHTML = '<option value="">All Languages</option>' +
      [...langs].sort().map(l => `<option value="${l}">${l}</option>`).join('');

    renderCatalogCards(items);
  }

  function renderCatalogCards(items) {
    const grid = $('#catalog-grid');
    grid.innerHTML = items.map((item) => {
      const badgeStyle = typeBadgeStyle(item.type);
      const langBadgeStyle = `background: rgba(255,255,255,0.05); color: var(--text-secondary);`;
      const params = (item.parameters || []).map(p =>
        `<dt>${esc(p.name)}${p.type_annotation ? ': ' + esc(p.type_annotation) : ''}${p.default_value ? ' = ' + esc(p.default_value) : ''}</dt>`
      ).join('');

      return `<div class="catalog-card">
        <div class="card-header">
          <span class="card-name">${esc(item.name)}</span>
          <div class="card-badges">
            <span class="card-badge" style="${badgeStyle}">${item.type}</span>
            <span class="card-badge" style="${langBadgeStyle}">${item.language}</span>
          </div>
        </div>
        ${item.line_count ? `<div class="text-xs" style="color: var(--text-muted)">${item.line_count} lines</div>` : ''}
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

    const container = $('#arch-diagram');
    container.innerHTML = `<pre class="mermaid">${data.mermaid}</pre>`;
    if (window.mermaid) {
      mermaid.run({ nodes: container.querySelectorAll('.mermaid') });
    }

    const modList = $('#arch-modules');
    modList.innerHTML = (data.modules || []).map(m => `
      <div class="module-item" onclick="this.classList.toggle('expanded')">
        <div class="module-item-header">
          <span>${esc(m.directory)}</span>
          <span class="module-item-count">${m.item_count} items</span>
        </div>
        <div class="module-item-body">
          ${(m.items || []).map(i => `<div class="py-0.5">${esc(i.name)} <span style="color: var(--text-muted)">(${i.type})</span></div>`).join('')}
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
      healthData = data;
      renderHealth(data);
      setStatus('Health analysis loaded');
    } catch (err) {
      setStatus(`Health error: ${err.message}`);
    }
  }

  function renderHealth(data) {
    $('#health-empty').classList.add('hidden');
    $('#health-content').classList.remove('hidden');

    const score = data.score || 0;
    const color = score >= 70 ? 'var(--success)' : score >= 40 ? 'var(--warning)' : 'var(--error)';
    $('#health-score').innerHTML = `<span style="color: ${color}">Health: ${score}/100</span>`;

    const longFns = $('#health-long-fns');
    longFns.innerHTML = (data.long_functions || []).map(f => {
      const len = f.line_count || 0;
      const c = len < 30 ? 'var(--success)' : len < 60 ? 'var(--warning)' : 'var(--error)';
      return `<div class="metric-card" onclick="app.showPreview('${esc(f.item_id || '')}')">
        <div class="metric-name">${esc(f.name)}</div>
        <div class="metric-value" style="color: ${c}">${len} lines</div>
        <div class="text-xs truncate" style="color: var(--text-muted)">${esc(f.file || '')}</div>
      </div>`;
    }).join('') || `<div class="text-xs" style="color: var(--text-muted)">No long functions found</div>`;

    const dups = $('#health-duplicates');
    dups.innerHTML = (data.duplications || []).map(d => {
      return `<div class="metric-card">
        <div class="metric-name">${esc(d.item_a)} &harr; ${esc(d.item_b)}</div>
        <div class="metric-value" style="color: var(--warning)">${Math.round(d.similarity * 100)}% similar</div>
      </div>`;
    }).join('') || `<div class="text-xs" style="color: var(--text-muted)">No duplications found</div>`;

    const coupling = $('#health-coupling');
    coupling.innerHTML = (data.coupling || []).map(c => {
      return `<div class="metric-card" onclick="app.showPreview('${esc(c.item_id || '')}')">
        <div class="metric-name">${esc(c.name)}</div>
        <div class="metric-value">${c.score} connections</div>
      </div>`;
    }).join('') || `<div class="text-xs" style="color: var(--text-muted)">No coupling data</div>`;
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
        <h3>${esc(s.name)} <span class="text-xs" style="color: var(--text-muted)">(${s.type})</span></h3>
        ${s.signature ? `<div class="docs-signature">${esc(s.signature)}</div>` : ''}
        ${s.description ? `<p class="text-xs mb-2" style="color: var(--text-secondary)">${esc(s.description)}</p>` : ''}
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
        <span class="text-xs" style="color: var(--success)">+ ADDED</span>
        <div class="text-sm font-medium" style="color: var(--text-primary)">${esc(item.name)} <span class="text-xs" style="color: var(--text-muted)">(${item.type})</span></div>
      </div>`;
    });

    (data.removed || []).forEach(item => {
      html += `<div class="diff-item removed">
        <span class="text-xs" style="color: var(--error)">- REMOVED</span>
        <div class="text-sm font-medium" style="color: var(--text-primary)">${esc(item.name)} <span class="text-xs" style="color: var(--text-muted)">(${item.type})</span></div>
      </div>`;
    });

    (data.modified || []).forEach(item => {
      html += `<div class="diff-item modified">
        <span class="text-xs" style="color: var(--warning)">~ MODIFIED</span>
        <div class="text-sm font-medium" style="color: var(--text-primary)">${esc(item.name)} <span class="text-xs" style="color: var(--text-muted)">(${item.type})</span></div>
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
      const confColor = item.confidence >= 0.8 ? 'var(--error)' : item.confidence >= 0.5 ? 'var(--warning)' : 'var(--success)';
      const shortFile = (item.file || '').replace(currentScan?.source_dir || '', '').replace(/^\//, '');
      return `<tr class="result-row cursor-pointer" style="border-bottom: 1px solid var(--border-default)" onclick="app.showPreview('${esc(item.item_id || '')}')">
        <td class="px-3 py-2 font-medium" style="color: var(--text-primary)">${esc(item.name)}</td>
        <td class="px-3 py-2 text-xs"><span class="px-1.5 py-0.5 rounded" style="${typeBadgeStyle(item.type)}">${item.type}</span></td>
        <td class="px-3 py-2 text-xs truncate max-w-xs" style="color: var(--text-muted)">${shortFile}</td>
        <td class="px-3 py-2 text-xs" style="color: ${confColor}">${Math.round(item.confidence * 100)}%</td>
        <td class="px-3 py-2 text-xs" style="color: var(--text-muted)">${esc(item.reason || '')}</td>
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

    const list = $('#tour-step-list');
    list.innerHTML = tourData.steps.map((s, i) => `
      <div class="tour-step-list-item ${i === tourStep ? 'active' : ''}" onclick="app.goToTourStep(${i})">
        ${i + 1}. ${esc(s.name)}
      </div>
    `).join('');

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
        <span class="ml-2 text-xs" style="color: var(--text-muted)">${step.type || ''} &middot; ${step.language || ''}</span>
      </div>
      <div class="tour-step-desc">${esc(step.description || '')}</div>
      ${step.code ? `<div class="tour-step-code"><pre><code class="text-xs">${esc(step.code)}</code></pre></div>` : ''}
      ${deps ? `<div class="tour-step-deps">Dependencies: ${deps}</div>` : ''}
    </div>`;

    content.querySelectorAll('pre code').forEach(el => hljs.highlightElement(el));

    $('#tour-prev').disabled = tourStep === 0;
    $('#tour-next').disabled = tourStep >= tourData.steps.length - 1;

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
      return `<div class="recent-item group flex items-center gap-1 px-2 py-1 rounded cursor-pointer" style="color: var(--text-secondary)" data-path="${r.path}" data-scan-id="${r.scanId || ''}">
        <span class="truncate flex-1">${short} <span style="color: var(--text-muted)">(${r.count})</span></span>
        <button class="recent-delete opacity-0 group-hover:opacity-100 transition-opacity px-1" style="color: var(--text-muted)" title="Remove">&times;</button>
      </div>`;
    }).join('');
    container.querySelectorAll('.recent-item').forEach(el => {
      el.querySelector('.recent-delete').addEventListener('click', (e) => {
        e.stopPropagation();
        deleteRecentScan(el.dataset.path, el.dataset.scanId);
      });
      el.addEventListener('click', () => {
        pathInput.value = el.dataset.path;
        scan();
      });
    });
  }

  async function deleteRecentScan(path, scanId) {
    if (scanId) {
      try {
        await fetch(`/api/scan/${scanId}`, { method: 'DELETE' });
      } catch (_) {}
    }

    let recent = JSON.parse(localStorage.getItem('ce_recent') || '[]');
    recent = recent.filter(r => r.path !== path);
    localStorage.setItem('ce_recent', JSON.stringify(recent));
    renderRecentScans();

    if (currentScan && currentScan.source_dir === path) {
      if (_pollTimer) { clearTimeout(_pollTimer); _pollTimer = null; }

      currentScan = null;
      allItems = [];
      filteredItems = [];
      selectedIds.clear();
      catalogData = null;
      tourData = null;
      itemStats = {};
      healthData = null;
      langBreakdown = null;
      Object.keys(tabLoaded).forEach(k => delete tabLoaded[k]);

      $('#results-body').innerHTML = '';
      $('#results-table').classList.add('hidden');
      $('#empty-state').classList.remove('hidden');
      $('#scan-dir').textContent = '';
      $('#item-count').textContent = '0 items';
      $('#download-link').classList.add('hidden');
      hideProgress();

      const tabPanels = ['catalog', 'arch', 'health', 'docs', 'deadcode', 'tour'];
      tabPanels.forEach(t => {
        const empty = $(`#${t}-empty`);
        const content = $(`#${t}-content`);
        if (empty) empty.classList.remove('hidden');
        if (content) content.classList.add('hidden');
      });

      // Hide detail panel cards
      const hc = $('#detail-health-card');
      const lc = $('#detail-lang-card');
      if (hc) hc.classList.add('hidden');
      if (lc) lc.classList.add('hidden');

      updateSelection();
      switchTab('scan');
      setStatus('Ready');
    }
  }

  // ═══════════════════════════════════════════════
  // UTILITY
  // ═══════════════════════════════════════════════

  function setStatus(text) {
    const footer = $('#footer-status');
    if (footer) footer.textContent = text;
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
