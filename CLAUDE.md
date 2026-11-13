# MetaForge Suite — Claude Code instructions

## Web UI work: always use `modern-web-guidance`

Use the `modern-web-guidance` skill before writing or changing any user-facing markup, CSS or client-side JS. That includes HTML generated inside Python files (engine log output, f-string templates), not just `.html`/`.css`/`.js` files. Pay particular attention to accessibility (WCAG, COGA).

**Browser Support:** MetaForge runs only in WebView2 (evergreen Chromium) and is meant to stay fully self-contained. Chromium-supported features may be used without cross-browser fallbacks or polyfills. No CDN or external runtime dependencies; any library must be vendored locally.
