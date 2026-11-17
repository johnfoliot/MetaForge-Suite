/* --- START OF FILE musicbrainz_submit.js --- */
/**
 * MetaForge Studio: MusicBrainz Submit
 * v2 (2026-11-16): album pass. Choose an album; MetaForge checks
 * MusicBrainz (what's already there, which artist each name is, which
 * instrument names exist); the rest are selected checkboxes grouped by
 * relationship; "Open in MusicBrainz" sends up to 25 to the release's
 * relationship editor, where the user clicks "Enter edit".
 * The tool's script loads once per page; init() runs on every visit.
 */
window.metaforge = window.metaforge || {};

window.metaforge.musicbrainz_submit = {
    BATCH: 25,
    SORT_KEY: 'mbs-sort',
    albums: new Map(),      // mf_id -> {data, li}
    current: null,          // {album, credits}
    checking: false,
    batch: null,            // {token, timer}

    url: (action) => `/run_tool_logic/musicbrainz_submit/${action}`,

    post: async function (action, body) {
        const res = await fetch(this.url(action), {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {})
        });
        let data = {};
        try { data = await res.json(); } catch (e) { /* not JSON */ }
        if (!res.ok || data.status === 'error') throw new Error(data.message || `the server answered ${res.status}`);
        return data;
    },

    init: function () {
        const $ = (id) => document.getElementById(id);
        this.albums = new Map();
        this.current = null;
        let sort = 'most';
        try { sort = localStorage.getItem(this.SORT_KEY) || 'most'; } catch (e) { /* storage blocked */ }
        $('mbs-sort').value = ['most', 'alpha', 'newest'].includes(sort) ? sort : 'most';

        $('mbs-search').addEventListener('input', () => this.applyView());
        $('mbs-show-skipped').addEventListener('change', () => this.applyView());
        $('mbs-sort').addEventListener('change', () => {
            try { localStorage.setItem(this.SORT_KEY, $('mbs-sort').value); } catch (e) { /* storage blocked */ }
            this.applyView(true);
        });
        $('mbs-list').addEventListener('click', (e) => {
            const btn = e.target.closest('.mbs-album-btn');
            if (btn) this.openAlbum(btn.dataset.id);
        });
        $('mbs-form').addEventListener('submit', (e) => { e.preventDefault(); this.openInMusicBrainz(); });
        $('mbs-form').addEventListener('change', (e) => this.onFormChange(e));
        $('mbs-form').addEventListener('click', (e) => {
            const b = e.target.closest('button[data-select-all]');
            if (b) this.selectAll(b);
        });
        $('mbs-check').addEventListener('click', () => this.runCheck());
        $('mbs-skip').addEventListener('click', () => this.toggleSkip());
        this.loadAlbums();
        // Left while a MusicBrainz window was open: carry on with it here.
        if (this.batch) {
            if (this.batch.last) this.showBatch(this.batch.last);
            clearTimeout(this.batch.timer);
            this.pollBatch();
        }
    },

    // --- ALBUM LIST ---------------------------------------------------------

    loadAlbums: async function () {
        const $ = (id) => document.getElementById(id);
        let data;
        try { data = await this.post('albums'); }
        catch (err) {
            if ($('mbs-album-count')) $('mbs-album-count').textContent = `The albums couldn't be loaded: ${err.message}`;
            return;
        }
        const list = $('mbs-list');
        if (!list) return;   // left the tool while loading
        const keep = new Map();
        data.albums.forEach((a) => {
            const old = this.albums.get(a.mf_id);
            const li = old ? old.li : this.albumItem(a);
            if (old) this.fillAlbumItem(li, a);
            keep.set(a.mf_id, { data: a, li });
        });
        this.albums.forEach((v, id) => { if (!keep.has(id)) v.li.remove(); });
        this.albums = keep;
        keep.forEach((v) => { if (!v.li.isConnected) list.append(v.li); });
        this.applyView();
    },

    albumItem: function (a) {
        const li = document.createElement('li');
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'mbs-album-btn';
        btn.dataset.id = a.mf_id;
        const title = document.createElement('span');
        title.className = 'mbs-a-title';
        const artist = document.createElement('span');
        artist.className = 'mbs-a-artist';
        const count = document.createElement('span');
        count.className = 'mbs-a-count';
        btn.append(title, artist, count);
        li.append(btn);
        this.fillAlbumItem(li, a);
        return li;
    },

    fillAlbumItem: function (li, a) {
        const btn = li.firstElementChild;
        btn.querySelector('.mbs-a-title').textContent = a.album;
        btn.querySelector('.mbs-a-artist').textContent = a.artist;
        const bits = [];
        // Until MusicBrainz has been checked, many of these may already be there.
        if (a.to_send) bits.push(a.checked ? `${a.to_send} to send` : `${a.to_send} to check`);
        if (a.waiting) bits.push(`${a.waiting} waiting`);
        if (a.skipped) bits.push('skipped');
        btn.querySelector('.mbs-a-count').textContent = bits.join(', ');
    },

    applyView: function (announceSort) {
        const $ = (id) => document.getElementById(id);
        const list = $('mbs-list');
        if (!list) return;
        const q = $('mbs-search').value.trim().toLocaleLowerCase();
        const showSkipped = $('mbs-show-skipped').checked;
        const sort = $('mbs-sort').value;
        const rows = [...this.albums.values()];
        const cmpText = (x, y) => x.localeCompare(y, undefined, { sensitivity: 'base' });
        rows.sort((x, y) => {
            const a = x.data, b = y.data;
            if (sort === 'alpha') return cmpText(a.artist, b.artist) || cmpText(a.album, b.album);
            if (sort === 'newest') return (b.newest || '').localeCompare(a.newest || '') || cmpText(a.artist, b.artist);
            return (b.to_send - a.to_send) || cmpText(a.artist, b.artist);
        });
        const move = Object.hasOwn(Element.prototype, 'moveBefore')
            ? (n) => list.moveBefore(n, null) : (n) => list.append(n);
        let shown = 0, credits = 0;
        rows.forEach(({ data: a, li }) => {
            move(li);
            const match = !q || a.album.toLocaleLowerCase().includes(q) || a.artist.toLocaleLowerCase().includes(q);
            li.hidden = !match || (a.skipped && !showSkipped);
            if (!li.hidden) { shown++; credits += a.to_send; }
        });
        let empty = list.querySelector('.mbs-list-empty');
        if (!shown) {
            if (!empty) {
                empty = document.createElement('li');
                empty.className = 'mbs-list-empty';
                list.append(empty);
            }
            empty.textContent = this.albums.size ? 'No albums match.' : 'Nothing to send: MusicBrainz has every credit MetaForge found.';
        } else if (empty) {
            empty.remove();
        }
        const order = { most: 'most credits first', alpha: 'artist A to Z', newest: 'newest first' }[sort];
        const text = `${shown} album${shown === 1 ? '' : 's'}, ${credits} credit${credits === 1 ? '' : 's'} MusicBrainz may not have. Order: ${order}.`;
        $('mbs-album-count').textContent = text;
        if (announceSort) window.MFAnnounce(text);
    },

    markCurrent: function (mfId) {
        this.albums.forEach((v, id) => {
            const btn = v.li.firstElementChild;
            if (id === mfId) btn.setAttribute('aria-current', 'true'); else btn.removeAttribute('aria-current');
        });
    },

    // --- ONE ALBUM ----------------------------------------------------------

    openAlbum: async function (mfId, { focusHeading = true } = {}) {
        const $ = (id) => document.getElementById(id);
        if (this.checking || this.batch) {
            window.MFAnnounce(this.batch ? 'Finish with the MusicBrainz window first.' : 'Wait for the check to finish.');
            return;
        }
        this.markCurrent(mfId);
        const seq = this.openSeq = (this.openSeq || 0) + 1;
        let data;
        try { data = await this.post('album', { mf_id: mfId }); }
        catch (err) {
            if (seq !== this.openSeq || !$('mbs-body')) return;
            $('mbs-album-h').textContent = 'This album couldn\'t be opened';
            $('mbs-album-sub').textContent = err.message;
            return;
        }
        // Another album was chosen meanwhile, or the tool was left.
        if (seq !== this.openSeq || !$('mbs-body') || this.checking) return;
        this.current = data;
        this.render();
        if (focusHeading) $('mbs-album-h').focus();
        // Check when never checked, when sent credits may have arrived, or when
        // an instrument name couldn't be checked last time.
        const again = data.credits.some((c) => c.status === 'sent' || (c.status === 'pending' && !c.track
            && c.relationship.kind === 'instrument' && !c.relationship.instrument_known));
        if (!data.album.checked_at || again) this.runCheck();
    },

    /** Sorts the album's credits into what the screen shows. */
    sortCredits: function (credits) {
        const g = { send: [], waiting: [], there: [], tracks: [], no: [], trackScoped: 0 };
        credits.forEach((c) => {
            if (c.track) { g.trackScoped++; return; }
            if (c.status === 'sent') { g.waiting.push(c); return; }
            if (c.status === 'on_mb' || c.status === 'submitted') { g.there.push(c); return; }
            if (!c.relationship.sendable) { (c.relationship.why === 'tracks' ? g.tracks : g.no).push(c); return; }
            g.send.push(c);
        });
        return g;
    },

    /** Artist MBID to send with, or null while the user still has to choose. */
    artistFor: function (c) {
        if (c.artist_mbid) return c.artist_mbid;
        const m = c.artist_match;
        return m && m.status === 'exact' ? m.mbid : null;
    },

    ready: function (c, checked) {
        if (!checked) return false;
        if (c.relationship.kind === 'instrument' && !c.relationship.instrument_known) return false;
        return !!this.artistFor(c);
    },

    render: function () {
        const $ = (id) => document.getElementById(id);
        const { album, credits } = this.current;
        const checked = !!album.checked_at;
        $('mbs-album-h').textContent = album.album;
        $('mbs-album-sub').textContent = album.artist;
        $('mbs-check').hidden = false;
        $('mbs-skip').hidden = false;
        $('mbs-skip').textContent = album.skipped ? 'Stop skipping this album' : 'Skip this album';

        const body = $('mbs-body');
        const keepBatch = $('mbs-batch');
        body.replaceChildren();
        if (keepBatch) body.append(keepBatch);
        const log = document.createElement('div');
        log.id = 'mbs-check-log';
        log.className = 'mf-ev-log';
        body.append(log);

        const g = this.sortCredits(credits);
        if (!checked) {
            const p = document.createElement('p');
            p.className = 'mbs-intro';
            p.textContent = 'Checking MusicBrainz before anything can be sent…';
            body.append(p);
        }

        // Selected checkboxes, grouped by relationship. Each group with more
        // than one credit gets Select all / Deselect all (John, 2026-11-17).
        const groups = new Map();
        g.send.forEach((c) => {
            const label = c.relationship.kind === 'instrument' ? 'Instruments' : c.relationship.label;
            if (!groups.has(label)) groups.set(label, []);
            groups.get(label).push(c);
        });
        groups.forEach((list, label) => {
            const fs = document.createElement('fieldset');
            fs.className = 'mbs-group';
            fs.dataset.group = label;
            const lg = document.createElement('legend');
            lg.textContent = `${label} (${list.length})`;
            fs.append(lg);
            if (list.length > 1) fs.append(this.selectAllButton(label));
            list.forEach((c) => fs.append(this.creditRow(c, checked)));
            body.append(fs);
            this.syncSelectAll(fs);
        });
        if (checked && !g.send.length) {
            const p = document.createElement('p');
            p.className = 'mbs-intro';
            p.textContent = 'Nothing left to send for this album.';
            body.append(p);
        }

        this.otherList(body, 'Waiting for MusicBrainz', g.waiting, (c) => [`${c.relationship.label}: ${c.name}`, ''],
            'Sent from MetaForge. MusicBrainz shows them once the edit is accepted (edits by newer editors are voted on for up to a week); MetaForge checks each time you open the album.');
        this.otherList(body, 'Already on MusicBrainz', g.there, (c) => [`${c.relationship.label || c.role}: ${c.name}`,
            c.status === 'submitted' ? 'added by you' : '']);
        this.otherList(body, 'Only on some tracks', g.tracks, (c) => [`${c.relationship.label}: ${c.name}`, c.tracks ? `tracks ${c.tracks}` : ''],
            'These aren\'t credits for the whole release. MusicBrainz Submit can\'t send credits for single tracks yet.');
        this.otherList(body, 'Can\'t be sent', g.no, (c) => [`${c.relationship.label}: ${c.name}`, c.relationship.reason]);
        if (g.trackScoped) {
            const p = document.createElement('p');
            p.className = 'mbs-intro';
            p.textContent = `${g.trackScoped} more credit${g.trackScoped === 1 ? ' is' : 's are'} for single tracks. MusicBrainz Submit can't send ${g.trackScoped === 1 ? 'that' : 'those'} yet.`;
            body.append(p);
        }
        $('mbs-foot').hidden = false;
        this.updateFoot();
    },

    creditRow: function (c, checked) {
        const row = document.createElement('div');
        row.className = 'mbs-credit';
        const id = `mbs-c-${Math.random().toString(36).slice(2, 10)}`;
        const box = document.createElement('input');
        box.type = 'checkbox';
        box.id = id;
        box.dataset.key = c.key;
        box.checked = c.status === 'pending' && c.mb_check !== 'similar' && !c.source_elsewhere;
        const label = document.createElement('label');
        label.htmlFor = id;
        label.textContent = c.relationship.kind === 'instrument'
            ? `${c.name}: ${c.relationship.instrument_known ? c.relationship.instrument : c.relationship.label}`
            : c.name;
        const meta = document.createElement('span');
        meta.className = 'mbs-meta';
        const own = c.provenance === 'MetaForge (Manual)' || c.provenance === 'Submitter Confirmed';
        const bits = [own ? c.source : `From ${c.source}`];
        if (c.role && c.relationship.kind !== 'instrument' && c.role.toLowerCase() !== c.relationship.label.toLowerCase()) bits.push(`credited as "${c.role}"`);
        meta.textContent = bits.join(', ');
        row.append(box, label, meta);
        const descs = [meta];
        if (c.source_elsewhere) {
            const n = this.note('The page you confirmed this with looks like a different release: ', descs);
            const a = document.createElement('a');
            a.href = c.verified_source_url;
            a.textContent = c.verified_source_url;
            a.target = '_blank';
            a.rel = 'noreferrer';
            n.append(a, '. Select it only if this credit is right for this album too.');
            row.append(n);
        }

        if (checked) {
            const m = c.artist_match;
            if (c.mb_check === 'similar') {
                row.append(this.note(`MusicBrainz already credits this person on this release${c.mb_has ? ` (${c.mb_has})` : ''}. Select it only if this is a different credit.`, descs));
            }
            if (c.relationship.kind === 'instrument' && !c.relationship.instrument_known) {
                row.append(this.note('MusicBrainz\'s instrument list couldn\'t be checked for this one. Check MusicBrainz again.', descs));
            }
            if (!this.artistFor(c)) {
                if (m && m.options && m.options.length) {
                    row.append(this.artistPicker(c, m, descs));
                } else {
                    row.append(this.note(m && m.status === 'error'
                        ? 'MusicBrainz couldn\'t be searched for this name. Check MusicBrainz again later.'
                        : 'MusicBrainz has no artist by this name, so it can\'t be sent yet.', descs));
                }
            } else if (c.artist_chosen) {
                const p = document.createElement('span');
                p.className = 'mbs-meta';
                p.textContent = `MusicBrainz artist: ${c.artist_name || 'chosen by you'}`;
                row.append(p);
                descs.push(p);
            }
        }
        descs.forEach((d, i) => { if (!d.id) d.id = `${id}-d${i}`; });
        box.setAttribute('aria-describedby', descs.map((d) => d.id).join(' '));
        return row;
    },

    /** One button per group. Both labels sit in the same grid cell (the
     *  unused one invisible), so the button never changes size when its
     *  label flips. The group's name is added for screen readers, so ten
     *  "Select all" buttons are told apart. */
    selectAllButton: function (label) {
        const b = document.createElement('button');
        b.type = 'button';
        b.className = 'mbs-select-all';
        b.dataset.selectAll = '';
        const on = document.createElement('span');
        on.className = 'mbs-sa-select';
        on.textContent = 'Select all';
        const off = document.createElement('span');
        off.className = 'mbs-sa-deselect';
        off.textContent = 'Deselect all';
        const who = document.createElement('span');
        who.className = 'mf-visually-hidden';
        who.textContent = ` ${label} credits`;
        b.append(on, off, who);
        return b;
    },

    /** Shows "Deselect all" when every credit in the group is selected. */
    syncSelectAll: function (fs) {
        const b = fs.querySelector('button[data-select-all]');
        if (!b) return;
        const boxes = [...fs.querySelectorAll('input[type="checkbox"][data-key]')];
        const all = boxes.length > 0 && boxes.every((x) => x.checked);
        b.classList.toggle('is-all', all);
        b.querySelector('.mbs-sa-select').setAttribute('aria-hidden', String(all));
        b.querySelector('.mbs-sa-deselect').setAttribute('aria-hidden', String(!all));
    },

    selectAll: async function (b) {
        const fs = b.closest('fieldset.mbs-group');
        const boxes = [...fs.querySelectorAll('input[type="checkbox"][data-key]')];
        const send = !b.classList.contains('is-all');
        const changed = boxes.filter((x) => x.checked !== send);
        changed.forEach((x) => { x.checked = send; });
        this.syncSelectAll(fs);
        this.updateFoot();
        const n = boxes.length;
        window.MFAnnounce(`${send ? 'Selected' : 'Deselected'} all ${n} ${fs.dataset.group} credit${n === 1 ? '' : 's'}.`);
        if (!changed.length) return;
        try {
            await this.post('set_credit', { keys: changed.map((x) => x.dataset.key), send });
            const keys = new Set(changed.map((x) => x.dataset.key));
            (this.current ? this.current.credits : []).forEach((c) => {
                if (keys.has(c.key)) c.status = send ? 'pending' : 'dismissed';
            });
        } catch (err) {
            window.MFAnnounce(`Error: that choice wasn't saved: ${err.message}`, { urgent: true });
        }
    },

    note: function (text, descs) {
        const p = document.createElement('span');
        p.className = 'mbs-need';
        p.textContent = text;
        descs.push(p);
        return p;
    },

    artistPicker: function (c, m, descs) {
        const wrap = document.createElement('span');
        wrap.className = 'mbs-pick';
        const sid = `mbs-p-${Math.random().toString(36).slice(2, 10)}`;
        const lab = document.createElement('label');
        lab.htmlFor = sid;
        lab.className = 'mbs-need';
        lab.textContent = m.status === 'ambiguous'
            ? 'More than one MusicBrainz artist has this name. Which one?'
            : 'No exact match on MusicBrainz. Is it one of these?';
        const sel = document.createElement('select');
        sel.id = sid;
        sel.dataset.pick = c.key;
        const first = document.createElement('option');
        first.value = '';
        first.textContent = 'Choose the artist';
        sel.append(first);
        m.options.forEach((o) => {
            const opt = document.createElement('option');
            opt.value = o.mbid;
            opt.dataset.name = o.name;
            opt.textContent = [o.name, o.disambiguation, o.country].filter(Boolean).join(', ');
            sel.append(opt);
        });
        const none = document.createElement('option');
        none.value = 'none';
        none.textContent = 'None of these: don\'t send';
        sel.append(none);
        wrap.append(lab, sel);
        descs.push(lab);
        return wrap;
    },

    otherList: function (body, title, list, line, help) {
        if (!list.length) return;
        const d = document.createElement('details');
        d.className = 'mbs-other';
        const s = document.createElement('summary');
        s.textContent = `${title} (${list.length})`;
        d.append(s);
        if (help) {
            const p = document.createElement('p');
            p.textContent = help;
            d.append(p);
        }
        const ul = document.createElement('ul');
        list.forEach((c) => {
            const [main, why] = line(c);
            const li = document.createElement('li');
            li.append(main);
            if (why) {
                const w = document.createElement('span');
                w.className = 'mbs-why';
                w.textContent = ` (${why})`;
                li.append(w);
            }
            ul.append(li);
        });
        d.append(ul);
        body.append(d);
    },

    /** The selected credits that can go now, in screen order. */
    sendable: function () {
        if (!this.current || !this.current.album.checked_at) return [];
        const byKey = new Map(this.current.credits.map((c) => [c.key, c]));
        return [...document.querySelectorAll('#mbs-body input[type="checkbox"][data-key]')]
            .map((b) => ({ c: byKey.get(b.dataset.key), on: b.checked }))
            .filter(({ c, on }) => c && this.ready(c, on))
            .map(({ c }) => c);
    },

    updateFoot: function () {
        const $ = (id) => document.getElementById(id);
        if (!$('mbs-open') || !this.current) return;
        const ready = this.sendable();
        const selected = document.querySelectorAll('#mbs-body input[type="checkbox"][data-key]:checked').length;
        const n = Math.min(this.BATCH, ready.length);
        $('mbs-open').disabled = !n || this.checking || !!this.batch;
        $('mbs-open').textContent = ready.length > n ? `Open in MusicBrainz (${n} of ${ready.length})` : 'Open in MusicBrainz';
        let note;
        if (!this.current.album.checked_at) note = 'Checking MusicBrainz first.';
        else if (!ready.length) note = selected ? 'None of the selected credits can be sent yet (see the notes beside them).' : 'Nothing is selected.';
        else {
            note = `${ready.length} credit${ready.length === 1 ? '' : 's'} ready to send`;
            if (ready.length > n) note += `; MusicBrainz gets ${n} at a time`;
            const wait = selected - ready.length;
            if (wait > 0) note += `; ${wait} selected can't be sent yet (see the note${wait === 1 ? '' : 's'} beside ${wait === 1 ? 'it' : 'them'})`;
            note += '.';
        }
        $('mbs-foot-note').textContent = note;
    },

    onFormChange: async function (e) {
        const t = e.target;
        if (t.matches('input[type="checkbox"][data-key]')) {
            const fs = t.closest('fieldset.mbs-group');
            if (fs) this.syncSelectAll(fs);
            this.updateFoot();
            try { await this.post('set_credit', { key: t.dataset.key, send: t.checked }); }
            catch (err) { window.MFAnnounce(`Error: that choice wasn't saved: ${err.message}`, { urgent: true }); }
            const c = this.current && this.current.credits.find((x) => x.key === t.dataset.key);
            if (c) c.status = t.checked ? 'pending' : 'dismissed';
            return;
        }
        if (t.matches('select[data-pick]')) {
            const key = t.dataset.pick;
            const c = this.current && this.current.credits.find((x) => x.key === key);
            if (!c || !t.value) return;
            try {
                if (t.value === 'none') {
                    await this.post('set_credit', { key, send: false });
                    c.status = 'dismissed';
                    const box = t.closest('.mbs-credit').querySelector('input[type="checkbox"]');
                    box.checked = false;
                    const fs = box.closest('fieldset.mbs-group');
                    if (fs) this.syncSelectAll(fs);
                    window.MFAnnounce(`${c.name} won't be sent.`);
                } else {
                    const name = t.selectedOptions[0].dataset.name || '';
                    await this.post('set_artist', { key, mbid: t.value, name });
                    c.artist_mbid = t.value; c.artist_name = name; c.artist_chosen = true;
                    const row = t.closest('.mbs-credit');
                    const fresh = this.creditRow(c, true);
                    row.replaceWith(fresh);
                    fresh.querySelector('input[type="checkbox"]').focus();
                    window.MFAnnounce(`${c.name}: artist chosen.`);
                }
            } catch (err) {
                window.MFAnnounce(`Error: that choice wasn't saved: ${err.message}`, { urgent: true });
            }
            this.updateFoot();
        }
    },

    // --- CHECK MUSICBRAINZ --------------------------------------------------

    runCheck: async function () {
        if (this.checking || !this.current) return;
        const $ = (id) => document.getElementById(id);
        const mfId = this.current.album.mf_id;
        this.checking = true;
        $('mbs-check').disabled = true;
        $('mbs-skip').disabled = true;
        $('mbs-progress').hidden = false;
        this.setProgress(0, 'Starting the check…');
        this.updateFoot();
        const log = $('mbs-check-log');
        if (log) log.replaceChildren();
        try {
            const res = await fetch(this.url('check'), {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ mf_id: mfId })
            });
            if (res.status === 409) throw new Error((await res.json()).message);
            await window.MFEvents.read(res, {
                log,
                onSignal: (name, data) => { if (name === 'progress') this.setProgress(data.percent, data.label); }
            });
        } catch (err) {
            window.MFEvents.render($('mbs-check-log'), { kind: 'error', text: `The check stopped: ${err.message}` });
            window.MFAnnounce(`Error: the check stopped: ${err.message}`, { urgent: true });
        } finally {
            this.checking = false;
            // The tool may have been left mid-check: look the screen up again.
            if ($('mbs-body')) {
                $('mbs-progress').hidden = true;
                $('mbs-check').disabled = false;
                $('mbs-skip').disabled = false;
                const kept = $('mbs-check-log') ? [...$('mbs-check-log').childNodes] : [];
                if (this.current && this.current.album.mf_id === mfId) {
                    try {
                        this.current = await this.post('album', { mf_id: mfId });
                        this.render();
                        $('mbs-check-log').append(...kept);
                    } catch (e) { /* keep what's shown */ }
                }
                this.loadAlbums();
            }
        }
    },

    setProgress: function (percent, label) {
        const pct = Math.max(0, Math.min(100, Number(percent) || 0));
        const bar = document.getElementById('mbs-progress-bar');
        const fill = document.getElementById('mbs-progress-fill');
        const text = document.getElementById('mbs-progress-label');
        if (fill) fill.style.width = `${pct}%`;
        if (text && label) text.textContent = label;
        if (bar) {
            bar.setAttribute('aria-valuenow', String(Math.round(pct)));
            if (label) bar.setAttribute('aria-valuetext', `${label} (${Math.round(pct)}%)`);
        }
    },

    toggleSkip: async function () {
        if (!this.current) return;
        const a = this.current.album;
        try { await this.post('skip_album', { mf_id: a.mf_id, skip: !a.skipped }); }
        catch (err) { window.MFAnnounce(`Error: ${err.message}`, { urgent: true }); return; }
        a.skipped = !a.skipped;
        const entry = this.albums.get(a.mf_id);
        if (entry) { entry.data.skipped = a.skipped; this.fillAlbumItem(entry.li, entry.data); }
        document.getElementById('mbs-skip').textContent = a.skipped ? 'Stop skipping this album' : 'Skip this album';
        window.MFAnnounce(a.skipped ? `${a.album} skipped. It's hidden from the list unless "Show skipped albums" is selected.` : `${a.album} is back in the list.`);
        this.applyView();
    },

    // --- SEND A BATCH -------------------------------------------------------

    openInMusicBrainz: async function () {
        if (this.batch || this.checking || !this.current) return;
        const $ = (id) => document.getElementById(id);
        const items = this.sendable().slice(0, this.BATCH);
        if (!items.length) return;
        $('mbs-open').disabled = true;
        let b;
        try {
            b = await this.post('batch', { mf_id: this.current.album.mf_id, keys: items.map((c) => c.key) });
            const res = await fetch('/open_mb_relationship_seed_window', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: b.url, script: b.script, title: b.title, token: b.token })
            });
            if (!res.ok) throw new Error('the MusicBrainz window couldn\'t be opened');
        } catch (err) {
            window.MFAnnounce(`Error: ${err.message}`, { urgent: true });
            this.updateFoot();
            return;
        }
        this.batch = { token: b.token, count: b.count, names: new Map(items.map((c) => [c.key, `${c.relationship.kind === 'instrument' ? c.relationship.instrument : c.relationship.label}: ${c.name}`])) };
        this.showBatch({ results: {}, finished: false });
        window.MFAnnounce(`MusicBrainz is opening in another window. MetaForge adds ${b.count} credit${b.count === 1 ? '' : 's'} there.`);
        this.pollBatch();
    },

    pollBatch: async function () {
        if (!this.batch) return;
        let s;
        try { s = await this.post('batch_status', { token: this.batch.token }); }
        catch (e) { s = null; }
        if (!this.batch) return;
        if (s) {
            this.batch.last = s;
            this.showBatch(s);
            if (s.finished && !this.batch.announced) {
                this.batch.announced = true;
                const ok = Object.values(s.results).filter((r) => r.ok).length;
                window.MFAnnounce(`${ok} of ${s.count} added in the MusicBrainz window. Check them there, click "Enter edit", then close that window.`);
            }
            // Closed: ask, if this screen is showing; otherwise ask on return (init).
            if (s.closed && document.getElementById('mbs-entered')) { this.askEntered(s); return; }
        }
        this.batch.timer = setTimeout(() => this.pollBatch(), 1500);
    },

    showBatch: function (s) {
        let box = document.getElementById('mbs-batch');
        const body = document.getElementById('mbs-body');
        if (!body) return;
        if (!box) {
            box = document.createElement('section');
            box.id = 'mbs-batch';
            box.setAttribute('aria-labelledby', 'mbs-batch-h');
            body.prepend(box);
        }
        const ok = Object.entries(s.results).filter(([, r]) => r.ok);
        const bad = Object.entries(s.results).filter(([, r]) => !r.ok);
        const h = document.createElement('h3');
        h.id = 'mbs-batch-h';
        h.textContent = 'MusicBrainz window';
        const p = document.createElement('p');
        p.textContent = s.finished
            ? `Added ${ok.length} of ${this.batch.count}. Check them and the edit note there, click "Enter edit", then close that window.`
            : `Adding ${this.batch.count} credits there: ${ok.length + bad.length} done so far. The window can take a few seconds to load.`;
        box.replaceChildren(h, p);
        if (bad.length) {
            const p2 = document.createElement('p');
            p2.textContent = 'Couldn\'t be added (they stay here, selected):';
            const ul = document.createElement('ul');
            bad.forEach(([k, r]) => {
                const li = document.createElement('li');
                li.textContent = `${this.batch.names.get(k) || k}${r.message ? ` (${r.message})` : ''}`;
                ul.append(li);
            });
            box.append(p2, ul);
        }
    },

    askEntered: function (s) {
        const dlg = document.getElementById('mbs-entered');
        const ok = Object.values(s.results).filter((r) => r.ok).length;
        const finish = async (entered) => {
            const token = this.batch.token;
            let marked = 0;
            try { marked = (await this.post('batch_done', { token, entered })).marked; } catch (e) { /* batch gone */ }
            clearTimeout(this.batch.timer);
            this.batch = null;
            document.getElementById('mbs-batch')?.remove();
            window.MFAnnounce(entered
                ? `${marked} credit${marked === 1 ? '' : 's'} marked as waiting for MusicBrainz.`
                : 'Nothing was recorded as sent.');
            if (this.current && document.getElementById('mbs-body')) this.openAlbum(this.current.album.mf_id, { focusHeading: false });
        };
        if (!ok || !dlg) { finish(false); return; }
        document.getElementById('mbs-entered-text').textContent =
            `The MusicBrainz window is closed. MetaForge added ${ok} credit${ok === 1 ? '' : 's'} there, but can't see whether the edit was entered.`;
        dlg.addEventListener('close', () => finish(dlg.returnValue === 'yes'), { once: true });
        dlg.returnValue = '';
        dlg.showModal();
    }
};
/* --- END OF FILE musicbrainz_submit.js --- */
