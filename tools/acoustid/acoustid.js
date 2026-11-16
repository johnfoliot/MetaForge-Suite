/* --- START OF FILE acoustid.js --- */
/**
 * MetaForge Studio: AcoustID Manager
 * v2 (2026-11-16): counts for both steps, event-stream runs (MFEvents),
 * Stop, and an "OK to leave?" question while a run is going.
 * The tool's script loads once per page; init() runs on every visit.
 */
window.metaforge = window.metaforge || {};

window.metaforge.acoustid = {
    running: false,

    init: function () {
        const $ = (id) => document.getElementById(id);
        $('aid-submit-btn').addEventListener('click', () => this.run('submit'));
        $('aid-resolve-btn').addEventListener('click', () => this.run('resolve'));
        $('aid-stop').addEventListener('click', () => this.stop());
        // Left mid-run and came back: the old run is still winding down.
        if (this.running) {
            $('aid-fieldset').disabled = true;
            this.setProgress(0, 'The last run is finishing. Come back in a moment.');
        }
        this.refresh();
    },

    refresh: async function () {
        const $ = (id) => document.getElementById(id);
        let s;
        try { s = await (await fetch('/run_tool_logic/acoustid/status')).json(); }
        catch (e) { $('aid-pending-count').textContent = "The lists couldn't be read."; return; }
        const n = (k, one, many) => `${s[k] || 'No'} ${s[k] === 1 ? one : many}`;
        $('aid-pending-count').textContent = n('pending', 'track is waiting to be submitted.', 'tracks are waiting to be submitted.');
        $('aid-submitted-count').textContent = n('submitted', 'submitted track is waiting for its AcoustID.', 'submitted tracks are waiting for their AcoustIDs.');

        const missing = [!s.has_app_key && 'application key', !s.has_user_key && 'user key'].filter(Boolean);
        const keyNote = $('aid-key-note');
        keyNote.hidden = !missing.length;
        keyNote.textContent = missing.length
            ? `Submitting needs your AcoustID ${missing.join(' and ')}. Add ${missing.length === 1 ? 'it' : 'them'} in Settings > Configuration & keys.`
            : '';

        const nf = $('aid-notfound-note');
        nf.hidden = !s.not_found;
        nf.replaceChildren();
        if (s.not_found) {
            const code = document.createElement('code');
            code.textContent = 'data\\acoustid\\not_found.txt';
            nf.append(`${s.not_found} file${s.not_found === 1 ? '' : 's'} couldn't be found (moved or renamed) and ${s.not_found === 1 ? 'was' : 'were'} set aside in `, code, '.');
        }
    },

    run: async function (action) {
        if (this.running) return;
        const $ = (id) => document.getElementById(id);
        const log = $('aid-console');
        this.running = true;
        $('aid-fieldset').disabled = true;
        $('aid-stop').disabled = false;
        log.replaceChildren();
        this.setProgress(0, action === 'submit' ? 'Starting to submit…' : 'Starting to check…');
        window.MFLeaveGuard?.set('acoustid', () => this.askLeave());
        try {
            const res = await fetch(`/run_tool_logic/acoustid/${action}`, { method: 'POST' });
            if (res.status === 409) throw new Error((await res.json()).message);
            await window.MFEvents.read(res, {
                log,
                onSignal: (name, data) => { if (name === 'progress') this.setProgress(data.percent, data.label); }
            });
        } catch (err) {
            window.MFEvents.render(log, { kind: 'error', text: `The run stopped: ${err.message}` });
            window.MFAnnounce(`Error: the run stopped: ${err.message}`, { urgent: true });
        } finally {
            this.running = false;
            window.MFLeaveGuard?.clear('acoustid');
            // The tool may have been left mid-run (and maybe come back to: a
            // fresh screen, not `log`'s), so look the screen up again.
            if ($('aid-console')) {
                $('aid-fieldset').disabled = false;
                $('aid-stop').disabled = true;
                $('aid-stop').textContent = 'Stop';
                (action === 'submit' ? $('aid-submit-btn') : $('aid-resolve-btn')).focus();
                this.refresh();
            }
        }
    },

    stop: async function () {
        const btn = document.getElementById('aid-stop');
        if (btn) { btn.disabled = true; btn.textContent = 'Stopping…'; }
        window.MFAnnounce('Stopping after the current track.');
        try { await fetch('/run_tool_logic/acoustid/stop', { method: 'POST' }); } catch (e) { /* the run ends anyway */ }
    },

    askLeave: function () {
        const dlg = document.getElementById('aid-leave');
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

    setProgress: function (percent, label) {
        const pct = Math.max(0, Math.min(100, Number(percent) || 0));
        const bar = document.getElementById('aid-progress-bar');
        const fill = document.getElementById('aid-progress-fill');
        const text = document.getElementById('aid-progress-label');
        if (fill) fill.style.width = `${pct}%`;
        if (text && label) text.textContent = label;
        if (bar) {
            bar.setAttribute('aria-valuenow', String(Math.round(pct)));
            if (label) bar.setAttribute('aria-valuetext', `${label} (${Math.round(pct)}%)`);
        }
    }
};
/* --- END OF FILE acoustid.js --- */
