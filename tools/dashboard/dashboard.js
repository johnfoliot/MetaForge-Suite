// --- START OF FILE dashboard.js ---
// MetaForge Tool: Dashboard (v2, 2026-11-16)
//
// The frame. Tiles are plug-ins in tools\dashboard\tiles\<id>\ (see
// dashboard.py). The frame asks which tiles exist and how they're laid out
// (Settings > Dashboard), loads each shown tile's tile.js (and tile.css if
// it has one), then lets each tile draw itself. A tile.js registers:
//
//   window.metaforge.dashboardTiles.<id> = {
//       render(t, data, kit)        t = { body, footer } of its <article>
//       detail(body, data, kit)     optional: fills the detail dialog
//       scanProgress(status, kit)   optional: called while the disk count runs
//   };
//
// `kit` (below) is everything a tile may use from the frame.
window.metaforge = window.metaforge || {};
window.metaforge.dashboardTiles = window.metaforge.dashboardTiles || {};

(function () {
    const API = '/run_tool_logic/dashboard/';
    const REG = window.metaforge.dashboardTiles;

    /** Small DOM builder: h('p', {class: 'x'}, 'text', child). Text is always text (no HTML). */
    function h(tag, props, ...kids) {
        const el = document.createElement(tag);
        for (const [k, v] of Object.entries(props || {})) {
            if (v === null || v === undefined || v === false) continue;
            if (k === 'class') el.className = v;
            else if (k === 'style') Object.entries(v).forEach(([p, val]) => el.style.setProperty(p, val));
            else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
            else if (k in el && typeof v !== 'string') el[k] = v;
            else el.setAttribute(k, v === true ? '' : v);
        }
        el.append(...kids.flat().filter((c) => c !== null && c !== undefined && c !== false));
        return el;
    }

    async function getJSON(url, opts) {
        const res = await fetch(url, opts);
        const data = await res.json().catch(() => ({ status: 'error', message: `The server answered ${res.status}.` }));
        if (data.status !== 'ok') throw new Error(data.message || 'Something went wrong.');
        return data;
    }

    /** Loads a tile's tile.js once (and its tile.css). Resolves when registered. */
    function loadTileFiles(m) {
        if (m.css && !document.getElementById(`db-css-${m.id}`)) {
            document.head.append(h('link', { rel: 'stylesheet', id: `db-css-${m.id}`, href: `/tool_asset/dashboard/tiles/${m.id}/tile.css?v=${Date.now()}` }));
        }
        if (REG[m.id]) return Promise.resolve();
        return new Promise((resolve) => {
            const s = h('script', { id: `db-js-${m.id}`, src: `/tool_asset/dashboard/tiles/${m.id}/tile.js?v=${Date.now()}` });
            s.onload = resolve;
            s.onerror = resolve;          // the tile shows its own error
            document.head.append(s);
        });
    }

    const D = {
        tiles: {},          // id -> tile.json (discovered)
        layout: [],
        scanTimer: null
    };

    // --- [ THE KIT: what tiles may use ] -------------------------------------
    const kit = {
        h,
        fmt: (n) => Number(n).toLocaleString(),
        day: (iso) => new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }),
        button: (text, onclick, quiet = false, extra = {}) =>
            h('button', { type: 'button', class: `mf-button-gold-fixed${quiet ? ' db-btn-quiet' : ''}`, onclick, ...extra }, text),
        /** Open another tool. */
        goTo: (toolId) => window.mfSwitchMode?.(toolId),
        /** Open (or refill) the detail dialog for a tile; extra = query args.
            Resolves with the data, or null on error. Changing args also reloads the tile. */
        openDetail: (id, extra) => D.openDetail(id, extra),
        closeDetail: () => document.getElementById('db-detail')?.close(),
        reloadTile: (id) => D.loadTile(id),
        scan: {
            start: () => D.startScan(),
            watch: () => D.watchScan()
        }
    };

    // --- [ FRAME ] -----------------------------------------------------------
    D.init = function () {
        if (!document.getElementById('db-tiles')) return;
        document.getElementById('db-refresh').addEventListener('click', () => D.refresh());
        D.load();
    };

    D.destroy = function () {
        clearTimeout(D.scanTimer);
        D.scanTimer = null;
    };

    D.load = async function () {
        const box = document.getElementById('db-tiles');
        try {
            const d = await getJSON(`${API}layout`);
            D.tiles = d.tiles;
            D.layout = d.layout;
        } catch (e) {
            box.replaceChildren(h('p', { class: 'db-error' }, `Error: the Dashboard couldn’t find its tiles. ${e.message}`));
            return;
        }
        D.render();
    };

    D.render = function () {
        const box = document.getElementById('db-tiles');
        if (!box) return;
        const shown = D.layout.filter((t) => t.shown && D.tiles[t.id]);
        if (!shown.length) {
            box.replaceChildren(h('p', { class: 'db-muted' }, 'No tiles are shown. Choose which tiles to show in Settings, under Dashboard.'));
            return;
        }
        box.replaceChildren(...shown.map((t) => h('article', {
            class: `db-tile${t.width > 1 ? ` db-w${t.width}` : ''}`, 'aria-labelledby': `db-t-${t.id}`, 'data-tile': t.id
        },
            h('h2', { id: `db-t-${t.id}` }, D.tiles[t.id].title),
            h('div', { class: 'db-body', 'aria-busy': 'true' }, h('p', { class: 'db-muted' }, 'Counting…')),
            h('footer', {}))));
        shown.forEach((t) => D.loadTile(t.id));
    };

    D.loadTile = async function (id) {
        const art = document.querySelector(`#db-tiles [data-tile="${id}"]`);
        if (!art) return;
        const body = art.querySelector('.db-body');
        const footer = art.querySelector('footer');
        body.setAttribute('aria-busy', 'true');
        try {
            await loadTileFiles(D.tiles[id]);
            if (!REG[id]) throw new Error('its script (tile.js) didn’t load.');
            const d = await getJSON(`${API}tile?id=${encodeURIComponent(id)}`);
            if (!art.isConnected) return;
            body.replaceChildren();
            footer.replaceChildren();
            REG[id].render({ body, footer }, d, kit);
        } catch (e) {
            if (!art.isConnected) return;
            body.replaceChildren(h('p', { class: 'db-error' }, `Error: this tile couldn’t load. ${e.message}`));
        } finally {
            body.removeAttribute('aria-busy');
        }
    };

    D.refresh = function () {
        D.load();
        document.getElementById('db-status').textContent =
            `Refreshed at ${new Date().toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}.`;
    };

    // --- [ DETAIL DIALOG ] ---------------------------------------------------
    D.openDetail = async function (id, extra) {
        const dlg = document.getElementById('db-detail');
        const body = document.getElementById('db-detail-body');
        if (!REG[id]?.detail) return null;
        document.getElementById('db-detail-h').textContent = D.tiles[id].title;
        body.replaceChildren(h('p', { class: 'db-muted' }, 'Counting…'));
        body.setAttribute('aria-busy', 'true');
        if (!dlg.open) dlg.showModal();
        const qs = extra ? '&' + new URLSearchParams(extra).toString() : '';
        try {
            const d = await getJSON(`${API}tile?id=${encodeURIComponent(id)}&detail=1${qs}`);
            body.replaceChildren();
            REG[id].detail(body, d, kit);
            body.scrollTop = 0;
            if (extra) D.loadTile(id);        // a setting changed: the tile follows
            return d;
        } catch (e) {
            body.replaceChildren(h('p', { class: 'db-error' }, `Error: ${e.message}`));
            return null;
        } finally {
            body.removeAttribute('aria-busy');
        }
    };

    // --- [ DISK COUNT (shared) ] ---------------------------------------------
    D.tellTiles = function (s) {
        Object.keys(REG).forEach((id) => REG[id].scanProgress?.(s, kit));
    };

    D.startScan = async function () {
        try {
            const s = await getJSON(`${API}scan`, { method: 'POST' });
            window.MFAnnounce?.('Counting files on disk. This takes several minutes; you can keep working.');
            D.tellTiles({ ...s, files: 0 });
            D.watchScan();
        } catch (e) {
            D.tellTiles({ running: false, error: e.message });
            window.MFAnnounce?.(`Error: ${e.message}`, { urgent: true });
        }
    };

    D.watchScan = function () {
        if (D.scanTimer) return;
        D.scanTimer = setTimeout(async () => {
            D.scanTimer = null;
            if (!document.getElementById('db-tiles')) return;
            let s;
            try { s = await getJSON(`${API}scan`); } catch (e) { return; }
            if (s.running) {
                D.tellTiles(s);
                D.watchScan();
            } else if (s.error) {
                D.tellTiles(s);
            } else {
                D.load();                       // every tile may use the new count
                window.MFAnnounce?.('Finished counting files on disk.');
            }
        }, 2000);
    };

    window.metaforge.dashboard = D;
})();
// --- END OF FILE dashboard.js ---
