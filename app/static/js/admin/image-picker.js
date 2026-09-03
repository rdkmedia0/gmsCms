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

  var backdrop, grid, cancel, upload, fileInput;

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
      addUpload(cancel && cancel.parentElement);
      return;
    }
    backdrop = document.createElement("div");
    backdrop.id = "cms-image-picker-backdrop";
    backdrop.className = "cms-modal-backdrop";
    backdrop.hidden = true;
    var box = document.createElement("div");
    box.className = "cms-modal cms-image-picker";
    var note = document.createElement("p");
    note.textContent = "Choose a picture from your Media Library, "
      + "or upload a new one.";
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
    addUpload(actions);
    box.appendChild(note);
    box.appendChild(grid);
    box.appendChild(actions);
    backdrop.appendChild(box);
    document.body.appendChild(backdrop);
  }

  //  Added to whichever dialog exists -- the one this module builds, or
  //  the copy public/page.html has carried since before this was
  //  extracted. Adding it in only one of those is how the two drift, and
  //  that drift is why this module exists at all.
  function addUpload(actions) {
    if (!actions || actions.querySelector(".cms-image-picker-upload")) return;
    upload = document.createElement("button");
    upload.type = "button";
    upload.className = "cms-image-picker-upload";
    upload.textContent = "Upload a picture";
    upload.title = "Add a picture from this device. It joins your Media Library, "
      + "so you can use it again.";
    fileInput = document.createElement("input");
    fileInput.type = "file";
    fileInput.accept = "image/*";
    fileInput.hidden = true;
    upload.addEventListener("click", function () { fileInput.click(); });
    actions.insertBefore(upload, actions.firstChild);
    actions.appendChild(fileInput);
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
        //  LAZY AND ASYNC. The picker lists every picture on the site at
        //  full size -- measured: 162 of them, 86 MB, 58 over 800 KB --
        //  as plain <img> tags that all start downloading at once, and a
        //  tile whose picture has not arrived paints as nothing. That is
        //  the "some of the images do not load" report: they had not
        //  loaded YET. Lazy means only the visible rows fetch; async
        //  means a big one decodes without freezing the rest; and the
        //  placeholder below says "loading" instead of showing a blank.
        //  Real thumbnails need Pillow in the image, which is a
        //  dependency decision for whoever runs this app.
        var thumb = document.createElement("img");
        thumb.loading = "lazy";
        thumb.decoding = "async";
        thumb.alt = "";
        b.classList.add("is-loading");
        thumb.addEventListener("load", function () { b.classList.remove("is-loading"); });
        thumb.addEventListener("error", function () {
          b.classList.remove("is-loading"); b.classList.add("is-broken");
          b.title = "This picture could not be loaded";
        });
        thumb.src = img.url;
        b.appendChild(thumb);
        b.addEventListener("click", function () { done(img.url); });
        grid.appendChild(b);
      });
      backdrop.hidden = false;

      async function onUpload() {
        var file = fileInput.files && fileInput.files[0];
        fileInput.value = "";
        if (!file) return;
        var url = await upload_(file);
        if (url) done(url);
      }
      if (fileInput) fileInput.addEventListener("change", onUpload);

      function done(url) {
        if (fileInput) fileInput.removeEventListener("change", onUpload);
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
    //  An empty library used to be refused with "upload a picture
    //  first", which was true when this dialog could only choose. It can
    //  upload now, so an empty library is exactly when it is most useful
    //  -- being turned away and told to go and do the thing the dialog
    //  does is the worst version of this.
    return from(images);
  }

  async function upload_(file) {
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

  window.cmsImagePicker = { open: open, from: from, upload: upload_ };
})();
