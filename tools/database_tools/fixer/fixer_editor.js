// --- START OF FILE fixer_editor.js ---
window.metaforge = window.metaforge || {};
window.metaforge.database_tools = window.metaforge.database_tools || {};

window.metaforge.database_tools.fixer_editor = {
    diagnose: async function() {
        const term = document.getElementById('fix-term').value;
        const results = document.getElementById('fix-results');
        const cat = document.querySelector('input[name="fix-cat"]:checked').value;
        
        if (!term) return;

        try {
            const res = await fetch('/run_tool_logic/database_tools/diagnose', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({term: term, category: cat})
            });

            if (!res.ok) throw new Error("Server returned " + res.status);
            
            const data = await res.json();
            
            if (data.status === "success") {
                let html = '<form id="fix-select-form">';
                data.data.forEach(item => {
                    html += `<div><input type="radio" name="fix-target" value="${item.type}:${item.id}"> 
                             [${item.type.toUpperCase()}] ${item.display}</div>`;
                });
                html += '</form>';
                results.innerHTML = html || '<p>No matches found.</p>';
                document.getElementById('fix-nuke-btn').disabled = (data.data.length === 0);
                
                results.focus();
            } else {
                results.innerHTML = `<p style="color:red;">Error: ${data.message}</p>`;
            }
        } catch (err) {
            console.error("Diagnostic error:", err);
            results.innerHTML = `<p style="color:red;">Diagnostic failed.</p>`;
        }
    },

    purge: function() {
        const selected = document.querySelector('input[name="fix-target"]:checked');
        if (!selected || !confirm("Permanently delete this record?")) return;
        
        const [type, id] = selected.value.split(':');
        
        fetch('/run_tool_logic/database_tools/purge', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({type: type, id: id})
        })
        .then(res => res.json())
        .then(data => {
            if (data.status === "success") {
                alert(data.message);
                this.diagnose();
            } else {
                alert("Error: " + data.message);
            }
        })
        .catch(err => {
            console.error("Purge error:", err);
            alert("Purge failed.");
        });
    }
};
// --- END OF FILE fixer_editor.js ---