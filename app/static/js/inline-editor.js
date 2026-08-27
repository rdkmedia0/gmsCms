(function () {
  "use strict";

  // ---------- Preserve scroll position across edit actions ----------
  // Almost every editing action here (a form save, a select's onchange that
  // reloads, a redirect back with an anchor) does a full page navigation,
  // which resets scroll to the top by default — "jumping around" away from
  // whatever the admin was just editing. Save scroll position right before
  // any navigation away, and restore it on load if we land back on the same
  // path, so edits keep the view where the admin was working.
  window.addEventListener("beforeunload", () => {
    try {
      sessionStorage.setItem("cmsScrollPos", JSON.stringify({ path: location.pathname, y: window.scrollY }));
    } catch {}
  });
  (function restoreScroll() {
    let saved = null;
    try { saved = JSON.parse(sessionStorage.getItem("cmsScrollPos") || "null"); } catch {}
    if (saved && saved.path === location.pathname && !location.hash) {
      window.scrollTo(0, saved.y);
    }
    sessionStorage.removeItem("cmsScrollPos");
  })();

  // ---------- Re-runnable element bindings ----------
  // Everything below that wires a handler onto each of a set of elements
  // goes through bindEach rather than querySelectorAll(...).forEach(...),
  // so the same wiring can be applied again to markup that arrived after
  // load. Applying a template no longer reloads the page — it swaps the
  // site's own regions in place (see admin/live-refresh.js) — and the
  // replacement markup has to be wired up exactly as the original was.
  //
  // Each registration remembers which elements it has already bound, so
  // running them again only ever touches new ones. The document-level
  // (delegated) listeners in this file are deliberately NOT part of this:
  // they survive a swap untouched, and re-binding them would fire every
  // action twice.
  const cmsBindings = [];
  function bindEach(selector, bind) {
    const bound = new WeakSet();
    function run() {
      document.querySelectorAll(selector).forEach((el) => {
        if (bound.has(el)) return;
        bound.add(el);
        bind(el);
      });
    }
    cmsBindings.push(run);
    run();
  }
  //  Same thing for the one-of-a-kind controls in the dock's own panels:
  //  Colours and Fonts are a view of whichever template is active, so
  //  they too are re-rendered when one is applied.
  function bindById(id, type, handler) {
    bindEach("#" + id, (el) => el.addEventListener(type, handler));
  }

  // ---------- Toast ----------
  const toastEl = document.getElementById("cms-toast");
  let toastTimer = null;
  function toast(message) {
    if (!toastEl) return;
    toastEl.textContent = message;
    toastEl.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { toastEl.hidden = true; }, 1800);
  }

  // ---------- Modal (replaces native confirm()/prompt()) ----------
  // Implementation lives in static/js/admin/modal.js (loaded before this
  // file — see page.html) and exposes itself as window.cmsModal; every
  // `cmsModal(...)` call below resolves to that global.
  const cmsModal = window.cmsModal;

  // ---------- Undo (Ctrl/Cmd+Z) ----------
  // Server-side, not a client-side history stack — every mutating action
  // that can lose real work (reorder, a tool dropped onto a section that
  // overwrites it, delete/clear/divide) already snapshotted the affected
  // page/zone's sections right before it ran (see _undo_snapshot in
  // admin.py); this just pops the newest one. Ignored while typing in a
  // text field/contenteditable — Ctrl+Z there means the browser's own
  // native text-undo, which must keep working untouched.
  document.addEventListener("keydown", function (e) {
    if (!((e.ctrlKey || e.metaKey) && !e.shiftKey && e.key.toLowerCase() === "z")) return;
    const active = document.activeElement;
    if (active && (active.isContentEditable || active.tagName === "TEXTAREA" || active.tagName === "INPUT")) return;
    e.preventDefault();
    fetch("/admin/undo", { method: "POST", headers: { "X-Inline-Edit": "1" } })
      .then((r) => r.json())
      .then((data) => {
        if (data.ok) {
          if (data.next_url) location.href = data.next_url;
          else location.reload();
        } else {
          toast(data.error || "Nothing to undo.");
        }
      })
      .catch(() => toast("Couldn't undo — please try again."));
  });

  // ---------- Image picker (choose 1 of several freshly-generated images) ----------
  const pickerBackdrop = document.getElementById("cms-image-picker-backdrop");
  const pickerGrid = document.getElementById("cms-image-picker-grid");
  const pickerCancel = document.getElementById("cms-image-picker-cancel");

  function cmsImagePicker(images) {
    return new Promise((resolve) => {
      pickerGrid.innerHTML = "";
      images.forEach((img) => {
        const b = document.createElement("button");
        b.type = "button";
        const thumb = document.createElement("img");
        thumb.src = img.url;
        b.appendChild(thumb);
        b.addEventListener("click", () => cleanup(img.url));
        pickerGrid.appendChild(b);
      });
      pickerBackdrop.hidden = false;
      function cleanup(url) {
        pickerBackdrop.hidden = true;
        pickerCancel.removeEventListener("click", onCancel);
        pickerBackdrop.removeEventListener("click", onBackdrop);
        resolve(url);
      }
      function onCancel() { cleanup(null); }
      function onBackdrop(e) { if (e.target === pickerBackdrop) onCancel(); }
      pickerCancel.addEventListener("click", onCancel);
      pickerBackdrop.addEventListener("click", onBackdrop);
    });
  }

  // ---------- Destructive form confirmation (sections) ----------
  bindEach(".cms-delete-form", (form) => {
    form.addEventListener("submit", async (e) => {
      if (form.dataset.confirmed === "1") return; // already confirmed, let it submit
      e.preventDefault();
      const { confirmed } = await cmsModal({ message: form.dataset.confirm || "Are you sure?" });
      if (confirmed) {
        form.dataset.confirmed = "1";
        form.submit();
      }
    });
  });

  // Pages are added/removed from the Dashboard only now — no nav add/delete
  // controls on the live page itself.

  // ---------- Menu tool ----------
  // The "Items" popover is selection only: check a page to add it, uncheck
  // to remove it, type an optional icon, add a custom link (url+label+
  // icon) or a divider. Everything else — order, Dropdown-style nesting,
  // and removing a custom link/divider — happens by directly manipulating
  // the menu's own live rendered links: drag to reorder, drop onto another
  // item to nest under it, drop in empty space to un-nest, click the small
  // × on a live item to remove it. One array (`items`) backs both the
  // popover and the live links, kept in sync with a hidden JSON field so a
  // single submit always carries the full state.
  bindEach(".cms-menu-builder", (builder) => {
    const form = builder.closest("form");
    const input = builder.querySelector(".cms-menu-items-input");
    const styleSelect = builder.querySelector(".cms-menu-style-select");
    const pagesBtn = builder.querySelector(".cms-menu-pages-btn");
    const pagesDropdown = builder.querySelector(".cms-menu-pages-dropdown");
    const addEl = builder.querySelector(".cms-menu-pages-add");
    let items;
    try { items = JSON.parse(builder.dataset.items || "[]"); } catch { items = []; }

    function isDropdown() { return styleSelect.value === "dropdown"; }
    function randomKey(prefix) { return prefix + Math.random().toString(36).slice(2, 9); }

    // A pending custom link isn't in `items` yet (only "+ Link" adds it), so
    // its icon choice needs its own slot until then.
    let pendingCustomIcon = "";

    function iconPreviewFor(key) {
      if (!key) return "";
      const gridBtn = builder.querySelector('.cms-icon-grid-btn[data-icon-key="' + CSS.escape(key) + '"]');
      return gridBtn ? gridBtn.innerHTML : "";
    }

    function render() {
      input.value = JSON.stringify(items);
      pagesBtn.textContent = "Items (" + items.length + ") ▾";
      const byId = new Map(items.filter((it) => it.type === "page").map((it) => [it.id, it]));

      addEl.querySelectorAll(".cms-menu-page-toggle").forEach((cb) => {
        const it = byId.get(Number(cb.value));
        cb.checked = !!it;
        const pickBtn = cb.closest(".cms-menu-page-check").querySelector(".cms-menu-icon-pick");
        if (pickBtn) {
          pickBtn.hidden = !it;
          if (it) pickBtn.querySelector(".cms-icon-pick-preview").innerHTML = iconPreviewFor(it.icon);
        }
      });
    }

    function commit() {
      render();
      if (!pagesDropdown.hidden) sessionStorage.setItem(openKey, "1");
      // Marks this particular submit as one that genuinely needs the full
      // reload (new page just created, needs its own checkbox row; a page
      // renamed/deleted elsewhere on the page) — the generic submit
      // listener below intercepts every other submit from this form
      // (style/size/align/direction/colors/... all still just call
      // this.form.requestSubmit() inline) and saves those in place instead.
      form.dataset.forceReload = "1";
      form.requestSubmit();
    }

    // Checking a page on/off is the single most common edit made here, and
    // it's the one that least needs a full page reload — the section
    // itself doesn't move or change shape, only its own link list does.
    // Save it in place instead: POST the form as usual but ask for JSON
    // (menu-update/columns-menu-update both support this — see
    // wants_json() in admin.py) and splice the returned HTML straight into
    // the live <nav> this same builder configures, with no navigation at
    // all — so the picker stays open and the page doesn't jump/scroll
    // (previously every toggle reloaded the whole page, which for a
    // full-height zone like the sidebar always landed back near the top).
    // Falls back to the old full-reload commit() if anything about that
    // goes wrong, or if this builder's live preview element can't be
    // found (e.g. a menu nested in a Columns cell isn't wired for this).
    function livePreviewEl() {
      const section = builder.closest(".cms-section");
      // Not a direct child — the live nav sits inside .block-html, one
      // level below .cms-section (a sibling of .cms-tool-panel, which is
      // where this builder itself lives), so a plain descendant lookup is
      // needed. .cms-tool-panel never contains a .cms-html-preview of its
      // own, so this can't accidentally match the wrong one.
      return section ? section.querySelector(".cms-html-preview") : null;
    }
    async function commitInPlace() {
      render();
      const preview = livePreviewEl();
      if (!preview) { commit(); return; }
      try {
        const res = await fetch(form.action, {
          method: "POST",
          body: new FormData(form),
          headers: { "X-Inline-Edit": "1" },
        });
        const data = await res.json();
        if (res.ok && data.ok && typeof data.content === "string") {
          preview.innerHTML = data.content;
          return;
        }
      } catch {}
      commit(); // AJAX path failed — fall back to the reliable full reload
    }

    // Every other field in this config bar (Style/Size/Font/Align/
    // Direction/Highlight/colors/Button style/Submenu style) is still a
    // plain `<select onchange="this.form.requestSubmit()">` in the
    // template — none of those need touching individually. Instead,
    // intercept the form's own submit event generically: a real reload is
    // only actually needed when commit() marks one (forceReload — new
    // page created, needs a fresh checkbox row), so every other submit
    // saves in place instead, the same way the page checkboxes already
    // do. This is what fixes "changing Align repositions/scrolls the
    // page" — every field here was doing a full navigation for what's
    // just a style tweak.
    form.addEventListener("submit", (e) => {
      if (form.dataset.forceReload === "1") {
        delete form.dataset.forceReload;
        return; // let this one through as a real navigation
      }
      e.preventDefault();
      commitInPlace();
    });

    addEl.querySelectorAll(".cms-menu-page-toggle").forEach((cb) => {
      cb.addEventListener("change", () => {
        const id = Number(cb.value);
        const key = "p" + id;
        if (cb.checked) {
          items.push({ key, type: "page", id, icon: "", parent: null });
        } else {
          items = items.filter((it) => it.key !== key);
          items.forEach((it) => { if (it.parent === key) it.parent = null; });
        }
        commitInPlace();
      });
    });

    const newPageTitle = builder.querySelector(".cms-menu-newpage-title");
    const newPageType = builder.querySelector(".cms-menu-newpage-type");
    const newPageBtn = builder.querySelector(".cms-menu-newpage-btn");
    newPageBtn?.addEventListener("click", async () => {
      const title = newPageTitle.value.trim();
      if (!title) { newPageTitle.focus(); return; }
      newPageBtn.disabled = true;
      const original = newPageBtn.textContent;
      newPageBtn.textContent = "Creating…";
      try {
        const formData = new URLSearchParams();
        formData.set("title", title);
        formData.set("page_type", newPageType ? newPageType.value : "standard");
        const res = await fetch(newPageBtn.dataset.createUrl, {
          method: "POST",
          headers: { "Content-Type": "application/x-www-form-urlencoded", "X-Inline-Edit": "1" },
          body: formData,
        });
        const data = await res.json();
        if (res.ok && data.ok) {
          items.push({ key: "p" + data.id, type: "page", id: data.id, icon: "", parent: null });
          newPageTitle.value = "";
          sessionStorage.setItem(openKey, "1");
          commit(); // full reload — the new page then shows up as a real checkbox too
        } else {
          toast(data.error || "Couldn't create the page");
          newPageBtn.disabled = false;
          newPageBtn.textContent = original;
        }
      } catch {
        toast("Couldn't create the page — check your connection");
        newPageBtn.disabled = false;
        newPageBtn.textContent = original;
      }
    });

    builder.querySelectorAll(".cms-menu-page-rename").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const row = btn.closest(".cms-menu-page-check");
        const titleEl = row.querySelector(".cms-menu-page-title");
        const { confirmed, value } = await cmsModal({
          message: "Rename this page:",
          showInput: true,
          defaultValue: titleEl.textContent.trim(),
          confirmLabel: "Rename",
          danger: false,
        });
        if (!confirmed || !value || !value.trim()) return;
        try {
          const formData = new URLSearchParams();
          formData.set("title", value.trim());
          const res = await fetch(btn.dataset.renameUrl, {
            method: "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded", "X-Inline-Edit": "1" },
            body: formData,
          });
          const data = await res.json();
          if (res.ok && data.ok) {
            titleEl.textContent = data.title;
            const cb = row.querySelector(".cms-menu-page-toggle");
            if (cb) cb.dataset.title = data.title;
            const pickBtn = row.querySelector(".cms-menu-icon-pick");
            if (pickBtn) pickBtn.dataset.targetLabel = data.title;
            const deleteBtn = row.querySelector(".cms-menu-page-delete");
            if (deleteBtn) deleteBtn.dataset.pageTitle = data.title;
            toast("Page renamed");
          } else {
            toast(data.error || "Couldn't rename the page");
          }
        } catch {
          toast("Couldn't rename the page — check your connection");
        }
      });
    });

    builder.querySelectorAll(".cms-menu-page-delete").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const pageId = Number(btn.dataset.pageId);
        const { confirmed } = await cmsModal({
          message: 'Delete "' + btn.dataset.pageTitle + '"? This cannot be undone, and removes it from every menu that links to it.',
          confirmLabel: "Delete",
          danger: true,
        });
        if (!confirmed) return;
        try {
          const res = await fetch(btn.dataset.deleteUrl, {
            method: "POST",
            headers: { "X-Inline-Edit": "1" },
          });
          const data = await res.json();
          if (res.ok && data.ok) {
            btn.closest(".cms-menu-page-check").remove();
            items = items.filter((it) => !(it.type === "page" && it.id === pageId));
            sessionStorage.setItem(openKey, "1");
            commit();
          } else {
            toast(data.error || "Couldn't delete the page");
          }
        } catch {
          toast("Couldn't delete the page — check your connection");
        }
      });
    });

    const customLabel = builder.querySelector(".cms-menu-custom-label");
    const customUrl = builder.querySelector(".cms-menu-custom-url");
    const customIconPick = builder.querySelector(".cms-menu-custom-icon-pick");
    const customAddBtn = builder.querySelector(".cms-menu-custom-add-btn");
    customAddBtn?.addEventListener("click", () => {
      const url = customUrl.value.trim();
      if (!url) { customUrl.focus(); return; }
      items.push({
        key: randomKey("c"), type: "custom", url,
        label: customLabel.value.trim() || url,
        icon: pendingCustomIcon, parent: null,
      });
      customLabel.value = ""; customUrl.value = ""; pendingCustomIcon = "";
      if (customIconPick) customIconPick.querySelector(".cms-icon-pick-preview").innerHTML = "";
      sessionStorage.setItem(openKey, "1");
      commit();
    });

    // ---------- Icon grid: a real visual list, never a typed code ----------
    // A plain dropdown, shared by every "choose icon" trigger in this
    // popover — opens right below whichever button was clicked (like a
    // native <select>), scrolls if it doesn't fit, and closes on picking
    // an icon or clicking away. Never replaces/hides the rest of the
    // popover the way an in-place "mode switch" would.
    const gridView = builder.querySelector(".cms-icon-grid-view");
    const pickerRoot = builder.querySelector(".cms-menu-pages-picker");
    let iconPickTarget = null; // a `items` key, or "custom" for the not-yet-added draft

    function openIconGrid(triggerBtn, target) {
      iconPickTarget = target;
      if (!gridView || !pickerRoot) return;
      // Position relative to the picker root (gridView's offsetParent),
      // using real rendered rects rather than offsetTop chains — the
      // trigger sits inside the pages-dropdown, which is itself
      // absolutely positioned with a calc() offset, so a bounding-rect
      // difference is simpler and correct regardless of that layering.
      const btnRect = triggerBtn.getBoundingClientRect();
      const rootRect = pickerRoot.getBoundingClientRect();
      gridView.style.top = (btnRect.bottom - rootRect.top + 2) + "px";
      gridView.style.left = "0px";
      gridView.hidden = false;
      keepOnScreen(gridView);
      sessionStorage.setItem(openKey, "1");
    }
    function closeIconGrid() {
      iconPickTarget = null;
      if (gridView) gridView.hidden = true;
    }

    builder.querySelectorAll(".cms-menu-icon-pick").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const isCustom = btn.classList.contains("cms-menu-custom-icon-pick");
        const opening = gridView.hidden || iconPickTarget !== (isCustom ? "custom" : "p" + btn.dataset.pageId);
        if (!opening) { closeIconGrid(); return; }
        openIconGrid(btn, isCustom ? "custom" : "p" + btn.dataset.pageId);
      });
    });
    document.addEventListener("click", (e) => {
      if (gridView && !gridView.hidden && !e.target.closest(".cms-icon-grid-view, .cms-menu-icon-pick")) {
        closeIconGrid();
      }
    });

    builder.querySelectorAll(".cms-icon-grid-btn").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const key = btn.dataset.iconKey || "";
        if (iconPickTarget === "custom") {
          pendingCustomIcon = key;
          if (customIconPick) customIconPick.querySelector(".cms-icon-pick-preview").innerHTML = iconPreviewFor(key);
          closeIconGrid();
        } else if (iconPickTarget) {
          const it = items.find((x) => x.key === iconPickTarget);
          closeIconGrid();
          if (it) { it.icon = key; commit(); }
        }
      });
    });

    const dividerAddBtn = builder.querySelector(".cms-menu-divider-add-btn");
    dividerAddBtn?.addEventListener("click", () => {
      items.push({ key: randomKey("d"), type: "divider", parent: null });
      sessionStorage.setItem(openKey, "1");
      commit();
    });

    // The popover itself — a compact "Items ▾" button instead of an
    // always-open block, so the panel stays out of the way until needed.
    // Every change inside it does a full-page reload (same as every other
    // tool-panel field in this app), which would otherwise close the
    // popover right after checking one page — remember it was open across
    // that reload the same way the tool panel itself remembers via the
    // #section-<id> hash.
    const panelId = builder.closest(".cms-tool-panel")?.id || "";
    const openKey = "cms-menu-popover-open:" + panelId;
    //  A floating panel that opens past the edge of the window shows
    //  half of itself and no way to reach the rest. This slides it back
    //  until it fits -- which matters on a wide screen too, since the
    //  panel can be as narrow as the column the tool is standing in.
    //  On a phone the stylesheet makes these flow inline instead, and a
    //  static element ignores `left`, so this quietly does nothing there.
    function keepOnScreen(el) {
      el.style.left = "0px";
      const room = window.innerWidth - 8;
      const past = el.getBoundingClientRect().right - room;
      if (past > 0) el.style.left = -past + "px";
      const short = 8 - el.getBoundingClientRect().left;
      if (short > 0) el.style.left = (parseFloat(el.style.left || 0) + short) + "px";
    }
    function openPopover() { pagesDropdown.hidden = false; keepOnScreen(pagesDropdown); }
    function closePopover() {
      pagesDropdown.hidden = true;
      sessionStorage.removeItem(openKey);
    }
    pagesBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      if (pagesDropdown.hidden) { openPopover(); sessionStorage.setItem(openKey, "1"); }
      else closePopover();
    });
    document.addEventListener("click", (e) => {
      if (!pagesDropdown.hidden && !e.target.closest(".cms-menu-pages-picker")) {
        closePopover();
      }
    });
    if (panelId && sessionStorage.getItem(openKey) === "1") openPopover();
    render();

    // ---------- Manage the live rendered links directly ----------
    // Drag to reorder; drop onto the middle of another item (Dropdown
    // style only) to nest under it; drop in empty space in the menu bar to
    // un-nest (moves to the end, top level); click a live item's × to
    // remove it outright — dividers and custom links have no popover row
    // of their own, so this is their only removal path.
    const menuScope = builder.closest(".cms-column, .cms-row-cell, .cms-section");
    const liveNav = menuScope ? menuScope.querySelector("nav.cms-menu[data-menu-items]") : null;
    if (liveNav) {
      liveNav.querySelectorAll("[data-menu-key]").forEach((el) => {
        el.draggable = true;
        if (el.querySelector(":scope > .cms-menu-remove")) return;
        const removeBtn = document.createElement("button");
        removeBtn.type = "button";
        removeBtn.className = "cms-menu-remove";
        removeBtn.title = "Remove from menu";
        removeBtn.textContent = "×";
        removeBtn.addEventListener("click", (e) => {
          e.preventDefault();
          e.stopPropagation();
          const key = el.dataset.menuKey;
          items = items.filter((it) => it.key !== key);
          items.forEach((it) => { if (it.parent === key) it.parent = null; });
          commit();
        });
        el.prepend(removeBtn);
      });

      let dragKey = null;
      function clearNestTarget() {
        liveNav.querySelectorAll(".cms-menu-nest-target").forEach((el) => el.classList.remove("cms-menu-nest-target"));
      }
      liveNav.addEventListener("dragstart", (e) => {
        const el = e.target.closest("[data-menu-key]");
        if (!el) return;
        dragKey = el.dataset.menuKey;
        e.dataTransfer.effectAllowed = "move";
      });
      liveNav.addEventListener("dragover", (e) => {
        if (dragKey === null) return;
        e.preventDefault();
        if (!isDropdown()) return;
        const target = e.target.closest("[data-menu-key]");
        clearNestTarget();
        if (target && target.dataset.menuKey !== dragKey) {
          const rect = target.getBoundingClientRect();
          const frac = (e.clientX - rect.left) / rect.width;
          if (frac > 0.3 && frac < 0.7) target.classList.add("cms-menu-nest-target");
        }
      });
      liveNav.addEventListener("dragleave", (e) => {
        if (!liveNav.contains(e.relatedTarget)) clearNestTarget();
      });
      liveNav.addEventListener("drop", (e) => {
        if (dragKey === null) return;
        e.preventDefault();
        clearNestTarget();
        const dragItem = items.find((it) => it.key === dragKey);
        const key = dragKey;
        dragKey = null;
        if (!dragItem) return;

        const target = e.target.closest("[data-menu-key]");
        if (!target) {
          // Empty space in the menu bar — un-nest, move to the end.
          dragItem.parent = null;
          items = items.filter((it) => it.key !== key);
          items.push(dragItem);
          commit();
          return;
        }
        const targetKey = target.dataset.menuKey;
        if (targetKey === key) return;
        const targetItem = items.find((it) => it.key === targetKey);

        if (isDropdown() && targetItem && targetItem.type !== "divider" && dragItem.type !== "divider") {
          const rect = target.getBoundingClientRect();
          const frac = (e.clientX - rect.left) / rect.width;
          if (frac > 0.3 && frac < 0.7) {
            dragItem.parent = targetKey;
            commit();
            return;
          }
        }
        // Ordinary reorder — move right before the target.
        items = items.filter((it) => it.key !== key);
        const toIndex = items.findIndex((it) => it.key === targetKey);
        items.splice(toIndex === -1 ? items.length : toIndex, 0, dragItem);
        commit();
      });
    }
  });

  // "+ Add Section" is now a plain submit button (no dropdown menu) —
  // it just adds a blank frame; division/tools happen after, from the
  // section's own toolbar.

  // ---------- Autosave helper ----------
  function debounce(fn, wait) {
    let t;
    return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), wait); };
  }

  async function saveField(url, field, value) {
    if (!url) return;
    const body = new URLSearchParams();
    body.set(field, value);
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded", "X-Inline-Edit": "1" },
        body,
      });
      if (res.ok) toast("Saved");
      else toast("Couldn't save — please try again");
    } catch {
      toast("Couldn't save — check your connection");
    }
  }

  const debouncedSave = debounce(saveField, 500);

  // Elements with data-save-url autosave themselves on blur/typing — used
  // both for page section fields (title/content/width) and template
  // header/footer chunk content.
  bindEach("[data-save-url][data-field]", (el) => {
    if (el.tagName === "TEXTAREA") return; // handled by the HTML editor's own Save button
    const url = el.dataset.saveUrl;
    const field = el.dataset.field;
    const isHtmlField = el.classList.contains("cms-wysiwyg-body");
    const isTextInput = el.tagName === "INPUT";
    const getValue = () => (isHtmlField ? el.innerHTML : isTextInput ? el.value.trim() : el.innerText.trim());
    el.addEventListener("blur", () => saveField(url, field, getValue()));
    // Also save shortly after typing stops, so work isn't lost if the admin
    // navigates away without clicking outside the field first.
    el.addEventListener("input", () => debouncedSave(url, field, getValue()));
  });

  // ---------- A post's own picture ----------
  // Uploaded straight from the post it belongs to, rather than from a
  // form somewhere else. The route redirects rather than answering in
  // JSON, so the page reloads to show the result — one picture at the top
  // of one post is not worth a second code path.
  bindEach(".cms-change-post-image-btn", (btn) => {
    const input = btn.parentElement.querySelector(".cms-post-image-file-input");
    if (!input) return;
    btn.addEventListener("click", () => input.click());
    input.addEventListener("change", async () => {
      const file = input.files[0];
      if (!file) return;
      const body = new FormData();
      body.append("image", file);
      try {
        const res = await fetch(input.dataset.uploadUrl, { method: "POST", body });
        if (res.ok) location.reload();
        else toast("Couldn't upload that picture");
      } catch {
        toast("Couldn't upload — check your connection");
      }
      input.value = "";
    });
  });

  // ---------- Picture fields inside block forms ----------
  // Choose from the Library, or upload straight from the device. Either
  // way the URL goes into the field's hidden input and the form saves
  // itself, so the picture appears on the page rather than after hunting
  // for an Apply button.
  bindEach(".cms-block-image-field", (field) => {
    const hidden = field.querySelector("input[type=hidden]");
    const thumb = field.querySelector(".cms-block-image-thumb");
    const empty = field.querySelector(".cms-block-image-none");
    const fileInput = field.querySelector(".cms-block-image-file");

    function use(url) {
      hidden.value = url || "";
      thumb.src = url || "";
      thumb.hidden = !url;
      empty.hidden = !!url;
      field.querySelector(".cms-block-image-clear").hidden = !url;
      field.closest("form")?.requestSubmit();
    }

    field.querySelector(".cms-block-image-pick").addEventListener("click", async () => {
      let images = [];
      try {
        const res = await fetch("/admin/images?picker=1", { headers: { "X-Inline-Edit": "1" } });
        images = (await res.json()).images || [];
      } catch {
        toast("Couldn't load the Media Library — check your connection");
        return;
      }
      if (!images.length) {
        toast("The Media Library is empty — upload a picture first");
        return;
      }
      const chosen = await cmsImagePicker(images);
      if (chosen) use(chosen);
    });

    field.querySelector(".cms-block-image-upload").addEventListener("click", () => fileInput.click());
    fileInput.addEventListener("change", async () => {
      const file = fileInput.files[0];
      if (!file) return;
      const body = new FormData();
      body.append("image", file);
      try {
        const res = await fetch("/admin/images/upload", {
          method: "POST", headers: { "X-Inline-Edit": "1" }, body,
        });
        const data = await res.json();
        if (res.ok && data.ok) use(data.url);
        else toast(data.error || "Couldn't upload that picture");
      } catch {
        toast("Couldn't upload — check your connection");
      }
      fileInput.value = "";
    });

    field.querySelector(".cms-block-image-clear").addEventListener("click", () => use(""));
  });

  // ---------- Link fields: reveal the address box only when needed ----------
  // A link is chosen from this site's pages. The last option is "somewhere
  // else", and only that one has anything to type, so the box for it stays
  // out of the way until it is the answer.
  bindEach("select.cms-link-select", (select) => {
    const other = select.closest("label")?.parentElement
      ?.querySelector(`input.cms-link-other[name="${select.name}__other"]`);
    if (!other) return;
    select.addEventListener("change", () => {
      const needsAddress = select.value === "__other__";
      other.hidden = !needsAddress;
      //  A chosen page is a finished answer, so it applies immediately.
      //  "Somewhere else" is not -- there is nothing to save until the
      //  address is typed, so that one waits for the box below it.
      if (needsAddress) other.focus();
      else select.form?.requestSubmit();
    });
    other.addEventListener("change", () => { if (other.value.trim()) other.form?.requestSubmit(); });
  });

  // ---------- Blocks: the words are edited in place ----------
  // A block's markup IS its stored value — the fields are read back off
  // the elements that display them — so editing one of those elements and
  // saving the whole block round-trips exactly. Each editable is a leaf
  // holding text, which is what keeps the structure safe: there is no
  // contenteditable wrapping a whole card for somebody to delete.
  bindEach(".cms-block-host[data-save-url]", (host) => {
    const url = host.dataset.saveUrl;
    const block = host.querySelector(".cms-block");
    if (!block) return;
    host.querySelectorAll("[data-field]").forEach((el) => {
      if (el.tagName === "IMG") return;           // pictures come from the toolbar
      //  A caret cannot go inside a <button>, and clicking an <a> follows
      //  it — so marking either one contenteditable produced a field that
      //  looked editable and was not. The builders put the words in a span
      //  inside the control now; this covers pages saved before that, by
      //  moving the field onto a span of its own the first time the page
      //  is edited. It heals on the next save, because a block's markup IS
      //  its stored value.
      if (el.tagName === "BUTTON" || el.tagName === "A") {
        const span = document.createElement("span");
        span.setAttribute("data-field", el.getAttribute("data-field"));
        span.textContent = el.textContent;
        el.removeAttribute("data-field");
        el.textContent = "";
        el.appendChild(span);
        el = span;
      }
      el.setAttribute("contenteditable", "true");
      el.classList.add("cms-block-editable");
      //  Inside a <button> or an <a>, a browser refuses to place a caret
      //  however editable the element says it is -- the control is atomic
      //  as far as editing goes. Making the control pointer-events: none
      //  (inline-editor.css) gets the click as far as this span, and this
      //  puts the caret in by hand, where it was clicked. Typing then
      //  works exactly as it does in a heading.
      const control = el.closest("button, a");
      if (control) {
        //  The click still has to be cancelled even though the control is
        //  pointer-events: none. That only governs hit-testing; the event
        //  still bubbles THROUGH the button, whose default action is to
        //  submit the form it sits in. The sign-up form has a required
        //  email box, so the browser failed validation and moved focus to
        //  it -- the caret was placed and then immediately taken away,
        //  which looked exactly like the label being uneditable.
        el.addEventListener("click", (e) => e.preventDefault());
        el.addEventListener("mousedown", (e) => {
          e.preventDefault();
          el.focus();
          const point = document.caretRangeFromPoint
            ? document.caretRangeFromPoint(e.clientX, e.clientY)
            : null;
          const range = point || (() => {
            const r = document.createRange();
            r.selectNodeContents(el);
            r.collapse(false);
            return r;
          })();
          const sel = document.getSelection();
          sel.removeAllRanges();
          sel.addRange(range);
        });
      }
      const push = () => saveField(url, "content", block.outerHTML);
      el.addEventListener("blur", push);
      el.addEventListener("input", () => debouncedSave(url, "content", block.outerHTML));
      // Enter inside a one-line field would otherwise plant a <div> in the
      // middle of a heading; a list is the one place it should work.
      el.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && el.tagName !== "UL" && el.tagName !== "OL") {
          e.preventDefault();
          el.blur();
        }
      });
    });
  });

  // ---------- WYSIWYG toolbar (formatting buttons + font/color pickers) ----------
  // A section can contain more than one editable body (Columns has one per
  // column), so track whichever was focused most recently rather than
  // always grabbing the first one in the section.
  let lastFocusedBody = null;
  document.addEventListener(
    "focusin",
    (e) => {
      if (e.target.classList?.contains("cms-wysiwyg-body")) lastFocusedBody = e.target;
    },
    true
  );

  function currentWysiwygBody(el) {
    const section = el.closest(".block, .cms-section");
    if (lastFocusedBody && section?.contains(lastFocusedBody)) return lastFocusedBody;
    return section?.querySelector(".cms-wysiwyg-body");
  }

  function saveWysiwygBody(body) {
    if (!body || !body.dataset.saveUrl) return;
    debouncedSave(body.dataset.saveUrl, "content", body.innerHTML);
  }

  // ---------- Section menu (the edit-section icon next to "+") ----------
  // Toggles the layout toolbar (Divide/background/width/Clear/Delete) for
  // one specific section — this is about the SECTION, never the tool.
  // The toolbar's position used to be pure CSS (absolute, left: 50% + a
  // fixed offset) — fine for a normal wide body section, but for a narrow
  // sidebar section that math places it way out past the section's own
  // (and often the viewport's) right edge: disconnected from the pencil
  // that opened it, partly or fully off-screen. Position it in JS instead,
  // anchored right next to whichever edit icon was actually clicked and
  // clamped to stay fully inside the viewport regardless of where that
  // icon lives.
  function positionSectionToolbar(toolbar, anchorIcon) {
    const iconRect = anchorIcon.getBoundingClientRect();
    toolbar.style.position = "fixed";
    toolbar.style.left = "0px"; toolbar.style.top = "0px"; // measure natural size unclamped first
    const tbRect = toolbar.getBoundingClientRect();
    let left = iconRect.right + 8;
    if (left + tbRect.width > window.innerWidth - 8) left = iconRect.left - tbRect.width - 8;
    if (left < 8) left = 8;
    let top = iconRect.top - 4;
    if (top + tbRect.height > window.innerHeight - 8) top = window.innerHeight - tbRect.height - 8;
    if (top < 8) top = 8;
    toolbar.style.left = left + "px";
    toolbar.style.top = top + "px";
  }
  bindEach(".cms-section-edit-icon", (icon) => {
    icon.addEventListener("click", () => {
      const target = document.getElementById(icon.dataset.target);
      if (!target) return;
      const opening = !target.classList.contains("cms-section-menu-open");
      document.querySelectorAll(".cms-section.cms-section-menu-open").forEach((s) => {
        s.classList.remove("cms-section-menu-open");
      });
      if (opening) {
        target.classList.add("cms-section-menu-open");
        const toolbar = target.querySelector(":scope > .cms-section-toolbar");
        if (toolbar) positionSectionToolbar(toolbar, icon);
      }
    });
  });
  document.addEventListener("click", (e) => {
    if (e.target.closest(".cms-section-toolbar, .cms-section-edit-icon")) return;
    document.querySelectorAll(".cms-section.cms-section-menu-open").forEach((s) => {
      s.classList.remove("cms-section-menu-open");
    });
  });

  // ---------- Tool menu (click the tool's own content to reveal it) ----------
  // Only clicking the tool's actual rendered content (the image, the text,
  // the menu links, ...) opens its menu — not the section generally, and
  // not the section's own layout toolbar/edit icon. Clicking away closes it.
  bindEach(".cms-section", (section) => {
    const panel = section.querySelector(":scope > .cms-tool-panel");
    const content = section.querySelector(":scope > .block");
    if (!panel || !content) return;
    content.addEventListener("click", (e) => {
      // The content itself can be (or contain) a link — an imported theme's
      // header logo pointing at "/" is exactly this — and without this, the
      // click both opens the tool panel AND fires the link's own
      // navigation, so the panel appears for an instant and then the page
      // navigates away, wiping it. While editing, selecting a tool should
      // never trigger the tool's own native behavior.
      const link = e.target.closest("a");
      // ...unless the link IS the editing action AND this tool is already
      // the one being worked on. First click selects the tool, like every
      // other tool; the second opens the post. Following it on the first
      // click meant brushing a card on the way to the tool's own settings
      // navigated away from the page instead.
      if (link && link.hasAttribute("data-cms-edit-link")
          && section.classList.contains("cms-tool-panel-open")) return;
      if (link && content.contains(link)) e.preventDefault();
      document.querySelectorAll(".cms-section.cms-tool-panel-open").forEach((s) => {
        if (s !== section) s.classList.remove("cms-tool-panel-open");
      });
      section.classList.add("cms-tool-panel-open");
    });
  });
  // Modals/popovers used by tool-panel controls (the image picker, the
  // confirm/prompt modal) render at the top of <body>, outside any
  // .cms-tool-panel — without excluding them here, picking an image (or
  // even just cancelling) reads as "clicked outside the panel" and closes
  // the toolbar the picker was opened from, right as the admin finishes
  // using it.
  document.addEventListener("click", (e) => {
    if (e.target.closest(".cms-section > .block, .cms-tool-panel, #cms-modal-backdrop, #cms-image-picker-backdrop")) return;
    document.querySelectorAll(".cms-section.cms-tool-panel-open").forEach((s) => {
      s.classList.remove("cms-tool-panel-open");
    });
  });

  // Tool-panel config fields (Menu's style/pages/nesting, Breadcrumb,
  // Banner, Card) submit via a full page reload rather than AJAX, which
  // would otherwise close the panel — that reopened-on-click state lives
  // only in a JS class, not anything the server remembers. Every one of
  // those forms redirects back with #section-<id> in the URL, so reopen
  // that section's panel on load instead of losing it every time a field
  // is changed (this was why picking "Dropdown" or a "nested under" page
  // looked like it did nothing: the panel vanished before the result was
  // visible).
  if (location.hash.startsWith("#section-")) {
    const target = document.querySelector(".cms-section" + location.hash);
    if (target && target.querySelector(":scope > .cms-tool-panel")) {
      target.classList.add("cms-tool-panel-open");
    }
  }

  // ---------- Single dynamic tool-header per Columns section ----------
  // Every populated cell/row has its own .cms-tool-header, but showing all
  // of them at once inside a multi-cell Columns section is cluttered — only
  // one is ever relevant at a time, and only once its own content has
  // actually been clicked (nothing shown by default). Move whichever
  // cell/row's content was clicked into the shared slot at the top of the
  // section; clicking a different cell swaps it; clicking outside the
  // whole Columns section clears it back to empty. Plain (non-Columns)
  // sections use the separate .cms-tool-panel mechanism instead.
  bindEach(".block-columns", (block) => {
    const slot = block.querySelector(".cms-active-tool-header-slot");
    if (!slot) return;
    let active = null;
    let originalParent = null;
    let originalNext = null;
    let activeZone = null;
    //  The header no longer travels to the slot at the top. It stays in
    //  its own cell -- always visible, collapsed to the tool's name --
    //  and expands in place. Moving it was how one tool's controls were
    //  kept from competing with five others, but that only worked while
    //  the headers were hidden; now that every cell shows its name, a
    //  bar that jumped out of its cell on click would take the one label
    //  saying which tool you just picked with it.
    function activate(zone, header) {
      if (!header || active === header) return;
      deactivate();
      header.classList.add("cms-tool-header-open");
      active = header;
      activeZone = zone;
      zone.classList.add("cms-tool-header-active");
    }
    function deactivate() {
      if (active) active.classList.remove("cms-tool-header-open");
      if (activeZone) activeZone.classList.remove("cms-tool-header-active");
      active = null;
      activeZone = null;
    }
    block.querySelectorAll(".cms-column, .cms-row-cell").forEach((zone) => {
      const header = zone.querySelector(":scope > .cms-tool-header");
      if (!header) return;
      // Only the cell's actual content activates it — its own header
      // (once moved into the slot) and the "Rows" control shouldn't.
      zone.addEventListener("click", (e) => {
        if (e.target.closest(".cms-tool-header, .cms-column-tools")) return;
        //  Same two-step in a Columns cell: the cell has to be the active
        //  one before a card inside it opens.
        if (e.target.closest("[data-cms-edit-link]")
            && zone.classList.contains("cms-tool-header-active")) return;
        // Same reason as the plain-section tool panel above: a cell's
        // content can itself be a link (an Image cell's link_url, a Menu
        // link, ...) — without this the click both activates the cell's
        // header in the slot AND fires the link, so it appears and is
        // immediately wiped by the resulting navigation.
        const link = e.target.closest("a");
        if (link && zone.contains(link)) e.preventDefault();
        activate(zone, header);
      });
    });
    document.addEventListener("click", (e) => {
      if (block.contains(e.target) || slot.contains(e.target)) return;
      deactivate();
    });
  });

  // Column-body divs now carry their own [data-save-url][data-field] (each
  // cell has its own save endpoint, since cells carry independent tool
  // state) so they're already covered by the generic autosave loop above —
  // no special-cased "serialize every column into one save" needed here
  // anymore. Formatting-toolbar buttons still call saveWysiwygBody directly
  // (see below), which now works unchanged for a column body too.

  // Column row-splitting is a real backend concept now (section_column_split_rows)
  // — each row is its own independent tool slot, not a client-side HTML
  // split of one shared tool's content — so the "Rows" select above is a
  // plain immediate-submit form (see page.html) with no JS needed here.

  // Track the last image clicked inside a WYSIWYG body — clicking an image
  // doesn't leave a usable text selection, so createLink needs another way
  // to know "link this image" was the intent.
  let lastClickedImage = null;
  document.addEventListener("click", (e) => {
    if (e.target.tagName === "IMG" && e.target.closest(".cms-wysiwyg-body")) {
      lastClickedImage = e.target;
    } else if (!e.target.closest(".cms-wysiwyg-toolbar")) {
      lastClickedImage = null;
    }
  });

  //  The toolbar's behaviour is shared with the admin's rich-text field
  //  (static/js/wysiwyg-commands.js). Only the three things that genuinely
  //  differ are passed in: which editable a control acts on, what to do
  //  afterwards, and how to ask for a URL.
  bindEach(".cms-wysiwyg-toolbar", (bar) => {
    window.cmsWysiwyg.bindToolbar(bar, {
      findBody: (el) => currentWysiwygBody(el),
      afterCommand: (body) => { if (body) saveWysiwygBody(body); },
      say: (message) => toast(message),
      askForLink: (done, body) => {
        const hasTextSelection = (window.getSelection()?.toString() || "").length > 0;
        const linkingImage = !hasTextSelection && lastClickedImage && body?.contains(lastClickedImage);
        cmsModal({
          message: linkingImage ? "Link URL for this image:" : "Link URL:",
          showInput: true,
          confirmLabel: "Add Link",
          danger: false,
        }).then(({ confirmed, value: url }) => done(confirmed ? url : null));
      },
      //  A link on a picture is not a link in the words: with nothing
      //  selected, createLink would do nothing at all, so the anchor is
      //  put around the image by hand.
      onLinkImage: (body, url) => {
        const hasTextSelection = (window.getSelection()?.toString() || "").length > 0;
        if (hasTextSelection || !lastClickedImage || !body?.contains(lastClickedImage)) return false;
        const existingLink = lastClickedImage.closest("a");
        if (existingLink) {
          existingLink.href = url;
        } else {
          const a = document.createElement("a");
          a.href = url;
          lastClickedImage.replaceWith(a);
          a.appendChild(lastClickedImage);
        }
        return true;
      },
    });
  });

  // Insert an image at the cursor — lets images sit alongside text inside
  // tables, cards, or any WYSIWYG body instead of only in dedicated Image
  // sections.
  // Insert an icon at the cursor — same shared grid the Menu tool uses
  // (see its own wiring above), but for freeform text: no stored item to
  // update, just an immediate insertHTML at wherever the cursor was before
  // the toolbar button stole focus.
  (function () {
    const grid = document.querySelector("#cms-insert-icon-picker .cms-icon-grid-view");
    if (!grid) return;
    let savedRange = null;
    let activeBody = null;

    function closeGrid() { grid.hidden = true; }

    document.querySelectorAll(".cms-insert-icon-btn").forEach((btn) => {
      btn.addEventListener("mousedown", () => {
        const sel = window.getSelection();
        if (sel.rangeCount) savedRange = sel.getRangeAt(0).cloneRange();
        activeBody = currentWysiwygBody(btn);
      });
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const opening = grid.hidden;
        if (!opening) { closeGrid(); return; }
        const btnRect = btn.getBoundingClientRect();
        grid.style.position = "fixed";
        grid.style.top = (btnRect.bottom + 2) + "px";
        grid.style.left = btnRect.left + "px";
        grid.hidden = false;
      });
    });
    grid.querySelectorAll(".cms-icon-grid-btn").forEach((iconBtn) => {
      iconBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        closeGrid();
        if (!activeBody) return;
        const sel = window.getSelection();
        sel.removeAllRanges();
        if (savedRange) sel.addRange(savedRange);
        document.execCommand("insertHTML", false, iconBtn.innerHTML + "&nbsp;");
        saveWysiwygBody(activeBody);
      });
    });
    document.addEventListener("click", (e) => {
      if (!grid.hidden && !e.target.closest(".cms-icon-grid-view, .cms-insert-icon-btn")) closeGrid();
    });
  })();

  // ---------- Table tool ----------
  // A table's shape (style, header row, how many rows/columns) is edited
  // straight in the live table and saved through the same WYSIWYG save its
  // cell text already uses — the two are one piece of content, so a
  // server-side rewrite would only be able to act on the last SAVED text,
  // silently dropping whatever the admin had just typed into a cell.
  // Replaces the old "cycle the table style" button, which was the tool's
  // only control and left row/column changes to the raw HTML editor.
  const TABLE_STYLES = ["cms-table", "cms-table-striped", "cms-table-colored", "cms-table-plain"];

  function tableCols(table) {
    return Math.max(0, ...Array.from(table.rows).map((r) => r.cells.length));
  }
  function tableBodyRows(table) {
    return Array.from(table.rows).filter((r) => r.parentElement.tagName !== "THEAD");
  }

  bindEach(".cms-table-config", (config) => {
    // Captured now, not on click: a Columns cell's tool header gets moved
    // into the section's shared header slot once the cell is selected, so
    // walking up from the button at click time would land on the wrong
    // cell (or the whole Columns section).
    const scope = config.closest(".cms-row-cell, .cms-column, .cms-section");
    const body = scope && scope.querySelector(".cms-html-preview, .cms-column-body");
    const table = body && body.querySelector("table");
    if (!table) return;

    const rowCount = config.querySelector(".cms-table-row-count");
    const colCount = config.querySelector(".cms-table-col-count");
    function commit() {
      rowCount.textContent = tableBodyRows(table).length;
      colCount.textContent = tableCols(table);
      saveWysiwygBody(body);
    }

    config.querySelector(".cms-table-style-select").addEventListener("change", (e) => {
      TABLE_STYLES.forEach((c) => table.classList.remove(c));
      table.classList.add(e.target.value);
      commit();
    });

    config.querySelector(".cms-table-header-toggle").addEventListener("change", (e) => {
      if (e.target.checked) {
        if (!table.tHead) {
          const head = table.createTHead();
          const row = head.insertRow();
          for (let i = 0; i < Math.max(1, tableCols(table)); i++) {
            const th = document.createElement("th");
            th.textContent = "Column " + (i + 1);
            row.appendChild(th);
          }
        }
      } else if (table.tHead) {
        table.deleteTHead();
      }
      commit();
    });

    config.querySelector(".cms-table-row-add").addEventListener("click", () => {
      const row = table.insertRow(-1); // -1 appends to the body, never the header
      for (let i = 0; i < Math.max(1, tableCols(table)); i++) {
        row.insertCell().textContent = "Detail";
      }
      commit();
    });

    config.querySelector(".cms-table-row-remove").addEventListener("click", () => {
      const rows = tableBodyRows(table);
      if (rows.length <= 1) {
        toast("A table needs at least one row");
        return;
      }
      rows[rows.length - 1].remove();
      commit();
    });

    config.querySelector(".cms-table-col-add").addEventListener("click", () => {
      const next = tableCols(table) + 1;
      Array.from(table.rows).forEach((row) => {
        const isHead = row.parentElement.tagName === "THEAD";
        const cell = document.createElement(isHead ? "th" : "td");
        cell.textContent = isHead ? "Column " + next : "Detail";
        row.appendChild(cell);
      });
      commit();
    });

    config.querySelector(".cms-table-col-remove").addEventListener("click", () => {
      if (tableCols(table) <= 1) {
        toast("A table needs at least one column");
        return;
      }
      Array.from(table.rows).forEach((row) => {
        if (row.cells.length) row.deleteCell(-1);
      });
      commit();
    });
  });



  // ---------- Video Gallery: upload a clip ----------
  // Each clip row's own button/input pair (the row is repeated, so each
  // button must find its own adjacent input rather than the first in the
  // form — same rule the Image Accordion's per-panel buttons follow). A
  // full reload after the upload is deliberate: the clip's thumbnail is
  // server-rendered markup, not a style tweak applied in place.
  bindEach(".cms-change-gallery-clip-btn", (btn) => {
    const input = btn.nextElementSibling;
    if (!input || !input.classList.contains("cms-gallery-clip-file-input")) return;
    btn.addEventListener("click", () => input.click());
    input.addEventListener("change", async () => {
      if (!input.files || !input.files[0]) return;
      const body = new FormData();
      body.append("clip", input.files[0]);
      btn.disabled = true;
      const stopTimer = window.cmsElapsedTimer ? window.cmsElapsedTimer(btn, "Uploading") : null;
      try {
        const res = await fetch(input.dataset.uploadUrl, {
          method: "POST",
          body,
          headers: { "X-Inline-Edit": "1" },
        });
        const data = await res.json();
        if (res.ok && data.ok) {
          location.reload();
          return;
        }
        toast(data.error || "Couldn't upload that video");
      } catch {
        toast("Couldn't upload — check your connection");
      }
      if (stopTimer) stopTimer();
      btn.disabled = false;
      input.value = "";
    });
  });


  // ---------- HTML section editor (raw code fallback, e.g. for embeds) ----------
  //  ".cms-column, .cms-section" rather than ".cms-section": the same
  //  Embed tool can stand in a column, and closest() then has to stop at
  //  the cell it lives in — stopping at the section would swap the FIRST
  //  preview/editor pair on the whole Columns block, whichever cell was
  //  clicked.
  bindEach(".cms-edit-html-btn", (btn) => {
    btn.addEventListener("click", () => {
      const section = btn.closest(".cms-column, .cms-section");
      section.querySelector(".cms-html-preview").hidden = true;
      section.querySelector(".cms-html-editor").hidden = false;
    });
  });

  bindEach(".cms-save-html-btn", (btn) => {
    btn.addEventListener("click", async () => {
      const section = btn.closest(".cms-column, .cms-section");
      const textarea = section.querySelector(".cms-html-editor textarea");
      await saveField(textarea.dataset.saveUrl, "content", textarea.value);
      section.querySelector(".cms-html-preview").innerHTML = textarea.value;
      section.querySelector(".cms-html-preview").hidden = false;
      section.querySelector(".cms-html-editor").hidden = true;
    });
  });

  // ---------- Card background image (optional, alongside the color fill) ----------
  // Sets the background-image directly on the .cms-card-shape element in
  // place, and toggles the "Remove image" button's own hidden state,
  // instead of reloading the whole page for what's just one CSS property
  // changing — a full reload here was resetting scroll position and
  // closing the side dock for a change with nothing structural about it.
  function setCardImage(scope, url, panelIndex) {
    // Shared by Card and Banner — both are background-image divs with the
    // same "Remove image" button class, just a different shape element.
    // An Image Accordion panel is the same idea repeated 5x in one
    // section, so it's told apart by panelIndex instead of a distinct
    // shape class — there's no single ".cms-accordion-panel" to match.
    const shape = panelIndex != null
      ? scope.querySelectorAll(".cms-accordion-panel")[panelIndex]
      : scope.querySelector(".cms-card-shape, .cms-banner");
    if (shape) shape.style.backgroundImage = url ? `url('${url}')` : "";
    if (panelIndex == null) {
      const clearBtn = scope.querySelector(".cms-clear-card-image-btn");
      if (clearBtn) clearBtn.hidden = !url;
    }
  }
  bindEach(".cms-change-card-image-btn, .cms-change-banner-image-btn, .cms-change-accordion-image-btn", (btn) => {
    const isPanel = btn.classList.contains("cms-change-accordion-image-btn");
    const scope = btn.closest(".cms-row-cell, .cms-column, .cms-section");
    // A Card/Banner scope has exactly one image button+input pair, so a
    // scope-wide query finds it; an Accordion scope has 5, so each button
    // must find its own adjacent input instead of always matching the
    // first one in the section.
    const fileInput = isPanel
      ? btn.nextElementSibling
      : scope.querySelector(".cms-card-image-file-input, .cms-banner-image-file-input");
    const panelIndex = isPanel ? parseInt(btn.dataset.panelIndex, 10) : null;
    btn.addEventListener("click", () => fileInput.click());
    fileInput.addEventListener("change", async () => {
      const file = fileInput.files[0];
      if (!file) return;
      const formData = new FormData();
      formData.set("image", file);
      try {
        const res = await fetch(fileInput.dataset.uploadUrl, {
          method: "POST",
          headers: { "X-Inline-Edit": "1" },
          body: formData,
        });
        const data = await res.json();
        if (res.ok && data.url) {
          setCardImage(scope, data.url, panelIndex);
          toast("Image updated");
        } else {
          toast(data.error || "Upload failed");
        }
      } catch {
        toast("Upload failed — check your connection");
      }
    });
  });
  bindEach(".cms-clear-card-image-btn", (btn) => {
    btn.addEventListener("click", async () => {
      const scope = btn.closest(".cms-row-cell, .cms-column, .cms-section");
      try {
        await fetch(btn.dataset.clearUrl, { method: "POST", headers: { "X-Inline-Edit": "1" } });
      } catch {}
      setCardImage(scope, null);
    });
  });

  // ---------- AI image generation (Image/Banner/Card "✨ Generate") ----------
  // One handler for all three tools — each button just carries its own
  // generate-url (see admin.py's *_image_generate routes), which already
  // knows the right target size and how to apply the result (content=
  // for Image, background-image for Banner/Card) server-side.
  async function applyGeneratedImage(btn, url) {
    // Persist the choice server-side (multi-generate no longer auto-applies
    // — see admin.py's *_image_apply routes) before touching the DOM, so a
    // failed apply doesn't leave the page showing an image that isn't
    // actually saved.
    try {
      const formData = new URLSearchParams();
      formData.set("kind", btn.dataset.kind || "image");
      formData.set("url", url);
      const res = await fetch(btn.dataset.applyUrl, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded", "X-Inline-Edit": "1" },
        body: formData,
      });
      if (!res.ok) {
        toast("Couldn't apply that image — check your connection");
        return;
      }
    } catch {
      toast("Couldn't apply that image — check your connection");
      return;
    }
    const scope = btn.closest(".cms-row-cell, .cms-column, .cms-section");
    if (btn.dataset.panelIndex != null && btn.dataset.panelIndex !== "") {
      setCardImage(scope, url, parseInt(btn.dataset.panelIndex, 10));
      return;
    }
    const img = scope.querySelector(".cms-column-body img, .cms-image-body img") || scope.querySelector("img");
    const bannerOrCard = scope.querySelector(".cms-banner, .cms-card-shape");
    if (img) img.src = url;
    else if (bannerOrCard) bannerOrCard.style.backgroundImage = `url('${url}')`;
    if (scope.querySelector(".cms-clear-card-image-btn")) {
      scope.querySelector(".cms-clear-card-image-btn").hidden = false;
    }
  }

  bindEach(".cms-generate-image-btn", (btn) => {
    btn.addEventListener("click", async () => {
      const { confirmed, value, count } = await cmsModal({
        message: "Describe the image you want:",
        showInput: true,
        showCount: true,
        confirmLabel: "Generate",
        danger: false,
      });
      if (!confirmed || !value || !value.trim()) return;
      // Generation can take anywhere from ~15s to well over a minute
      // depending on the backend (a cold-start ComfyUI workflow is slow) —
      // the original static toast vanished after 1.8s regardless, making
      // a genuinely-working long request look identical to a hung one.
      // A live counter directly on the button (which is also disabled,
      // so it can't be clicked again mid-request) stays visible the whole
      // time instead.
      const originalLabel = btn.textContent;
      btn.disabled = true;
      let seconds = 0;
      btn.textContent = "✨ Generating… 0s";
      const timer = setInterval(() => {
        seconds += 1;
        btn.textContent = "✨ Generating… " + seconds + "s";
      }, 1000);
      try {
        const formData = new URLSearchParams();
        formData.set("prompt", value.trim());
        formData.set("count", String(count || 1));
        const res = await fetch(btn.dataset.generateUrl, {
          method: "POST",
          headers: { "Content-Type": "application/x-www-form-urlencoded", "X-Inline-Edit": "1" },
          body: formData,
        });
        clearInterval(timer);
        const data = await res.json();
        btn.disabled = false;
        btn.textContent = originalLabel;
        const images = data.images || [];
        if (res.ok && images.length === 1) {
          // Single image: apply immediately, nothing to choose between.
          await applyGeneratedImage(btn, images[0].url);
          toast(data.error ? `Image generated (${data.error})` : "Image generated");
        } else if (res.ok && images.length > 1) {
          toast(`Generated ${images.length} — pick your favorite`);
          const chosen = await cmsImagePicker(images);
          if (chosen) {
            await applyGeneratedImage(btn, chosen);
            toast("Image applied — the rest are saved in the Media Library");
          } else {
            toast("Kept as-is — all generated images are saved in the Media Library");
          }
        } else {
          toast(data.error || "Image generation failed");
        }
      } catch {
        clearInterval(timer);
        btn.disabled = false;
        btn.textContent = originalLabel;
        toast("Image generation failed — check your connection");
      }
    });
  });

  // ---------- Banner/Card config forms (shape, color, position, text style, ...) ----------
  // These used to submit as a plain full-page reload (see the removed
  // comment in section_banner_update et al.) — harmless for most fields,
  // but it reset the page's scroll/panel-open state on every change, and
  // for a range input (the opacity slider) firing on every mouseup, that
  // read as the toolbar itself "closing" mid-adjustment. The backend now
  // returns the resulting class/style directly (see _banner_dom_response
  // in admin.py) so this can apply it in place instead.
  function applyCardBannerDom(scope, data, isBanner) {
    const target = scope.querySelector(isBanner ? ".cms-banner" : ".cms-card-shape");
    if (target) {
      target.className = data.class || target.className;
      if (data.style) target.setAttribute("style", data.style);
      else target.removeAttribute("style");
    }
    if (isBanner) {
      const overlay = scope.querySelector(".cms-banner-overlay");
      if (overlay) {
        if (data.overlay_style) overlay.setAttribute("style", data.overlay_style);
        else overlay.removeAttribute("style");
      }
    }
  }

  //  Declared blocks (Pricing, Testimonial, Numbers, Logo row, The team,
  //  Timeline, Call to action, Email sign-up) apply as you change them,
  //  like every other tool. They used to need an Apply button and a page
  //  load — eight tools out of step with the rest of the app for no
  //  reason other than that one shared form was written before the
  //  convention settled. The route hands back the rebuilt markup, which
  //  goes straight into the block's host.
  // ---------- Contacts: + and - change the FORM, not the page ----------
  // A line becomes content when it has something written in it, so adding
  // one is a question for the panel and not for the server: pressing +
  // should put an empty box under the line you pressed it on, with the
  // caret in it, and nothing else should happen at all. It used to submit
  // — which meant a round trip, and (briefly, worse) a whole-page refresh
  // that threw away where you were.
  //
  // The new row is CLONED from the one next to it rather than written out
  // here. This file has no business knowing what a contacts row looks
  // like; that is the template's, and a second copy of it here is exactly
  // the drift this project keeps having to undo.
  function renumber(form) {
    const rows = [...form.querySelectorAll(".cms-contact-row")];
    rows.forEach((row, i) => {
      row.querySelectorAll("[name]").forEach((el) => {
        el.name = el.name.replace(/_\d+$/, "_" + i);
        if (el.name === "op") el.value = el.value.replace(/_\d+$/, "_" + i);
      });
      row.querySelectorAll('button[name="op"]').forEach((b) => {
        b.value = b.value.replace(/_\d+$/, "_" + i);
      });
      const pick = row.querySelector(".cms-contact-icon-pick");
      if (pick) pick.dataset.row = String(i);
    });
    const count = form.querySelector('input[name="row_count"]');
    if (count) count.value = String(rows.length);
    return rows;
  }

  document.addEventListener("click", (e) => {
    const btn = e.target.closest('.cms-contact-tool-form button[name="op"]');
    if (!btn) return;
    const form = btn.closest(".cms-contact-tool-form");
    const row = btn.closest(".cms-contact-row");
    if (!form || !row) return;
    e.preventDefault();
    if (btn.value.startsWith("add_")) {
      const fresh = row.cloneNode(true);
      fresh.querySelectorAll("input").forEach((el) => {
        if (el.type === "checkbox") el.checked = true;
        else el.value = "";
      });
      row.after(fresh);
      renumber(form);
      //  On the next tick: the button takes focus on mousedown, which
      //  happens after this handler runs, so focusing the box here is
      //  undone a moment later and the caret ends up nowhere.
      const box = fresh.querySelector(".cms-contact-value");
      if (box) setTimeout(() => box.focus(), 0);
      //  Nothing is saved: an empty line is not content, and the server
      //  learns about it with the first thing typed into it.
      return;
    }
    //  Removing one IS a change to what is published, so it goes to the
    //  server — after the row is gone, so what is sent is what is left.
    row.remove();
    renumber(form);
    if (form.requestSubmit) form.requestSubmit();
    else form.submit();
  });

  bindEach(".cms-block-config-form", (form) => {
    const host = () => form.closest(".cms-section, .cms-column, .cms-row-cell")
      ?.querySelector(".cms-block-host");
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const body = new FormData(form);
      //  The +/- buttons carry their instruction in the button itself, so
      //  it has to be put back — FormData never includes the submitter.
      if (e.submitter && e.submitter.name) body.append(e.submitter.name, e.submitter.value);

      try {
        const res = await fetch(form.action, {
          method: "POST", headers: { "X-Inline-Edit": "1" }, body,
        });
        const data = await res.json();
        if (res.ok && data.ok) {
          const target = host();
          if (target) target.innerHTML = data.html;
          document.dispatchEvent(new CustomEvent("cms:site-refreshed"));
        } else {
          toast(data.error || "Couldn't save — please try again");
        }
      } catch {
        toast("Couldn't save — check your connection");
      }
    });
    //  A dropdown or a colour lands as soon as it changes; typing waits
    //  for a pause, the same debounce the rest of the editor uses.
    form.addEventListener("change", (e) => {
      if (e.target.type === "text" || e.target.tagName === "TEXTAREA") return;
      form.requestSubmit();
    });
    //  One debounced submitter per form, made once. Building it inside
    //  the handler would start a fresh timer on every keystroke, which
    //  debounces nothing and posts on every letter.
    const submitSoon = debounce(() => form.requestSubmit(), 600);
    form.addEventListener("input", (e) => {
      if (e.target.type !== "text" && e.target.tagName !== "TEXTAREA") return;
      submitSoon();
    });
  });

  bindEach(".cms-banner-config-form, .cms-card-config-form", (form) => {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const scope = form.closest(".cms-row-cell, .cms-column, .cms-section");
      const isBanner = form.classList.contains("cms-banner-config-form");
      try {
        const res = await fetch(form.action, {
          method: "POST",
          headers: { "X-Inline-Edit": "1" },
          body: new FormData(form),
        });
        const data = await res.json();
        if (res.ok && data.ok) {
          applyCardBannerDom(scope, data, isBanner);
        } else {
          toast(data.error || "Couldn't save — please try again");
        }
      } catch {
        toast("Couldn't save — check your connection");
      }
    });
  });

  bindEach(".cms-reset-card-btn", (btn) => {
    btn.addEventListener("click", async () => {
      const scope = btn.closest(".cms-row-cell, .cms-column, .cms-section");
      const form = btn.closest(".cms-card-config-form");
      try {
        const res = await fetch(btn.dataset.resetUrl, {
          method: "POST",
          headers: { "X-Inline-Edit": "1" },
        });
        const data = await res.json();
        if (res.ok && data.ok) {
          applyCardBannerDom(scope, data, false);
          if (form) {
            const shapeSelect = form.querySelector('select[name="shape"]');
            if (shapeSelect) shapeSelect.value = "rectangle";
            const colorInput = form.querySelector('input[name="color"]');
            if (colorInput) colorInput.value = "#f0f1f3";
          }
          const clearBtn = scope.querySelector(".cms-clear-card-image-btn");
          if (clearBtn) clearBtn.hidden = true;
          toast("Card reset to default");
        } else {
          toast(data.error || "Couldn't reset — please try again");
        }
      } catch {
        toast("Couldn't reset — check your connection");
      }
    });
  });

  // ---------- Media Library picker (choose an existing file instead of generating/uploading) ----------
  bindEach(".cms-library-pick-btn", (btn) => {
    btn.addEventListener("click", async () => {
      let images = [];
      try {
        const res = await fetch("/admin/images?picker=1", { headers: { "X-Inline-Edit": "1" } });
        const data = await res.json();
        images = data.images || [];
      } catch {
        toast("Couldn't load the Media Library — check your connection");
        return;
      }
      if (!images.length) {
        toast("The Media Library is empty — upload or generate an image first");
        return;
      }
      const chosen = await cmsImagePicker(images);
      if (chosen) await applyGeneratedImage(btn, chosen);
    });
  });

  // ---------- Image controls ----------
  // Every one of these controls can now live either in a full section's
  // toolbar or in a single Columns cell's own inline header — `.closest`
  // finds whichever is nearer, so a control inside a cell scopes to that
  // cell instead of accidentally grabbing the first match anywhere in the
  // (possibly multi-cell) parent section.
  bindEach(".cms-change-image-btn", (btn) => {
    const scope = btn.closest(".cms-row-cell, .cms-column, .cms-section");
    const fileInput = scope.querySelector(".cms-image-file-input");
    btn.addEventListener("click", () => fileInput.click());
    fileInput.addEventListener("change", async () => {
      const file = fileInput.files[0];
      if (!file) return;
      const formData = new FormData();
      formData.set("image", file);
      try {
        const res = await fetch(fileInput.dataset.uploadUrl, {
          method: "POST",
          headers: { "X-Inline-Edit": "1" },
          body: formData,
        });
        const data = await res.json();
        if (res.ok && data.url) {
          let img = scope.querySelector(".cms-managed-image");
          const placeholder = scope.querySelector(".cms-image-placeholder");
          if (!img) {
            img = document.createElement("img");
            img.className = "cms-managed-image";
            if (placeholder) placeholder.replaceWith(img);
            else (scope.querySelector(".block-image, .cms-column-body") || scope).appendChild(img);
          }
          img.src = data.url + "?t=" + Date.now();
          toast("Image updated");
        } else {
          toast(data.error || "Upload failed");
        }
      } catch {
        toast("Upload failed — check your connection");
      }
    });
  });

  bindEach(".cms-width-select", (select) => {
    select.addEventListener("change", async () => {
      const scope = select.closest(".cms-row-cell, .cms-column, .cms-section");
      const block = scope.querySelector(".block-image, .block-media, .cms-column-body");
      block.className = block.className.replace(/cms-img-\S+/, `cms-img-${select.value}`);
      await saveField(select.dataset.saveUrl, "width", select.value);
    });
  });

  bindEach(".cms-anim-select", (select) => {
    select.addEventListener("change", async () => {
      const scope = select.closest(".cms-row-cell, .cms-column, .cms-section");
      const block = scope.querySelector(".block-image, .cms-column-body");
      block.className = block.className.replace(/cms-anim-\S+/, "").trim();
      if (select.value !== "none") block.classList.add(`cms-anim-${select.value}`);
      await saveField(select.dataset.saveUrl, "animation", select.value);
    });
  });

  bindEach(".cms-mask-select", (select) => {
    select.addEventListener("change", async () => {
      const scope = select.closest(".cms-row-cell, .cms-column, .cms-section");
      const block = scope.querySelector(".block-image, .cms-column-body");
      block.className = block.className.replace(/cms-mask-\S+/, "").trim();
      block.classList.add(`cms-mask-${select.value}`);
      await saveField(select.dataset.saveUrl, "mask_shape", select.value);
    });
  });

  // ---------- Selected-section/zone styling (Colors panel's "Selection") ----------
  // Every section and zone carries its own bg/border(/corner) as data
  // attributes on a small 🎨 button rather than inline color pickers of
  // their own — clicking one just records what's selected and opens the
  // Colors panel, which has the one shared set of controls. Keeps the
  // page's own toolbars from getting crowded with color swatches, and
  // gives color editing one home instead of three.
  let cmsSelectedStyle = null; // {saveUrl, targetEl, cornerTargetEl, supportsCorner, label}

  function applyBg(el, value) { if (el) el.style.backgroundColor = value || ""; }
  function applyBorder(el, value) { if (el) el.style.border = value ? `2px solid ${value}` : ""; }
  function applyCorner(el, value) {
    if (!el) return;
    if (value) el.setAttribute("data-corner-style", value);
    else el.removeAttribute("data-corner-style");
  }
  // Depth rides on the SECTION rather than the inner block: the preset
  // redefines --site-shadow for everything inside it (see site-base.css),
  // so one attribute covers a Card, an Image and a Banner alike.
  function applyShadow(el, value) {
    if (!el) return;
    if (value) el.setAttribute("data-shadow-style", value);
    else el.removeAttribute("data-shadow-style");
  }

  function renderSelectedStyle() {
    const box = document.getElementById("cms-selected-style");
    const hint = document.getElementById("cms-selected-style-hint");
    if (!box || !hint) return;
    if (!cmsSelectedStyle) {
      box.hidden = true;
      hint.hidden = false;
      return;
    }
    box.hidden = false;
    hint.hidden = true;
    document.getElementById("cms-selected-style-label").textContent = cmsSelectedStyle.label;
    const bgInput = document.getElementById("cms-selected-bg-input");
    const borderInput = document.getElementById("cms-selected-border-input");
    const cornerSelect = document.getElementById("cms-selected-corner-select");
    bgInput.value = cmsSelectedStyle.bg || "#ffffff";
    document.getElementById("cms-selected-bg-reset").hidden = !cmsSelectedStyle.bg;
    borderInput.value = cmsSelectedStyle.border || "#000000";
    document.getElementById("cms-selected-border-reset").hidden = !cmsSelectedStyle.border;
    cornerSelect.hidden = !cmsSelectedStyle.supportsCorner;
    if (cmsSelectedStyle.supportsCorner) cornerSelect.value = cmsSelectedStyle.corner || "";
    //  The picture controls only mean anything on a real section — a zone
    //  has no row to store one on — so they follow the shadow control's
    //  rule rather than the corner one's.
    const bgImg = document.getElementById("cms-selected-bgimg-select");
    if (bgImg) {
      const isSection = !!cmsSelectedStyle.shadowEl;
      bgImg.hidden = !isSection;
      bgImg.value = cmsSelectedStyle.bgImage || "";
      ["cms-selected-bgoverlay-select", "cms-selected-bgpos-select"].forEach((id) => {
        const el = document.getElementById(id);
        if (!el) return;
        //  The dimming and position questions only arise once there IS a
        //  picture; showing them beforehand asks about nothing.
        el.hidden = !isSection || !cmsSelectedStyle.bgImage;
      });
      const overlay = document.getElementById("cms-selected-bgoverlay-select");
      const position = document.getElementById("cms-selected-bgpos-select");
      if (overlay) overlay.value = cmsSelectedStyle.bgOverlay || "medium";
      if (position) position.value = cmsSelectedStyle.bgPosition || "center";
    }
    const shadowSelect = document.getElementById("cms-selected-shadow-select");
    if (shadowSelect) {
      // Every section type can be raised (unlike corners, which only mean
      // something for Banner and the block-html tools), but a zone can't:
      // there is no section row to store it on.
      shadowSelect.hidden = !cmsSelectedStyle.shadowEl;
      shadowSelect.value = cmsSelectedStyle.shadow || "";
    }
  }

  // No dedicated "select for coloring" button on the page itself — the
  // point of moving this into the Colors panel was to get color chrome
  // OFF the sections/zones entirely. Instead, any click anywhere on a
  // section or zone (the same ordinary clicks that already select a tool,
  // follow a link's hover state, etc. — this is passive bookkeeping, never
  // preventDefault/stopPropagation, so it can't interfere with anything
  // else that click was already going to do) marks it "selected"; opening
  // Colors afterward shows whichever one was clicked most recently.
  document.addEventListener("click", (e) => {
    const section = e.target.closest(".cms-section");
    const scope = section || e.target.closest("header.site-header, footer.site-footer, aside.site-sidebar, main.site-content");
    if (!scope) return;
    const isBody = scope.tagName === "MAIN";
    //  The section itself, not the block inside it. Corners has a level
    //  for each now (see the tool select above), and this control is
    //  labelled "This section" — pointing it at the block made the two
    //  levels write to the same box, so neither could differ from the
    //  other. The value is inherited, so setting it here still reaches
    //  everything in the section that has not overridden it.
    const cornerTargetEl = section || null;
    cmsSelectedStyle = {
      saveUrl: scope.dataset.saveUrl,
      targetEl: isBody ? document.body : scope, // body's bg/border render on <body>, not <main> itself
      cornerTargetEl,
      bg: scope.dataset.bgColor || "",
      border: scope.dataset.borderColor || "",
      corner: scope.dataset.cornerStyle || "",
      supportsCorner: scope.dataset.supportsCorner === "1",
      shadow: section ? (scope.dataset.shadowStyle || "") : "",
      shadowEl: section || null,
      bgImage: section ? (scope.dataset.bgImage || "") : "",
      bgOverlay: section ? (scope.dataset.bgOverlay || "") : "",
      bgPosition: section ? (scope.dataset.bgPosition || "") : "",
      label: scope.dataset.styleLabel || "Selection",
    };
    if (document.getElementById("cms-colors-panel")?.classList.contains("cms-dock-front")) renderSelectedStyle();
  });
  // Also refresh right when Colors is opened (clicking a section, then
  // opening Colors, should show that selection immediately — not wait for
  // one more click after the panel's already up).
  bindById("cms-colors-tab", "click", renderSelectedStyle);

  // The site's own markup can be replaced under us without a page load
  // (see admin/live-refresh.js, which is what applying a template does
  // now). Two things have to happen when it is: the new markup needs the
  // same wiring the old markup had, and anything holding a reference to
  // a node that is no longer in the document has to let go of it — a
  // selection whose section has been replaced would otherwise write
  // colors into a detached element nobody can see.
  document.addEventListener("cms:site-refreshed", () => {
    cmsBindings.forEach((run) => run());
    if (cmsSelectedStyle && !document.contains(cmsSelectedStyle.targetEl)) {
      cmsSelectedStyle = null;
      renderSelectedStyle();
    }
  });

  // ---------- Individual font picker (Fonts & Shape panel) ----------
  // One shared <select> (style-revealing — see style_panel.html) plus
  // three small "apply as ___" buttons, instead of duplicating the same
  // ~50-font list three times. Each button's form just needs the
  // currently-picked name copied into its own hidden field before it
  // submits.
  bindEach(".cms-font-role-form", (form) => {
    form.addEventListener("submit", (e) => {
      const picker = document.getElementById("cms-font-individual-select");
      const input = form.querySelector(".cms-font-role-input");
      if (!picker || !picker.value) {
        e.preventDefault();
        return;
      }
      input.value = picker.value;
    });
  });

  bindById("cms-selected-bg-input", "change", async (e) => {
    if (!cmsSelectedStyle) return;
    cmsSelectedStyle.bg = e.target.value;
    applyBg(cmsSelectedStyle.targetEl, e.target.value);
    document.getElementById("cms-selected-bg-reset").hidden = false;
    await saveField(cmsSelectedStyle.saveUrl, "bg_color", e.target.value);
  });
  bindById("cms-selected-bg-reset", "click", async () => {
    if (!cmsSelectedStyle) return;
    cmsSelectedStyle.bg = "";
    applyBg(cmsSelectedStyle.targetEl, "");
    document.getElementById("cms-selected-bg-reset").hidden = true;
    await saveField(cmsSelectedStyle.saveUrl, "bg_color", "");
  });
  bindById("cms-selected-border-input", "change", async (e) => {
    if (!cmsSelectedStyle) return;
    cmsSelectedStyle.border = e.target.value;
    applyBorder(cmsSelectedStyle.targetEl, e.target.value);
    document.getElementById("cms-selected-border-reset").hidden = false;
    await saveField(cmsSelectedStyle.saveUrl, "border_color", e.target.value);
  });
  bindById("cms-selected-border-reset", "click", async () => {
    if (!cmsSelectedStyle) return;
    cmsSelectedStyle.border = "";
    applyBorder(cmsSelectedStyle.targetEl, "");
    document.getElementById("cms-selected-border-reset").hidden = true;
    await saveField(cmsSelectedStyle.saveUrl, "border_color", "");
  });
  //  Background picture, how much it is dimmed, and where it sits. Same
  //  pattern as the colour controls above — change it, it saves. A reload
  //  follows because the overlay and the text colour that goes with it
  //  are decided server-side, not patched onto the element here.
  ["cms-selected-bgimg-select", "cms-selected-bgoverlay-select", "cms-selected-bgpos-select"]
    .forEach((id) => {
      bindById(id, "change", async () => {
        if (!cmsSelectedStyle) return;
        const value = document.getElementById(id).value;
        const field = { "cms-selected-bgimg-select": "bg_image",
                        "cms-selected-bgoverlay-select": "bg_overlay",
                        "cms-selected-bgpos-select": "bg_position" }[id];
        await saveField(cmsSelectedStyle.saveUrl, field, value);
        //  In place where that is possible: this control lives in the
        //  Colours panel, and a reload would shut the panel it was just
        //  used from (see admin/live-refresh.js).
        if (window.cmsRefreshSite) window.cmsRefreshSite({});
        else window.location.reload();
      });
    });

  //  The same setting, on the section's own toolbar. Writes the attribute
  //  straight onto the section so the change is visible immediately —
  //  every corner in the app reads --site-radius, and [data-corner-style]
  //  redefines it for everything inside that section (see site-base.css).
  //  The innermost level: this tool only. Written onto the block (or the
  //  Columns cell) rather than the section, so it redefines --site-radius
  //  for its own subtree and leaves its neighbours on the section's value.
  bindEach(".cms-tool-corner-select", (select) => {
    select.addEventListener("change", async () => {
      const scope = select.closest(".cms-column, .cms-row-cell")
        || select.closest(".cms-section")?.querySelector(":scope > .block");
      if (scope) applyCorner(scope, select.value);
      await saveField(select.dataset.saveUrl, select.dataset.cornerField, select.value);
    });
  });

  //  Depth's tool level, the counterpart to the corner select above.
  bindEach(".cms-tool-shadow-select", (select) => {
    select.addEventListener("change", async () => {
      const scope = select.closest(".cms-column, .cms-row-cell")
        || select.closest(".cms-section")?.querySelector(":scope > .block");
      if (scope) applyShadow(scope, select.value);
      await saveField(select.dataset.saveUrl, select.dataset.shadowField, select.value);
    });
  });

  //  The section's background picture, dim and position, from the
  //  section's own bar. The same three fields the Colours panel writes —
  //  and like that copy, the page is refreshed afterwards, because the
  //  overlay class and the text colour that goes with it are decided
  //  server-side rather than patched onto the element here.
  const mediaImages = (() => {
    const el = document.getElementById("cms-media-images");
    try { return el ? JSON.parse(el.textContent) : []; } catch { return []; }
  })();
  async function saveSectionBg(btn, url) {
    await saveField(btn.dataset.saveUrl, "bg_image", url);
    if (window.cmsRefreshSite) window.cmsRefreshSite({});
    else window.location.reload();
  }
  bindEach(".cms-section-bg-pick", (btn) => {
    btn.addEventListener("click", async () => {
      if (!mediaImages.length) {
        toast("No pictures yet — add some in the Media Library first");
        return;
      }
      const url = await cmsImagePicker(mediaImages);
      if (url) await saveSectionBg(btn, url);
    });
  });
  bindEach(".cms-section-bg-clear", (btn) => {
    btn.addEventListener("click", () => saveSectionBg(btn, ""));
  });
  bindEach(".cms-section-bg-select", (select) => {
    select.addEventListener("change", async () => {
      await saveField(select.dataset.saveUrl, select.dataset.field, select.value);
      if (window.cmsRefreshSite) window.cmsRefreshSite({});
      else window.location.reload();
    });
  });

  bindEach(".cms-section-corner-select", (select) => {
    select.addEventListener("change", async () => {
      const section = select.closest(".cms-section");
      if (!section) return;
      applyCorner(section, select.value);
      //  Keep the Colors panel's copy of this control in step, in case
      //  this section is also the one currently selected there.
      if (cmsSelectedStyle && cmsSelectedStyle.targetEl === section) {
        cmsSelectedStyle.corner = select.value;
        renderSelectedStyle();
      }
      await saveField(select.dataset.saveUrl, "corner_style", select.value);
    });
  });

  bindById("cms-selected-corner-select", "change", async (e) => {
    if (!cmsSelectedStyle) return;
    cmsSelectedStyle.corner = e.target.value;
    applyCorner(cmsSelectedStyle.cornerTargetEl, e.target.value);
    await saveField(cmsSelectedStyle.saveUrl, "corner_style", e.target.value);
  });
  bindById("cms-selected-shadow-select", "change", async (e) => {
    if (!cmsSelectedStyle || !cmsSelectedStyle.shadowEl) return;
    cmsSelectedStyle.shadow = e.target.value;
    applyShadow(cmsSelectedStyle.shadowEl, e.target.value);
    await saveField(cmsSelectedStyle.saveUrl, "shadow_style", e.target.value);
  });

  // ---------- Section width (auto / full / custom %) ----------
  const defaultSectionWidth = document.getElementById("cms-sections-list")?.dataset.defaultWidth || "auto";
  bindEach(".cms-layout-width-select", (select) => {
    select.addEventListener("change", async () => {
      const section = select.closest(".cms-section");
      const pctInput = section.querySelector(":scope > .cms-section-toolbar .cms-layout-width-pct-input");
      if (pctInput) pctInput.hidden = select.value !== "custom";
      // "auto" resolves to whatever the site-wide default currently is —
      // everything else (full/custom) is exactly what was just picked.
      const effective = select.value === "auto" ? defaultSectionWidth : select.value;
      section.dataset.layoutWidth = effective;
      if (effective === "custom" && pctInput) {
        section.style.setProperty("--cms-width-pct", pctInput.value);
      }
      await saveField(select.dataset.saveUrl, "layout_width", select.value);
      // In the sidebar this same control also decides page-wide reach
      // (Full pushes the header/footer over too, via a server-rendered
      // <body> class) — that's a structural change no client-side CSS
      // tweak can express, so reload to pick it up immediately instead
      // of only taking effect on the next navigation.
      if (section.closest(".site-sidebar-zone")) location.reload();
    });
  });
  bindEach(".cms-layout-width-pct-input", (input) => {
    input.addEventListener("change", async () => {
      const section = input.closest(".cms-section");
      section.style.setProperty("--cms-width-pct", input.value);
      await saveField(input.dataset.saveUrl, "layout_width_pct", input.value);
    });
  });

  // ---------- Sidebar rail width (auto / custom px) ----------
  // Separate from the Height control above (which reuses layout_width for
  // a different axis in the sidebar) — this is the rail's own width, and
  // it changes the whole page's grid/flex column sizing, not just this
  // section, so it needs the same reload-to-apply treatment Full/Auto
  // height already gets.
  bindEach(".cms-sidebar-width-select", (select) => {
    select.addEventListener("change", async () => {
      const section = select.closest(".cms-section");
      const pxInput = section.querySelector(":scope > .cms-section-toolbar .cms-sidebar-width-px-input");
      if (pxInput) pxInput.hidden = select.value !== "custom";
      await saveField(select.dataset.saveUrl, "sidebar_width", select.value);
      location.reload();
    });
  });
  bindEach(".cms-sidebar-width-px-input", (input) => {
    input.addEventListener("change", async () => {
      await saveField(input.dataset.saveUrl, "sidebar_width_px", input.value);
      location.reload();
    });
  });

  // ---------- Drag-to-resize: sidebar width / horizontal section height ----------
  // Same two fields the Width/Height selects above already write
  // (sidebar_width+sidebar_width_px, content_height_px) — dragging is just
  // a second, more direct way to set the same values, not a separate
  // system. Width drags update --cms-sidebar-width live on <body> (every
  // sidebar-layout rule already reads that variable); height drags set
  // the section's own inline height directly. Saves once on release, not
  // on every mousemove.
  bindEach(".cms-resize-handle", (handle) => {
    const axis = handle.dataset.axis;
    // Left rail vs right rail write to different CSS variables (and drag
    // in opposite directions relative to the mouse — dragging the right
    // rail's inner edge further right should make it NARROWER, not wider).
    const isRightRail = handle.classList.contains("cms-resize-handle-w-right");
    const widthVar = isRightRail ? "--cms-sidebar-right-width" : "--cms-sidebar-width";
    handle.addEventListener("mousedown", (e) => {
      e.preventDefault();
      const section = handle.closest(".cms-section");
      const startX = e.clientX, startY = e.clientY;
      const startWidth = parseInt(getComputedStyle(document.body).getPropertyValue(widthVar)) || section.getBoundingClientRect().width;
      const startHeight = section.getBoundingClientRect().height;
      let pending = null;
      document.body.classList.add("cms-resizing", axis === "width" ? "cms-resizing-w" : "cms-resizing-h");

      function onMove(ev) {
        if (axis === "width") {
          const delta = isRightRail ? (startX - ev.clientX) : (ev.clientX - startX);
          pending = Math.max(160, Math.min(600, Math.round(startWidth + delta)));
          document.body.style.setProperty(widthVar, pending + "px");
        } else {
          pending = Math.max(60, Math.min(2000, Math.round(startHeight + (ev.clientY - startY))));
          // The height/scroll goes on the .block content wrapper, not
          // .cms-section itself — see .cms-has-custom-height in
          // site-base.css. Keeping .cms-section unconstrained is what
          // stops its own toolbar/resize-handle from being clipped.
          section.style.setProperty("--cms-content-height-px", pending + "px");
          section.classList.add("cms-has-custom-height");
        }
      }
      function onUp() {
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup", onUp);
        document.body.classList.remove("cms-resizing", "cms-resizing-w", "cms-resizing-h");
        if (pending === null) return;
        if (axis === "width") {
          saveField(handle.dataset.saveUrl, "sidebar_width", "custom");
          saveField(handle.dataset.saveUrl, "sidebar_width_px", String(pending));
        } else {
          saveField(handle.dataset.saveUrl, "content_height_px", String(pending));
          const resetBtn = section.querySelector(":scope > .cms-section-toolbar .cms-content-height-reset");
          if (resetBtn) resetBtn.hidden = false;
        }
      }
      document.addEventListener("mousemove", onMove);
      document.addEventListener("mouseup", onUp);
    });
  });
  bindEach(".cms-content-height-reset", (btn) => {
    btn.addEventListener("click", async () => {
      const section = btn.closest(".cms-section");
      section.classList.remove("cms-has-custom-height");
      section.style.removeProperty("--cms-content-height-px");
      btn.hidden = true;
      await saveField(btn.dataset.saveUrl, "content_height_px", "");
    });
  });

  // ---------- File / download controls ----------
  bindEach(".cms-file-display-select", (select) => {
    select.addEventListener("change", async () => {
      await saveField(select.dataset.saveUrl, "file_display", select.value);
      location.reload(); // display styles differ structurally (card/button/link/icon)
    });
  });

  bindEach(".cms-change-file-btn", (btn) => {
    const scope = btn.closest(".cms-row-cell, .cms-column, .cms-section");
    const fileInput = scope.querySelector(".cms-file-file-input");
    btn.addEventListener("click", () => fileInput.click());
    fileInput.addEventListener("change", async () => {
      const file = fileInput.files[0];
      if (!file) return;
      const formData = new FormData();
      formData.set("file", file);
      try {
        const res = await fetch(fileInput.dataset.uploadUrl, {
          method: "POST",
          headers: { "X-Inline-Edit": "1" },
          body: formData,
        });
        const data = await res.json();
        if (res.ok && data.url) {
          toast("File uploaded — reloading…");
          location.reload();
        } else {
          toast(data.error || "Upload failed");
        }
      } catch {
        toast("Upload failed — check your connection");
      }
    });
  });

  // ---------- Media player controls ----------
  bindEach(".cms-media-type-select", (select) => {
    select.addEventListener("change", async () => {
      await saveField(select.dataset.saveUrl, "media_type", select.value);
      location.reload(); // youtube/video/audio need different controls entirely
    });
  });

  bindEach(".cms-change-media-btn", (btn) => {
    const scope = btn.closest(".cms-row-cell, .cms-column, .cms-section");
    const fileInput = scope.querySelector(".cms-media-file-input");
    btn.addEventListener("click", () => fileInput.click());
    fileInput.addEventListener("change", async () => {
      const file = fileInput.files[0];
      if (!file) return;
      const formData = new FormData();
      formData.set("media", file);
      try {
        const res = await fetch(fileInput.dataset.uploadUrl, {
          method: "POST",
          headers: { "X-Inline-Edit": "1" },
          body: formData,
        });
        const data = await res.json();
        if (res.ok && data.url) {
          toast("Media uploaded — reloading…");
          location.reload();
        } else {
          toast(data.error || "Upload failed");
        }
      } catch {
        toast("Upload failed — check your connection");
      }
    });
  });

  bindEach(".cms-generate-video-btn", (btn) => {
    btn.addEventListener("click", async () => {
      const { confirmed, value } = await cmsModal({
        message: "Describe the video you want (24s, generated by AI — this can take several minutes):",
        showInput: true,
        confirmLabel: "Generate",
        danger: false,
      });
      if (!confirmed || !value || !value.trim()) return;
      const originalLabel = btn.textContent;
      btn.disabled = true;
      let seconds = 0;
      btn.textContent = "🎥 Generating… 0s";
      const timer = setInterval(() => {
        seconds += 1;
        btn.textContent = "🎥 Generating… " + seconds + "s";
      }, 1000);
      try {
        const formData = new URLSearchParams();
        formData.set("prompt", value.trim());
        const res = await fetch(btn.dataset.generateUrl, {
          method: "POST",
          headers: { "Content-Type": "application/x-www-form-urlencoded", "X-Inline-Edit": "1" },
          body: formData,
        });
        clearInterval(timer);
        const data = await res.json();
        btn.disabled = false;
        btn.textContent = originalLabel;
        if (res.ok && data.url) {
          toast("Video generated — reloading…");
          location.reload();
        } else {
          toast(data.error || "Video generation failed");
        }
      } catch {
        clearInterval(timer);
        btn.disabled = false;
        btn.textContent = originalLabel;
        toast("Video generation failed — check your connection");
      }
    });
  });

  // Live-update the YouTube preview as the admin types/pastes a link,
  // without waiting for a reload.
  const YOUTUBE_ID_RE = /(?:youtube(?:-nocookie)?\.com\/(?:watch\?v=|embed\/|shorts\/)|youtu\.be\/)([\w-]{11})/;
  bindEach(".cms-youtube-input", (input) => {
    input.addEventListener("input", () => {
      const scope = input.closest(".cms-row-cell, .cms-column, .cms-section");
      const match = input.value.match(YOUTUBE_ID_RE);
      let wrap = scope.querySelector(".cms-media-responsive");
      const placeholder = scope.querySelector(".cms-image-placeholder");
      if (match) {
        const embedUrl = `https://www.youtube-nocookie.com/embed/${match[1]}`;
        if (!wrap) {
          wrap = document.createElement("div");
          wrap.className = "cms-media-responsive";
          wrap.innerHTML = '<iframe allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>';
          (placeholder || scope.querySelector(".block-media, .cms-column-body")).replaceWith(wrap);
        }
        wrap.querySelector("iframe").src = embedUrl;
      }
    });
  });

  // ---------- Drag-and-drop reordering ----------
  bindEach("[data-reorder-url]", (container) => {
    container.querySelectorAll(".cms-drag-handle").forEach((handle) => {
      handle.setAttribute("draggable", "true");
      handle.addEventListener("dragstart", (e) => {
        const section = handle.closest(".cms-section");
        if (!section) return;
        const id = section.dataset.sectionId ?? section.dataset.chunkIndex;
        container.dataset.draggingId = id;
        e.dataTransfer.effectAllowed = "move";
        e.dataTransfer.setData("text/plain", String(id));
        section.classList.add("cms-dragging");
      });
    });

    container.addEventListener("dragover", (e) => {
      const draggingId = container.dataset.draggingId;
      if (draggingId === undefined) return;
      e.preventDefault();
      const draggingEl = [...container.children].find(
        (el) => (el.dataset.sectionId ?? el.dataset.chunkIndex) === draggingId
      );
      const target = e.target.closest(".cms-section");
      if (!draggingEl || !target || target === draggingEl || target.parentElement !== container) return;
      const rect = target.getBoundingClientRect();
      const before = e.clientY - rect.top < rect.height / 2;
      container.insertBefore(draggingEl, before ? target : target.nextSibling);
    });

    container.addEventListener("drop", (e) => e.preventDefault());

    container.addEventListener("dragend", async () => {
      const draggingEl = container.querySelector(".cms-dragging");
      if (draggingEl) draggingEl.classList.remove("cms-dragging");
      delete container.dataset.draggingId;
      const order = [...container.children].map((el) => el.dataset.sectionId ?? el.dataset.chunkIndex);
      const body = new URLSearchParams();
      body.set("order", order.join(","));
      try {
        const res = await fetch(container.dataset.reorderUrl, {
          method: "POST",
          headers: { "Content-Type": "application/x-www-form-urlencoded", "X-Inline-Edit": "1" },
          body,
        });
        toast(res.ok ? "Order saved" : "Couldn't save the new order");
      } catch {
        toast("Couldn't save the new order — check your connection");
      }
    });
  });
})();

//  Contacts: pick a line's icon by looking at it.
//  The grid is the shared one (partials/icon_picker.html), rendered once
//  per Contacts form and opened beside whichever line's icon button was
//  pressed. Choosing writes the glyph into that line's hidden field and
//  submits, so the page shows the new icon straight away — the same
//  apply-on-change every other tool panel has.
(function () {
  const FALLBACK_ICON = "\u{1F517}";
  document.addEventListener("click", (e) => {
    const pick = e.target.closest(".cms-contact-icon-pick");
    const form = pick && pick.closest(".cms-contact-tool-form");
    if (pick && form) {
      e.preventDefault();
      const grid = form.querySelector(".cms-icon-grid-view");
      if (!grid) return;
      const same = grid.dataset.row === pick.dataset.row && !grid.hidden;
      grid.hidden = same;
      grid.dataset.row = pick.dataset.row;
      return;
    }
    const iconBtn = e.target.closest(".cms-contact-tool-form .cms-icon-grid-btn");
    if (iconBtn) {
      e.preventDefault();
      const grid = iconBtn.closest(".cms-icon-grid-view");
      const f = iconBtn.closest(".cms-contact-tool-form");
      const row = grid && grid.dataset.row;
      if (!f || row === undefined) return;
      const field = f.querySelector('input[name="icon_' + row + '"]');
      const button = f.querySelector('.cms-contact-icon-pick[data-row="' + row + '"]');
      if (field) field.value = iconBtn.dataset.iconKey || "";
      //  The grid button already holds the drawn mark -- an emoji, or the
      //  SVG for a brand. Copying its contents is why a network's icon
      //  shows as its logo; writing the key put "brand:x" on the button.
      if (button) button.innerHTML = iconBtn.innerHTML || FALLBACK_ICON;
      grid.hidden = true;
      if (f.requestSubmit) { f.requestSubmit(); } else { f.submit(); }
      return;
    }
    //  Anywhere else closes an open grid.
    if (!e.target.closest(".cms-icon-grid-view")) {
      document.querySelectorAll(".cms-contact-tool-form .cms-icon-grid-view")
        .forEach((g) => { g.hidden = true; });
    }
  });
})();
