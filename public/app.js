// ClipGrab: paste a link, preview it, pick an item and a time range, download.
const $ = (id) => document.getElementById(id);
const [link, start, end, submit, feedback, steps] = ["link", "start", "end", "submit", "feedback", "install-steps"].map($);
let current = { url: "", info: null, item: null, lookup: null };

const time = (s) => (s ? `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}` : "");
const show = (image, src) => (src ? (image.src = src) : image.removeAttribute("src"));
const filename = (header) =>
  decodeURIComponent(/filename\*=utf-8''([^;]+)/i.exec(header)?.[1] ?? "") || /filename="([^"]+)"/.exec(header)?.[1];

async function api(path, body, signal) {
  const options = { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal };
  const response = await fetch(path, options).catch((error) => {
    throw error.name === "AbortError" ? error : new Error("Couldn't reach ClipGrab. Check your connection.");
  });
  if (response.ok) return response;
  const { error, code } = await response.json().catch(() => ({}));
  throw Object.assign(new Error(error ?? `Something went wrong (${response.status}).`), { code });
}

// Look the link up as soon as it's pasted or typed, so the preview shows what's there.
async function lookup(force = false) {
  const url = link.value.trim();
  if (url === current.url && !force) return;
  current.lookup?.abort();
  current = { url, info: null, item: null, lookup: new AbortController() };
  const { signal } = current.lookup;
  const isLink = /\S\.\S/.test(url);
  say();
  render(isLink);
  if (!isLink) return;
  try {
    current.info = await (await api("/api/info", { url }, signal)).json();
    current.item = current.info.items[0];
  } catch (error) {
    if (!signal.aborted) say(error);
  }
  if (!signal.aborted) render();
}

function render(loading = false) {
  const { info, item } = current;
  const many = info?.items.length > 1;
  $("preview").hidden = !info && !loading;
  $("preview").classList.toggle("loading", loading);
  $("platform").textContent = loading ? "Looking up the link…" : (info?.platform ?? "");
  $("title").textContent = info?.title ?? "";
  $("uploader").textContent = info?.uploader ? `by ${info.uploader}` : "";
  $("badge").textContent = many ? `${info.items.length} items` : time(item?.duration);
  show($("thumb"), info?.thumbnail);
  $("items").hidden = !many;
  $("tiles").replaceChildren(...(many ? info.items.map(tile) : []));
  update();
}

function tile(item) {
  const label = Object.assign(document.createElement("label"), { className: "tile" });
  label.innerHTML = '<input type="radio" name="item"><img alt="" referrerpolicy="no-referrer"><span></span>';
  const [radio, image, tag] = label.children;
  const kind = item.kind === "image" ? "Photo" : "Video";
  Object.assign(radio, { checked: item === current.item, ariaLabel: `${kind} ${item.index}` });
  radio.onchange = () => {
    current.item = item;
    start.value = end.value = "";
    update();
  };
  show(image, item.thumbnail);
  tag.textContent = item.kind === "image" ? "Photo" : time(item.duration) || "Video";
  return label;
}

function update() {
  const photo = current.item?.kind === "image";
  const trimmed = start.value.trim() || end.value.trim();
  $("trim").hidden = photo;
  end.placeholder = time(current.item?.duration) || "End";
  submit.textContent = photo ? "Download photo" : trimmed ? "Download clip" : "Download video";
}

function say(result) {
  feedback.hidden = !result;
  if (!result) return;
  const failed = result instanceof Error;
  feedback.classList.toggle("error", failed);
  $("message").textContent = failed ? result.message : `Downloaded “${result}”`;
  $("login-hint").hidden = result.code !== "auth_required";
}

function busy(on) {
  for (const input of [link, start, end, submit]) input.disabled = on;
  submit.classList.toggle("loading", on);
  if (on) submit.textContent = "Preparing your file…";
  else update();
}

$("form").onsubmit = async (event) => {
  event.preventDefault();
  if (!current.info || current.url !== link.value.trim()) await lookup(true);
  if (!current.info) return;
  busy(true);
  try {
    const { url, item } = current;
    const response = await api("/api/download", { url, item: item.index, start: start.value, end: end.value });
    const name = filename(response.headers.get("Content-Disposition") ?? "") || "clipgrab";
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
  typing = setTimeout(lookup, 500);
};
start.oninput = end.oninput = update;
$("paste").onclick = async () => {
  link.value = await navigator.clipboard.readText().catch(() => link.value);
  lookup();
};
// Some CDNs refuse to show their images on other sites; fall back to a placeholder.
document.addEventListener("error", (e) => e.target.tagName === "IMG" && e.target.removeAttribute("src"), true);

const openSteps = (open = steps.hidden) => {
  steps.hidden = !open;
  $("install-toggle").setAttribute("aria-expanded", open);
};
$("install-toggle").onclick = () => openSteps();
$("get-extension").onclick = () => {
  openSteps(true);
  steps.scrollIntoView({ behavior: "smooth" });
};

// Links can be shared as https://clip-grab.vercel.app/?url=…
link.value = new URLSearchParams(location.search).get("url") ?? "";
lookup();
