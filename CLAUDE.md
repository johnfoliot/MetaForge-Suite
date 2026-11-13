# MetaForge Suite — Claude Code instructions

## Web UI work: always use `modern-web-guidance`

Use the `modern-web-guidance` skill before writing or changing any user-facing markup, CSS or client-side JS. That includes HTML generated inside Python files (engine log output, f-string templates), not just `.html`/`.css`/`.js` files. Pay particular attention to accessibility (WCAG, COGA).

**Desktop only:** MetaForge is a desktop tool with a minimum window width of 1240px. Don't design or test phone/tablet layouts; do make sure everything fits at 1240px.

**Brand colour:** `#CC9900` is the ONLY gold. Never introduce an alternative gold (lighter, darker or "adjusted for contrast"), including for focus rings or warning colours. Where gold text or thin gold lines would fail WCAG contrast (e.g. on light surfaces), the light theme pivots to its blue (`#1a2fb5`, with `ui/images/logo_blue.svg`) instead of a different gold. `#CC9900` may still be used as a fill behind dark text. The 3-D logo (`logo.svg`) is part of the brand: never replace it with a text wordmark.

**Browser Support:** MetaForge runs only in WebView2 (evergreen Chromium) and is meant to stay fully self-contained. Chromium-supported features may be used without cross-browser fallbacks or polyfills. No CDN or external runtime dependencies; any library must be vendored locally.
