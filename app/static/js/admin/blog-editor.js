/*  The blog post writing tool.

    Almost everything on it is already shared: the rich-text toolbar is
    the one this app has, the picture button is the Media Library
    chooser, and choosing when to publish is admin/schedule-picker.js --
    the same control, reading the same dates, as the newsletter editor.

    What is left is this file, and it is small on purpose. If it starts
    growing a second copy of something the newsletter editor does, that
    is the signal the two want one shared file, not two similar ones.
*/
(function () {
  var form = document.getElementById("cms-post-tool");
  if (!form) return;

  //  Choosing when, from the schedules that have been named. Its own
  //  dates block, because this screen carries the tool AND the list of
  //  schedules, and two elements with one id is a page where the second
  //  one is never read.
  if (window.cmsSchedulePicker) {
    window.cmsSchedulePicker(form, "cms-post-schedule-dates");
  }

  //  The clock the "a time I choose" box was typed on. Without it a time
  //  is read as UTC, which is an hour or two out for most of the world
  //  and wrong in a way nobody notices until it publishes at the wrong
  //  time of day.
  //
  //  RAW, not negated. `scheduling.to_utc` says it plainly --
  //  "getTimezoneOffset() is minutes to ADD to local to reach UTC" --
  //  and this file negated it while admin/local-time.js, which fills the
  //  same field on the schedules form, did not. Two files writing one
  //  field with opposite signs: a post set for 14:00 in Zurich in summer
  //  was booked for 12:00 UTC instead of 16:00, four hours early, and
  //  nothing said so. Found by a checker asserting the two agree.
  var offset = form.querySelector("[data-tz-offset]");
  if (offset) offset.value = String(new Date().getTimezoneOffset());

  //  Starting from a template.
  //
  //  A layout is a starting ARRANGEMENT, not a kind: it lays out
  //  headings and paragraphs to write over, and nothing afterwards asks
  //  which one a post came from.
  //
  //  It asks before replacing work, and asks only when there IS work.
  //  "Does the box contain words" is the obvious test and it is wrong --
  //  a template lays out words of its own, so a post that has only ever
  //  had a template applied would answer yes and every later change
  //  would ask to replace nothing. What is compared is whether what is
  //  there is still one of the templates.
  var layoutPick = form.querySelector("[data-post-layout]");
  var LAYOUTS = {};
  try {
    var block = document.getElementById("cms-post-layouts");
    LAYOUTS = JSON.parse((block && block.textContent) || "{}") || {};
  } catch (e) {
    LAYOUTS = {};
  }

  function writtenIn() {
    var box = form.querySelector(".cms-richtext [contenteditable]")
           || form.querySelector("#post-content");
    return box;
  }

  //  GAPS is built rather than typed. An escape written into this file
  //  has been eaten in transit twice now, and what came out was a real
  //  tab and a real newline inside a regular expression -- which is a
  //  syntax error, and an invisible one.
  var GAPS = new RegExp('[' + String.fromCharCode(32, 9, 10, 13) + ']+', 'g');

  function squeezed(html) {
    return (html || '').replace(GAPS, ' ').trim();
  }

  function isUntouched(html) {
    var now = squeezed(html);
    if (!now) return true;
    return Object.keys(LAYOUTS).some(function (key) {
      return squeezed(LAYOUTS[key]) === now;
    });
  }

  if (layoutPick) {
    layoutPick.addEventListener("change", async function () {
      var key = layoutPick.value;
      if (!key || !LAYOUTS[key]) return;
      var box = writtenIn();
      if (!box) return;
      var current = box.innerHTML !== undefined ? box.innerHTML : box.value;
      if (!isUntouched(current)) {
        var ok = window.cmsModal
          ? await window.cmsModal({
              title: "Replace what you have written?",
              body: "Starting from a template lays this post out again. "
                  + "What is written here now would be replaced.",
              confirmText: "Replace it",
              cancelText: "Leave it as it is",
              danger: true,
            })
          : window.confirm("Replace what you have written?");
        if (!(ok && ok.confirmed !== false)) {
          layoutPick.value = "";
          return;
        }
      }
      if (box.innerHTML !== undefined) {
        box.innerHTML = LAYOUTS[key];
        box.dispatchEvent(new Event("input", { bubbles: true }));
      } else {
        box.value = LAYOUTS[key];
      }
      var store = form.querySelector("#post-content");
      if (store && store !== box) store.value = LAYOUTS[key];
    });
  }

  //  A post with no title cannot be published: the list is a list of
  //  titles, and "Untitled" twice is two rows nobody can tell apart.
  //  Asked here rather than only at the server so the answer arrives
  //  before the work does.
  var title = form.querySelector("#post-title");
  var publish = form.querySelector("#post-publish");
  if (title && publish) {
    publish.addEventListener("change", function () {
      if (publish.checked && !title.value.trim()) {
        publish.checked = false;
        title.focus();
        if (window.cmsModal) {
          window.cmsModal({
            title: "It needs a name first",
            body: "Give the post a title before publishing it — the title is "
                + "the heading readers see, and how you will find it again here.",
            confirmText: "Right you are",
            cancelText: null,
          });
        }
      }
    });
  }
}());
