// --- START OF FILE audit_engine.js ---
/**
 * MetaForge Studio: Database Tools - Audit Engine
 * Role: Orchestrates Maintenance & Library Diagnostics.
 * Physical Location: \tools\database_tools\js\audit_engine.js
 * Build 1.0.1: Mandatory 10ms Paint Guard (Directive III.2).
 */

(function() {
    window.metaforge = window.metaforge || {};
    window.metaforge.database_tools = window.metaforge.database_tools || {};

    window.metaforge.database_tools.audit = {
        /**
         * Run Forensic Audit
         */
        runSummary: async function() {
            const consoleElem = document.getElementById('audit-console');
            if (!consoleElem) return;

            try {
                const res = await fetch('/run_tool_logic/database_tools/audit_run');
                const data = await res.json();

                // Directive III.2: 10ms Paint Guard
                setTimeout(() => {
                    if (data.status === "success") {
                        consoleElem.textContent = data.output;
                        consoleElem.style.color = "var(--status-success)";
                    } else {
                        consoleElem.textContent = `>>> AUDIT FAILED: ${data.message}`;
                        consoleElem.style.color = "var(--status-error)";
                    }
                }, 10);
            } catch (err) {
                console.error("Audit Engine Failure:", err);
            }
        },

        /**
         * Run Database Maintenance
         */
        runMaintenance: async function() {
            const consoleElem = document.getElementById('audit-console');
            if (!consoleElem || !confirm("Optimize database and rebuild indices?")) return;

            try {
                const res = await fetch('/run_tool_logic/database_tools/audit_maintenance');
                const data = await res.json();

                // Directive III.2: 10ms Paint Guard
                setTimeout(() => {
                    if (data.status === "success") {
                        consoleElem.textContent = ">>> [SUCCESS] MAINTENANCE COMPLETE.";
                        consoleElem.style.color = "var(--status-success)";
                    } else {
                        consoleElem.textContent = `>>> [!] MAINTENANCE FAILED: ${data.message}`;
                        consoleElem.style.color = "var(--status-error)";
                    }
                }, 10);
            } catch (err) {
                console.error("Maintenance Engine Failure:", err);
            }
        }
    };
})();
// --- END OF FILE audit_engine.js ---