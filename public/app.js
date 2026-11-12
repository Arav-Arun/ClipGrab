// ClipGrab website: paste a link, scrub to the moment, pick a format, download.
const $ = (id) => document.getElementById(id);
const [link, player, from, to, start, end, submit, quality] = ["link", "player", "from", "to", "start", "end", "submit", "quality"].map($);

const MAX_CONVERT_SECONDS = 60; // matches MAX_SECONDS in server/export.py
const RECENT_KEY = "clipgrab:recent";

// The link in the box, what /api/info said about it, and the lookup still running (if any).
let current = { url: "", info: null, request: null };

// 75.4 → "1:15.4", and back again ("1:15.4" → 75.4). Empty or invalid text → null.
const clock = (s) => `${Math.floor(s / 60)}:${(s % 60).toFixed(1).padStart(4, "0")}`;
const seconds = (text) => {
  if (!text.trim()) return null;
  const value = text.split(":").reduce((total, part) => total * 60 + Number(part), 0);
  return Number.isFinite(value) ? value : null;
};
const megabytes = (bytes) => (bytes ? ` · ${(bytes / 2 ** 20).toFixed(1)} MB` : "");
const preset = () => document.querySelector("[name=preset]:checked").value;
const NAMES = { mp4: "MP4", gif: "GIF", mp3: "MP3", small: "small MP4", vertical: "9:16 MP4" };

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

function say(text = "", failed = false) {
  $("status").textContent = text;
  $("status").classList.toggle("error", failed);
}

// Look the link up as soon as it's pasted, then show the editor for that video.
async function lookup(force = false) {
  const url = link.value.trim();
  if (url === current.url && !force) return;
  current.request?.abort(); // a newer link replaces a lookup that's still running
  current = { url, info: null, request: new AbortController() };
  const { signal } = current.request;
  $("editor").hidden = true;
  say(url ? "Looking up the link…" : "");
  if (!url) return;
  try {
    current.info = await (await api("/api/info", { url }, signal)).json();
    say();
    show(current.info);
  } catch (error) {
    if (!signal.aborted) say(error.message, true);
  }
}

function show(info) {
  $("platform").textContent = info.platform;
  $("title").textContent = info.title ?? "Untitled";
  $("uploader").textContent = info.uploader ? `by ${info.uploader}` : "";
  player.poster = info.thumbnail ?? "";
  player.src = info.preview ?? "";
  player.hidden = !info.preview;

  // The timeline needs a length; without one, the start and end boxes still work.
  const length = info.duration ?? 0;
  $("timeline").hidden = !length;
  for (const handle of [from, to]) handle.max = length;

  quality.replaceChildren(
    ...info.qualities.map(({ height, size }) => new Option(`${height}p${megabytes(size)}`, height)),
  );
  $("editor").hidden = false;
  setRange(0, length);
}

// The clip is the range between the two handles; the boxes and the highlight follow it.
function setRange(a, b) {
  const length = Number(to.max) || Infinity;
  a = Math.max(0, Math.min(a, length));
  b = Math.max(a, Math.min(b, length));
  from.value = a;
  to.value = b;
  start.value = clock(a);
  end.value = clock(b);
  const percent = (value) => (length === Infinity ? 0 : (value / length) * 100);
  Object.assign($("selection").style, { left: `${percent(a)}%`, width: `${percent(b) - percent(a)}%` });
  update();
}

const range = () => [seconds(start.value) ?? 0, seconds(end.value) ?? current.info?.duration ?? 0];

// The button says what you'll get, and refuses what the server would refuse.
function update() {
  const [a, b] = range();
  const kind = preset();
  const length = b - a;
  const tooLong = kind !== "mp4" && kind !== "mp3" && length > MAX_CONVERT_SECONDS;
  $("quality-row").hidden = kind !== "mp4" || quality.options.length < 2;
  submit.disabled = length <= 0 || tooLong;
  submit.textContent = tooLong
    ? `Clips up to ${MAX_CONVERT_SECONDS} s for ${NAMES[kind]}`
    : `Download ${clock(Math.max(length, 0))} as ${NAMES[kind]}`;
}

// The filename the server picked, from its Content-Disposition header.
const filename = (header) =>
  decodeURIComponent(/filename\*=utf-8''([^;]+)/i.exec(header)?.[1] ?? "") || /filename="([^"]+)"/.exec(header)?.[1];

$("form").onsubmit = async (event) => {
  event.preventDefault();
  if (!current.info || current.url !== link.value.trim()) return lookup(true);
  const [a, b] = range();
  const whole = current.info.duration ?? Infinity;
  const body = {
    url: current.url,
    start: a > 0 ? a : null, // the full video needs no trimming
    end: b < whole ? b : null,
    preset: preset(),
    height: preset() === "mp4" ? Number(quality.value) || null : null,
  };
  submit.disabled = true;
  submit.classList.add("loading");
  submit.textContent = body.preset === "mp4" ? "Cutting your clip…" : "Cutting and converting…";
  say();
  try {
    const response = await api("/api/download", body);
    const name = filename(response.headers.get("Content-Disposition") ?? "") || "clipgrab";
    const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(await response.blob()), download: name });
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 60_000);
    say(`Saved “${name}”`);
    remember(current.info);
  } catch (error) {
    say(error.message, true);
  } finally {
    submit.classList.remove("loading");
    update();
  }
};

// Recent clips live in this browser's localStorage only.
function remember({ title, platform, thumbnail }) {
  const entry = { url: current.url, title, platform, thumbnail, at: Date.now() };
  const list = [entry, ...recent().filter((item) => item.url !== entry.url)].slice(0, 6);
  localStorage.setItem(RECENT_KEY, JSON.stringify(list));
  renderRecent();
}

function recent() {
  try {
    return JSON.parse(localStorage.getItem(RECENT_KEY)) ?? [];
  } catch {
    return [];
  }
}

function renderRecent() {
  const list = recent();
  $("recent").hidden = !list.length;
  $("recent-list").replaceChildren(
    ...list.map((item) => {
      const row = document.createElement("li");
      row.innerHTML = '<button type="button"><img alt="" referrerpolicy="no-referrer"><span></span><small></small></button>';
      const button = row.firstChild;
      const [image, title, when] = button.children;
      if (item.thumbnail) image.src = item.thumbnail;
      image.onerror = () => image.removeAttribute("src");
      title.textContent = item.title ?? item.url;
      when.textContent = `${item.platform} · ${new Date(item.at).toLocaleDateString()}`;
      button.onclick = () => {
        link.value = item.url;
        lookup();
        scrollTo({ top: 0, behavior: "smooth" });
      };
      return row;
    }),
  );
}

// Wiring
let typing;
link.oninput = () => {
  clearTimeout(typing);
  typing = setTimeout(lookup, 500); // wait until they stop typing
};
$("paste").onclick = async () => {
  link.value = await navigator.clipboard.readText().catch(() => link.value);
  lookup();
};
// Dragging a handle past the other one pushes it along.
from.oninput = () => setRange(Number(from.value), Math.max(Number(from.value), Number(to.value)));
to.oninput = () => setRange(Math.min(Number(from.value), Number(to.value)), Number(to.value));
from.onchange = () => (player.currentTime = Number(from.value)); // show the frame you landed on
to.onchange = () => (player.currentTime = Number(to.value));
start.onchange = end.onchange = () => setRange(...range());
start.oninput = end.oninput = update;
$("mark-start").onclick = () => setRange(player.currentTime, range()[1]);
$("mark-end").onclick = () => setRange(range()[0], player.currentTime);
// "Play clip" plays from the start handle and stops at the end handle.
let playingClip = false;
$("play-clip").onclick = () => {
  player.currentTime = range()[0];
  playingClip = true;
  player.play();
};
player.onpause = () => (playingClip = false);
player.ontimeupdate = () => {
  if (playingClip && player.currentTime >= range()[1]) player.pause();
};
player.onerror = () => (player.hidden = true); // the timeline still works without a preview
for (const radio of document.querySelectorAll("[name=preset]")) radio.onchange = update;

// Links can be shared as https://clipgrab.aravarun.in/?url=…
link.value = new URLSearchParams(location.search).get("url") ?? "";
renderRecent();
lookup();
