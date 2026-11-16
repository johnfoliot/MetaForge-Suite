/* --- START OF FILE music-sharing.js --- */
/**
 * MetaForge Studio: Music Sharing
 * v2 (2026-11-16): choose a track (native picker, MP3 filter), its details
 * and a true preview, "a video with this name exists" dialog (Cancel /
 * Keep both / Replace it), event-stream render (MFEvents) with FFmpeg's real
 * progress, Stop, "OK to leave?" while rendering, and Show the video.
 * The tool's script loads once per page; init() runs on every visit.
 */
window.metaforge = window.metaforge || {};

window.metaforge['music-sharing'] = {
    running: false,
    track: null,      // the last /info answer for the chosen MP3
    lastVideo: '',    // full path of the video made this visit (for Show)

    init: function () {
        const $ = (id) => document.getElementById(id);
        $('shr-pick').addEventListener('click', () => this.pick());
        $('shr-form').addEventListener('submit', (e) => { e.preventDefault(); this.make(); });
        $('shr-stop').addEventListener('click', () => this.stop());
        $('shr-show').addEventListener('click', () => this.show());
        if (this.running) {
            $('shr-make').disabled = true;
            $('shr-pick').disabled = true;
            this.setProgress(0, 'The last video is still being made. Come back in a moment.');
        } else if (this.track) {
            this.showTrack(this.track);
        }
        this.updateShow();
    },

    pick: async function () {
        if (this.running) return;
        let data;
        try { data = await (await fetch('/select_file?kind=audio')).json(); }
        catch (e) { window.MFAnnounce("The file picker couldn't be opened.", { urgent: true }); return; }
        if (!data.path) return;   // cancelled
        await this.loadTrack(data.path);
    },

    loadTrack: async function (path) {
        const $ = (id) => document.getElementById(id);
        let info;
        try {
            info = await (await fetch('/run_tool_logic/music-sharing/info', {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path })
            })).json();
        } catch (e) { info = { status: 'error', message: "The track couldn't be read." }; }
        if (!$('shr-form')) return;   // left the tool meanwhile
        if (info.status !== 'ok') {
            this.track = null;
            $('shr-path').value = path;
            $('shr-details').hidden = true;
            $('shr-make').disabled = true;
            this.setPicture(null);
            window.MFEvents.render($('shr-console'), { kind: 'error', text: info.message });
            window.MFAnnounce(`Error: ${info.message}`, { urgent: true });
            return;
        }
        this.track = info;
        this.lastVideo = '';
        this.showTrack(info);
        this.setProgress(0, 'Standing by');
        $('shr-console').replaceChildren();
        window.MFEvents.render($('shr-console'), { kind: 'info', text: `Chosen: ${info.name}` });
        window.MFAnnounce(`${info.title} chosen. Make the video when you're ready.`);
        this.updateShow();
        $('shr-make').focus();
    },

    showTrack: function (t) {
        const $ = (id) => document.getElementById(id);
        $('shr-path').value = t.path;
        $('shr-d-title').textContent = t.title || '—';
        $('shr-d-artist').textContent = t.artist || '—';
        $('shr-d-album').textContent = t.album ? (t.year ? `${t.album} (${t.year})` : t.album) : '—';
        $('shr-d-length').textContent = t.length ? this.clock(t.length) : 'Unknown';
        $('shr-d-video').textContent = t.video_exists ? `${t.video_name} (one already exists)` : t.video_name;
        $('shr-details').hidden = false;
        $('shr-make').disabled = this.running;
        this.setPicture(t);
    },

    setPicture: function (t) {
        const pic = document.getElementById('shr-pic');
        if (t && t.picture_url) {
            pic.src = t.picture_url;
            pic.hidden = false;
        } else {
            pic.removeAttribute('src');
            pic.hidden = true;
        }
        document.getElementById('shr-d-picture').textContent = !t ? '' : {
            embedded: 'The cover stored in the MP3',
            folder: 'folder.jpg from the album folder',
            none: 'None found, so the video is a plain black square'
        }[t.picture] || '';
    },

    make: async function () {
        if (this.running || !this.track) return;
        let existing = 'replace';
        if (this.track.video_exists) {
            existing = await this.askExisting();
            if (existing === 'cancel' || !existing) return;
        }
        this.render(existing);
    },

    askExisting: function () {
        const dlg = document.getElementById('shr-exists');
        const t = this.track;
        document.getElementById('shr-exists-text').textContent =
            `${t.video_name} is already in your Videos folder. Replace it, or keep both and save the new one as ${t.kept_name}?`;
        return new Promise((resolve) => {
            dlg.addEventListener('close', () => resolve(dlg.returnValue || 'cancel'), { once: true });
            dlg.returnValue = '';
            dlg.showModal();
        });
    },

    render: async function (existing) {
        const $ = (id) => document.getElementById(id);
        const log = $('shr-console');
        this.running = true;
        $('shr-make').disabled = true;
        $('shr-pick').disabled = true;
        $('shr-stop').disabled = false;
        log.replaceChildren();
        this.setProgress(0, 'Starting…');
        window.MFLeaveGuard?.set('music-sharing', () => this.askLeave());
        let made = false;
        try {
            const res = await fetch('/run_tool_logic/music-sharing/render', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: this.track.path, existing })
            });
            if (res.status === 409) throw new Error((await res.json()).message);
            await window.MFEvents.read(res, {
                log,
                onSignal: (name, data) => {
                    if (name === 'progress') this.setProgress(data.percent, data.label);
                    if (name === 'video_ready') { this.lastVideo = data.path; made = true; }
                }
            });
        } catch (err) {
            window.MFEvents.render(log, { kind: 'error', text: `The video couldn't be made: ${err.message}` });
            window.MFAnnounce(`Error: the video couldn't be made: ${err.message}`, { urgent: true });
        } finally {
            this.running = false;
            window.MFLeaveGuard?.clear('music-sharing');
            // Look the screen up again: if the tool was left and come back to
            // mid-render, it's a fresh screen, not `log`'s.
            if ($('shr-console')) {
                $('shr-stop').disabled = true;
                $('shr-stop').textContent = 'Stop';
                $('shr-pick').disabled = false;
                if (!made) this.setProgress(0, $('shr-progress-label').textContent === 'Stopped' ? 'Stopped' : 'Not finished');
                // Refresh "one already exists" (and the Keep-both name) for the next go.
                if (this.track) await this.loadTrackQuietly(this.track.path);
                this.updateShow();
                (made ? $('shr-show') : $('shr-make')).focus();
            }
        }
    },

    loadTrackQuietly: async function (path) {
        try {
            const info = await (await fetch('/run_tool_logic/music-sharing/info', {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path })
            })).json();
            if (info.status === 'ok' && document.getElementById('shr-form')) { this.track = info; this.showTrack(info); }
        } catch (e) { /* keep what's shown */ }
    },

    stop: async function () {
        const btn = document.getElementById('shr-stop');
        if (btn) { btn.disabled = true; btn.textContent = 'Stopping…'; }
        window.MFAnnounce('Stopping.');
        try { await fetch('/run_tool_logic/music-sharing/stop', { method: 'POST' }); } catch (e) { /* the render ends anyway */ }
    },

    askLeave: function () {
        const dlg = document.getElementById('shr-leave');
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

    show: async function () {
        try {
            await fetch('/run_tool_logic/music-sharing/show', {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path: this.lastVideo })
            });
        } catch (e) { window.MFAnnounce("The folder couldn't be opened.", { urgent: true }); }
    },

    updateShow: function () {
        const btn = document.getElementById('shr-show');
        if (btn) btn.textContent = this.lastVideo ? 'Show the video' : 'Open the videos folder';
    },

    clock: function (secs) {
        const s = Math.round(secs);
        return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
    },

    setProgress: function (percent, label) {
        const pct = Math.max(0, Math.min(100, Number(percent) || 0));
        const bar = document.getElementById('shr-progress-bar');
        const fill = document.getElementById('shr-progress-fill');
        const text = document.getElementById('shr-progress-label');
        if (fill) fill.style.width = `${pct}%`;
        if (text && label) text.textContent = label;
        if (bar) {
            bar.setAttribute('aria-valuenow', String(Math.round(pct)));
            if (label) bar.setAttribute('aria-valuetext', `${label} (${Math.round(pct)}%)`);
        }
    }
};
/* --- END OF FILE music-sharing.js --- */
