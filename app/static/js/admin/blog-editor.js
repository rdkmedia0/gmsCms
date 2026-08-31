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
  var offset = form.querySelector("[data-tz-offset]");
  if (offset) offset.value = String(-new Date().getTimezoneOffset());

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
