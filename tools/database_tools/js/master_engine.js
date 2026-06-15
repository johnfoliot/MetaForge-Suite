// --- START OF FILE master_engine.js ---
/**
 * MetaForge Studio: Database Tools - Master Engine (Phase 2)
 * Physical Location: \tools\database_tools\js\master_engine.js
 * Build 1.1.28: Mandatory 10ms Paint Guard and Namespace-safe initialization.
 */

(function() {
    window.metaforge = window.metaforge || {};
    window.metaforge.database_tools = window.metaforge.database_tools || {};

    window.metaforge.database_tools.master = {
        /**
         * Load Record
         * Pulls the master archival record from the Hub via Python.
         */
        load: async function() {
            const mfId = window.metaforge.database_tools.state.activeId;
            if (!mfId) return;

            try {
                const res = await fetch(`/run_tool_logic/database_tools/master_get?mf_id=${encodeURIComponent(mfId)}`);
                const data = await res.json();

                // Directive III.2: 10ms Paint Guard
                setTimeout(() => {
                    if (data.status === "success") {
                        this.render(data.record);
                    }
                }, 10);
            } catch (err) {
                console.error("Master Record Load Failure:", err);
            }
        },

        /**
         * Render Master Form
         */
        render: function(record) {
            const fields =['master-mf-id', 'master-artist', 'master-album', 'master-year', 'master-label'];
            const map = {
                'master-mf-id': record.mf_id,
                'master-artist': record.artist_name,
                'master-album': record.album_title,
                'master-year': record.original_year,
                'master-label': record.label
            };

            fields.forEach(id => {
                const el = document.getElementById(id);
                if (el) el.value = map[id] || '';
            });
        },

        /**
         * Save Changes
         */
        commit: async function() {
            const payload = {
                mf_id: document.getElementById('master-mf-id').value,
                artist: document.getElementById('master-artist').value.trim(),
                album: document.getElementById('master-album').value.trim(),
                year: document.getElementById('master-year').value.trim(),
                label: document.getElementById('master-label').value.trim()
            };

            try {
                const res = await fetch('/run_tool_logic/database_tools/master_save', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                
                const data = await res.json();
                if (data.status === "success") {
                    const personnelTab = document.getElementById('tab-personnel');
                    if (personnelTab) {
                        window.metaforge.database_tools.showPanel('personnel', personnelTab);
                    }
                }
            } catch (err) {
                console.error("Master Save Failure:", err);
            }
        }
    };
})();
// --- END OF FILE master_engine.js ---