# MetaForge Suite: Production & Engineering Standards

## 1. Architectural Philosophy
MetaForge is a **Plugin-Based Suite**. The core system (Shell) acts as an orchestrator, while functionality is siloed into independent tool modules.

### Directory Structure
- `\ui`: The Application Shell (Flask, Global CSS, Base Templates).
- `\tools`: Functional modules. Each tool must be atomic, containing its own logic, UI fragment, and metadata.
- `\common`: Shared Python logic (Database handlers, Environment loaders).
- `\data`: Global reference assets (Taxonomy, Tag Whitelists).
- `\bin`: External binaries (fpcalc, ffmpeg).
- `\logs`: Diagnostic output (mapped to %APPDATA% in production).

---

## 2. Tool Integration (The Discovery Protocol)
Every tool must contain a `manifest.json`. The Shell performs a "Discovery Scan" on startup to register tools dynamically.

### SVG Icon Strategy (Embedded XML)
- **Deployment:** Tool icons live in the tool's root as `[tool_name].svg`.
- **Injection:** The Shell reads raw SVG XML and injects it directly into the DOM.
- **Styling:** SVGs must use `fill="currentColor"` or omit hardcoded fills to allow the Global CSS to apply `--mf-gold` or state-based colors dynamically.

### UI Fragments (.mfi)
- Tool UIs are authored as `.mfi` (MetaForge Include) files.
- **Elastic Layouts:** Fragments must not use hardcoded `vh` heights. They must be designed to fill the "Stage" container provided by the Shell.
- **Scoped CSS:** All tool-specific styles must be scoped to the tool's ID to prevent global style leakage.

---

## 3. UI/UX & Accessibility Standards
- **Typography:** `text-align: justify` is strictly prohibited.
- **Color System:** All styles must reference the MetaForge Unified Palette via CSS Variables.
- **Hierarchy:** Use semantic HTML (`<thead>`, `<main>`, `<section>`) to ensure WCAG compliance and professional-grade document structure.
- **Responsiveness:** Use Flexbox/Grid for "elastic" containers that adapt to window resizing.
- **Compliance:** All UI output content MUST (RFC 2119) comply with WCAG 2.1 (https://www.w3.org/TR/WCAG21/). Interactive components must either use native elements (<button>) or include the appropriate ARIA markup (https://www.w3.org/TR/wai-aria-1.3/)

---

## 4. Development & Git Workflow
- **Strict Logic Separation:** Sensitive data (API Keys, local paths) must reside in `%APPDATA%\MetaForge\.env` and are never committed to version control.
- **Atomic Commits:** Changes to `\common` logic and the tools that depend on them should be committed together to maintain system integrity.
- **Code Quality:** All generated code must be complete, functional, and "Save-Ready." Placeholder logic or partial remediations are unacceptable.
