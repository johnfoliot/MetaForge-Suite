// --- START OF FILE database_tools.js ---
/**
 * MetaForge Tool: Database Tools (hub)
 * v2 (2026-11-15): loads the three panel scripts, runs the tabs, and gives
 * them shared helpers: api() (server calls), say() (visible status line +
 * announcement), confirm() (native modal <dialog>; never alert/confirm),
 * el() (builds DOM from data with textContent, never HTML strings) and a
 * per-form unsaved-changes guard wired to MFLeaveGuard.
 * The .mfi is fetched fresh on every visit, so init() re-wires each time;
 * this script itself loads once.
 */
window.metaforge = window.metaforge || {};
window.metaforge.database_tools = window.metaforge.database_tools || { booted: false, booting: null };

(function () {
    const D = window.metaforge.database_tools;
    D.$ = (id) => document.getElementById(id);

    D.boot = async function () {
        if (D.booted) return true;
        if (D.booting) return D.booting;
        D.booting = (async () => {
            for (const path of ['artist/artist_editor.js', 'album/album_editor.js', 'fixer/fixer_editor.js']) {
                await new Promise((resolve) => {
                    const s = document.createElement('script');
                    s.src = `/tool_asset/database_tools/${path}?v=${Date.now()}`;
                    s.onload = resolve;
                    s.onerror = () => { console.error(`Database Tools: couldn't load ${path}`); resolve(); };
                    document.head.appendChild(s);
                });
            }
            D.booted = true;
            D.booting = null;
            return true;
        })();
        return D.booting;
    };

    /** Server call. GET with params, or POST with a JSON body. Never throws:
     *  a network or server failure comes back as {status:'error', message}. */
    D.api = async function (action, { params, body } = {}) {
        const qs = params ? '?' + new URLSearchParams(params) : '';
        try {
            const res = await fetch(`/run_tool_logic/database_tools/${action}${qs}`, body === undefined ? {} : {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
            });
            const data = await res.json().catch(() => ({}));
            if (!data.status) return { status: 'error', message: `The server answered ${res.status} with nothing usable.` };
            return data;
        } catch (e) {
            return { status: 'error', message: "Couldn't reach the MetaForge server." };
        }
    };

    /** Visible status line + screen-reader announcement. kind: '', 'ok', 'error', 'warning'. */
    D.say = function (statusId, message, kind = '') {
        const el = D.$(statusId);
        if (el) {
            el.textContent = message || '';
            el.className = 'dbt-status' + (kind ? ` is-${kind}` : '');
        }
        if (message && window.MFAnnounce) window.MFAnnounce(message, { urgent: kind === 'error' });
    };

    /** el('li', {className:'x', dataset:{id:1}}, 'text', childNode, ...) */
    D.el = function (tag, props = {}, ...kids) {
        const n = document.createElement(tag);
        for (const [k, v] of Object.entries(props)) {
            if (v === undefined || v === null || v === false) continue;
            if (k === 'dataset') Object.assign(n.dataset, v);
            else if (k in n && k !== 'list') n[k] = v;
            else n.setAttribute(k, v === true ? '' : v);
        }
        for (const kid of kids.flat()) if (kid !== null && kid !== undefined && kid !== false) n.append(kid);
        return n;
    };

    /**
     * confirm({title, lines, notes, ok, danger, typed}) -> Promise<boolean>.
     * lines: what will change (a list); notes: extra paragraphs. typed:true
     * asks for the word "remove" (removals). Esc and Cancel mean "no"; focus
     * starts on Cancel, or on the word field when there is one.
     */
    D.confirm = function ({ title, intro, lines = [], notes = [], ok = 'OK', danger = false, typed = false }) {
        const dlg = D.$('dbt-confirm');
        if (!dlg) return Promise.resolve(false);
        D.$('dbt-confirm-h').textContent = title;
        const body = D.$('dbt-confirm-body');
        body.replaceChildren(
            intro ? D.el('p', {}, intro) : '',
            lines.length ? D.el('ul', {}, lines.map(l => D.el('li', {}, l))) : '',
            ...notes.map(n => D.el('p', {}, n))
        );
        const okBtn = D.$('dbt-confirm-ok');
        okBtn.textContent = ok;
        okBtn.classList.toggle('mf-btn-danger', danger);
        const typedBox = D.$('dbt-confirm-typed-box');
        const typedIn = D.$('dbt-confirm-typed');
        typedBox.hidden = !typed;
        typedIn.value = '';
        typedIn.removeAttribute('aria-invalid');
        D.$('dbt-confirm-typed-err').textContent = '';
        typedIn.toggleAttribute('autofocus', typed);
        D.$('dbt-confirm-cancel').toggleAttribute('autofocus', !typed);
        dlg.returnValue = '';
        return new Promise((resolve) => {
            dlg.addEventListener('close', () => { const yes = dlg.returnValue === 'ok'; dlg.returnValue = ''; resolve(yes); }, { once: true });
            dlg.showModal();
        });
    };

    function wireConfirm() {
        const form = D.$('dbt-confirm-form');
        form.addEventListener('submit', (e) => {
            e.preventDefault();
            if (!D.$('dbt-confirm-typed-box').hidden) {
                const typedIn = D.$('dbt-confirm-typed');
                if (typedIn.value.trim().toLowerCase() !== 'remove') {
                    typedIn.setAttribute('aria-invalid', 'true');
                    D.$('dbt-confirm-typed-err').textContent = 'Type the word remove, or choose Cancel.';
                    typedIn.focus();
                    return;
                }
            }
            D.$('dbt-confirm').close('ok');
        });
        D.$('dbt-confirm-typed').addEventListener('input', (e) => {
            e.target.removeAttribute('aria-invalid');
            D.$('dbt-confirm-typed-err').textContent = '';
        });
    }

    /** Server "confirm" answer -> dialog lines. */
    D.previewLines = (r) => (r.summary && r.summary.length ? r.summary : ['Nothing else changes.']);

    /**
     * Unsaved-changes tracking for one editor form. markDirty() on edits,
     * clean() after load/save. Leaving the tool asks first (MFLeaveGuard);
     * so does loading another record over unsaved edits (askLeave()).
     */
    D.dirtyTracker = function (key, flagId, describe) {
        const t = {
            dirty: false,
            mark() {
                if (t.dirty) return;
                t.dirty = true;
                const f = D.$(flagId); if (f) f.hidden = false;
                if (window.MFLeaveGuard) window.MFLeaveGuard.set(key, () => t.ask());
            },
            clean() {
                t.dirty = false;
                const f = D.$(flagId); if (f) f.hidden = true;
                if (window.MFLeaveGuard) window.MFLeaveGuard.clear(key);
            },
            async ask() {
                if (!t.dirty) return true;
                const yes = await D.confirm({
                    title: 'Leave without saving?',
                    intro: `Your changes to ${describe()} aren't saved yet.`,
                    ok: 'Leave without saving'
                });
                if (yes) t.clean();
                return yes;
            }
        };
        return t;
    };

    // --- TABS ---
    const tabs = () => Array.from(document.querySelectorAll('#dbt-tabs > button'));
    const panelFor = (tab) => D.$(tab.id.replace('dbt-tab-', 'dbt-panel-'));

    D.selectTab = function (name) {
        const tab = typeof name === 'string' ? D.$(`dbt-tab-${name}`) : name;
        for (const t of tabs()) {
            const on = t === tab;
            t.setAttribute('aria-selected', on ? 'true' : 'false');
            t.toggleAttribute('focusgroupstart', on);
            const p = panelFor(t);
            if (on) p.removeAttribute('hidden'); else p.setAttribute('hidden', 'until-found');
        }
        D.$('dbt-panels').scrollTop = 0;
    };

    function wireTabs() {
        const list = D.$('dbt-tabs');
        list.addEventListener('focusin', (e) => { if (e.target.matches('button')) D.selectTab(e.target); });
        list.addEventListener('click', (e) => { const b = e.target.closest('button'); if (b) D.selectTab(b); });
        for (const t of tabs()) panelFor(t).addEventListener('beforematch', () => D.selectTab(t));
    }

    D.init = async function () {
        await D.boot();
        if (!D.$('dbt-tabs') || D.$('dbt-tabs').dataset.wired) return;
        D.$('dbt-tabs').dataset.wired = 'true';
        wireTabs();
        wireConfirm();
        D.artist && D.artist.wire();
        D.album && D.album.wire();
        D.remove && D.remove.wire();
    };
})();
// --- END OF FILE database_tools.js ---
