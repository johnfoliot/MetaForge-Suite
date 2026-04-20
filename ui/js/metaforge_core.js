/**
 * MetaForge Master Logic (Solid State)
 * Strictly follows the established D:\MetaForge\audio\tools\ directory structure.
 */

// --- GLOBAL UTILITIES ---

/**
 * Global Guard: Verifies the Python Bridge (pywebview) is initialized.
 */
window.checkMetaForgeBridge = function() {
    if (!window.pywebview || !window.pywebview.api) {
        console.error("MetaForge Error: Python Bridge (pywebview.api) is not initialized.");
        const consoleDiv = document.querySelector('[id$="Console"]') || document.querySelector('[id$="-console"]') || document.querySelector('.console-scroll');
        if (consoleDiv) {
            consoleDiv.innerHTML = '<div style="color:#ff0000; font-weight:bold;">🔥 SYSTEM ERROR: Python connection not initialized. Please restart the app.</div>';
        }
        return false;
    }
    return true;
};

// --- GLOBAL UTILITIES END ---

// --- SETTINGS TOOL LOGIC (MANIFEST SYSTEM) ---

/**
 * UI TRAFFIC CONTROLLER: Switches between panels.
 */
window.showSettingsPanel = function(panelId) {
    document.querySelectorAll('.settings-panel').forEach(p => p.style.display = 'none');
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
    
    const targetPanel = document.getElementById(panelId);
    if (targetPanel) targetPanel.style.display = 'block';

    const navMap = { 'updates': 'nav-updates', 'api-keys': 'nav-api', 'help': 'nav-help' };
    const navBtn = document.getElementById(navMap[panelId]);
    if (navBtn) navBtn.classList.add('active');

    // Trigger data loads based on panel visibility
    if (panelId === 'api-keys') window.loadSettingsData();
    if (panelId === 'updates') window.loadLocalManifest();
};

/**
 * LIBRARIAN: Loads existing .env values into the UI.
 */
window.loadSettingsData = async function() {
    try {
        const response = await fetch('/run_tool_logic/settings');
        const data = await response.json();
        
        if (data) {
            if (document.getElementById('set_email')) document.getElementById('set_email').value = data.user_email || '';
            if (document.getElementById('set_acoustid')) document.getElementById('set_acoustid').value = data.acoustid_key || '';
            if (document.getElementById('set_gemini')) document.getElementById('set_gemini').value = data.gemini_key || '';
            if (document.getElementById('set_library')) document.getElementById('set_library').value = data.library_root || '';
        }
    } catch (err) {
        console.error("Settings: Failed to load .env data", err);
    }
};

/**
 * ARCHIVIST: Saves UI values back to the .env file.
 */
window.saveSettings = async function() {
    const status = document.getElementById('save-status');
    const payload = {
        user_email: document.getElementById('set_email').value,
        acoustid_key: document.getElementById('set_acoustid').value,
        gemini_key: document.getElementById('set_gemini').value,
        library_root: document.getElementById('set_library').value
    };

    try {
        const response = await fetch('/run_tool_logic/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const result = await response.json();
        
        if (result.status === 'success') {
            status.innerText = "✅ Changes Saved.";
            status.style.color = "#44ff44";
        } else {
            status.innerText = "❌ Save Failed.";
            status.style.color = "#ff4444";
        }
        setTimeout(() => { status.innerText = ""; }, 3000);
    } catch (err) {
        console.error("Settings: Save error", err);
    }
};

/**
 * PICKER: Launches the Bridge-based Folder Picker.
 * [RULE: THE BRIDGE GUARD] applied.
 */
window.browseSettingsLibrary = async function() {
    if (!window.checkMetaForgeBridge()) return;
    try {
        const path = await window.pywebview.api.select_folder();
        if (path) {
            const libInput = document.getElementById('set_library');
            if (libInput) libInput.value = path;
        }
    } catch (err) {
        console.error("Settings: Picker failed", err);
    }
};

/**
 * MANIFEST: Loads local versioning data.
 */
window.loadLocalManifest = async function() {
    const grid = document.getElementById('manifest-tools-grid');
    if (!grid) return;
    try {
        const response = await fetch('/run_tool_logic/settings/get_local_manifest');
        const data = await response.json();
        if (data && data.approved_dependencies) {
            let html = `<h3 class="update_version">Current Version: <span class="white">${data.metaforge_version}</span></h3><h4 class="white">Libraries Used:</h4>`;
            for (const [tool, ver] of Object.entries(data.approved_dependencies)) {
                html += `<table class="dep-item"><tr><th class="dep-item">${tool}</th><td class="dep-item">version: ${ver}</td></tr></table>`;
            }
            grid.innerHTML = html;
        }
    } catch (err) {
        grid.innerHTML = '<div style="color:#ff4444;">Error accessing local manifest.json</div>';
    }
};

/**
 * SYNC: Compares and updates local files with Master.
 */
window.syncWithMaster = async function() {
    const btn = document.getElementById('sync-btn');
    const status = document.getElementById('sync-status');
    if (!btn || !status) return;
    
    btn.disabled = true;
    btn.innerText = "Syncing...";
    status.innerText = "Checking Master Manifest...";

    try {
        const response = await fetch('/run_tool_logic/settings/sync_manifest', { method: 'POST' });
        const result = await response.json();

        if (result.status === "match") {
            status.innerHTML = "✅ All systems up to date.";
            status.style.color = "#44ff44";
            btn.innerText = "OK";
            btn.disabled = false;
        } else if (result.status === "update") {
            status.innerHTML = `⚠️ Update Required: ${result.new}`;
            btn.innerText = "Update Now";
            btn.disabled = false;
            btn.onclick = async () => {
                btn.disabled = true;
                btn.innerText = "Installing...";
                const upRes = await fetch('/run_tool_logic/settings/install_update', { method: 'POST' });
                const upData = await upRes.json();
                if (upData.status === "success") {
                    status.innerHTML = "✅ Update Complete.";
                    btn.innerText = "OK";
                    btn.disabled = false;
                    setTimeout(() => window.loadLocalManifest(), 1000);
                }
            };
        }
    } catch (err) {
        status.innerText = "Connection failed.";
        btn.disabled = false;
    }
};

// --- SETTINGS TOOL LOGIC END ---

// --- UNPACKER TOOL LOGIC ---
/**
 * Unified Unpacker: Strictly adheres to the Bridge Guard and Python API.
 * Replaces old fetch-based folder picking with the direct bridge method.
 */
window.runUnpacker = async function() {
    // 1. Mandatory Bridge Guard (Cookbook Rule)
    if (!window.checkMetaForgeBridge()) return;

    try {
        // 2. Launch Native OS Picker via the Bridge API
        // This 'await' is critical; it forces the engine to wait for the user's input.
        const path = await window.pywebview.api.select_folder();
        
        // 3. Exit gracefully if user cancels the picker or closes the window
        if (!path) {
            console.log("Unpacker: Folder selection cancelled.");
            return;
        }

        const consoleBox = document.getElementById('unpacker-console');
        if (consoleBox) {
            consoleBox.innerHTML = `<div style="color:#cc9900;">🚀 Starting Unpack sequence for: ${path}</div>`;
        }

        // 4. Execution via Flask Route
        const res = await fetch(`/run_tool_logic/unpack?path=${encodeURIComponent(path)}`);
        const reader = res.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            
            const text = decoder.decode(value);
            if (consoleBox) {
                consoleBox.innerHTML += `<div>${text}</div>`;
                // Mandatory Auto-scroll (Cookbook Phase 3)
                consoleBox.scrollTop = consoleBox.scrollHeight;
            }
        }
    } catch (err) {
        console.error("MetaForge Bridge Error:", err);
        const consoleBox = document.getElementById('unpacker-console');
        if (consoleBox) {
            consoleBox.innerHTML += `<div style="color:#ff4444; font-weight:bold;">❌ BRIDGE EXECUTION ERROR: ${err.message}</div>`;
        }
    }
};
// --- UNPACKER TOOL LOGIC END ---

// --- ACOUSTID TOOL LOGIC ---

window.runAcoustIDTask = async function(taskType) {
    if (!window.checkMetaForgeBridge()) return;

    const consoleBox = document.getElementById('acoustid-console');
    if (!consoleBox) return;

    consoleBox.innerHTML = `<div style="color:#cc9900;">🛰️ Initializing AcoustID ${taskType}...</div>`;

    try {
        const response = await fetch(`/run_tool_logic/acoustid?task=${taskType}`);
        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            const text = decoder.decode(value);
            consoleBox.innerHTML += `<div>${text}</div>`;
            consoleBox.scrollTop = consoleBox.scrollHeight;
        }
    } catch (err) {
        console.error("AcoustID Error:", err);
    }
};
// --- ACOUSTID TOOL LOGIC END ---

// --- [ YOUTUBE TOOL LOGIC START ] ---
/**
 * YouTube Downloader Engine.
 * Note: This tool does NOT use the Bridge/Picker. It uses a server-side path.
 */
window.runYouTubeDownload = async function() {
    const urlInput = document.getElementById('yt-url');
    const consoleBox = document.getElementById('youtube-console');
    const progressContainer = document.getElementById('yt-progress-container');
    const progressBar = document.getElementById('yt-progress');

    if (!urlInput || !urlInput.value) {
        if (consoleBox) consoleBox.innerHTML = '<div style="color:#ff4444;">⚠️ Please enter a YouTube URL.</div>';
        return;
    }

    const url = urlInput.value;
    if (consoleBox) consoleBox.innerHTML = '';
    if (progressContainer) progressContainer.style.display = 'block';

    try {
        // MUST MATCH MetaForge_Routes.py EXACTLY
        const response = await fetch('/run_tool_logic/youtube', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: url })
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            
            const text = decoder.decode(value);
            
            // Execute progress scripts (updateProgress) yielded by Python
            if (text.includes('<script>')) {
                const temp = document.createElement('div');
                temp.innerHTML = text;
                const scripts = temp.querySelectorAll('script');
                scripts.forEach(s => {
                    try { eval(s.innerHTML); } catch(e) { console.error("YT Eval Error", e); }
                });
                
                const cleanText = text.replace(/<script.*?>.*?<\/script>/g, '');
                if (cleanText.trim() && consoleBox) {
                    consoleBox.innerHTML += `<div>${cleanText}</div>`;
                }
            } else {
                if (consoleBox) consoleBox.innerHTML += `<div>${text}</div>`;
            }
            if (consoleBox) consoleBox.scrollTop = consoleBox.scrollHeight;
        }
    } catch (err) {
        console.error("YouTube Download Error:", err);
        if (consoleBox) consoleBox.innerHTML += `<div style="color:#ff4444;">❌ Error: ${err.message}</div>`;
    }
};

window.updateProgress = function(elementId, percent) {
    const bar = document.getElementById(elementId);
    if (bar) bar.style.width = percent + '%';
};
// --- [ YOUTUBE TOOL LOGIC END ] ---

// --- AUDIO REPAIR TOOL LOGIC ---

window.pickRepairFolder = async function() {
    if (!window.checkMetaForgeBridge()) return; 

    try {
        const path = await window.pywebview.api.select_folder();
        if (path) document.getElementById('targetPath').value = path;
    } catch (err) {
        console.error("Audio Repair: Picker failed", err);
    }
};

window.runRepair = async function() {
    const pathInput = document.getElementById('targetPath');
    const consoleDiv = document.getElementById('repairConsole');
    if (!pathInput || !consoleDiv) return;
    const path = pathInput.value.trim();

    if (!path) {
        consoleDiv.innerHTML = '<div style="color:#ff0000;">⚠️ Valid path required.</div>';
        return;
    }

    try {
        const response = await fetch('/route_audio_repair', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: path })
        });
        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            consoleDiv.innerHTML += decoder.decode(value);
            consoleDiv.scrollTop = consoleDiv.scrollHeight;
        }
    } catch (err) {
        console.error("Repair Error:", err);
    }
};

// --- AUDIO REPAIR TOOL LOGIC END ---


// --- MUSICBRAINZ TOOL LOGIC --- 

window.runMusicBrainzWorkflow = async function() {
    if (!window.checkMetaForgeBridge()) return;
    
    const tableBody = document.getElementById('mb-table-body');
    const pathDisplay = document.getElementById('mb-path-display');
    const hiddenInput = document.getElementById('mb-selected-path');

    try {
        const folderPath = await window.pywebview.api.select_folder();
        if (!folderPath) return;

        if (pathDisplay) pathDisplay.innerText = folderPath;
        if (hiddenInput) hiddenInput.value = folderPath;
        
        if (tableBody) tableBody.innerHTML = "<tr><td colspan='6' style='text-align:center; padding:20px; color:#cc9900;'>Analyzing directory...</td></tr>";

        const response = await fetch('/run_tool_logic/musicbrainz', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ task: 'start', path: folderPath })
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        if (tableBody) tableBody.innerHTML = ""; 

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            const chunk = decoder.decode(value);
            
            const tempTable = document.createElement('table');
            tempTable.innerHTML = `<tbody>${chunk}</tbody>`;
            
            const rows = tempTable.querySelectorAll('tr');
            rows.forEach(row => {
                if (tableBody) tableBody.appendChild(row);
            });

            const scripts = tempTable.querySelectorAll('script');
            scripts.forEach(s => {
                const ns = document.createElement('script');
                ns.text = s.text;
                document.body.appendChild(ns).parentNode.removeChild(ns);
            });
        }
    } catch (e) {
        if (tableBody) tableBody.innerHTML = `<tr><td colspan='6' class='error-text'>Bridge Error: ${e.message}</td></tr>`;
    }
};

window.runMBSearch = function() {
    const modal = document.getElementById('mb-modal');
    if (modal) modal.style.display = 'flex';
    window.executeMBLookup();
};

window.executeMBLookup = async function() {
    const artist = document.getElementById('mb-search-artist')?.value || "";
    const album = document.getElementById('mb-search-album')?.value || "";
    const consoleBox = document.getElementById('mb-results-console');
    if (!consoleBox) return;

    consoleBox.innerHTML = `<div style="color: #cc9900;">[SYSTEM] Querying MusicBrainz API...</div>`;
    try {
        const response = await fetch('/run_tool_logic/musicbrainz', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ task: 'search', artist: artist, album: album })
        });
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        consoleBox.innerHTML = ''; 
        while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            consoleBox.innerHTML += decoder.decode(value);
            consoleBox.scrollTop = consoleBox.scrollHeight;
        }
    } catch (err) {
        consoleBox.innerHTML += `<div style="color: #ff4444;">[ERROR] ${err.message}</div>`;
    }
};

window.closeMBModal = function() {
    document.getElementById('mb-modal').style.display = 'none';
};

// --- MUSICBRAINZ TOOL LOGIC END ---


// --- NO EDITS BEYOND THIS POINT - TOOL LOADER MUST COME LAST ---

// --- ENGINE: TOOL LOADER ---

async function loadTool(toolId) {
    const stage = document.getElementById('mfi-content');
    const statusText = document.getElementById('status-text');
    if (!stage) return;

    if (statusText) statusText.innerText = `Module: ${toolId} active.`;

    try {
        const response = await fetch(`/get_tool/${toolId}?v=${new Date().getTime()}`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        stage.innerHTML = await response.text();

        if (toolId === 'settings') {
            window.showSettingsPanel('updates');
        }
    } catch (error) {
        console.error("MetaForge Load Error:", error);
    }
}
// --- ENGINE: TOOL LOADER END ---