// Theme/Layout/Template-content controls — shared between the live-page
// "Theme & Layout" dock panel (partials/template_panel.html) and the
// Dashboard's own Templates/Layout sections (admin/dashboard.html). Both
// templates render the same ids/classes/data-* attributes below (never at
// the same time — one is the docked panel on the live site, the other is
// the standalone Dashboard page), so this one file drives whichever is
// actually present; every lookup is null-checked for exactly that reason.
(function () {
  document.addEventListener("DOMContentLoaded", init);
  if (document.readyState !== "loading") init();
  //  Applying anything from this panel re-renders the panel itself from
  //  the server rather than reloading the page (see admin/live-refresh.js),
  //  so init() runs again over markup that has only just arrived.
  document.addEventListener("cms:dock-refreshed", init);

  //  Which is only safe if nothing gets wired twice: an element that
  //  survived the swap must keep the one listener it already has, or a
  //  single click would fire two requests.
  const wired = new WeakSet();
  function each(list, bind) {
    list.forEach((el) => {
      if (wired.has(el)) return;
      wired.add(el);
      bind(el);
    });
  }

  function init() {
    const themeGrid = document.getElementById("cms-tpl-theme-grid");
    const structureGrid = document.getElementById("cms-tpl-structure-grid");
    const sidebarGrid = document.getElementById("cms-tpl-sidebar-grid");
    const footerGrid = document.getElementById("cms-tpl-footer-grid");
    if (!themeGrid && !structureGrid) return;

    // Read off <body data-save-template-url> (see admin/base.html and
    // public/page.html) rather than the "Save as New Template" form's own
    // button, which isn't even rendered in the same place on every page
    // these destructive confirms can happen from. Posting with no `name`
    // auto-names the save (see template_save_current) — the modal's own
    // "Save the current setup as a new template first" checkbox (see
    // modal.js) is the one way back if this turns out to lose something
    // worth keeping; the admin can rename/reactivate it afterward from
    // the Dashboard's Templates list.
    const saveTemplateUrl = document.body.dataset.saveTemplateUrl;

    //  Everything in this panel changes the whole site, so everything in
    //  it needs the page re-rendered afterwards. Not reloaded: the dock is
    //  the admin's own workspace, and closing the panel/popover they had
    //  open is their decision, not a side effect of picking a colour. The
    //  one argument is where the server says they should end up — after
    //  activating a template that does not have the page they were
    //  looking at, that is somewhere else, and a real navigation.
    function refresh(go) {
      const url = go && go !== location.pathname ? go : null;
      if (window.cmsRefreshSite) return window.cmsRefreshSite(url ? { url } : {});
      if (url) location.href = url;
      else location.reload();
      return Promise.resolve(false);
    }

    async function maybeSaveTemplate(shouldSave) {
      if (!shouldSave || !saveTemplateUrl) return;
      try {
        await fetch(saveTemplateUrl, { method: "POST", headers: { "X-Inline-Edit": "1" } });
      } catch {
        // Best-effort — the main action still proceeds even if the save failed.
      }
    }

    async function apply(btn, url, body) {
      if (btn.disabled) return;
      const grid = btn.parentElement;
      grid.querySelectorAll("button").forEach((b) => (b.disabled = true));
      const original = btn.style.opacity;
      btn.style.opacity = "0.6";
      try {
        //  Where the admin currently is, so the server can say whether
        //  that page still exists once it has finished.
        const withFrom = (body ? body + "&" : "") +
          "from=" + encodeURIComponent(location.pathname);
        const res = await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/x-www-form-urlencoded",
                     "X-Inline-Edit": "1" },
          body: withFrom,
        });
        //  Reloading blindly is what put people on a "page not found"
        //  after activating a template that does not have the page they
        //  were looking at.
        let go = null;
        try { go = (await res.json()).go; } catch {}
        await refresh(go);
      } catch {
        // fall through to the same tidy-up as a successful apply
      } finally {
        //  Usually these very buttons have just been replaced by the
        //  panel's freshly-rendered ones, so this does nothing; it
        //  matters when they have not been — a request that failed, or a
        //  refresh that could not run — where leaving the grid disabled
        //  would strand the panel.
        grid.querySelectorAll("button").forEach((b) => (b.disabled = false));
        btn.style.opacity = original;
      }
    }

    // Activate — loads the template's look AND its content (if it has
    // any) in one step. Every template row/swatch on both surfaces
    // (Dashboard's table, the dock panel's swatch grid) renders
    // data-activate-url + data-conflict="true"/"false" (see
    // routes/admin/dashboard.py's activate_conflict_map). Only a
    // template whose default layout or content would replace something
    // already there needs to ask first — every other activation applies
    // immediately, same as before.
    each(document.querySelectorAll("[data-activate-url]"), (btn) => {
      btn.addEventListener("click", async () => {
        if (btn.dataset.conflict === "true") {
          //  Three answers, because there are three things somebody might
          //  mean by "use this template". Cancel used to be the only
          //  alternative to replacing everything, which hid the most
          //  common want of all: a new look on the writing you already
          //  have. The server has always supported it — activating
          //  without force applies the look and leaves the pages alone —
          //  but nothing in the interface asked for it.
          const { confirmed, alt, saveSnapshot } = await window.cmsModal({
            message: "Use this template? It comes with its own pages and layout. "
              + "Take the look only and your own pages, wording and pictures stay exactly as they are. "
              + "Take everything and its pages replace yours where they share a name.",
            confirmLabel: "Take everything",
            altLabel: "Just the look",
            danger: true, showSnapshotOption: true,
          });
          if (!confirmed && !alt) return;
          await maybeSaveTemplate(saveSnapshot);
          //  "Just the look" is the un-forced activation: the theme, the
          //  palette and the fonts land, and _apply_pack_content is
          //  skipped because it would replace something.
          apply(btn, btn.dataset.activateUrl, confirmed ? "force=1" : "");
          return;
        }
        apply(btn, btn.dataset.activateUrl);
      });
    });

    // Delete — the small × badge on each non-active swatch (see
    // template_panel.html; the Dashboard's own Templates table has its
    // own plain delete form instead, so this only exists here).
    each(document.querySelectorAll(".cms-tpl-delete-btn"), (btn) => {
      btn.addEventListener("click", async (e) => {
        e.stopPropagation();
        const { confirmed } = await window.cmsModal({
          message: 'Delete "' + btn.dataset.name + '"? This cannot be undone.',
          confirmLabel: "Delete", danger: true,
        });
        if (!confirmed) return;
        btn.disabled = true;
        try {
          const res = await fetch(btn.dataset.deleteUrl, { method: "POST", headers: { "X-Inline-Edit": "1" } });
          if (!res.ok) throw new Error("Request failed");
          await refresh();
        } catch {
          btn.disabled = false;
          alert("Couldn't delete that template — please try again.");
        }
      });
    });

    if (structureGrid) {
      const hasSidebarContent = structureGrid.dataset.hasSidebarContent === "true";
      each(structureGrid.querySelectorAll(".nav-layout-option"), (btn) => {
        btn.addEventListener("click", async () => {
          // Header layouts and sidebar presets are one unified "Layout"
          // choice — picking a header-only layout (no sidebars) should
          // genuinely take over, same as a sidebar preset does, instead of
          // leaving old sidebar content silently still rendering. Only
          // asks when there's actually a sidebar section to lose.
          let body = "nav_layout=" + encodeURIComponent(btn.dataset.navLayout);
          if (hasSidebarContent) {
            const { confirmed, saveSnapshot } = await window.cmsModal({
              message: "Switch to this layout? It has no sidebars, so this removes the current sidebar section(s) too.",
              confirmLabel: "Switch", danger: false, showSnapshotOption: true,
            });
            if (!confirmed) return;
            await maybeSaveTemplate(saveSnapshot);
            body += "&clear_sidebars=1";
          }
          apply(btn, btn.dataset.navUrl, body);
        });
      });
    }

    if (sidebarGrid) {
      // Unlike theme/header-layout (always safe, non-destructive), a
      // sidebar preset can land on a rail that already has a section —
      // silently skipping it (the old behavior) meant clicking a preset
      // sometimes just... did nothing, with no explanation. Ask first,
      // then force-replace on confirm, so it's an explicit choice instead
      // of either a silent no-op or a silent overwrite.
      each(sidebarGrid.querySelectorAll(".nav-layout-option"), (btn) => {
        btn.addEventListener("click", async () => {
          const label = btn.querySelector(".nav-layout-option-label")?.textContent || "this layout";
          const { confirmed, saveSnapshot } = await window.cmsModal({
            message: 'Apply "' + label + '"? If a sidebar already has a section, this replaces it — the new one starts empty except for a fresh page menu.',
            confirmLabel: "Apply", danger: false, showSnapshotOption: true,
          });
          if (!confirmed) return;
          await maybeSaveTemplate(saveSnapshot);
          apply(btn, btn.dataset.sidebarUrl, "preset=" + encodeURIComponent(btn.dataset.preset) + "&force=1");
        });
      });
    }

    if (footerGrid) {
      each(footerGrid.querySelectorAll(".nav-layout-option"), (btn) => {
        btn.addEventListener("click", async () => {
          const label = btn.querySelector(".nav-layout-option-label")?.textContent || "this layout";
          const { confirmed, saveSnapshot } = await window.cmsModal({
            message: 'Apply "' + label + '"? If the footer already has section(s), this replaces them.',
            confirmLabel: "Apply", danger: false, showSnapshotOption: true,
          });
          if (!confirmed) return;
          await maybeSaveTemplate(saveSnapshot);
          apply(btn, btn.dataset.footerUrl, "preset=" + encodeURIComponent(btn.dataset.preset) + "&force=1");
        });
      });
    }

    // Load Content — all-or-nothing, no per-page picker (a template has
    // its base data; you load all of it or none), available on ANY
    // installed template that ships content, not just a curated "demo
    // pack", and independent of Activate (which already loads it once on
    // first activation).
    each(document.querySelectorAll(".cms-load-content-btn"), (btn) => {
      btn.addEventListener("click", async () => {
        const { confirmed, saveSnapshot } = await window.cmsModal({
          message: "Load this template's content? This replaces any of its pages' current content on your site — other pages are untouched.",
          confirmLabel: "Load", danger: true, showSnapshotOption: true,
        });
        if (!confirmed) return;
        await maybeSaveTemplate(saveSnapshot);
        btn.disabled = true;
        try {
          const res = await fetch(btn.dataset.url, { method: "POST", headers: { "X-Inline-Edit": "1" } });
          if (!res.ok) throw new Error("Request failed");
          await refresh();
        } catch {
          btn.disabled = false;
          alert("Couldn't load that content — please try again.");
        }
      });
    });
  }
})();
