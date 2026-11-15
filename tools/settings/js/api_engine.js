// --- START OF FILE api_engine.js ---
/**
 * Settings > Configuration & keys. v2 (2026-11-15) rewrite.
 *  - Plain-language labels; the .env name is shown as a hint (John).
 *  - MF_FILING_POLICY is a 3-way choice; MF_UNPACKER_CONSENT a checkbox.
 *  - DOM-built (1.x put values straight into value="" HTML) with theme
 *    tokens (1.x hard-coded white fields at 12.8px).
 *  - Only changed settings are sent; the server keeps the file's notes and
 *    order. Keys are not masked for now: hiding them without a login would
 *    be false security (John; a Settings login is on the to-do list).
 */
(function () {
    const S = window.metaforge.settings;
    const $ = (id) => document.getElementById(id);
    const el = (tag, props = {}, ...kids) => { const n = Object.assign(document.createElement(tag), props); n.append(...kids); return n; };
    let loaded = {};

    // kind: text | code | select | consent. link: [text, url] for "Get a key".
    const GROUPS = [
        { legend: 'Your library', fields: [
            { key: 'LIBRARY_ROOT', label: 'Music library folder', kind: 'code', hint: 'The top folder of your music library (for example, F:\\).' },
            { key: 'MF_FILING_POLICY', label: 'How your library folders are organised', kind: 'select', options: [
                ['BASIC', 'Basic: album folders at the top level'],
                ['STANDARD', 'Standard: Artist, then Album'],
                ['ENHANCED', 'Enhanced: Category, then Artist, then Album']] },
            { key: 'USER_EMAIL', label: 'Your email address (for MusicBrainz)', kind: 'text', type: 'email', hint: 'Sent to MusicBrainz with each lookup, as they ask, so they can contact you about heavy use.' }
        ]},
        { legend: 'Unpack & Convert', fields: [
            { key: 'MF_UNPACKER_CONSENT', label: 'Unpack & Convert may delete original archives and old metadata', kind: 'consent', hint: 'Turn this off to be asked again the next time you use Unpack & Convert.' },
            { key: 'MF_UNPACKER_LOCKED_CATEGORY', label: 'Locked filing category', kind: 'text', hint: 'Leave empty for no lock. Set from Unpack & Convert\u2019s lock button.' },
            { key: 'MF_UNPACKER_LOCKED_ARTIST', label: 'Locked filing artist', kind: 'text', hint: 'Leave empty for no lock. Set from Unpack & Convert\u2019s lock button.' }
        ]},
        { legend: 'Service keys', fields: [
            { key: 'ACOUSTID_APPLICATION_KEY', label: 'AcoustID application key', kind: 'code', hint: 'Used for every audio-fingerprint lookup.', link: ['Get one at acoustid.org', 'https://acoustid.org/my-applications'] },
            { key: 'ACOUSTID_USER_KEY', label: 'AcoustID user key', kind: 'code', hint: 'Only needed to submit new fingerprints.', link: ['Shown at acoustid.org once you\u2019re signed in', 'https://acoustid.org/api-key'] },
            { key: 'GEMINI_KEY', label: 'Google Gemini API key', kind: 'code', hint: 'Used by Intelli-Tagger and Bio Builder.', link: ['Get one at Google AI Studio', 'https://aistudio.google.com/app/api-keys'] },
            { key: 'DISCOGS_TOKEN', label: 'Discogs personal token', kind: 'code', hint: 'Used for credits and artist photos.', link: ['Get one at Discogs Developers', 'https://www.discogs.com/settings/developers'] }
        ]}
    ];

    function field(f, value) {
        const id = `set-env-${f.key}`, hintId = `${id}-hint`;
        const hint = el('p', { className: 'set-hint', id: hintId },
            ...(f.hint ? [f.hint + ' '] : []), 'Stored as ', el('code', { textContent: f.key }), '.');
        if (f.link) {
            const a = el('a', { href: f.link[1], textContent: f.link[0] });
            a.addEventListener('click', (e) => { e.preventDefault(); window.metaforge.openExternalLink(a.href); });
            hint.append(' ', a, '.');
        }
        if (f.kind === 'consent') {
            const box = el('input', { type: 'checkbox', id, checked: String(value).toUpperCase() === 'TRUE' });
            box.dataset.key = f.key;
            box.setAttribute('aria-describedby', hintId);
            return el('div', { className: 'set-field' }, el('div', { className: 'set-check' }, box, el('label', { htmlFor: id, textContent: f.label })), hint);
        }
        let control;
        if (f.kind === 'select') {
            control = el('select', { className: 'set-select', id });
            const v = String(value || 'STANDARD').toUpperCase();
            for (const [val, text] of f.options) control.append(el('option', { value: val, textContent: text, selected: val === v }));
        } else {
            control = el('input', { type: f.type || 'text', className: 'set-input' + (f.kind === 'code' ? ' is-code' : ''), id, value: value || '', autocomplete: 'off', spellcheck: false });
        }
        control.dataset.key = f.key;
        control.setAttribute('aria-describedby', hintId);
        return el('div', { className: 'set-field' }, el('label', { htmlFor: id, textContent: f.label }), control, hint);
    }

    function valueOf(c) {
        if (c.type === 'checkbox') return c.checked ? 'TRUE' : 'FALSE';
        return c.value.trim();
    }

    S.api = {
        load: async function () {
            const box = $('api-form-container');
            const form = $('set-config-form');
            if (!box || !form) return;
            if (!form.dataset.wired) {
                form.dataset.wired = 'true';
                form.addEventListener('submit', (e) => { e.preventDefault(); this.save(); });
            }
            try {
                loaded = await (await fetch('/run_tool_logic/settings/get_env')).json();
                this.render();
            } catch (e) {
                S.say('set-config-status', `The configuration couldn't be loaded: ${e.message}`, 'error');
            }
        },

        render: function () {
            const known = new Set(GROUPS.flatMap(g => g.fields.map(f => f.key)));
            const sets = GROUPS.map(g => el('fieldset', { className: 'set-fieldset' },
                el('legend', { textContent: g.legend }), ...g.fields.map(f => field(f, loaded[f.key]))));
            const others = Object.keys(loaded).filter(k => !known.has(k)).sort();
            if (others.length) {
                sets.push(el('fieldset', { className: 'set-fieldset' }, el('legend', { textContent: 'Other settings' }),
                    ...others.map(k => field({ key: k, label: k, kind: 'code' }, loaded[k]))));
            }
            $('api-form-container').replaceChildren(...sets);
        },

        save: async function () {
            const changes = {};
            const email = $('set-env-USER_EMAIL');
            if (email && email.value.trim() && !email.checkValidity()) {
                email.setAttribute('aria-invalid', 'true');
                email.focus();
                S.say('set-config-status', 'That email address doesn\u2019t look complete (for example name@example.com).', 'error');
                return;
            }
            if (email) email.removeAttribute('aria-invalid');
            for (const c of document.querySelectorAll('#api-form-container [data-key]')) {
                const k = c.dataset.key, v = valueOf(c);
                const before = k in loaded ? String(loaded[k]) : null;
                const same = before === null ? (v === '' || (c.type === 'checkbox' && v === 'FALSE') || (c.tagName === 'SELECT' && v === 'STANDARD'))
                                             : (c.type === 'checkbox' || c.tagName === 'SELECT' ? before.toUpperCase() === v : before === v);
                if (!same) changes[k] = v;
            }
            const n = Object.keys(changes).length;
            if (!n) { S.say('set-config-status', 'Nothing has changed, so there was nothing to save.'); return; }
            try {
                const r = await (await fetch('/run_tool_logic/settings/save_env', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(changes)
                })).json();
                if (r.status !== 'success') throw new Error(r.message || 'unknown error');
                Object.assign(loaded, changes);
                S.say('set-config-status', `Saved ${n} ${n === 1 ? 'setting' : 'settings'}.`, 'ok');
            } catch (e) {
                S.say('set-config-status', `The configuration wasn't saved: ${e.message}`, 'error');
            }
        }
    };
})();
// --- END OF FILE api_engine.js ---
