(function () {
  const form = document.getElementById("chat-form");
  if (!form) return; // unconfigured state — nothing else to wire up

  const chatUrl = form.dataset.chatUrl;
  const applyUrl = form.dataset.applyUrl;
  const log = document.getElementById("chat-log");
  const input = document.getElementById("chat-input");
  const proposalBox = document.getElementById("chat-proposal");
  const proposalReason = document.getElementById("proposal-reason");
  const proposalPreview = document.getElementById("proposal-preview");
  let history = [];
  let pendingProposal = null;
  let pendingImage = null; // {mime, data} — base64, cleared after each send

  const imageBtn = document.getElementById("chat-image-btn");
  const imageInput = document.getElementById("chat-image-input");
  const imagePreview = document.getElementById("chat-image-preview");
  const imageThumb = document.getElementById("chat-image-thumb");
  const imageRemove = document.getElementById("chat-image-remove");

  imageBtn.addEventListener("click", () => imageInput.click());
  imageInput.addEventListener("change", () => {
    const file = imageInput.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      // reader.result is "data:image/png;base64,AAAA..." — split off the header.
      const [header, data] = reader.result.split(",");
      const mime = header.match(/data:(.*?);base64/)[1];
      pendingImage = { mime, data };
      imageThumb.src = reader.result;
      imagePreview.hidden = false;
    };
    reader.readAsDataURL(file);
  });
  imageRemove.addEventListener("click", () => {
    pendingImage = null;
    imageInput.value = "";
    imagePreview.hidden = true;
  });

  function addMessage(role, text) {
    const div = document.createElement("div");
    div.className = "chat-msg chat-msg-" + role;
    div.textContent = text;
    log.appendChild(div);
    log.scrollTop = log.scrollHeight;
  }

  // A visible "still working" bubble with a live elapsed-seconds counter —
  // a real response can take anywhere from a few seconds to well over a
  // minute (slow models, cold starts, tool-calling round-trips), and with
  // nothing shown in that gap the panel looked identical to a hung/broken
  // one. Removed the moment the real reply (or an error) arrives.
  function startThinking() {
    const div = document.createElement("div");
    div.className = "chat-msg chat-msg-assistant chat-msg-thinking";
    const spinner = document.createElement("span");
    spinner.className = "cms-chat-spinner";
    const label = document.createElement("span");
    div.appendChild(spinner);
    div.appendChild(label);
    log.appendChild(div);
    log.scrollTop = log.scrollHeight;
    const stop = window.cmsElapsedTimer((seconds) => { label.textContent = "Thinking… " + seconds + "s"; });
    return () => { stop(); div.remove(); };
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    addMessage("user", text + (pendingImage ? " 🖼️" : ""));
    history.push({ role: "user", content: text });
    const imageToSend = pendingImage;
    pendingImage = null;
    imageInput.value = "";
    imagePreview.hidden = true;
    input.value = "";
    input.disabled = true;
    const stopThinking = startThinking();

    try {
      const res = await fetch(chatUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: history, image: imageToSend }),
      });
      stopThinking();
      const data = await res.json();
      if (!res.ok) {
        addMessage("assistant", data.error || "Something went wrong.");
        return;
      }
      if (data.reply) {
        addMessage("assistant", data.reply);
        history.push({ role: "assistant", content: data.reply });
      }
      if (data.proposal) {
        pendingProposal = data.proposal;
        const args = data.proposal.args || {};
        proposalReason.textContent = args.reason || "Reformatted HTML (no visible content change intended).";
        proposalPreview.textContent = args.new_content || args.reformatted_html || "";
        proposalBox.hidden = false;
      }
    } catch {
      stopThinking();
      addMessage("assistant", "Couldn't reach the assistant — check your connection.");
    } finally {
      input.disabled = false;
      input.focus();
    }
  });

  document.getElementById("proposal-discard").addEventListener("click", () => {
    pendingProposal = null;
    proposalBox.hidden = true;
  });

  document.getElementById("proposal-apply").addEventListener("click", async () => {
    if (!pendingProposal) return;
    try {
      const res = await fetch(applyUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(pendingProposal),
      });
      const data = await res.json();
      if (res.ok) {
        addMessage("assistant", "Applied — the change is live. Refresh to see it.");
      } else {
        addMessage("assistant", data.error || "Couldn't apply that change.");
      }
    } catch {
      addMessage("assistant", "Couldn't reach the server to apply that change.");
    }
    pendingProposal = null;
    proposalBox.hidden = true;
  });
})();
