// Blocks that wire up the page's own markup register themselves here
// instead of running once. The editor can replace the site's regions in
// place, with no page load (see admin/live-refresh.js — applying a
// template does exactly that), and the replacement markup needs the same
// wiring the original had.
//
// A registered block must therefore be safe to run more than once: it may
// bind to elements it finds, but never to `document` or `window`, since
// re-running that would double-fire it. The lightbox block below is not
// registered for precisely that reason — it is entirely delegated off
// `document`, so it keeps working across a swap without being touched.
var cmsSiteSetups = [];
function cmsSiteSetup(fn) {
  cmsSiteSetups.push(fn);
  fn();
}
document.addEventListener("cms:site-refreshed", function () {
  cmsSiteSetups.forEach(function (fn) { fn(); });
});

cmsSiteSetup(function () {
  "use strict";
  // Menu tool: "highlight current page" has to be resolved client-side
  // (or per-request) since the exact same saved menu HTML is reused on
  // every page of the site — there's no single "current page" at save
  // time. Compares each link's pathname against the page actually being
  // viewed and marks the match.
  document.querySelectorAll('nav.cms-menu[data-highlight-current="1"]').forEach(function (nav) {
    var here = location.pathname.replace(/\/+$/, "") || "/";
    nav.querySelectorAll("a[href]").forEach(function (a) {
      var linkPath = a.pathname.replace(/\/+$/, "") || "/";
      if (linkPath === here) a.classList.add("cms-menu-current");
    });
  });

  // Mobile hamburger toggle for the Menu tool — every menu gets one (see
  // site-base.css, hidden until the mobile breakpoint), so this just wires
  // the click regardless of style/plain/buttons/dropdown.
  document.querySelectorAll(".cms-menu-toggle").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var nav = btn.closest(".cms-menu");
      var open = nav.classList.toggle("cms-menu-open");
      btn.setAttribute("aria-expanded", open ? "true" : "false");
    });
  });
  // Dropdown submenus open on hover on desktop, which doesn't exist on
  // touch — tapping the parent link toggles its submenu open instead once
  // the mobile layout is active (see the max-width:700px block in CSS).
  document.querySelectorAll(".cms-menu-dropdown .cms-menu-has-submenu > a").forEach(function (a) {
    a.addEventListener("click", function (e) {
      if (window.innerWidth > 700) return;
      var li = a.closest(".cms-menu-has-submenu");
      if (!li.classList.contains("cms-submenu-open")) {
        e.preventDefault();
        li.classList.add("cms-submenu-open");
      }
    });
  });
  // "minimal" nav layout (see site-base.css .nav-minimal): the site-wide
  // nav itself starts hidden and opens as a dropdown panel from the
  // toggle button — same idea as the Menu tool's own mobile toggle above,
  // just for the structural site header instead of one Menu tool.
  document.querySelectorAll(".cms-nav-toggle").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var zone = btn.closest(".site-header")?.querySelector(".site-header-zone");
      if (!zone) return;
      var open = zone.classList.toggle("cms-nav-open");
      btn.setAttribute("aria-expanded", open ? "true" : "false");
    });
  });
});

(function () {
  "use strict";
  // Always loaded (for every visitor, not just the admin) — powers the
  // video gallery's popup player so clicking a thumbnail plays right here
  // on the site instead of leaving to YouTube.
  var modal = document.getElementById("cms-lightbox");
  var frame = document.getElementById("cms-lightbox-frame");
  var image = document.getElementById("cms-lightbox-img");
  var video = document.getElementById("cms-lightbox-video");
  if (!modal || !frame) return;

  // One overlay, two jobs: a video player for the Video Gallery, and an
  // enlarged picture for an Image Accordion set to "click to enlarge".
  // Whichever opens hides the other, so the two can never stack up (a
  // still-loaded iframe behind a photo would keep playing audio).
  function hideAllModes() {
    if (image) { image.hidden = true; image.src = ""; }
    if (video) { video.hidden = true; video.pause(); video.removeAttribute("src"); video.load(); }
    frame.hidden = true;
    frame.src = "";
  }
  // An uploaded clip plays in the same popup as a YouTube one — the
  // gallery no longer forces a site to publish its footage to a third
  // party just to show it.
  function openUploadedVideo(src) {
    if (!video) return;
    hideAllModes();
    video.src = src;
    video.hidden = false;
    modal.hidden = false;
    video.play().catch(function () {});
  }
  function openVideo(youtubeId) {
    if (image) image.hidden = true;
    if (video) { video.hidden = true; video.pause(); video.removeAttribute("src"); video.load(); }
    frame.hidden = false;
    frame.src = "https://www.youtube-nocookie.com/embed/" + youtubeId + "?autoplay=1";
    modal.hidden = false;
  }
  function openImage(url, alt) {
    if (!image) return;
    frame.hidden = true;
    frame.src = "";
    if (video) { video.hidden = true; video.pause(); video.removeAttribute("src"); video.load(); }
    image.src = url;
    image.alt = alt || "";
    image.hidden = false;
    modal.hidden = false;
  }
  function closeLightbox() {
    modal.hidden = true;
    hideAllModes();
  }

  // The panel's picture is a background-image, so the URL has to come back
  // out of the inline style rather than off an <img src>.
  function panelImageUrl(panel) {
    var match = /url\(["']?(.*?)["']?\)/.exec(panel.style.backgroundImage || "");
    return match ? match[1] : "";
  }
  function enlargeablePanel(target) {
    var panel = target.closest(".cms-accordion-lightbox .cms-accordion-panel");
    return panel && panelImageUrl(panel) ? panel : null;
  }

  document.addEventListener("click", function (e) {
    // While editing, clicking a thumbnail or panel means "configure this
    // tool" (it opens the tool's own panel) — opening a player or a photo
    // over the top of that would just be in the way.
    var editing = document.body.classList.contains("cms-editing");
    var thumb = e.target.closest("[data-youtube-id]");
    if (thumb && !editing) {
      e.preventDefault();
      openVideo(thumb.dataset.youtubeId);
      return;
    }
    var uploaded = e.target.closest("[data-video-src]");
    if (uploaded && !editing) {
      e.preventDefault();
      openUploadedVideo(uploaded.dataset.videoSrc);
      return;
    }
    var panel = editing ? null : enlargeablePanel(e.target);
    if (panel) {
      e.preventDefault();
      var caption = panel.querySelector(".cms-accordion-caption");
      openImage(panelImageUrl(panel), caption ? caption.textContent : "");
      return;
    }
    if (e.target === modal || e.target.closest(".cms-lightbox-close")) {
      closeLightbox();
    }
  });

  // Panels already carry tabindex for the hover-expand display's keyboard
  // support, so they are focusable — which makes Enter/Space the expected
  // way to open one without a mouse.
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !modal.hidden) {
      closeLightbox();
      return;
    }
    if (e.key !== "Enter" && e.key !== " ") return;
    if (document.body.classList.contains("cms-editing")) return;
    var panel = enlargeablePanel(e.target);
    if (panel) {
      e.preventDefault();
      var caption = panel.querySelector(".cms-accordion-caption");
      openImage(panelImageUrl(panel), caption ? caption.textContent : "");
    }
  });
})();

cmsSiteSetup(function () {
  "use strict";
  // Table (Data): wraps every table in a scrollable div at runtime rather
  // than a CSS-only trick on the table itself (display:block breaks
  // header/body column alignment — see site-base.css) — a table wider
  // than its column/viewport scrolls in place instead of blowing out the
  // whole page's width on mobile. Skips a table inside a contenteditable
  // region (edit mode) — that wrapper would otherwise get captured into
  // the saved HTML the next time that field is saved, permanently baking
  // a runtime-only element into stored content.
  // Every table style, not just the default one: the tool's style control
  // swaps cms-table for cms-table-striped/-colored/-plain, so matching only
  // "table.cms-table" left three of the four styles with no mobile
  // scroll wrapper at all.
  var TABLE_SELECTOR = "table.cms-table, table.cms-table-striped, table.cms-table-colored, table.cms-table-plain";
  document.querySelectorAll(TABLE_SELECTOR).forEach(function (table) {
    if (table.parentElement.classList.contains("cms-table-scroll")) return;
    if (table.closest('[contenteditable="true"]')) return;
    var wrap = document.createElement("div");
    wrap.className = "cms-table-scroll";
    table.parentNode.insertBefore(wrap, table);
    wrap.appendChild(table);
  });
});

cmsSiteSetup(function () {
  "use strict";
  // Image Accordion, Carousel display: give the snap track prev/next
  // buttons. Injected at runtime rather than saved into the section's
  // content — the same reasoning as the mobile table wrapper below: the
  // stored markup stays identical for all three displays, so switching
  // display can never leave stray controls behind in saved content.
  // Swiping already works without this (it is a real scroll container);
  // these are for pointer users, who have nothing to swipe with.
  document.querySelectorAll(".cms-accordion-style-carousel").forEach(function (track) {
    if (track.parentElement.classList.contains("cms-accordion-carousel-wrap")) return;
    var wrap = document.createElement("div");
    wrap.className = "cms-accordion-carousel-wrap";
    track.parentNode.insertBefore(wrap, track);
    wrap.appendChild(track);

    function button(kind, label, glyph) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "cms-accordion-carousel-btn cms-accordion-carousel-btn-" + kind;
      b.setAttribute("aria-label", label);
      b.textContent = glyph;
      wrap.appendChild(b);
      return b;
    }
    var prev = button("prev", "Previous image", "‹");
    var next = button("next", "Next image", "›");

    function step() {
      var panel = track.querySelector(".cms-accordion-panel");
      return panel ? panel.getBoundingClientRect().width + 12 : track.clientWidth;
    }
    function sync() {
      prev.disabled = track.scrollLeft <= 1;
      next.disabled = track.scrollLeft >= track.scrollWidth - track.clientWidth - 1;
    }
    prev.addEventListener("click", function () { track.scrollLeft -= step(); });
    next.addEventListener("click", function () { track.scrollLeft += step(); });
    track.addEventListener("scroll", sync);
    window.addEventListener("resize", sync);
    sync();
  });
});

cmsSiteSetup(function () {
  "use strict";
  // The Search tool.
  //
  // A dropped-in control rather than a behaviour belonging to one kind of
  // page: it filters whatever on the page has said it is searchable, which
  // today means the questions written by FAQ Content and the ones shown by
  // FAQ Reader. A page with none simply has nothing to filter.
  //
  // Runs for visitors, not only while editing — this is how the published
  // page is used.
  var tools = document.querySelectorAll("[data-search-tool]");
  if (!tools.length) return;

  function searchable() {
    return document.querySelectorAll(".cms-faq-item");
  }

  function textOf(el) {
    return (el.textContent || "").toLowerCase();
  }

  tools.forEach(function (tool) {
    var input = tool.querySelector("input");
    var count = tool.querySelector(".cms-search-count");
    var showCount = tool.dataset.showCount === "1";

    function filter() {
      var term = (input.value || "").trim().toLowerCase();
      var items = searchable();
      var shown = 0;
      var visible = {};
      items.forEach(function (item) {
        // Answers count as well as questions: people remember a word from
        // the answer at least as often as the question it belonged to.
        var hit = !term || textOf(item).indexOf(term) !== -1;
        item.hidden = !hit;
        if (hit) {
          shown++;
          visible[item.id] = true;
        }
      });
      // Any contents list on the page follows the questions rather than
      // being searched in its own right — matching its own text hid the
      // line for a question that was still shown, whenever the word
      // appeared only in that question's answer.
      document.querySelectorAll(".cms-faq-contents li").forEach(function (li) {
        var link = li.querySelector("[data-faq-jump]");
        li.hidden = !!term && !(link && visible["faq-" + link.dataset.faqJump]);
      });
      if (count) {
        if (!showCount || !term) {
          count.hidden = true;
        } else {
          count.hidden = false;
          count.textContent = shown === 0
            ? "Nothing matches that. Try a shorter word."
            : shown === 1 ? "1 question matches" : shown + " questions match";
        }
      }
    }

    input.addEventListener("input", filter);
    // Escape clears, which is what a search field's own clear button does
    // and what people try first.
    input.addEventListener("keydown", function (e) {
      if (e.key === "Escape") {
        input.value = "";
        filter();
      }
    });
  });
});

cmsSiteSetup(function () {
  "use strict";
  // Contents links open the question they name, rather than scrolling to a
  // closed row that shows no answer. Separate from the Search tool: a
  // contents list is the FAQ Reader's own display option and works whether
  // or not a search box was dropped anywhere near it.
  document.querySelectorAll("[data-faq-jump]").forEach(function (link) {
    link.addEventListener("click", function (e) {
      var target = document.getElementById("faq-" + link.dataset.faqJump);
      if (!target) return;
      e.preventDefault();
      target.open = true;
      target.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  });

  if (location.hash.indexOf("#faq-") === 0) {
    var landed = document.getElementById(location.hash.slice(1));
    if (landed) landed.open = true;
  }
});


cmsSiteSetup(function () {
  "use strict";
  // The Email sign-up answers where it was asked.
  //
  // It used to post normally: the whole page was thrown away, rebuilt,
  // and scrolled back to the top, with the answer as a line up there. On
  // a sign-up block near the foot of a long page that is a reload, a jump
  // away from what you were reading, and no visible sign that anything
  // happened at all — the one message somebody MUST see is "go and look
  // in your inbox", and it was the one message they were least likely to.
  //
  // So the form posts itself and writes the reply into its own box. Every
  // check still happens on the server, which still answers a plain form
  // post with a redirect, so a browser with no script behaves exactly as
  // it did before. The wording comes from the server either way
  // (public.py's SIGNUP_MESSAGES) rather than being written out twice.
  document.querySelectorAll("form.cms-newsletter-form").forEach(function (form) {
    if (form.dataset.cmsWired === "1") return;   // survives a region swap
    form.dataset.cmsWired = "1";
    form.addEventListener("submit", function (e) {
      //  Not while the page is being edited: the editor owns the block
      //  then, and a stray sign-up from the person writing the page is
      //  not what the button is for.
      if (document.body.classList.contains("cms-editing")) return;
      e.preventDefault();
      var note = form.querySelector("[data-subscribe-note]");
      if (!note) {
        //  Blocks saved before this note existed still get an answer.
        note = document.createElement("p");
        note.className = "cms-subscribe-note";
        note.setAttribute("role", "status");
        note.setAttribute("data-subscribe-note", "");
        form.appendChild(note);
      }
      var button = form.querySelector("button[type=submit]");
      if (button) button.disabled = true;
      note.hidden = false;
      note.classList.remove("is-bad");
      note.textContent = "One moment…";
      fetch(form.action, {
        method: "POST",
        body: new FormData(form),
        //  How the server knows to answer in words rather than with a
        //  redirect. Same origin, so the CSRF check sees its Origin
        //  header exactly as it does for an ordinary post.
        headers: { "X-Requested-With": "cms-subscribe" },
        credentials: "same-origin",
      }).then(function (r) {
        return r.json();
      }).then(function (answer) {
        note.textContent = answer.message;
        note.classList.toggle("is-bad", !answer.ok);
        if (answer.ok) form.reset();
      }).catch(function () {
        note.textContent = "That didn't go through — check your connection and try again.";
        note.classList.add("is-bad");
      }).then(function () {
        if (button) button.disabled = false;
      });
    });
  });
});


cmsSiteSetup(function () {
  "use strict";
  // Cover flow: how far each panel is from the middle of the strip.
  //
  // CSS cannot ask that question -- it has no notion of "the centre of my
  // scroll container" -- so it is answered here as one number per panel,
  // -1 at the left edge through 0 in the middle to 1 at the right, and
  // every angle, scale and fade in site-base.css is written against it.
  // Nothing about the LOOK lives here; move the numbers in the
  // stylesheet and this keeps feeding it.
  document.querySelectorAll(".cms-accordion-style-coverflow").forEach(function (track) {
    if (track.dataset.cmsFlowWired === "1") return;
    track.dataset.cmsFlowWired = "1";
    var panels = [].slice.call(track.querySelectorAll(".cms-accordion-panel"));

    function place() {
      var box = track.getBoundingClientRect();
      var middle = box.left + box.width / 2;
      var reach = box.width / 2 || 1;
      panels.forEach(function (panel) {
        var rect = panel.getBoundingClientRect();
        var offset = (rect.left + rect.width / 2 - middle) / reach;
        panel.style.setProperty("--cms-flow", Math.max(-1, Math.min(1, offset)).toFixed(3));
      });
    }
    //  On scroll, on resize, and once now. requestAnimationFrame rather
    //  than the raw scroll event: a snap track fires a great many of
    //  those and each one reads geometry back.
    var waiting = false;
    function schedule() {
      if (waiting) return;
      waiting = true;
      requestAnimationFrame(function () { waiting = false; place(); });
    }
    track.addEventListener("scroll", schedule);
    window.addEventListener("resize", schedule);
    place();
    //  A picture that has not loaded yet has no height, so the first
    //  reading can be wrong; take it again when they arrive.
    window.addEventListener("load", place);

    //  The same two arrows the carousel gets, for a mouse with no wheel
    //  and for a keyboard. Injected rather than saved into the section,
    //  so switching display leaves nothing behind.
    if (!track.parentElement.classList.contains("cms-accordion-carousel-wrap")) {
      var wrap = document.createElement("div");
      wrap.className = "cms-accordion-carousel-wrap";
      track.parentNode.insertBefore(wrap, track);
      wrap.appendChild(track);
      [["prev", "Previous image", "\u2039", -1], ["next", "Next image", "\u203a", 1]]
        .forEach(function (spec) {
          var b = document.createElement("button");
          b.type = "button";
          b.className = "cms-accordion-carousel-btn cms-accordion-carousel-btn-" + spec[0];
          b.setAttribute("aria-label", spec[1]);
          b.textContent = spec[2];
          b.addEventListener("click", function () {
            var panel = track.querySelector(".cms-accordion-panel");
            track.scrollLeft += spec[3] * (panel ? panel.getBoundingClientRect().width : track.clientWidth);
          });
          wrap.appendChild(b);
        });
    }
  });

  // Deck: which card is on top.
  //
  // The pile is an order, and clicking sends the front card to the back.
  // Kept as a number per panel (--cms-deck: 0 is the front) rather than
  // by reordering the DOM, so the markup saved in the section is never
  // touched by looking at it -- the same rule the carousel's arrows
  // follow.
  document.querySelectorAll(".cms-accordion-style-deck").forEach(function (deck) {
    if (deck.dataset.cmsDeckWired === "1") return;
    deck.dataset.cmsDeckWired = "1";
    var panels = [].slice.call(deck.querySelectorAll(".cms-accordion-panel"));
    if (!panels.length) return;
    var order = panels.map(function (_, i) { return i; });

    function paint() {
      order.forEach(function (panelIndex, place) {
        panels[panelIndex].style.setProperty("--cms-deck", place);
        //  A class as well as the number: the stylesheet asks "is this
        //  the front one" and a class answers that without depending on
        //  how a browser writes a custom property back out.
        panels[panelIndex].classList.toggle("cms-accordion-front", place === 0);
        //  Only the front card is in the tab order and readable to a
        //  screen reader; the ones behind it are decoration until they
        //  come round.
        panels[panelIndex].setAttribute("aria-hidden", place === 0 ? "false" : "true");
        panels[panelIndex].tabIndex = place === 0 ? 0 : -1;
      });
    }
    function advance() {
      order.push(order.shift());
      paint();
    }
    deck.addEventListener("click", function (e) {
      //  Not while the page is being edited: a click there means "select
      //  this tool", and the lightbox has the same rule.
      if (document.body.classList.contains("cms-editing")) return;
      if (e.target.closest(".cms-accordion-panel")) advance();
    });
    deck.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") {
        if (document.body.classList.contains("cms-editing")) return;
        e.preventDefault();
        advance();
      }
    });
    //  Said out loud, because a pile of photographs does not obviously
    //  invite a click. Added here rather than saved into the section for
    //  the same reason as the arrows.
    if (!deck.parentElement.querySelector(".cms-accordion-deck-hint")) {
      var hint = document.createElement("p");
      hint.className = "cms-accordion-deck-hint";
      hint.textContent = panels.length > 1 ? "Click to see the next one" : "";
      deck.appendChild(hint);
    }
    paint();
  });
});
