// --- START OF FILE taxonomy_engine.js ---
/**
 * Settings > Genre list. v2 (2026-11-15) rewrite. 1.x problems fixed:
 *  - names were interpolated into onclick strings and value="" (a genre
 *    with an apostrophe broke the page); now DOM-built.
 *  - every field was labelled "Edit name"; now each has its own label.
 *  - window.confirm() for deletes; no warning that tagged tracks are
 *    affected; blanks and duplicates could be saved. Now: track counts on
 *    screen, ONE review dialog at Save listing every change that touches
 *    tagged tracks, and blanks/duplicates are refused (server checks too).
 *  - unsaved edits were invisible; now "Unsaved changes" + Discard.
 * Model: genres = [{id, orig, name, subs: [{id, orig, name}]}]; orig is the
 * saved name (null for new items) so renames are known and counts (keyed by
 * the saved names in the database) still line up.
 */
(function () {
    const S = window.metaforge.settings;
    const SEP = '\u001f';
    let genres = [];
    let selectedId = null;
    let usage = { genres: {}, sub_genres: {} };
    let nextId = 1;
    let dirty = false;

    const $ = (id) => document.getElementById(id);
    const el = (tag, props = {}, ...kids) => { const n = Object.assign(document.createElement(tag), props); n.append(...kids); return n; };
    const tracks = (n) => n ? `${n.toLocaleString()} ${n === 1 ? 'track' : 'tracks'}` : 'not used yet';
    const genreCount = (g) => g.orig ? (usage.genres[g.orig] || 0) : 0;
    const subCount = (g, s) => (g.orig && s.orig) ? (usage.sub_genres[g.orig + SEP + s.orig] || 0) : 0;
    const selected = () => genres.find(g => g.id === selectedId) || null;

    function setDirty(on) {
        dirty = on;
        $('set-genres-dirty').hidden = !on;
    }

    function fromData(data) {
        genres = Object.keys(data).sort((a, b) => a.localeCompare(b)).map(name => ({
            id: nextId++, orig: name, name,
            subs: (data[name] || []).map(s => ({ id: nextId++, orig: s, name: s }))
        }));
    }

    S.taxonomy = {
        load: async function () {
            const form = $('set-genres-form');
            if (!form) return;
            this.wire();
            try {
                const [data, use] = await Promise.all([
                    fetch('/run_tool_logic/settings/get_taxonomy').then(r => r.json()),
                    fetch('/run_tool_logic/settings/taxonomy_usage').then(r => r.json()).catch(() => ({}))
                ]);
                if (data.status === 'error') throw new Error(data.message);
                if (use.status === 'success') usage = { genres: use.genres || {}, sub_genres: use.sub_genres || {} };
                fromData(data);
                selectedId = genres.length ? genres[0].id : null;
                setDirty(false);
                this.render();
            } catch (e) {
                S.say('set-genres-status', `The genre list couldn't be loaded: ${e.message}`, 'error');
            }
        },

        wire: function () {
            const form = $('set-genres-form');
            if (form.dataset.wired) return;
            form.dataset.wired = 'true';
            form.addEventListener('submit', (e) => { e.preventDefault(); this.save(); });
            $('set-add-genre-form').addEventListener('submit', (e) => { e.preventDefault(); this.addGenre(); });
            $('set-add-sub-form').addEventListener('submit', (e) => { e.preventDefault(); this.addSub(); });
            $('set-genres-discard').addEventListener('click', () => this.discard());

            $('set-genre-list').addEventListener('click', (e) => {
                const b = e.target.closest('.set-genre-btn');
                if (!b) return;
                selectedId = Number(b.dataset.id);
                this.renderList();
                this.renderEditor();
            });
            const col = $('set-sub-col');
            col.addEventListener('input', (e) => {
                const g = selected();
                if (!g) return;
                if (e.target.id === 'set-genre-name') {
                    g.name = e.target.value;
                    this.renderList();
                    $('set-sub-heading').textContent = g.name.trim() ? `Sub-genres of ${g.name.trim()}` : 'Sub-genres';
                } else if (e.target.dataset.sub) {
                    const s = g.subs.find(x => x.id === Number(e.target.dataset.sub));
                    if (s) s.name = e.target.value;
                }
                e.target.removeAttribute('aria-invalid');
                setDirty(true);
            });
            col.addEventListener('click', (e) => {
                const del = e.target.closest('[data-del-sub]');
                if (del) this.deleteSub(Number(del.dataset.delSub));
                else if (e.target.closest('#set-del-genre')) this.deleteGenre();
            });
        },

        render: function () { this.renderList(); this.renderEditor(); },

        renderList: function () {
            const list = $('set-genre-list');
            list.replaceChildren(...genres.map(g => {
                const n = genreCount(g);
                const btn = el('button', { type: 'button', className: 'set-genre-btn' },
                    el('span', { textContent: g.name.trim() || '(no name)' }),
                    g.orig ? el('span', { className: 'set-count', textContent: n ? n.toLocaleString() : '0' })
                           : el('span', { className: 'set-new-flag', textContent: 'new' }));
                btn.dataset.id = g.id;
                if (g.orig) btn.setAttribute('aria-description', tracks(n));
                if (g.id === selectedId) btn.setAttribute('aria-current', 'true');
                return el('li', {}, btn);
            }));
        },

        renderEditor: function () {
            const col = $('set-sub-col');
            const g = selected();
            if (!g) { col.replaceChildren(el('p', { className: 'set-hint', textContent: 'Choose a genre to see and edit its sub-genres.' })); return; }

            const nameField = el('div', { className: 'set-field' },
                el('label', { htmlFor: 'set-genre-name', textContent: 'Genre name' }),
                el('input', { type: 'text', className: 'set-input', id: 'set-genre-name', value: g.name, autocomplete: 'off' }),
                el('p', { className: 'set-hint', id: 'set-genre-name-hint', textContent: g.orig ? `Used by ${tracks(genreCount(g))}.` : 'New genre, not saved yet.' }));
            nameField.querySelector('input').setAttribute('aria-describedby', 'set-genre-name-hint');

            const heading = el('h3', { id: 'set-sub-heading', textContent: g.name.trim() ? `Sub-genres of ${g.name.trim()}` : 'Sub-genres' });
            const list = el('ul', { className: 'set-sub-list' });
            list.setAttribute('aria-labelledby', 'set-sub-heading');
            g.subs.forEach((s, i) => {
                const inputId = `set-sub-${s.id}`, countId = `set-sub-count-${s.id}`;
                const label = el('label', { htmlFor: inputId, className: 'mf-visually-hidden', textContent: `Sub-genre ${i + 1} name` });
                const input = el('input', { type: 'text', className: 'set-input', id: inputId, value: s.name, autocomplete: 'off' });
                input.dataset.sub = s.id;
                input.setAttribute('aria-describedby', countId);
                const count = el('span', { className: s.orig ? 'set-count' : 'set-new-flag', id: countId, textContent: s.orig ? tracks(subCount(g, s)) : 'new' });
                const del = el('button', { type: 'button', className: 'set-del-btn' }, 'Delete', el('span', { className: 'mf-visually-hidden', textContent: ` ${s.name.trim() || `sub-genre ${i + 1}`}` }));
                del.dataset.delSub = s.id;
                list.append(el('li', { className: 'set-sub-row' }, label, input, count, del));
            });
            const empty = g.subs.length ? null : el('p', { className: 'set-hint', textContent: 'No sub-genres yet.' });

            const add = el('div', { className: 'set-field' },
                el('label', { htmlFor: 'set-new-sub', textContent: 'New sub-genre' }),
                el('div', { className: 'set-add-row' },
                    Object.assign(el('input', { type: 'text', className: 'set-input', id: 'set-new-sub', autocomplete: 'off' }), {}),
                    el('button', { type: 'submit', textContent: 'Add sub-genre' })));
            add.querySelector('input').setAttribute('form', 'set-add-sub-form');
            add.querySelector('button').setAttribute('form', 'set-add-sub-form');

            const foot = el('div', { className: 'set-genre-foot' },
                el('button', { type: 'button', className: 'set-del-btn', id: 'set-del-genre', textContent: 'Delete this genre' }),
                el('p', { className: 'set-hint', textContent: 'Deletes it and its sub-genres from the list (not from any tracks).' }));

            col.replaceChildren(...[nameField, heading, list, empty, add, foot].filter(Boolean));
        },

        // --- edits (all in memory until Save) ---
        addGenre: function () {
            const input = $('set-new-genre');
            const name = input.value.trim();
            if (!name) { S.say('set-genres-status', 'Type a name for the new genre first.', 'error'); input.focus(); return; }
            if (genres.some(g => g.name.trim().toLowerCase() === name.toLowerCase())) {
                S.say('set-genres-status', `There's already a genre called “${name}”.`, 'error'); input.focus(); return;
            }
            const g = { id: nextId++, orig: null, name, subs: [] };
            genres.push(g);
            selectedId = g.id;
            input.value = '';
            setDirty(true);
            this.render();
            $('set-new-sub').focus();
            S.say('set-genres-status', `Added the genre ${name}. Now add its sub-genres. Not saved yet.`);
        },

        addSub: function () {
            const g = selected();
            const input = $('set-new-sub');
            if (!g || !input) return;
            const name = input.value.trim();
            if (!name) { S.say('set-genres-status', 'Type a name for the new sub-genre first.', 'error'); input.focus(); return; }
            if (g.subs.some(s => s.name.trim().toLowerCase() === name.toLowerCase())) {
                S.say('set-genres-status', `${g.name.trim()} already has a sub-genre called “${name}”.`, 'error'); input.focus(); return;
            }
            g.subs.push({ id: nextId++, orig: null, name });
            setDirty(true);
            this.renderEditor();
            $('set-new-sub').focus();
            S.say('set-genres-status', `Added ${name} to ${g.name.trim()}. Not saved yet.`);
        },

        deleteSub: function (id) {
            const g = selected();
            const i = g.subs.findIndex(s => s.id === id);
            if (i < 0) return;
            const [s] = g.subs.splice(i, 1);
            setDirty(true);
            this.renderEditor();
            const next = g.subs[i] || g.subs[i - 1];
            (next ? $(`set-sub-${next.id}`) : $('set-new-sub')).focus();
            S.say('set-genres-status', `Deleted ${s.name.trim() || 'the sub-genre'}. Not saved yet; Discard changes brings it back.`);
        },

        deleteGenre: function () {
            const i = genres.findIndex(g => g.id === selectedId);
            if (i < 0) return;
            const [g] = genres.splice(i, 1);
            const next = genres[i] || genres[i - 1];
            selectedId = next ? next.id : null;
            setDirty(true);
            this.render();
            const btn = next && document.querySelector(`.set-genre-btn[data-id="${next.id}"]`);
            (btn || $('set-new-genre')).focus();
            S.say('set-genres-status', `Deleted the genre ${g.name.trim() || ''}. Not saved yet; Discard changes brings it back.`);
        },

        discard: async function () {
            if (!dirty) { S.say('set-genres-status', 'There are no unsaved changes.'); return; }
            const yes = await S.confirm({ title: 'Discard your changes?', body: 'Every change since the genre list was last saved will be undone.', ok: 'Discard changes', cancel: 'Keep editing' });
            if (!yes) return;
            await this.load();
            S.say('set-genres-status', 'Changes discarded. The genre list is as it was last saved.');
        },

        // --- save ---
        problems: function () {
            const seen = new Map();
            for (const g of genres) {
                const n = g.name.trim();
                if (!n) return { msg: 'A genre has no name.', g, field: 'set-genre-name' };
                if (seen.has(n.toLowerCase())) return { msg: `The genre “${n}” is listed twice.`, g, field: 'set-genre-name' };
                seen.set(n.toLowerCase(), true);
                const subSeen = new Set();
                for (const s of g.subs) {
                    const sn = s.name.trim();
                    if (!sn) return { msg: `A sub-genre of ${n} has no name.`, g, field: `set-sub-${s.id}` };
                    if (subSeen.has(sn.toLowerCase())) return { msg: `${n} has “${sn}” twice.`, g, field: `set-sub-${s.id}` };
                    subSeen.add(sn.toLowerCase());
                }
            }
            return null;
        },

        impacts: function () {
            // Changes to names that tracks are already tagged with.
            const out = [];
            const kept = new Map(genres.filter(g => g.orig).map(g => [g.orig, g]));
            for (const orig of Object.keys(usage.genres)) {
                const n = usage.genres[orig];
                const g = kept.get(orig);
                if (!g && this.savedNames.has(orig)) out.push(`The genre ${orig} (${tracks(n)}) will be deleted.`);
                else if (g && g.name.trim() !== orig) out.push(`The genre ${orig} (${tracks(n)}) will be renamed ${g.name.trim()}.`);
            }
            for (const key of Object.keys(usage.sub_genres)) {
                const [gOrig, sOrig] = key.split(SEP);
                const g = kept.get(gOrig);
                if (!this.savedSubs.has(key) || !g) continue;   // not in the saved list, or its genre is going (reported above)
                const s = g.subs.find(x => x.orig === sOrig);
                const n = usage.sub_genres[key];
                if (!s) out.push(`The sub-genre ${sOrig} under ${gOrig} (${tracks(n)}) will be deleted.`);
                else if (s.name.trim() !== sOrig) out.push(`The sub-genre ${sOrig} under ${gOrig} (${tracks(n)}) will be renamed ${s.name.trim()}.`);
            }
            return out;
        },

        save: async function () {
            if (!dirty) { S.say('set-genres-status', 'There are no unsaved changes.'); return; }
            const p = this.problems();
            if (p) {
                selectedId = p.g.id;
                this.render();
                const f = $(p.field);
                if (f) { f.setAttribute('aria-invalid', 'true'); f.focus(); }
                S.say('set-genres-status', `${p.msg} Fix it, then save again.`, 'error');
                return;
            }
            const changes = this.impacts();
            if (changes.length) {
                const ul = el('ul', {}, ...changes.map(c => el('li', { textContent: c })));
                const yes = await S.confirm({
                    title: 'These changes affect tagged tracks',
                    body: [ul, 'Those tracks keep the tags they have now; nothing is retagged. Intelli-Tagger just won’t offer the old names any more.'],
                    ok: 'Save anyway', cancel: 'Go back'
                });
                if (!yes) return;
            }
            const out = {};
            for (const g of [...genres].sort((a, b) => a.name.trim().localeCompare(b.name.trim()))) {
                out[g.name.trim()] = g.subs.map(s => s.name.trim()).sort((a, b) => a.localeCompare(b));
            }
            S.say('set-genres-status', 'Saving the genre list…');
            try {
                const r = await (await fetch('/run_tool_logic/settings/save_taxonomy', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(out)
                })).json();
                if (r.status !== 'success') throw new Error(r.message || 'unknown error');
                const keepName = selected() ? selected().name.trim() : null;
                fromData(out);
                const again = genres.find(g => g.name === keepName);
                selectedId = again ? again.id : (genres[0] && genres[0].id);
                this.remember(out);
                setDirty(false);
                this.render();
                S.say('set-genres-status', `Saved. The previous list was backed up${r.backup ? ` as ${r.backup}` : ''}.`, 'ok');
            } catch (e) {
                S.say('set-genres-status', `The genre list wasn't saved: ${e.message}`, 'error');
            }
        },

        // Names in the last-saved file, so impacts() only reports real changes.
        savedNames: new Set(),
        savedSubs: new Set(),
        remember: function (data) {
            this.savedNames = new Set(Object.keys(data));
            this.savedSubs = new Set(Object.entries(data).flatMap(([g, subs]) => subs.map(s => g + SEP + s)));
        }
    };

    // Keep the saved-name sets in step with every load.
    const baseLoad = S.taxonomy.load;
    S.taxonomy.load = async function () {
        await baseLoad.call(this);
        const data = {};
        for (const g of genres) data[g.orig] = g.subs.map(s => s.orig);
        this.remember(data);
    };
})();
// --- END OF FILE taxonomy_engine.js ---
