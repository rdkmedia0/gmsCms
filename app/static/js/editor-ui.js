// The editor's toolbars, arranged: one group of settings at a time, so the
// thing being edited stays on screen.
//
// A layer over the server's markup, not a second copy of it. Every control
// is the one the page already sent, with its own listeners; this only
// shows one group at a time and draws friendlier faces for two selects.
// Without this script the toolbars are simply all open, as before.
(function () {
  "use strict";
  if (!document.body.classList.contains("cms-editing")) return;

  //  Which tab each tool was left on, so a redraw does not jump away. Kept
  //  for this browser tab too: some tools reload the page to save, which
  //  would otherwise put the toolbar back on its first tab every time.
  const STORE = "cms-ui-tabs";
  let kept = [];
  try { kept = JSON.parse(sessionStorage.getItem(STORE) || "[]"); } catch { kept = []; }
  const chosen = new Map(kept);
  const remember = (key, name) => {
    chosen.set(key, name);
    try { sessionStorage.setItem(STORE, JSON.stringify([...chosen])); } catch { /* private window */ }
  };
  const wired = new WeakSet();

  const make = (tag, className, text) => {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (text) el.textContent = text;
    return el;
  };

  // ---------- Banner: one tab per group ----------
  const TAB_NAMES = [
    ["Text", (label) => label.startsWith("text — whole")],
    ["Background", (label) => label.startsWith("background")],
    ["Text box", (label) => label.startsWith("text box")],
    ["Portrait", (label) => label.startsWith("portrait")],
    ["Button", (label) => label.startsWith("button")],
  ];

  function tabsFor(form) {
    if (wired.has(form)) return;
    wired.add(form);
    const groups = [...form.querySelectorAll(":scope > .cms-banner-text-config")];
    if (!groups.length) return;
    const found = TAB_NAMES.map(([name, matches]) => {
      const group = groups.find((g) => matches(
        (g.querySelector(".cms-banner-text-config-label")?.textContent || "").trim().toLowerCase()));
      return group ? { name, group } : null;
    }).filter(Boolean);
    if (!found.length) return;

    //  The ribbon for selected words belongs with the other text controls.
    //  Its buttons are all type="button", so they are inert to the form.
    const words = found.find((t) => t.name === "Text");
    const header = form.closest(".cms-tool-header-controls") || form.parentElement;
    const ribbonLabel = header.querySelector(":scope > .cms-banner-ribbon-label");
    if (words && ribbonLabel) {
      const row = make("div", "cms-ui-ribbon-row");
      const ribbon = ribbonLabel.nextElementSibling;
      row.append(ribbonLabel);
      if (ribbon && ribbon.classList.contains("cms-wysiwyg-toolbar")) row.append(ribbon);
      words.group.append(row);
    }

    const key = form.getAttribute("action") || "";
    const bar = make("div", "cms-ui-tabs");
    bar.setAttribute("role", "tablist");
    const show = (name) => {
      remember(key, name);
      found.forEach((tab) => {
        const on = tab.name === name;
        tab.group.hidden = !on;
        tab.button.classList.toggle("is-active", on);
        tab.button.setAttribute("aria-selected", on ? "true" : "false");
      });
    };
    found.forEach((tab) => {
      tab.button = make("button", "cms-ui-tab", tab.name);
      tab.button.type = "button";
      tab.button.setAttribute("role", "tab");
      tab.button.addEventListener("click", () => show(tab.name));
      tab.group.classList.add("cms-ui-tab-panel");
      tab.group.setAttribute("role", "tabpanel");
      bar.append(tab.button);
    });
    groups[0].before(bar);
    show(found.some((t) => t.name === chosen.get(key)) ? chosen.get(key) : found[0].name);
  }

  // ---------- The other tools with enough settings to need tabs ----------
  //  Which controls go under which tab, in the order the tabs are shown.
  //  A control a rule does not name stays where it was, so a setting added
  //  later is never lost -- it just is not tabbed until it is listed here.
  //  `root` is what the tabs are built inside; controls are looked for
  //  across the whole toolbar, since some sit outside the form.
  const TOOLS = [
    { root: ".cms-card-config-form", tabs: [
      ["Text", [".cms-wysiwyg-toolbar"]],
      ["Style", ['[name="shape"]', ".cms-swatches", ".cms-reset-card-btn"]],
      ["Picture", [".cms-pick-library-btn", ".cms-change-card-image-btn",
                   ".cms-clear-card-image-btn", ".cms-generate-image-btn"]],
      ["Button", ['[name="button"]', '[name="button_link"]', '[name="new_tab"]', '[name="button_color"]']],
    ] },
    { root: ".cms-blog-config-form", tabs: [
      ["Posts", ['[name="blog_id"]', '[name="blog_name"]', '[name="blog_count"]',
                 '.cms-faq-config-row:has([name="blog_new_name"])', 'a[href*="/posts/new"]', ".hint"]],
      ["Layout", ['[name="blog_style"]', '[name="blog_image"]']],
    ] },
    { root: ".cms-block-config-form:has(> .cms-gallery-manage)", tabs: [
      ["Pictures", [".cms-gallery-manage"]],
      ["Layout", ['[name="layout"]', '[name="size"]', '[name="fit"]', '[name="zoom"]']],
    ] },
    { root: ".cms-menu-builder", tabs: [
      ["Items", [".cms-menu-pages-picker"]],
      ["Style", ['[name="menu_style"]', '[name="menu_button_style"]', '[name="menu_submenu_style"]',
                 '[name="menu_size"]', '[name="menu_font"]', '[name="menu_link_style"]']],
      ["Layout", ['[name="menu_align"]', '[name="menu_direction"]', '[name="menu_highlight_current"]']],
      ["Colours", ['[name="menu_text_color_on"]', '[name="menu_text_color"]',
                   '[name="menu_bg_color_on"]', '[name="menu_bg_color"]']],
    ] },
    { root: ".cms-accordion-config-form", tabs: [
      ["Panels", ['.cms-accordion-style-row:has(.cms-stepper)', ".hint", ".cms-accordion-panel-config"]],
      ["Style", ['.cms-accordion-style-row:has([name="style"])']],
    ] },
    { root: ".cms-video-gallery-config-form", tabs: [
      ["Videos", [".hint", ".cms-video-clip-config", ".cms-video-clip-add"]],
      ["Layout", [".cms-video-config-row"]],
    ] },
    //  The Image tool has no form: its controls save one at a time.
    { root: ".cms-tool-header-controls:has(> .cms-image-file-input)", tabs: [
      ["Picture", [".cms-pick-library-btn", ".cms-change-image-btn",
                   ".cms-generate-image-btn", ".cms-caption-input"]],
      ["Display", [".cms-width-select", ".cms-anim-select", ".cms-mask-select"]],
      ["Link", [".cms-link-input", ".cms-newtab-check"]],
    ] },
  ];

  //  Names for the drop-downs that never had one beside them.
  const CAPTIONS = [
    ['.cms-card-config-form select[name="shape"]', "Shape"],
    ['select[name="button_color"]', "Button colour"],
    ['select[name="menu_style"]', "Menu style"],
    ['select[name="menu_button_style"]', "Button style"],
    ['select[name="menu_submenu_style"]', "Submenu style"],
    ['select[name="menu_size"]', "Size"],
    ['select[name="menu_font"]', "Font"],
    ['select[name="menu_link_style"]', "Link text"],
    ['select[name="menu_align"]', "Align"],
    ['select[name="menu_direction"]', "Direction"],
    ["select.cms-width-select", "Width"],
    ["select.cms-anim-select", "Animation"],
    ["select.cms-mask-select", "Cut-out"],
  ];

  //  Settings every tool shares go in one row at the foot of its toolbar.
  const SHARED = [".cms-heading-controls", ".cms-tool-corner-select",
                  ".cms-tool-shadow-select", ".cms-tool-color-select"].join(",");

  function tabbed(root, groups, key, before) {
    const bar = make("div", "cms-ui-tabs");
    bar.setAttribute("role", "tablist");
    const show = (name) => {
      remember(key, name);
      groups.forEach((tab) => {
        const on = tab.name === name;
        tab.panel.hidden = !on;
        tab.button.classList.toggle("is-active", on);
        tab.button.setAttribute("aria-selected", on ? "true" : "false");
      });
    };
    groups.forEach((tab) => {
      tab.button = make("button", "cms-ui-tab", tab.name);
      tab.button.type = "button";
      tab.button.setAttribute("role", "tab");
      tab.button.addEventListener("click", (e) => { e.stopPropagation(); show(tab.name); });
      tab.panel.setAttribute("role", "tabpanel");
      bar.append(tab.button);
    });
    if (before) before.before(bar); else root.append(bar);
    show(groups.some((t) => t.name === chosen.get(key)) ? chosen.get(key) : groups[0].name);
    return bar;
  }

  function arrangeTool(root, spec, index) {
    if (wired.has(root)) return;
    wired.add(root);
    const scope = root.closest(".cms-tool-header-controls") || root;
    const taken = new Set();
    const groups = spec.tabs.map(([name, selectors]) => {
      const units = [];
      selectors.forEach((selector) => {
        scope.querySelectorAll(selector).forEach((found) => {
          //  A control travels with its label, so the two stay together.
          const label = found.closest(".cms-ui-field") || found.closest("label");
          const unit = label && scope.contains(label) ? label : found;
          if (taken.has(unit) || [...taken].some((t) => t.contains(unit))) return;
          taken.add(unit);
          units.push(unit);
        });
      });
      return units.length ? { name, units } : null;
    }).filter(Boolean);
    if (groups.length < 2) return;
    groups.forEach((tab) => {
      tab.panel = make("div", "cms-ui-tab-panel cms-ui-group");
      tab.panel.append(...tab.units);
      root.append(tab.panel);
    });
    const form = root.closest("form");
    const key = (form ? form.getAttribute("action") : root.closest(".cms-section")?.id || "") + "#" + index;
    tabbed(root, groups, key, groups[0].panel);
  }

  function captions() {
    CAPTIONS.forEach(([selector, text]) => {
      document.querySelectorAll(selector).forEach((select) => {
        if (select.closest("label, .cms-ui-field")) return;
        const field = make("div", "cms-ui-field");
        field.title = select.title;
        select.before(field);
        field.append(make("span", "cms-ui-caption", text), select);
      });
    });
  }

  function sharedRow() {
    document.querySelectorAll(".cms-tool-header-controls").forEach((controls) => {
      const loose = [...controls.querySelectorAll(SHARED)]
        .filter((el) => !el.closest(".cms-ui-shared") && el.closest(".cms-tool-header-controls") === controls);
      if (!loose.length) return;
      let row = controls.querySelector(":scope > .cms-ui-shared");
      if (!row) {
        row = make("div", "cms-ui-shared");
        controls.append(row);
      }
      row.append(...loose);
    });
  }

  // ---------- A select drawn as buttons ----------
  // The select stays in the form and stays the value; the buttons set it.
  function buttonsFor(select, className, faces) {
    if (wired.has(select)) return;
    wired.add(select);
    const host = make("span", className);
    const buttons = [...select.options].map((option) => {
      const button = make("button", "cms-ui-choice", faces ? faces[option.value] : "");
      button.type = "button";
      button.title = option.textContent.trim();
      button.setAttribute("aria-label", option.textContent.trim());
      button.addEventListener("click", (e) => {
        e.preventDefault();
        if (select.value === option.value) return;
        select.value = option.value;
        select.dispatchEvent(new Event("change", { bubbles: true }));
      });
      host.append(button);
      return { button, value: option.value };
    });
    const paint = () => buttons.forEach(({ button, value }) => {
      button.classList.toggle("is-active", select.value === value);
      button.setAttribute("aria-pressed", select.value === value ? "true" : "false");
    });
    select.addEventListener("change", paint);
    select.cmsPaint = paint;
    select.classList.add("cms-ui-replaced");
    //  Outside the <label>, or a click anywhere in it would press the
    //  first button.
    const label = select.closest("label");
    if (label) {
      const field = make("div", "cms-ui-field");
      field.title = label.title || select.title;
      const caption = make("span", "cms-ui-caption", label.childNodes[0]?.textContent.trim() || "");
      label.replaceWith(field);
      field.append(caption, select, host);
    } else {
      select.after(host);
    }
    paint();
  }

  function arrange() {
    captions();
    TOOLS.forEach((spec, index) => {
      document.querySelectorAll(spec.root).forEach((root) => arrangeTool(root, spec, index));
    });
    document.querySelectorAll(".cms-banner-config-form").forEach((form) => {
      tabsFor(form);
      form.querySelectorAll('select[name="position"]').forEach(
        (s) => buttonsFor(s, "cms-ui-position"));
      form.querySelectorAll('select[name="text_align"]').forEach(
        (s) => buttonsFor(s, "cms-ui-segment", { left: "Left", center: "Centre", right: "Right" }));
    });
    //  Last, so that this row lands under whatever tabs were just built.
    sharedRow();
  }

  // ---------- Room for a toolbar over a narrow tool ----------
  //  A section or column can be as narrow as the owner likes; its open
  //  toolbar cannot, or the controls spill out of it. So the toolbar alone
  //  is widened, kept on screen and clear of the side rail.
  const ROOM = 360;
  const OPEN = [".cms-section.cms-tool-panel-open > .cms-tool-panel > .cms-tool-header",
                ".cms-tool-header.cms-tool-header-open",
                ".cms-active-tool-header-slot .cms-tool-header"].join(",");

  function makeRoom() {
    document.querySelectorAll(".cms-tool-header.cms-ui-widened").forEach((header) => {
      header.classList.remove("cms-ui-widened");
      header.style.width = header.style.left = "";
    });
    const open = [...document.querySelectorAll(OPEN)];
    if (!open.length) return;
    let edge = document.documentElement.clientWidth;
    document.querySelectorAll(".cms-dock-tab-btn:not(.cms-dock-bottom)").forEach((tab) => {
      const box = tab.getBoundingClientRect();
      if (box.width && box.left > edge / 2) edge = Math.min(edge, box.left);
    });
    open.forEach((header) => {
      const space = header.parentElement.getBoundingClientRect();
      const width = Math.min(ROOM, edge - 16);
      if (!space.width || space.width >= width) return;
      header.classList.add("cms-ui-widened");
      header.style.width = width + "px";
      const now = header.getBoundingClientRect().left;
      const centred = space.left + (space.width - width) / 2;
      const left = Math.max(8, Math.min(centred, edge - width - 8));
      header.style.left = (left - now) + "px";
    });
  }

  let roomQueued = false;
  const queueRoom = () => {
    if (roomQueued) return;
    roomQueued = true;
    requestAnimationFrame(() => {
      roomQueued = false;
      watcher.disconnect();
      makeRoom();
      watch();
    });
  };
  //  Toolbars open by gaining a class, or by being moved into a columns
  //  section's shared slot. Not watched while this is the one changing them.
  const watcher = new MutationObserver((changes) => {
    if (changes.some((c) => c.type === "childList"
        || /cms-tool-(panel|header)-open/.test((c.oldValue || "") + " " + c.target.className))) queueRoom();
  });
  const watch = () => watcher.observe(document.body, {
    subtree: true, childList: true, attributes: true,
    attributeFilter: ["class"], attributeOldValue: true,
  });
  watch();
  window.addEventListener("resize", queueRoom);

  //  After shared styles are copied in, the drawn buttons are redrawn.
  document.addEventListener("cms:controls-synced", () => {
    document.querySelectorAll("select.cms-ui-replaced").forEach((s) => s.cmsPaint && s.cmsPaint());
  });
  document.addEventListener("cms:site-refreshed", arrange);
  document.documentElement.classList.add("cms-ui-modern");
  arrange();
})();
