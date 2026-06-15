// --- START OF FILE audit_engine.js ---
/**
 * Standalone Dependency Auditor. Build 5.2.3
 * Role: Handles system-level binary verification and version reporting.
 * Build 5.2.3: Accessibility Hardening (Emoji Scrub) and Multi-Modal Status.
 */

window.metaforge.settings.audit = {
    /**
     * Entry Point: Triggers the Python audit and renders the result table.
     */
    run: async function() {
        const container = document.getElementById('binary-audit-container');
        if(!container) return;

        container.innerHTML = '<p class="tool_notes">Auditing local specialized helper programmes...</p>';

        try {
            const res = await fetch('/run_tool_logic/settings/check_binaries');
            const results = await res.json();

            this.render(results);
        } catch (e) {
            container.innerHTML = `<p class="error-text">Audit bridge failure: ${e.message}</p>`;
        }
    },

    /**
     * Renders the audit table with semantic colour signaling and ARIA-hidden icons.
     * Adheres to WCAG 2.2 AA (SC 1.1.1) and COGA Module 10.
     */
    render: function(results) {
        const container = document.getElementById('binary-audit-container');
        
        let html = `
            <table class="meta-table" style="width:100%;">
                <thead>
                    <tr style="text-align:left; color:var(--mf-gold); border-bottom:1px solid var(--bg-accent);">
                        <th style="padding:8px; font-size:0.75rem;">Binary component</th>
                        <th style="padding:8px; font-size:0.75rem;">Local version</th>
                        <th style="padding:8px; font-size:0.75rem; text-align:center;">Status</th>
                    </tr>
                </thead>
                <tbody>
        `;

        results.forEach(bin => {
            const statusColor = bin.status === 'ok' ? 'var(--status-success)' : 'var(--status-error)';
            const statusLabel = bin.status === 'ok' ? 'READY' : 'MISSING';
            const statusIcon = bin.status === 'ok' ? '✅' : '❌';

            html += `
                <tr style="border-bottom:1px solid var(--bg-main);">
                    <td class="data-text" style="padding:8px; font-weight:bold;">${bin.name}</td>
                    <td class="data-text" style="padding:8px; color:var(--text-message); font-size:0.75rem;">${bin.version}</td>
                    <td class="data-text" style="padding:8px; text-align:center; color:${statusColor}; font-weight:bold;">
                        <span aria-hidden="true">${statusIcon}</span> ${statusLabel}
                    </td>
                </tr>
            `;
        });

        html += '</tbody></table>';
        container.innerHTML = html;
    }
};

// --- SETTINGS MINI-ENGINE: audit_engine.js END ---