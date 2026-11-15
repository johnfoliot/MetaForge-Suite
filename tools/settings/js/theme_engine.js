// --- START OF FILE theme_engine.js ---
/**
 * Settings > Theme. v2 (2026-11-15): a native radio group of cards (was
 * role=button divs with interpolated onclick strings). Choosing a card
 * previews the theme; Save theme (the form's submit) keeps it. The logo for
 * each theme comes from window.mfLogoForTheme (metaforge_core.js).
 */
(function () {
    const S = window.metaforge.settings;
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

    function currentFile() {
        const link = document.getElementById('mf-theme-stylesheet');
        return link ? link.href.split('/').pop().split('?')[0] : 'default_theme.css';
    }

    function apply(file) {
        if (typeof window.applyThemeFile === 'function') window.applyThemeFile(file);
        const logo = document.getElementById('mf-main-logo');
        if (logo && window.mfLogoForTheme) logo.src = window.mfLogoForTheme(file);
    }

    S.themes = {
        load: async function () {
            const grid = document.getElementById('theme-selector-grid');
            const form = document.getElementById('set-theme-form');
            if (!grid || !form) return;
            if (!form.dataset.wired) {
                form.dataset.wired = 'true';
                form.addEventListener('submit', (e) => { e.preventDefault(); this.save(); });
                grid.addEventListener('change', (e) => {
                    if (!e.target.matches('input[type="radio"]')) return;
                    apply(e.target.value);
                    S.say('set-theme-status', `Showing ${e.target.dataset.name}. Choose Save theme to keep it.`);
                });
            }
            try {
                const themes = await (await fetch('/run_tool_logic/settings/get_themes')).json();
                if (!Array.isArray(themes) || !themes.length) throw new Error('no themes were found');
                this.render(themes);
            } catch (e) {
                S.say('set-theme-status', `The themes couldn't be loaded: ${e.message}`, 'error');
            }
        },

        render: function (themes) {
            const grid = document.getElementById('theme-selector-grid');
            const legend = grid.querySelector('legend');
            const now = currentFile();
            const cards = themes.map(t => {
                const card = document.createElement('label');
                card.className = 'set-theme-card';
                const name = document.createElement('span');
                name.className = 'set-theme-name';
                const radio = Object.assign(document.createElement('input'), { type: 'radio', name: 'set-theme', value: t.file, checked: t.file === now });
                radio.dataset.name = t.name;
                name.append(radio, document.createTextNode(t.name));
                const list = document.createElement('ul');
                list.className = 'set-palette';
                list.setAttribute('aria-hidden', 'true');   // decorative sample; the name is the choice
                for (const [v, label] of Object.entries(LABELS)) {
                    const li = document.createElement('li');
                    const sw = document.createElement('span');
                    sw.className = 'set-swatch';
                    sw.style.background = (t.palette && t.palette[v]) || 'transparent';
                    li.append(document.createTextNode(label), sw);
                    list.append(li);
                }
                card.append(name, list);
                return card;
            });
            grid.replaceChildren(legend, ...cards);
        },

        save: async function () {
            const chosen = document.querySelector('#theme-selector-grid input:checked');
            if (!chosen) { S.say('set-theme-status', 'Choose a theme first.', 'error'); return; }
            try {
                const r = await (await fetch('/run_tool_logic/settings/save_prefs', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ theme_file: chosen.value })
                })).json();
                if (r.status !== 'success') throw new Error(r.message || 'unknown error');
                S.say('set-theme-status', `Saved. MetaForge will start with ${chosen.dataset.name}.`, 'ok');
            } catch (e) {
                S.say('set-theme-status', `The theme couldn't be saved: ${e.message}`, 'error');
            }
        }
    };
})();
// --- END OF FILE theme_engine.js ---
