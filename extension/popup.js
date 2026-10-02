// ClipGrab extension: clip the current tab's video, with your login for the site if you allow it.
const API = "https://clip-grab.vercel.app"; // http://localhost:8000 while developing
const $ = (id) => document.getElementById(id);
const [link, start, end, submit, message, login] = ["link", "start", "end", "submit", "message", "login"].map($);
let info, item, downloadId, typing;
let lookups = 0;

const time = (s) => (s ? `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}` : "");

function target() {
  const value = link.value.trim();
  try {
    return value && new URL(/^https?:\/\//.test(value) ? value : `https://${value}`).href;
  } catch {
    return "";
  }
}

// "www.instagram.com" → "instagram.com", "news.bbc.co.uk" → "bbc.co.uk"
function site(url) {
  const host = new URL(url).hostname;
  return host.split(".").slice(/\.(co|com|org|net|ac|gov|edu)\.[a-z]{2}$/.test(host) ? -3 : -2).join(".");
}

const access = (url) => ({ permissions: ["cookies"], origins: [`https://*.${site(url)}/*`] });

// Your cookies for the site, but only once you've let ClipGrab use your login there.
async function cookies(url) {
  if (await chrome.permissions.contains(access(url))) return chrome.cookies.getAll({ domain: site(url) });
}

async function lookup() {
  const ticket = ++lookups;
  const url = target();
  info = item = null;
  say(url ? "Looking up the link…" : "");
  render();
  if (!url) return;
  try {
    const sent = await cookies(url);
    const body = JSON.stringify({ url, cookies: sent });
    const response = await fetch(`${API}/api/info`, { method: "POST", headers: { "Content-Type": "application/json" }, body });
    const data = await response.json();
    if (ticket !== lookups) return; // a newer link was entered meanwhile
    if (data.code === "auth_required" && sent) return say(`${data.error} Log in to ${site(url)} in Chrome, then try again.`);
    if (!response.ok) return say(data.error, data.code === "auth_required" && url);
    [info, item] = [data, data.items[0]];
    say("");
  } catch {
    if (ticket !== lookups) return;
    say("Couldn't reach ClipGrab. Check your connection.");
  }
  render();
}

function render() {
  const many = info?.items.length > 1;
  $("preview").hidden = !info;
  $("platform").textContent = info?.platform ?? "";
  $("title").textContent = info?.title ?? "";
  $("items").hidden = !many;
  $("tiles").replaceChildren(...(many ? info.items.map(tile) : []));
  update();
}

function tile(entry) {
  const label = document.createElement("label");
  label.innerHTML = '<input type="radio" name="item"><img alt=""><span></span>';
  const [radio, image, tag] = label.children;
  Object.assign(radio, { checked: entry === item, ariaLabel: `${entry.kind === "image" ? "Photo" : "Video"} ${entry.index}` });
  radio.onchange = () => {
    item = entry;
    start.value = end.value = "";
    update();
  };
  if (entry.thumbnail) image.src = entry.thumbnail;
  tag.textContent = entry.kind === "image" ? "Photo" : time(entry.duration);
  return label;
}

function update() {
  const photo = item?.kind === "image";
  $("trim").hidden = photo;
  end.placeholder = time(item?.duration) || "End";
  submit.textContent = photo ? "Download photo" : start.value.trim() || end.value.trim() ? "Download clip" : "Download video";
}

function say(text, loginUrl) {
  message.textContent = text;
  login.hidden = !loginUrl;
  if (loginUrl) login.textContent = `Use my ${site(loginUrl)} login`;
}

// Chrome asks the user first; the cookies only ever go to ClipGrab, with requests for that site.
login.onclick = async () => {
  if (await chrome.permissions.request(access(target()))) lookup();
};

// Chrome's download manager does the download, so it carries on even if this popup closes.
$("form").onsubmit = async (event) => {
  event.preventDefault();
  if (!info) return lookup();
  const url = target();
  submit.disabled = true;
  say("Preparing your file. It'll show up in your downloads.");
  try {
    const body = JSON.stringify({ url, item: item.index, start: start.value, end: end.value, cookies: await cookies(url) });
    const headers = [{ name: "Content-Type", value: "application/json" }];
    downloadId = await chrome.downloads.download({ url: `${API}/api/download`, method: "POST", headers, body });
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
start.oninput = end.oninput = update;
document.addEventListener("error", (e) => e.target.tagName === "IMG" && e.target.removeAttribute("src"), true);

const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
if (/^https?:/.test(tab?.url ?? "")) link.value = tab.url;
lookup();
