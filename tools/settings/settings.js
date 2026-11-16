// --- START OF FILE settings.js ---
/**
 * MetaForge Tool: Settings (hub)
 * v2 (2026-11-15): loads the panel engines (js/*.js), runs the tabs, and
 * provides the shared helpers they use: say() (visible status + announcer)
 * and confirm() (native modal <dialog>, never window.confirm).
 * The tabs are a focusgroup tablist (arrow keys between tabs, built into
 * WebView2): this file only keeps aria-selected / hidden in step and loads
 * nothing on tab change, because every panel is loaded once at start.
 */
window.metaforge = window.metaforge || {};
window.metaforge.settings = window.metaforge.settings || { booted: false, booting: null };

(function () {
    const S = window.metaforge.settings;

    S.boot = async function () {
        if (S.booted) return true;
        if (S.booting) return S.booting;
        S.booting = (async () => {
            const engines = ['theme_engine.js', 'theme_maker.js', 'toolbar_engine.js', 'dashboard_engine.js', 'taxonomy_engine.js',
                             'api_engine.js', 'update_engine.js', 'help_engine.js'];
            for (const engine of engines) {
                await new Promise((resolve) => {
                    const s = document.createElement('script');
                    s.src = `/tool_asset/settings/js/${engine}?v=${Date.now()}`;
                    s.onload = resolve;
                    s.onerror = () => { console.error(`Settings: couldn't load ${engine}`); resolve(); };
                    document.head.appendChild(s);
                });
            }
            S.booted = true;
            S.booting = null;
            return true;
        })();
        return S.booting;
    };

    /** Visible status line + screen-reader announcement. kind: '', 'ok', 'error', 'warning'. */
    S.say = function (statusId, message, kind = '') {
        const el = document.getElementById(statusId);
        if (el) {
            el.textContent = message;
            el.className = 'set-status' + (kind ? ` is-${kind}` : '');
        }
        if (message && window.MFAnnounce) window.MFAnnounce(message, { urgent: kind === 'error' });
    };

    /**
     * confirm({title, body: Node|string|Node[], ok, cancel}) -> Promise<boolean>.
     * Esc and Cancel both mean "no". Focus starts on Cancel (the safe choice)
     * and the browser returns it to whatever opened the dialog.
     */
    S.confirm = function ({ title, body, ok = 'OK', cancel = 'Cancel' }) {
        const dlg = document.getElementById('set-confirm');
        if (!dlg) return Promise.resolve(false);
        document.getElementById('set-confirm-title').textContent = title;
        const holder = document.getElementById('set-confirm-body');
        holder.replaceChildren(...[].concat(body).map(b => typeof b === 'string' ? Object.assign(document.createElement('p'), { textContent: b }) : b));
        document.getElementById('set-confirm-ok').textContent = ok;
        document.getElementById('set-confirm-cancel').textContent = cancel;
        dlg.returnValue = '';
        return new Promise((resolve) => {
            dlg.addEventListener('close', () => { const yes = dlg.returnValue === 'ok'; dlg.returnValue = ''; resolve(yes); }, { once: true });
            dlg.showModal();
        });
    };

    // --- TABS ---
    function tabs() { return Array.from(document.querySelectorAll('#set-tabs > button')); }
    function panelFor(tab) { return document.getElementById(tab.id.replace('set-tab-', 'set-panel-')); }

    S.selectTab = function (tab) {
        for (const t of tabs()) {
            const on = t === tab;
            t.setAttribute('aria-selected', on ? 'true' : 'false');
            t.toggleAttribute('focusgroupstart', on);
            const p = panelFor(t);
            if (on) p.removeAttribute('hidden'); else p.setAttribute('hidden', 'until-found');
        }
        document.getElementById('set-panels').scrollTop = 0;
    };

    function wireTabs() {
        const list = document.getElementById('set-tabs');
        if (!list || list.dataset.wired) return;
        list.dataset.wired = 'true';
        // Selection follows focus (arrow keys) and click.
        list.addEventListener('focusin', (e) => { if (e.target.matches('button')) S.selectTab(e.target); });
        list.addEventListener('click', (e) => { const b = e.target.closest('button'); if (b) S.selectTab(b); });
        // Find-in-page revealed a hidden panel: select its tab.
        for (const t of tabs()) panelFor(t).addEventListener('beforematch', () => S.selectTab(t));
    }

    // Called by the app (metaforge_core.js) every time Settings is opened;
    // this script itself is only loaded once.
    S.init = async function () {
        await S.boot();
        wireTabs();
        S.themes && S.themes.load();
        S.toolbar && S.toolbar.load();
        S.dashboard && S.dashboard.load();
        S.taxonomy && S.taxonomy.load();
        S.api && S.api.load();
        S.updates && S.updates.load();
        S.help && S.help.load();
    };
})();
// --- END OF FILE settings.js ---
