// --- START OF FILE dashboard_engine.js ---
/**
 * Settings > Dashboard (v2, 2026-11-16).
 * The Dashboard's Customize, moved to Settings (John: "set it, finalize it,
 * and leave it"). Tiles are found by the Dashboard itself (one folder per
 * tile in tools\dashboard\tiles\), so this list grows and shrinks on its
 * own. Reads and saves through the Dashboard's `layout` action, which owns
 * data\dashboard\layout.json.
 *
 * Order: Move up / Move down (keyboard, single pointer: WCAG 2.5.7) or drag
 * by the handle. Moves keep focus on the button used (or the other one when
 * it becomes disabled) and are announced once.
 */
window.metaforge.settings.dashboard = {
    data: null,
    drag: null,

    load: async function () {
        const form = document.getElementById('set-dashboard-form');
        if (!form) return;
        if (!form.dataset.wired) {
            form.dataset.wired = 'true';
            form.addEventListener('submit', (e) => { e.preventDefault(); this.save(); });
            document.getElementById('set-db-reset').addEventListener('click', () => {
                this.build(this.data.default);
                this.say('Back to the default layout. Choose Save dashboard to keep it.');
            });
        }
        try {
            const res = await fetch('/run_tool_logic/dashboard/layout');
            const d = await res.json();
            if (d.status !== 'ok') throw new Error(d.message || `the server answered ${res.status}`);
            this.data = d;
            this.build(d.layout);
        } catch (e) {
            document.getElementById('set-db-list').replaceChildren(
                Object.assign(document.createElement('li'), { className: 'set-hint', textContent: `The Dashboard tiles couldn't be loaded: ${e.message}` }));
        }
    },

    say: function (msg, kind = '') {
        window.metaforge.settings.say('set-dashboard-status', msg, kind);
    },

    el: function (tag, props = {}, ...kids) {
        const e = document.createElement(tag);
        for (const [k, v] of Object.entries(props)) {
            if (v === null || v === undefined || v === false) continue;
            if (k === 'class') e.className = v;
            else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
            else if (k in e && typeof v !== 'string') e[k] = v;
            else e.setAttribute(k, v === true ? '' : v);
        }
        e.append(...kids.flat().filter((c) => c !== null && c !== undefined && c !== false));
        return e;
    },

    build: function (layout) {
        const el = this.el.bind(this);
        const tiles = this.data.tiles;
        const list = document.getElementById('set-db-list');
        const rows = layout.filter((t) => tiles[t.id]).map((t) => {
            const m = tiles[t.id];
            const boxId = `set-db-show-${t.id}`;
            const descId = `set-db-desc-${t.id}`;
            const li = el('li', { 'data-id': t.id },
                el('span', { class: 'set-db-handle', 'aria-hidden': 'true', title: 'Drag to move', onpointerdown: (e) => this.dragStart(e, li) }, '⠿'),
                el('div', { class: 'set-db-name' },
                    el('label', { for: boxId },
                        el('input', { type: 'checkbox', id: boxId, name: 'shown', checked: t.shown, 'aria-describedby': descId }),
                        m.title),
                    m.description ? el('p', { class: 'set-hint', id: descId }, m.description) : null),
                el('select', { class: 'set-select', name: 'width', 'aria-label': `Width: ${m.title}` },
                    [1, 2, 3].map((n) => el('option', { value: String(n), selected: n === t.width }, `${n} column${n > 1 ? 's' : ''}`))),
                el('span', { class: 'set-db-moves' },
                    el('button', { type: 'button', class: 'set-secondary', 'data-dir': 'up', 'aria-label': `Move up: ${m.title}`, onclick: (e) => this.move(li, -1, e.currentTarget) }, 'Move up'),
                    el('button', { type: 'button', class: 'set-secondary', 'data-dir': 'down', 'aria-label': `Move down: ${m.title}`, onclick: (e) => this.move(li, 1, e.currentTarget) }, 'Move down')));
            return li;
        });
        list.replaceChildren(...(rows.length ? rows
            : [el('li', { class: 'set-hint' }, 'No tiles were found in tools\\dashboard\\tiles.')]));
        this.updateMoves();
    },

    items: function () {
        return [...document.querySelectorAll('#set-db-list > li[data-id]')];
    },

    updateMoves: function () {
        const items = this.items();
        items.forEach((li, i) => {
            li.querySelector('[data-dir="up"]').disabled = i === 0;
            li.querySelector('[data-dir="down"]').disabled = i === items.length - 1;
        });
    },

    place: function (list, li, ref) {
        if ('moveBefore' in Element.prototype) list.moveBefore(li, ref);   // keeps focus and state
        else list.insertBefore(li, ref);
    },

    announceMove: function (li) {
        const items = this.items();
        document.getElementById('set-db-moved').textContent =
            `${this.data.tiles[li.dataset.id].title}: now ${items.indexOf(li) + 1} of ${items.length}.`;
    },

    move: function (li, dir, btn) {
        const list = li.parentElement;
        if (dir < 0 && !li.previousElementSibling) return;
        if (dir > 0 && !li.nextElementSibling) return;
        const ref = dir < 0 ? li.previousElementSibling : li.nextElementSibling.nextElementSibling;
        this.place(list, li, ref);
        this.updateMoves();
        const target = btn.disabled ? li.querySelector(`[data-dir="${dir < 0 ? 'down' : 'up'}"]`) : btn;
        target.focus();
        this.announceMove(li);
    },

    dragStart: function (e, li) {
        if (e.button !== 0) return;
        e.preventDefault();
        const list = li.parentElement;
        const handle = e.currentTarget;
        handle.setPointerCapture(e.pointerId);
        li.classList.add('is-dragging');
        document.documentElement.classList.add('set-db-grabbing');
        const drag = this.drag = { ref: undefined, pointerId: e.pointerId };
        const clear = () => {
            list.classList.remove('is-drop-end');
            list.querySelectorAll('.is-drop-before').forEach((x) => x.classList.remove('is-drop-before'));
        };
        const onMove = (ev) => {
            if (ev.pointerId !== drag.pointerId) return;
            const y = ev.clientY - list.getBoundingClientRect().top;
            const others = [...list.children].filter((x) => x !== li);
            const ref = others.find((x) => x.offsetTop + x.offsetHeight / 2 > y) ?? null;
            clear();
            drag.ref = ref;
            if (ref === li.nextElementSibling) return;          // its own place: no marker
            if (ref) ref.classList.add('is-drop-before'); else list.classList.add('is-drop-end');
        };
        const end = (drop) => {
            handle.removeEventListener('pointermove', onMove);
            handle.removeEventListener('pointerup', onUp);
            handle.removeEventListener('lostpointercapture', onLost);
            document.removeEventListener('keydown', onKey, true);
            clear();
            li.classList.remove('is-dragging');
            document.documentElement.classList.remove('set-db-grabbing');
            this.drag = null;
            if (drop && drag.ref !== undefined && drag.ref !== li.nextElementSibling && drag.ref !== li) {
                this.place(list, li, drag.ref);
                this.updateMoves();
                li.scrollIntoView({ block: 'nearest' });
                this.announceMove(li);
            }
        };
        const onUp = (ev) => { if (ev.pointerId === drag.pointerId) end(true); };
        const onLost = () => { if (this.drag === drag) end(false); };
        const onKey = (ev) => {
            if (ev.key !== 'Escape') return;
            ev.preventDefault();
            ev.stopPropagation();
            end(false);
            document.getElementById('set-db-moved').textContent = 'Move cancelled.';
        };
        handle.addEventListener('pointermove', onMove);
        handle.addEventListener('pointerup', onUp);
        handle.addEventListener('lostpointercapture', onLost);
        document.addEventListener('keydown', onKey, true);
    },

    save: async function () {
        const tiles = this.items().map((li) => ({
            id: li.dataset.id,
            shown: li.querySelector('[name="shown"]').checked,
            width: Number(li.querySelector('[name="width"]').value)
        }));
        this.say('Saving the Dashboard layout…');
        try {
            const res = await fetch('/run_tool_logic/dashboard/layout', {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ tiles })
            });
            const d = await res.json();
            if (d.status !== 'ok') throw new Error(d.message || `the server answered ${res.status}`);
            this.data = d;
            const shown = tiles.filter((t) => t.shown).length;
            this.say(`Dashboard saved: ${shown} of ${tiles.length} tiles shown.`, 'ok');
        } catch (e) {
            this.say(`The Dashboard layout couldn't be saved: ${e.message}`, 'error');
        }
    }
};
// --- SETTINGS MINI-ENGINE: dashboard_engine.js END ---
