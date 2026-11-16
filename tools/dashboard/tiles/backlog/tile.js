// --- START OF FILE tiles/backlog/tile.js ---
// Dashboard tile: What's waiting? (v2, 2026-11-16). Each line opens its tool.
window.metaforge.dashboardTiles.backlog = {
    render(t, d, kit) {
        const { h, fmt } = kit;
        const asOf = d.lines.find((l) => l.as_of)?.as_of;
        t.body.append(h('ul', { class: 'db-list' }, d.lines.map((l) => h('li', {},
            h('a', { href: '#', onclick: (e) => { e.preventDefault(); kit.goTo(l.tool); } }, l.label),
            l.count === null ? h('span', { class: 'db-muted' }, 'open to count') : h('span', { class: 'db-n' }, fmt(l.count))))));
        if (asOf) t.body.append(h('p', { class: 'db-muted' }, `MusicBrainz count as of ${kit.day(asOf)}.`));
    }
};
