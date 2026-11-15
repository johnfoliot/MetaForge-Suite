// --- START OF FILE theme_engine.js ---
/**
 * Settings > Theme (the list). v2 (2026-11-15): a native radio group of
 * cards. Choosing a card previews the theme (its own logo comes with it via
 * applyThemeFile); Save theme keeps it. Themes you made (Create a theme,
 * js/theme_maker.js) are listed after the built-in ones with Edit and
 * Delete. v2 saves its choice as theme_file_v2; the shared theme_file (read
 * by the 1.x build) is only updated for built-in themes, which 1.x has too.
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

    function currentFile() {
        const link = $('mf-theme-stylesheet');
        return link ? decodeURIComponent(link.href.split('/').pop().split('?')[0]) : 'default_theme.css';
    }

    S.themes = {
        list: () => themes,
        currentFile,

        load: async function (selectFile) {
            const grid = $('theme-selector-grid');
            const form = $('set-theme-form');
            if (!grid || !form) return;
            if (!form.dataset.wired) {
                form.dataset.wired = 'true';
                form.addEventListener('submit', (e) => { e.preventDefault(); this.save(); });
                grid.addEventListener('change', (e) => {
                    if (!e.target.matches('input[type="radio"]')) return;
                    window.applyThemeFile(e.target.value);
                    S.say('set-theme-status', `Showing ${e.target.dataset.name}. Choose Save theme to keep it.`);
                });
                grid.addEventListener('click', (e) => {
                    const b = e.target.closest('button[data-act]');
                    if (!b) return;
                    const t = themes.find(x => x.file === b.dataset.file);
                    if (b.dataset.act === 'edit') S.maker && S.maker.open({ file: t.file, name: t.name, edit: true });
                    if (b.dataset.act === 'delete') this.remove(t);
                });
                $('set-theme-create').addEventListener('click', () => S.maker && S.maker.open({ file: currentFile() }));
            }
            try {
                themes = await (await fetch('/run_tool_logic/settings/get_themes')).json();
                if (!Array.isArray(themes) || !themes.length) throw new Error('no themes were found');
                this.render(selectFile || currentFile());
            } catch (e) {
                S.say('set-theme-status', `The themes couldn't be loaded: ${e.message}`, 'error');
            }
        },

        render: function (checkedFile) {
            const grid = $('theme-selector-grid');
            const legend = grid.querySelector('legend');
            const cards = themes.map(t => {
                const radio = el('input', { type: 'radio', name: 'set-theme', value: t.file, checked: t.file === checkedFile });
                radio.dataset.name = t.name;
                const name = el('label', { className: 'set-theme-name' }, radio, t.name);
                const list = el('ul', { className: 'set-palette' });
                list.setAttribute('aria-hidden', 'true');   // decorative sample; the name is the choice
                for (const [v, label] of Object.entries(LABELS)) {
                    const sw = el('span', { className: 'set-swatch' });
                    sw.style.background = (t.palette && t.palette[v]) || 'transparent';
                    list.append(el('li', {}, label, sw));
                }
                const card = el('div', { className: 'set-theme-card' }, name, list);
                if (t.custom) {
                    const edit = el('button', { type: 'button', className: 'set-secondary' }, 'Edit', el('span', { className: 'mf-visually-hidden', textContent: ` ${t.name}` }));
                    const del = el('button', { type: 'button', className: 'set-del-btn' }, 'Delete', el('span', { className: 'mf-visually-hidden', textContent: ` ${t.name}` }));
                    edit.dataset.act = 'edit'; edit.dataset.file = t.file;
                    del.dataset.act = 'delete'; del.dataset.file = t.file;
                    card.append(el('p', { className: 'set-hint', textContent: 'A theme you made.' }), el('div', { className: 'set-row' }, edit, del));
                }
                return card;
            });
            grid.replaceChildren(legend, ...cards);
        },

        save: async function () {
            const chosen = document.querySelector('#theme-selector-grid input:checked');
            if (!chosen) { S.say('set-theme-status', 'Choose a theme first.', 'error'); return; }
            const t = themes.find(x => x.file === chosen.value);
            const prefs = { theme_file_v2: chosen.value };
            if (t && !t.custom) prefs.theme_file = chosen.value;
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
                    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ file: t.file })
                })).json();
                if (r.status !== 'success') throw new Error(r.message || 'unknown error');
                let note = '';
                const prefs = await (await fetch('/run_tool_logic/settings/get_prefs')).json();
                if (prefs.theme_file_v2 === t.file || currentFile() === t.file) {
                    window.applyThemeFile('default_theme.css');
                    await fetch('/run_tool_logic/settings/save_prefs', {
                        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ theme_file_v2: 'default_theme.css' })
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
