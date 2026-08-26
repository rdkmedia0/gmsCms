// Re-render the site in place, without a page load.
//
// Every dock action that changes the whole site — activating a template,
// picking a palette, switching the header layout, reloading a template's
// content — used to finish with location.reload(). That threw away far
// more than it needed to: the editing dock was rebuilt from scratch, so
// whatever the admin had open (a panel, a popover, a folded section, a
// scroll position part-way along the bar) closed itself, and the dock
// animated back in as if it had just been opened for the first time.
// Closing those is the admin's decision to make, not a side effect of
// changing a colour.
//
// So instead: ask the server for the page it would have sent, and put
// only the parts that actually changed into the live document —
//
//   * the theme/colour/font stylesheets in <head> (updated in place, so
//     the page never renders unstyled for a frame),
//   * <title> and <body>'s own classes/inline style (the nav layout and
//     the page background live there),
//   * the site's regions: admin bar, header, both sidebars, main, footer,
//   * the three dock panels whose contents are a view OF the active
//     template — Colours, Fonts & Shape, Template & Layout — since a
//     different template has different palette roles, different fonts and
//     a different "active" tile. Their open/folded/scrolled state is
//     recorded first and put back afterwards, so they look untouched.
//
// Everything else — the Assistant, Tools, the modal, the tab strip, the
// dock's position and size — is left exactly as it was, because nothing
// about it depends on which template is active.
//
// Two events go out afterwards: "cms:site-refreshed" for the page's own
// scripts (site.js, inline-editor.js) to wire up the new markup, and
// "cms:dock-refreshed" for the panels' (template-panel.js, side-panels.js).
// Anything that cannot be done — a failed request, a response that is not
// a page (a login redirect, say) — falls back to a full load, so the
// admin always ends up looking at the truth.
(function () {
  "use strict";

  //  In document order. The insertion logic below relies on that: a
  //  region the current page does not have yet (a sidebar that has just
  //  appeared) goes in front of the next one that does exist.
  var REGIONS = [
    ".cms-admin-bar",
    "header.site-header",
    "aside.site-sidebar:not(.site-sidebar-right)",
    "main.site-content",
    "aside.site-sidebar-right",
    "footer.site-footer",
  ];

  //  Also in document order, and also the order they must appear in the
  //  <head> — fonts, then the theme's own stylesheet, then the colour
  //  overrides that have to win against it.
  var THEME_ASSETS = ["fonts", "theme", "colors", "font-preview"];

  var PANELS = ["cms-colors-panel", "cms-style-panel", "cms-template-panel"];

  function assetSelector(key) {
    return '[data-cms-theme-asset="' + key + '"]';
  }

  function syncThemeAssets(fresh) {
    var end = document.head.querySelector("[data-cms-theme-end]");
    THEME_ASSETS.forEach(function (key, index) {
      var from = fresh.head.querySelector(assetSelector(key));
      var live = document.head.querySelector(assetSelector(key));
      if (!from) {
        if (live) live.remove();
        return;
      }
      //  Point the existing node at the new stylesheet rather than
      //  swapping the node out: a removed <link> takes its rules with it
      //  immediately, and the page flashes unstyled until the replacement
      //  has loaded.
      if (live && live.tagName === from.tagName) {
        if (live.tagName === "LINK") {
          if (live.getAttribute("href") !== from.getAttribute("href")) {
            live.setAttribute("href", from.getAttribute("href"));
          }
        } else if (live.textContent !== from.textContent) {
          live.textContent = from.textContent;
        }
        return;
      }
      if (live) live.remove();
      var before = null;
      for (var i = index + 1; i < THEME_ASSETS.length && !before; i++) {
        before = document.head.querySelector(assetSelector(THEME_ASSETS[i]));
      }
      document.head.insertBefore(document.importNode(from, true), before || end || null);
    });
  }

  function syncRegions(fresh) {
    //  Always present, for every visitor, and it sits after the last of
    //  the regions — so it is what a newly-appeared region is inserted in
    //  front of when there is no later region to use.
    var tail = document.getElementById("cms-lightbox");
    REGIONS.forEach(function (selector, index) {
      var from = fresh.querySelector(selector);
      var live = document.querySelector(selector);
      if (!from) {
        if (live) live.remove();
        return;
      }
      var node = document.importNode(from, true);
      if (live) {
        live.replaceWith(node);
        return;
      }
      var before = null;
      for (var i = index + 1; i < REGIONS.length && !before; i++) {
        before = document.querySelector(REGIONS[i]);
      }
      document.body.insertBefore(node, before || tail || null);
    });
  }

  //  What a disclosure or a folded section is called is the only handle
  //  there is on it: the server gives them no ids, and it should not have
  //  to — this is the editor keeping its own state, not content.
  function labelOf(el) {
    var clone = el.cloneNode(true);
    clone.querySelectorAll(".cms-panel-help").forEach(function (help) { help.remove(); });
    return clone.textContent.trim().slice(0, 60);
  }

  function readPanelState(panel) {
    var content = panel.querySelector(".cms-dock-content");
    var open = [];
    var collapsed = [];
    if (content) {
      content.querySelectorAll("details[open] > summary").forEach(function (summary) {
        open.push(labelOf(summary));
      });
      content.querySelectorAll(".cms-dock-group.is-collapsed > .cms-dock-group-head").forEach(function (head) {
        collapsed.push(labelOf(head));
      });
    }
    return {
      open: open,
      collapsed: collapsed,
      scrollLeft: content ? content.scrollLeft : 0,
      scrollTop: content ? content.scrollTop : 0,
    };
  }

  function restorePanelState(panel, state) {
    var content = panel.querySelector(".cms-dock-content");
    if (!content) return;
    content.querySelectorAll("details > summary").forEach(function (summary) {
      if (state.open.indexOf(labelOf(summary)) !== -1) summary.parentElement.open = true;
    });
    content.querySelectorAll(".cms-dock-group > .cms-dock-group-head").forEach(function (head) {
      if (state.collapsed.indexOf(labelOf(head)) !== -1) head.parentElement.classList.add("is-collapsed");
    });
    content.scrollLeft = state.scrollLeft;
    content.scrollTop = state.scrollTop;
  }

  function syncPanels(fresh) {
    PANELS.forEach(function (id) {
      var live = document.getElementById(id);
      var from = fresh.getElementById(id);
      if (!live || !from) return;
      var liveContent = live.querySelector(".cms-dock-content");
      var freshContent = from.querySelector(".cms-dock-content");
      if (!liveContent || !freshContent) return;
      var state = readPanelState(live);
      liveContent.replaceWith(document.importNode(freshContent, true));
      //  Sections and popovers are built by side-panels.js out of the flat
      //  markup the server sends, so the replacement needs the same
      //  treatment before its state can be put back.
      if (window.cmsRebuildDockPanel) window.cmsRebuildDockPanel(live);
      restorePanelState(live, state);
    });
  }

  //  Colour presets, the custom palette, font pairings, "apply as body
  //  font" — the panels do plenty through plain <form method="post">,
  //  which navigates, which is the very thing this file exists to avoid.
  //  Posted here instead and re-rendered in place. Only the three panels
  //  above, and never a file upload (importing a toolkit is a real
  //  navigation with a real progress bar); anything already handled by
  //  its own script has called preventDefault long before this.
  document.addEventListener("submit", function (e) {
    if (e.defaultPrevented) return;
    var form = e.target;
    if (!form || !form.closest) return;
    if (!form.closest(PANELS.map(function (id) { return "#" + id; }).join(", "))) return;
    if ((form.getAttribute("method") || "get").toLowerCase() !== "post") return;
    if ((form.getAttribute("enctype") || "") === "multipart/form-data") return;
    e.preventDefault();
    fetch(form.action, {
      method: "POST",
      credentials: "same-origin",
      headers: { "X-Cms-Refresh": "1" },
      body: new URLSearchParams(new FormData(form)),
    })
      .then(function (res) {
        if (!res.ok) throw new Error("Request failed");
        //  The server redirects to wherever its own "next" field said,
        //  which is normally this page — but not always, so follow it.
        var here = location.pathname + location.search;
        var landed = new URL(res.url, location.href);
        var there = landed.pathname + landed.search;
        return window.cmsRefreshSite(there === here ? {} : { url: there });
      })
      .catch(function () {
        //  Let the browser do it the ordinary way rather than leaving the
        //  admin looking at a panel whose button did nothing.
        form.submit();
      });
  });

  window.cmsRefreshSite = function (options) {
    var opts = options || {};
    var url = opts.url || location.href;
    return fetch(url, { credentials: "same-origin", headers: { "X-Cms-Refresh": "1" } })
      .then(function (res) {
        if (!res.ok) throw new Error("Request failed");
        return res.text();
      })
      .then(function (html) {
        var fresh = new DOMParser().parseFromString(html, "text/html");
        //  Not the page that was asked for — a login screen, an error
        //  page, a redirect somewhere else entirely. Let the browser go
        //  there properly rather than grafting half of it onto this one.
        if (!fresh.querySelector("main.site-content")) throw new Error("Not a page");

        syncThemeAssets(fresh);
        document.title = fresh.title;
        document.body.className = fresh.body.className;
        var style = fresh.body.getAttribute("style");
        if (style) document.body.setAttribute("style", style);
        else document.body.removeAttribute("style");
        syncRegions(fresh);
        syncPanels(fresh);

        if (opts.url && opts.url !== location.pathname + location.search) {
          history.pushState(null, "", opts.url);
        }
        document.dispatchEvent(new CustomEvent("cms:site-refreshed"));
        document.dispatchEvent(new CustomEvent("cms:dock-refreshed"));
        return true;
      })
      .catch(function () {
        if (opts.url) location.href = opts.url;
        else location.reload();
        return false;
      });
  };
})();
