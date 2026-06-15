/* --- START OF FILE personnel_manual.js --- */
/**
 * MetaForge Studio: Personnel - Manual Entry Sidecar
 * Role: Manages the manual input modal and syncs with Personnel state.
 * Physical Location: \tools\personnel\personnel_manual.js
 */

window.metaforge = window.metaforge || {};
window.metaforge.personnel_manual = {

    open: function() {
        const modal = document.getElementById('p-manual-modal');
        if (modal) {
            modal.style.display = 'flex';
            document.getElementById('p-manual-name').focus();
        }
    },

    close: function() {
        const modal = document.getElementById('p-manual-modal');
        if (modal) {
            modal.style.display = 'none';
            document.getElementById('p-manual-name').value = '';
            document.getElementById('p-manual-role').value = '';
        }
    },

    accept: function() {
        const name = document.getElementById('p-manual-name').value.trim();
        const role = document.getElementById('p-manual-role').value.trim();

        if (name && role) {
            // Push directly to the primary Personnel state
            window.metaforge.personnel.state.mapping.push({ name: name, role: role });
            
            // Re-render the main mapping UI using the existing function
            window.metaforge.personnel.renderMapping();
            
            // Activate the commit button (mirroring your existing logic)
            const commitBtn = document.getElementById('p-commit-btn');
            if (commitBtn) {
                commitBtn.style.opacity = "1";
                commitBtn.disabled = false;
            }
            
            this.close();
        } else {
            alert("Both Name and Role are required.");
        }
    }
};
/* --- END OF FILE personnel_manual.js --- */