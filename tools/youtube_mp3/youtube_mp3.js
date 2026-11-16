/* --- START OF FILE youtube_mp3.js --- */
/**
 * MetaForge Studio: YouTube to MP3
 * v2 (2026-11-16): built. Look up a link; fill in the details; make the
 * MP3s. A whole album in one video takes two steps: "Find the tracks"
 * (download + find where each song starts), then "Check the cuts", where
 * every start time can be played and corrected before the MP3s are made.
 * The tool's script loads once per page; init() runs on every visit.
 */
window.metaforge = window.metaforge || {};

window.metaforge.youtube_mp3 = {
    running: false,
    info: null,          // the last lookup
    stage: null,         // song | playlist | album-list | album-review
    cuts: null,          // {duration, rows} from Find the tracks
    audio: null,
    playing: null,       // the Play button that's playing

    init: function () {
        const $ = (id) => document.getElementById(id);
        $('yt-lookup').addEventListener('submit', (e) => { e.preventDefault(); this.lookup(); });
        $('yt-form').addEventListener('submit', (e) => { e.preventDefault(); this.go(); });
        $('yt-form').addEventListener('input', (e) => this.clearError(e.target));
        $('yt-url').addEventListener('input', (e) => this.clearError(e.target));
        $('yt-form').addEventListener('change', (e) => {
            if (e.target.name === 'kind') this.setStage(e.target.value === 'album' ? 'album-list' : 'song');
            if (e.target.matches('#yt-songs input[type="checkbox"]')) this.updateGo();
        });
        $('yt-folder-btn').addEventListener('click', () => this.chooseFolder());
        $('yt-back').addEventListener('click', () => this.setStage('album-list', true));
        $('yt-stop').addEventListener('click', () => this.stop());
        $('yt-continue').addEventListener('click', () => this.continueOn());
        $('yt-cuts').addEventListener('click', (e) => {
            const b = e.target.closest('button.yt-play');
            if (b) this.play(b);
        });
        $('yt-cuts').addEventListener('change', (e) => { if (e.target.matches('.yt-start')) this.checkStarts(); });
        if (this.running) {
            $('yt-lookup-btn').disabled = true;
            this.setProgress(0, 'The last run is finishing. Come back in a moment.');
        }
    },

    destroy: function () { this.stopPlaying(); },

    // --- [ LOOK UP ] ---------------------------------------------------------
    lookup: async function () {
        const $ = (id) => document.getElementById(id);
        const url = $('yt-url');
        if (!url.value.trim()) { this.showError(url); url.focus(); return; }
        if (this.running) return;
        this.stopPlaying();
        $('yt-lookup-btn').disabled = true;
        $('yt-handoff').hidden = true;
        this.setBusy('Looking up the link… (YouTube takes 10 to 20 seconds)');
        window.MFAnnounce('Looking up the link.');
        let data;
        try {
            const res = await fetch('/run_tool_logic/youtube_mp3/inspect', {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url: url.value.trim() })
            });
            data = await res.json();
        } catch (e) {
            data = { status: 'error', message: `The lookup failed: ${e.message}` };
        }
        if (!$('yt-form')) return;   // left the tool meanwhile
        $('yt-lookup-btn').disabled = false;
        if (data.status !== 'ok') {
            this.setProgress(0, 'Standing by');
            $('yt-url-error').textContent = `Error: ${data.message}`;
            this.showError(url);
            url.focus();
            window.MFAnnounce(`Error: ${data.message}`, { urgent: true });
            return;
        }
        this.setProgress(0, 'Standing by');
        this.info = data;
        this.cuts = null;
        this.fill(data);
    },

    fill: function (d) {
        const $ = (id) => document.getElementById(id);
        $('yt-intro').hidden = true;
        $('yt-form').hidden = false;
        $('yt-foot').hidden = false;
        $('yt-found-h').textContent = d.heading;
        $('yt-artist').value = d.artist || '';
        $('yt-album').value = d.album || '';
        if (d.kind === 'playlist') {
            const n = d.tracks.length;
            $('yt-found-meta').textContent = `A playlist of ${n} video${n === 1 ? '' : 's'}${d.channel ? ` · ${d.channel}` : ''}`;
            this.buildSongs(d.tracks);
            this.setStage('playlist');
        } else {
            $('yt-found-meta').textContent = `${this.clock(d.duration)}${d.channel ? ` · ${d.channel}` : ''}`;
            $('yt-title').value = d.title || '';
            const tl = d.tracklist;
            const titles = tl ? tl.titles : (d.mb ? d.mb.tracks.map((t) => t.title) : []);
            $('yt-titles').value = titles.join('\n');
            $('yt-titles-hint').textContent = tl
                ? (tl.from === 'chapters' ? "From the video's chapters, with their start times."
                    : tl.from === 'times' ? "From the video's description, with their start times."
                    : "From the video's description. Correct any line; one line per song, in order.")
                : (d.mb ? `From MusicBrainz (${d.mb.title}). One line per song, in order.`
                    : "The video doesn't list its tracks. Type one title per line, in order.");
            $('yt-kind-album').checked = d.looks_like_album;
            $('yt-kind-song').checked = !d.looks_like_album;
            this.setStage(d.looks_like_album ? 'album-list' : 'song');
        }
        document.querySelector('.yt-scroll').scrollTop = 0;
        $('yt-found-h').focus();
        window.MFAnnounce(`Found: ${d.heading}. ${$('yt-found-meta').textContent}.`);
    },

    buildSongs: function (tracks) {
        const list = document.getElementById('yt-songs');
        list.replaceChildren(...tracks.map((t, i) => {
            const li = document.createElement('li');
            li.className = 'yt-song';
            const cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.checked = t.include;
            cb.id = `yt-song-on-${i}`;
            cb.dataset.id = t.id;
            cb.setAttribute('aria-label', `Include song ${i + 1}`);
            const title = document.createElement('input');
            title.type = 'text';
            title.value = t.title;
            title.id = `yt-song-${i}`;
            title.setAttribute('aria-label', `Title of song ${i + 1}`);
            const len = document.createElement('span');
            len.className = 'yt-len';
            len.textContent = t.duration ? this.clock(t.duration) : '';
            li.append(cb, title, len);
            return li;
        }));
        document.getElementById('yt-songs-legend').textContent = `Songs (${tracks.length})`;
    },

    // Only the parts for the current stage are shown; hidden fields are
    // disabled so they're never checked or sent.
    setStage: function (stage, focus = false) {
        const $ = (id) => document.getElementById(id);
        this.stage = stage;
        const isVideo = this.info?.kind === 'video';
        const show = (id, on) => {
            const el = $(id);
            el.hidden = !on;
            el.querySelectorAll('input, textarea').forEach((f) => { if (f.type !== 'radio') f.disabled = !on; });
        };
        $('yt-kind-set').hidden = !isVideo;
        // Settled details fold into one line while the cuts are checked, so
        // the cuts are what's on screen.
        $('yt-details').hidden = stage === 'album-review';
        if (stage === 'album-review') {
            $('yt-saving').textContent = `Saving to ${$('yt-folder').value}`;
        }
        show('yt-title-field', stage === 'song');
        show('yt-titles-field', stage === 'album-list');
        show('yt-songs-set', stage === 'playlist');
        show('yt-review', stage === 'album-review');
        $('yt-artist').disabled = $('yt-album').disabled = stage === 'album-review';
        this.updateGo();
        if (stage === 'album-list') this.stopPlaying();
        if (focus) (stage === 'album-list' ? $('yt-titles') : $('yt-found-h')).focus();
    },

    updateGo: function () {
        const go = document.getElementById('yt-go');
        if (this.stage === 'song') go.textContent = 'Make the MP3';
        else if (this.stage === 'album-list') go.textContent = 'Find the tracks';
        else if (this.stage === 'album-review') go.textContent = `Make ${this.cuts?.rows.length || ''} MP3s`;
        else {
            const n = document.querySelectorAll('#yt-songs input[type="checkbox"]:checked').length;
            go.textContent = `Make ${n} MP3${n === 1 ? '' : 's'}`;
        }
    },

    chooseFolder: async function () {
        const f = document.getElementById('yt-folder');
        const path = await window.pywebview?.api?.select_folder();
        if (!path || !f) return;
        f.value = path;
        this.clearError(f);
    },

    // --- [ CHECKING THE FIELDS ] ---------------------------------------------
    showError: function (field) {
        const err = document.getElementById(field.dataset.error);
        if (!err) return;
        err.classList.add('is-shown');
        field.setAttribute('aria-invalid', 'true');
        const ids = (field.getAttribute('aria-describedby') || '').split(/\s+/).filter((i) => i && i !== err.id);
        field.setAttribute('aria-describedby', [...ids, err.id].join(' '));
    },

    clearError: function (field) {
        if (!field?.dataset?.error || field.getAttribute('aria-invalid') !== 'true') return;
        const err = document.getElementById(field.dataset.error);
        err?.classList.remove('is-shown');
        field.setAttribute('aria-invalid', 'false');
        const ids = (field.getAttribute('aria-describedby') || '').split(/\s+/).filter((i) => i && i !== err?.id);
        if (ids.length) field.setAttribute('aria-describedby', ids.join(' '));
        else field.removeAttribute('aria-describedby');
    },

    /** Empty required fields that are in use; the first is focused. */
    checkFields: function () {
        const bad = [...document.querySelectorAll('#yt-form [required][data-error]')]
            .filter((f) => !f.disabled && !f.closest('[hidden]') && !f.value.trim());
        bad.forEach((f) => this.showError(f));
        if (bad.length) {
            const first = bad[0];
            (first.id === 'yt-folder' ? document.getElementById('yt-folder-btn') : first).focus();
            window.MFAnnounce(document.getElementById(first.dataset.error).textContent, { urgent: true });
        }
        return !bad.length;
    },

    // --- [ RUNS ] ------------------------------------------------------------
    go: function () {
        if (this.running || !this.info || !this.checkFields()) return;
        const $ = (id) => document.getElementById(id);
        const d = this.info;
        const base = { id: d.id, url: d.url, artist: $('yt-artist').value.trim(), album: $('yt-album').value.trim(), folder: $('yt-folder').value };
        if (this.stage === 'song') return this.run({ ...base, mode: 'song', title: $('yt-title').value.trim() });
        if (this.stage === 'playlist') {
            const tracks = [...document.querySelectorAll('#yt-songs .yt-song')].map((li) => ({
                id: li.querySelector('input[type="checkbox"]').dataset.id,
                include: li.querySelector('input[type="checkbox"]').checked,
                title: li.querySelector('input[type="text"]').value
            }));
            if (!tracks.some((t) => t.include)) { window.MFAnnounce('Tick at least one song.', { urgent: true }); return; }
            return this.run({ ...base, mode: 'playlist', tracks });
        }
        if (this.stage === 'album-list') {
            const titles = $('yt-titles').value.split('\n').map((t) => t.trim()).filter(Boolean);
            const tl = d.tracklist;
            const same = tl && tl.titles.length === titles.length;
            return this.run({ ...base, mode: 'album_find', titles,
                starts: same && tl.starts ? tl.starts : null, starts_from: tl?.from,
                lengths: same && tl.lengths ? tl.lengths : null });
        }
        if (!this.checkStarts(true)) return;
        const rows = [...document.querySelectorAll('#yt-cuts .yt-cut')].map((li) => ({
            title: li.querySelector('.yt-title-in').value.trim(),
            start: this.parseClock(li.querySelector('.yt-start').value)
        }));
        return this.run({ ...base, mode: 'album_make', rows });
    },

    run: async function (body) {
        if (this.running) return;
        const $ = (id) => document.getElementById(id);
        const log = $('yt-console');
        this.running = true;
        this.stopPlaying();
        // Let go of the downloaded audio: on Windows an open file can't be
        // deleted, and the run deletes it once its MP3s are made.
        if (this.audio) { this.audio.removeAttribute('src'); this.audio.load(); }
        $('yt-go').disabled = $('yt-lookup-btn').disabled = $('yt-back').disabled = true;
        document.querySelectorAll('#yt-cuts .yt-play').forEach((b) => { b.disabled = true; });
        $('yt-stop').disabled = false;
        $('yt-handoff').hidden = true;
        log.replaceChildren();
        this.setProgress(0, 'Starting…');
        window.MFLeaveGuard?.set('youtube_mp3', () => this.askLeave());
        let made = null;
        let cuts = null;
        let refused = null;
        try {
            const res = await fetch('/run_tool_logic/youtube_mp3/run', {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
            });
            if (!res.ok) throw new Error((await res.json()).message);
            await window.MFEvents.read(res, {
                log,
                onSignal: (name, data) => {
                    if (name === 'progress') this.setProgress(data.percent, data.label, data.busy);
                    if (name === 'made') made = data;
                    if (name === 'cuts') cuts = data;
                    if (name === 'refused') refused = data.message || '';
                }
            });
        } catch (err) {
            window.MFEvents.render(log, { kind: 'error', text: `It stopped: ${err.message}` });
            window.MFAnnounce(`Error: it stopped: ${err.message}`, { urgent: true });
        } finally {
            this.running = false;
            window.MFLeaveGuard?.clear('youtube_mp3');
            if ($('yt-console')) {
                $('yt-stop').disabled = true;
                $('yt-stop').textContent = 'Stop';
                $('yt-go').disabled = $('yt-lookup-btn').disabled = $('yt-back').disabled = false;
                document.querySelectorAll('#yt-cuts .yt-play').forEach((b) => { b.disabled = false; });
                if (cuts) this.showCuts(cuts);
                else if (made) this.showHandoff(made);
                else if (refused !== null) {
                    // Nothing was started: say so, and go to what needs changing.
                    this.setProgress(0, 'Not started: see the message');
                    // The folder controls are folded away while the cuts are checked.
                    const to = /folder/.test(refused) ? (this.stage === 'album-review' ? 'yt-back' : 'yt-folder-btn')
                        : /artist/.test(refused) ? 'yt-artist' : 'yt-go';
                    $(to)?.focus();
                }
            }
        }
    },

    stop: async function () {
        const btn = document.getElementById('yt-stop');
        if (btn) { btn.disabled = true; btn.textContent = 'Stopping…'; }
        window.MFAnnounce('Stopping.');
        try { await fetch('/run_tool_logic/youtube_mp3/stop', { method: 'POST' }); } catch (e) { /* the run ends anyway */ }
    },

    askLeave: function () {
        const dlg = document.getElementById('yt-leave');
        if (!dlg) return Promise.resolve(true);
        return new Promise((resolve) => {
            dlg.addEventListener('close', () => {
                const leave = dlg.returnValue === 'leave';
                if (leave) this.stop();
                resolve(leave);
            }, { once: true });
            dlg.returnValue = '';
            dlg.showModal();
        });
    },

    showHandoff: function (made) {
        this.made = made;
        const h = document.getElementById('yt-handoff');
        h.hidden = false;
        const btn = document.getElementById('yt-continue');
        btn.focus();
        btn.scrollIntoView({ block: 'nearest' });   // large text: the column may scroll
    },

    continueOn: function () {
        if (!this.made) return;
        window.mf_context_album = { artist: this.made.artist, album: this.made.album };
        window.mfAdvanceWorkflow('unpack_convert', this.made.folder);
    },

    // --- [ CHECK THE CUTS ] --------------------------------------------------
    showCuts: function (cuts) {
        this.cuts = cuts;
        const $ = (id) => document.getElementById(id);
        // Every note is about where THIS track starts, i.e. the change from
        // the track before (John, 2026-11-16: "Check" under track 6 read as
        // possibly being about the end of 6 or the start of 7).
        const NOTE = {
            start: () => ['Starts at the beginning of the video.', false],
            chapter: () => ["Start taken from the video's chapters.", false],
            times: () => ["Start taken from the times in the video's description.", false],
            gap: (n) => [`Starts after a clear gap following track ${n - 1}.`, false],
            faint: (n) => [`Check where track ${n} starts: there's only a faint gap after track ${n - 1}. Use Play start to hear the change.`, true],
            length: (n) => [`Check where track ${n} starts: there's no gap after track ${n - 1}, so the start is worked out from the track lengths. Use Play start to hear the change.`, true],
            guess: (n) => [`Check where track ${n} starts: no gap was found, so this is a guess. Use Play start to hear it, and correct the time.`, true]
        };
        const check = cuts.rows.filter((r, i) => NOTE[r.how]?.(i + 1)[1]).length;
        $('yt-review-intro').textContent =
            `${cuts.rows.length} songs in ${this.clock(cuts.duration)}${cuts.basis ? `, placed using ${cuts.basis}` : ''}. ` +
            'Each time is where that track starts (minutes:seconds). Play start plays from 4 seconds before it to 6 seconds after, so you hear the previous track end and this one begin.' +
            (check ? ` ${check} ${check === 1 ? 'start needs' : 'starts need'} checking: look for “Check”.` : '');
        $('yt-cuts').replaceChildren(...cuts.rows.map((r, i) => {
            const li = document.createElement('li');
            li.className = 'yt-cut';
            const num = document.createElement('span');
            num.className = 'yt-num';
            num.textContent = `${i + 1}.`;
            num.setAttribute('aria-hidden', 'true');
            const title = document.createElement('input');
            title.type = 'text';
            title.className = 'yt-title-in';
            title.value = r.title;
            title.setAttribute('aria-label', `Track ${i + 1} title`);
            const start = document.createElement('input');
            start.type = 'text';
            start.className = 'yt-start';
            start.value = this.clock(r.start, true);
            start.readOnly = i === 0;
            start.inputMode = 'decimal';
            start.spellcheck = false;
            start.setAttribute('aria-label', `Track ${i + 1} starts at`);
            const play = document.createElement('button');
            play.type = 'button';
            play.className = 'mf-button-gold-fixed yt-play';
            play.dataset.n = String(i + 1);
            this.setPlayLabel(play, false);
            const note = document.createElement('p');
            const [text, warn] = NOTE[r.how]?.(i + 1) || ['', false];
            note.className = `yt-note${warn ? ' is-check' : ''}`;
            note.id = `yt-cut-note-${i}`;
            note.textContent = text;
            start.setAttribute('aria-describedby', note.id);
            li.append(num, title, start, play, note);
            return li;
        }));
        this.setStage('album-review');
        document.querySelector('.yt-scroll').scrollTop = 0;
        $('yt-review-h').focus();
        window.MFAnnounce($('yt-review-intro').textContent);
    },

    /** Start times must be times, and each after the one before. */
    checkStarts: function (announce = false) {
        const inputs = [...document.querySelectorAll('#yt-cuts .yt-start')];
        let prev = -1, prevAt = -1, firstBad = null;
        const dur = this.cuts?.duration || Infinity;
        inputs.forEach((inp, i) => {
            const v = this.parseClock(inp.value);
            const ok = v !== null && v > prev && v < dur;
            const note = document.getElementById(`yt-cut-note-${i}`);
            if (!ok) {
                inp.setAttribute('aria-invalid', 'true');
                note.dataset.was ??= note.textContent;
                note.textContent = v === null ? 'Error: type a time like 4:31.5.'
                    : v >= dur ? `Error: the video is only ${this.clock(dur)} long.`
                    : `Error: this is before track ${prevAt + 1} (${inputs[prevAt].value}). Each track has to start after the one before it.`;
                note.classList.add('is-check');
                firstBad ??= inp;
            } else {
                inp.setAttribute('aria-invalid', 'false');
                if (note.dataset.was !== undefined) {
                    note.textContent = note.dataset.was;
                    delete note.dataset.was;
                    note.classList.toggle('is-check', note.textContent.startsWith('Check'));
                }
                prev = v;
                prevAt = i;
            }
        });
        if (firstBad && announce) {
            firstBad.focus();
            window.MFAnnounce(`Error: ${firstBad.getAttribute('aria-label')}: ${firstBad.parentElement.querySelector('.yt-note').textContent}`, { urgent: true });
        }
        return !firstBad;
    },

    play: function (btn) {
        if (this.playing === btn) { this.stopPlaying(); return; }
        this.stopPlaying();
        const li = btn.closest('.yt-cut');
        const t = this.parseClock(li.querySelector('.yt-start').value);
        if (t === null) { this.checkStarts(true); return; }
        if (!this.audio) {
            this.audio = new Audio();
            this.audio.preload = 'auto';
            this.audio.addEventListener('timeupdate', () => {
                if (this.playing && this.audio.currentTime >= this.stopAt) this.stopPlaying();
            });
            this.audio.addEventListener('ended', () => this.stopPlaying());
        }
        const src = `/run_tool_logic/youtube_mp3/preview?id=${encodeURIComponent(this.info.id)}`;
        if (!this.audio.src.endsWith(src)) this.audio.src = src;
        const from = Math.max(0, t - 4);
        this.stopAt = t + 6;
        this.audio.currentTime = from;
        this.audio.play().catch((e) => window.MFAnnounce(`Error: it couldn't play: ${e.message}`, { urgent: true }));
        this.playing = btn;
        this.setPlayLabel(btn, true);
    },

    stopPlaying: function () {
        if (this.audio) this.audio.pause();
        if (this.playing) this.setPlayLabel(this.playing, false);
        this.playing = null;
    },

    /** The visible words start the accessible name (WCAG 2.5.3 Label in Name). */
    setPlayLabel: function (btn, playing) {
        btn.textContent = playing ? 'Stop' : 'Play start';
        btn.setAttribute('aria-label', playing ? `Stop playing track ${btn.dataset.n}` : `Play start of track ${btn.dataset.n}`);
    },

    // --- [ HELPERS ] ---------------------------------------------------------
    clock: function (s, tenths = false) {
        s = Math.max(0, Number(s) || 0);
        const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
        const sec = tenths ? (s % 60).toFixed(1).padStart(4, '0') : String(Math.floor(s % 60)).padStart(2, '0');
        return h ? `${h}:${String(m).padStart(2, '0')}:${sec}` : `${m}:${sec}`;
    },

    parseClock: function (text) {
        const m = String(text).trim().match(/^(?:(\d+):)?(\d{1,2}):(\d{1,2}(?:\.\d+)?)$/);
        if (!m) return null;
        const v = (Number(m[1] || 0) * 3600) + Number(m[2]) * 60 + Number(m[3]);
        return Number(m[3]) >= 60 ? null : v;
    },

    /** A step with no measurable progress: a full, shimmering bar, announced as indeterminate. */
    setBusy: function (label) {
        const bar = document.getElementById('yt-progress-bar');
        const fill = document.getElementById('yt-progress-fill');
        const text = document.getElementById('yt-progress-label');
        if (fill) fill.style.width = '100%';
        if (text) text.textContent = label;
        if (bar) {
            bar.removeAttribute('aria-valuenow');
            bar.setAttribute('aria-valuetext', label);
        }
    },

    setProgress: function (percent, label, busy = false) {
        if (busy) { this.setBusy(label); return; }
        const pct = Math.max(0, Math.min(100, Number(percent) || 0));
        const bar = document.getElementById('yt-progress-bar');
        const fill = document.getElementById('yt-progress-fill');
        const text = document.getElementById('yt-progress-label');
        if (fill) fill.style.width = `${pct}%`;
        if (text && label) text.textContent = label;
        if (bar) {
            bar.setAttribute('aria-valuenow', String(Math.round(pct)));
            if (label) bar.setAttribute('aria-valuetext', `${label} (${Math.round(pct)}%)`);
        }
    }
};
/* --- END OF FILE youtube_mp3.js --- */
