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

  //  ---- sites and pictures somebody likes ----
  //
  //  A LINK is read by the server, from the page's own CSS, with no AI
  //  involved. A PICTURE has nothing to parse, and reading what is in a
  //  photograph needs a provider that can see -- which not every one
  //  can. So its colours are sampled HERE, in the browser, and only the
  //  hex values are sent. The picture is never uploaded.
  var rows = form.querySelector("[data-references]");
  var addRow = form.querySelector("[data-add-reference]");

  function sample(file, into) {
    var reader = new FileReader();
    reader.onload = function () {
      var img = new Image();
      img.onload = function () {
        //  Downscaled first: a phone photograph is millions of pixels
        //  and the answer is the same from a few thousand.
        //
        //  NEAREST, not smooth. A smoothing downscale averages
        //  neighbouring pixels and invents colours that are in no part
        //  of the picture -- measured against real screenshots it turned
        //  Hacker News orange into three tints of peach and gov.uk into
        //  three blues. Nearest keeps colours that are actually there.
        var side = 160;
        var canvas = document.createElement("canvas");
        canvas.width = side;
        canvas.height = side;
        var ctx = canvas.getContext("2d");
        ctx.imageSmoothingEnabled = false;
        ctx.drawImage(img, 0, 0, side, side);
        var data;
        try {
          data = ctx.getImageData(0, 0, side, side).data;
        } catch (e) {
          into.textContent = "That picture could not be read here.";
          into.hidden = false;
          return;
        }
        var buckets = {};
        for (var i = 0; i < data.length; i += 4) {
          if (data[i + 3] < 128) continue;
          var r = data[i], g = data[i + 1], b = data[i + 2];
          var max = Math.max(r, g, b), min = Math.min(r, g, b);
          var sat = max ? (max - min) / max : 0;
          //  Paper, ink and flat greys are in every picture, so they say
          //  nothing about this one.
          if (sat < 0.25 || max < 40 || min > 235) continue;
          var key = [r, g, b].map(function (v) {
            return Math.round(v / 8) * 8;
          }).join(",");
          //  Weighted by how DECIDED the colour is, not merely how much
          //  of it there is: a big pale wash should not beat a small
          //  strong mark, and a brand colour is a decision while a
          //  photograph's average is not.
          buckets[key] = (buckets[key] || 0) + sat * sat;
        }
        //  Three colours that are actually different from each other.
        //  Without this, a gradient gives three shades of one colour and
        //  the palette has no secondary and no accent.
        var ranked = Object.keys(buckets).sort(function (a, b) {
          return buckets[b] - buckets[a];
        });
        var top = [];
        ranked.forEach(function (key) {
          if (top.length === 3) return;
          var here = key.split(",").map(Number);
          var near = top.some(function (other) {
            var them = other.split(",").map(Number);
            return Math.abs(here[0] - them[0]) + Math.abs(here[1] - them[1])
                 + Math.abs(here[2] - them[2]) < 90;
          });
          if (!near) top.push(key);
        });
        into.parentNode.querySelectorAll("[data-sampled]").forEach(function (old) {
          old.remove();
        });
        top.forEach(function (key) {
          var parts = key.split(",").map(Number);
          var hex = "#" + parts.map(function (v) {
            return Math.min(255, v).toString(16).padStart(2, "0");
          }).join("");
          var field = document.createElement("input");
          field.type = "hidden";
          field.name = "ref_colour";
          field.value = hex;
          field.setAttribute("data-sampled", "1");
          into.parentNode.appendChild(field);
        });
        into.innerHTML = top.length
          ? "Read " + top.length + " colour" + (top.length === 1 ? "" : "s")
            + " from this picture: " + top.map(function (key) {
                var parts = key.split(",").map(Number);
                var hex = "#" + parts.map(function (v) {
                  return Math.min(255, v).toString(16).padStart(2, "0");
                }).join("");
                return "<span class=\"cms-swatch\" style=\"background:" + hex
                     + "\" title=\"" + hex + "\"></span>";
              }).join("")
          : "No strong colours in that picture.";
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
