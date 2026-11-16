// --- START OF FILE fixer_editor.js ---
/**
 * MetaForge Studio: Database Tools - Remove records tab
 * v2 (2026-11-15). Find, choose one record, see exactly what goes (counts),
 * type "remove" to confirm. The server backs up first and never touches
 * music files (engines/fixer_engine.py, engines/identity_ops.py).
 */
window.metaforge = window.metaforge || {};
window.metaforge.database_tools = window.metaforge.database_tools || {};

(function () {
    const D = window.metaforge.database_tools;
    const R = D.remove = { items: new Map() };
    const GROUPS = [['artist', 'Artists'], ['album', 'Albums'], ['track', 'Tracks'], ['credit', 'Credits']];
    const ONE = { artist: 'artist', album: 'album', track: 'track', credit: 'credit' };

    R.wire = function () {
        D.$('dbt-rm-find').addEventListener('submit', (e) => { e.preventDefault(); R.find(); });
        D.$('dbt-rm-form').addEventListener('submit', (e) => { e.preventDefault(); R.remove(); });
    };

    R.find = async function () {
        const term = D.$('dbt-rm-q').value.trim();
        if (!term) return;
        const category = (document.querySelector('input[name="dbt-rm-cat"]:checked') || {}).value || 'all';
        D.say('dbt-rm-find-status', 'Searching…');
        D.say('dbt-rm-status', '');
        const r = await D.api('diagnose', { body: { term, category } });
        if (r.status !== 'success') { D.say('dbt-rm-find-status', r.message || "Couldn't search.", 'error'); return; }
        R.term = term;
        R.category = category;
        R.render(r.data || [], r.limit);
    };

    R.render = function (items, limit) {
        R.items = new Map(items.map((x, i) => [String(i), x]));
        const box = D.$('dbt-rm-results');
        if (!items.length) {
            D.$('dbt-rm-form').hidden = true;
            D.say('dbt-rm-find-status', `Nothing found for “${R.term}”.`, 'warning');
            return;
        }
        const sets = GROUPS.map(([kind, label]) => {
            const list = items.filter(x => x.kind === kind);
            if (!list.length) return null;
            const more = limit && list.length >= limit ? ` (first ${limit}: narrow the search to see more)` : '';
            return D.el('fieldset', { className: 'dbt-fieldset' },
                D.el('legend', {}, `${label}: ${list.length}${more}`),
                D.el('ul', {}, list.map(x => {
                    const idx = String(items.indexOf(x));
                    return D.el('li', {}, D.el('label', { className: 'dbt-radio' },
                        D.el('input', { type: 'radio', name: 'dbt-rm-pick', value: idx, required: true }),
                        D.el('span', {}, x.name, D.el('small', {}, x.detail))));
                })));
        });
        box.replaceChildren(...sets.filter(Boolean));
        D.$('dbt-rm-h').textContent = `Results for “${R.term}”`;
        D.$('dbt-rm-form').hidden = false;
        D.say('dbt-rm-find-status', `${items.length} record${items.length === 1 ? '' : 's'} found. Choose one to remove.`);
    };

    R.remove = async function () {
        const pick = document.querySelector('input[name="dbt-rm-pick"]:checked');
        if (!pick) { D.say('dbt-rm-status', 'Choose a record first.', 'warning'); return; }
        const x = R.items.get(pick.value);
        const body = { kind: x.kind, key: x.key };
        const r = await D.api('purge', { body });
        if (r.status !== 'confirm') { D.say('dbt-rm-status', r.message || "This record can't be removed.", 'error'); return; }
        const yes = await D.confirm({
            title: `Remove this ${ONE[x.kind]}?`,
            intro: `${x.name} (${x.detail}). Removing it deletes from the database:`,
            lines: D.previewLines(r),
            notes: [...(r.notes || []), 'Music files are not touched. A backup of the database is made first.'],
            ok: 'Remove', danger: true, typed: true
        });
        if (!yes) { D.say('dbt-rm-status', 'Nothing was removed.'); return; }
        const done = await D.api('purge', { body: { ...body, confirmed: true, typed: 'remove' } });
        if (done.status !== 'success') { D.say('dbt-rm-status', done.message || "Couldn't remove it.", 'error'); return; }
        const msg = `Removed ${x.name}. Backup: ${done.backup}`;
        await R.find();
        D.say(D.$('dbt-rm-form').hidden ? 'dbt-rm-find-status' : 'dbt-rm-status', msg, 'ok');
    };
})();
// --- END OF FILE fixer_editor.js ---
