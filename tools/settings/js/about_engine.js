// --- START OF FILE about_engine.js ---
/**
 * Settings > About (2026-11-19). The page's wording is tools/settings/about.mfi
 * (trusted, shipped with MetaForge, so it is inserted as HTML, like a help
 * file). The lists of programs, libraries, fonts and images are data from
 * the licenses/ folder: they are built here as DOM, text only.
 *
 * A licence name with its text on board is a button that opens the text in
 * a native modal <dialog>; Esc and Close both close it, and the browser
 * returns focus to the button that opened it.
 */
(function () {
    const S = window.metaforge.settings;

    function el(tag, props = {}, ...kids) {
        const n = Object.assign(document.createElement(tag), props);
        for (const k of kids.flat()) if (k !== null && k !== undefined && k !== false) n.append(k);
        return n;
    }

    function link(text, url) {
        return /^https?:\/\//.test(url || '') ? el('a', { href: url, textContent: text }) : document.createTextNode(text);
    }

    /** The licence cell: a button that opens the text when MetaForge has it, plain text when it doesn't. */
    function licenceCell(row) {
        if (!row.text) return el('td', {}, row.licence || '');
        const b = el('button', { type: 'button', className: 'set-link-btn', textContent: row.licence || 'Licence' });
        b.dataset.aboutText = row.text;
        if (row.tool) b.dataset.aboutTool = row.tool;      // the text is in that tool's own folder
        b.dataset.aboutTitle = `${row.name}: ${row.licence}`;
        b.setAttribute('aria-label', `${row.licence}. Read the licence for ${row.name}`);
        return el('td', {}, b);
    }

    /**
     * table(id, caption, columns, rows): columns are [heading, cell(row) -> Node|string].
     * The first column is each row's header. The wrapper is a named, focusable
     * region so a keyboard user can scroll it sideways if a long word forces it.
     */
    function table(id, caption, columns, rows) {
        const capId = `set-about-cap-${id}`;
        const body = rows.map(r => el('tr', {}, columns.map(([, cell], i) => {
            const v = cell(r);
            if (v instanceof HTMLTableCellElement) return v;
            return i === 0 ? el('th', { scope: 'row' }, v) : el('td', {}, v);
        })));
        const wrap = el('div', { className: 'set-about-table', tabIndex: 0 },
            el('table', {},
                el('caption', { id: capId, textContent: caption }),
                el('thead', {}, el('tr', {}, columns.map(([h]) => el('th', { scope: 'col', textContent: h })))),
                el('tbody', {}, body)));
        wrap.setAttribute('role', 'region');
        wrap.setAttribute('aria-labelledby', capId);
        return wrap;
    }

    const TABLES = {
        programs: d => table('programs', 'Programs included', [
            ['Program', r => link(r.name, r.url)],
            ['What MetaForge uses it for', r => r.used_for || ''],
            ['Licence', licenceCell],
            ['Source code', r => r.source ? link('Get the source', r.source) : 'Not published'],
        ], d.programs),
        libraries: d => table('libraries', `Libraries (${d.libraries.length})`, [
            ['Library', r => link(r.name, r.url)],
            ['Version', r => r.version || ''],
            ['What it does here', r => r.used_for || ''],
            ['Licence', r => r.licence || ''],
        ], d.libraries),
        fonts: d => table('fonts', 'Fonts', [
            ['Font', r => link(r.name, r.url)],
            ['Used for', r => r.used_for || ''],
            ['Credit', r => r.credit || ''],
            ['Licence', licenceCell],
        ], d.fonts),
        images: d => table('images', 'Images', [
            ['Images', r => link(r.name, r.url)],
            ['Used for', r => r.used_for || ''],
            ['Credit', r => r.credit || ''],
            ['Licence', licenceCell],
        ], d.images),
    };

    async function openText(button) {
        const dlg = document.getElementById('set-licence');
        const pre = document.getElementById('set-licence-text');
        document.getElementById('set-licence-title').textContent = button.dataset.aboutTitle || 'Licence';
        pre.textContent = 'Loading…';
        pre.scrollTop = 0;
        if (!dlg.open) dlg.showModal();
        try {
            const from = button.dataset.aboutTool ? `&tool=${encodeURIComponent(button.dataset.aboutTool)}` : '';
            const res = await fetch(`/run_tool_logic/settings/licence_text?name=${encodeURIComponent(button.dataset.aboutText)}${from}`);
            const data = await res.json();
            pre.textContent = data.status === 'ok' ? data.text : (data.message || 'That licence text couldn’t be read.');
        } catch (e) {
            pre.textContent = `The licence text couldn’t be read (${e.message}).`;
        }
        pre.scrollTop = 0;
    }

    S.about = {
        load: async function () {
            const box = document.getElementById('set-about-page');
            if (!box) return;
            let d;
            try {
                d = await (await fetch('/run_tool_logic/settings/get_about')).json();
                if (d.status !== 'ok') throw new Error(d.message || 'no details');
            } catch (e) {
                box.replaceChildren(el('p', { className: 'set-status is-error', textContent: `The About page couldn’t be loaded (${e.message}).` }));
                return;
            }
            box.innerHTML = d.html;
            for (const n of box.querySelectorAll('[data-about="version"]')) n.textContent = `version ${d.version}`;
            for (const slot of box.querySelectorAll('[data-about-table]')) {
                const make = TABLES[slot.dataset.aboutTable];
                const rows = d[slot.dataset.aboutTable];
                if (make && Array.isArray(rows) && rows.length) slot.replaceChildren(make(d));
                else slot.replaceChildren(el('p', { className: 'set-hint', textContent: 'This list isn’t available in this copy of MetaForge.' }));
            }
            if (window.MFHelp) window.MFHelp.prepare(box);      // marks outside links; they open in the real browser
            if (!box.dataset.wired) {
                box.dataset.wired = 'true';
                box.addEventListener('click', (e) => {
                    const b = e.target.closest('button[data-about-text]');
                    if (b) openText(b);
                });
            }
        }
    };
})();
// --- END OF FILE about_engine.js ---
