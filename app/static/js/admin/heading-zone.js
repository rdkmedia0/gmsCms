// The optional heading for a tool. The CONTROLS (a tick for on/off, the
// level H2/H3/Paragraph and the alignment) live in the tool's own toolbar;
// the heading itself sits ABOVE the tool. The two are linked by a shared
// data-save-url, so this pairs them and keeps the heading in step. The
// heading's words autosave through inline-editor.js (data-field="title").
(function () {
  "use strict";

  function save(url, field, value) {
    if (!url) return;
    var body = new URLSearchParams();
    body.set(field, value);
    fetch(url, {
      method: "POST", credentials: "same-origin",
      headers: { "X-Inline-Edit": "1", "Content-Type": "application/x-www-form-urlencoded" },
      body: body,
    }).catch(function () {});
  }

  //  The heading's anchor (above its tool) carries the SAME data-save-url as
  //  its controls -- match on that rather than DOM proximity, which a
  //  columns section would get wrong.
  function anchorFor(url) {
    var found = null;
    document.querySelectorAll(".cms-tool-heading").forEach(function (a) {
      if (a.getAttribute("data-save-url") === url) found = a;
    });
    return found;
  }
  function heading(anchor) { return anchor ? anchor.querySelector(".cms-tool-title") : null; }

  function makeHeading(anchor, lvl, aln) {
    var el = document.createElement(lvl || "h2");
    el.className = "cms-tool-title cms-th-align-" + (aln || "left");
    el.setAttribute("data-field", "title");
    el.setAttribute("data-save-url", anchor.getAttribute("data-save-url"));
    el.setAttribute("data-placeholder", "Type a heading\u2026");
    el.setAttribute("contenteditable", "true");
    anchor.appendChild(el);
    document.dispatchEvent(new CustomEvent("cms:site-refreshed")); // wire its autosave
    el.focus();
  }

  function bind(ctrl) {
    if (ctrl.__thBound) return;
    ctrl.__thBound = true;
    var url = ctrl.getAttribute("data-save-url");
    var on = ctrl.querySelector(".cms-th-on");
    var lvlSel = ctrl.querySelector(".cms-th-level");
    var alnSel = ctrl.querySelector(".cms-th-align");

    if (on) on.addEventListener("change", function () {
      var isOn = on.checked;
      save(url, "title_on", isOn ? "1" : "0");
      if (lvlSel) lvlSel.hidden = !isOn;
      if (alnSel) alnSel.hidden = !isOn;
      var anchor = anchorFor(url);
      if (!anchor) return;
      var h = heading(anchor);
      if (isOn && !h) makeHeading(anchor, lvlSel && lvlSel.value, alnSel && alnSel.value);
      else if (!isOn && h) h.remove();
    });

    if (lvlSel) lvlSel.addEventListener("change", function () {
      save(url, "title_level", lvlSel.value);
      var h = heading(anchorFor(url));
      if (!h) return;
      var fresh = document.createElement(lvlSel.value);
      fresh.className = h.className;
      ["data-field", "data-save-url", "data-placeholder", "contenteditable"]
        .forEach(function (a) { if (h.hasAttribute(a)) fresh.setAttribute(a, h.getAttribute(a)); });
      fresh.innerHTML = h.innerHTML;
      h.replaceWith(fresh);
      document.dispatchEvent(new CustomEvent("cms:site-refreshed"));
    });

    if (alnSel) alnSel.addEventListener("change", function () {
      save(url, "title_align", alnSel.value);
      var h = heading(anchorFor(url));
      if (h) h.className = "cms-tool-title cms-th-align-" + alnSel.value;
    });
  }

  function bindAll() { document.querySelectorAll(".cms-heading-controls").forEach(bind); }
  bindAll();
  document.addEventListener("cms:site-refreshed", bindAll);
})();
