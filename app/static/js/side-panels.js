/*
 * Coordinates the independent side panels (AI Assistant, Tools, Colors,
 * Fonts & Shape, Theme & Layout) as a strict accordion — only one can ever
 * be open at a time:
 * - Collapsed + click a tab -> that panel opens, its tab becomes active/front.
 * - Expanded + click the active tab again -> collapses (both tabs retract).
 * - Expanded + click the inactive tab -> the clicked one opens and becomes
 *   active/front; the previously-open one actually closes (not just hidden
 *   behind it) — otherwise closing the front panel later would reveal the
 *   other one still sitting open underneath, looking like a fresh expansion.
 */
(function () {
  document.addEventListener("DOMContentLoaded", init);
  if (document.readyState !== "loading") init();

  function init() {
    const tabs = document.querySelectorAll(".cms-dock-tab-btn");
    const panels = document.querySelectorAll(".cms-dock-panel");
    if (!tabs.length || !panels.length) return;

    function setTabsOpen(open) {
      tabs.forEach((t) => t.classList.toggle("cms-open", open));
    }

    // The tabs sit fixed one above another (assistant, tools, colors,
    // style, template, top to bottom) and stay visible together whenever
    // the dock is open, overlapping slightly at their edges. Which one "wins" an
    // overlap isn't just active-vs-not — the middle tab (tools) sits
    // between the other two, so a plain "front tab gets a boost" rule
    // still left it pinched between two neighbors that tied with each
    // other. The actual rule wanted: rank by physical distance from
    // whichever tab is active (active itself always on top), so e.g.
    // selecting the top tab reads as chat > tools > palette, selecting
    // the bottom one reads as palette > tools > chat — never a tie.
    const TAB_ORDER = ["assistant", "tools", "colors", "style", "template"];

    function applyStacking(activeName) {
      const activeIndex = TAB_ORDER.indexOf(activeName);
      tabs.forEach((t) => {
        const i = TAB_ORDER.indexOf(t.dataset.panel);
        const distance = activeIndex === -1 || i === -1 ? 0 : Math.abs(i - activeIndex);
        t.style.zIndex = 10010 - distance * 2;
      });
      panels.forEach((p) => {
        const i = TAB_ORDER.indexOf(p.dataset.panel);
        const distance = activeIndex === -1 || i === -1 ? 0 : Math.abs(i - activeIndex);
        p.style.zIndex = 10010 - distance * 2;
      });
    }

    function openPanel(name) {
      // Every panel sits at the exact same position/size — in EITHER
      // orientation, since the dock moves as a whole (see applyDockPosition
      // below) — so all of them share one dock-wide "open" state (added
      // together, always). The only per-panel thing that changes on a tab
      // switch is the stacking order (see applyStacking). That makes
      // switching between tabs a pure, instant restack with no slide
      // animation, whether or not this particular panel has ever been the
      // front one before.
      panels.forEach((p) => p.classList.add("cms-open"));
      panels.forEach((p) => p.classList.toggle("cms-dock-front", p.dataset.panel === name));
      tabs.forEach((t) => t.classList.toggle("cms-dock-front", t.dataset.panel === name));
      applyStacking(name);
      setTabsOpen(true);
      localStorage.setItem("cmsDockActive", name);
      applyBottomHeight(name);
    }

    // How short the bottom bar may be for each panel. A row of tiles is
    // readable at 180px; a conversation is not — at that height the chat
    // log came to about 70px, two lines, which is not enough to see a
    // reply in. So the bar grows for the Assistant and shrinks again on
    // the way out, rather than every panel paying for the tallest one.
    const BOTTOM_MIN = { assistant: 320 };
    // The natural height, worked out the same way the stylesheet does it:
    // two rows of tiles plus the chrome around them. Read from the same
    // custom properties rather than repeated as a number here, so the two
    // cannot drift apart.
    function naturalBottomHeight() {
      const style = getComputedStyle(document.documentElement);
      const chip = parseFloat(style.getPropertyValue("--cms-tool-chip-height-bottom")) || 46;
      const chrome = parseFloat(style.getPropertyValue("--cms-dock-bottom-chrome")) || 76;
      //  Ungrouped is one row, so the bar is one row tall. The height is
      //  meant to follow what the bar holds; leaving it at two rows would
      //  leave the second one standing empty.
      const rows = localStorage.getItem("cmsDockGrouped") === "0" ? 1 : 2;
      return rows * chip + (rows - 1) * 3 + chrome;
    }
    function applyBottomHeight(name) {
      if (!panels[0] || !panels[0].classList.contains("cms-dock-bottom")) return;
      //  Nothing stores a bottom height any more — the bar is only ever
      //  as tall as what it holds (see naturalBottomHeight).
      const base = naturalBottomHeight();
      //  A height the admin dragged for themselves is a floor, never a
      //  ceiling — this only ever raises the bar, so it cannot undo it.
      const wanted = Math.max(base, BOTTOM_MIN[name] || 0);
      document.documentElement.style.setProperty("--cms-dock-bottom-height", wanted + "px");
    }

    function closeAll() {
      panels.forEach((p) => p.classList.remove("cms-open", "cms-dock-front"));
      tabs.forEach((t) => t.classList.remove("cms-dock-front"));
      setTabsOpen(false);
      localStorage.removeItem("cmsDockActive");
    }

    tabs.forEach((tab) => {
      tab.addEventListener("click", () => {
        const name = tab.dataset.panel;
        const panel = document.querySelector('.cms-dock-panel[data-panel="' + name + '"]');
        if (!panel) return;
        // "cms-open" is now shared by every panel once the dock is open (see
        // openPanel), so it can't tell active from inactive — only
        // "cms-dock-front" (the currently-on-top one) can.
        if (panel.classList.contains("cms-dock-front")) closeAll();
        else openPanel(name);
      });
    });

    document.querySelectorAll(".cms-assistant-close").forEach((btn) => {
      btn.addEventListener("click", closeAll);
    });

    // ---------- Sections as collapsible groups ----------
    //
    // A panel is written as a flat run of headings and controls, which is
    // all a tall narrow column needs. Laid along the bottom it has to read
    // as GROUPS instead — a heading beside the controls it names, then the
    // next heading — and an admin needs to be able to fold away the ones
    // they are not using, since the bar is competing with the page for
    // space.
    //
    // Both need the same thing: each heading and everything up to the next
    // heading, wrapped together. Done once, for both orientations, so the
    // DOM never changes as the dock is flipped; the side dock renders the
    // wrapper as `display: contents`, so it lays out exactly as it did
    // before. Ids and structure inside are untouched — the panels' own
    // scripts look those up and must keep finding them.
    function buildGroups(panel) {
      const content = panel.querySelector(".cms-dock-content");
      if (!content || content.dataset.grouped) return;
      content.dataset.grouped = "1";
      let group = null;
      [...content.children].forEach((kid) => {
        if (kid.classList && kid.classList.contains("cms-tpl-section-label")) {
          group = document.createElement("div");
          group.className = "cms-dock-group";
          content.insertBefore(group, kid);
          group.appendChild(kid);
          kid.classList.add("cms-dock-group-head");
          kid.setAttribute("title", "Click to hide or show these options");
          // Bound per heading, NOT to the loop's `group` variable — that
          // one is reassigned on every section, so a closure over it left
          // every heading toggling whichever group happened to be last.
          const own = group;
          kid.addEventListener("click", (e) => {
            // The heading carries a "?" help button of its own; clicking
            // that is asking what the section IS, not to fold it away.
            if (e.target.closest(".cms-panel-help")) return;
            own.classList.toggle("is-collapsed");
          });
        } else if (group) {
          group.appendChild(kid);
        }
      });
      //  A heading with nothing under it is a super-heading over the
      //  sections that follow — "Customize" above Headers/Pages/Footers.
      //  That reads fine as a heading in the tall panel, but in the bar it
      //  becomes a spine you can click and which then folds nothing away.
      //  Marked so the bar can leave it out.
      content.querySelectorAll(".cms-dock-group").forEach((g) => {
        const hasContent = [...g.children].some((k) => !k.classList.contains("cms-dock-group-head"));
        g.classList.toggle("cms-dock-group-empty", !hasContent);
      });
    }
    panels.forEach(buildGroups);

    // ---------- A way out of each popover ----------
    //
    // In the bottom bar a disclosure opens as a panel over the page, and a
    // panel that covers something needs an obvious way to dismiss it. Its
    // summary still toggles it, but that summary is a spine down at the
    // edge of the bar — not where anyone looks to close what just opened
    // in front of them.
    //
    // A real button, not a pseudo-element, because it has to be clickable.
    // Appended after the summary, which is what puts it inside the
    // ::details-content box the popover is drawn from; the CSS then pins
    // it to that box's top-right corner. Down the side the disclosure is
    // an ordinary inline fold and the button is hidden — there is nothing
    // covering anything to dismiss.
    function addPopoverCloses(panel) {
      panel.querySelectorAll(".cms-dock-content details").forEach((details) => {
        if (details.querySelector(":scope > .cms-dock-popover-close")) return;
        const close = document.createElement("button");
        close.type = "button";
        close.className = "cms-dock-popover-close";
        close.setAttribute("aria-label", "Close");
        close.title = "Close";
        close.textContent = "×";
        close.addEventListener("click", (e) => {
          e.preventDefault();
          e.stopPropagation();
          details.open = false;
        });
        details.appendChild(close);

        //  The summary's own "?" explains what the disclosure is for, but
        //  in the bar that summary is a rotated spine, where the button
        //  ends up floating outside the bar entirely — so it is hidden
        //  there. The panel has room for it, so a copy goes inside,
        //  beside the close button. A copy rather than a move: down the
        //  side the original still belongs next to the heading.
        const help = details.querySelector(":scope > summary .cms-panel-help");
        if (help && !details.querySelector(":scope > .cms-dock-popover-help")) {
          const copy = help.cloneNode(true);
          copy.classList.add("cms-dock-popover-help");
          //  Its own click must not reach the summary and toggle the
          //  disclosure shut the moment somebody asks what it does.
          copy.addEventListener("click", (e) => { e.preventDefault(); e.stopPropagation(); });
          details.appendChild(copy);
        }
      });
    }
    panels.forEach(addPopoverCloses);

    //  A panel's content can be replaced without a page load — applying a
    //  template re-renders Colours, Fonts and Template from the server
    //  (see admin/live-refresh.js), since each is a view of whichever
    //  template is active. The replacement arrives as the flat markup the
    //  server sends, so it needs the same two passes the original got.
    window.cmsRebuildDockPanel = function (panel) {
      buildGroups(panel);
      addPopoverCloses(panel);
    };

    // ---------- One disclosure at a time ----------
    //
    // Opening a second one used to leave the first open. Down the side
    // that is merely untidy; along the bottom every disclosure is a
    // popover drawn over the page at the same place, so they stacked and
    // the one underneath was unreachable — and unclosable, since its own
    // close button was behind the new one.
    //
    // `toggle` does not bubble, so this listens in the capture phase,
    // which non-bubbling events still pass through on their way down.
    document.addEventListener("toggle", (e) => {
      const opened = e.target;
      if (!opened.matches || !opened.matches(".cms-dock-panel details") || !opened.open) return;
      document.querySelectorAll(".cms-dock-panel details[open]").forEach((other) => {
        if (other !== opened) other.open = false;
      });
    }, true);

    // ---------- Help tooltips in the bottom bar ----------
    //
    // Every box a "?" sits in down here clips it: the bar's content
    // scrolls sideways, a popover scrolls down, a spine is 26px wide. And
    // `position: fixed` is no escape — a spine is rotated, and a transform
    // makes that element the containing block for fixed descendants, so
    // viewport coordinates land relative to the spine and the tooltip
    // ends up off-screen.
    //
    // So the bar borrows one bubble that lives on <body>, outside every
    // box and every transform. Hovering a "?" fills it, places it and
    // shows it. Above the button by preference — the bar is at the foot
    // of the screen, so the room is up there — and nudged sideways to
    // stay on screen.
    let helpBubble = null;
    function showHelp(button) {
      const panel = button.closest(".cms-dock-panel");
      const source = button.querySelector(".cms-panel-help-text");
      //  Down the side the tooltip is drawn in place, as it always was —
      //  nothing clips it there. Hide the borrowed bubble rather than
      //  just declining to fill it, or one left over from the bar sits on
      //  screen after the dock is moved.
      if (!panel || !panel.classList.contains("cms-dock-bottom") || !source) {
        hideHelp();
        return;
      }
      if (!helpBubble) {
        helpBubble = document.createElement("div");
        helpBubble.className = "cms-dock-help-bubble";
        helpBubble.setAttribute("role", "tooltip");
        document.body.appendChild(helpBubble);
      }
      helpBubble.textContent = source.textContent;
      helpBubble.classList.add("is-shown");
      const b = button.getBoundingClientRect();
      const t = helpBubble.getBoundingClientRect();
      const margin = 8;
      let left = b.left + b.width / 2 - t.width / 2;
      left = Math.max(margin, Math.min(left, window.innerWidth - t.width - margin));
      //  Clear of the bar, not merely above the button: anchored to the
      //  button it still lay across the row it came from, covering the
      //  headings either side of it.
      const barTop = panel.getBoundingClientRect().top;
      let top = barTop - t.height - margin;
      if (top < margin) top = Math.max(margin, b.top - t.height - margin);
      helpBubble.style.left = Math.round(left) + "px";
      helpBubble.style.top = Math.round(top) + "px";
    }
    function hideHelp() {
      if (helpBubble) helpBubble.classList.remove("is-shown");
    }
    document.addEventListener("mouseover", (e) => {
      const button = e.target.closest && e.target.closest(".cms-panel-help");
      if (button) showHelp(button);
    });
    document.addEventListener("mouseout", (e) => {
      const button = e.target.closest && e.target.closest(".cms-panel-help");
      if (button && !button.contains(e.relatedTarget)) hideHelp();
    });
    document.addEventListener("focusin", (e) => {
      const button = e.target.closest && e.target.closest(".cms-panel-help");
      if (button) showHelp(button); else hideHelp();
    });

    // ---------- Grouped, or one flat row ----------
    //
    // A dock-wide choice, like the orientation: every panel is the same
    // shape in the bottom bar — sections behind foldable headings — so
    // "just show me one row" is one question asked once rather than a
    // separate switch per tab. Tools rebuilds its own grid when this
    // changes (tools-panel.js listens to the same inputs); the other
    // panels only need their groups to stop being groups, which is CSS.
    const groupedInputs = Array.from(document.querySelectorAll(".cms-grouped-input"));
    function applyGrouped(on) {
      panels.forEach((p) => p.classList.toggle("cms-dock-ungrouped", !on));
      groupedInputs.forEach((i) => { i.checked = on; });
    }
    applyGrouped(localStorage.getItem("cmsDockGrouped") !== "0");
    groupedInputs.forEach((input) => {
      input.addEventListener("change", () => {
        applyGrouped(input.checked);
        localStorage.setItem("cmsDockGrouped", input.checked ? "1" : "0");
        //  One row or two changes how tall the bar needs to be.
        const front = document.querySelector(".cms-dock-panel.cms-dock-front");
        if (front) applyBottomHeight(front.dataset.panel);
      });
    });

    // ---------- Orientation: down the side, or along the bottom ----------
    //
    // A whole-dock property, not a per-panel one: every panel and every tab
    // carries the class together. Any panel's header toggle flips all of
    // them, so an admin who moved the dock while in Fonts finds Tools and
    // the Assistant where they left them, and the accordion's
    // one-rect-for-every-panel assumption keeps holding either way.
    function applyDockPosition(position) {
      const bottom = position === "bottom";
      panels.forEach((p) => p.classList.toggle("cms-dock-bottom", bottom));
      tabs.forEach((t) => t.classList.toggle("cms-dock-bottom", bottom));
      document.querySelectorAll(".cms-dock-position-toggle").forEach((btn) => {
        const icon = btn.querySelector(".cms-dock-position-icon");
        const label = btn.querySelector(".cms-dock-position-label");
        // Labelled by the action a click performs, not the state it is in.
        if (icon) icon.textContent = bottom ? "⬒" : "⬓";
        if (label) label.textContent = bottom ? "Side" : "Bottom";
        btn.title = bottom
          ? "Move these panels back to the side of the screen"
          : "Move these panels to the bottom of the screen — handy for editing on a phone";
      });
    }

    // A 220px-plus side panel is most of a phone's screen width — the whole
    // reason the bottom bar exists — so a small screen gets it without
    // making every admin discover and click the toggle once per device.
    // Only while nothing has been explicitly chosen: a real click below
    // wins from then on, at any screen size.
    const mobileQuery = window.matchMedia("(max-width: 700px)");
    const currentPosition = () =>
      localStorage.getItem("cmsDockPosition") || (mobileQuery.matches ? "bottom" : "side");

    //  The panels are rendered closed and side-docked, and the real
    //  state is only known here, one script later. Applying it is a
    //  change of transform, which the CSS transition would happily
    //  animate — so on every single page load the bar slid in from the
    //  right-hand edge on its way to the bottom of the screen, as if it
    //  had just been opened. It had not: it was already open before the
    //  page was replaced. Suppressed for exactly as long as it takes to
    //  put the saved state back, and the layout is read once in between
    //  so the browser resolves both changes together rather than
    //  transitioning from one to the other.
    document.documentElement.classList.add("cms-dock-restoring");
    applyDockPosition(currentPosition());
    mobileQuery.addEventListener("change", () => {
      if (!localStorage.getItem("cmsDockPosition")) applyDockPosition(currentPosition());
    });
    document.querySelectorAll(".cms-dock-position-toggle").forEach((btn) => {
      btn.addEventListener("click", () => {
        const next = panels[0].classList.contains("cms-dock-bottom") ? "side" : "bottom";
        applyDockPosition(next);
        localStorage.setItem("cmsDockPosition", next);
        // Moving to the bottom has to pick up the front panel's own
        // minimum height, or the Assistant lands in a 180px bar.
        const front = document.querySelector(".cms-dock-panel.cms-dock-front");
        if (front) applyBottomHeight(front.dataset.panel);
      });
    });

    // The tool search sits in every panel's header (see
    // dock_tool_search.html), so typing in it from Colours or Fonts has to
    // be able to bring the Tools panel forward. tools-panel.js owns the
    // filtering; this is the one thing it cannot do for itself.
    window.cmsOpenDockPanel = openPanel;

    const savedActive = localStorage.getItem("cmsDockActive");
    if (savedActive && document.querySelector('.cms-dock-panel[data-panel="' + savedActive + '"]')) {
      openPanel(savedActive);
    }
    void document.body.offsetHeight;
    document.documentElement.classList.remove("cms-dock-restoring");

    // ---------- Resize (drag the top-left corner handle) ----------
    // Width and height are CSS custom properties on the root, so every
    // panel/tab reads the same size (see cms-sidepanel.css) — resizing
    // while any panel is open resizes all of them together, and the
    // choice persists across reloads via localStorage.
    const root = document.documentElement;
    const savedWidth = localStorage.getItem("cmsDockWidth");
    const savedHeight = localStorage.getItem("cmsDockHeight");
    if (savedWidth) root.style.setProperty("--cms-dock-width", savedWidth);
    if (savedHeight) root.style.setProperty("--cms-dock-height", savedHeight);

    function startResize(handle, e, { resizeWidth, resizeHeight }) {
      e.preventDefault();
      const panel = handle.closest(".cms-dock-panel");
      const startX = e.clientX;
      const startY = e.clientY;
      const startWidth = panel.getBoundingClientRect().width;
      const startHeight = panel.getBoundingClientRect().height;
      handle.setPointerCapture(e.pointerId);
      root.classList.add("cms-dock-resizing");

      function onMove(ev) {
        // Panel is pinned to the right edge and to top:0. Dragging left
        // (negative deltaX) widens it; dragging down (positive deltaY)
        // grows it — both are just the negated/direct deltas against the
        // size at drag-start, clamped to the same min/max the CSS itself
        // enforces (min-width/min-height there, max-width/max-height here)
        // so the drag can't produce a size the layout would just re-clamp
        // anyway.
        if (resizeWidth) {
          const newWidth = Math.max(220, Math.min(window.innerWidth * 0.9, startWidth - (ev.clientX - startX)));
          root.style.setProperty("--cms-dock-width", newWidth + "px");
        }
        if (resizeHeight) {
          const newHeight = Math.max(240, Math.min(window.innerHeight, startHeight + (ev.clientY - startY)));
          root.style.setProperty("--cms-dock-height", newHeight + "px");
        }
      }
      function onUp(ev) {
        handle.releasePointerCapture(e.pointerId);
        root.classList.remove("cms-dock-resizing");
        document.removeEventListener("pointermove", onMove);
        document.removeEventListener("pointerup", onUp);
        localStorage.setItem("cmsDockWidth", getComputedStyle(root).getPropertyValue("--cms-dock-width").trim());
        localStorage.setItem("cmsDockHeight", getComputedStyle(root).getPropertyValue("--cms-dock-height").trim());
      }
      document.addEventListener("pointermove", onMove);
      document.addEventListener("pointerup", onUp);
    }

    // Corner handle: both width and height, diagonal drag.
    document.querySelectorAll(".cms-dock-resize-handle").forEach((handle) => {
      handle.addEventListener("pointerdown", (e) => startResize(handle, e, { resizeWidth: true, resizeHeight: true }));
    });
    // Full left-edge strip: width only, grabbable anywhere down the side.
    document.querySelectorAll(".cms-dock-resize-edge").forEach((handle) => {
      handle.addEventListener("pointerdown", (e) => startResize(handle, e, { resizeWidth: true, resizeHeight: false }));
    });
  }
})();
