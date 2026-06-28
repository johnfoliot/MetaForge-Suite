/* --- START OF FILE [D:\MetaForge Suite\tools\database_tools\album\album_importer.js] --- */
(function() {
    window.metaforge = window.metaforge || {};
    
    // Ensure namespace is never overwritten
    if (!window.metaforge.album_importer) {
        window.metaforge.album_importer = {
            openModal: function() {
                if (document.getElementById("p-json-modal")) return;

                const modal = document.createElement('div');
                modal.id = "p-json-modal";
                modal.style = "position:fixed; top:20%; left:30%; width:40%; background:var(--bg-main); border:1px solid var(--mf-gold); padding:20px; z-index:10000; box-shadow: 0 0 20px rgba(0,0,0,0.5);";
                modal.innerHTML = `
                    <h3 style="color:var(--mf-gold); margin-top:0;">Import JSON Credits</h3>
                    <textarea id="p-json-input" style="width:100%; height:200px; background:var(--input-background2); color:var(--input-foreground2); font-family:monospace; border:1px solid #444;"></textarea>
                    <div style="margin-top:15px; display:flex; gap:10px; justify-content:flex-end;">
                        <button class="mf-button-gold-fixed" onclick="window.metaforge.album_importer.processJson()">Import Data</button>
                        <button class="mf-button-gold-fixed" onclick="document.getElementById('p-json-modal').remove()">Cancel</button>
                    </div>
                `;
                document.body.appendChild(modal);
            },

            processJson: function() {
                try {
                    const raw = document.getElementById('p-json-input').value;
                    const data = JSON.parse(raw);
                    
                    if (!Array.isArray(data)) throw new Error("Invalid format: Expected an array.");

                    data.forEach(entry => {
                        window.metaforge.database_tools.album.addBlankPersonnel();
                        
                        setTimeout(() => {
                            const rows = document.querySelectorAll('#personnel-rows-container tr');
                            const lastRow = rows[rows.length - 1];
                            if (lastRow) {
                                // Locate inputs by their class, which is more reliable
                                const nameInput = lastRow.querySelector('.p-map-name') || lastRow.querySelector('input');
                                const roleInput = lastRow.querySelector('.p-map-role') || lastRow.querySelectorAll('input')[1];
                                if (nameInput) nameInput.value = entry.name || "";
                                if (roleInput) roleInput.value = entry.role || "";
                            }
                        }, 50);
                    });

                    document.getElementById('p-json-modal').remove();
                } catch (e) {
                    alert("Error parsing JSON: " + e.message);
                }
            }
        };
    }
})();
/* --- END OF FILE [D:\MetaForge Suite\tools\database_tools\album\album_importer.js] --- */