// --- START OF FILE toolbar_engine.js ---
/**
 * Standalone Toolbar Customizer. Build 5.2.3
 * Role: Handles tool visibility, custom ordering, and sequence normalization.
 * Build 5.2.3: Accessibility Hardening (Emoji Scrub) and Persistence Sync.
 */

window.metaforge.settings.toolbar = {
    /**
     * Entry Point: Fetches tool manifests and saved layout from Python.
     */
    load: async function() {
        this.initLabelsPref();
        const grid = document.getElementById('toolbar-customizer-grid');
        const form = document.getElementById('set-toolbar-form');
        if(!grid || !form) return;

        // v2 (2026-11-15): Update toolbar is the form's submit (Enter in an
        // order box runs it); separator buttons are wired here, not inline.
        if (!form.dataset.wired) {
            form.dataset.wired = 'true';
            form.addEventListener('submit', (e) => { e.preventDefault(); this.save(); });
            grid.addEventListener('click', (e) => {
                if (e.target.closest('.tb-sep-remove')) this.removeSeparator(e.target.closest('.tb-sep-remove'));
                else if (e.target.closest('.tb-sep-add')) this.addSeparator();
            });
        }

        try {
            const res = await fetch('/run_tool_logic/settings/get_discovery');
            const data = await res.json();
            this.render(data);
        } catch (e) {
            this.say(`The toolbar layout couldn't be loaded: ${e.message}`, 'error');
        }
    },

    /**
     * v2 (2026-11-13): "Show names under toolbar icons". Saved as
     * toolbar_labels in preferences.json (default off) and applied
     * immediately via mfApplyToolbarLabels (metaforge_core.js).
     */
    initLabelsPref: async function() {
        const box = document.getElementById('pref-toolbar-labels');
        const status = document.getElementById('pref-toolbar-labels-status');
        if (!box || box.dataset.wired) return;
        box.dataset.wired = 'true';

        try {
            const prefs = await (await fetch('/run_tool_logic/settings/get_prefs')).json();
            box.checked = prefs.toolbar_labels === true;
        } catch (e) { /* default stays off */ }

        box.addEventListener('change', async () => {
            const on = box.checked;
            // Same shared path as the rail toggle and Ctrl+B (metaforge_core.js)
            const saved = await window.mfSetToolbarLabels(on);
            status.textContent = !saved
                ? "The setting is applied for now but couldn't be saved."
                : on ? 'Saved. Tool names now show in the toolbar.'
                     : 'Saved. The toolbar now shows icons only.';
        });
    },

    /**
     * Renders the toolbar list: tools (show / order) and the user's own
     * separators (order / Remove). v2 (2026-11-13): separators replace the
     * fixed group labels; they're stored as {id:"separator", type:"separator"}
     * in toolbar_layout_v2.json.
     */
    render: function(data) {
        const grid = document.getElementById('toolbar-customizer-grid');
        const esc = (s) => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

        let html = `
            <table class="meta-table" id="toolbar-customizer-table">
                <caption class="mf-visually-hidden">Toolbar tools and separators, in order</caption>
                <thead>
                    <tr style="text-align:left; color:var(--mf-gold); border-bottom:1px solid var(--bg-accent);">
                        <th scope="col" style="padding:8px; font-size:0.75rem;">Show</th>
                        <th scope="col" style="padding:8px; font-size:0.75rem;">Item</th>
                        <th scope="col" style="padding:8px; font-size:0.75rem; text-align:center;">Order</th>
                    </tr>
                </thead>
                <tbody id="toolbar-customizer-rows">`;

        // Newly found tool folders that aren't in the saved layout yet are
        // appended (visible only if the manifest says required:true), as before.
        const knownIds = new Set(data.layout.map(e => e.id));
        const effectiveLayout = data.layout.concat(
            Object.keys(data.manifests)
                .filter(id => !knownIds.has(id))
                .map(id => ({ id, visible: !!data.manifests[id].required }))
        );

        let order = 1;
        effectiveLayout.forEach((entry) => {
            if (entry.type === 'separator') { html += this.separatorRow(order++); return; }
            if (["dashboard", "settings"].includes(entry.id)) return;
            const tool = data.manifests[entry.id];
            if (!tool) return;   // saved layout names a tool folder that no longer exists
            const name = esc(tool.name || entry.id);
            const iconPath = `/tool_asset/${entry.id}/${tool.icon || 'default.svg'}`;
            const isVisible = entry.visible ? 'checked' : '';
            const isRequired = tool.required ? 'disabled checked' : '';
            html += `
                <tr style="border-bottom:1px solid var(--bg-main);">
                    <td style="padding:8px;">
                        <input type="checkbox" class="tool-toggle" data-id="${entry.id}" ${isVisible} ${isRequired} aria-label="Show ${name}">
                    </td>
                    <td style="padding:8px; display:flex; align-items:center; gap:10px;">
                        <div class="mf-icon-mask" style="-webkit-mask-image: url('${iconPath}'); mask-image: url('${iconPath}'); width:18px; height:18px; background-color: var(--mf-gold);"></div>
                        <span class="data-text" style="font-size:0.85rem;">${name}</span>
                    </td>
                    <td style="padding:8px; text-align:center;">
                        <input type="number" class="tool-order" data-id="${entry.id}" value="${order++}" aria-label="Order for ${name}">
                    </td>
                </tr>`;
        });

        html += `</tbody></table>
            <div class="tb-sep-actions">
                <button type="button" class="tb-sep-add">Add separator</button>
                <p class="mf-pref-hint">Separators draw a line between tools in the toolbar. Give a separator the order number of the tool it should sit above (1 puts it straight after Dashboard). Dashboard always stays at the top and Settings at the bottom.</p>
            </div>`;
        grid.innerHTML = html;
    },

    separatorRow: function(order) {
        return `
                <tr class="tb-sep-row" style="border-bottom:1px solid var(--bg-main);">
                    <td style="padding:8px;"></td>
                    <td style="padding:8px;">
                        <div style="display:flex; align-items:center; gap:10px;">
                            <span class="tb-sep-line" aria-hidden="true"></span>
                            <span class="data-text" style="font-size:0.85rem;">Separator</span>
                            <button type="button" class="tb-sep-remove">Remove<span class="mf-visually-hidden"> this separator</span></button>
                        </div>
                    </td>
                    <td style="padding:8px; text-align:center;">
                        <input type="number" class="tool-order" data-kind="separator" value="${order}" aria-label="Order for separator">
                    </td>
                </tr>`;
    },

    addSeparator: function() {
        const rows = document.getElementById('toolbar-customizer-rows');
        if (!rows) return;
        const highest = Math.max(0, ...Array.from(rows.querySelectorAll('.tool-order')).map(i => parseInt(i.value) || 0));
        rows.insertAdjacentHTML('beforeend', this.separatorRow(highest + 1));
        const input = rows.lastElementChild.querySelector('.tool-order');
        input.focus(); input.select();
        this.say(`Separator added at position ${highest + 1}. Change its order number to move it, then choose Update toolbar.`);
    },

    removeSeparator: function(btn) {
        const row = btn.closest('tr');
        const next = row.nextElementSibling || row.previousElementSibling;
        row.remove();
        const target = next && next.querySelector('input, button');
        if (target) target.focus();
        this.say('Separator removed. Choose Update toolbar to save.');
    },

    say: function(msg, kind = '') {
        window.metaforge.settings.say('set-toolbar-status', msg, kind);
    },

    /**
     * Normalization: sort everything (tools and separators) by order number.
     * A separator given the same number as a tool takes that position, i.e.
     * it lands just BEFORE that tool ("put a separator at 1" = right after
     * Dashboard). Other ties keep their on-screen order. Dashboard first,
     * Settings last.
     */
    save: async function() {
        const orderInputs = Array.from(document.querySelectorAll('#toolbar-customizer-rows .tool-order'));

        const items = orderInputs.map((input, index) => {
            const userValue = parseInt(input.value) || 99;
            if (input.dataset.kind === 'separator') return { kind: 'separator', userValue, index };
            const tid = input.getAttribute('data-id');
            const toggle = document.querySelector(`.tool-toggle[data-id="${tid}"]`);
            return { kind: 'tool', id: tid, userValue, index, visible: toggle ? toggle.checked : true };
        });
        const sepFirst = (x) => (x.kind === 'separator' ? 0 : 1);
        items.sort((a, b) => (a.userValue - b.userValue) || (sepFirst(a) - sepFirst(b)) || (a.index - b.index));

        const finalLayout = [
            { id: "dashboard", visible: true },
            ...items.map((item, i) => item.kind === 'separator'
                ? { id: "separator", type: "separator", order: i + 1 }
                : { id: item.id, visible: item.visible, order: i + 1 }),
            { id: "settings", visible: true }
        ];

        this.say('Saving the toolbar…');
        try {
            const res = await fetch('/run_tool_logic/settings/save_toolbar', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(finalLayout)
            });
            const result = await res.json();
            if (result.status === 'success') {
                this.say('Toolbar saved. Reloading to apply it…', 'ok');
                setTimeout(() => { location.reload(); }, 1200);
            } else {
                throw new Error(result.message || 'unknown error');
            }
        } catch (e) {
            this.say(`The toolbar couldn't be saved: ${e.message}`, 'error');
        }
    }
};

// --- SETTINGS MINI-ENGINE: toolbar_engine.js END ---