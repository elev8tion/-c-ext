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

  // Remix Board state
  let remixPalette = [];       // [{scan_id, project_name, source_dir, items}]
  let remixCanvas = [];        // [{scan_id, item_id, name, type, language, project_name, parent}]
  let remixConflicts = [];     // from server
  let remixResolutions = {};   // "scan_id::item_id" → new_name
  let remixValidation = { errors: [], warnings: [], conflicts: [], is_buildable: true };
  let remixScore = null;       // {score, grade, breakdown}
  let _currentSuggestions = [];
  let _suggestionTimer = null;
  let _remixStateDirty = false;
  let remixUnresolved = [];
  let remixPreviewData = null;
  let _remixPreviewTimer = null;
  const REMIX_TEMPLATES_KEY = 'code-extract-remix-templates';
  const REMIX_CONTAINER_TYPES = new Set(['class', 'component', 'widget', 'struct', 'trait', 'interface', 'mixin']);

  // AI Chat state
  let aiChatHistory = [];
  let aiLoading = false;
  const AI_KEY_STORAGE = 'code-extract-ai-key';

  // AI Agent / Copilot state
  let aiAgentLoading = false;
  let _aiWidgetVisible = false;
  let _aiWidgetCollapsed = false;

  // Language compatibility groups (mirrors backend LANGUAGE_GROUPS)
  const REMIX_LANGUAGE_GROUPS = {
    javascript: 'js_ts', typescript: 'js_ts',
    java: 'jvm', kotlin: 'jvm',
    python: 'python', dart: 'dart', rust: 'rust', go: 'go',
    cpp: 'cpp', ruby: 'ruby', swift: 'swift', csharp: 'csharp', sql: 'sql',
  };
  const REMIX_SQL_TYPES = new Set([
    'table', 'view', 'trigger', 'policy', 'migration', 'index', 'sql_function',
  ]);

  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  // --- Init mermaid ---
  if (window.mermaid) {
    mermaid.initialize({ startOnLoad: false, theme: 'dark', securityLevel: 'loose' });
  }

  // --- Register cytoscape-dagre plugin ---
  if (window.cytoscape && window.cytoscapeDagre) {
    cytoscape.use(cytoscapeDagre);
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
    // Intercept 'ai' tab — open the floating widget instead
    if (tabName === 'ai') {
      if (!_aiWidgetVisible) toggleAIWidget();
      return;
    }

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

    // Re-layout architecture graph when switching to its tab (may have been initialized while hidden with 0x0 container)
    if (tabName === 'architecture' && archCy) {
      setTimeout(() => {
        archCy.resize();
        const cfg = Object.assign({}, ARCH_LAYOUTS[currentArchLayout] || ARCH_LAYOUTS.dagre, { animate: false });
        archCy.layout(cfg).run();
        archCy.fit(undefined, 30);
      }, 100);
    }

    // Lazy-load tab data if scan exists (remix loads independently of currentScan)
    if (tabName === 'remix') {
      loadRemix();
    } else if (currentScan && (!tabLoaded[tabName] || tabLoaded[tabName] === 'cached')) {
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
      clone: loadClone,
      boilerplate: loadBoilerplate,
      migration: loadMigration,
      remix: loadRemix,
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
            ['catalog', 'architecture', 'health', 'docs', 'deadcode', 'tour', 'clone', 'boilerplate', 'migration', 'remix'].forEach(tab => {
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
    boilerplateSelectedIds.clear();
    boilerplateTemplate = null;
    boilerplateSelectedPattern = null;
    boilerplateVariants = [];
    variantCounter = 0;
    migrationPatterns = [];
    remixCanvas = [];
    remixConflicts = [];
    remixResolutions = {};

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
  // PACKAGE POPOVER
  // ═══════════════════════════════════════════════

  let _popoverOutsideHandler = null;

  function showPackagePopover() {
    if (selectedIds.size === 0 || !currentScan) return;
    const nameInput = $('#package-name-input');
    const firstSelected = allItems.find(i => selectedIds.has(i.id));
    nameInput.value = firstSelected ? firstSelected.name.replace(/[^a-zA-Z0-9_-]/g, '-') : 'extracted-package';
    $('#package-popover').classList.remove('hidden');
    nameInput.focus();

    nameInput.addEventListener('keydown', function onEnter(e) {
      if (e.key === 'Enter') {
        e.preventDefault();
        nameInput.removeEventListener('keydown', onEnter);
        confirmPackage();
      }
    });

    setTimeout(() => {
      _popoverOutsideHandler = (e) => {
        const popover = $('#package-popover');
        if (popover && !popover.contains(e.target)) hidePackagePopover();
      };
      document.addEventListener('click', _popoverOutsideHandler);
    }, 0);
  }

  function hidePackagePopover() {
    $('#package-popover').classList.add('hidden');
    if (_popoverOutsideHandler) {
      document.removeEventListener('click', _popoverOutsideHandler);
      _popoverOutsideHandler = null;
    }
  }

  async function confirmPackage() {
    const packageName = ($('#package-name-input').value || '').trim() || 'extracted-package';
    hidePackagePopover();
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
          package_name: packageName,
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
  // TAB: ARCHITECTURE (Cytoscape.js)
  // ═══════════════════════════════════════════════

  let archCy = null;  // Cytoscape instance
  let currentArchLayout = 'dagre';

  const ARCH_LAYOUTS = {
    dagre:  { name: 'dagre', rankDir: 'TB', nodeSep: 50, rankSep: 70, padding: 30, animate: true, animationDuration: 400 },
    cose:   { name: 'cose', idealEdgeLength: 100, nodeRepulsion: 6000, nodeOverlap: 20, padding: 30, animate: true, animationDuration: 400 },
    circle: { name: 'circle', padding: 30, animate: true, animationDuration: 400 },
  };

  const ARCH_TYPE_COLORS = {
    module:    '#f78166',
    class:     '#d2a8ff',
    component: '#79c0ff',
    function:  '#7ee787',
    method:    '#ffa657',
    overflow:  '#484f58',
  };

  async function loadArchitecture() {
    if (!currentScan) return;
    setStatus('Analyzing architecture...');
    const loadingEl = $('#arch-loading');
    if (loadingEl) loadingEl.classList.remove('hidden');

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
    } finally {
      if (loadingEl) loadingEl.classList.add('hidden');
    }
  }

  function renderArchitecture(data) {
    $('#arch-empty').classList.add('hidden');
    $('#arch-content').classList.remove('hidden');

    // Stats bar
    const s = data.stats || {};
    $('#arch-stats').innerHTML = `${s.total_items || 0} items &middot; ${s.total_modules || 0} modules &middot; ${s.total_edges || 0} edges &middot; ${s.cross_module_edges || 0} cross-module`;

    // Destroy previous instance
    if (archCy) { archCy.destroy(); archCy = null; }

    // Init Cytoscape
    archCy = cytoscape({
      container: $('#arch-diagram'),
      elements: data.elements || [],
      minZoom: 0.15,
      maxZoom: 4,
      wheelSensitivity: 0.3,
      style: [
        // Compound/parent nodes (directories)
        { selector: 'node:parent', style: {
          'background-color': 'rgba(255,255,255,0.02)',
          'background-opacity': 1,
          'border-color': 'rgba(255,255,255,0.08)',
          'border-width': 1.5,
          'shape': 'roundrectangle',
          'padding': '20px',
          'label': 'data(label)',
          'text-valign': 'top',
          'text-halign': 'center',
          'font-size': '13px',
          'font-weight': 'bold',
          'color': 'rgba(255,255,255,0.45)',
          'text-margin-y': -6,
        }},
        // Leaf nodes (sized by connections)
        { selector: 'node:child', style: {
          'background-color': function(ele) { return ARCH_TYPE_COLORS[ele.data('type')] || '#8b949e'; },
          'width': function(ele) { var c = ele.data('connections') || 0; return Math.min(52, Math.max(28, 28 + c * 3)); },
          'height': function(ele) { var c = ele.data('connections') || 0; return Math.min(52, Math.max(28, 28 + c * 3)); },
          'label': 'data(label)',
          'text-valign': 'bottom',
          'text-halign': 'center',
          'font-size': '9px',
          'color': 'rgba(255,255,255,0.7)',
          'text-margin-y': 6,
          'border-width': 2,
          'border-color': '#08090d',
          'text-outline-color': '#08090d',
          'text-outline-width': 2,
          'transition-property': 'background-color, border-color, width, height, opacity',
          'transition-duration': '0.2s',
        }},
        // Overflow nodes (+N more)
        { selector: 'node[type="overflow"]', style: {
          'background-color': '#21262d',
          'border-color': '#30363d',
          'border-width': 1,
          'border-style': 'dashed',
          'width': 28,
          'height': 28,
          'font-size': '8px',
          'color': 'rgba(255,255,255,0.35)',
        }},
        // Edges
        { selector: 'edge', style: {
          'width': 1.2,
          'line-color': 'rgba(255,255,255,0.1)',
          'target-arrow-color': 'rgba(255,255,255,0.1)',
          'target-arrow-shape': 'triangle',
          'arrow-scale': 0.7,
          'curve-style': 'bezier',
          'opacity': 0.5,
          'transition-property': 'line-color, target-arrow-color, opacity, width',
          'transition-duration': '0.2s',
        }},
        // Cross-module edges (thickness by weight)
        { selector: 'edge[edgeType="cross_module"]', style: {
          'width': function(ele) { var w = ele.data('weight') || 1; return Math.min(5, Math.max(1.5, 1 + w * 0.5)); },
          'line-color': 'rgba(0,240,255,0.15)',
          'target-arrow-color': 'rgba(0,240,255,0.15)',
          'line-style': 'dashed',
          'opacity': 0.6,
        }},
        // Highlighted states
        { selector: 'node.highlighted', style: {
          'border-color': '#00f0ff',
          'border-width': 3,
          'width': function(ele) { var c = ele.data('connections') || 0; return Math.min(52, Math.max(28, 28 + c * 3)) + 8; },
          'height': function(ele) { var c = ele.data('connections') || 0; return Math.min(52, Math.max(28, 28 + c * 3)) + 8; },
          'z-index': 999,
        }},
        { selector: 'node.neighbor', style: {
          'border-color': '#00f0ff',
          'border-width': 2,
          'opacity': 1,
        }},
        { selector: 'edge.highlighted', style: {
          'line-color': '#00f0ff',
          'target-arrow-color': '#00f0ff',
          'opacity': 1,
          'width': 2.5,
          'z-index': 999,
        }},
        { selector: 'node.dimmed', style: { 'opacity': 0.12 }},
        { selector: 'edge.dimmed', style: { 'opacity': 0.04 }},
      ],
      layout: { name: 'preset' },
    });

    // ── Tooltip ──
    const tooltip = $('#arch-tooltip');

    archCy.on('mouseover', 'node:child', function(e) {
      const d = e.target.data();
      if (d.type === 'overflow') return;
      const color = ARCH_TYPE_COLORS[d.type] || '#8b949e';
      const inE = e.target.incomers('edge').length;
      const outE = e.target.outgoers('edge').length;
      tooltip.innerHTML = `
        <div style="font-weight:600;font-size:13px;color:#f0f6fc;margin-bottom:3px">${esc(d.label)}</div>
        <span style="display:inline-block;padding:1px 8px;border-radius:12px;font-size:10px;font-weight:500;background:${color}22;color:${color}">${d.type}</span>
        <div style="color:#8b949e;font-size:11px;margin-top:5px">${d.file ? esc(d.file) : ''}</div>
        <div style="color:#8b949e;font-size:11px;margin-top:2px">${outE} outgoing &middot; ${inE} incoming</div>`;
      tooltip.style.display = 'block';
    });

    archCy.on('mousemove', 'node:child', function(e) {
      const p = e.renderedPosition;
      const container = archCy.container();
      const cw = container.clientWidth;
      const ch = container.clientHeight;
      const tw = 300; // max-width of tooltip
      const th = 100; // estimated tooltip height
      let x = p.x + 18;
      let y = p.y - 8;
      if (x + tw > cw) x = p.x - tw - 10;
      if (y + th > ch) y = ch - th - 8;
      if (y < 0) y = 4;
      tooltip.style.left = x + 'px';
      tooltip.style.top  = y + 'px';
    });

    archCy.on('mouseout', 'node:child', function() {
      tooltip.style.display = 'none';
    });

    // ── Click to focus ──
    archCy.on('tap', 'node:child', function(e) {
      const node = e.target;
      archResetHighlight();
      archCy.elements().addClass('dimmed');
      node.removeClass('dimmed').addClass('highlighted');
      const edges = node.connectedEdges();
      edges.removeClass('dimmed').addClass('highlighted');
      const neighbors = node.neighborhood('node');
      neighbors.removeClass('dimmed').addClass('neighbor');
      node.ancestors().removeClass('dimmed');
      neighbors.ancestors().removeClass('dimmed');
    });

    archCy.on('tap', function(e) {
      if (e.target === archCy) archResetHighlight();
    });

    // If the tab is currently visible, force resize + re-layout after DOM settles
    if (activeTab === 'architecture') {
      setTimeout(() => {
        archCy.resize();
        archCy.layout(ARCH_LAYOUTS[currentArchLayout] || ARCH_LAYOUTS.dagre).run();
      }, 100);
    }

    // ── Module sidebar ──
    const modList = $('#arch-modules');
    modList.innerHTML = (data.modules || []).map(m => {
      const dirId = _safeId(m.directory);
      return `
      <div class="module-item" data-dir-id="${dirId}">
        <div class="module-item-header">
          <span>${esc(m.directory)}</span>
          <span class="module-item-count">${m.item_count} items</span>
        </div>
        <div class="module-item-body">
          ${(m.items || []).map(i => `<div class="py-0.5">${esc(i.name)} <span style="color: var(--text-muted)">(${i.type})</span></div>`).join('')}
        </div>
      </div>`;
    }).join('');

    // Single-click: toggle expand/collapse; Double-click: zoom to module in graph
    modList.querySelectorAll('.module-item-header').forEach(header => {
      header.addEventListener('click', () => {
        header.parentElement.classList.toggle('expanded');
      });
      header.addEventListener('dblclick', (e) => {
        e.preventDefault();
        const dirId = header.parentElement.dataset.dirId;
        if (!archCy || !dirId) return;
        const compound = archCy.getElementById(dirId);
        if (compound.empty()) return;
        const targets = compound.union(compound.descendants());
        archCy.animate({ fit: { eles: targets, padding: 40 } }, { duration: 400 });
        // Flash cyan border on compound
        compound.style('border-color', '#00f0ff');
        compound.style('border-width', 3);
        setTimeout(() => {
          compound.style('border-color', 'rgba(255,255,255,0.08)');
          compound.style('border-width', 1.5);
        }, 600);
      });
    });
  }

  function setArchLayout(name) {
    if (!archCy) return;
    currentArchLayout = name;
    document.querySelectorAll('.arch-ctrl-btn[data-layout]').forEach(b => b.classList.remove('active'));
    const btn = document.querySelector(`.arch-ctrl-btn[data-layout="${name}"]`);
    if (btn) btn.classList.add('active');
    archCy.layout(ARCH_LAYOUTS[name] || ARCH_LAYOUTS.dagre).run();
  }

  function archFitView() {
    if (archCy) archCy.fit(undefined, 30);
  }

  function archResetHighlight() {
    if (archCy) archCy.elements().removeClass('highlighted neighbor dimmed');
    const searchInput = $('#arch-search');
    if (searchInput) searchInput.value = '';
  }

  function exportArchPNG() {
    if (!archCy) return;
    archResetHighlight();
    const dataUrl = archCy.png({ bg: '#08090d', scale: 2, full: true });
    const a = document.createElement('a');
    a.href = dataUrl;
    a.download = 'architecture.png';
    a.click();
  }

  // Match backend's _safe_id() — converts directory paths to valid Cytoscape node IDs
  function _safeId(dirPath) {
    return (dirPath || '').replace(/[^a-zA-Z0-9_-]/g, '_').replace(/^_+|_+$/g, '') || 'root';
  }

  // ── Search / filter nodes ──
  function archSearchNodes(query) {
    if (!archCy) return;
    query = (query || '').trim().toLowerCase();
    if (!query) { archResetHighlight(); return; }

    archCy.elements().addClass('dimmed');
    const matches = archCy.nodes().filter(n => {
      const label = (n.data('label') || '').toLowerCase();
      const file = (n.data('file') || '').toLowerCase();
      return label.includes(query) || file.includes(query);
    });
    matches.removeClass('dimmed').addClass('highlighted');
    // Show parent compounds of matched nodes
    matches.ancestors().removeClass('dimmed');
  }

  // ── ESC key handler ──
  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape' && activeTab === 'architecture') {
      archResetHighlight();
    }
  });

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

  let lastDocUpdate = null;
  let docsWatchTimerInterval = null;

  function _docsTimestamp() {
    if (!lastDocUpdate) return '';
    const sec = Math.round((Date.now() - lastDocUpdate) / 1000);
    if (sec < 5) return ' · Updated just now';
    if (sec < 60) return ` · Updated ${sec}s ago`;
    const min = Math.round(sec / 60);
    return ` · Updated ${min}m ago`;
  }

  function _refreshDocsIndicator() {
    const indicator = $('#docs-live-indicator');
    if (!indicator || indicator.classList.contains('hidden')) return;
    indicator.innerHTML = `<span class="w-2 h-2 rounded-full inline-block animate-pulse" style="background: var(--success)"></span> Live${_docsTimestamp()}`;
  }

  function toggleDocsWatch(enabled) {
    if (enabled && currentScan) {
      const wsUrl = `ws://${location.host}/api/docs/ws/docs-watch`;
      docsWs = new WebSocket(wsUrl);
      docsWs.onopen = () => {
        docsWs.send(JSON.stringify({ scan_id: currentScan.scan_id }));
        const indicator = $('#docs-live-indicator');
        indicator.classList.remove('hidden');
        indicator.style.color = 'var(--success)';
        indicator.innerHTML = '<span class="w-2 h-2 rounded-full inline-block animate-pulse" style="background: var(--success)"></span> Live';
        docsWatchTimerInterval = setInterval(_refreshDocsIndicator, 10000);
      };
      docsWs.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data);
          if (data.sections) {
            renderDocs(data);
            lastDocUpdate = Date.now();
            _refreshDocsIndicator();
          }
        } catch (err) {
          setStatus(`Docs watch: parse error — ${err.message}`);
        }
      };
      docsWs.onclose = () => {
        docsWs = null;
        if (docsWatchTimerInterval) { clearInterval(docsWatchTimerInterval); docsWatchTimerInterval = null; }
        const indicator = $('#docs-live-indicator');
        indicator.classList.remove('hidden');
        indicator.style.color = 'var(--warning)';
        indicator.innerHTML = '<span class="w-2 h-2 rounded-full inline-block" style="background: var(--warning)"></span> Disconnected — toggle to reconnect';
        $('#docs-watch-toggle').checked = false;
      };
      docsWs.onerror = () => {
        // onclose will fire after onerror, so the disconnect UI is handled there
      };
    } else if (docsWs) {
      docsWs.close();
      docsWs = null;
      if (docsWatchTimerInterval) { clearInterval(docsWatchTimerInterval); docsWatchTimerInterval = null; }
      const indicator = $('#docs-live-indicator');
      indicator.classList.add('hidden');
      indicator.style.color = 'var(--success)';
      indicator.innerHTML = '<span class="w-2 h-2 rounded-full inline-block animate-pulse" style="background: var(--success)"></span> Live';
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
    const added = data.added || [];
    const removed = data.removed || [];
    const modified = data.modified || [];

    // Collect all types across change categories
    const allTypes = new Set();
    [...added, ...removed, ...modified].forEach(i => { if (i.type) allTypes.add(i.type); });

    // Changelog summary
    const summaryEl = $('#diff-summary');
    summaryEl.classList.remove('hidden');
    summaryEl.innerHTML = `
      <div class="text-xs mb-2" style="color: var(--text-secondary)">
        ${added.length} added, ${removed.length} removed, ${modified.length} modified across ${allTypes.size} type${allTypes.size !== 1 ? 's' : ''}
      </div>
      <div class="diff-summary">
        <span class="diff-stat diff-added">${added.length} added</span>
        <span class="diff-stat diff-removed">${removed.length} removed</span>
        <span class="diff-stat diff-modified">${modified.length} modified</span>
        <span class="diff-stat diff-unchanged">${data.unchanged || 0} unchanged</span>
      </div>`;

    // Group items by type
    function groupByType(items) {
      const groups = {};
      items.forEach(item => {
        const t = item.type || 'unknown';
        (groups[t] = groups[t] || []).push(item);
      });
      return groups;
    }

    function renderDiffItem(item, kind) {
      const labels = { added: { sym: '+', label: 'ADDED', color: 'var(--success)' }, removed: { sym: '-', label: 'REMOVED', color: 'var(--error)' }, modified: { sym: '~', label: 'MODIFIED', color: 'var(--warning)' } };
      const l = labels[kind];
      let diffPreview = '';
      if (kind === 'modified' && item.before && item.after) {
        diffPreview = `<div class="diff-side-by-side">
          <pre><code class="text-xs">${esc(item.before)}</code></pre>
          <pre><code class="text-xs">${esc(item.after)}</code></pre>
        </div>`;
      }
      return `<div class="diff-item ${kind}">
        <span class="text-xs" style="color: ${l.color}">${l.sym} ${l.label}</span>
        <div class="text-sm font-medium" style="color: var(--text-primary)">${esc(item.name)}</div>
        ${diffPreview}
      </div>`;
    }

    // Build grouped sections per type
    const results = $('#diff-results');
    let html = '';

    const addedByType = groupByType(added);
    const removedByType = groupByType(removed);
    const modifiedByType = groupByType(modified);

    const sortedTypes = [...allTypes].sort();

    for (const type of sortedTypes) {
      const typeAdded = addedByType[type] || [];
      const typeRemoved = removedByType[type] || [];
      const typeModified = modifiedByType[type] || [];
      const total = typeAdded.length + typeRemoved.length + typeModified.length;

      const badgeStyle = typeBadgeStyle(type);

      html += `<details open class="mb-3">
        <summary class="cursor-pointer flex items-center gap-2 py-2 text-sm font-medium" style="color: var(--text-primary)">
          <span class="px-1.5 py-0.5 rounded text-xs" style="${badgeStyle}">${esc(type)}</span>
          <span style="color: var(--text-muted)">${total} change${total !== 1 ? 's' : ''}</span>
        </summary>
        <div class="pl-2">`;

      typeAdded.forEach(item => { html += renderDiffItem(item, 'added'); });
      typeRemoved.forEach(item => { html += renderDiffItem(item, 'removed'); });
      typeModified.forEach(item => { html += renderDiffItem(item, 'modified'); });

      html += `</div></details>`;
    }

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
  // TAB: CLONE
  // ═══════════════════════════════════════════════

  function loadClone() {
    if (!currentScan) return;
    $('#clone-empty').classList.add('hidden');
    $('#clone-content').classList.remove('hidden');
    tabLoaded.clone = true;

    const sel = $('#clone-item-select');
    sel.innerHTML = '<option value="">Choose an item...</option>' +
      allItems.map(i => {
        const badgeText = i.type || '';
        return `<option value="${esc(i.id)}">${esc(i.name)} (${badgeText})</option>`;
      }).join('');
  }

  function onCloneItemChange() {
    const itemId = $('#clone-item-select').value;
    if (!itemId) { $('#clone-preview').innerHTML = ''; return; }
    const item = allItems.find(i => i.id === itemId);
    if (item) {
      $('#clone-preview').innerHTML = `<div class="pattern-card"><div class="text-xs" style="color: var(--text-muted)">Selected: <strong style="color: var(--text-primary)">${esc(item.qualified_name)}</strong> (${esc(item.type)}, ${esc(item.language)})</div></div>`;
    }
  }

  async function previewClone() {
    const itemId = $('#clone-item-select').value;
    const newName = ($('#clone-new-name').value || '').trim();
    if (!itemId || !newName || !currentScan) return;

    const item = allItems.find(i => i.id === itemId);
    const originalName = item ? item.name : '';

    setStatus('Previewing clone...');
    try {
      const res = await fetch('/api/tools/clone/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scan_id: currentScan.scan_id, item_ids: [itemId], original_name: originalName, new_name: newName }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || 'Clone preview failed');
      const data = await res.json();

      let html = '';
      (data.items || []).forEach(ci => {
        const variants = (ci.variants || []).map(v =>
          `<div class="flex items-center gap-2 py-0.5 text-xs"><span style="color: var(--text-muted)">${esc(v.original)}</span> <span style="color: var(--accent)">&rarr;</span> <span style="color: var(--success)">${esc(v.replacement)}</span></div>`
        ).join('');

        html += `<div class="pattern-card mb-3">
          <div class="text-sm font-medium mb-2" style="color: var(--text-primary)">${esc(ci.name)}</div>
          ${variants ? `<div class="mb-2"><div class="text-xs font-semibold mb-1" style="color: var(--text-secondary)">Case Variants</div>${variants}</div>` : ''}
          ${ci.preview ? `<div><div class="text-xs font-semibold mb-1" style="color: var(--text-secondary)">Preview</div><pre style="background: var(--canvas); border-radius: 0.375rem; padding: 0.5rem; overflow: auto; max-height: 200px;"><code class="text-xs">${esc(ci.preview)}</code></pre></div>` : ''}
        </div>`;
      });

      $('#clone-preview').innerHTML = html;
      $('#clone-preview').querySelectorAll('pre code').forEach(el => hljs.highlightElement(el));
      setStatus('Clone preview ready');
    } catch (err) {
      setStatus(`Clone preview error: ${err.message}`);
    }
  }

  async function executeClone() {
    const itemId = $('#clone-item-select').value;
    const newName = ($('#clone-new-name').value || '').trim();
    if (!itemId || !newName || !currentScan) return;

    const item = allItems.find(i => i.id === itemId);
    const originalName = item ? item.name : '';

    setStatus('Cloning...');
    showProgress();
    try {
      const res = await fetch('/api/tools/clone', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scan_id: currentScan.scan_id, item_ids: [itemId], original_name: originalName, new_name: newName }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || 'Clone failed');
      const data = await res.json();
      setStatus(`Cloned: ${data.files_created} files`);
      showDownload(data.download_url);
    } catch (err) {
      setStatus(`Clone error: ${err.message}`);
    }
    hideProgress();
  }

  // ═══════════════════════════════════════════════
  // TAB: BOILERPLATE
  // ═══════════════════════════════════════════════

  let boilerplateSelectedIds = new Set();
  let boilerplateTemplate = null;
  let boilerplateSelectedPattern = null;  // {directory, block_type} or null
  let boilerplateVariants = [];           // [{id, el}]
  let variantCounter = 0;
  let _syncTimer = null;

  function loadBoilerplate() {
    if (!currentScan) return;
    $('#boilerplate-empty').classList.add('hidden');
    $('#boilerplate-content').classList.remove('hidden');
    tabLoaded.boilerplate = true;

    const list = $('#boilerplate-item-list');
    list.innerHTML = allItems.map(i => {
      const checked = boilerplateSelectedIds.has(i.id) ? 'checked' : '';
      return `<label class="flex items-center gap-1.5 text-xs px-2 py-1 rounded cursor-pointer" style="color: var(--text-secondary); background: var(--glass-bg)">
        <input type="checkbox" class="bp-item-check" data-id="${esc(i.id)}" ${checked}> ${esc(i.name)}
      </label>`;
    }).join('');

    list.querySelectorAll('.bp-item-check').forEach(cb => {
      cb.addEventListener('change', () => {
        if (cb.checked) boilerplateSelectedIds.add(cb.dataset.id);
        else boilerplateSelectedIds.delete(cb.dataset.id);
      });
    });
  }

  function selectPattern(cardEl) {
    const dir = cardEl.dataset.dir;
    const type = cardEl.dataset.type;

    // Toggle selection
    if (boilerplateSelectedPattern &&
        boilerplateSelectedPattern.directory === dir &&
        boilerplateSelectedPattern.block_type === type) {
      // Deselect
      boilerplateSelectedPattern = null;
      cardEl.classList.remove('selected');
      // Re-fetch without filter
      detectBoilerplate();
      return;
    }

    // Deselect all, select this one
    $$('#boilerplate-patterns .pattern-card').forEach(c => c.classList.remove('selected'));
    cardEl.classList.add('selected');
    boilerplateSelectedPattern = { directory: dir, block_type: type };

    // Re-fetch with filter
    detectBoilerplate();
  }

  function renderTemplate(template) {
    boilerplateTemplate = template;
    const templateEl = $('#boilerplate-template');
    templateEl.classList.remove('hidden');

    const editor = $('#boilerplate-template-editor');
    editor.value = template.template_code || '';
    editor.removeEventListener('input', syncVariablesFromTemplate);
    editor.addEventListener('input', syncVariablesFromTemplate);

    // Render auto-detected variable inputs
    renderVariableInputs(template.variables || []);

    // Clear custom vars and variants
    $('#boilerplate-custom-vars').innerHTML = '';
    $('#boilerplate-variants').innerHTML = '';
    boilerplateVariants = [];
    variantCounter = 0;
    $('#boilerplate-generated').innerHTML = '';
  }

  function renderVariableInputs(vars) {
    const varsEl = $('#boilerplate-variables');
    varsEl.innerHTML = vars.length > 0
      ? `<div class="text-xs font-semibold mb-1" style="color: var(--text-secondary)">Template Variables</div>` +
        vars.map(v => `<div class="flex items-center gap-2 mb-1">
          <span class="text-xs" style="color: var(--text-muted); min-width: 100px">${esc(v.name)}</span>
          <input type="text" class="glass-input px-2 py-1 text-xs flex-1 bp-var-input" data-var="${esc(v.name)}" placeholder="${esc(v.example || v.name)}">
        </div>`).join('')
      : '';
  }

  function syncVariablesFromTemplate() {
    clearTimeout(_syncTimer);
    _syncTimer = setTimeout(() => {
      const editor = $('#boilerplate-template-editor');
      const text = editor.value;
      const found = new Set();
      const re = /\{\{(\w+)\}\}/g;
      let m;
      while ((m = re.exec(text)) !== null) found.add(m[1]);

      // Get existing auto-detected var names
      const autoVars = new Set();
      $$('#boilerplate-variables .bp-var-input').forEach(el => autoVars.add(el.dataset.var));

      // Get existing custom var names
      const customVars = new Set();
      $$('#boilerplate-custom-vars .bp-custom-var-name').forEach(el => customVars.add(el.value));

      // Add missing vars as custom var rows
      for (const name of found) {
        if (!autoVars.has(name) && !customVars.has(name)) {
          addCustomVariable(name);
        }
      }
    }, 300);
  }

  function addCustomVariable(prefillName) {
    const container = $('#boilerplate-custom-vars');
    // Add header if first custom var
    if (container.children.length === 0) {
      const hdr = document.createElement('div');
      hdr.className = 'text-xs font-semibold mb-1';
      hdr.style.color = 'var(--text-secondary)';
      hdr.textContent = 'Custom Variables';
      container.appendChild(hdr);
    }
    const row = document.createElement('div');
    row.className = 'bp-custom-var-row';
    row.innerHTML = `<input type="text" class="glass-input px-2 py-1 text-xs bp-custom-var-name" placeholder="name" style="width:100px" value="${esc(prefillName || '')}">
      <input type="text" class="glass-input px-2 py-1 text-xs flex-1 bp-custom-var-value" placeholder="value">
      <button class="bp-remove-btn" onclick="this.parentElement.remove()">&times;</button>`;
    container.appendChild(row);
  }

  function collectAllVariables() {
    const variables = {};
    // Auto-detected vars
    $$('#boilerplate-variables .bp-var-input').forEach(input => {
      variables[input.dataset.var] = input.value;
    });
    // Custom vars
    $$('#boilerplate-custom-vars .bp-custom-var-row').forEach(row => {
      const name = row.querySelector('.bp-custom-var-name');
      const value = row.querySelector('.bp-custom-var-value');
      if (name && name.value.trim()) {
        variables[name.value.trim()] = (value && value.value) || '';
      }
    });
    return variables;
  }

  function addVariant() {
    variantCounter++;
    const container = $('#boilerplate-variants');
    const varNames = Object.keys(collectAllVariables());
    if (varNames.length === 0) {
      setStatus('Add variables first before creating variants');
      return;
    }

    const setEl = document.createElement('div');
    setEl.className = 'bp-variant-set';
    setEl.dataset.variantId = variantCounter;
    setEl.innerHTML = `<div class="flex items-center justify-between mb-2">
        <span class="text-xs font-semibold" style="color: var(--text-secondary)">Variant ${variantCounter}</span>
        <button class="bp-remove-btn" data-vid="${variantCounter}">&times;</button>
      </div>` +
      varNames.map(n => `<div class="flex items-center gap-2 mb-1">
        <span class="text-xs" style="color: var(--text-muted); min-width: 100px">${esc(n)}</span>
        <input type="text" class="glass-input px-2 py-1 text-xs flex-1 bp-variant-var" data-var="${esc(n)}" placeholder="${esc(n)}">
      </div>`).join('');
    container.appendChild(setEl);

    setEl.querySelector('.bp-remove-btn').addEventListener('click', () => {
      setEl.remove();
      boilerplateVariants = boilerplateVariants.filter(v => v.id !== variantCounter);
    });

    boilerplateVariants.push({ id: variantCounter, el: setEl });
  }

  async function detectBoilerplate() {
    if (!currentScan) return;
    const ids = boilerplateSelectedIds.size > 0 ? [...boilerplateSelectedIds] : allItems.map(i => i.id);

    setStatus('Detecting boilerplate patterns...');
    try {
      const body = { scan_id: currentScan.scan_id, item_ids: ids, template_name: 'template' };
      if (boilerplateSelectedPattern) {
        body.pattern_filter = boilerplateSelectedPattern;
      }

      const res = await fetch('/api/tools/boilerplate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error((await res.json()).detail || 'Boilerplate detection failed');
      const data = await res.json();

      // Render pattern cards with data attrs and click handlers
      const patternsEl = $('#boilerplate-patterns');
      patternsEl.innerHTML = (data.patterns || []).map(p => `
        <div class="pattern-card" data-dir="${esc(p.directory)}" data-type="${esc(p.block_type)}">
          <div class="text-sm font-medium" style="color: var(--text-primary)">${esc(p.pattern_name)}</div>
          <div class="text-xs" style="color: var(--text-muted)">${p.count || 0} occurrences</div>
          ${(p.example_names || []).length > 0 ? `<div class="mt-1 text-xs" style="color: var(--text-secondary)">${p.example_names.map(i => esc(i)).join(', ')}</div>` : ''}
        </div>
      `).join('');

      // Attach click handlers and restore selection
      patternsEl.querySelectorAll('.pattern-card').forEach(card => {
        if (boilerplateSelectedPattern &&
            card.dataset.dir === boilerplateSelectedPattern.directory &&
            card.dataset.type === boilerplateSelectedPattern.block_type) {
          card.classList.add('selected');
        }
        card.addEventListener('click', () => selectPattern(card));
      });

      // Render template
      if (data.template) {
        renderTemplate(data.template);
      }

      setStatus(`Found ${(data.patterns || []).length} patterns`);
    } catch (err) {
      setStatus(`Boilerplate error: ${err.message}`);
    }
  }

  async function generateFromTemplate() {
    const editor = $('#boilerplate-template-editor');
    const templateCode = editor ? editor.value : '';
    if (!templateCode.trim()) return;

    const baseVars = collectAllVariables();

    // Collect variant variable sets
    const variantSets = [];
    $$('#boilerplate-variants .bp-variant-set').forEach(setEl => {
      const vars = {};
      setEl.querySelectorAll('.bp-variant-var').forEach(input => {
        vars[input.dataset.var] = input.value;
      });
      variantSets.push(vars);
    });

    setStatus('Generating from template...');
    try {
      if (variantSets.length > 0) {
        // Batch generate: base + variants
        const allSets = [baseVars, ...variantSets];
        const res = await fetch('/api/tools/boilerplate/generate-batch', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ template_code: templateCode, variable_sets: allSets }),
        });
        if (!res.ok) throw new Error((await res.json()).detail || 'Batch generation failed');
        const data = await res.json();
        renderGeneratedResults(data.generated_codes || [], templateCode);
      } else {
        // Single generate
        const res = await fetch('/api/tools/boilerplate/generate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ template_code: templateCode, variables: baseVars }),
        });
        if (!res.ok) throw new Error((await res.json()).detail || 'Generation failed');
        const data = await res.json();
        renderGeneratedResults([data.generated_code || ''], templateCode);
      }
      setStatus('Code generated from template');
    } catch (err) {
      setStatus(`Generate error: ${err.message}`);
    }
  }

  function renderGeneratedResults(results, templateCode) {
    const genEl = $('#boilerplate-generated');
    const ext = (boilerplateTemplate && boilerplateTemplate.config && boilerplateTemplate.config.language) || 'txt';

    let html = `<div class="text-xs font-semibold mb-2" style="color: var(--text-secondary)">Generated Code (${results.length} variant${results.length !== 1 ? 's' : ''})</div>`;

    results.forEach((code, i) => {
      const label = results.length > 1 ? `Variant ${i + 1}` : 'Output';
      html += `<div class="mb-3">
        <div class="flex items-center justify-between mb-1">
          <span class="text-xs" style="color: var(--text-muted)">${label}</span>
          <div class="bp-download-row">
            <button class="neon-btn-outlined neon-btn-cyan text-xs py-0.5 px-2" onclick="app.downloadVariant(${i})">Download</button>
          </div>
        </div>
        <pre style="background: var(--canvas); border-radius: 0.375rem; padding: 0.75rem; overflow: auto; max-height: 300px;"><code class="text-xs bp-gen-code">${esc(code)}</code></pre>
      </div>`;
    });

    if (results.length > 1) {
      html += `<div class="bp-download-row"><button class="neon-btn-filled neon-btn-green text-xs py-1" onclick="app.downloadAllGenerated()">Download All</button></div>`;
    }

    genEl.innerHTML = html;
    genEl.querySelectorAll('pre code').forEach(el => hljs.highlightElement(el));
    // Stash results for download
    genEl._results = results;
    genEl._ext = ext;
  }

  function downloadVariant(index) {
    const genEl = $('#boilerplate-generated');
    const results = genEl._results;
    const ext = genEl._ext || 'txt';
    if (!results || !results[index]) return;
    const blob = new Blob([results[index]], { type: 'text/plain' });
    downloadBlob(blob, `generated_${index + 1}.${ext}`);
  }

  function downloadAllGenerated() {
    const genEl = $('#boilerplate-generated');
    const results = genEl._results;
    const ext = genEl._ext || 'txt';
    if (!results || results.length === 0) return;
    const separator = `\n${'='.repeat(60)}\n`;
    const combined = results.map((c, i) => `// === Variant ${i + 1} ===\n${c}`).join(separator);
    const blob = new Blob([combined], { type: 'text/plain' });
    downloadBlob(blob, `generated_all.${ext}`);
  }

  // ═══════════════════════════════════════════════
  // TAB: MIGRATION
  // ═══════════════════════════════════════════════

  let migrationPatterns = [];

  function loadMigration() {
    if (!currentScan) return;
    $('#migration-empty').classList.add('hidden');
    $('#migration-content').classList.remove('hidden');
    tabLoaded.migration = true;
  }

  async function detectMigrations() {
    if (!currentScan) return;
    setStatus('Detecting migration patterns...');

    try {
      const res = await fetch('/api/tools/migration/detect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scan_id: currentScan.scan_id }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || 'Migration detection failed');
      const data = await res.json();
      migrationPatterns = data.patterns || [];

      const container = $('#migration-patterns');
      container.innerHTML = migrationPatterns.map(p => {
        const items = (p.items || []).map(item => {
          const conf = item.confidence || 0;
          const cls = conf >= 0.8 ? 'confidence-high' : conf >= 0.5 ? 'confidence-mid' : 'confidence-low';
          return `<div class="flex items-center justify-between py-1 text-xs" style="border-bottom: 1px solid var(--border-default)">
            <span style="color: var(--text-secondary)">${esc(item.name)}</span>
            <div class="flex items-center gap-2">
              <span class="confidence-badge ${cls}">${Math.round(conf * 100)}%</span>
              <button class="neon-btn-outlined neon-btn-cyan migration-apply-btn" style="font-size:0.625rem; padding: 2px 8px;" data-item-id="${esc(item.item_id)}" data-pattern-id="${esc(p.id)}">Apply</button>
            </div>
          </div>`;
        }).join('');

        return `<details class="pattern-card">
          <summary class="cursor-pointer flex items-center justify-between">
            <div>
              <div class="text-sm font-medium" style="color: var(--text-primary)">${esc(p.name)}</div>
              <div class="text-xs" style="color: var(--text-muted)">${esc(p.description || '')}</div>
            </div>
            <span class="text-xs" style="color: var(--text-secondary)">${(p.items || []).length} items</span>
          </summary>
          <div class="mt-2 pt-2" style="border-top: 1px solid var(--border-default)">${items}</div>
        </details>`;
      }).join('');

      container.querySelectorAll('.migration-apply-btn').forEach(btn => {
        btn.addEventListener('click', () => applyMigration(btn.dataset.itemId, btn.dataset.patternId));
      });

      setStatus(`Found ${migrationPatterns.length} migration patterns`);
    } catch (err) {
      setStatus(`Migration error: ${err.message}`);
    }
  }

  async function applyMigration(itemId, patternId) {
    if (!currentScan) return;
    setStatus('Applying migration...');

    try {
      const res = await fetch('/api/tools/migration/apply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scan_id: currentScan.scan_id, item_id: itemId, pattern_id: patternId }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || 'Migration apply failed');
      const data = await res.json();

      const previewEl = $('#migration-preview');
      previewEl.innerHTML = `<h3 class="text-sm font-semibold mb-2" style="color: var(--text-secondary)">Migration Result</h3>
        ${(data.changes || []).length > 0 ? `<div class="text-xs mb-2" style="color: var(--text-muted)">${data.changes.length} change${data.changes.length !== 1 ? 's' : ''} applied</div>` : ''}
        <div class="diff-side-by-side">
          <div>
            <div class="text-xs font-semibold mb-1" style="color: var(--error)">Before</div>
            <pre style="background: var(--canvas); border-radius: 0.375rem; padding: 0.5rem; overflow: auto; max-height: 300px;"><code class="text-xs">${esc(data.original || '')}</code></pre>
          </div>
          <div>
            <div class="text-xs font-semibold mb-1" style="color: var(--success)">After</div>
            <pre style="background: var(--canvas); border-radius: 0.375rem; padding: 0.5rem; overflow: auto; max-height: 300px;"><code class="text-xs">${esc(data.migrated || '')}</code></pre>
          </div>
        </div>`;
      previewEl.querySelectorAll('pre code').forEach(el => hljs.highlightElement(el));
      setStatus('Migration applied — review changes above');
    } catch (err) {
      setStatus(`Migration apply error: ${err.message}`);
    }
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
      boilerplateSelectedIds.clear();
      boilerplateTemplate = null;
      boilerplateSelectedPattern = null;
      boilerplateVariants = [];
      variantCounter = 0;
      migrationPatterns = [];
      remixCanvas = [];
      remixConflicts = [];
      remixResolutions = {};
      Object.keys(tabLoaded).forEach(k => delete tabLoaded[k]);

      $('#results-body').innerHTML = '';
      $('#results-table').classList.add('hidden');
      $('#empty-state').classList.remove('hidden');
      $('#scan-dir').textContent = '';
      $('#item-count').textContent = '0 items';
      $('#download-link').classList.add('hidden');
      hideProgress();

      const tabPanels = ['catalog', 'arch', 'health', 'docs', 'deadcode', 'tour', 'clone', 'boilerplate', 'migration', 'remix'];
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
  // REMIX BOARD
  // ═══════════════════════════════════════════════

  // Project color palette for visual distinction
  const REMIX_PROJECT_COLORS = [
    '#00f0ff', '#ff3366', '#a78bfa', '#00ff9d', '#ffb800',
    '#fb923c', '#38bdf8', '#f472b6', '#a3e635', '#e879f9',
  ];
  let _remixProjectColorMap = {};

  function _remixColor(projectName) {
    if (!_remixProjectColorMap[projectName]) {
      const idx = Object.keys(_remixProjectColorMap).length % REMIX_PROJECT_COLORS.length;
      _remixProjectColorMap[projectName] = REMIX_PROJECT_COLORS[idx];
    }
    return _remixProjectColorMap[projectName];
  }

  async function loadRemix() {
    try {
      const res = await fetch('/api/remix/palette');
      if (!res.ok) return;
      const data = await res.json();
      remixPalette = data.palette || [];

      const emptyEl = $('#remix-empty');
      const contentEl = $('#remix-content');

      if (remixPalette.length > 0) {
        if (emptyEl) emptyEl.classList.add('hidden');
        if (contentEl) contentEl.classList.remove('hidden');
        renderRemixPalette();
        renderRemixCanvas();
        initRemixDropZone();
        renderRemixTemplates();
      } else {
        if (emptyEl) emptyEl.classList.remove('hidden');
        if (contentEl) contentEl.classList.add('hidden');
      }
      tabLoaded['remix'] = true;
    } catch (_) { /* ignore */ }
  }

  function renderRemixPalette() {
    const el = $('#remix-palette');
    if (!el) return;

    if (remixPalette.length === 0) {
      el.innerHTML = '<div class="text-xs p-2" style="color:var(--text-muted)">No scans available</div>';
      return;
    }

    el.innerHTML = remixPalette.map(proj => {
      const color = _remixColor(proj.project_name);
      const items = proj.items.map(item => `
        <div class="remix-palette-item"
             draggable="true"
             data-scan-id="${esc(proj.scan_id)}"
             data-item-id="${esc(item.item_id)}"
             data-name="${esc(item.name)}"
             data-type="${esc(item.type)}"
             data-language="${esc(item.language)}"
             data-parent="${esc(item.parent || '')}"
             data-project="${esc(proj.project_name)}"
             data-type-references="${esc(JSON.stringify(item.type_references || []))}">
          <span style="${typeBadgeStyle(item.type)} font-size:0.5625rem; padding:0 0.25rem; border-radius:0.125rem">${esc(item.type)}</span>
          <span>${esc(item.name)}</span>
        </div>
      `).join('');

      return `
        <div class="remix-palette-project expanded">
          <div class="remix-palette-header" onclick="this.parentElement.classList.toggle('expanded')">
            <span><span class="remix-palette-chevron">&#x25BE;</span><span style="color:${color}; margin-right:4px">&#x25CF;</span>${esc(proj.project_name)}</span>
            <span style="color:var(--text-muted); font-size:0.625rem">${proj.items.length}</span>
          </div>
          <div class="remix-palette-items">${items}</div>
        </div>
      `;
    }).join('');

    // Attach drag listeners
    el.querySelectorAll('.remix-palette-item').forEach(item => {
      item.addEventListener('dragstart', onRemixDragStart);
      item.addEventListener('dragend', onRemixDragEnd);
    });
  }

  function initRemixDropZone() {
    const canvas = $('#remix-canvas');
    if (!canvas || canvas._remixInited) return;
    canvas._remixInited = true;

    canvas.addEventListener('dragover', (e) => {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'copy';
      canvas.classList.add('drag-over');
    });

    canvas.addEventListener('dragleave', (e) => {
      if (!canvas.contains(e.relatedTarget)) {
        canvas.classList.remove('drag-over');
      }
    });

    canvas.addEventListener('drop', (e) => {
      e.preventDefault();
      canvas.classList.remove('drag-over');
      try {
        const data = JSON.parse(e.dataTransfer.getData('application/json'));
        if (data && data.scan_id && data.item_id) {
          addToRemixCanvas(data);
        }
      } catch (_) { /* ignore bad drops */ }
    });
  }

  function onRemixDragStart(e) {
    const el = e.currentTarget;
    const data = {
      scan_id: el.dataset.scanId,
      item_id: el.dataset.itemId,
      name: el.dataset.name,
      type: el.dataset.type,
      language: el.dataset.language,
      parent: el.dataset.parent || '',
      project_name: el.dataset.project,
      type_references: JSON.parse(el.dataset.typeReferences || '[]'),
    };
    e.dataTransfer.setData('application/json', JSON.stringify(data));
    e.dataTransfer.effectAllowed = 'copy';
    el.classList.add('dragging');
  }

  function onRemixDragEnd(e) {
    e.currentTarget.classList.remove('dragging');
  }

  function addToRemixCanvas(data) {
    // Dedupe
    const exists = remixCanvas.some(c => c.scan_id === data.scan_id && c.item_id === data.item_id);
    if (exists) return;

    remixCanvas.push({
      scan_id: data.scan_id,
      item_id: data.item_id,
      name: data.name,
      type: data.type,
      language: data.language,
      parent: data.parent || '',
      project_name: data.project_name,
      type_references: data.type_references || [],
    });
    // Mark state as stale instead of nuking resolutions
    _remixStateDirty = true;
    // Only clear conflicts that the new item doesn't participate in
    const newName = data.name;
    const hasCollision = remixCanvas.filter(c => c.name === newName).length > 1;
    if (!hasCollision) {
      // No name collision — leave conflicts intact
    } else {
      remixConflicts = [];
    }
    remixScore = null;
    renderRemixCanvas();
    remixQuickValidate();
    remixSchedulePreview();
    // Show suggestions for container types
    if (REMIX_CONTAINER_TYPES.has(data.type)) {
      showRemixSuggestions(data);
    }
  }

  function removeFromRemixCanvas(scanId, itemId) {
    remixCanvas = remixCanvas.filter(c => !(c.scan_id === scanId && c.item_id === itemId));
    // Prune only resolutions belonging to the removed item
    const prefix = `${scanId}::${itemId}`;
    for (const key of Object.keys(remixResolutions)) {
      if (key.includes(prefix)) delete remixResolutions[key];
    }
    _remixStateDirty = true;
    remixScore = null;
    renderRemixCanvas();
    remixQuickValidate();
    remixSchedulePreview();
  }

  function remixClearCanvas() {
    remixCanvas = [];
    remixConflicts = [];
    remixResolutions = {};
    remixScore = null;
    _remixStateDirty = false;
    remixValidation = { errors: [], warnings: [], conflicts: [], is_buildable: true };
    remixPreviewData = null;
    _currentSuggestions = [];
    remixUnresolved = [];
    renderRemixCanvas();
    renderRemixValidationBar();
    const conflictsEl = $('#remix-conflicts');
    if (conflictsEl) conflictsEl.classList.add('hidden');
    const sugEl = $('#remix-suggestions');
    if (sugEl) sugEl.classList.add('hidden');
    const depsEl = $('#remix-deps-panel');
    if (depsEl) depsEl.classList.add('hidden');
    const previewEl = $('#remix-live-preview');
    if (previewEl) previewEl.innerHTML = '';
    // Clean up Gap 10 / Gap 13 UI
    const banner = $('#remix-unmatched-banner');
    if (banner) banner.remove();
    const bd = $('#remix-score-breakdown');
    if (bd) bd.remove();
    dismissRemixCardPopover();
  }

  function renderRemixCanvas() {
    const placeholder = $('#remix-canvas-placeholder');
    const grid = $('#remix-canvas-grid');
    const countEl = $('#remix-count');
    const buildBtn = $('#remix-build-btn');

    if (countEl) countEl.textContent = `${remixCanvas.length} item${remixCanvas.length !== 1 ? 's' : ''}`;
    if (buildBtn) buildBtn.disabled = remixCanvas.length === 0;

    if (remixCanvas.length === 0) {
      if (placeholder) {
        placeholder.classList.remove('hidden');
        placeholder.innerHTML = `
          <svg class="remix-empty-arrow" width="48" height="32" viewBox="0 0 48 32" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M46 16H4M4 16L16 4M4 16L16 28" stroke="var(--accent)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          <p>Drag items from the palette to start remixing</p>
        `;
      }
      if (grid) { grid.classList.add('hidden'); grid.innerHTML = ''; }
      return;
    }

    if (placeholder) placeholder.classList.add('hidden');
    if (!grid) return;
    grid.classList.remove('hidden');

    grid.innerHTML = remixCanvas.map(c => {
      const color = _remixColor(c.project_name);
      return `
        <div class="remix-card" onclick="app.showRemixPreview('${esc(c.scan_id)}', '${esc(c.item_id)}')">
          <button class="remix-card-remove" onclick="event.stopPropagation(); app.removeFromRemixCanvas('${esc(c.scan_id)}', '${esc(c.item_id)}')">&times;</button>
          <div class="flex items-center gap-1.5 mb-1">
            <span style="${typeBadgeStyle(c.type)} font-size:0.5625rem; padding:0.0625rem 0.375rem; border-radius:0.25rem">${esc(c.type)}</span>
            <span style="color:var(--text-muted); font-size:0.5625rem">${esc(c.language)}</span>
          </div>
          <div class="remix-card-name">${esc(c.name)}</div>
          <div class="remix-card-project" style="background:${color}15; color:${color}">${esc(c.project_name)}</div>
        </div>
      `;
    }).join('');
  }

  async function remixDetectConflicts() {
    if (remixCanvas.length === 0) return;
    setStatus('Checking conflicts...');

    try {
      const res = await fetch('/api/remix/detect-conflicts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          canvas_items: remixCanvas.map(c => ({ scan_id: c.scan_id, item_id: c.item_id })),
        }),
      });
      if (!res.ok) throw new Error('Conflict detection failed');
      const data = await res.json();
      remixConflicts = data.conflicts || [];
      renderRemixConflicts();
      setStatus(remixConflicts.length > 0
        ? `${remixConflicts.length} naming conflict(s) found`
        : 'No conflicts detected');
    } catch (err) {
      setStatus(`Error: ${err.message}`);
    }
  }

  function renderRemixConflicts() {
    const el = $('#remix-conflicts');
    if (!el) return;

    if (remixConflicts.length === 0) {
      el.classList.add('hidden');
      el.innerHTML = '';
      return;
    }

    el.classList.remove('hidden');
    el.innerHTML = `
      <div class="text-xs font-semibold mb-2" style="color: var(--warning)">
        &#x26A0; ${remixConflicts.length} Naming Conflict${remixConflicts.length > 1 ? 's' : ''} — rename to resolve
      </div>
      ${remixConflicts.map(conflict => conflict.items.map(item => `
        <div class="remix-conflict-row">
          <span class="conflict-name">${esc(conflict.name)}</span>
          <span class="conflict-project">${esc(item.project_name)}</span>
          <input type="text" class="glass-input px-2 py-1 text-xs"
            placeholder="New name..."
            value="${esc(conflict.name)}"
            data-composite-key="${esc(item.composite_key)}"
            oninput="app.onRemixConflictRename(this)">
        </div>
      `).join('')).join('')}
    `;
  }

  function onRemixConflictRename(input) {
    const key = input.dataset.compositeKey;
    const newName = input.value.trim();
    if (newName) {
      remixResolutions[key] = newName;
    } else {
      delete remixResolutions[key];
    }
    remixSchedulePreview();
  }

  // ── Remix validation ─────────────────────────────────────

  function remixQuickValidate() {
    const errors = [];
    const warnings = [];

    if (remixCanvas.length === 0) {
      remixValidation = { errors: [], warnings: [], conflicts: [], is_buildable: true };
      renderRemixValidationBar();
      return;
    }

    // Rule 1: Language coherence (exclude SQL items)
    const langGroups = {};
    for (const c of remixCanvas) {
      const group = REMIX_LANGUAGE_GROUPS[c.language] || c.language;
      if (group === 'sql') continue;
      (langGroups[group] = langGroups[group] || []).push(c.name);
    }
    const groupKeys = Object.keys(langGroups);
    if (groupKeys.length > 1) {
      errors.push({
        severity: 'error', rule: 'language_coherence',
        message: `Mixed language groups: ${groupKeys.join(', ')}. Items must share a compatible language.`,
        items: groupKeys,
      });
    }

    // Rule 2: Orphaned methods
    const namesOnCanvas = new Set(remixCanvas.map(c => c.name));
    for (const c of remixCanvas) {
      if (c.type === 'method' && c.parent && !namesOnCanvas.has(c.parent)) {
        warnings.push({
          severity: 'warning', rule: 'orphaned_method',
          message: `Method '${c.name}' needs parent class '${c.parent}' on canvas.`,
          items: [c.name],
        });
      }
    }

    // Rule 4: SQL isolation
    const hasSql = remixCanvas.some(c => REMIX_SQL_TYPES.has(c.type));
    const hasRuntime = remixCanvas.some(c => !REMIX_SQL_TYPES.has(c.type));
    if (hasSql && hasRuntime) {
      errors.push({
        severity: 'error', rule: 'sql_isolation',
        message: 'SQL blocks cannot mix with runtime code blocks.',
        items: [],
      });
    }

    remixValidation = { errors, warnings, conflicts: [], is_buildable: errors.length === 0 };
    renderRemixValidationBar();
  }

  function renderRemixValidationBar() {
    const bar = $('#remix-validation-bar');
    const details = $('#remix-validation-details');
    if (!bar) return;

    if (remixCanvas.length === 0) {
      bar.classList.add('hidden');
      if (details) details.classList.add('hidden');
      // Hide score breakdown
      const bd = $('#remix-score-breakdown');
      if (bd) bd.remove();
      return;
    }

    bar.classList.remove('hidden', 'validation-ok', 'validation-warn', 'validation-error');

    const { errors, warnings } = remixValidation;
    const buildBtn = $('#remix-build-btn');

    const staleBadge = (_remixStateDirty && (remixValidation.errors.length > 0 || remixValidation.warnings.length > 0 || remixScore))
      ? '<span class="remix-stale-badge">(stale — re-check)</span>'
      : '';

    // Score badge with tooltip breakdown (Gap 13)
    let scoreBadge = '';
    if (remixScore) {
      const bd = remixScore.breakdown || {};
      const tipParts = [];
      if (bd.language !== undefined) tipParts.push(`Language: ${bd.language}`);
      if (bd.deps !== undefined) tipParts.push(`Deps: ${bd.deps}`);
      if (bd.conflicts !== undefined) tipParts.push(`Conflicts: ${bd.conflicts}`);
      if (bd.orphans !== undefined) tipParts.push(`Orphans: ${bd.orphans}`);
      if (bd.cycles !== undefined) tipParts.push(`Cycles: ${bd.cycles}`);
      const tooltip = tipParts.join(' | ');
      scoreBadge = `<span class="remix-score-badge grade-${remixScore.grade.toLowerCase()}" title="${esc(tooltip)}" onclick="event.stopPropagation(); app.toggleRemixScoreBreakdown()">${remixScore.score} ${remixScore.grade}</span>`;
    }

    // Chevron indicator (Gap 3)
    const isExpanded = details && !details.classList.contains('hidden');
    const chevron = `<span class="remix-validation-chevron">${isExpanded ? '&#x25BE;' : '&#x25B8;'}</span>`;

    if (errors.length > 0) {
      bar.classList.add('validation-error');
      bar.innerHTML = `<span>&#x2718;</span> <span>${errors.length} error${errors.length > 1 ? 's' : ''} — build blocked</span>${staleBadge}${chevron}${scoreBadge}`;
      if (buildBtn) buildBtn.disabled = true;
    } else if (warnings.length > 0) {
      bar.classList.add('validation-warn');
      bar.innerHTML = `<span>&#x26A0;</span> <span>${warnings.length} warning${warnings.length > 1 ? 's' : ''} — build allowed</span>${staleBadge}${chevron}${scoreBadge}`;
      if (buildBtn) buildBtn.disabled = false;
    } else {
      bar.classList.add('validation-ok');
      bar.innerHTML = `<span>&#x2714;</span> <span>Compatible</span>${staleBadge}${chevron}${scoreBadge}`;
      if (buildBtn) buildBtn.disabled = false;
    }

    bar.onclick = () => toggleRemixValidationDetails();
  }

  function toggleRemixValidationDetails() {
    const details = $('#remix-validation-details');
    if (!details) return;

    if (!details.classList.contains('hidden')) {
      details.classList.add('hidden');
      return;
    }

    const allIssues = [...remixValidation.errors, ...remixValidation.warnings];
    if (allIssues.length === 0) {
      details.classList.add('hidden');
      return;
    }

    details.classList.remove('hidden');
    details.innerHTML = allIssues.map(issue => {
      const cls = issue.severity === 'error' ? 'validation-detail-error' : 'validation-detail-warn';
      const icon = issue.severity === 'error' ? '&#x2718;' : '&#x26A0;';
      return `<div class="validation-detail ${cls}"><span>${icon}</span> <span>${esc(issue.message)}</span></div>`;
    }).join('');
  }

  async function remixCheckCompatibility() {
    if (remixCanvas.length === 0) return;
    setStatus('Checking compatibility...');

    try {
      const res = await fetch('/api/remix/validate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          canvas_items: remixCanvas.map(c => ({ scan_id: c.scan_id, item_id: c.item_id })),
          full: true,
        }),
      });
      if (!res.ok) throw new Error('Compatibility check failed');
      const data = await res.json();
      remixValidation = {
        errors: data.errors || [],
        warnings: data.warnings || [],
        conflicts: data.conflicts || [],
        is_buildable: data.is_buildable,
      };

      // Capture compatibility score
      if (data.score !== undefined) {
        remixScore = { score: data.score, grade: data.grade, breakdown: data.score_breakdown };
      }
      _remixStateDirty = false;

      renderRemixValidationBar();

      // Also update conflicts panel for naming conflicts
      remixConflicts = data.conflicts || [];
      renderRemixConflicts();

      // Auto-trigger dep resolution
      remixResolveDeps();

      const total = (data.errors || []).length + (data.warnings || []).length;
      setStatus(total > 0
        ? `${total} issue${total > 1 ? 's' : ''} found`
        : 'All checks passed — compatible');
    } catch (err) {
      setStatus(`Error: ${err.message}`);
    }
  }

  async function remixBuild() {
    if (remixCanvas.length === 0) return;

    const projectName = ($('#remix-project-name') || {}).value || 'remix-package';
    const includeDeps = ($('#remix-include-deps') || {}).checked || false;

    setStatus('Building remix package...');
    showProgress();

    // Build resolutions array
    const resolutions = Object.entries(remixResolutions).map(([k, v]) => ({
      composite_key: k,
      new_name: v,
    }));

    try {
      const res = await fetch('/api/remix/build', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          canvas_items: remixCanvas.map(c => ({ scan_id: c.scan_id, item_id: c.item_id })),
          resolutions,
          project_name: projectName,
          include_deps: includeDeps,
        }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Build failed');
      }
      const data = await res.json();
      showDownload(data.download_url);
      setStatus(`Remix built — ${data.files_created} files`);
    } catch (err) {
      hideProgress();
      setStatus(`Error: ${err.message}`);
    }
  }

  async function showRemixPreview(scanId, itemId) {
    // Dismiss any existing popover
    dismissRemixCardPopover();

    try {
      const res = await fetch(`/api/preview/${encodeURIComponent(itemId)}?scan_id=${scanId}`);
      if (!res.ok) return;
      const data = await res.json();

      const item = remixCanvas.find(c => c.scan_id === scanId && c.item_id === itemId);
      const name = item ? item.name : itemId;
      const lang = item ? item.language : '';

      // Create floating popover
      const popover = document.createElement('div');
      popover.className = 'remix-card-popover';
      popover.id = 'remix-card-popover';
      popover.innerHTML = `
        <div class="remix-card-popover-header">
          <div class="flex items-center gap-1.5">
            <span class="font-medium text-sm" style="color: var(--text-primary)">${esc(name)}</span>
            ${lang ? `<span style="font-size:0.5625rem; padding:0.0625rem 0.375rem; border-radius:0.25rem; background:rgba(0,240,255,0.08); color:var(--accent)">${esc(lang)}</span>` : ''}
          </div>
          <button class="remix-card-popover-close" onclick="app.dismissRemixCardPopover()">&times;</button>
        </div>
        <pre><code class="text-xs language-${esc(lang)}">${esc(data.code || data.source || '')}</code></pre>
      `;

      // Position near center of canvas
      const canvas = $('#remix-canvas');
      if (canvas) {
        canvas.style.position = 'relative';
        popover.style.top = '1rem';
        popover.style.right = '1rem';
        canvas.appendChild(popover);
      } else {
        document.body.appendChild(popover);
      }

      // Syntax highlight
      const codeEl = popover.querySelector('pre code');
      if (codeEl && window.hljs) {
        try { hljs.highlightElement(codeEl); } catch (_) {}
      }

      // Click-outside-to-dismiss
      setTimeout(() => {
        document.addEventListener('click', _remixPopoverOutsideClick);
      }, 0);
    } catch (_) { /* ignore */ }
  }

  function _remixPopoverOutsideClick(e) {
    const popover = $('#remix-card-popover');
    if (popover && !popover.contains(e.target)) {
      dismissRemixCardPopover();
    }
  }

  function dismissRemixCardPopover() {
    const popover = $('#remix-card-popover');
    if (popover) popover.remove();
    document.removeEventListener('click', _remixPopoverOutsideClick);
  }

  // ── Smart Suggestions (F1) ─────────────────────────────────

  function computeRemixSuggestions(dropped) {
    const canvasNames = new Set(remixCanvas.map(c => `${c.scan_id}::${c.item_id}`));
    const canvasItemNames = new Set(remixCanvas.map(c => c.name));
    const suggestions = [];
    const seen = new Set();

    for (const proj of remixPalette) {
      for (const item of proj.items) {
        const key = `${proj.scan_id}::${item.item_id}`;
        if (canvasNames.has(key) || seen.has(key)) continue;

        let reason = '';
        // (a) Child methods of the dropped container
        if (item.parent === dropped.name) {
          reason = `method of ${dropped.name}`;
        }
        // (b) Items matching dropped.type_references
        else if (dropped.type_references && dropped.type_references.includes(item.name)) {
          reason = `referenced by ${dropped.name}`;
        }
        // (c) Items whose type_references include the dropped name
        else if ((item.type_references || []).includes(dropped.name)) {
          reason = `references ${dropped.name}`;
        }

        if (reason) {
          seen.add(key);
          suggestions.push({
            scan_id: proj.scan_id,
            item_id: item.item_id,
            name: item.name,
            type: item.type,
            language: item.language,
            parent: item.parent || '',
            project_name: proj.project_name,
            type_references: item.type_references || [],
            reason,
          });
        }
      }
    }
    return suggestions;
  }

  function showRemixSuggestions(dropped) {
    const suggestions = computeRemixSuggestions(dropped);
    _currentSuggestions = suggestions;
    const panel = $('#remix-suggestions');
    if (!panel || suggestions.length === 0) {
      if (panel) panel.classList.add('hidden');
      return;
    }

    panel.classList.remove('hidden');
    panel.innerHTML = `
      <div class="remix-suggestions-header">
        <span>&#x2728; ${suggestions.length} suggestion${suggestions.length > 1 ? 's' : ''} for ${esc(dropped.name)}</span>
        <div style="display:flex;gap:0.375rem">
          <button onclick="app.remixAddAllSuggestions()" class="remix-suggestion-add" style="font-size:0.625rem">Add All</button>
          <button onclick="app.remixDismissSuggestions()" class="remix-suggestion-add" style="font-size:0.625rem">Dismiss</button>
        </div>
      </div>
      <div class="remix-suggestions-list">
        ${suggestions.map((s, i) => `
          <div class="remix-suggestion-item">
            <span style="${typeBadgeStyle(s.type)} font-size:0.5rem; padding:0 0.25rem; border-radius:0.125rem">${esc(s.type)}</span>
            <span class="remix-suggestion-name">${esc(s.name)}</span>
            <span class="remix-suggestion-reason">${esc(s.reason)}</span>
            <button class="remix-suggestion-add" onclick="app.remixAddSuggestion('${esc(s.scan_id)}', '${esc(s.item_id)}')">+</button>
          </div>
        `).join('')}
      </div>
      <div class="remix-suggestion-countdown" id="remix-suggestion-countdown"></div>
    `;

    // Auto-dismiss after 30s with hover-pause
    if (_suggestionTimer) clearTimeout(_suggestionTimer);
    _suggestionTimer = setTimeout(() => remixDismissSuggestions(), 30000);

    panel.addEventListener('mouseenter', _pauseSuggestionCountdown);
    panel.addEventListener('mouseleave', _resumeSuggestionCountdown);
  }

  function _pauseSuggestionCountdown() {
    if (_suggestionTimer) { clearTimeout(_suggestionTimer); _suggestionTimer = null; }
    const bar = $('#remix-suggestion-countdown');
    if (bar) bar.classList.add('paused');
  }

  function _resumeSuggestionCountdown() {
    const bar = $('#remix-suggestion-countdown');
    if (bar) bar.classList.remove('paused');
    // Resume with remaining visible width as proportional time
    if (!_suggestionTimer) {
      _suggestionTimer = setTimeout(() => remixDismissSuggestions(), 15000);
    }
  }

  function remixAddSuggestion(scanId, itemId) {
    const sug = _currentSuggestions.find(s => s.scan_id === scanId && s.item_id === itemId);
    if (!sug) return;
    addToRemixCanvas(sug);
    _currentSuggestions = _currentSuggestions.filter(s => !(s.scan_id === scanId && s.item_id === itemId));
    if (_currentSuggestions.length === 0) {
      remixDismissSuggestions();
    } else {
      // Re-render remaining
      const panel = $('#remix-suggestions');
      if (panel) {
        const listEl = panel.querySelector('.remix-suggestions-list');
        if (listEl) {
          const el = listEl.querySelector(`button[onclick*="${itemId}"]`);
          if (el) el.closest('.remix-suggestion-item')?.remove();
        }
        const headerSpan = panel.querySelector('.remix-suggestions-header span');
        if (headerSpan) headerSpan.textContent = `\u2728 ${_currentSuggestions.length} suggestion${_currentSuggestions.length > 1 ? 's' : ''}`;
      }
    }
  }

  function remixAddAllSuggestions() {
    for (const sug of _currentSuggestions) {
      addToRemixCanvas(sug);
    }
    remixDismissSuggestions();
  }

  function remixDismissSuggestions() {
    _currentSuggestions = [];
    if (_suggestionTimer) { clearTimeout(_suggestionTimer); _suggestionTimer = null; }
    const panel = $('#remix-suggestions');
    if (panel) {
      panel.removeEventListener('mouseenter', _pauseSuggestionCountdown);
      panel.removeEventListener('mouseleave', _resumeSuggestionCountdown);
      panel.classList.add('hidden');
      panel.innerHTML = '';
    }
  }

  // ── Cross-Project Deps (F4) ────────────────────────────────

  async function remixResolveDeps() {
    if (remixCanvas.length === 0) return;

    try {
      const res = await fetch('/api/remix/resolve-deps', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          canvas_items: remixCanvas.map(c => ({ scan_id: c.scan_id, item_id: c.item_id })),
        }),
      });
      if (!res.ok) return;
      const data = await res.json();
      remixUnresolved = data;
      renderRemixDepsPanel(data);
    } catch (_) { /* ignore */ }
  }

  function renderRemixDepsPanel(data) {
    const panel = $('#remix-deps-panel');
    if (!panel) return;

    if (data.total_unresolved === 0) {
      panel.classList.add('hidden');
      panel.innerHTML = '';
      return;
    }

    panel.classList.remove('hidden');
    const resolvable = data.resolvable || [];
    const unresolvable = data.unresolvable || [];

    panel.innerHTML = `
      <div class="remix-deps-header">
        <span>${data.total_unresolved} unresolved dep${data.total_unresolved > 1 ? 's' : ''}</span>
        ${resolvable.length > 0 ? `<button onclick="app.remixAddAllResolvable()" class="remix-dep-add" style="font-size:0.625rem">Add All Resolvable</button>` : ''}
      </div>
      ${resolvable.map(d => `
        <div class="remix-dep-row">
          <span class="remix-dep-name">${esc(d.unresolved_ref)}</span>
          <span class="remix-dep-count">${d.candidates.length} candidate${d.candidates.length > 1 ? 's' : ''}</span>
          <button class="remix-dep-add" onclick="app.remixAddDep('${esc(d.candidates[0].scan_id)}', '${esc(d.candidates[0].item_id)}', '${esc(d.candidates[0].name)}', '${esc(d.candidates[0].type)}', '${esc(d.candidates[0].language)}', '${esc(d.candidates[0].project_name)}')">+</button>
        </div>
      `).join('')}
      ${unresolvable.map(d => `
        <div class="remix-dep-row">
          <span class="remix-dep-name remix-dep-unresolvable">${esc(d.unresolved_ref)}</span>
          <span class="remix-dep-count" style="color:var(--text-muted)">no candidates</span>
        </div>
      `).join('')}
    `;
  }

  function remixAddDep(scanId, itemId, name, type, language, projectName) {
    addToRemixCanvas({
      scan_id: scanId, item_id: itemId, name, type, language,
      parent: '', project_name: projectName, type_references: [],
    });
    // Re-run dep resolution
    remixResolveDeps();
  }

  function remixAddAllResolvable() {
    const data = remixUnresolved;
    if (!data || !data.resolvable) return;
    for (const d of data.resolvable) {
      if (d.candidates.length > 0) {
        const c = d.candidates[0];
        addToRemixCanvas({
          scan_id: c.scan_id, item_id: c.item_id, name: c.name, type: c.type,
          language: c.language, parent: c.parent || '', project_name: c.project_name,
          type_references: [],
        });
      }
    }
    remixResolveDeps();
  }

  // ── Remix Templates (F3) ──────────────────────────────────

  function remixGetTemplates() {
    try {
      return JSON.parse(localStorage.getItem(REMIX_TEMPLATES_KEY) || '[]');
    } catch (_) { return []; }
  }

  function remixSaveTemplate() {
    if (remixCanvas.length === 0) { setStatus('No items on canvas to save'); return; }
    const name = prompt('Template name:');
    if (!name) return;
    const description = prompt('Description (optional):') || '';
    const projectName = ($('#remix-project-name') || {}).value || 'remix-package';
    const includeDeps = ($('#remix-include-deps') || {}).checked || false;

    const template = {
      id: Date.now().toString(36) + Math.random().toString(36).slice(2, 6),
      name,
      description,
      created: new Date().toISOString(),
      project_name: projectName,
      include_deps: includeDeps,
      items: remixCanvas.map(c => ({
        name: c.name, type: c.type, language: c.language, parent: c.parent || null,
      })),
    };

    const templates = remixGetTemplates();
    templates.unshift(template);
    localStorage.setItem(REMIX_TEMPLATES_KEY, JSON.stringify(templates));
    renderRemixTemplates();
    setStatus(`Template "${name}" saved`);
  }

  async function remixLoadTemplate(id) {
    const templates = remixGetTemplates();
    const tmpl = templates.find(t => t.id === id);
    if (!tmpl) return;

    try {
      const res = await fetch('/api/remix/template/match', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ items: tmpl.items }),
      });
      if (!res.ok) throw new Error('Template match failed');
      const data = await res.json();

      // Clear canvas first
      remixCanvas = [];
      remixConflicts = [];
      remixResolutions = {};
      remixScore = null;

      let matched = 0;
      const unmatchedItems = [];
      for (const m of data.matches) {
        if (m.unmatched) {
          unmatchedItems.push(m);
          continue;
        }
        addToRemixCanvas({
          scan_id: m.scan_id, item_id: m.item_id, name: m.name,
          type: m.type, language: m.language, parent: m.parent || '',
          project_name: m.project_name, type_references: [],
        });
        matched++;
      }

      if ($('#remix-project-name')) $('#remix-project-name').value = tmpl.project_name || 'remix-package';
      if ($('#remix-include-deps')) $('#remix-include-deps').checked = tmpl.include_deps || false;

      // Gap 10: Show unmatched items banner
      if (unmatchedItems.length > 0) {
        showRemixUnmatchedBanner(unmatchedItems);
      }

      setStatus(`Template loaded — ${matched} matched, ${unmatchedItems.length} unmatched`);
    } catch (err) {
      setStatus(`Error: ${err.message}`);
    }
  }

  function remixDeleteTemplate(id) {
    if (!confirm('Delete this template?')) return;
    const templates = remixGetTemplates().filter(t => t.id !== id);
    localStorage.setItem(REMIX_TEMPLATES_KEY, JSON.stringify(templates));
    renderRemixTemplates();
  }

  function renderRemixTemplates() {
    const el = $('#remix-templates-list');
    if (!el) return;
    const templates = remixGetTemplates();

    if (templates.length === 0) {
      el.innerHTML = '<div class="text-xs p-1" style="color:var(--text-muted)">No saved templates</div>';
      return;
    }

    el.innerHTML = templates.map(t => `
      <div class="remix-template-item" onclick="app.remixLoadTemplate('${esc(t.id)}')">
        <div class="remix-template-info">
          <div class="remix-template-name">${esc(t.name)}</div>
          <div class="remix-template-meta">${t.items.length} items</div>
          ${t.description ? `<div class="remix-template-desc">${esc(t.description)}</div>` : ''}
        </div>
        <button class="remix-template-delete" onclick="event.stopPropagation(); app.remixDeleteTemplate('${esc(t.id)}')">&times;</button>
      </div>
    `).join('');
  }

  // ── Live Preview (F2) ──────────────────────────────────────

  function remixSchedulePreview() {
    if (_remixPreviewTimer) clearTimeout(_remixPreviewTimer);
    _remixPreviewTimer = setTimeout(() => remixLivePreview(), 600);
  }

  async function remixLivePreview() {
    const panel = $('#remix-live-preview');
    if (!panel || panel.classList.contains('hidden')) return;
    if (remixCanvas.length === 0) {
      panel.innerHTML = '<div class="text-xs p-3" style="color:var(--text-muted)">Add items to see preview</div>';
      remixPreviewData = null;
      return;
    }

    const resolutions = Object.entries(remixResolutions).map(([k, v]) => ({
      composite_key: k, new_name: v,
    }));
    const projectName = ($('#remix-project-name') || {}).value || 'remix-package';

    try {
      const res = await fetch('/api/remix/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          canvas_items: remixCanvas.map(c => ({ scan_id: c.scan_id, item_id: c.item_id })),
          resolutions,
          project_name: projectName,
        }),
      });
      if (!res.ok) return;
      remixPreviewData = await res.json();
      renderRemixLivePreview();
    } catch (_) { /* ignore */ }
  }

  function renderRemixLivePreview() {
    const panel = $('#remix-live-preview');
    if (!panel || !remixPreviewData) return;

    const files = remixPreviewData.files || [];
    panel.innerHTML = `
      <div class="flex items-center justify-between px-3 py-2" style="border-bottom: 1px solid var(--border-default)">
        <span class="font-medium text-sm" style="color: var(--text-primary)">${files.length} file${files.length !== 1 ? 's' : ''}</span>
        <button onclick="app.remixToggleLivePreview()" class="text-lg" style="color: var(--text-muted)">&times;</button>
      </div>
      <div class="remix-preview-tree">
        ${files.map((f, i) => `
          <div class="remix-preview-file" id="preview-file-${i}">
            <div class="remix-preview-file-header" onclick="document.getElementById('preview-file-${i}').classList.toggle('expanded')">
              <span class="remix-preview-chevron">&#x25B8;</span>
              <span class="remix-preview-file-path">${esc(f.path)}</span>
              <span style="font-size:0.5625rem;color:var(--text-muted);margin-left:auto">${esc(f.language)}</span>
            </div>
            <div class="remix-preview-file-code"><pre><code class="text-xs language-${esc(f.language)}">${esc(f.content)}</code></pre></div>
          </div>
        `).join('')}
      </div>
    `;

    // Syntax highlight
    panel.querySelectorAll('pre code').forEach(el => {
      try { hljs.highlightElement(el); } catch (_) {}
    });
  }

  function remixToggleLivePreview() {
    const panel = $('#remix-live-preview');
    const btn = $('#remix-preview-toggle');
    if (!panel) return;

    if (panel.classList.contains('hidden')) {
      panel.classList.remove('hidden');
      if (btn) btn.classList.add('active');
      remixLivePreview();
    } else {
      panel.classList.add('hidden');
      if (btn) btn.classList.remove('active');
    }
  }

  // ── Palette Search (Gap 9) ──────────────────────────────────

  function onRemixPaletteSearch(query) {
    const term = (query || '').toLowerCase().trim();
    const projects = $$('#remix-palette .remix-palette-project');
    projects.forEach(proj => {
      const items = proj.querySelectorAll('.remix-palette-item');
      let anyVisible = false;
      items.forEach(item => {
        const name = (item.dataset.name || '').toLowerCase();
        const type = (item.dataset.type || '').toLowerCase();
        const match = !term || name.includes(term) || type.includes(term);
        item.style.display = match ? '' : 'none';
        if (match) anyVisible = true;
      });
      proj.style.display = anyVisible ? '' : 'none';
    });
  }

  // ── Unmatched Banner (Gap 10) ──────────────────────────────

  function showRemixUnmatchedBanner(unmatchedItems) {
    // Remove existing banner
    const old = $('#remix-unmatched-banner');
    if (old) old.remove();

    const names = unmatchedItems.map(m => `${m.name || m.requested_name} (${m.type || '?'}, ${m.language || '?'})`).join(', ');
    const banner = document.createElement('div');
    banner.className = 'remix-unmatched-banner';
    banner.id = 'remix-unmatched-banner';
    banner.innerHTML = `
      <span>&#x26A0; Could not find: ${esc(names)}</span>
      <button onclick="this.parentElement.remove()">&times;</button>
    `;

    // Insert before canvas
    const canvas = $('#remix-canvas');
    if (canvas && canvas.parentElement) {
      canvas.parentElement.insertBefore(banner, canvas);
    }
  }

  // ── Score Breakdown Toggle (Gap 13) ────────────────────────

  function toggleRemixScoreBreakdown() {
    let bd = $('#remix-score-breakdown');
    if (bd) {
      bd.remove();
      return;
    }
    if (!remixScore || !remixScore.breakdown) return;

    const b = remixScore.breakdown;
    bd = document.createElement('div');
    bd.className = 'remix-score-breakdown';
    bd.id = 'remix-score-breakdown';

    const fields = [];
    if (b.language !== undefined) fields.push(`<span>Language: ${b.language}</span>`);
    if (b.deps !== undefined) fields.push(`<span>Deps: ${b.deps}</span>`);
    if (b.conflicts !== undefined) fields.push(`<span>Conflicts: ${b.conflicts}</span>`);
    if (b.orphans !== undefined) fields.push(`<span>Orphans: ${b.orphans}</span>`);
    if (b.cycles !== undefined) fields.push(`<span>Cycles: ${b.cycles}</span>`);
    bd.innerHTML = fields.join('');

    // Insert after validation details or validation bar
    const details = $('#remix-validation-details');
    const bar = $('#remix-validation-bar');
    const ref = (details && !details.classList.contains('hidden')) ? details : bar;
    if (ref && ref.parentElement) {
      ref.parentElement.insertBefore(bd, ref.nextSibling);
    }
  }

  // ═══════════════════════════════════════════════
  // AI CHAT
  // ═══════════════════════════════════════════════

  function loadAIChat() {
    // Restore saved API key
    const savedKey = localStorage.getItem(AI_KEY_STORAGE) || '';
    const keyInput = $('#ai-api-key');
    if (keyInput && savedKey) keyInput.value = savedKey;

    if (!currentScan) return;
    fetch(`/api/ai/history/${currentScan.scan_id}`)
      .then(r => r.json())
      .then(data => {
        aiChatHistory = data.history || [];
        _aiRenderHistory();
      })
      .catch(() => {});
  }

  function aiSaveKey() {
    const key = $('#ai-api-key')?.value || '';
    if (key) {
      localStorage.setItem(AI_KEY_STORAGE, key);
    } else {
      localStorage.removeItem(AI_KEY_STORAGE);
    }
  }

  function aiToggleKeyVisibility() {
    const input = $('#ai-api-key');
    if (!input) return;
    input.type = input.type === 'password' ? 'text' : 'password';
  }

  async function aiSendQuery() {
    const input = $('#ai-query-input');
    if (!input) return;
    const query = input.value.trim();
    if (!query || !currentScan || aiLoading) return;

    const model = $('#ai-model')?.value || 'deepseek-coder';
    const includeAnalysis = $('#ai-include-analysis')?.checked ?? true;
    const items = selectedIds.size > 0 ? [...selectedIds] : null;

    // Disable UI during request
    aiLoading = true;
    input.disabled = true;
    const sendBtn = $('#ai-send-btn');
    if (sendBtn) sendBtn.disabled = true;
    _aiSetStatus('Thinking...');

    // Show user message
    _aiAddMessage('user', query);
    input.value = '';
    input.style.height = 'auto';

    // Show typing indicator
    _aiShowTyping();

    try {
      const res = await fetch('/api/ai/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scan_id: currentScan.scan_id,
          query,
          item_ids: items,
          include_analysis: includeAnalysis,
          model,
          api_key: $('#ai-api-key')?.value || '',
        }),
      });

      if (res.status === 503) {
        const err = await res.json();
        _aiShowNoKeyMessage(err.detail || 'API key not configured');
        return;
      }
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Request failed' }));
        _aiAddMessage('error', err.detail || 'AI request failed');
        return;
      }

      const data = await res.json();
      _aiAddMessage('assistant', data.answer, {
        model: data.model,
        usage: data.usage,
      });

      aiChatHistory.push({ query, answer: data.answer, model: data.model });
    } catch (err) {
      _aiAddMessage('error', `Network error: ${err.message}`);
    } finally {
      _aiHideTyping();
      aiLoading = false;
      input.disabled = false;
      if (sendBtn) sendBtn.disabled = false;
      _aiSetStatus('');
      input.focus();
    }
  }

  function aiClearChat() {
    if (!currentScan) return;
    fetch(`/api/ai/history/${currentScan.scan_id}`, { method: 'DELETE' }).catch(() => {});
    aiChatHistory = [];
    const el = $('#ai-chat-messages');
    if (!el) return;
    const welcome = el.querySelector('.ai-welcome-message');
    el.innerHTML = '';
    if (welcome) el.appendChild(welcome);
    _aiSetStatus('');
  }

  function _aiAddMessage(role, content, meta = {}) {
    const el = $('#ai-chat-messages');
    if (!el) return;

    const cls = role === 'user' ? 'ai-message-user'
      : role === 'assistant' ? 'ai-message-assistant'
      : 'ai-message-error';
    const label = role === 'user' ? 'You' : role === 'assistant' ? 'AI' : 'Error';
    const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    const rendered = role === 'assistant' ? _aiRenderMarkdown(content) : esc(content);

    let footer = '';
    if (meta.usage) {
      const u = meta.usage;
      footer = `<div class="ai-message-footer">Tokens: ${u.prompt_tokens || 0} in / ${u.completion_tokens || 0} out</div>`;
    }

    const copyId = 'ai-msg-' + Math.random().toString(36).slice(2, 8);
    const copyBtn = role === 'assistant'
      ? `<button class="ai-msg-copy-btn" onclick="app.aiCopyMessage('${copyId}')" title="Copy response">Copy</button>`
      : '';

    const html = `<div class="ai-message ${cls}" id="${copyId}" data-raw-content="${esc(content).replace(/"/g, '&quot;')}">
      <div class="ai-message-header">
        <span class="ai-message-role">${label}</span>
        ${meta.model ? `<span class="ai-message-model">${esc(meta.model)}</span>` : ''}
        ${copyBtn}
        <span class="ai-message-time">${time}</span>
      </div>
      <div class="ai-message-content">${rendered}</div>
      ${footer}
    </div>`;

    el.insertAdjacentHTML('beforeend', html);
    el.scrollTop = el.scrollHeight;

    // Highlight code blocks
    setTimeout(() => {
      el.querySelectorAll('pre code').forEach(block => {
        if (window.hljs) hljs.highlightElement(block);
      });
    }, 50);
  }

  function _aiRenderHistory() {
    const el = $('#ai-chat-messages');
    if (!el) return;
    // Keep welcome message, clear rest
    const welcome = el.querySelector('.ai-welcome-message');
    el.innerHTML = '';
    if (welcome) el.appendChild(welcome);
    // Render stored history
    for (const entry of aiChatHistory) {
      _aiAddMessage('user', entry.query);
      _aiAddMessage('assistant', entry.answer, { model: entry.model });
    }
  }

  function _aiRenderMarkdown(text) {
    if (!text) return '';
    // Escape HTML first
    let s = esc(text);

    // Code blocks: ```lang\n...\n```  — with copy button
    s = s.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
      const id = 'ai-code-' + Math.random().toString(36).slice(2, 8);
      return `<div class="ai-code-block-wrap"><button class="ai-copy-btn" onclick="app.aiCopyCode('${id}')" title="Copy code">&#x2398;</button><pre id="${id}"><code class="language-${lang || 'text'}">${code}</code></pre></div>`;
    });

    // Inline code: `...`
    s = s.replace(/`([^`]+)`/g, '<code>$1</code>');
    // Bold: **...**
    s = s.replace(/\*\*(.+?)\*\*/g, '<strong style="color:var(--text-primary)">$1</strong>');
    // Headers: ## heading (must be at line start or after <br>)
    s = s.replace(/(^|<br>)#{3}\s+(.+?)(<br>|$)/g, '$1<div class="ai-md-h3">$2</div>$3');
    s = s.replace(/(^|<br>)#{2}\s+(.+?)(<br>|$)/g, '$1<div class="ai-md-h2">$2</div>$3');
    s = s.replace(/(^|<br>)#{1}\s+(.+?)(<br>|$)/g, '$1<div class="ai-md-h1">$2</div>$3');
    // Horizontal rule: --- or ***
    s = s.replace(/(^|<br>)([-*]{3,})(<br>|$)/g, '$1<hr class="ai-md-hr">$3');

    // Process lines for lists
    const lines = s.split('<br>');
    let out = [];
    let inUl = false, inOl = false;
    for (const line of lines) {
      const ulMatch = line.match(/^[-*]\s+(.+)/);
      const olMatch = line.match(/^\d+\.\s+(.+)/);
      if (ulMatch) {
        if (!inUl) { out.push('<ul class="ai-md-list">'); inUl = true; }
        out.push(`<li>${ulMatch[1]}</li>`);
        continue;
      } else if (inUl) { out.push('</ul>'); inUl = false; }
      if (olMatch) {
        if (!inOl) { out.push('<ol class="ai-md-list ai-md-ol">'); inOl = true; }
        out.push(`<li>${olMatch[1]}</li>`);
        continue;
      } else if (inOl) { out.push('</ol>'); inOl = false; }
      out.push(line);
    }
    if (inUl) out.push('</ul>');
    if (inOl) out.push('</ol>');

    // Rejoin — don't add <br> between list items or after headings
    s = out.join('<br>');
    s = s.replace(/<br>(<ul|<ol|<\/ul>|<\/ol>|<div class="ai-md-h)/g, '$1');
    s = s.replace(/(<\/ul>|<\/ol>|<\/div>)<br>/g, '$1');
    return s;
  }

  function aiCopyCode(id) {
    const el = document.getElementById(id);
    if (!el) return;
    const text = el.textContent;
    navigator.clipboard.writeText(text).then(() => {
      const btn = el.parentElement?.querySelector('.ai-copy-btn');
      if (btn) { btn.textContent = 'Copied!'; setTimeout(() => btn.innerHTML = '&#x2398;', 1500); }
    });
  }

  function aiCopyMessage(id) {
    const el = document.getElementById(id);
    if (!el) return;
    // Use raw content attribute to get original markdown text
    const raw = el.getAttribute('data-raw-content') || el.querySelector('.ai-message-content')?.textContent || '';
    // Decode HTML entities
    const txt = raw.replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"');
    navigator.clipboard.writeText(txt).then(() => {
      const btn = el.querySelector('.ai-msg-copy-btn');
      if (btn) { btn.textContent = 'Copied!'; setTimeout(() => btn.textContent = 'Copy', 1500); }
    });
  }

  function _aiShowNoKeyMessage(detail) {
    const el = $('#ai-chat-messages');
    if (!el) return;
    const html = `<div class="ai-no-key-message">
      <span style="font-size:1.25rem">&#x26A0;</span>
      <div>
        <div class="font-medium mb-1">${esc(detail)}</div>
        <div style="color:var(--text-secondary)">
          Run: <code>export DEEPSEEK_API_KEY="your-key-here"</code> then restart the server.
        </div>
      </div>
    </div>`;
    el.insertAdjacentHTML('beforeend', html);
    el.scrollTop = el.scrollHeight;
  }

  function _aiSetStatus(text) {
    const el = $('#ai-status');
    if (el) el.textContent = text;
  }

  function _aiShowTyping() {
    const el = $('#ai-chat-messages');
    if (!el) return;
    const indicator = document.createElement('div');
    indicator.id = 'ai-typing';
    indicator.className = 'ai-typing-indicator';
    indicator.innerHTML = '<span class="ai-typing-dot"></span><span class="ai-typing-dot"></span><span class="ai-typing-dot"></span>';
    el.appendChild(indicator);
    el.scrollTop = el.scrollHeight;
  }

  function _aiHideTyping() {
    const el = document.getElementById('ai-typing');
    if (el) el.remove();
  }

  // ═══════════════════════════════════════════════
  // AI COPILOT — Floating Widget + Agent
  // ═══════════════════════════════════════════════

  function toggleAIWidget() {
    const widget = $('#ai-widget');
    if (!widget) return;
    _aiWidgetVisible = !_aiWidgetVisible;
    widget.classList.toggle('hidden', !_aiWidgetVisible);

    // Update nav item active state
    const navItem = document.querySelector('.nav-item[data-tab="ai"]');
    if (navItem) navItem.classList.toggle('active', _aiWidgetVisible);

    if (_aiWidgetVisible) {
      // Restore saved key
      const savedKey = localStorage.getItem(AI_KEY_STORAGE) || '';
      const keyInput = $('#ai-api-key');
      if (keyInput && savedKey && !keyInput.value) keyInput.value = savedKey;
      // Focus input
      const input = $('#ai-agent-input');
      if (input) setTimeout(() => input.focus(), 100);
      // Init drag
      _initWidgetDrag();
    }
  }

  function aiWidgetCollapse() {
    const widget = $('#ai-widget');
    if (!widget) return;
    _aiWidgetCollapsed = !_aiWidgetCollapsed;
    widget.classList.toggle('collapsed', _aiWidgetCollapsed);
  }

  function aiWidgetSettings() {
    const panel = $('#ai-widget-settings');
    if (panel) panel.classList.toggle('visible');
  }

  // ── Draggable header ─────────────────────────
  let _widgetDragInited = false;
  function _initWidgetDrag() {
    if (_widgetDragInited) return;
    _widgetDragInited = true;
    const header = $('#ai-widget-header');
    const widget = $('#ai-widget');
    if (!header || !widget) return;

    let dragging = false, startX, startY, startLeft, startTop;

    header.addEventListener('mousedown', (e) => {
      if (e.target.closest('.ai-widget-header-btn')) return;
      dragging = true;
      const rect = widget.getBoundingClientRect();
      startX = e.clientX;
      startY = e.clientY;
      startLeft = rect.left;
      startTop = rect.top;
      widget.style.transition = 'none';
      e.preventDefault();
    });

    document.addEventListener('mousemove', (e) => {
      if (!dragging) return;
      const dx = e.clientX - startX;
      const dy = e.clientY - startY;
      const newLeft = Math.max(0, Math.min(window.innerWidth - 100, startLeft + dx));
      const newTop = Math.max(0, Math.min(window.innerHeight - 40, startTop + dy));
      widget.style.left = newLeft + 'px';
      widget.style.top = newTop + 'px';
      widget.style.right = 'auto';
      widget.style.bottom = 'auto';
    });

    document.addEventListener('mouseup', () => {
      if (dragging) {
        dragging = false;
        widget.style.transition = '';
      }
    });

    // Resize handle
    const resizeHandle = widget.querySelector('.ai-widget-resize');
    if (resizeHandle) {
      let resizing = false, resizeStartY, resizeStartH;
      resizeHandle.addEventListener('mousedown', (e) => {
        resizing = true;
        resizeStartY = e.clientY;
        resizeStartH = widget.offsetHeight;
        widget.style.transition = 'none';
        e.preventDefault();
        e.stopPropagation();
      });
      document.addEventListener('mousemove', (e) => {
        if (!resizing) return;
        const dy = resizeStartY - e.clientY;
        const newH = Math.max(200, Math.min(800, resizeStartH + dy));
        widget.style.height = newH + 'px';
        // Adjust top so it grows upward
        const rect = widget.getBoundingClientRect();
        widget.style.top = (rect.bottom - newH) + 'px';
        widget.style.bottom = 'auto';
      });
      document.addEventListener('mouseup', () => {
        if (resizing) {
          resizing = false;
          widget.style.transition = '';
        }
      });
    }
  }

  // ── Agent send ───────────────────────────────

  async function aiAgentSend() {
    const input = $('#ai-agent-input');
    if (!input) return;
    const query = input.value.trim();
    if (!query || !currentScan || aiAgentLoading) return;

    aiAgentLoading = true;
    input.disabled = true;
    const sendBtn = $('#ai-agent-send-btn');
    if (sendBtn) sendBtn.disabled = true;

    // Show user message
    _aiWidgetAddMessage('user', query);
    input.value = '';
    input.style.height = 'auto';

    // Show typing
    _aiWidgetShowTyping();

    try {
      const res = await fetch('/api/ai/agent', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scan_id: currentScan.scan_id,
          query,
          model: $('#ai-model')?.value || 'deepseek-coder',
          api_key: $('#ai-api-key')?.value || '',
        }),
      });

      _aiWidgetHideTyping();

      if (res.status === 503) {
        const err = await res.json();
        _aiWidgetAddMessage('error', err.detail || 'API key not configured. Open settings (gear icon) to add your DeepSeek API key.');
        return;
      }
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Request failed' }));
        _aiWidgetAddMessage('error', err.detail || 'Agent request failed');
        return;
      }

      const data = await res.json();

      // Render the answer
      _aiWidgetAddMessage('assistant', data.answer, {
        model: data.model,
        usage: data.usage,
      });

      // Play actions if any
      if (data.actions && data.actions.length > 0) {
        await _aiPlayActions(data.actions);
      }
    } catch (err) {
      _aiWidgetHideTyping();
      _aiWidgetAddMessage('error', `Network error: ${err.message}`);
    } finally {
      aiAgentLoading = false;
      input.disabled = false;
      if (sendBtn) sendBtn.disabled = false;
      input.focus();
    }
  }

  // ── Action executor ──────────────────────────

  async function _aiPlayActions(actions) {
    const bar = $('#ai-action-bar');
    const barText = $('#ai-action-text');
    if (bar) bar.classList.add('active');

    for (let i = 0; i < actions.length; i++) {
      const action = actions[i];
      const desc = _aiActionDescription(action);
      if (barText) barText.textContent = `Step ${i + 1}/${actions.length}: ${desc}`;
      _aiWidgetAddActionStep(desc);

      try {
        await _aiExecuteAction(action);
      } catch (e) {
        _aiWidgetAddActionStep(`Error: ${e.message}`);
      }

      // Delay between steps for visual feedback
      if (i < actions.length - 1) {
        await new Promise(r => setTimeout(r, 400));
      }
    }

    if (bar) bar.classList.remove('active');
    // Mark all step messages as done
    $$('.ai-action-step-msg:not(.done)').forEach(el => el.classList.add('done'));
  }

  function _aiActionDescription(action) {
    switch (action.type) {
      case 'navigate': return `Navigate to ${action.tab}`;
      case 'select': return `Select ${(action.item_names || []).join(', ')}`;
      case 'fill': return `Fill ${action.selector}`;
      case 'click': return `Run ${action.function}`;
      case 'remix_add': return `Add ${action.name} to remix`;
      case 'highlight': return `Highlight element`;
      default: return action.type;
    }
  }

  async function _aiExecuteAction(action) {
    switch (action.type) {
      case 'navigate':
        switchTab(action.tab);
        break;

      case 'select':
        if (action.item_ids) {
          action.item_ids.forEach(id => selectedIds.add(id));
          updateSelection();
          // Re-render scan list to show checkmarks
          if (typeof renderItems === 'function') renderItems();
        }
        break;

      case 'fill': {
        const el = document.querySelector(action.selector);
        if (!el) break;
        el.value = action.value || '';
        el.dispatchEvent(new Event('change', { bubbles: true }));
        el.dispatchEvent(new Event('input', { bubbles: true }));
        _aiFlashElement(el);
        break;
      }

      case 'click': {
        const fn = app[action.function];
        if (typeof fn === 'function') {
          const result = fn();
          if (result && typeof result.then === 'function') await result;
        }
        break;
      }

      case 'remix_add': {
        addToRemixCanvas({
          scan_id: action.scan_id,
          item_id: action.item_id,
          name: action.name,
          type: action.item_type || 'function',
          language: action.language || 'unknown',
          project_name: currentScan?.source_dir?.split('/').pop() || 'project',
        });
        break;
      }

      case 'highlight': {
        const el = action.selector ? document.querySelector(action.selector) : null;
        if (el) _aiFlashElement(el);
        break;
      }
    }
  }

  function _aiFlashElement(el) {
    if (!el) return;
    const original = el.style.boxShadow;
    el.style.boxShadow = '0 0 12px rgba(0, 240, 255, 0.6), inset 0 0 4px rgba(0, 240, 255, 0.15)';
    el.style.transition = 'box-shadow 0.3s ease';
    setTimeout(() => {
      el.style.boxShadow = original;
      setTimeout(() => el.style.transition = '', 300);
    }, 1500);
  }

  // ── Widget message rendering ─────────────────

  function _aiWidgetAddMessage(role, content, meta) {
    const container = $('#ai-widget-messages');
    if (!container) return;

    const msgId = 'ai-wm-' + Math.random().toString(36).slice(2, 8);
    const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    let roleLabel = role === 'user' ? 'You' : role === 'assistant' ? 'Copilot' : 'Error';
    let cssClass = `ai-message ai-message-${role === 'error' ? 'error' : role}`;

    let headerExtra = '';
    if (meta?.model) {
      headerExtra += `<span class="ai-message-model">${esc(meta.model)}</span>`;
    }

    const rendered = role === 'user' ? esc(content).replace(/\n/g, '<br>') : _aiRenderMarkdown(content);

    const html = `<div id="${msgId}" class="${cssClass}" data-raw-content="${esc(content)}">
      <div class="ai-message-header">
        <span class="ai-message-role">${roleLabel}</span>
        ${headerExtra}
        <span class="ai-message-time">${time}</span>
        ${role === 'assistant' ? `<button class="ai-msg-copy-btn" onclick="app.aiCopyMessage('${msgId}')">Copy</button>` : ''}
      </div>
      <div class="ai-message-content">${rendered}</div>
      ${meta?.usage ? `<div class="ai-message-footer">${meta.usage.total_tokens || 0} tokens</div>` : ''}
    </div>`;

    container.insertAdjacentHTML('beforeend', html);
    container.scrollTop = container.scrollHeight;
  }

  function _aiWidgetAddActionStep(desc) {
    const container = $('#ai-widget-messages');
    if (!container) return;
    const html = `<div class="ai-action-step-msg">&#x25B6; ${esc(desc)}</div>`;
    container.insertAdjacentHTML('beforeend', html);
    container.scrollTop = container.scrollHeight;
  }

  function _aiWidgetShowTyping() {
    const container = $('#ai-widget-messages');
    if (!container) return;
    const indicator = document.createElement('div');
    indicator.id = 'ai-widget-typing';
    indicator.className = 'ai-typing-indicator';
    indicator.innerHTML = '<span class="ai-typing-dot"></span><span class="ai-typing-dot"></span><span class="ai-typing-dot"></span>';
    container.appendChild(indicator);
    container.scrollTop = container.scrollHeight;
  }

  function _aiWidgetHideTyping() {
    const el = document.getElementById('ai-widget-typing');
    if (el) el.remove();
  }

  // ═══════════════════════════════════════════════
  // INIT
  // ═══════════════════════════════════════════════

  renderRecentScans();

  return {
    scan, applyFilters, toggleAll, closePreview, extract,
    switchTab, smartExtract, createPackage, showPreview,
    showPackagePopover, hidePackagePopover, confirmPackage,
    filterCatalog, exportCatalogHTML,
    setArchLayout, archFitView, archResetHighlight, exportArchPNG, archSearchNodes,
    toggleDocsWatch, exportDocsMarkdown,
    runDiff, loadDeadCode,
    goToTourStep, tourPrev, tourNext, exportTourMarkdown,
    onCloneItemChange, previewClone, executeClone,
    detectBoilerplate, generateFromTemplate,
    addCustomVariable, addVariant, downloadVariant, downloadAllGenerated,
    detectMigrations,
    removeFromRemixCanvas, remixDetectConflicts, remixCheckCompatibility,
    remixBuild, remixClearCanvas, onRemixConflictRename, showRemixPreview,
    dismissRemixCardPopover,
    // F1: Smart Suggestions
    remixAddSuggestion, remixAddAllSuggestions, remixDismissSuggestions,
    // F2: Live Preview
    remixToggleLivePreview,
    // F3: Templates
    remixSaveTemplate, remixLoadTemplate, remixDeleteTemplate,
    // F4: Cross-Project Deps
    remixResolveDeps, remixAddDep, remixAddAllResolvable,
    // UX Gap Fixes
    onRemixPaletteSearch, toggleRemixScoreBreakdown,
    // AI Chat (legacy)
    aiSendQuery, aiClearChat, aiSaveKey, aiToggleKeyVisibility,
    aiCopyCode, aiCopyMessage,
    // AI Copilot
    toggleAIWidget, aiWidgetCollapse, aiWidgetSettings, aiAgentSend,
  };
})();
