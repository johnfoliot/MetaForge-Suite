// --- START OF FILE album_editor.js ---
/**
 * MetaForge Studio: Database Tools - Albums tab
 * v2 (2026-11-15). Search, edit details, tracks and credits; track
 * details dialog; credits from JSON.
 *  - Genre is only written when the user chooses one. An album whose
 *    tracks have different genres says so and offers "leave them as they
 *    are" (saving used to give every track the first track's genre).
 *  - A new title or album artist is previewed and confirmed first (the
 *    album's ID is a hash of both; engines/identity_ops.py re-keys it).
 *  - Per-track artists are shown only on compilations: on a single-artist
 *    album every track has the album's artist.
 */
window.metaforge = window.metaforge || {};
window.metaforge.database_tools = window.metaforge.database_tools || {};

(function () {
    const D = window.metaforge.database_tools;
    const B = D.album = { current: null, coverPath: null, taxonomy: null, moods: null };
    const KEEP = '__keep__';
    const KEYS = (() => {
        const notes = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];
        return notes.map(n => `${n}Maj`).concat(notes.map(n => `${n}Min`));
    })();
    let tracker;

    B.wire = function () {
        tracker = D.dirtyTracker('dbt-album', 'dbt-al-dirty', () => (B.current ? B.current.album_title : 'this album'));
        tracker.clean();
        D.$('dbt-album-find').addEventListener('submit', (e) => { e.preventDefault(); B.search(D.$('dbt-album-q').value); });
        D.$('dbt-album-matches').addEventListener('click', (e) => {
            const b = e.target.closest('button[data-id]');
            if (b) B.load(b.dataset.id);
        });
        const form = D.$('dbt-album-form');
        form.addEventListener('submit', (e) => { e.preventDefault(); B.save(); });
        form.addEventListener('input', () => tracker.mark());
        form.addEventListener('change', () => tracker.mark());
        D.$('dbt-al-genre').addEventListener('change', () => { B.fillSubs(D.$('dbt-al-sub'), D.$('dbt-al-genre').value, ''); B.genreHint(); });
        D.$('dbt-al-cover-btn').addEventListener('click', () => B.browseCover());
        D.$('dbt-al-cover').addEventListener('error', (e) => {
            if (!e.target.src.endsWith('/no-cover.png')) e.target.src = '/ui/images/no-cover.png';
        });
        D.$('dbt-al-add-credit').addEventListener('click', () => { const row = B.addCredit({}); tracker.mark(); row.querySelector('input').focus(); });
        D.$('dbt-al-credits').addEventListener('click', (e) => {
            const b = e.target.closest('button[data-remove]');
            if (!b) return;
            const row = b.closest('tr');
            const next = row.nextElementSibling || row.previousElementSibling;
            row.remove();
            B.renumberCredits();
            tracker.mark();
            (next ? next.querySelector('input') : D.$('dbt-al-add-credit')).focus();
            D.say('dbt-al-status', 'Credit removed from the list. Save changes to keep it that way.');
        });
        D.$('dbt-al-tracks').addEventListener('click', (e) => {
            const b = e.target.closest('button[data-path]');
            if (b) B.openTrack(b.dataset.path, b.dataset.title);
        });
        D.$('dbt-al-json-btn').addEventListener('click', () => {
            D.$('dbt-json-text').value = '';
            D.say('dbt-json-status', '');
            D.$('dbt-json').showModal();
        });
        D.$('dbt-json-form').addEventListener('submit', (e) => { e.preventDefault(); B.importJson(); });
        D.$('dbt-track-form').addEventListener('submit', (e) => { e.preventDefault(); B.saveTrack(); });
        D.$('dbt-tr-genre').addEventListener('change', () => B.fillSubs(D.$('dbt-tr-sub'), D.$('dbt-tr-genre').value, ''));
        D.$('dbt-tr-reanalyze').addEventListener('click', () => B.reanalyze());
    };

    B.loadTaxonomy = async function () {
        if (B.taxonomy) return;
        const r = await D.api('get_taxonomy');
        if (r.status === 'success') { B.taxonomy = r.taxonomy || {}; B.moods = r.moods || {}; }
        else B.taxonomy = {};
    };

    const opt = (value, text, selected) => D.el('option', { value, selected: !!selected }, text);

    B.fillSubs = function (select, genre, current) {
        const subs = (B.taxonomy && B.taxonomy[genre]) ? [...B.taxonomy[genre]].sort() : [];
        select.replaceChildren(opt('', subs.length ? 'Choose a sub-genre' : '(none)', !current), ...subs.map(s => opt(s, s, s === current)));
        select.disabled = !genre || genre === KEEP;
    };

    B.search = async function (q) {
        q = (q || '').trim();
        if (!q) return;
        D.$('dbt-album-matches-box').hidden = true;
        D.say('dbt-album-find-status', 'Searching…');
        const r = await D.api('search_album', { params: { album: q } });
        if (r.status === 'multiple') {
            D.say('dbt-album-find-status', `${r.candidates.length} albums match “${q}”.`);
            D.$('dbt-album-matches').replaceChildren(...r.candidates.map(c => D.el('li', {},
                D.el('button', { type: 'button', className: 'dbt-match', dataset: { id: c.mf_id } },
                    D.el('span', {}, c.album_title), D.el('small', {}, c.artist_name || 'Unknown artist')))));
            D.$('dbt-album-matches-box').hidden = false;
        } else if (r.status === 'success') {
            D.say('dbt-album-find-status', '');
            await B.load(r.album.mf_id);
        } else {
            D.say('dbt-album-find-status', r.message || 'No album found.', 'warning');
        }
    };

    B.load = async function (mfId, { force = false } = {}) {
        if (!force && tracker.dirty && !(B.current && B.current.mf_id === mfId) && !(await tracker.ask())) return;
        await B.loadTaxonomy();
        const r = await D.api('get_album_details', { params: { mf_id: mfId } });
        if (r.status !== 'success') { D.say('dbt-album-find-status', r.message || "That album couldn't be loaded.", 'error'); return; }
        D.$('dbt-album-matches-box').hidden = true;
        D.say('dbt-album-find-status', '');
        B.render(r.album);
    };

    B.render = function (a) {
        B.current = a;
        B.coverPath = null;
        D.$('dbt-album-form').hidden = false;
        D.$('dbt-album-h').textContent = a.album_title || 'Album';
        D.$('dbt-al-title').value = a.album_title || '';
        D.$('dbt-al-artist').value = a.artist_name || '';
        D.$('dbt-al-year').value = a.original_year || '';
        D.$('dbt-al-label').value = a.label || '';
        D.$('dbt-al-country').value = a.country || '';
        D.$('dbt-al-stamp').textContent = a.last_updated ? `Last updated ${a.last_updated}` : '';
        D.$('dbt-al-cover').src = `/ui/covers/${encodeURIComponent(a.mf_id)}.jpg?t=${Date.now()}`;
        D.$('dbt-al-cover-name').textContent = "The album folder's folder.jpg";

        // Genre: "leave as they are" when the tracks differ.
        const genres = Object.keys(B.taxonomy || {}).sort();
        const g = D.$('dbt-al-genre');
        g.replaceChildren(
            a.genre_mixed ? opt(KEEP, 'Tracks differ: leave them as they are', true) : opt('', a.genre ? '(not in the genre list)' : '(none)', !a.genre),
            ...genres.map(x => opt(x, x, !a.genre_mixed && x === a.genre)));
        if (!a.genre_mixed && a.genre && !genres.includes(a.genre)) g.prepend(opt(a.genre, a.genre, true));
        B.fillSubs(D.$('dbt-al-sub'), a.genre_mixed ? KEEP : a.genre, a.sub_genre || '');
        B.initialGenre = g.value;
        B.initialSub = D.$('dbt-al-sub').value;
        B.genreHint();

        // Tracks
        const comp = !!a.is_compilation;
        D.$('dbt-al-artist-col').hidden = !comp;
        D.$('dbt-al-tracks-hint').textContent = comp
            ? 'This is a compilation, so each track has its own artist.'
            : "Every track has the album artist. Change the album artist above to change them all.";
        const tracks = [...(a.tracks || [])].sort((x, y) => (x.file_path || '').localeCompare(y.file_path || '', undefined, { numeric: true }));
        D.$('dbt-al-tracks').replaceChildren(...(tracks.length ? tracks.map((t, i) => B.trackRow(t, i + 1, comp))
            : [D.el('tr', {}, D.el('td', { colSpan: 5, className: 'dbt-hint' }, 'This album has no tracks in the database.'))]));

        // Credits
        D.$('dbt-al-credits').replaceChildren();
        (a.personnel || []).forEach(p => B.addCredit({ id: p.id, name: p.name, role: p.role, scope: p.evidence_detail }));
        B.renumberCredits();

        D.$('dbt-al-problems').hidden = true;
        D.say('dbt-al-status', '');
        tracker.clean();
    };

    B.genreHint = function () {
        const v = D.$('dbt-al-genre').value;
        const mixed = B.current && B.current.genre_mixed;
        D.$('dbt-al-genre-hint').textContent = mixed
            ? (v === KEEP ? "This album's tracks have different genres; saving leaves each track's genre as it is. Choose a genre only if every track should have it."
                          : `Saving gives every track on this album the genre ${v}.`)
            : 'Changing the genre changes it for every track on this album.';
    };

    B.trackRow = function (t, n, comp) {
        const conf = Number(t.orig_year_conf || 0);
        const noteId = `dbt-al-yr-note-${n}`;
        const note = t.original_year
            ? `${t.orig_year_source || 'Unknown source'}, ${conf}% sure${conf < 50 ? ': worth checking' : ''}`
            : 'No original year yet';
        const title = t.title || `Track ${n}`;
        return D.el('tr', { dataset: { path: t.file_path || '' } },
            D.el('td', { className: 'dbt-num' }, String(n)),
            D.el('td', {}, D.el('input', { type: 'text', className: 'dbt-input dbt-tr-title', value: t.title || '', 'aria-label': `Title, track ${n}` })),
            comp ? D.el('td', {}, D.el('input', { type: 'text', className: 'dbt-input dbt-tr-artist', value: t.artist || '', 'aria-label': `Artist, track ${n}: ${title}` })) : null,
            D.el('td', {},
                D.el('input', { type: 'text', className: 'dbt-input dbt-tr-year', value: t.original_year || '', inputMode: 'numeric', maxLength: 4,
                                'aria-label': `Original year, track ${n}: ${title}`, 'aria-describedby': noteId }),
                D.el('span', { id: noteId, className: 'dbt-year-note' + (t.original_year && conf < 50 ? ' is-low' : '') }, note)),
            D.el('td', {}, D.el('button', { type: 'button', className: 'dbt-secondary', dataset: { path: t.file_path || '', title },
                                             'aria-label': `More details, track ${n}: ${title}` }, 'More…')));
    };

    B.addCredit = function ({ id, name = '', role = '', scope = '' }) {
        const row = D.el('tr', { dataset: id !== undefined && id !== null ? { edgeId: String(id) } : {} },
            D.el('td', {}, D.el('input', { type: 'text', className: 'dbt-input dbt-cr-name', value: name || '' })),
            D.el('td', {}, D.el('input', { type: 'text', className: 'dbt-input dbt-cr-role', value: role || '' })),
            D.el('td', {}, D.el('input', { type: 'text', className: 'dbt-input dbt-cr-scope', value: scope || '', size: 6 })),
            D.el('td', {}, D.el('button', { type: 'button', className: 'dbt-danger-outline', dataset: { remove: '1' } }, 'Remove')));
        D.$('dbt-al-credits').append(row);
        B.renumberCredits();
        return row;
    };

    // Each field's name says which credit it belongs to (row number + who).
    B.renumberCredits = function () {
        [...D.$('dbt-al-credits').rows].forEach((row, i) => {
            const n = i + 1;
            const who = row.querySelector('.dbt-cr-name').value || 'new credit';
            row.querySelector('.dbt-cr-name').setAttribute('aria-label', `Name, credit ${n}`);
            row.querySelector('.dbt-cr-role').setAttribute('aria-label', `Role, credit ${n}`);
            row.querySelector('.dbt-cr-scope').setAttribute('aria-label', `Tracks, credit ${n}`);
            row.querySelector('button[data-remove]').setAttribute('aria-label', `Remove credit ${n}: ${who}`);
        });
    };

    B.save = async function () {
        if (!B.current) return;
        const title = D.$('dbt-al-title').value.trim();
        const artist = D.$('dbt-al-artist').value.trim();
        for (const [id, v] of [['dbt-al-title', title], ['dbt-al-artist', artist]]) D.$(id).toggleAttribute('aria-invalid', !v);
        if (!title || !artist) {
            D.say('dbt-al-status', 'The album needs a title and an album artist.', 'error');
            D.$(!title ? 'dbt-al-title' : 'dbt-al-artist').focus();
            return;
        }
        const genre = D.$('dbt-al-genre').value;
        const sub = D.$('dbt-al-sub').value;
        const genreChanged = genre !== KEEP && (genre !== B.initialGenre || sub !== B.initialSub);
        const tracks = [...D.$('dbt-al-tracks').rows].filter(r => r.dataset.path).map(r => ({
            file_path: r.dataset.path,
            title: r.querySelector('.dbt-tr-title').value.trim(),
            artist: r.querySelector('.dbt-tr-artist') ? r.querySelector('.dbt-tr-artist').value.trim() : '',
            original_year: r.querySelector('.dbt-tr-year').value.trim()
        }));
        const personnel = [...D.$('dbt-al-credits').rows].map(r => ({
            id: r.dataset.edgeId ? parseInt(r.dataset.edgeId, 10) : null,
            name: r.querySelector('.dbt-cr-name').value.trim(),
            role: r.querySelector('.dbt-cr-role').value.trim(),
            track_scope: r.querySelector('.dbt-cr-scope').value.trim()
        })).filter(p => p.name && p.role);
        const body = {
            mf_id: B.current.mf_id, title, artist,
            year: D.$('dbt-al-year').value.trim(), label: D.$('dbt-al-label').value.trim(),
            country: D.$('dbt-al-country').value.trim().toUpperCase(),
            genre: genreChanged ? genre : '', sub_genre: genreChanged ? sub : '', genre_changed: genreChanged,
            cover_path: B.coverPath, tracks, personnel
        };
        D.say('dbt-al-status', 'Saving…');
        let r = await D.api('save_album', { body });
        if (r.status === 'confirm') {
            D.say('dbt-al-status', '');
            const what = [title !== B.current.album_title ? `title “${title}”` : '', artist !== B.current.artist_name ? `album artist “${artist}”` : ''].filter(Boolean).join(' and ');
            const yes = await D.confirm({ title: 'Save the new ' + (what.startsWith('title') && what.includes(' and ') ? 'title and artist?' : what.startsWith('title') ? 'title?' : 'album artist?'),
                intro: `The album gets the ${what}. This changes:`, lines: D.previewLines(r), notes: r.notes, ok: 'Save' });
            if (!yes) { D.say('dbt-al-status', 'Not saved. Your edits are still here.', 'warning'); return; }
            D.say('dbt-al-status', 'Saving…');
            r = await D.api('save_album', { body: { ...body, confirmed: true } });
        }
        if (r.status !== 'success') { D.say('dbt-al-status', r.message || "Couldn't save.", 'error'); return; }
        await B.load(r.mf_id || B.current.mf_id, { force: true });
        B.showProblems(r.problems || []);
    };

    B.showProblems = function (problems) {
        const ul = D.$('dbt-al-problems');
        ul.replaceChildren(...problems.slice(0, 20).map(p => D.el('li', {}, p)),
            problems.length > 20 ? D.el('li', {}, `…and ${problems.length - 20} more.`) : '');
        ul.hidden = !problems.length;
        D.say('dbt-al-status', problems.length
            ? `Saved, but ${problems.length} file${problems.length === 1 ? '' : 's'} couldn't be updated (listed below).`
            : 'Saved.', problems.length ? 'warning' : 'ok');
    };

    B.browseCover = async function () {
        try {
            const r = await (await fetch('/select_file')).json();
            if (!r.path) return;
            B.coverPath = r.path;
            D.$('dbt-al-cover-name').textContent = `New cover: ${r.path}`;
            tracker.mark();
        } catch (e) { D.say('dbt-al-status', "The file picker couldn't open.", 'error'); }
    };

    B.importJson = function () {
        let data;
        try { data = JSON.parse(D.$('dbt-json-text').value); }
        catch (e) { D.say('dbt-json-status', `That isn't valid JSON: ${e.message}`, 'error'); return; }
        if (!Array.isArray(data)) { D.say('dbt-json-status', 'Expected a list in square brackets: [ … ].', 'error'); return; }
        const good = data.filter(x => x && typeof x === 'object' && String(x.name || '').trim() && String(x.role || '').trim());
        if (!good.length) { D.say('dbt-json-status', 'No credits found: each needs a name and a role.', 'error'); return; }
        good.forEach(x => B.addCredit({ name: String(x.name).trim(), role: String(x.role).trim(), scope: String(x.track_scope || '').trim() }));
        tracker.mark();
        D.$('dbt-json').close();
        const skipped = data.length - good.length;
        D.say('dbt-al-status', `${good.length} credit${good.length === 1 ? '' : 's'} added to the list${skipped ? `; ${skipped} skipped (no name or role)` : ''}. Save changes to keep them.`);
    };

    // --- TRACK DETAILS DIALOG ---
    B.openTrack = async function (path, title) {
        await B.loadTaxonomy();
        const r = await D.api('get_track_detail', { params: { file_path: path } });
        if (r.status !== 'success') { D.say('dbt-al-status', r.message || "That track couldn't be loaded.", 'error'); return; }
        const t = r.track;
        B.trackPath = path;
        D.$('dbt-track-h').textContent = `Track details: ${title || t.title || ''}`;
        const fill = (id, list, cur, none = '(not set)') => {
            const sel = D.$(id);
            const items = [...list];
            if (cur && !items.includes(cur)) items.unshift(cur);
            sel.replaceChildren(opt('', none, !cur), ...items.map(x => opt(x, x, x === cur)));
        };
        const m = B.moods || {};
        fill('dbt-tr-genre', Object.keys(B.taxonomy || {}).sort(), t.genre);
        B.fillSubs(D.$('dbt-tr-sub'), t.genre || '', t.sub_genre || '');
        fill('dbt-tr-mood', m.anchors || [], t.mood);
        fill('dbt-tr-texture', (m.modifiers || {}).Sonic_Texture || [], t.sonic_texture);
        fill('dbt-tr-flavor', (m.modifiers || {}).Emotional_Flavor || [], t.emotional_flavor);
        fill('dbt-tr-key', KEYS, t.key_val);
        D.$('dbt-tr-bpm').value = t.bpm ?? '';
        D.$('dbt-tr-intensity').value = t.intensity ?? '';
        D.$('dbt-tr-mbtrack').value = t.mb_track_id || '';
        D.$('dbt-tr-mbrec').value = t.mb_recording_id || '';
        D.$('dbt-tr-mbwork').value = t.mb_work_id || '';
        D.$('dbt-tr-mbartist').value = t.mb_artist_id || '';
        D.$('dbt-tr-acoustid').value = t.acoustid || '';
        D.say('dbt-tr-status', '');
        D.say('dbt-tr-reanalyze-status', '');
        D.$('dbt-track').showModal();
        D.$('dbt-tr-genre').focus();
    };

    B.saveTrack = async function () {
        for (const [id, label, lo, hi] of [['dbt-tr-bpm', 'BPM', 1, 400], ['dbt-tr-intensity', 'Intensity', 1, 10]]) {
            const v = D.$(id).value.trim();
            const bad = v && !(/^\d+$/.test(v) && +v >= lo && +v <= hi);
            D.$(id).toggleAttribute('aria-invalid', !!bad);
            if (bad) { D.say('dbt-tr-status', `${label} must be a whole number from ${lo} to ${hi}, or blank.`, 'error'); D.$(id).focus(); return; }
        }
        const body = {
            file_path: B.trackPath,
            genre: D.$('dbt-tr-genre').value, sub_genre: D.$('dbt-tr-sub').value, mood: D.$('dbt-tr-mood').value,
            sonic_texture: D.$('dbt-tr-texture').value, emotional_flavor: D.$('dbt-tr-flavor').value,
            bpm: D.$('dbt-tr-bpm').value.trim(), key: D.$('dbt-tr-key').value, intensity: D.$('dbt-tr-intensity').value.trim(),
            mb_track_id: D.$('dbt-tr-mbtrack').value.trim(), mb_recording_id: D.$('dbt-tr-mbrec').value.trim(),
            mb_work_id: D.$('dbt-tr-mbwork').value.trim(), mb_artist_id: D.$('dbt-tr-mbartist').value.trim(),
            acoustid: D.$('dbt-tr-acoustid').value.trim()
        };
        D.say('dbt-tr-status', 'Saving…');
        const r = await D.api('save_track_detail', { body });
        if (r.status !== 'success') { D.say('dbt-tr-status', r.message || "Couldn't save.", 'error'); return; }
        D.$('dbt-track').close();
        const p = r.problems || [];
        D.say('dbt-al-status', p.length ? p[0] : 'Track details saved.', p.length ? 'warning' : 'ok');
    };

    B.reanalyze = async function () {
        const btn = D.$('dbt-tr-reanalyze');
        btn.disabled = true;
        D.say('dbt-tr-reanalyze-status', 'Measuring… this takes a few seconds.');
        try {
            const res = await fetch('/run_tool_logic/intelli-tagger/reanalyze_track', {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ file_path: B.trackPath })
            });
            const r = await res.json();
            if (r.status === 'success') {
                D.$('dbt-tr-bpm').value = r.bpm ?? '';
                D.$('dbt-tr-key').value = r.key || '';
                D.$('dbt-tr-intensity').value = r.intensity ?? '';
                D.say('dbt-tr-reanalyze-status', 'Measured and saved.', 'ok');
            } else {
                D.say('dbt-tr-reanalyze-status', `Couldn't measure: ${r.message || 'unknown error'}`, 'error');
            }
        } catch (e) {
            D.say('dbt-tr-reanalyze-status', "Couldn't measure: the server didn't answer.", 'error');
        } finally { btn.disabled = false; }
    };
})();
// --- END OF FILE album_editor.js ---
