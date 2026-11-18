// --- START OF FILE artist_editor.js ---
/**
 * MetaForge Studio: Database Tools - Artists tab
 * v2 (2026-11-15). Search, edit, rename (carried through), merge.
 * A new name is previewed (counts of albums, tracks, credits and files)
 * and confirmed before the server applies it; see engines/identity_ops.py.
 */
window.metaforge = window.metaforge || {};
window.metaforge.database_tools = window.metaforge.database_tools || {};

(function () {
    const D = window.metaforge.database_tools;
    const A = D.artist = { current: null, mergeOther: null };
    let tracker;

    A.wire = function () {
        tracker = D.dirtyTracker('dbt-artist', 'dbt-art-dirty', () => (A.current ? A.current.artist_name : 'this artist'));
        tracker.clean();
        D.$('dbt-artist-find').addEventListener('submit', (e) => { e.preventDefault(); A.search(D.$('dbt-artist-q').value); });
        D.$('dbt-artist-matches').addEventListener('click', (e) => {
            const b = e.target.closest('button[data-id]');
            if (b) A.load(b.dataset.id);
        });
        const form = D.$('dbt-artist-form');
        form.addEventListener('submit', (e) => { e.preventDefault(); A.save(); });
        form.addEventListener('input', () => tracker.mark());
        D.$('dbt-art-photo-btn').addEventListener('click', () => A.browsePhoto());
        D.$('dbt-art-bio-btn').addEventListener('click', () => A.openBioBuilder());
        D.$('dbt-art-merge-btn').addEventListener('click', () => A.openMerge());
        D.$('dbt-art-albums').addEventListener('click', (e) => {
            const b = e.target.closest('button[data-id]');
            if (b && D.album) { D.selectTab('album'); D.album.load(b.dataset.id); }
        });
        D.$('dbt-art-img').addEventListener('error', (e) => {
            if (!e.target.src.endsWith('/no-photo.png')) e.target.src = '/ui/images/no-photo.png';
        });
        D.$('dbt-merge-find').addEventListener('submit', (e) => { e.preventDefault(); A.mergeSearch(); });
        D.$('dbt-merge-form').addEventListener('submit', (e) => { e.preventDefault(); A.mergePreview(); });
        D.$('dbt-merge-pick').addEventListener('change', () => A.mergeNames());
    };

    A.search = async function (q) {
        q = (q || '').trim();
        if (!q) return;
        D.$('dbt-artist-matches-box').hidden = true;
        D.say('dbt-artist-find-status', 'Searching…');
        const r = await D.api('search_artist', { params: { artist: q } });
        if (r.status === 'multiple') {
            D.say('dbt-artist-find-status', `${r.candidates.length} artists match “${q}”.`);
            D.$('dbt-artist-matches').replaceChildren(...r.candidates.map(c => D.el('li', {},
                D.el('button', { type: 'button', className: 'dbt-match', dataset: { id: c.mf_artist_id } },
                    D.el('span', {}, c.artist_name), D.el('small', {}, c.country && c.country !== 'Unknown' ? c.country : '')))));
            D.$('dbt-artist-matches-box').hidden = false;
        } else if (r.status === 'success') {
            D.say('dbt-artist-find-status', '');
            await A.load(r.artist.mf_artist_id);
        } else {
            D.say('dbt-artist-find-status', r.message || 'No artist found.', 'warning');
        }
    };

    A.load = async function (aid, { force = false } = {}) {
        if (!force && tracker.dirty && !(A.current && A.current.mf_artist_id === aid) && !(await tracker.ask())) return;
        const r = await D.api('get_artist_details', { params: { mf_artist_id: aid } });
        if (r.status !== 'success') { D.say('dbt-artist-find-status', r.message || "That artist couldn't be loaded.", 'error'); return; }
        D.$('dbt-artist-matches-box').hidden = true;
        D.say('dbt-artist-find-status', '');
        A.render(r.artist);
    };

    A.render = function (a) {
        A.current = a;
        D.$('dbt-artist-form').hidden = false;
        D.$('dbt-artist-h').textContent = a.artist_name || 'Artist';
        D.$('dbt-art-name').value = a.artist_name || '';
        D.$('dbt-art-country').value = a.country || '';
        D.$('dbt-art-bio').value = a.biography || '';
        D.$('dbt-art-photo').value = a.photo_path || '';
        const img = D.$('dbt-art-img');
        img.src = a.photo_path ? `/ui/artist_photo/${encodeURIComponent(a.mf_artist_id)}?t=${Date.now()}` : '/ui/images/no-photo.png';
        const albums = a.albums || [];
        D.$('dbt-art-albums-h').textContent = `Albums (${albums.length})`;
        D.$('dbt-art-albums').replaceChildren(...(albums.length ? albums.map(al => D.el('li', {},
            D.el('button', { type: 'button', className: 'dbt-album-card', dataset: { id: al.mf_id } },
                D.el('img', { src: `/ui/covers/${encodeURIComponent(al.mf_id)}.jpg`, alt: '', loading: 'lazy' }),
                D.el('strong', {}, al.album_title || 'Untitled'),
                al.year ? D.el('span', { className: 'dbt-album-year' }, `(${al.year})`) : null,
                D.el('small', {}, al.role === 'Primary Artist' ? 'Album artist' : 'Appears on'))))
            : [D.el('li', { className: 'dbt-hint' }, 'No albums in the database.')]));
        D.say('dbt-art-status', '');
        tracker.clean();
    };

    A.save = async function () {
        if (!A.current) return;
        const name = D.$('dbt-art-name').value.trim();
        if (!name) {
            D.$('dbt-art-name').setAttribute('aria-invalid', 'true');
            D.say('dbt-art-status', 'The artist needs a name.', 'error');
            D.$('dbt-art-name').focus();
            return;
        }
        D.$('dbt-art-name').removeAttribute('aria-invalid');
        const body = {
            mf_artist_id: A.current.mf_artist_id, name,
            country: D.$('dbt-art-country').value.trim().toUpperCase(),
            biography: D.$('dbt-art-bio').value,
            photo_path: D.$('dbt-art-photo').value.trim()
        };
        D.say('dbt-art-status', 'Saving…');
        let r = await D.api('save_artist', { body });
        if (r.status === 'confirm') {
            D.say('dbt-art-status', '');
            const yes = await D.confirm({
                title: `Rename to ${name}?`,
                intro: `“${A.current.artist_name}” becomes “${name}”. This changes:`,
                lines: D.previewLines(r), notes: r.notes, ok: 'Rename'
            });
            if (!yes) { D.say('dbt-art-status', 'Not renamed. Your edits are still here.', 'warning'); return; }
            D.say('dbt-art-status', 'Renaming… this can take a while for an artist with many tracks.');
            r = await D.api('save_artist', { body: { ...body, confirmed: true } });
        }
        if (r.status !== 'success') { D.say('dbt-art-status', r.message || "Couldn't save.", 'error'); return; }
        await A.load(r.mf_artist_id, { force: true });
        const problems = r.problems || [];
        D.say('dbt-art-status', problems.length
            ? `Saved, but ${problems.length} file${problems.length === 1 ? '' : 's'} couldn't be updated: ${problems.slice(0, 3).join(' ')}`
            : 'Saved.', problems.length ? 'warning' : 'ok');
    };

    A.browsePhoto = async function () {
        try {
            const r = await (await fetch('/select_file')).json();
            if (r.path) { D.$('dbt-art-photo').value = r.path; tracker.mark(); }
        } catch (e) { D.say('dbt-art-status', "The file picker couldn't open.", 'error'); }
    };

    A.openBioBuilder = async function () {
        if (!A.current) return;
        // Bio Builder opens this artist directly (biography.js ingestContext).
        window.mf_context_artist_id = A.current.mf_artist_id;
        window.mfSwitchMode('biography');
    };

    // --- MERGE ---
    A.openMerge = function () {
        if (!A.current) return;
        A.mergeOther = null;
        D.$('dbt-merge-q').value = '';
        D.$('dbt-merge-pick').replaceChildren();
        D.$('dbt-merge-pick-box').hidden = true;
        D.$('dbt-merge-name-box').hidden = true;
        D.say('dbt-merge-find-status', '');
        D.say('dbt-merge-status', '');
        D.$('dbt-merge').showModal();
    };

    A.mergeSearch = async function () {
        const q = D.$('dbt-merge-q').value.trim();
        if (!q) return;
        const r = await D.api('search_artist', { params: { artist: q } });
        let list = r.status === 'multiple' ? r.candidates : (r.status === 'success' ? [r.artist] : []);
        list = list.filter(c => c.mf_artist_id !== A.current.mf_artist_id);
        D.$('dbt-merge-name-box').hidden = true;
        if (!list.length) {
            D.$('dbt-merge-pick-box').hidden = true;
            D.say('dbt-merge-find-status', `No other artist matches “${q}”.`, 'warning');
            return;
        }
        D.say('dbt-merge-find-status', `${list.length} found. Choose one.`);
        D.$('dbt-merge-pick').replaceChildren(...list.map(c => D.el('li', {},
            D.el('label', { className: 'dbt-radio' },
                D.el('input', { type: 'radio', name: 'dbt-merge-other', value: c.mf_artist_id, dataset: { name: c.artist_name } }),
                D.el('span', {}, c.artist_name, c.country && c.country !== 'Unknown' ? D.el('small', {}, c.country) : '')))));
        D.$('dbt-merge-pick-box').hidden = false;
    };

    A.mergeNames = function () {
        const pick = document.querySelector('input[name="dbt-merge-other"]:checked');
        if (!pick) return;
        A.mergeOther = { id: pick.value, name: pick.dataset.name };
        const mine = A.current.artist_name;
        D.$('dbt-merge-names').replaceChildren(
            D.el('label', { className: 'dbt-radio' }, D.el('input', { type: 'radio', name: 'dbt-merge-name', value: 'keep', checked: true }), D.el('span', {}, mine)),
            D.el('label', { className: 'dbt-radio' }, D.el('input', { type: 'radio', name: 'dbt-merge-name', value: 'other' }), D.el('span', {}, A.mergeOther.name)));
        D.$('dbt-merge-name-box').hidden = false;
        D.say('dbt-merge-status', '');
    };

    A.mergePreview = async function () {
        if (!A.mergeOther) { D.say('dbt-merge-status', 'Find and choose the other artist first.', 'warning'); return; }
        if (tracker.dirty) { D.say('dbt-merge-status', 'Save or undo your changes to this artist first.', 'warning'); return; }
        const keepOther = (document.querySelector('input[name="dbt-merge-name"]:checked') || {}).value === 'other';
        const body = { keep_id: A.current.mf_artist_id, other_id: A.mergeOther.id, name: keepOther ? A.mergeOther.name : A.current.artist_name };
        const r = await D.api('merge_artists', { body });
        if (r.status !== 'confirm') { D.say('dbt-merge-status', r.message || "Couldn't check the merge.", 'error'); return; }
        D.$('dbt-merge').close();
        const yes = await D.confirm({
            title: `Merge into ${body.name}?`,
            intro: `“${A.current.artist_name}” and “${A.mergeOther.name}” become one artist named “${body.name}”. This changes:`,
            lines: D.previewLines(r), notes: r.notes, ok: 'Merge'
        });
        D.$('dbt-art-merge-btn').focus();   // the dialog that opened this one is closed
        if (!yes) { D.say('dbt-art-status', 'Not merged.', 'warning'); return; }
        D.say('dbt-art-status', 'Merging… this can take a while for artists with many tracks.');
        const done = await D.api('merge_artists', { body: { ...body, confirmed: true } });
        if (done.status !== 'success') { D.say('dbt-art-status', done.message || "Couldn't merge.", 'error'); return; }
        await A.load(done.mf_artist_id, { force: true });
        const problems = done.problems || [];
        D.say('dbt-art-status', problems.length ? `Merged, but ${problems.length} file${problems.length === 1 ? '' : 's'} couldn't be updated.` : 'Merged.', problems.length ? 'warning' : 'ok');
    };
})();
// --- END OF FILE artist_editor.js ---
