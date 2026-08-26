CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    google_email TEXT  -- optional: this admin's Google account, for OAuth sign-in (see auth.py)
);

-- One row per failed /admin/login attempt, keyed by client IP — a sliding
-- window lockout (see auth.py's _login_rate_limited). Kept in the DB (not
-- in-process memory) since gunicorn runs multiple worker processes with
-- no shared memory between them.
CREATE TABLE IF NOT EXISTS login_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ip TEXT NOT NULL,
    attempted_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Every AI-generated image, kept even after it stops being used anywhere —
-- generating is slow/costly enough (15s-2min) that a rejected variant or
-- an old one no longer in use should still be picked back up later rather
-- than regenerated from scratch. url points at the same /static/uploads
-- file a manual upload would use, so nothing downstream needs to treat a
-- generated image differently from an uploaded one. Deleted only by an
-- explicit admin action (see admin.py's generated_image_delete).
CREATE TABLE IF NOT EXISTS generated_images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    prompt TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    css_path TEXT,
    is_active INTEGER NOT NULL DEFAULT 0,
    is_builtin INTEGER NOT NULL DEFAULT 0,
    header_sections TEXT,  -- JSON list of HTML chunks, each independently editable
    footer_sections TEXT,  -- JSON list of HTML chunks, each independently editable
    layout_json TEXT,
    palette_json TEXT,      -- JSON list of {slug, name, color} — the theme's full color palette
    color_overrides TEXT,   -- JSON {slug: color} — admin's picked replacements
    google_fonts_url TEXT,  -- Google Fonts stylesheet link, if the theme uses a Google-hosted font
    nav_layout TEXT NOT NULL DEFAULT 'topbar'  -- structural nav position: topbar, split, centered, sidebar, minimal
);

CREATE TABLE IF NOT EXISTS pages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    is_home INTEGER NOT NULL DEFAULT 0,
    nav_order INTEGER NOT NULL DEFAULT 0,
    page_type TEXT NOT NULL DEFAULT 'standard',   -- 'standard' or 'blog'
    blog_card_style TEXT NOT NULL DEFAULT 'grid-3', -- blog pages: grid-3, grid-2, list
    bg_color TEXT,  -- optional page-wide background color override
    meta_description TEXT,  -- SEO: <meta name="description">, shown in search results
    nav_layout_override TEXT,  -- NULL = use the site-wide nav_layout setting
    hide_sidebar INTEGER NOT NULL DEFAULT 0,        -- skip the sidebar zone on this page even if the active template has content there
    hide_sidebar_right INTEGER NOT NULL DEFAULT 0,
    hide_footer INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS content_tools (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    icon TEXT NOT NULL DEFAULT '🧰',
    section_type TEXT NOT NULL,   -- matches sections.type
    block_key TEXT,               -- optional BLOCK_LIBRARY key for a starter layout
    starter_content TEXT,         -- optional starter HTML/content for custom tools
    is_builtin INTEGER NOT NULL DEFAULT 0,
    position INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS menus (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS menu_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    menu_id INTEGER NOT NULL REFERENCES menus(id) ON DELETE CASCADE,
    page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    position INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS blog_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    slug TEXT NOT NULL,
    excerpt TEXT,
    content TEXT,
    featured_image TEXT,
    published_at TEXT,   -- ISO date string, e.g. 2026-08-19; blank = draft
    position INTEGER NOT NULL DEFAULT 0,
    UNIQUE(page_id, slug)
);

CREATE TABLE IF NOT EXISTS sections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    page_id INTEGER REFERENCES pages(id) ON DELETE CASCADE,      -- set for body sections
    template_id INTEGER REFERENCES templates(id) ON DELETE CASCADE, -- set for header/footer sections
    zone TEXT NOT NULL DEFAULT 'body',  -- 'body', 'header', 'sidebar', 'sidebar_right', 'footer'
    type TEXT NOT NULL,          -- 'header', 'text', 'html', 'image', 'file'
    title TEXT,
    content TEXT,
    position INTEGER NOT NULL DEFAULT 0,
    width TEXT NOT NULL DEFAULT 'normal',  -- image sizing: small, medium, large, full
    link_url TEXT,                          -- image sections: wrap image in a link
    animation TEXT NOT NULL DEFAULT 'none', -- image sections: none, fade-in, zoom-hover
    file_size INTEGER,                      -- file sections: byte size, for display
    file_display TEXT NOT NULL DEFAULT 'card', -- file sections: card, button, text-link, icon
    mask_shape TEXT NOT NULL DEFAULT 'none', -- image sections: none, rounded, circle, square, diamond, hexagon, star
    media_type TEXT NOT NULL DEFAULT 'youtube', -- media sections: youtube, video, audio
    bg_color TEXT,  -- optional per-section background color override
    layout_width TEXT NOT NULL DEFAULT 'auto', -- auto (theme default), full (edge-to-edge), custom (see layout_width_pct)
    layout_width_pct INTEGER,  -- % of the page's content width, only used when layout_width = 'custom'
    sidebar_width TEXT NOT NULL DEFAULT 'auto', -- sidebar sections only: auto (240px default) or custom (see sidebar_width_px) — the rail's own width, independent of layout_width/layout_width_pct which that same section reuses for HEIGHT there
    sidebar_width_px INTEGER,   -- rail width in px, only used when sidebar_width = 'custom'
    content_height_px INTEGER  -- horizontal (non-sidebar) sections only: an explicit height in px, set by dragging the section's bottom edge; NULL = auto (normal content-driven height)
);

-- A short (3-deep) global undo stack for section-structure changes —
-- reorders, tool drops that overwrite a section, delete/clear/divide —
-- the kind of action a bad drag-and-drop makes with no other way back.
-- Each row is a full snapshot of every section in the affected scope
-- (one page's body, or one template+zone) captured right BEFORE that
-- mutation runs, so Undo is always "replace this scope's sections with
-- exactly what they were" rather than trying to invert each action type
-- individually. Capped at 3 rows (see _undo_snapshot) — oldest dropped.
CREATE TABLE IF NOT EXISTS undo_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    description TEXT NOT NULL,
    page_id INTEGER,
    template_id INTEGER,
    zone TEXT,
    next_url TEXT,
    sections_json TEXT NOT NULL
);
