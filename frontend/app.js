/* ClipGrab — Client Logic */

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("clip-form");
  const urlInput = document.getElementById("video-url");
  const startInput = document.getElementById("start-time");
  const endInput = document.getElementById("end-time");
  const submitBtn = document.getElementById("submit-btn");
  const btnText = submitBtn.querySelector(".btn-text");
  const loader = submitBtn.querySelector(".loader");
  const pasteBtn = document.getElementById("paste-btn");
  const badge = document.getElementById("platform-badge");
  const feedback = document.getElementById("feedback");
  const feedbackMsg = document.getElementById("feedback-msg");
  const installToggle = document.getElementById("install-toggle-btn");
  const installSteps = document.getElementById("install-steps");

  // Toggle install instructions
  if (installToggle && installSteps) {
    installToggle.addEventListener("click", () => {
      const open = !installSteps.classList.contains("hidden");
      installSteps.classList.toggle("hidden", open);
      installToggle.setAttribute("aria-expanded", String(!open));
    });
  }

  // Platform detection
  const detectPlatform = (url) => {
    if (/twitter\.com|x\.com/.test(url)) return "X / Twitter";
    if (/instagram\.com/.test(url)) return "Instagram";
    if (/reddit\.com/.test(url)) return "Reddit";
    if (/vimeo\.com/.test(url)) return "Vimeo";
    if (/twitch\.tv/.test(url)) return "Twitch";
    if (/streamable\.com/.test(url)) return "Streamable";
    return null;
  };

  const updateBadge = () => {
    const platform = detectPlatform(urlInput.value.trim());
    badge.textContent = platform ? `Detected: ${platform}` : "";
    badge.classList.toggle("hidden", !platform);
  };

  // Paste from clipboard
  pasteBtn.addEventListener("click", async () => {
    try {
      urlInput.value = await navigator.clipboard.readText();
      urlInput.focus();
      updateBadge();
    } catch { urlInput.focus(); }
  });

  // Time validation
  const TIME_RE = /^([0-1]?\d|2[0-3]):[0-5]?\d:[0-5]?\d$/;
  const validTime = (t) => !t.trim() || TIME_RE.test(t);
  const toSec = (t) => {
    if (!t) return 0;
    const [h, m, s] = t.split(":").map(Number);
    return h * 3600 + m * 60 + s;
  };

  // Collect errors
  const getErrors = () => {
    const errs = [];
    const url = urlInput.value.trim();
    const s = startInput.value.trim();
    const e = endInput.value.trim();

    if (!url) errs.push("A video URL is required.");
    else if (!detectPlatform(url)) errs.push("Unsupported URL. Use X/Twitter, Instagram, Reddit, Vimeo, Twitch, or Streamable.");
    if (s && !validTime(s)) errs.push("Start time must be HH:MM:SS.");
    if (e && !validTime(e)) errs.push("End time must be HH:MM:SS.");
    if (s && e && validTime(s) && validTime(e) && toSec(s) >= toSec(e))
      errs.push("Start time must be before end time.");
    return errs;
  };

  urlInput.addEventListener("input", updateBadge);

  // Show feedback message
  const showFeedback = (content, isError = false) => {
    feedback.className = `feedback ${isError ? "error" : "success"}`;
    feedbackMsg.innerHTML = isError
      ? `<strong class="error-header">Error:</strong><ul class="error-list">${content.map(e => `<li>${e}</li>`).join("")}</ul>`
      : `<strong class="success-header">Done!</strong> ${content}`;
    feedback.classList.remove("hidden");
  };

  // Lock/unlock UI
  const setLoading = (on) => {
    submitBtn.disabled = on;
    submitBtn.classList.toggle("loading", on);
    btnText.classList.toggle("hidden", on);
    loader.classList.toggle("hidden", !on);
    [urlInput, startInput, endInput, pasteBtn].forEach(el => el.disabled = on);
  };

  // Submit
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    feedback.classList.add("hidden");

    const errors = getErrors();
    if (errors.length) {
      showFeedback(errors, true);
      return;
    }

    setLoading(true);

    try {
      const res = await fetch("/clip", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: urlInput.value.trim(),
          start: startInput.value.trim(),
          end: endInput.value.trim(),
        }),
      });

      // Server returns JSON on errors
      const ct = res.headers.get("Content-Type") || "";
      if (ct.includes("application/json")) {
        const data = await res.json();
        throw new Error(data.error || "Server error.");
      }
      if (!res.ok) throw new Error(`Server returned ${res.status}.`);

      // Trigger download
      const blob = await res.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "ClipGrab-video.mp4";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(a.href);

      showFeedback("Video downloaded successfully!");
      form.reset();
      updateBadge();
    } catch (err) {
      showFeedback([err.message], true);
    } finally {
      setLoading(false);
    }
  });
});
