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