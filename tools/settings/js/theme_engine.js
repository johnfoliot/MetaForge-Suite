// --- START OF FILE theme_engine.js ---
/**
 * Settings > Theme (the list). v2: a native radio group of cards. Choosing
 * a card previews the theme (its own logo comes with it via applyTheme);
 * Save theme keeps it, as theme_id. Themes you made (Create a theme,
 * js/theme_maker.js) are listed after the built-in ones with Edit and
 * Delete. Theme folders (2026-11-17): themes are picked by id (folder
 * name); a folder that fails its checks isn't offered, and is listed in a
 * closed "isn't offered" disclosure with the reason.
 */
(function () {
    const S = window.metaforge.settings;
    const $ = (id) => document.getElementById(id);
    const el = (tag, props = {}, ...kids) => { const n = Object.assign(document.createElement(tag), props); n.append(...kids); return n; };
    const LABELS = {
        '--bg-main': 'Background',
        '--bg-stage': 'Panels',
        '--bg-accent': 'Raised areas',
        '--mf-gold': 'Brand colour',
        '--text-output': 'Text',
        '--text-message': 'Secondary text',
        '--status-success': 'Success',
        '--status-error': 'Error',
        '--input-background': 'Buttons'
    };
    let themes = [];
    let rejected = [];
    let allowLow = false;        // preferences: allow_low_contrast_themes (default off)

    const shortText = (t) => `Below contrast guidelines. Hard to see: ${t.hard_to_see.join(', ')}.`;

    function currentId() {
        const link = $('mf-theme-stylesheet');
        return link ? decodeURIComponent(new URL(link.href).pathname.split('/').pop()) : 'default';
    }

    S.themes = {
        list: () => themes,
        currentId,
        allowLow: () => allowLow,

        load: async function (selectId) {
            const grid = $('theme-selector-grid');
            const form = $('set-theme-form');
            if (!grid || !form) return;
            if (!form.dataset.wired) {
                form.dataset.wired = 'true';
                form.addEventListener('submit', (e) => { e.preventDefault(); this.save(); });
                grid.addEventListener('change', (e) => {
                    if (!e.target.matches('input[type="radio"]')) return;
                    window.applyTheme(e.target.value);
                    const t = themes.find(x => x.id === e.target.value);
                    S.say('set-theme-status', `Showing ${e.target.dataset.name}.${t && t.below_contrast ? ` ${shortText(t)}` : ''} Choose Save theme to keep it.`,
                          t && t.below_contrast ? 'warning' : '');
                });
                $('set-theme-lowcontrast').addEventListener('change', async (e) => {
                    allowLow = e.target.checked;
                    const checked = document.querySelector('#theme-selector-grid input:checked');
                    this.render(checked ? checked.value : currentId());
                    try {
                        const r = await (await fetch('/run_tool_logic/settings/save_prefs', {
                            method: 'POST', headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ allow_low_contrast_themes: allowLow })
                        })).json();
                        if (r.status !== 'success') throw new Error(r.message || 'unknown error');
                        const n = themes.filter(t => t.below_contrast).length;
                        S.say('set-theme-status', allowLow
                            ? `Saved. ${n ? `${n} ${n === 1 ? 'theme' : 'themes'} below contrast guidelines ${n === 1 ? 'is' : 'are'} now in the list, marked.` : 'No themes are below the guidelines right now.'}`
                            : 'Saved. Only themes that meet contrast guidelines are offered.', 'ok');
                    } catch (err) {
                        S.say('set-theme-status', `The list changed for now, but the setting couldn't be saved: ${err.message}`, 'error');
                    }
                });
                grid.addEventListener('click', (e) => {
                    const b = e.target.closest('button[data-act]');
                    if (!b) return;
                    const t = themes.find(x => x.id === b.dataset.id);
                    if (b.dataset.act === 'edit') S.maker && S.maker.open({ id: t.id, name: t.name, edit: true });
                    if (b.dataset.act === 'delete') this.remove(t);
                });
                $('set-theme-create').addEventListener('click', () => S.maker && S.maker.open({ id: currentId() }));
            }
            try {
                const [r, prefs] = await Promise.all([
                    fetch('/run_tool_logic/settings/get_themes').then(x => x.json()),
                    fetch('/run_tool_logic/settings/get_prefs').then(x => x.json()).catch(() => ({}))
                ]);
                themes = r.themes;
                rejected = r.rejected || [];
                allowLow = prefs.allow_low_contrast_themes === true;
                $('set-theme-lowcontrast').checked = allowLow;
                if (!Array.isArray(themes) || !themes.length) throw new Error(r.message || 'no themes were found');
                this.render(selectId || currentId());
            } catch (e) {
                S.say('set-theme-status', `The themes couldn't be loaded: ${e.message}`, 'error');
            }
        },

        // Themes that can't be chosen right now: broken folders, and (while the
        // switch is off) themes below contrast guidelines. One closed line
        // ("1 theme isn't offered") that opens to each one and the reason.
        renderRejected: function (hiddenLow) {
            const box = $('set-theme-rejected');
            if (!box) return;
            const items = [
                ...hiddenLow.map(t => el('li', {}, el('strong', { textContent: t.name }),
                    `: ${shortText(t)} Turn on “Also show themes that don’t meet contrast guidelines” to choose it.`)),
                ...rejected.map(x => el('li', {}, el('strong', { textContent: x.folder }),
                    ` (${x.custom ? 'your themes' : 'built-in'}): ${x.reason}`))
            ];
            box.hidden = !items.length;
            if (!items.length) return;
            const n = items.length;
            $('set-theme-rejected-sum').textContent = `${n} ${n === 1 ? 'theme isn’t' : 'themes aren’t'} offered`;
            $('set-theme-rejected-list').replaceChildren(...items);
        },

        render: function (checkedId) {
            const grid = $('theme-selector-grid');
            const legend = grid.querySelector('legend');
            // A theme below the guidelines is listed when the switch is on, or
            // when it's the one in use (so the current theme never vanishes).
            const shown = themes.filter(t => !t.below_contrast || allowLow || t.id === checkedId);
            this.renderRejected(themes.filter(t => !shown.includes(t)));
            const cards = shown.map(t => {
                const radio = el('input', { type: 'radio', name: 'set-theme', value: t.id, checked: t.id === checkedId });
                radio.dataset.name = t.name;
                let advisory = null;
                if (t.below_contrast) {
                    advisory = el('p', { className: 'set-hint set-theme-adv', id: `set-adv-${t.id}`, textContent: shortText(t) });
                    radio.setAttribute('aria-describedby', advisory.id);
                }
                const list = el('ul', { className: 'set-palette' });
                list.setAttribute('aria-hidden', 'true');   // decorative sample; the name is the choice
                for (const [v, label] of Object.entries(LABELS)) {
                    const sw = el('span', { className: 'set-swatch' });
                    sw.style.background = (t.palette && t.palette[v]) || 'transparent';
                    list.append(el('li', {}, label, sw));
                }
                // The label covers the name AND the sample, so clicking anywhere on
                // the card (except Edit/Delete) chooses it; aria-hidden keeps the
                // sample out of the radio's name.
                const pick = el('label', { className: 'set-theme-pick' },
                    el('span', { className: 'set-theme-name' }, radio, t.name), list);
                const card = el('div', { className: 'set-theme-card' }, pick);
                if (advisory) card.append(advisory);
                if (t.custom) {
                    const edit = el('button', { type: 'button', className: 'set-secondary' }, 'Edit', el('span', { className: 'mf-visually-hidden', textContent: ` ${t.name}` }));
                    const del = el('button', { type: 'button', className: 'set-del-btn' }, 'Delete', el('span', { className: 'mf-visually-hidden', textContent: ` ${t.name}` }));
                    edit.dataset.act = 'edit'; edit.dataset.id = t.id;
                    del.dataset.act = 'delete'; del.dataset.id = t.id;
                    card.append(el('p', { className: 'set-hint', textContent: 'A theme you made.' }), el('div', { className: 'set-row' }, edit, del));
                }
                return card;
            });
            grid.replaceChildren(legend, ...cards);
        },

        save: async function () {
            const chosen = document.querySelector('#theme-selector-grid input:checked');
            if (!chosen) { S.say('set-theme-status', 'Choose a theme first.', 'error'); return; }
            const prefs = { theme_id: chosen.value };
            try {
                const r = await (await fetch('/run_tool_logic/settings/save_prefs', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(prefs)
                })).json();
                if (r.status !== 'success') throw new Error(r.message || 'unknown error');
                S.say('set-theme-status', `Saved. MetaForge will start with ${chosen.dataset.name}.`, 'ok');
            } catch (e) {
                S.say('set-theme-status', `The theme couldn't be saved: ${e.message}`, 'error');
            }
        },

        remove: async function (t) {
            const yes = await S.confirm({
                title: `Delete ${t.name}?`,
                body: 'The theme and its logo are deleted. This can’t be undone.',
                ok: 'Delete theme', cancel: 'Keep it'
            });
            if (!yes) return;
            try {
                const r = await (await fetch('/run_tool_logic/settings/delete_custom_theme', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: t.id })
                })).json();
                if (r.status !== 'success') throw new Error(r.message || 'unknown error');
                let note = '';
                const prefs = await (await fetch('/run_tool_logic/settings/get_prefs')).json();
                if (prefs.theme_id === t.id || currentId() === t.id) {
                    window.applyTheme('default');
                    await fetch('/run_tool_logic/settings/save_prefs', {
                        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ theme_id: 'default' })
                    });
                    note = ' MetaForge is back on the Default theme.';
                }
                await this.load();
                $('set-theme-create').focus();
                S.say('set-theme-status', `Deleted ${t.name}.${note}`, 'ok');
            } catch (e) {
                S.say('set-theme-status', `${t.name} wasn't deleted: ${e.message}`, 'error');
            }
        }
    };
})();
// --- END OF FILE theme_engine.js ---
