// --- START OF FILE tiles/backlog/tile.js ---
// Dashboard tile: What's waiting? (v2, 2026-11-16). Each line opens its tool.
// 2026-11-17 (John): the two "Tracks without…" lines open a list by album
// instead (the tool alone couldn't tell you which tracks); each album's
// button opens the tool that fixes it, with the album folder loaded
// (window.mf_context_path, read by the tool's own ingestContext).
const BACKLOG_LISTS = {
    mb: {
        title: 'Tracks without a MusicBrainz ID',
        intro: 'Choose an album to open it in MusicBrainz IDs with its folder loaded. If MusicBrainz doesn’t have the album, there’s nothing to match until someone adds it at musicbrainz.org.',
        tool: 'musicbrainz_id',
        button: 'Open in MusicBrainz IDs'
    },
    acoustid: {
        title: 'Tracks without an AcoustID',
        intro: 'Choose an album to open it in the Intelli-Tagger. Tagging it again looks each track up on AcoustID again; a track AcoustID doesn’t know goes on AcoustID Manager’s list to submit.',
        tool: 'intelli-tagger',
        button: 'Open in Intelli-Tagger'
    }
};

window.metaforge.dashboardTiles.backlog = {
    render(t, d, kit) {
        const { h, fmt } = kit;
        const asOf = d.lines.find((l) => l.as_of)?.as_of;
        // A line that opens a list is a button (it opens a dialog); a line
        // that opens another tool stays a link.
        const opener = (l) => l.list
            ? h('button', { type: 'button', class: 'db-link', onclick: () => kit.openDetail('backlog', { list: l.list }) }, l.label)
            : h('a', { href: '#', onclick: (e) => { e.preventDefault(); kit.goTo(l.tool); } }, l.label);
        t.body.append(h('ul', { class: 'db-list' }, d.lines.map((l) => h('li', {},
            opener(l),
            l.count === null ? h('span', { class: 'db-muted' }, 'open to count') : h('span', { class: 'db-n' }, fmt(l.count))))));
        if (asOf) t.body.append(h('p', { class: 'db-muted' }, `MusicBrainz count as of ${kit.day(asOf)}.`));
    },

    detail(body, d, kit) {
        const { h, fmt } = kit;
        const L = BACKLOG_LISTS[d.list];
        if (!L) return;
        body.append(h('h3', {}, `${L.title} (${fmt(d.count)})`));
        if (!d.albums.length) { body.append(h('p', { class: 'db-muted' }, 'None.')); return; }
        body.append(h('p', { class: 'db-muted' }, L.intro));
        const openAlbum = (a) => kit.button(L.button, () => {
            kit.closeDetail();
            window.mf_context_path = a.folder;
            kit.goTo(L.tool);
        }, false, { 'aria-label': `${L.button}: ${a.album}` });
        body.append(h('table', { class: 'db-table' },
            h('thead', {}, h('tr', {},
                h('th', { scope: 'col' }, 'Album'),
                h('th', { scope: 'col', class: 'db-n' }, 'Tracks'),
                h('th', { scope: 'col' }, 'Why'),
                h('th', { scope: 'col' }, h('span', { class: 'mf-visually-hidden' }, 'Action')))),
            h('tbody', {}, d.albums.map((a) => h('tr', {},
                h('td', {}, a.album),
                h('td', { class: 'db-n' }, `${fmt(a.missing)} of ${fmt(a.total)}`),
                h('td', {}, a.why),
                h('td', {}, openAlbum(a)))))));
        if (d.more) body.append(h('p', { class: 'db-muted' }, `…and ${fmt(d.more)} more albums.`));
    }
};
