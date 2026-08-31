/*  Showing only the questions the chosen answer actually needs.

    The form was a column of a dozen fields in no particular relation,
    and half of them did nothing depending on an answer given elsewhere:
    "how it should sound" applies only if the AI is writing, "pages" only
    if it is writing new ones. Four controls about voice sitting under
    "keep my words" are four controls doing nothing, and nothing on
    screen said so.

    REMOVED, not greyed. That is the rule this app already follows for a
    schedule's irrelevant fields, and it came from the same complaint: a
    control that is not a choice is not a choice being refused.

    Which mode needs which rows is decided in Python
    (`theme_generator.MODE_NEEDS`) and read from a JSON block, so the
    form and the run cannot disagree about it -- the same reason every
    other list in this app is passed as data rather than written twice.
*/
(function () {
  "use strict";

  var form = document.querySelector("[data-generator-form]");
  if (!form) return;

  var mode = form.querySelector("[data-generator-mode]");
  if (!mode) return;

  var NEEDS = {};
  try {
    var block = document.getElementById("cms-generator-needs");
    NEEDS = JSON.parse((block && block.textContent) || "{}") || {};
  } catch (e) {
    NEEDS = {};
  }

  function show() {
    var wanted = NEEDS[mode.value] || [];
    form.querySelectorAll("[data-needs]").forEach(function (row) {
      var needed = wanted.indexOf(row.dataset.needs) >= 0;
      row.hidden = !needed;
      //  A hidden field still submits, which is right: switching back
      //  should find what was typed, not a cleared box. What must not
      //  happen is a hidden field being REQUIRED, which would refuse a
      //  submit for a reason nobody can see.
      row.querySelectorAll("[required]").forEach(function (field) {
        field.required = needed;
      });
    });
  }

  //  ---- colours somebody set themselves ----
  var setColours = form.querySelector("[data-set-colours]");
  var pickers = form.querySelector("[data-colour-pickers]");
  if (setColours && pickers) {
    var showPickers = function () { pickers.hidden = !setColours.checked; };
    setColours.addEventListener("change", showPickers);
    showPickers();
  }

  //  ---- pictures somebody likes the look of ----
  //
  //  The colours are worked out HERE, in this browser, and sent as hex
  //  values. That is deliberate and it is the part that always works:
  //  arithmetic on pixels needs no AI provider, so an install with no
  //  model at all still gets a palette out of a screenshot.
  //
  //  The picture itself is sent only when the chosen model can look at
  //  one, and only to name what pixels cannot: the typeface feel, the
  //  corners, the depth.
  var rows = form.querySelector("[data-references]");
  var addRow = form.querySelector("[data-add-reference]");

  //  ---- reading a look out of a picture ----
  //
  //  Measured against real screenshots, and every rule here is one of
  //  those measurements:
  //
  //  NEAREST rather than smooth, because a smoothing downscale averages
  //  neighbouring pixels and invents colours that are in no part of the
  //  picture -- it turned Hacker News orange into three tints of peach.
  //
  //  Weighted by how DECIDED a colour is rather than by how much of it
  //  there is, because a brand colour is a decision and a photograph's
  //  average is not.
  //
  //  And the TOP of a page counts for more: a header, a nav bar and the
  //  first button are where a site states its colour, while the body is
  //  mostly paper. Weighting the top third double is what finds a
  //  brand colour that occupies very little of a long screenshot.
  var SIDE = 200;
  //  What a picture is shrunk to before it is SENT to a model, as
  //  against the 200px grid the colours are counted on.
  //
  //  Measured against a real vision model, on the full 1280x800
  //  screenshot this was first tried with: 943 KB of PNG came back HTTP
  //  400, and 87 KB at 1024px came back EMPTY -- no error, no words, a
  //  blank reply that reads exactly like a model with nothing to say.
  //  64 KB answered. So the ceiling is real and the failure above it is
  //  SILENT, which is the worst kind to leave to chance.
  //
  //  800px at 0.78 lands around 40 KB, and a style question does not
  //  want detail anyway: it wants the typeface's weight, the corners
  //  and whether anything casts a shadow.
  var SEND_SIDE = 800;
  //  A BYTE target, not just a quality, because quality is not a size:
  //  the same 0.78 gave 47 KB on a flat screenshot and 70 KB on a
  //  photograph, and 70 was over the line that a model answered at.
  //  What varies is the picture, so what is held fixed has to be the
  //  number that matters.
  var SEND_MAX_KB = 55;
  var SEND_QUALITIES = [0.78, 0.65, 0.5, 0.38];

  function paletteFrom(canvas) {
    var ctx = canvas.getContext("2d");
    var data;
    try {
      data = ctx.getImageData(0, 0, SIDE, SIDE).data;
    } catch (e) {
      return null;
    }
    var strong = {}, plain = {};
    for (var i = 0; i < data.length; i += 4) {
      if (data[i + 3] < 128) continue;
      var r = data[i], g = data[i + 1], b = data[i + 2];
      var row = Math.floor((i / 4) / SIDE);
      var weight = row < SIDE / 3 ? 2 : 1;
      var max = Math.max(r, g, b), min = Math.min(r, g, b);
      var sat = max ? (max - min) / max : 0;
      var key = [r, g, b].map(function (v) {
        return Math.round(v / 8) * 8;
      }).join(",");
      if (sat >= 0.22 && max >= 40 && min <= 235) {
        strong[key] = (strong[key] || 0) + sat * sat * weight;
      } else {
        //  Paper and ink: not a brand colour, but the GROUND a look sits
        //  on, and a cream page is a different look from a white one.
        plain[key] = (plain[key] || 0) + weight;
      }
    }
    return { strong: strong, plain: plain };
  }

  function distinct(buckets, howMany, apart) {
    var ranked = Object.keys(buckets).sort(function (a, b) {
      return buckets[b] - buckets[a];
    });
    var out = [];
    ranked.forEach(function (key) {
      if (out.length === howMany) return;
      var here = key.split(",").map(Number);
      var near = out.some(function (other) {
        var them = other.split(",").map(Number);
        return Math.abs(here[0] - them[0]) + Math.abs(here[1] - them[1])
             + Math.abs(here[2] - them[2]) < apart;
      });
      if (!near) out.push(key);
    });
    return out;
  }

  function hexOf(key) {
    return "#" + key.split(",").map(Number).map(function (v) {
      return Math.min(255, v).toString(16).padStart(2, "0");
    }).join("");
  }

  function small_thumb(img) {
    var side = 132;
    var box = document.createElement("canvas");
    var scale = Math.min(side / img.width, side / img.height);
    box.width = Math.max(1, Math.round(img.width * scale));
    box.height = Math.max(1, Math.round(img.height * scale));
    box.getContext("2d").drawImage(img, 0, 0, box.width, box.height);
    var shown = document.createElement("img");
    shown.className = "cms-reference-thumb";
    shown.setAttribute("data-reference-thumb", "1");
    shown.alt = "The picture you chose";
    shown.src = box.toDataURL("image/jpeg", 0.7);
    return shown;
  }

  function sample(file, into) {
    var reader = new FileReader();
    reader.onload = function () {
      var img = new Image();
      img.onload = function () {
        var canvas = document.createElement("canvas");
        canvas.width = SIDE;
        canvas.height = SIDE;
        var ctx = canvas.getContext("2d");
        ctx.imageSmoothingEnabled = false;
        ctx.drawImage(img, 0, 0, SIDE, SIDE);
        var found = paletteFrom(canvas);
        if (!found) {
          into.textContent = "That picture could not be read here.";
          into.hidden = false;
          return;
        }
        //  Three colours that differ from each other -- a gradient
        //  otherwise gives three shades of one and the palette has no
        //  secondary and no accent. Plus the ground it all sits on.
        var top = distinct(found.strong, 3, 90);
        var ground = distinct(found.plain, 1, 0);
        var row = into.parentNode;
        row.querySelectorAll("[data-sampled]").forEach(function (old) {
          old.remove();
        });
        top.concat(ground).forEach(function (key) {
          var field = document.createElement("input");
          field.type = "hidden";
          field.name = "ref_colour";
          field.value = hexOf(key);
          field.setAttribute("data-sampled", "1");
          row.appendChild(field);
        });
        //  The picture itself goes too, but ONLY when the model can
        //  look at it -- colours are arithmetic and need no provider,
        //  so with no eyes at the other end nothing about the picture
        //  leaves this browser at all.
        //
        //  Shrunk here rather than uploaded whole. That is not thrift:
        //  the file is decoded onto a canvas for the colours already,
        //  so the small copy costs one more draw, and it is the
        //  difference between a reply and a silence (see SEND_SIDE).
        if (form.getAttribute("data-send-picture") === "1") {
          var small = document.createElement("canvas");
          var scale = Math.min(1, SEND_SIDE / Math.max(img.width, img.height));
          small.width = Math.max(1, Math.round(img.width * scale));
          small.height = Math.max(1, Math.round(img.height * scale));
          small.getContext("2d").drawImage(img, 0, 0, small.width, small.height);
          var url = "";
          for (var q = 0; q < SEND_QUALITIES.length; q += 1) {
            url = small.toDataURL("image/jpeg", SEND_QUALITIES[q]);
            //  A base64 character is six bits of the file.
            if ((url.length * 3) / 4096 <= SEND_MAX_KB) break;
          }
          var carried = document.createElement("input");
          carried.type = "hidden";
          carried.name = "ref_picture";
          carried.value = url;
          carried.setAttribute("data-sampled", "1");
          row.appendChild(carried);
        }
        //  The picture itself, small. Somebody who has just chosen a
        //  file should be able to see WHICH file -- a row of swatches
        //  says a picture was read, not that it was theirs.
        var thumb = small_thumb(img);
        var already = row.querySelector("[data-reference-thumb]");
        if (already) already.remove();
        row.insertBefore(thumb, into);

        into.innerHTML = top.length
          ? "Read from this picture: " + top.concat(ground).map(function (key) {
              return "<span class=\"cms-swatch\" style=\"background:" + hexOf(key)
                   + "\" title=\"" + hexOf(key) + "\"></span>";
            }).join("")
          : "No strong colours in that picture — its ground is used instead.";
        into.hidden = false;
      };
      img.src = reader.result;
    };
    reader.readAsDataURL(file);
  }

  //  ---- saying that it is working ----
  //
  //  A run is synchronous and can take minutes: the design, then one
  //  request per page, one after another. The screen said NOTHING while
  //  that happened -- the button stayed pressable, the page sat there,
  //  and the only honest reading of it was that the click had missed.
  //  Watched on a real machine it was ten minutes of a still page.
  //
  //  The counter is the app's own (elapsed-timer.js), the same one the
  //  Media Library and the assistant use, because a third hand-rolled
  //  setInterval for "the thing is still going" is how they drift.
  var WORKING = {
    preview: ["Working out the look", "Asking your AI provider for the colours, the "
              + "typefaces and the shape of each page. Nothing is made yet."],
    make: ["Making it", "The look, then the words for each page — one request each, "
           + "one after another. Leave this open; it lands in your template list."]
  };

  function saysItIsWorking(where, button, which) {
    var said = WORKING[which];
    var note = document.createElement("p");
    note.className = "hint cms-working";
    note.setAttribute("role", "status");
    note.textContent = said[1];
    button.parentNode.insertBefore(note, button.nextSibling);

    //  The pressed button's OWN name and value, carried in a hidden
    //  field before anything is disabled.
    //
    //  A disabled control is not submitted -- so disabling the submitter
    //  inside the submit event deletes the one field that says WHICH
    //  button was pressed. "Show me the plan" arrived at the server with
    //  no `preview`, and the server did what a form with no preview
    //  means: it made the whole thing. The free look silently cost a
    //  full run, which is the exact promise this screen makes.
    if (button.name) {
      var carried = document.createElement("input");
      carried.type = "hidden";
      carried.name = button.name;
      carried.value = button.value || "1";
      where.appendChild(carried);
    }
    var label = button.textContent;
    //  Every submit goes dead, not just this one: two presses is two
    //  runs, and the second is paid for the same as the first.
    where.querySelectorAll("button[type=submit]").forEach(function (other) {
      other.disabled = true;
      other.setAttribute("aria-busy", "true");
    });
    window.cmsElapsedTimer(function (seconds) {
      button.textContent = said[0] + "… " + seconds + "s";
    });
    return label;
  }

  //  BOTH forms, and that is the whole point of doing it this way.
  //
  //  The plan is its own little form -- "Make it" and "Change
  //  something" -- sitting above the big one. Attaching this to the
  //  form the script was written around covered "Show me the plan" and
  //  missed the button that starts the run that actually takes
  //  minutes. The one press that most needs to say it is working was
  //  the one press that said nothing.
  document.querySelectorAll("form[action*='theme-generator']").forEach(function (each) {
    each.addEventListener("submit", function (event) {
      var button = event.submitter;
      if (!button || button.type !== "submit") return;
      saysItIsWorking(each, button, button.name === "preview" ? "preview" : "make");
    });
  });

  function watch(row) {
    var file = row.querySelector("[data-reference-image]");
    var said = row.querySelector("[data-reference-read]");
    if (!file || !said) return;
    file.addEventListener("change", function () {
      if (file.files && file.files[0]) sample(file.files[0], said);
    });
  }

  if (rows) {
    rows.querySelectorAll("[data-reference]").forEach(watch);
    if (addRow) {
      addRow.addEventListener("click", function () {
        var first = rows.querySelector("[data-reference]");
        if (!first) return;
        var made = first.cloneNode(true);
        made.querySelectorAll("input").forEach(function (field) { field.value = ""; });
        made.querySelectorAll("[data-sampled]").forEach(function (f) { f.remove(); });
        var said = made.querySelector("[data-reference-read]");
        if (said) { said.hidden = true; said.textContent = ""; }
        rows.appendChild(made);
        watch(made);
      });
    }
  }

  mode.addEventListener("change", show);
  show();
}());
