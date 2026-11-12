// ClipGrab website: paste a link, see what it is, pick a time range, download.
const $ = (id) => document.getElementById(id);
const [link, start, end, submit, feedback, steps] = ["link", "start", "end", "submit", "feedback", "install-steps"].map($);

// The link currently in the box, and what /api/info said about it.
let current = { url: "", info: null, request: null };

const clock = (seconds) => (seconds ? `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, "0")}` : "");

// POST JSON to the API. Errors come back as { error } and are thrown with that message.
async function api(path, body, signal) {
  const options = { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal };
  const response = await fetch(path, options).catch((error) => {
    throw error.name === "AbortError" ? error : new Error("Couldn't reach ClipGrab. Check your connection.");
  });
  if (response.ok) return response;
  const { error } = await response.json().catch(() => ({}));
  throw new Error(error ?? `Something went wrong (${response.status}).`);
}

// Look the link up as soon as it's pasted, so the preview shows which video it is.
async function lookup(force = false) {
  const url = link.value.trim();
  if (url === current.url && !force) return;
  current.request?.abort(); // a newer link replaces any lookup still running
  current = { url, info: null, request: new AbortController() };
  const { signal } = current.request;
  say();
  render(Boolean(url));
  if (!url) return;
  try {
    current.info = await (await api("/api/info", { url }, signal)).json();
  } catch (error) {
    if (!signal.aborted) say(error);
  }
  if (!signal.aborted) render();
}

function render(loading = false) {
  const { info } = current;
  $("preview").hidden = !info && !loading;
  $("preview").classList.toggle("loading", loading);
  $("platform").textContent = loading ? "Looking up the link…" : (info?.platform ?? "");
  $("title").textContent = info?.title ?? "";
  $("uploader").textContent = info?.uploader ? `by ${info.uploader}` : "";
  $("badge").textContent = clock(info?.duration);
  if (info?.thumbnail) $("thumb").src = info.thumbnail;
  else $("thumb").removeAttribute("src");
  end.placeholder = clock(info?.duration) || "End";
  label();
}

function label() {
  submit.textContent = start.value.trim() || end.value.trim() ? "Download clip" : "Download video";
}

// Show a success message (a filename) or an Error. Called with nothing, it hides the box.
function say(result) {
  feedback.hidden = !result;
  if (!result) return;
  const failed = result instanceof Error;
  feedback.classList.toggle("error", failed);
  $("message").textContent = failed ? result.message : `Downloaded “${result}”`;
}

function busy(on) {
  for (const input of [link, start, end, submit]) input.disabled = on;
  submit.classList.toggle("loading", on);
  if (on) submit.textContent = "Preparing your file…";
  else label();
}

// The filename the server picked, from its Content-Disposition header.
const filename = (header) =>
  decodeURIComponent(/filename\*=utf-8''([^;]+)/i.exec(header)?.[1] ?? "") || /filename="([^"]+)"/.exec(header)?.[1];

$("form").onsubmit = async (event) => {
  event.preventDefault();
  if (!current.info || current.url !== link.value.trim()) await lookup(true);
  if (!current.info) return;
  busy(true);
  try {
    const response = await api("/api/download", { url: current.url, start: start.value, end: end.value });
    const name = filename(response.headers.get("Content-Disposition") ?? "") || "clipgrab.mp4";
    const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(await response.blob()), download: name });
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 60_000);
    say(name);
  } catch (error) {
    say(error);
  } finally {
    busy(false);
  }
};

let typing;
link.oninput = () => {
  clearTimeout(typing);
  typing = setTimeout(lookup, 500); // wait until they stop typing
};
start.oninput = end.oninput = label;
$("paste").onclick = async () => {
  link.value = await navigator.clipboard.readText().catch(() => link.value);
  lookup();
};
// Some CDNs won't show their thumbnails on other sites; hide a broken image.
$("thumb").onerror = () => $("thumb").removeAttribute("src");

$("install-toggle").onclick = () => {
  steps.hidden = !steps.hidden;
  $("install-toggle").setAttribute("aria-expanded", !steps.hidden);
};

// Links can be shared as https://clipgrab.aravarun.in/?url=…
link.value = new URLSearchParams(location.search).get("url") ?? "";
lookup();
