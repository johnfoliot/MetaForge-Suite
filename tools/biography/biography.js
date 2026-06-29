// --- START OF FILE biography.js ---
/**
 * ======================================================================
 * MetaForge Logic Bridge: Biography Builder
 * Build 1.0.16: Added Local Photo Upload & Resizing Logic
 * ======================================================================
 */

window.metaforge = window.metaforge || {};
window.metaforge.biography = {
    observer: null,
    currentArtist: null,

    init: function() {
        const stage = document.getElementById('bio-container-main');
        if (!stage) return;
        if (stage.getAttribute('data-synced') === 'true') return;
        stage.setAttribute('data-synced', 'true');

        setTimeout(() => {
            this.currentArtist = null;
            this.bindEvents();
            this.resetUI();
        }, 10);
    },

    resetUI: function() {
        const artistIn = document.getElementById('bio-artist');
        const bioEd = document.getElementById('bio-text-editor');
        const img = document.getElementById('bio-img-element');
        
        if (artistIn) artistIn.value = "";
        if (bioEd) bioEd.value = "";
        if (img) img.src = '/ui/images/no-photo.png';
        
        const toggle = document.getElementById('bio-profile-toggle');
        if (toggle) {
            toggle.setAttribute('aria-checked', 'false');
            document.getElementById('bio-toggle-label').innerHTML = "Enhanced<br>Bio: Off";
        }
        
        this.setButtonState('get', false);
        this.setButtonState('save', false);
        this.toggleLoading(false);
    },

    bindEvents: function() {
        const searchBtn = document.getElementById('btn-search-artist');
        const saveBtn = document.getElementById('btn-save-biography');
        const getBtn = document.getElementById('btn-get-biography');
        const browseBtn = document.getElementById('btn-browse-photo');

        if (searchBtn) searchBtn.onclick = () => this.performSearch(document.getElementById('bio-artist').value);
        if (saveBtn) saveBtn.onclick = () => this.saveBiography();
        if (getBtn) getBtn.onclick = () => this.generateBiography();
        if (browseBtn) browseBtn.onclick = () => this.handleLocalPhoto();
        
        const toggle = document.getElementById('bio-profile-toggle');
        if (toggle) toggle.onclick = () => this.toggleEnhancedMode(toggle);
    },

    toggleEnhancedMode: function(el) {
        const isChecked = el.getAttribute('aria-checked') === 'true';
        const newState = !isChecked;
        el.setAttribute('aria-checked', newState.toString());
        document.getElementById('bio-toggle-label').innerHTML = newState ? "Enhanced<br>Bio: On" : "Enhanced<br>Bio: Off";
    },

    setButtonState: function(type, enabled) {
        const btn = document.getElementById(type === 'get' ? 'btn-get-biography' : 'btn-save-biography');
        if (btn) btn.disabled = !enabled;
    },

    toggleLoading: function(show) {
        const overlay = document.getElementById('bio-loading-overlay');
        if (overlay) overlay.style.display = show ? 'flex' : 'none';
    },

    performSearch: async function(query) {
        if (!query) return;
        try {
            const res = await fetch(`/run_tool_logic/biography/search?q=${encodeURIComponent(query)}&t=${Date.now()}`);
            const result = await res.json();
            if (result.status === 'success' && result.data.length > 0) {
                this.loadArtist(result.data[0].mf_artist_id);
            } else {
                alert("Artist not found.");
            }
        } catch (e) { console.error("Search Error:", e); }
    },

    loadArtist: async function(mf_id) {
        try {
            const res = await fetch(`/run_tool_logic/biography/get_details?mf_id=${mf_id}&t=${Date.now()}`);
            const result = await res.json();
            if (result.status === 'success') {
                this.currentArtist = result.data;
                document.getElementById('bio-text-editor').value = result.data.biography || "";
                document.getElementById('bio-img-element').src = result.data.md5_hash ? 
                    `/ui/artist_photo/${result.data.md5_hash}?t=${Date.now()}` : '/ui/images/no-photo.png';
                
                const hasBio = (result.data.biography && result.data.biography.trim() !== "");
                this.setButtonState('get', !hasBio);
                this.setButtonState('save', hasBio);
            }
        } catch (e) { console.error("Load Error:", e); }
    },

    handleLocalPhoto: async function() {
        const localPath = document.getElementById('bio-add-photo').value;
        if (!localPath || !this.currentArtist) return alert("Select artist and enter path.");
        
        this.toggleLoading(true);
        const res = await fetch('/run_tool_logic/biography/upload_local_photo', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ 
                artist_name: this.currentArtist.artist_name, 
                local_path: localPath 
            })
        });
        const result = await res.json();
        if (result.status === 'success') {
            document.getElementById('bio-img-element').src = `/ui/artist_photo/${result.md5_hash}?t=${Date.now()}`;
        } else {
            alert("Error: " + result.message);
        }
        this.toggleLoading(false);
    },

    generateBiography: async function() {
        if (!this.currentArtist) return;
        const isEnhanced = document.getElementById('bio-profile-toggle').getAttribute('aria-checked') === 'true';
        this.toggleLoading(true);
        try {
            const res = await fetch('/run_tool_logic/biography/generate_bio', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ 
                    artist_name: this.currentArtist.artist_name, 
                    enhanced: isEnhanced,
                    t: Date.now() 
                })
            });
            const result = await res.json();
            if (result.status === 'success') {
                document.getElementById('bio-text-editor').value = result.biography;
                document.getElementById('bio-img-element').src = `/ui/artist_photo/${result.md5_hash}?t=${Date.now()}`;
                this.setButtonState('get', false);
                this.setButtonState('save', true);
            } else {
                alert("Error: " + result.message);
            }
        } catch (e) { console.error(e); } finally {
            this.toggleLoading(false);
        }
    },

    saveBiography: async function() {
        if (!this.currentArtist) return;
        const payload = {
            mf_artist_id: this.currentArtist.mf_artist_id,
            artist_name: this.currentArtist.artist_name,
            biography: document.getElementById('bio-text-editor').value
        };
        const res = await fetch('/run_tool_logic/biography/save_bio', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        if ((await res.json()).status === 'success') {
            alert("Biography saved.");
            this.init(); 
        }
    }
};

window.metaforge.biography.init();
// --- END OF FILE biography.js ---