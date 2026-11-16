// --- START OF FILE dashboard.js ---
// MetaForge Tool: Dashboard
// MOCK-UP (2026-11-16): only opens the dialogs and switches the Progress
// view, so John can try the layout. No data is loaded yet.
window.metaforge = window.metaforge || {};
window.metaforge.dashboard = {

    init: function () {
        const $ = (id) => document.getElementById(id);
        if (!$('db-tiles')) return;
        document.querySelectorAll('[data-db-open]').forEach((btn) => {
            btn.addEventListener('click', () => $(btn.dataset.dbOpen)?.showModal());
        });
        $('db-customize-btn').addEventListener('click', () => $('db-dlg-custom').showModal());
        document.querySelectorAll('input[name="db-view"]').forEach((r) => {
            r.addEventListener('change', () => {
                $('db-view-folder').hidden = r.value !== 'folder';
                $('db-view-genre').hidden = r.value !== 'genre';
            });
        });
        $('db-threshold-form').addEventListener('submit', (e) => e.preventDefault());
    },

    destroy: function () {}
};
