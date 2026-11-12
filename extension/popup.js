// ClipGrab extension: clip the video in the current tab using the ClipGrab API.
const API = "https://clipgrab.aravarun.in"; // http://localhost:8000 while developing
const $ = (id) => document.getElementById(id);
const [link, start, end, submit, message] = ["link", "start", "end", "submit", "message"].map($);
let info, downloadId, typing;
let lookups = 0; // counts lookups, so an older one finishing late is ignored

const clock = (seconds) => (seconds ? `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, "0")}` : "");
const say = (text) => (message.textContent = text);

async function lookup() {
  const ticket = ++lookups;
  const url = link.value.trim();
  info = null;
  say(url ? "Looking up the link…" : "");
  render();
  if (!url) return;
  try {
    const response = await fetch(`${API}/api/info`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    const data = await response.json();
    if (ticket !== lookups) return;
    if (!response.ok) return say(data.error);
    info = data;
    say("");
  } catch {
    if (ticket === lookups) say("Couldn't reach ClipGrab. Check your connection.");
  }
  render();
}

function render() {
  $("preview").hidden = !info;
  $("platform").textContent = info?.platform ?? "";
  $("title").textContent = info?.title ?? "";
  end.placeholder = clock(info?.duration) || "End";
  label();
}

function label() {
  submit.textContent = start.value.trim() || end.value.trim() ? "Download clip" : "Download video";
}

// Chrome's download manager does the download, so it carries on if this popup closes.
$("form").onsubmit = async (event) => {
  event.preventDefault();
  if (!info) return lookup();
  submit.disabled = true;
  say("Preparing your file. It'll show up in your downloads.");
  try {
    downloadId = await chrome.downloads.download({
      url: `${API}/api/download`,
      method: "POST",
      headers: [{ name: "Content-Type", value: "application/json" }],
      body: JSON.stringify({ url: link.value.trim(), start: start.value, end: end.value }),
    });
  } catch (error) {
    say(error.message);
  }
  submit.disabled = false;
};

chrome.downloads.onChanged.addListener(({ id, state, error }) => {
  if (id !== downloadId) return;
  if (error) say("The download failed. Check the start and end times, then try again.");
  else if (state?.current === "complete") say("Downloaded. It's in your downloads folder.");
});

link.oninput = () => {
  clearTimeout(typing);
  typing = setTimeout(lookup, 500);
};
start.oninput = end.oninput = label;

// Start with the link of the tab you're on.
const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
if (/^https?:/.test(tab?.url ?? "")) link.value = tab.url;
lookup();
