// --- START OF FILE radar_engine.js ---
/**
 * MetaForge Studio: Database Tools - Radar Engine (Phase 1)
 * Role: Orchestrates Identity Radar (Search & Selection).
 * Physical Location: \tools\database_tools\js\radar_engine.js
 * Build 1.1.31: Mandatory 10ms Paint Guard and Namespace-safe initialization.
 * Accessibility: WCAG 2.2 AA (SC 2.1.1, SC 4.1.2)
 */

(function() {
    window.metaforge = window.metaforge || {};
    window.metaforge.database_tools = window.metaforge.database_tools || {};

    window.metaforge.database_tools.radar = {
        /**
         * Phase 1 Execution: Search
         */
        execute: async function() {
            const artistInput = document.getElementById('search-artist');
            const body = document.getElementById('matches-list');
            const container = document.getElementById('multiple-matches-container');

            if (!body) return;

            const artist = artistInput ? artistInput.value.trim() : "";
            if (!artist) return;

            try {
                const res = await fetch(`/run_tool_logic/database_tools/search_artist?artist=${encodeURIComponent(artist)}`);
                const data = await res.json();

                // Directive III.2: 10ms Paint Guard
                setTimeout(() => {
                    if (data.status === "multiple") {
                        container.style.display = 'block';
                        this.render(data.candidates);
                    } else if (data.status === "success") {
                        container.style.display = 'none';
                        window.metaforge.database_tools.artist_editor.render(data.artist);
                    } else {
                        container.style.display = 'none';
                        alert(data.message || "No records found.");
                    }
                }, 10);
            } catch (err) {
                console.error("Radar Search Failure:", err);
            }
        },

        /**
         * Render Results (Disambiguation)
         */
        render: function(candidates) {
            const body = document.getElementById('matches-list');
            if (!body) return;
            body.innerHTML = '';

            candidates.forEach(row => {
                const div = document.createElement('div');
                div.style = "border: 1px solid var(--mf-gold); padding: 10px; display: flex; justify-content: space-between; align-items: center; background: var(--bg-accent);";
                div.innerHTML = `
                    <span style="color: var(--text-output); font-weight: bold;">${row.artist_name}</span>
                    <button class="mf-button-gold-fixed" onclick="window.metaforge.database_tools.artist_editor.load('${row.mf_artist_id}')">Select</button>
                `;
                body.appendChild(div);
            });
        }
    };
})();
// --- END OF FILE radar_engine.js ---