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

  mode.addEventListener("change", show);
  show();
}());
