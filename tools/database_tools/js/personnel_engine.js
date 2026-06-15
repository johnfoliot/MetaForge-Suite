// --- START OF FILE personnel_engine.js ---
/**
 * MetaForge Studio: Database Tools - Personnel Engine (Phase 3)
 * Physical Location: \tools\database_tools\js\personnel_engine.js
 * Build 1.1.30: Mandatory 10ms Paint Guard and Namespace-safe initialization.
 */

(function() {
    window.metaforge = window.metaforge || {};
    window.metaforge.database_tools = window.metaforge.database_tools || {};

    window.metaforge.database_tools.personnel = {
        /**
         * Load Personnel
         */
        load: async function() {
            const mfId = window.metaforge.database_tools.state.activeId;
            if (!mfId) return;

            try {
                const res = await fetch(`/run_tool_logic/database_tools/personnel_get?mf_id=${encodeURIComponent(mfId)}`);
                const data = await res.json();

                // Directive III.2: 10ms Paint Guard
                setTimeout(() => {
                    if (data.status === "success") {
                        this.render(data.edges);
                    }
                }, 10);
            } catch (err) {
                console.error("Personnel Load Failure:", err);
            }
        },

        /**
         * Render Table
         */
        render: function(edges) {
            const body = document.getElementById('personnel-rows-container');
            if (!body) return;
            body.innerHTML = '';

            if (!edges || edges.length === 0) {
                body.innerHTML = '<p class="tool_notes">No personnel relationships found.</p>';
                return;
            }

            edges.forEach(edge => {
                const div = document.createElement('div');
                div.style = "background: var(--bg-accent); padding:6px; border: 1px solid #444; border-radius:2px; margin-bottom: 4px;";
                div.innerHTML = `
                    <div style="display:grid; grid-template-columns: 1fr 1fr 1fr auto; gap:5px; align-items: center;">
                        <span class="mf-card-label">${edge.name}</span>
                        <span class="mf-card-label">${edge.role}</span>
                        <span class="mf-card-label">${edge.provenance}</span>
                        <button class="mf-button-gold-fixed" style="background: var(--status-error) !important;" 
                                onclick="window.metaforge.database_tools.personnel.remove('${edge.id}')">Remove</button>
                    </div>
                `;
                body.appendChild(div);
            });
        },

        /**
         * Remove Credit
         */
        remove: async function(edgeId) {
            if (!confirm("Are you sure?")) return;
            try {
                const res = await fetch(`/run_tool_logic/database_tools/personnel_delete?id=${encodeURIComponent(edgeId)}`);
                if ((await res.json()).status === "success") this.load();
            } catch (err) {
                console.error("Personnel Deletion Failure:", err);
            }
        }
    };
})();
// --- END OF FILE personnel_engine.js ---