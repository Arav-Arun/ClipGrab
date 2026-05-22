const BACKEND = "https://clip-grab.vercel.app";

document.addEventListener("DOMContentLoaded", async () => {
  const form    = document.getElementById("clip-form");
  const urlIn   = document.getElementById("video-url");
  const startIn = document.getElementById("start-time");
  const endIn   = document.getElementById("end-time");
  const btn     = document.getElementById("submit-btn");
  const btnText = btn.querySelector(".btn-text");
  const loader  = btn.querySelector(".loader");
  const badge   = document.getElementById("badge");
  const msg     = document.getElementById("msg");

  // Platform detection
  const detect = (url) => {
    if (/twitter\.com|x\.com/.test(url)) return "X / Twitter";
    if (/instagram\.com/.test(url)) return "Instagram";
    if (/reddit\.com/.test(url)) return "Reddit";
    if (/vimeo\.com/.test(url)) return "Vimeo";
    if (/twitch\.tv/.test(url)) return "Twitch";
    if (/streamable\.com/.test(url)) return "Streamable";
    return null;
  };

  const showBadge = (url) => {
    const p = detect(url);
    badge.textContent = p ? `Detected: ${p}` : "";
    badge.classList.toggle("hidden", !p);
  };

  // Auto-fill from current tab
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tab?.url && detect(tab.url)) {
      urlIn.value = tab.url;
      showBadge(tab.url);
    }
  } catch {}

  urlIn.addEventListener("input", () => showBadge(urlIn.value));

  // Helpers
  const TIME_RE = /^([0-1]?\d|2[0-3]):[0-5]?\d:[0-5]?\d$/;
  const ok = (t) => !t.trim() || TIME_RE.test(t);

  const showMsg = (text, error = false) => {
    msg.className = `msg ${error ? "error" : "success"}`;
    msg.textContent = text;
    msg.classList.remove("hidden");
  };

  const setLoading = (on) => {
    btn.disabled = on;
    btn.classList.toggle("loading", on);
    btnText.classList.toggle("hidden", on);
    loader.classList.toggle("hidden", !on);
    urlIn.disabled = on;
    startIn.disabled = on;
    endIn.disabled = on;
  };

  // Submit
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    msg.classList.add("hidden");

    const url   = urlIn.value.trim();
    const start = startIn.value.trim();
    const end   = endIn.value.trim();

    // Validate
    if (!url) return showMsg("Paste a video URL first.", true);
    if (!detect(url)) return showMsg("Unsupported URL. Use X, Instagram, Reddit, Vimeo, Twitch, or Streamable.", true);
    if (start && !ok(start)) return showMsg("Start time must be HH:MM:SS.", true);
    if (end && !ok(end)) return showMsg("End time must be HH:MM:SS.", true);

    setLoading(true);

    try {
      const res = await fetch(`${BACKEND}/clip`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, start, end }),
      });

      // JSON = error response
      const ct = res.headers.get("Content-Type") || "";
      if (ct.includes("application/json")) {
        const data = await res.json();
        throw new Error(data.error || "Server error.");
      }
      if (!res.ok) throw new Error(`Server returned ${res.status}.`);

      // Download via chrome API
      const blob = await res.blob();
      const reader = new FileReader();
      reader.onloadend = async () => {
        try {
          await chrome.downloads.download({
            url: reader.result,
            filename: "ClipGrab-video.mp4",
            saveAs: true,
          });
          showMsg("Download started!");
          form.reset();
          showBadge("");
        } catch (err) {
          showMsg(err.message, true);
        }
      };
      reader.readAsDataURL(blob);
    } catch (err) {
      showMsg(err.message, true);
    } finally {
      setLoading(false);
    }
  });
});
