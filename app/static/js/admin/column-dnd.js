// Dragging tools BETWEEN column cells, and reordering the rows inside a
// column. Both post with X-Inline-Edit (so the server answers with JSON,
// never a redirect) and then re-render the site in place -- no full reload,
// no scroll jump, and it can never bounce to the admin dashboard.
//
// The two use different dataTransfer types (cms-cell-move / cms-row-move)
// so they never trip the tool-panel's own "drop a NEW tool here" drag
// (cms-tool-id), and neither trips the other.
(function () {
  "use strict";
  var boundCells = new WeakSet();
  var boundRows = new WeakSet();

  function post(url, params) {
    if (!url) return;
    fetch(url, {
      method: "POST", credentials: "same-origin",
      headers: { "X-Inline-Edit": "1", "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams(params),
    })
      .then(function (r) {
        if (!r.ok) throw new Error("failed");
        if (window.cmsRefreshSite) return window.cmsRefreshSite();
        location.reload();
      })
      .catch(function () { location.reload(); });
  }

  //  Move a tool from one cell to another (a SWAP server-side, so nothing
  //  is lost). The handle names its column; the drop target is another.
  function wireCellMove(grid) {
    if (boundCells.has(grid)) return;
    boundCells.add(grid);
    function clearTargets() {
      grid.querySelectorAll(".cms-cell-drop-target").forEach(function (c) {
        c.classList.remove("cms-cell-drop-target");
      });
    }
    grid.querySelectorAll(".cms-cell-drag-handle").forEach(function (h) {
      h.addEventListener("dragstart", function (e) {
        var col = h.closest(".cms-column");
        var from = col ? col.getAttribute("data-col-index") : "";
        e.dataTransfer.effectAllowed = "move";
        e.dataTransfer.setData("text/cms-cell-move", from || "");
      });
    });
    grid.addEventListener("dragover", function (e) {
      if (!e.dataTransfer.types.includes("text/cms-cell-move")) return;
      e.preventDefault();
      clearTargets();
      var col = e.target.closest(".cms-column");
      if (col) col.classList.add("cms-cell-drop-target");
    });
    grid.addEventListener("dragleave", function (e) {
      if (!grid.contains(e.relatedTarget)) clearTargets();
    });
    grid.addEventListener("drop", function (e) {
      if (!e.dataTransfer.types.includes("text/cms-cell-move")) return;
      e.preventDefault();
      var from = e.dataTransfer.getData("text/cms-cell-move");
      var col = e.target.closest(".cms-column");
      clearTargets();
      if (!col || from === "") return;
      var to = col.getAttribute("data-col-index");
      if (to === from) return;
      post(grid.getAttribute("data-cell-move-url"),
           { from: from, to: to, next: location.pathname });
    });
  }

  //  Reorder the stacked rows in one column. The elements are moved in the
  //  DOM as you drag; on drop their ORIGINAL data-row-index values, read in
  //  the new DOM order, are the permutation the server applies.
  function wireRowReorder(container) {
    if (boundRows.has(container)) return;
    boundRows.add(container);
    var dragRow = null;
    function rows() {
      return [].slice.call(container.children).filter(function (el) {
        return el.classList && el.classList.contains("cms-row-cell");
      });
    }
    container.querySelectorAll(".cms-row-drag-handle").forEach(function (h) {
      if (h.closest(".cms-column-rows") !== container) return;
      h.addEventListener("dragstart", function (e) {
        dragRow = h.closest(".cms-row-cell");
        e.dataTransfer.effectAllowed = "move";
        e.dataTransfer.setData("text/cms-row-move", "1");
        container.classList.add("cms-rows-dragging");
      });
    });
    container.addEventListener("dragover", function (e) {
      if (!dragRow) return;
      e.preventDefault();
      var target = e.target.closest(".cms-row-cell");
      if (!target || target === dragRow || target.parentElement !== container) return;
      var rect = target.getBoundingClientRect();
      var before = (e.clientY - rect.top) < rect.height / 2;
      container.insertBefore(dragRow, before ? target : target.nextSibling);
    });
    container.addEventListener("drop", function (e) { e.preventDefault(); });
    container.addEventListener("dragend", function () {
      container.classList.remove("cms-rows-dragging");
      if (!dragRow) return;
      dragRow = null;
      var order = rows().map(function (c) { return c.getAttribute("data-row-index"); }).join(",");
      post(container.getAttribute("data-rows-reorder-url"),
           { order: order, next: location.pathname });
    });
  }

  function wireAll() {
    document.querySelectorAll(".cms-columns[data-cell-move-url]").forEach(wireCellMove);
    document.querySelectorAll(".cms-column-rows[data-rows-reorder-url]").forEach(wireRowReorder);
  }
  wireAll();
  //  The live refresh swaps main.site-content, so re-wire the new markup.
  document.addEventListener("cms:site-refreshed", wireAll);
})();
