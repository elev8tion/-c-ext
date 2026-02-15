/* code-extract web UI — vanilla JS */

const app = (() => {
  let currentScan = null;
  let allItems = [];
  let filteredItems = [];
  let selectedIds = new Set();
  let ws = null;

  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

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

  // --- Autocomplete ---
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

  // --- Scan ---
  async function scan() {
    const path = pathInput.value.trim();
    if (!path) return;

    setStatus('Scanning...');
    $('#scan-btn').disabled = true;
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
      setStatus(`Found ${data.count} items`);
      $('#scan-dir').textContent = data.source_dir;
    } catch (err) {
      setStatus(`Error: ${err.message}`);
    } finally {
      $('#scan-btn').disabled = false;
    }
  }

  // --- Filters ---
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

  // --- Render results ---
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

    // Group by file
    const byFile = {};
    filteredItems.forEach(item => {
      (byFile[item.file] = byFile[item.file] || []).push(item);
    });

    let html = '';
    for (const [file, items] of Object.entries(byFile)) {
      // File header
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

    // Event listeners
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

  // --- Selection ---
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
  }

  // --- Preview ---
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

  // --- Extract ---
  async function extract() {
    if (selectedIds.size === 0 || !currentScan) return;

    const progressBar = $('#progress-bar');
    const progressFill = $('#progress-fill');
    const progressText = $('#progress-text');
    const downloadLink = $('#download-link');

    progressBar.classList.remove('hidden');
    progressText.classList.remove('hidden');
    downloadLink.classList.add('hidden');

    // Try WebSocket first, fall back to HTTP
    const wsUrl = `ws://${location.host}/api/ws/progress`;
    try {
      ws = new WebSocket(wsUrl);
      ws.onmessage = (e) => {
        const msg = JSON.parse(e.data);
        if (msg.stage === 'done') {
          progressFill.style.width = '100%';
          progressText.textContent = `Done! ${msg.files_created} files`;
          downloadLink.href = msg.download_url;
          downloadLink.classList.remove('hidden');
          ws.close();
        } else if (msg.error) {
          progressText.textContent = `Error: ${msg.error}`;
        } else {
          const pct = msg.total > 0 ? Math.round((msg.current / msg.total) * 100) : 0;
          progressFill.style.width = `${pct}%`;
          progressText.textContent = `${msg.stage}: ${msg.current}/${msg.total}`;
        }
      };
      ws.onopen = () => {
        ws.send(JSON.stringify({
          action: 'extract',
          scan_id: currentScan.scan_id,
          item_ids: [...selectedIds],
        }));
      };
      ws.onerror = () => {
        // Fall back to HTTP
        extractHTTP();
      };
    } catch {
      extractHTTP();
    }
  }

  async function extractHTTP() {
    const progressFill = $('#progress-fill');
    const progressText = $('#progress-text');
    const downloadLink = $('#download-link');

    progressFill.style.width = '50%';
    progressText.textContent = 'Extracting...';

    try {
      const res = await fetch('/api/extract', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scan_id: currentScan.scan_id,
          item_ids: [...selectedIds],
        }),
      });
      if (!res.ok) throw new Error('Extract failed');
      const data = await res.json();
      progressFill.style.width = '100%';
      progressText.textContent = `Done! ${data.files_created} files`;
      downloadLink.href = data.download_url;
      downloadLink.classList.remove('hidden');
    } catch (err) {
      progressText.textContent = `Error: ${err.message}`;
    }
  }

  // --- Recent scans (localStorage) ---
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

  // --- Utility ---
  function setStatus(text) {
    $('#status-text').textContent = text;
  }

  // --- Init ---
  renderRecentScans();

  return { scan, applyFilters, toggleAll, closePreview, extract };
})();
