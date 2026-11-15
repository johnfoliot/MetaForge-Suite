// --- START OF FILE theme_maker.js ---
/**
 * Settings > Theme > Create a theme. v2 (2026-11-15, John).
 * Built from the theme template (engines/theme_template.py, fetched once):
 * the 17 colours, their groups and hints, the contrast pairs and the
 * one-gold rule all come from there, so this file never lists them itself.
 *  - One colour at a time: a grouped list, then that colour's controls
 *    (code, picker, Hue/Saturation/Lightness sliders) and every contrast
 *    pair it takes part in, with Fix (moves only its lightness).
 *  - A live preview that uses the new colours (on the preview only; the
 *    rest of Settings keeps the app's theme so it stays readable).
 *  - The logo (full recolour or faces only) is drawn by the server
 *    (engines/logo_engine.py) so preview and saved file are identical.
 *  - Save is refused while anything fails (John: block + Fix); the server
 *    checks again.
 */
(function () {
    const S = window.metaforge.settings;
    const $ = (id) => document.getElementById(id);
    const el = (tag, props = {}, ...kids) => { const n = Object.assign(document.createElement(tag), props); n.append(...kids); return n; };
    const LOGO = 'logo';

    let tpl = null;            // template from the server
    let labels = {};
    let values = {};           // key -> '#rrggbb'
    let logo = { style: 'full', colour: '#cc9900' };
    let selected = 'bg-main';
    let editing = null;        // file name when editing one of your themes
    let dirty = false;
    let hueMemo = {};          // keeps a grey's hue slider where the user left it
    let logoTimer = null;

    // --- colour maths (same formulas as theme_template.py) ---
    const lum = (h) => {
        const [r, g, b] = [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16) / 255)
            .map(c => c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
        return 0.2126 * r + 0.7152 * g + 0.0722 * b;
    };
    const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
    function toHsl(h) {
        const [r, g, b] = [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16) / 255);
        const max = Math.max(r, g, b), min = Math.min(r, g, b), l = (max + min) / 2;
        let hue = 0, s = 0;
        if (max !== min) {
            const d = max - min;
            s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
            hue = max === r ? ((g - b) / d + (g < b ? 6 : 0)) : max === g ? ((b - r) / d + 2) : ((r - g) / d + 4);
            hue *= 60;
        }
        return { h: hue, s: s * 100, l: l * 100, grey: max === min };
    }
    function toHex(h, s, l) {
        s /= 100; l /= 100;
        const k = (n) => (n + h / 30) % 12, a = s * Math.min(l, 1 - l);
        const f = (n) => l - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)));
        return '#' + [0, 8, 4].map(n => Math.round(f(n) * 255).toString(16).padStart(2, '0')).join('');
    }
    const isHex = (v) => /^#[0-9a-f]{6}$/i.test(v);
    function readsAsGold(h) {
        if (h.toLowerCase() === tpl.brand_gold) return false;
        const { h: hue, s, l } = toHsl(h), R = tpl.gold_rule;
        return hue >= R.hue_min && hue <= R.hue_max && s / 100 >= R.sat_min && l / 100 >= R.light_min && l / 100 <= R.light_max;
    }

    // --- checks ---
    function failingPairs(v = values) {
        return tpl.pairs.map(p => ({ ...p, r: ratio(v[p.fg], v[p.bg]) })).filter(p => p.r < p.min);
    }
    function problems() {
        const out = failingPairs().map(p => ({ keys: [p.fg, p.bg], text: `${labels[p.fg]} on ${labels[p.bg]}: ${p.r.toFixed(2)}:1, needs ${p.min}:1` }));
        for (const k of Object.keys(values)) if (readsAsGold(values[k])) out.push({ keys: [k], text: `${labels[k]} reads as gold` });
        if (readsAsGold(logo.colour)) out.push({ keys: [LOGO], text: 'Logo colour reads as gold' });
        return out;
    }
    const flagged = () => new Set(problems().flatMap(p => p.keys));

    function setDirty(on) {
        dirty = on;
        if (window.MFLeaveGuard) {
            if (on) window.MFLeaveGuard.set('theme-maker', askLeave); else window.MFLeaveGuard.clear('theme-maker');
        }
    }
    async function askLeave() {
        const leave = await S.confirm({ title: 'Leave without saving this theme?', body: 'The theme you’re making hasn’t been saved. If you leave now, it’s lost.', ok: 'Leave without saving', cancel: 'Keep working' });
        if (!leave) {
            const tab = $('set-tab-theme'); if (tab) S.selectTab(tab);
        }
        return leave;
    }

    // --- rendering ---
    function renderList() {
        const bad = flagged();
        const groups = new Map();
        for (const t of tpl.tokens) { if (!groups.has(t.group)) groups.set(t.group, []); groups.get(t.group).push(t); }
        groups.set('Logo', [{ key: LOGO, label: 'Logo colour' }]);
        const parts = [];
        for (const [g, toks] of groups) {
            const hid = `tm-g-${g.replace(/\W+/g, '-').toLowerCase()}`;
            parts.push(el('h3', { className: 'tm-group', id: hid, textContent: g }));
            const ul = el('ul', { className: 'tm-items' });
            ul.setAttribute('aria-labelledby', hid);
            for (const t of toks) {
                const hex = t.key === LOGO ? logo.colour : values[t.key];
                const sw = el('span', { className: 'tm-swatch' }); sw.style.background = hex;
                const b = el('button', { type: 'button', className: 'tm-item' }, sw, el('span', { className: 'tm-item-name', textContent: t.label }));
                if (bad.has(t.key)) b.append(el('span', { className: 'tm-flag', textContent: 'Fix' }), el('span', { className: 'mf-visually-hidden', textContent: ': needs fixing' }));
                b.dataset.key = t.key;
                if (t.key === selected) b.setAttribute('aria-current', 'true');
                ul.append(el('li', {}, b));
            }
            parts.push(ul);
        }
        $('tm-list').replaceChildren(...parts);
    }

    function renderEditor() {
        const isLogo = selected === LOGO;
        const tok = tpl.tokens.find(t => t.key === selected);
        const hex = isLogo ? logo.colour : values[selected];
        $('tm-ed-title').textContent = isLogo ? 'Logo colour' : tok.label;
        $('tm-ed-hint').textContent = isLogo
            ? 'Full recolour: the whole 3-D logo in this colour. Faces only: this colour on the letter faces, with gold edges and a gold “Studio”.'
            : tok.hint;
        $('tm-logo-style').hidden = !isLogo;
        $('tm-hex').value = hex;
        $('tm-picker').value = hex;
        const hsl = toHsl(hex);
        const hue = hsl.grey ? (hueMemo[selected] ?? 0) : hsl.h;
        for (const [id, v] of [['tm-h', hue], ['tm-s', hsl.s], ['tm-l', hsl.l]]) {
            $(id).value = Math.round(v);
            $(id + '-out').value = Math.round(v) + (id === 'tm-h' ? '°' : '%');
        }
        $('tm-hex').removeAttribute('aria-invalid');
        renderChecks();
    }

    function renderChecks() {
        const isLogo = selected === LOGO;
        const hex = isLogo ? logo.colour : values[selected];
        const mine = isLogo ? [] : tpl.pairs.filter(p => p.fg === selected || p.bg === selected);
        const ul = $('tm-pairs');
        if (isLogo) {
            ul.replaceChildren(el('li', { textContent: 'Logos don’t need a contrast ratio, but check that it’s easy to see in the preview.' }));
        } else if (!mine.length) {
            ul.replaceChildren(el('li', { textContent: 'Decorative only: no contrast ratio needed.' }));
        } else {
            ul.replaceChildren(...mine.map(p => {
                const r = ratio(values[p.fg], values[p.bg]), pass = r >= p.min;
                const other = p.fg === selected ? `on ${labels[p.bg]}` : `${labels[p.fg]} on this`;
                return el('li', { className: pass ? 'is-pass' : 'is-fail' },
                    el('span', { className: 'tm-mark', textContent: pass ? '✓' : '✗' }),
                    ` ${other}: ${r.toFixed(2)}:1 `,
                    el('span', { className: 'tm-verdict', textContent: pass ? 'passes' : `fails (needs ${p.min}:1)` }));
            }));
        }
        const gold = readsAsGold(hex);
        $('tm-gold').hidden = !gold;
        const failing = mine.some(p => ratio(values[p.fg], values[p.bg]) < p.min);
        $('tm-fix').hidden = !failing;
        renderSummary();
    }

    function renderSummary() {
        const n = problems().length;
        $('tm-problems').textContent = n ? `${n} ${n === 1 ? 'problem' : 'problems'} to fix before saving` : 'Every check passes';
        $('tm-problems').className = n ? 'set-dirty' : 'set-status is-ok';
        $('tm-next').hidden = !n;
    }

    function applyPreview() {
        const pv = $('tm-preview');
        for (const [k, v] of Object.entries(values)) pv.style.setProperty(`--${k}`, v);
        clearTimeout(logoTimer);
        logoTimer = setTimeout(() => {
            $('tm-logo').src = `/run_tool_logic/settings/logo_preview?style=${logo.style}&colour=${encodeURIComponent(logo.colour)}`;
        }, 250);
    }

    function setColour(hex, { from } = {}) {
        hex = hex.toLowerCase();
        if (selected === LOGO) logo.colour = hex; else values[selected] = hex;
        setDirty(true);
        if (from !== 'hex') $('tm-hex').value = hex;
        if (from !== 'picker') $('tm-picker').value = hex;
        if (from !== 'slider') {
            const hsl = toHsl(hex);
            if (!hsl.grey) $('tm-h').value = Math.round(hsl.h);
            $('tm-s').value = Math.round(hsl.s); $('tm-l').value = Math.round(hsl.l);
        }
        for (const id of ['tm-h', 'tm-s', 'tm-l']) $(id + '-out').value = $(id).value + (id === 'tm-h' ? '°' : '%');
        const item = document.querySelector(`.tm-item[data-key="${selected}"] .tm-swatch`);
        if (item) item.style.background = hex;
        applyPreview();
        renderChecks();
        refreshFlags();
    }

    function refreshFlags() {
        const bad = flagged();
        for (const b of document.querySelectorAll('.tm-item')) {
            const has = !!b.querySelector('.tm-flag');
            if (bad.has(b.dataset.key) !== has) {
                if (has) { b.querySelector('.tm-flag').remove(); b.querySelector('.mf-visually-hidden')?.remove(); }
                else b.append(el('span', { className: 'tm-flag', textContent: 'Fix' }), el('span', { className: 'mf-visually-hidden', textContent: ': needs fixing' }));
            }
        }
    }

    function select(key, focusEditor) {
        selected = key;
        for (const b of document.querySelectorAll('.tm-item')) {
            if (b.dataset.key === key) b.setAttribute('aria-current', 'true'); else b.removeAttribute('aria-current');
        }
        renderEditor();
        if (focusEditor) $('tm-hex').focus();
    }

    /** Smallest lightness change that makes every pair of the selected colour pass. */
    function fix() {
        const base = values[selected], hsl = toHsl(base);
        const mine = tpl.pairs.filter(p => p.fg === selected || p.bg === selected);
        const passes = (hex) => {
            const v = { ...values, [selected]: hex };
            return mine.every(p => ratio(v[p.fg], v[p.bg]) >= p.min) && !readsAsGold(hex);
        };
        for (let step = 1; step <= 100; step++) {
            for (const dir of [-1, 1]) {
                const l = hsl.l + dir * step;
                if (l < 0 || l > 100) continue;
                const hex = toHex(hsl.grey ? (hueMemo[selected] ?? 0) : hsl.h, hsl.s, l);
                if (passes(hex)) {
                    setColour(hex);
                    S.say('tm-status', `${labels[selected]} is now ${hex} (lightness ${dir < 0 ? 'down' : 'up'} ${step}%). Every check for it passes.`, 'ok');
                    $('tm-hex').focus();
                    return;
                }
            }
        }
        const other = mine.find(p => ratio(values[p.fg], values[p.bg]) < p.min);
        S.say('tm-status', `${labels[selected]} can’t pass every check by changing its lightness alone. Try changing ${labels[other.fg === selected ? other.bg : other.fg]} instead.`, 'error');
    }

    // --- start points ---
    function fillStartSelect(currentFile) {
        const sel = $('tm-start');
        const opts = [el('option', { value: 'tpl:dark', textContent: 'Dark template' }), el('option', { value: 'tpl:light', textContent: 'Light template' })];
        const og = el('optgroup', { label: 'Colours from a theme' });
        for (const t of S.themes.list()) og.append(el('option', { value: t.file, textContent: t.name, selected: t.file === currentFile }));
        sel.replaceChildren(...opts, og);
    }

    async function loadStart(choice) {
        if (choice.startsWith('tpl:')) {
            const which = choice.slice(4);
            values = Object.fromEntries(tpl.tokens.map(t => [t.key, t[which]]));
            logo = { style: 'full', colour: values['mf-gold'] };
            return `the ${which} template`;
        }
        const r = await (await fetch(`/run_tool_logic/settings/theme_values?file=${encodeURIComponent(choice)}`)).json();
        if (r.status !== 'success') throw new Error(r.message || 'not found');
        values = Object.fromEntries(tpl.tokens.map(t => [t.key, r.values[t.key] || t.dark]));
        logo = { style: r.logo_style === 'faces' ? 'faces' : 'full', colour: isHex(r.logo_colour) ? r.logo_colour.toLowerCase() : values['mf-gold'] };
        return r.name;
    }

    function renderAll() {
        renderList();
        renderEditor();
        applyPreview();
        for (const r of document.querySelectorAll('input[name="tm-logo-style"]')) r.checked = r.value === logo.style;
    }

    // --- wiring ---
    function wire() {
        const form = $('tm-form');
        if (form.dataset.wired) return;
        form.dataset.wired = 'true';
        form.addEventListener('submit', (e) => { e.preventDefault(); S.maker.save(); });
        $('tm-back').addEventListener('click', () => S.maker.close());
        $('tm-name').addEventListener('input', () => { setDirty(true); $('tm-name').removeAttribute('aria-invalid'); });
        $('tm-list').addEventListener('click', (e) => { const b = e.target.closest('.tm-item'); if (b) select(b.dataset.key, false); });
        $('tm-hex').addEventListener('input', (e) => {
            let v = e.target.value.trim(); if (!v.startsWith('#')) v = '#' + v;
            if (isHex(v)) { e.target.removeAttribute('aria-invalid'); setColour(v, { from: 'hex' }); }
        });
        $('tm-hex').addEventListener('change', (e) => {
            let v = e.target.value.trim(); if (!v.startsWith('#')) v = '#' + v;
            if (!isHex(v)) { e.target.setAttribute('aria-invalid', 'true'); S.say('tm-status', 'A colour code is # followed by 6 digits or letters a to f, like #1a2fb5.', 'error'); }
        });
        $('tm-picker').addEventListener('input', (e) => setColour(e.target.value, { from: 'picker' }));
        for (const id of ['tm-h', 'tm-s', 'tm-l']) {
            $(id).addEventListener('input', () => {
                hueMemo[selected] = Number($('tm-h').value);
                setColour(toHex(Number($('tm-h').value), Number($('tm-s').value), Number($('tm-l').value)), { from: 'slider' });
            });
        }
        $('tm-fix').addEventListener('click', fix);
        $('tm-use-gold').addEventListener('click', () => { setColour(tpl.brand_gold); S.say('tm-status', `${selected === LOGO ? 'Logo colour' : labels[selected]} is now #CC9900.`, 'ok'); });
        $('tm-logo-style').addEventListener('change', (e) => { logo.style = e.target.value; setDirty(true); applyPreview(); });
        $('tm-next').addEventListener('click', () => {
            const p = problems()[0]; if (!p) return;
            select(p.keys[0], true);
            renderList();
            S.say('tm-status', `${p.text}.`);
        });
        $('tm-start-load').addEventListener('click', async () => {
            if (dirty && !(await S.confirm({ title: 'Replace every colour?', body: 'All the colours (and the logo settings) are replaced with the ones you chose to start from.', ok: 'Replace colours', cancel: 'Keep mine' }))) return;
            try {
                const what = await loadStart($('tm-start').value);
                hueMemo = {};
                setDirty(true);
                renderAll();
                S.say('tm-status', `Started from ${what}.`, 'ok');
            } catch (e) { S.say('tm-status', `Those colours couldn't be loaded: ${e.message}`, 'error'); }
        });
    }

    S.maker = {
        open: async function ({ file, name, edit } = {}) {
            try {
                if (!tpl) {
                    tpl = await (await fetch('/run_tool_logic/settings/theme_template')).json();
                    labels = Object.fromEntries(tpl.tokens.map(t => [t.key, t.label]));
                    labels[LOGO] = 'Logo colour';
                }
                wire();
                fillStartSelect(file);
                await loadStart(file || 'tpl:dark');
            } catch (e) {
                S.say('set-theme-status', `Create a theme couldn't start: ${e.message}`, 'error');
                return;
            }
            editing = edit ? file : null;
            $('tm-title').textContent = edit ? `Edit ${name}` : 'Create a theme';
            $('tm-name').value = edit ? name : '';
            selected = 'bg-main';
            hueMemo = {};
            setDirty(false);
            $('set-theme-form').hidden = true;
            $('tm-form').hidden = false;
            renderAll();
            S.say('tm-status', '');
            $('set-panels').scrollTop = 0;
            $('tm-name').focus();
        },

        close: async function (force) {
            if (!force && dirty && !(await S.confirm({ title: 'Discard this theme?', body: 'The theme you’re making hasn’t been saved.', ok: 'Discard theme', cancel: 'Keep working' }))) return;
            setDirty(false);
            $('tm-form').hidden = true;
            $('set-theme-form').hidden = false;
            $('set-theme-create').focus();
        },

        save: async function () {
            const nameBox = $('tm-name');
            const name = nameBox.value.trim();
            if (!name) {
                nameBox.setAttribute('aria-invalid', 'true'); nameBox.focus();
                S.say('tm-status', 'Give the theme a name first.', 'error');
                return;
            }
            nameBox.removeAttribute('aria-invalid');
            const p = problems();
            if (p.length) {
                select(p[0].keys[0], true);
                renderList();
                S.say('tm-status', `Not saved yet: ${p.length} ${p.length === 1 ? 'check fails' : 'checks fail'}. First: ${p[0].text}. Fix shows next to the colour.`, 'error');
                return;
            }
            const send = async (overwrite) => (await fetch('/run_tool_logic/settings/save_custom_theme', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, values, logo, overwrite })
            })).json();
            try {
                S.say('tm-status', 'Saving the theme…');
                const slugFile = name.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '') + '_theme.css';
                let r = await send(editing === slugFile);
                if (r.status === 'exists') {
                    const yes = await S.confirm({ title: `Replace ${name}?`, body: `${r.message} Saving replaces it and its logo.`, ok: 'Replace it', cancel: 'Go back' });
                    if (!yes) { S.say('tm-status', 'Not saved. Choose another name to keep both.'); nameBox.focus(); return; }
                    r = await send(true);
                }
                if (r.status !== 'success') throw new Error(r.message || 'unknown error');
                setDirty(false);
                $('tm-form').hidden = true;
                $('set-theme-form').hidden = false;
                await S.themes.load(r.file);
                window.applyThemeFile(r.file);
                const radio = document.querySelector(`#theme-selector-grid input[value="${r.file}"]`);
                if (radio) radio.focus();
                S.say('set-theme-status', `Saved ${r.name}. It's showing now; choose Save theme to start MetaForge with it.`, 'ok');
            } catch (e) {
                S.say('tm-status', `The theme wasn't saved: ${e.message}`, 'error');
            }
        }
    };
})();
// --- END OF FILE theme_maker.js ---
