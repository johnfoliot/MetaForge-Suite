/* --- START OF FILE repair.js --- */
/**
 * MetaForge Studio: Audio Repair
 * v2 (2026-11-16): the list (with Remove), "Repair these files?" dialog,
 * event-stream run (MFEvents), Stop, and "OK to leave?" while running.
 * The tool's script loads once per page; init() runs on every visit.
 */
window.metaforge = window.metaforge || {};

window.metaforge.repair = {
    running: false,
    count: 0,

    init: function () {
        const $ = (id) => document.getElementById(id);
        $('rep-run-btn').addEventListener('click', () => this.confirmRun());
        $('rep-stop').addEventListener('click', () => this.stop());
        $('rep-list').addEventListener('click', (e) => {
            const b = e.target.closest('button[data-path]');
            if (b) this.remove(b.dataset.path, b);
        });
        if (this.running) {
            $('rep-run-btn').disabled = true;
            this.setProgress(0, 'The last run is finishing. Come back in a moment.');
        }
        this.loadQueue();
    },

    loadQueue: async function () {
        const $ = (id) => document.getElementById(id);
        let data;
        try { data = await (await fetch('/run_tool_logic/repair/get_queue')).json(); }
        catch (e) { $('rep-count').textContent = "The list couldn't be read."; return; }
        if (!$('rep-list')) return;   // left the tool meanwhile
        const q = data.queue || [];
        this.count = q.length;
        $('rep-count').textContent = q.length ? `${q.length} file${q.length === 1 ? '' : 's'}` : 'No files';
        $('rep-empty').hidden = q.length > 0;
        $('rep-list').replaceChildren(...q.map((item) => {
            const li = document.createElement('li');
            li.className = 'rep-item';
            const name = document.createElement('span');
            name.className = 'rep-name';
            name.textContent = item.name;
            const meta = document.createElement('span');
            meta.className = 'rep-meta';
            meta.textContent = `${item.album} · ${item.reason}`;
            if (!item.exists) {
                const miss = document.createElement('span');
                miss.className = 'rep-missing';
                miss.textContent = ' · File not found';
                meta.append(miss);
            }
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'mf-button-gold-fixed';
            btn.textContent = 'Remove';
            btn.dataset.path = item.path;
            btn.setAttribute('aria-label', `Remove ${item.name} from the list`);
            li.append(name, btn, meta);
            return li;
        }));
        $('rep-run-btn').disabled = this.running || !q.length;
        $('rep-run-btn').textContent = q.length ? `Repair ${q.length === 1 ? 'the file' : `all ${q.length} files`}` : 'Repair the files';

        const nf = $('rep-notfound');
        nf.hidden = !data.not_found;
        nf.replaceChildren();
        if (data.not_found) {
            const code = document.createElement('code');
            code.textContent = 'data\\repair\\not_found.txt';
            nf.append(`${data.not_found} file${data.not_found === 1 ? '' : 's'} couldn't be found (moved or renamed) and ${data.not_found === 1 ? 'was' : 'were'} set aside in `, code, '.');
        }
    },

    remove: async function (path, btn) {
        const items = [...document.querySelectorAll('#rep-list button[data-path]')];
        const at = items.indexOf(btn);
        const name = btn.closest('.rep-item')?.querySelector('.rep-name')?.textContent || 'The file';
        const res = await fetch('/run_tool_logic/repair/remove', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path })
        });
        if (!res.ok) { window.MFAnnounce((await res.json()).message || "It couldn't be removed.", { urgent: true }); return; }
        await this.loadQueue();
        window.MFAnnounce(`${name} removed from the list.`);
        // Focus the next file's Remove (or the previous one, or Repair).
        const left = [...document.querySelectorAll('#rep-list button[data-path]')];
        (left[Math.min(at, left.length - 1)] || document.getElementById('rep-run-btn')).focus();
    },

    confirmRun: function () {
        const dlg = document.getElementById('rep-confirm');
        document.getElementById('rep-confirm-count').textContent =
            `${this.count} file${this.count === 1 ? '' : 's'} will be repaired, one at a time.`;
        dlg.returnValue = '';
        dlg.addEventListener('close', () => { if (dlg.returnValue === 'run') this.run(); }, { once: true });
        dlg.showModal();
    },

    run: async function () {
        if (this.running) return;
        const $ = (id) => document.getElementById(id);
        const log = $('rep-console');
        this.running = true;
        $('rep-run-btn').disabled = true;
        $('rep-stop').disabled = false;
        $('rep-list').querySelectorAll('button').forEach((b) => { b.disabled = true; });
        log.replaceChildren();
        this.setProgress(0, 'Starting…');
        window.MFLeaveGuard?.set('repair', () => this.askLeave());
        try {
            const res = await fetch('/run_tool_logic/repair/run', { method: 'POST' });
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
            window.MFLeaveGuard?.clear('repair');
            if (document.body.contains(log)) {
                $('rep-stop').disabled = true;
                $('rep-stop').textContent = 'Stop';
                await this.loadQueue();
                ($('rep-run-btn').disabled ? $('rep-list-h') : $('rep-run-btn')).focus?.();
            }
        }
    },

    stop: async function () {
        const btn = document.getElementById('rep-stop');
        if (btn) { btn.disabled = true; btn.textContent = 'Stopping…'; }
        window.MFAnnounce('Stopping after the current file.');
        try { await fetch('/run_tool_logic/repair/stop', { method: 'POST' }); } catch (e) { /* the run ends anyway */ }
    },

    askLeave: function () {
        const dlg = document.getElementById('rep-leave');
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
        const bar = document.getElementById('rep-progress-bar');
        const fill = document.getElementById('rep-progress-fill');
        const text = document.getElementById('rep-progress-label');
        if (fill) fill.style.width = `${pct}%`;
        if (text && label) text.textContent = label;
        if (bar) {
            bar.setAttribute('aria-valuenow', String(Math.round(pct)));
            if (label) bar.setAttribute('aria-valuetext', `${label} (${Math.round(pct)}%)`);
        }
    }
};
/* --- END OF FILE repair.js --- */
