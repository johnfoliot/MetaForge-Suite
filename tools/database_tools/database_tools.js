// --- START OF FILE database_tools.js ---
/**
 * MetaForge Studio: Database Tools Hub (Build 2.1.2)
 * Role: Orchestrates engine boot sequences and handles air-gapped sub-module loading.
 * Physical Location: \tools\database_tools\database_tools.js
 */

window.metaforge = window.metaforge || {};
window.metaforge.database_tools = window.metaforge.database_tools || {
    state: { activeId: null, stagedCoverPath: null },
    booted: false,
    booting: null
};

window.metaforge.database_tools.boot = async function() {
    if (this.booted) return true;
    if (this.booting) return this.booting;

    this.booting = (async () => {
        // Structured asset array mapping exact relative physical layout folders on disk
        const engines = [
            { name: "radar_engine.js", path: "js/radar_engine.js" },
            { name: "personnel_engine.js", path: "js/personnel_engine.js" },
            { name: "audit_engine.js", path: "js/audit_engine.js" },
            { name: "master_engine.js", path: "js/master_engine.js" },
            { name: "artist_editor.js", path: "artist/artist_editor.js" },
            { name: "album_editor.js", path: "album/album_editor.js" },
            { name: "fixer_editor.js", path: "fixer/fixer_editor.js" }
        ];

        for (const engine of engines) {
            await new Promise((resolve) => {
                const script = document.createElement('script');
                script.src = `/tool_asset/database_tools/${engine.path}?v=${new Date().getTime()}`;
                script.onload = resolve;
                script.onerror = resolve; // Continue even if one fails
                document.head.appendChild(script);
            });
        }
        this.booted = true;
        return true;
    })();

    return this.booting;
};

window.metaforge.database_tools.showPanel = async function(panelId, element) {
    await this.boot();

    document.querySelectorAll('.sub-nav-btn').forEach(el => el.classList.remove('active'));
    if (element) element.classList.add('active');

    const stage = document.getElementById('workspace-stage');
    if (!stage) return;

    try {
        // Fetch HTML template markup from backend route matching our new file scheme
        const response = await fetch(`/run_tool_logic/database_tools/fetch_sub_module?module=${encodeURIComponent(panelId)}`);
        const data = await response.json();

        if (data.status === "success") {
            // Securely inject layout markup into the staging viewport
            stage.innerHTML = data.html;

            // Directive III.2: 10ms Paint Guard & Focus Safety Routine
            setTimeout(() => {
                const targetPanel = document.getElementById('panel-' + panelId);
                if (targetPanel) {
                    targetPanel.style.display = 'flex';
                    const dynamicHeader = targetPanel.querySelector('h2');
                    if (dynamicHeader) dynamicHeader.focus();
                }
            }, 10);
        } else {
            stage.innerHTML = `<div style="padding: 20px; color: var(--status-error);">Error loading sub-module layout: ${data.message}</div>`;
        }
    } catch (err) {
        console.error("Sub-module injection failure:", err);
        stage.innerHTML = `<div style="padding: 20px; color: var(--status-error);">Failed to execute backend orchestration request.</div>`;
    }
};


// --- DOCUMENTATION & HELP MANAGEMENT ---
window.metaforge.database_tools.lastTrigger = null;

window.metaforge.database_tools.openHelp = async function() {
    const panel = document.getElementById('database-panel');
    const body = document.getElementById('upk-help-body');
    const title = document.getElementById('database-title');
    this.lastTrigger = document.activeElement;
    if (!panel || !body) return;
		
	try {
        const response = await fetch('/tool_asset/database_tools/help.mfi');
        const html = await response.text();
        body.innerHTML = html;
        panel.style.display = 'flex';
        setTimeout(() => {
            if (title) {
                title.setAttribute('tabindex', '-1');
                title.focus();
            }
        }, 20);
    } catch (err) {
        body.innerHTML = `<p style="color:red; padding:15px;">Error: ${err.message}</p>`;	
        panel.style.display = 'flex';
    }
};

window.metaforge.database_tools.closeHelp = function() {
    const panel = document.getElementById('database-panel');
    if (panel) {
        panel.style.display = 'none';
        if (this.lastTrigger) this.lastTrigger.focus();
    }
};

// Global shorthand breakout namespace routing synchronization map
window.metaforge.database = {
    openHelp: function() {
        window.metaforge.database_tools.openHelp();
    },
    closeHelp: function() {
        window.metaforge.database_tools.closeHelp();
    }
};

// Auto-boot sequence initialization on load
(async () => {
    await window.metaforge.database_tools.boot();
    // Default workspace viewport to load the Artist identity view initially
    const initialTab = document.getElementById('tab-artist');
    if (initialTab) {
        await window.metaforge.database_tools.showPanel('artist', initialTab);
    }
})();
// --- END OF FILE database_tools.js ---