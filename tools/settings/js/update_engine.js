// --- START OF FILE update_engine.js ---
/**
 * Settings > Updates. v2 (2026-11-15): shows this version and the last
 * check; announces test mode; release notes are plain text (textContent);
 * the link is GitHub-only (checked server-side too); Dismiss never changes
 * the app's version; required updates can't be dismissed.
 */
(function () {
    const S = window.metaforge.settings;
    const $ = (id) => document.getElementById(id);
    let latest = null;

    S.updates = {
        load: async function () {
            const btn = $('set-upd-check');
            if (!btn) return;
            if (!btn.dataset.wired) {
                btn.dataset.wired = 'true';
                btn.addEventListener('click', () => this.run());
                $('set-upd-open').addEventListener('click', () => { if (latest && latest.url) window.metaforge.openExternalLink(latest.url); });
                $('set-upd-dismiss').addEventListener('click', () => this.dismiss());
            }
            try {
                const r = await (await fetch('/run_tool_logic/settings/last_update_check')).json();
                $('set-upd-current').textContent = r.current_version || '—';
                $('set-upd-last').textContent = r.last_checked || 'Never';
                $('set-upd-test').hidden = !r.test_mode;
            } catch (e) { /* the check button still works */ }
        },

        run: async function () {
            const btn = $('set-upd-check');
            btn.disabled = true;
            $('set-upd-card').hidden = true;
            S.say('set-upd-status', 'Checking for updates…');
            try {
                const r = await (await fetch('/run_tool_logic/settings/check_updates')).json();
                $('set-upd-current').textContent = r.current_version || '—';
                if (r.last_checked) $('set-upd-last').textContent = r.last_checked;
                $('set-upd-test').hidden = !r.test_mode;
                if (r.status === 'error') { S.say('set-upd-status', r.message, 'error'); return; }
                latest = r;
                if (r.status === 'update_available') {
                    this.show(r, true);
                    S.say('set-upd-status', `Version ${r.latest_version} is available.`, r.priority === 'required' ? 'warning' : 'ok');
                } else if (r.dismissed_version) {
                    this.show(r, false);
                    S.say('set-upd-status', `Version ${r.dismissed_version} is available, but you chose not to be reminded about it.`);
                } else {
                    S.say('set-upd-status', `You're up to date (version ${r.current_version}).`, 'ok');
                }
            } catch (e) {
                S.say('set-upd-status', `The check didn't finish: ${e.message}`, 'error');
            } finally {
                btn.disabled = false;
            }
        },

        show: function (r, canDismiss) {
            $('set-upd-title').textContent = r.title;
            $('set-upd-released').textContent = r.released ? `Released ${r.released}` : '';
            $('set-upd-released').hidden = !r.released;
            $('set-upd-required').hidden = r.priority !== 'required';
            $('set-upd-notes').textContent = r.notes || '';
            $('set-upd-open').hidden = !r.url;
            $('set-upd-nolink').hidden = !!r.url;
            $('set-upd-dismiss').hidden = !canDismiss || r.priority === 'required';
            $('set-upd-card').hidden = false;
        },

        dismiss: async function () {
            if (!latest) return;
            try {
                const r = await (await fetch('/run_tool_logic/settings/dismiss_update', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ version: latest.latest_version })
                })).json();
                if (r.status !== 'success') throw new Error(r.message || 'unknown error');
                $('set-upd-dismiss').hidden = true;
                $('set-upd-check').focus();
                S.say('set-upd-status', `OK. You won't be reminded about ${latest.latest_version} again; a later version will still be announced.`, 'ok');
            } catch (e) {
                S.say('set-upd-status', `That couldn't be saved: ${e.message}`, 'error');
            }
        }
    };
})();
// --- END OF FILE update_engine.js ---
