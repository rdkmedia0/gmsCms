// Deferred to DOMContentLoaded: this partial is included near the top of
// the page (right after the admin bar), before #cms-sections-list even
// exists in the DOM (it's further down inside <main>) — running
// immediately made every lookup of it return null, silently skipping all
// drag-and-drop wiring. This was the actual cause of "dragging doesn't work".
(function () {
  document.addEventListener("DOMContentLoaded", init);
  if (document.readyState !== "loading") init();

  function init() {
  const panel = document.getElementById("cms-tools-panel");
  const deleteForm = document.getElementById("cms-tool-delete-form");
  const currentPath = panel.dataset.currentPath;

  panel.querySelectorAll(".cms-tool-delete").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (!confirm("Delete this custom tool? Sections already using it are unaffected.")) return;
      deleteForm.action = "/admin/tools/" + btn.dataset.toolId + "/delete";
      deleteForm.submit();
    });
  });

  // Dragging a tool chip onto a sections list adds it to the page (at the
  // end) — the existing drag-handle reorder then moves it wherever it's
  // wanted, so this doesn't need to compute a drop index itself. There are
  // up to four lists on a page (header/body/sidebar/footer) — all of them
  // need to accept tool placement, not just the body list.
  //  These lists are in the PAGE, not in this panel, and the page can be
  //  re-rendered underneath without a load — applying a template does
  //  exactly that (see admin/live-refresh.js). Every wiring pass over
  //  them is therefore kept, so it can be applied again to the lists that
  //  arrive; each list remembers which passes it has already had, so a
  //  list that survived is never wired twice.
  const zonePasses = [];
  const zoneWired = new WeakMap();
  function zoneLists() {
    return Array.from(document.querySelectorAll(
      "#cms-sections-list, #cms-header-list, #cms-sidebar-list, #cms-footer-list"
    )).filter((el) => el.id);
  }
  function applyZonePass(pass) {
    zoneLists().forEach((list) => {
      let had = zoneWired.get(list);
      if (!had) zoneWired.set(list, (had = new Set()));
      if (had.has(pass)) return;
      had.add(pass);
      pass(list);
    });
  }
  function wireZones(pass) {
    zonePasses.push(pass);
    applyZonePass(pass);
  }
  document.addEventListener("cms:site-refreshed", () => zonePasses.forEach(applyZonePass));
  panel.querySelectorAll(".cms-tool-chip").forEach((chip) => {
    chip.addEventListener("dragstart", (e) => {
      e.dataTransfer.effectAllowed = "copy";
      e.dataTransfer.setData("text/cms-tool-id", chip.dataset.toolId);
    });
  });

  // Primary interaction: click a tool to "arm" it, then click the section
  // (or cell) to place it there. Drag-and-drop above still works for anyone
  // whose browser/input supports it, but click-to-arm/click-to-place is the
  // one that doesn't depend on native HTML5 DnD actually firing.
  const hint = document.getElementById("cms-tools-hint");
  const defaultHint = hint ? hint.textContent : "";
  let armedTool = null;

  function setArmed(chip) {
    if (armedTool && armedTool.chip) armedTool.chip.classList.remove("cms-tool-armed");
    if (chip) {
      chip.classList.add("cms-tool-armed");
      armedTool = { id: chip.dataset.toolId, chip: chip };
      if (hint) hint.textContent = "Now click the section or cell for " + chip.dataset.toolName + " — or click the tool again to cancel.";
      document.body.classList.add("cms-placing-tool");
    } else {
      armedTool = null;
      if (hint) hint.textContent = defaultHint;
      document.body.classList.remove("cms-placing-tool");
    }
  }

  panel.querySelectorAll(".cms-tool-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      if (armedTool && armedTool.id === chip.dataset.toolId) {
        setArmed(null);
      } else {
        setArmed(chip);
      }
    });
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && armedTool) setArmed(null);
  });

  wireZones((sectionsList) => {
    sectionsList.addEventListener("click", (e) => {
      if (!armedTool) return;
      // Ignore clicks on real controls, or on a contenteditable area that
      // already has content (that's a text-editing click, not a placement
      // click). An EMPTY contenteditable — e.g. a Columns cell's body div,
      // which is present and contenteditable even with nothing in it —
      // still counts as a valid placement target, otherwise most of an
      // empty column cell is dead space that silently swallows the click.
      if (e.target.closest("button, a, input, select, textarea")) return;
      const editableAncestor = e.target.closest('[contenteditable="true"]');
      if (editableAncestor && editableAncestor.textContent.trim() !== "") return;
      // A row cell (inside a divided column) is more specific than the
      // column it lives in — check it first, or clicks inside a row would
      // always target the whole column instead of that one row.
      const targetRow = e.target.closest(".cms-row-cell");
      const targetColumn = e.target.closest(".cms-column");
      const targetSection = e.target.closest(".cms-section[data-section-id]");
      let action = null;
      if (targetRow && targetRow.dataset.setToolUrl) {
        action = targetRow.dataset.setToolUrl;
      } else if (targetColumn && targetColumn.dataset.setToolUrl) {
        action = targetColumn.dataset.setToolUrl;
      } else if (targetSection) {
        action = "/admin/sections/" + targetSection.dataset.sectionId + "/set-tool";
      } else {
        // No section/cell here yet to place into (an empty page, or empty
        // space below the last section) — create one and drop the tool
        // straight into it in one step, rather than making the admin add
        // a blank section first and then place the tool separately.
        action = newSectionUrl(sectionsList);
      }
      if (!action) return;
      e.preventDefault();
      const form = document.createElement("form");
      form.method = "post";
      form.action = action;
      form.hidden = true;
      const toolInput = document.createElement("input");
      toolInput.type = "hidden"; toolInput.name = "tool_id"; toolInput.value = armedTool.id;
      const nextInput = document.createElement("input");
      nextInput.type = "hidden"; nextInput.name = "next"; nextInput.value = currentPath;
      form.appendChild(toolInput);
      form.appendChild(nextInput);
      document.body.appendChild(form);
      form.submit();
    });
  });

  // A Columns section has several cells but only ONE .cms-section element
  // (they all share it) — so a drop target must resolve to the specific
  // .cms-column cell first; only fall back to the whole .cms-section when
  // it's a plain (non-columns) frame, where the section itself is the
  // one cell.
  function resolveDropTarget(el) {
    return el.closest(".cms-row-cell") || el.closest(".cms-column") || el.closest(".cms-section[data-section-id]");
  }
  // No section exists at the drop/click point yet (an empty page, or empty
  // space below the last section) — reuse the same "Add a section here"
  // divider's own form action (always rendered, even with zero sections;
  // see render_zone_list) so a new section gets created in the right zone
  // (body/header/footer) and page, then the tool is placed into it as part
  // of that same request via tool_id.
  function newSectionUrl(sectionsList) {
    const dividerForm = sectionsList.querySelector(".cms-section-divider form");
    return dividerForm ? dividerForm.action : null;
  }
  wireZones((sectionsList) => {
    let lastHovered = null;
    sectionsList.addEventListener("dragover", (e) => {
      if (!e.dataTransfer.types.includes("text/cms-tool-id")) return;
      e.preventDefault();
      const target = resolveDropTarget(e.target);
      if (target === lastHovered) return;
      if (lastHovered) lastHovered.classList.remove("cms-tool-drop-target");
      lastHovered = target;
      if (target) target.classList.add("cms-tool-drop-target");
    });
    sectionsList.addEventListener("dragleave", (e) => {
      if (!sectionsList.contains(e.relatedTarget) && lastHovered) {
        lastHovered.classList.remove("cms-tool-drop-target");
        lastHovered = null;
      }
    });
    sectionsList.addEventListener("drop", (e) => {
      const toolId = e.dataTransfer.getData("text/cms-tool-id");
      if (!toolId) return;
      e.preventDefault();

      // Dropping onto a specific cell (whether inside a Columns section or
      // a plain single-cell frame) sets just that cell's tool in place.
      // Dropping anywhere else in the list is a no-op — there's no "append
      // at the end" target once tool chips stopped being individual forms.
      const targetRow = e.target.closest(".cms-row-cell");
      const targetColumn = e.target.closest(".cms-column");
      const targetSection = e.target.closest(".cms-section[data-section-id]");
      let action = null;
      if (targetRow && targetRow.dataset.setToolUrl) {
        action = targetRow.dataset.setToolUrl;
      } else if (targetColumn && targetColumn.dataset.setToolUrl) {
        action = targetColumn.dataset.setToolUrl;
      } else if (targetSection) {
        action = "/admin/sections/" + targetSection.dataset.sectionId + "/set-tool";
      } else {
        action = newSectionUrl(sectionsList);
      }
      if (!action) return;
      const form = document.createElement("form");
      form.method = "post";
      form.action = action;
      form.hidden = true;
      const toolInput = document.createElement("input");
      toolInput.type = "hidden"; toolInput.name = "tool_id"; toolInput.value = toolId;
      const nextInput = document.createElement("input");
      nextInput.type = "hidden"; nextInput.name = "next"; nextInput.value = currentPath;
      form.appendChild(toolInput);
      form.appendChild(nextInput);
      document.body.appendChild(form);
      form.submit();
    });
  });

  // ---------- Search, grouping, collapsing, and drag-to-reorder ----------
  //
  // The grid arrives from the server already grouped — one
  // .cms-tools-group per category, each with its own heading — which is
  // also the site's stored order, so the default view needs nothing from
  // this file. Everything here rearranges the chips already on the page:
  // searching hides them, the Grouped switch regroups or flattens them,
  // a heading folds its own group away, and dragging moves a chip and
  // persists the result as the new stored order.
  const grid = document.getElementById("cms-tools-grid");
  if (grid) {
    // One search box per panel header (see dock_tool_search.html) — matched
    // by class, and kept showing the same text, so it reads as one control
    // that happens to be wherever you are rather than several.
    const searchInputs = Array.from(document.querySelectorAll(".cms-tools-search-input"));
    const searchInput = searchInputs[0] || null;
    //  The Grouped switch is dock-wide now and rendered in every panel's
    //  header (see dock_grouped_toggle.html), so read whichever copy is
    //  to hand — side-panels.js keeps them all showing the same state.
    const groupedToggle = document.querySelector(".cms-grouped-input");
    const noMatch = document.getElementById("cms-tools-no-match");
    const reorderUrl = grid.dataset.reorderUrl;

    // The true order — what the server has stored. Captured once from the
    // rendered grid, then kept in step with every drag. Regrouping and
    // flattening are both rebuilt from this, so neither can lose it.
    let customOrder = Array.from(grid.querySelectorAll(".cms-tool-chip"));
    // Category key -> its heading text, read off the markup the server
    // rendered rather than duplicated here as a second list to keep in
    // step with the Python one.
    const categoryLabelText = {};
    const categoryOrder = [];
    grid.querySelectorAll(".cms-tools-group").forEach((group) => {
      const key = group.dataset.category;
      const head = group.querySelector(".cms-tools-group-head");
      if (key && !(key in categoryLabelText)) {
        categoryLabelText[key] = head ? head.textContent.trim() : key;
        categoryOrder.push(key);
      }
    });
    // Which groups the admin has folded away, so rebuilding the grid
    // (toggling Grouped, or a drag) does not silently reopen them.
    const collapsed = new Set();

    function makeGroup(key) {
      const group = document.createElement("div");
      group.className = "cms-tools-group";
      group.dataset.category = key;
      const head = document.createElement("div");
      head.className = "cms-tools-group-head";
      head.title = "Click to fold this group away";
      head.textContent = categoryLabelText[key] || key;
      const chips = document.createElement("div");
      chips.className = "cms-tools-group-chips";
      group.appendChild(head);
      group.appendChild(chips);
      if (collapsed.has(key)) group.classList.add("is-collapsed");
      return { group, chips };
    }

    //  Read the stored choice rather than the checkbox's markup default:
    //  this file and side-panels.js both run on DOMContentLoaded, so the
    //  box may not have been set to the remembered state yet when the
    //  first layout happens.
    function isGrouped() {
      return localStorage.getItem("cmsDockGrouped") !== "0";
    }

    function layOut() {
      const grouped = isGrouped();
      grid.textContent = "";
      grid.classList.toggle("is-flat", !grouped);
      if (!grouped) {
        //  Ungrouped: the admin's own order, straight into the grid, with
        //  no headings — which is also the only view in which dragging a
        //  chip anywhere is unambiguous.
        customOrder.forEach((chip) => grid.appendChild(chip));
      } else {
        categoryOrder.forEach((key) => {
          const inCategory = customOrder.filter((chip) => chip.dataset.toolCategory === key);
          if (!inCategory.length) return;
          const { group, chips } = makeGroup(key);
          inCategory.forEach((chip) => chips.appendChild(chip));
          grid.appendChild(group);
        });
      }
      applyFilters();
    }

    function applyFilters() {
      const query = (searchInput ? searchInput.value : "").trim().toLowerCase();
      let anyVisible = false;
      grid.querySelectorAll(".cms-tool-chip").forEach((chip) => {
        const show = !query || chip.dataset.toolName.toLowerCase().includes(query);
        chip.hidden = !show;
        if (show) anyVisible = true;
      });
      // A heading with nothing visible under it is worse than no heading —
      // "Ecommerce" over an empty space reads as a fault, not as "nothing
      // here matched your search".
      grid.querySelectorAll(".cms-tools-group").forEach((group) => {
        const hasVisible = !!group.querySelector(".cms-tool-chip:not([hidden])");
        group.hidden = !hasVisible;
      });
      if (noMatch) noMatch.hidden = anyVisible;
    }

    searchInputs.forEach((input) => {
      input.addEventListener("input", () => {
        searchInputs.forEach((other) => { if (other !== input) other.value = input.value; });
        applyFilters();
        // Typing a tool's name from Colours or Fonts is a request to see
        // that tool, so bring the panel holding it forward. Only on a real
        // query — clearing the box should not yank the panel about.
        if (input.value.trim() && window.cmsOpenDockPanel) {
          const panelEl = document.getElementById("cms-tools-panel");
          if (panelEl && !panelEl.classList.contains("cms-dock-front")) {
            window.cmsOpenDockPanel("tools");
            // Carry on typing in the box that is now in front, not the one
            // that just went behind the Tools panel.
            const here = panelEl.querySelector(".cms-tools-search-input");
            if (here && here !== input) {
              here.focus();
              here.setSelectionRange(here.value.length, here.value.length);
            }
          }
        }
      });
    });
    document.querySelectorAll(".cms-grouped-input").forEach((input) => {
      input.addEventListener("change", () => {
        //  The input's own state is the freshest answer on a real click;
        //  store it before laying out so isGrouped() agrees.
        localStorage.setItem("cmsDockGrouped", input.checked ? "1" : "0");
        layOut();
      });
    });
    //  The grid arrives grouped from the server. If the remembered choice
    //  is "flat", it has to be rebuilt once at load — otherwise the switch
    //  reads unticked while the tools are still in their groups.
    if (!isGrouped()) layOut();

    // Folding a group away. Delegated from the grid, so it keeps working
    // on the groups layOut() builds fresh rather than only the ones the
    // server rendered.
    grid.addEventListener("click", (e) => {
      const head = e.target.closest(".cms-tools-group-head");
      if (!head || !grid.contains(head)) return;
      const group = head.closest(".cms-tools-group");
      const key = group.dataset.category;
      group.classList.toggle("is-collapsed");
      if (group.classList.contains("is-collapsed")) collapsed.add(key);
      else collapsed.delete(key);
    });

    // Dragging a chip within the grid reorders the panel — a separate
    // gesture from dragging it onto the page, told apart only by where it
    // is dropped, which is exactly how a person would expect a single
    // drag action to work. The chip is moved live as the cursor crosses
    // its neighbours, the common "sortable list" feel, using distance to
    // each chip's own center to decide which one the cursor is nearest.
    let dragging = null;
    grid.addEventListener("dragstart", (e) => {
      const chip = e.target.closest(".cms-tool-chip");
      if (chip && grid.contains(chip)) dragging = chip;
    });
    grid.addEventListener("dragend", () => { dragging = null; });

    function nearestChip(x, y) {
      let best = null;
      let bestDistance = Infinity;
      grid.querySelectorAll(".cms-tool-chip").forEach((chip) => {
        if (chip === dragging || chip.hidden) return;
        const rect = chip.getBoundingClientRect();
        const cx = rect.left + rect.width / 2;
        const cy = rect.top + rect.height / 2;
        const distance = Math.hypot(x - cx, y - cy);
        if (distance < bestDistance) {
          bestDistance = distance;
          best = { chip, after: x > cx || y > cy + rect.height / 2 };
        }
      });
      return best;
    }

    grid.addEventListener("dragover", (e) => {
      if (!dragging) return;
      e.preventDefault();
      const target = nearestChip(e.clientX, e.clientY);
      if (!target) return;
      if (target.after) target.chip.after(dragging);
      else target.chip.before(dragging);
    });

    grid.addEventListener("drop", (e) => {
      if (!dragging) return;
      e.preventDefault();
      //  Read the new order from the DOM before anything rebuilds it, and
      //  drop out of Grouped: a hand-made order and a by-category one are
      //  different answers to the same question, so a drag is taken as
      //  asking for the former.
      customOrder = Array.from(grid.querySelectorAll(".cms-tool-chip"));
      document.querySelectorAll(".cms-grouped-input").forEach((i) => { i.checked = false; });
      document.querySelectorAll(".cms-dock-panel").forEach((p) => p.classList.add("cms-dock-ungrouped"));
      localStorage.setItem("cmsDockGrouped", "0");
      layOut();
      if (reorderUrl) {
        fetch(reorderUrl, {
          method: "POST",
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
          body: "order=" + customOrder.map((chip) => chip.dataset.toolId).join(","),
        }).catch(() => {});
      }
    });
    }
  }
})();
