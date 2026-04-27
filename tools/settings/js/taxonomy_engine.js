// --- START OF FILE taxonomy_engine.js ---
/**
 * Standalone Taxonomy Manager. Build 5.2.5
 * Handles UI rendering, state for Genre/Sub-Genre management, and Drawer logic.
 * Build 5.2.5: Integrated toggleDrawer logic for instructional text expansion.
 */

window.metaforge.settings.taxonomy = {
    /**
     * Entry Point: Fetches data and triggers the visual render.
     */
    load: async function() {
        const container = document.getElementById('taxonomy-manager-container');
        if(!container) return;
        
        container.innerHTML = '<p class="tool_notes">Synchronizing taxonomy matrix...</p>';
        
        try {
            const res = await fetch('/run_tool_logic/settings/get_taxonomy');
            const data = await res.json();
            
            // Directive IV.3: Store data in the Hub's global state object
            window.metaforge.settings.state.taxonomy = data;
            this.render();
        } catch (e) {
            container.innerHTML = `<p class="error-text">Taxonomy data fetch failure: ${e.message}</p>`;
        }
    },

    /**
     * Renders the split-pane workbench view.
     */
    render: function() {
        const container = document.getElementById('taxonomy-manager-container');
        if(!container) return;

        const data = window.metaforge.settings.state.taxonomy || {};
        const activeParent = window.metaforge.settings.state.activeParentGenre;
        const parents = Object.keys(data).sort();
        
        let html = `
            <div style="display: flex; gap: 20px; min-height: 450px;">
                <!-- SECTION 1: Genre List -->
                <section style="flex: 1; border-right: 1px solid var(--bg-accent); overflow-y: auto; padding-right: 15px;" aria-labelledby="mf-tax-genre-label">
                    <h2 id="mf-tax-genre-label" style="color: var(--text-output); font-size: 1.5rem; margin: 0 0 15px 0; border-bottom: 1px solid var(--bg-accent);">Genre</h2>
                    <ul role="listbox" aria-labelledby="mf-tax-genre-label" style="list-style:none; padding:0;">
                        ${parents.map(p => `
                            <li role="option" tabindex="0" 
                                class="taxonomy-item ${activeParent === p ? 'active' : ''}" 
                                aria-selected="${activeParent === p}" 
                                onclick="metaforge.settings.taxonomy.selectParent('${p}')" 
                                onkeydown="if(event.key==='Enter'||event.key===' ') metaforge.settings.taxonomy.selectParent('${p}')">
                                ${p}
                            </li>
                        `).join('')}
                    </ul>
                    <div style="margin-top:20px; border-top: 1px solid var(--bg-accent); padding-top: 10px;">
                        <label class="data-text" for="new-parent-name" style="display:block;">Add category</label>
                        <input type="text" id="new-parent-name" class="mf-input" placeholder="New genre..." style="margin-bottom: 5px;">
                        <button class="mf-button-gold-fixed" onclick="metaforge.settings.taxonomy.addParent()">Add genre</button>
                    </div>
                </section>

                <!-- SECTION 2: Sub-Genre List -->
                <section style="flex: 2; overflow-y: auto;" aria-labelledby="mf-tax-subgenre-label">
                    <h2 id="mf-tax-subgenre-label" style="color: var(--text-output); font-size: 1.5rem; margin: 0 0 15px 0; border-bottom: 1px solid var(--bg-accent);">Sub-genre</h2>
                    <div id="sub-genre-controls">
                        ${this.renderSubControls()}
                    </div>
                </section>
            </div>`;
        container.innerHTML = html;
    },

    /**
     * Generates the Management UI for the selected category.
     */
    renderSubControls: function() {
        const activeParent = window.metaforge.settings.state.activeParentGenre;
        const data = window.metaforge.settings.state.taxonomy || {};
        
        if (!activeParent) return '<p class="tool_notes">Select a genre to manage its sub-taxonomies.</p>';
        const subs = data[activeParent] || [];
        
        return `
            <h3 class="data-text" style="margin-bottom:15px; font-size: 1rem; color: var(--mf-gold);">Editing: ${activeParent}</h3>
            <ul style="list-style:none; padding:0;">
                ${subs.map((s, idx) => `
                    <li style="display:flex; gap:10px; margin-bottom:8px; align-items:center;">
                        <label class="data-text" for="sub-genre-${idx}" style="min-width: 8rem;">Edit name</label>
                        <input type="text" id="sub-genre-${idx}" class="mf-input sub-genre-input" value="${s}" onchange="metaforge.settings.taxonomy.updateSub(${idx}, this.value)" style="flex:1;">
                        <button class="mf-btn-danger" onclick="metaforge.settings.taxonomy.removeSub(${idx})" aria-label="Delete ${s}">×</button>
                    </li>
                `).join('')}
            </ul>
            <div style="margin-top:20px; padding-top: 15px; border-top: 1px solid var(--bg-accent); display:flex; gap:10px; align-items:center;">
                <label class="data-text" for="new-sub-name" style="min-width: 8rem;">New sub-genre</label>
                <input type="text" id="new-sub-name" class="mf-input" placeholder="Name...">
                <button class="mf-button-gold-fixed" onclick="metaforge.settings.taxonomy.addSub()">Add</button>
            </div>
            <div style="margin-top:30px; display:flex; gap:10px; align-items:center;">
                <button class="mf-btn-danger" onclick="metaforge.settings.taxonomy.removeParent()">Delete category</button>
            </div>
        `;
    },

    /**
     * UI Logic: Toggles the instructional text drawer expansion.
     */
    toggleDrawer: function() {
        const drawer = document.getElementById('taxonomy-instruction-drawer');
        const btn = document.getElementById('tax-drawer-toggle');
        if (!drawer || !btn) return;

        const isOpen = drawer.classList.toggle('open');
        btn.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
        btn.innerText = isOpen ? 'Read less...' : 'Read more...';
    },

    // --- LOGIC ACTIONS ---

    selectParent: function(p) { 
        window.metaforge.settings.state.activeParentGenre = p; 
        this.render(); 
        // Directive II.3: 10ms focus guard for keyboard navigation
        setTimeout(() => { 
            const activeItem = document.querySelector('.taxonomy-item.active'); 
            if (activeItem) activeItem.focus(); 
        }, 10);
    },

    addParent: function() {
        const input = document.getElementById('new-parent-name');
        const n = input.value.trim();
        if (n && !window.metaforge.settings.state.taxonomy[n]) {
            window.metaforge.settings.state.taxonomy[n] = [];
            window.metaforge.settings.state.activeParentGenre = n;
            input.value = '';
            this.render();
        }
    },

    removeParent: function() {
        const p = window.metaforge.settings.state.activeParentGenre;
        if (!p) return;
        
        if (confirm(`Delete entire '${p}' category and all its sub-genres?`)) {
            delete window.metaforge.settings.state.taxonomy[p];
            window.metaforge.settings.state.activeParentGenre = null;
            this.render();
        }
    },

    addSub: function() {
        const input = document.getElementById('new-sub-name');
        const n = input.value.trim();
        const p = window.metaforge.settings.state.activeParentGenre;
        if (n && p) {
            window.metaforge.settings.state.taxonomy[p].push(n);
            input.value = '';
            this.render();
        }
    },

    updateSub: function(idx, val) {
        const p = window.metaforge.settings.state.activeParentGenre;
        if (p) {
            window.metaforge.settings.state.taxonomy[p][idx] = val.trim();
        }
    },

    removeSub: function(idx) {
        const p = window.metaforge.settings.state.activeParentGenre;
        if (p && window.metaforge.settings.state.taxonomy[p]) {
            window.metaforge.settings.state.taxonomy[p].splice(idx, 1);
            this.render();
        }
    },

    save: async function() {
        const status = document.getElementById('save-status');
        if (!status) return;

        status.innerHTML = "<span class='data-text'>Committing taxonomy changes...</span>";
        try {
            const res = await fetch('/run_tool_logic/settings/save_taxonomy', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(window.metaforge.settings.state.taxonomy)
            });
            const r = await res.json();
            if (r.status === 'success') {
                status.innerHTML = "<span style='color:var(--status-success);'>✓ Taxonomy matrix physically committed.</span>";
                setTimeout(() => { status.innerHTML = ""; }, 4000);
            }
        } catch (e) { 
            status.innerHTML = "<span style='color:var(--status-error);'>Commit error.</span>"; 
        }
    }
};

// --- SETTINGS TAXONOMY ENGINE END ---
// --- END OF FILE taxonomy_engine.js ---