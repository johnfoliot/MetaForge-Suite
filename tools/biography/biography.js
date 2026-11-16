// --- START OF FILE biography.js ---
/**
 * ======================================================================
 * MetaForge Logic Bridge: Bio Builder
 * v2 (2026-11-15): per-tool pass.
 *  - Grounded bios with their sources; an unsourced bio is flagged.
 *  - The portrait is a draft until Save (nothing on disk changes before).
 *  - Regenerate for artists who already have a bio (John), with a confirm
 *    before replacing text that's in the editor.
 *  - Arriving from Intelli-Tagger / Album Personnel loads the album's artist.
 *  - No blocking alert()s: a status line + the shared announcer.
 * ======================================================================
 */

window.metaforge = window.metaforge || {};
window.metaforge.biography = {
    currentArtist: null,
    savedText: '',          // what's in the database, to spot unsaved edits
    draftPhoto: false,      // a draft portrait is waiting for Save

    $: (id) => document.getElementById(id),

    init: function() {
        const stage = document.getElementById('bio-container-main');
        if (!stage || stage.getAttribute('data-synced') === 'true') return;
        stage.setAttribute('data-synced', 'true');
        setTimeout(() => {
            this.currentArtist = null;
            this.draftPhoto = false;
            this.bindEvents();
            this.resetUI();
            this.ingestContext();
        }, 10);
    },

    bindEvents: function() {
        this.$('bio-search-form').addEventListener('submit', (e) => {
            e.preventDefault();
            this.performSearch(this.$('bio-artist').value);
        });
        this.$('btn-get-biography').addEventListener('click', () => this.generateBiography());
        this.$('btn-save-biography').addEventListener('click', () => this.saveBiography());
        this.$('btn-browse-photo').addEventListener('click', () => this.browsePhoto());
        this.$('bio-text-editor').addEventListener('input', () => this.updateDirty());
        this.$('bio-candidate-list').addEventListener('click', (e) => {
            const b = e.target.closest('button[data-id]');
            if (b) { this.hideCandidates(); this.loadArtist(b.dataset.id); }
        });
    },

    resetUI: function() {
        this.$('bio-artist').value = '';
        this.setEditor('');
        this.setPortrait(null);
        this.hideCandidates();
        this.showSources(null);
        this.setStatus('', '');
        this.$('btn-get-biography').disabled = true;
        this.$('btn-save-biography').disabled = true;
        this.$('bio-dirty').textContent = '';
    },

    // ------------------------------------------------------------ helpers
    setStatus: function(msg, kind, speak) {
        const el = this.$('bio-status');
        el.textContent = msg;
        el.className = kind === 'error' ? 'is-error' : (kind === 'ok' ? 'is-ok' : '');
        if (speak && msg) window.MFAnnounce?.(kind === 'error' ? `Error: ${msg}` : msg);
    },

    setEditor: function(text) {
        const ed = this.$('bio-text-editor');
        ed.value = text;
        ed.dispatchEvent(new Event('scroll'));   // resync the custom scrollbar (see biography.mfi)
        this.updateDirty();
    },

    toggleLoading: function(show) {
        this.$('bio-busy').hidden = !show;
        this.$('bio-left').inert = show;
        document.querySelector('.bio-right').inert = show;
        if (show) window.MFAnnounce?.('Writing the biography. This can take a little while.');
    },

    /** Saved portrait, draft portrait, or none; with an honest caption. */
    setPortrait: function(mode, info) {
        const img = this.$('bio-img-element');
        const cap = this.$('bio-photo-caption');
        const a = this.currentArtist;
        cap.replaceChildren();
        if (!a || !mode) {
            img.src = '/ui/images/no-photo.png';
            img.alt = 'No portrait yet';
            cap.textContent = a ? `${a.artist_name} has no portrait yet.` : 'Choose an artist to see their portrait.';
            return;
        }
        const name = a.artist_name;
        if (mode === 'saved') {
            img.src = `/ui/artist_photo/${a.md5_hash}?t=${Date.now()}`;
            img.alt = `Portrait of ${name}`;
            cap.textContent = 'Saved portrait.';
        } else {
            img.src = `/run_tool_logic/biography/draft_photo?md5=${a.md5_hash}&t=${Date.now()}`;
            img.alt = `Draft portrait of ${name}`;
            cap.append('Draft portrait: replaces the saved one only when you save. ');
            if (info?.match) {
                if (info.exact) cap.append(`From Discogs artist “${info.match}”.`);
                else {
                    const w = document.createElement('span');
                    w.className = 'is-warn';
                    w.textContent = `Discogs' closest match was “${info.match}”, not an exact name match. Check it's the right artist.`;
                    cap.append(w);
                }
            } else if (info?.file) {
                cap.append('From the file you chose.');
            }
        }
    },

    showSources: function(sources, grounded) {
        const box = this.$('bio-sources');
        const warn = this.$('bio-unverified');
        if (sources === null) { box.hidden = true; warn.hidden = true; return; }
        warn.hidden = !!grounded;
        box.hidden = !sources.length;
        this.$('bio-sources-summary').textContent = `Sources (${sources.length})`;
        this.$('bio-sources-list').replaceChildren(...sources.map(s => Object.assign(document.createElement('li'), { textContent: s })));
    },

    updateDirty: function() {
        const ed = this.$('bio-text-editor');
        const changed = !!this.currentArtist && (ed.value !== this.savedText || this.draftPhoto);
        this.$('btn-save-biography').disabled = !this.currentArtist || !ed.value.trim() || !changed;
        this.$('bio-dirty').textContent = changed ? 'Not saved yet.' : '';
    },

    // ------------------------------------------------------------ context + search
    ingestContext: async function() {
        // v2: Database Tools' "Write a biography" hands over the artist itself.
        const artistId = window.mf_context_artist_id;
        if (artistId) {
            window.mf_context_artist_id = null;
            return this.loadArtist(artistId);
        }
        const path = window.mf_context_path;
        if (!path) return;
        window.mf_context_path = null;
        try {
            const res = await fetch('/run_tool_logic/biography/folder_artist', {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path })
            });
            const data = await res.json();
            if (data.status === 'success' && data.artist) {
                this.$('bio-artist').value = data.artist;
                this.performSearch(data.artist);
            }
        } catch (e) { /* stays on an empty search: nothing lost */ }
    },

    performSearch: async function(query) {
        query = (query || '').trim();
        if (!query) { this.setStatus('Type an artist name to search.', 'error', true); return; }
        this.hideCandidates();
        try {
            const res = await fetch(`/run_tool_logic/biography/search?q=${encodeURIComponent(query)}&t=${Date.now()}`);
            const result = await res.json();
            const matches = result.status === 'success' ? result.data : [];
            if (!matches.length) {
                this.setStatus(`No artist called “${query}” is in the MetaForge database.`, 'error', true);
                return;
            }
            // Exact (case-insensitive) match loads directly. Otherwise the user
            // picks: 1.x took the first substring match, and a bio was once
            // saved to the wrong artist ("Ace" matched "John Ac-erno").
            const exact = matches.filter(m => m.artist_name.toLowerCase() === query.toLowerCase());
            if (exact.length === 1) return this.loadArtist(exact[0].mf_artist_id);
            if (matches.length === 1) return this.loadArtist(matches[0].mf_artist_id);
            this.showCandidates(matches);
        } catch (e) {
            this.setStatus("The search couldn't be completed.", 'error', true);
        }
    },

    showCandidates: function(matches) {
        const items = matches.map(m => {
            const li = document.createElement('li');
            const b = document.createElement('button');
            b.type = 'button';
            b.className = 'bio-candidate';
            b.dataset.id = m.mf_artist_id;
            b.append(m.artist_name);
            if (m.country) {
                const c = document.createElement('span');
                c.className = 'bio-candidate-country';
                c.textContent = ` (${m.country})`;
                b.append(c);
            }
            li.append(b);
            return li;
        });
        this.$('bio-candidate-list').replaceChildren(...items);
        this.$('bio-candidates').hidden = false;
        this.setStatus(`${matches.length} artists match. Choose one.`, '', true);
        this.$('bio-candidate-list').querySelector('button')?.focus();
    },

    hideCandidates: function() {
        this.$('bio-candidates').hidden = true;
        this.$('bio-candidate-list').replaceChildren();
    },

    loadArtist: async function(mf_id) {
        // A draft portrait for the previous artist is thrown away, not kept.
        if (this.draftPhoto && this.currentArtist) this.discardDraft(this.currentArtist.artist_name);
        try {
            const res = await fetch(`/run_tool_logic/biography/get_details?mf_id=${encodeURIComponent(mf_id)}&t=${Date.now()}`);
            const result = await res.json();
            if (result.status !== 'success') { this.setStatus("That artist couldn't be loaded.", 'error', true); return; }
            this.currentArtist = result.data;
            this.draftPhoto = false;
            this.savedText = result.data.biography || '';
            this.$('bio-artist').value = result.data.artist_name;
            this.$('bio-add-photo').value = '';
            this.setEditor(this.savedText);
            this.setPortrait(result.data.has_photo ? 'saved' : null);
            this.showSources(null);
            const hasBio = !!this.savedText.trim();
            const get = this.$('btn-get-biography');
            get.disabled = false;
            get.textContent = hasBio ? 'Regenerate Biography' : 'Get Biography';
            this.setStatus(hasBio ? `${result.data.artist_name}: biography loaded. Edit it, or regenerate it.`
                                  : `${result.data.artist_name} has no biography yet.`, 'ok', true);
        } catch (e) {
            this.setStatus("That artist couldn't be loaded.", 'error', true);
        }
    },

    discardDraft: function(name) {
        fetch('/run_tool_logic/biography/discard_draft', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ artist_name: name })
        }).catch(() => {});
        this.draftPhoto = false;
    },

    // ------------------------------------------------------------ portrait from a file
    browsePhoto: async function() {
        if (!this.currentArtist) { this.setStatus('Choose an artist first.', 'error', true); return; }
        const res = await fetch('/select_file');
        const data = await res.json();
        if (!data.path) return;
        this.$('bio-add-photo').value = data.path;
        try {
            const r = await fetch('/run_tool_logic/biography/upload_local_photo', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ artist_name: this.currentArtist.artist_name, local_path: data.path })
            });
            const result = await r.json();
            if (result.status === 'success') {
                this.draftPhoto = true;
                this.setPortrait('draft', { file: true });
                this.updateDirty();
                this.setStatus('Draft portrait ready. Save to keep it.', 'ok', true);
            } else {
                this.setStatus(result.message || "That image couldn't be used.", 'error', true);
            }
        } catch (e) {
            this.setStatus("That image couldn't be used.", 'error', true);
        }
    },

    // ------------------------------------------------------------ generate / regenerate
    confirmReplace: function() {
        const dlg = this.$('bio-regen-dialog');
        return new Promise((resolve) => {
            dlg.addEventListener('close', () => resolve(dlg.returnValue === 'replace'), { once: true });
            dlg.returnValue = '';
            dlg.showModal();
        });
    },

    generateBiography: async function() {
        if (!this.currentArtist) return;
        if (this.$('bio-text-editor').value.trim() && !(await this.confirmReplace())) {
            this.$('btn-get-biography').focus();
            return;
        }
        this.toggleLoading(true);
        try {
            const res = await fetch('/run_tool_logic/biography/generate_bio', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ artist_name: this.currentArtist.artist_name,
                                       mf_artist_id: this.currentArtist.mf_artist_id,
                                       enhanced: this.$('bio-enhanced').checked })
            });
            const result = await res.json();
            if (result.status === 'success') {
                this.setEditor(result.biography);
                this.showSources(result.sources || [], result.grounded);
                if (result.draft_photo) {
                    this.draftPhoto = true;
                    this.setPortrait('draft', { match: result.photo_match, exact: result.photo_exact });
                }
                this.updateDirty();
                const n = (result.sources || []).length;
                this.setStatus(result.grounded ? `Biography written from ${n} web source${n === 1 ? '' : 's'}. Review it, then save.`
                                               : 'Biography written without web sources. Check the facts before saving.',
                               result.grounded ? 'ok' : 'error', true);
            } else {
                this.setStatus(result.message || "The biography couldn't be written.", 'error', true);
            }
        } catch (e) {
            this.setStatus("The biography couldn't be written (no reply).", 'error', true);
        } finally {
            this.toggleLoading(false);
            this.$('bio-text-editor').focus();
        }
    },

    // ------------------------------------------------------------ save
    saveBiography: async function() {
        if (!this.currentArtist) return;
        const text = this.$('bio-text-editor').value;
        this.$('btn-save-biography').disabled = true;
        try {
            const res = await fetch('/run_tool_logic/biography/save_bio', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ mf_artist_id: this.currentArtist.mf_artist_id,
                                       artist_name: this.currentArtist.artist_name,
                                       biography: text, use_draft_photo: this.draftPhoto })
            });
            const result = await res.json();
            if (result.status === 'success') {
                const hadDraft = this.draftPhoto;
                this.savedText = text;
                this.draftPhoto = false;
                if (hadDraft) this.setPortrait('saved');
                this.$('btn-get-biography').textContent = 'Regenerate Biography';
                const n = this.currentArtist.artist_name;
                const owner = /s$/i.test(n) ? `${n}'` : `${n}'s`;   // "The Meters'", "Marianne Faithfull's"
                this.setStatus(`Saved ${owner} biography${hadDraft ? ' and portrait' : ''}.`, 'ok', true);
            } else {
                this.setStatus(result.message || "The biography couldn't be saved.", 'error', true);
            }
        } catch (e) {
            this.setStatus("The biography couldn't be saved (no reply).", 'error', true);
        } finally {
            this.updateDirty();
        }
    }
};

window.metaforge.biography.init();
// --- END OF FILE biography.js ---
