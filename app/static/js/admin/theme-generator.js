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
