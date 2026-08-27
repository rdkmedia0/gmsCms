// Choosing a picture from the Media Library, written once.
//
// It lived inside inline-editor.js, which only ever loads on the public
// page -- so an ADMIN screen that needed a picture had no way to ask for
// one, and the newsletter editor was about to grow a second picker of
// its own. That is the drift this project keeps warning about, and the
// remedy it keeps reaching for: pull the shared thing out, leave one
// implementation, let both callers use it. Same move as modal.js and
// wysiwyg-commands.js.
//
//   window.cmsImagePicker.open()      -> Promise<url|null>, fetching the
//                                        library itself
//   window.cmsImagePicker.from(list)  -> Promise<url|null>, for a caller
//                                        that already has the pictures
//                                        (the live page reads its own
//                                        from a JSON block)
//   window.cmsImagePicker.upload(file) -> Promise<url|null>
//
// The markup is built here rather than required of every page that wants
// one. A caller that has its own copy in the page (public/page.html has
// had one since before this was extracted) is used as it stands, so
// nothing is drawn twice.
(function () {
  "use strict";

  var backdrop, grid, cancel;

  function say(message) {
    if (window.cmsModal) window.cmsModal({ message: message, confirmLabel: "OK", danger: false });
    else window.alert(message);
  }

  function ensure() {
    if (backdrop) return;
    backdrop = document.getElementById("cms-image-picker-backdrop");
    if (backdrop) {
      grid = document.getElementById("cms-image-picker-grid");
      cancel = document.getElementById("cms-image-picker-cancel");
      return;
    }
    backdrop = document.createElement("div");
    backdrop.id = "cms-image-picker-backdrop";
    backdrop.className = "cms-modal-backdrop";
    backdrop.hidden = true;
    var box = document.createElement("div");
    box.className = "cms-modal cms-image-picker";
    var note = document.createElement("p");
    note.textContent = "Choose a picture. Everything in your Media Library is here.";
    grid = document.createElement("div");
    grid.id = "cms-image-picker-grid";
    grid.className = "cms-image-picker-grid";
    var actions = document.createElement("div");
    actions.className = "cms-modal-actions";
    cancel = document.createElement("button");
    cancel.type = "button";
    cancel.id = "cms-image-picker-cancel";
    cancel.textContent = "Cancel";
    cancel.title = "Close this without choosing a picture.";
    actions.appendChild(cancel);
    box.appendChild(note);
    box.appendChild(grid);
    box.appendChild(actions);
    backdrop.appendChild(box);
    document.body.appendChild(backdrop);
  }

  function from(images) {
    ensure();
    return new Promise(function (resolve) {
      grid.innerHTML = "";
      (images || []).forEach(function (img) {
        var b = document.createElement("button");
        b.type = "button";
        //  The filename is the only thing distinguishing two pictures
        //  that look alike at thumbnail size.
        b.title = img.name || img.filename || "Use this picture";
        var thumb = document.createElement("img");
        thumb.src = img.url;
        thumb.alt = "";
        b.appendChild(thumb);
        b.addEventListener("click", function () { done(img.url); });
        grid.appendChild(b);
      });
      backdrop.hidden = false;

      function done(url) {
        backdrop.hidden = true;
        cancel.removeEventListener("click", onCancel);
        backdrop.removeEventListener("click", onBackdrop);
        document.removeEventListener("keydown", onKey);
        resolve(url);
      }
      function onCancel() { done(null); }
      function onBackdrop(e) { if (e.target === backdrop) done(null); }
      function onKey(e) { if (e.key === "Escape") done(null); }
      cancel.addEventListener("click", onCancel);
      backdrop.addEventListener("click", onBackdrop);
      document.addEventListener("keydown", onKey);
    });
  }

  async function open() {
    var images = [];
    try {
      //  The header is what makes the route answer JSON rather than the
      //  Media Library page.
      var res = await fetch("/admin/images?picker=1", { headers: { "X-Inline-Edit": "1" } });
      images = (await res.json()).images || [];
    } catch (e) {
      say("Couldn't load the Media Library — check your connection.");
      return null;
    }
    if (!images.length) {
      say("The Media Library is empty — upload a picture first.");
      return null;
    }
    return from(images);
  }

  async function upload(file) {
    if (!file) return null;
    var body = new FormData();
    body.append("image", file);
    try {
      var res = await fetch("/admin/images/upload", {
        method: "POST", headers: { "X-Inline-Edit": "1" }, body,
      });
      var data = await res.json();
      if (res.ok && data.ok) return data.url;
      say(data.error || "Couldn't upload that picture.");
    } catch (e) {
      say("Couldn't upload — check your connection.");
    }
    return null;
  }

  window.cmsImagePicker = { open: open, from: from, upload: upload };
})();
