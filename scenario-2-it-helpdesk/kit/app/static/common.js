// Small helpers shared by the three pages: palette switch, API calls, tiny DOM builder, formatting.

const Icons = {
  palm: '<svg class="i" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M12 21V10"/><path d="M12 10C10 6 6 5 3 6c3 0 5 1.5 6 4"/><path d="M12 10c2-4 6-5 9-4-3 0-5 1.5-6 4"/><path d="M12 10C11 6 11 4 12 2c1 2 1 4 0 8"/><path d="M12 10c-3-1-6 0-8 3 3-1 6-1 8 1"/><path d="M12 10c3-1 6 0 8 3-3-1-6-1-8 1"/></svg>',
  plus: '<svg class="i" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>',
  send: '<svg class="i" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M13 6l6 6-6 6"/></svg>',
  menu: '<svg class="i" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 7h16M4 12h16M4 17h16"/></svg>',
  logout: '<svg class="i" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M9 4H5v16h4"/><path d="M16 8l4 4-4 4M20 12H9"/></svg>',
  eye: '<svg class="i" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg>',
  ticket: '<svg class="i" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 8a2 2 0 0 0 0 4v0a2 2 0 0 1 0 4v2h16v-2a2 2 0 0 1 0-4v0a2 2 0 0 0 0-4V6H4z"/><path d="M14 6v12" stroke-dasharray="2 3"/></svg>',
};

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  try { localStorage.setItem("nakhla-theme", theme); } catch (e) { /* private mode: the choice just is not remembered */ }
  document.querySelectorAll("[data-theme-pick]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.themePick === theme)));
}
function initTheme() {
  applyTheme(document.documentElement.dataset.theme || "palm");
  document.querySelectorAll("[data-theme-pick]").forEach((b) => b.addEventListener("click", () => applyTheme(b.dataset.themePick)));
}

// fetch with the cookie, JSON in and out. A 401 anywhere (except the sign-in form) sends the person to the sign-in page.
async function api(path, options = {}) {
  const res = await fetch(path, { credentials: "same-origin", headers: { "Content-Type": "application/json" }, ...options });
  let data = null;
  try { data = await res.json(); } catch (e) { /* no body */ }
  if (res.status === 401 && path !== "/web/login") { location.href = "/login"; throw new Error("Signed out"); }
  if (!res.ok) {
    const error = new Error((data && data.detail) || "Request failed (" + res.status + ")");
    error.status = res.status;
    throw error;
  }
  return data;
}

// Builds elements with textContent only, so text from users or the model can never become HTML.
function h(tag, attrs, ...kids) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value == null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "icon") node.innerHTML = Icons[value];          // our own fixed icon strings only
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const kid of kids.flat()) {
    if (kid == null || kid === false) continue;
    node.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return node;
}

const pad = (n) => String(n).padStart(2, "0");
function clock(ts) { const d = new Date(ts * 1000); return pad(d.getHours()) + ":" + pad(d.getMinutes()); }
function dayLabel(ts) {
  const d = new Date(ts * 1000), now = new Date();
  const days = Math.round((new Date(now.getFullYear(), now.getMonth(), now.getDate()) - new Date(d.getFullYear(), d.getMonth(), d.getDate())) / 864e5);
  if (days <= 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days < 7) return "Previous 7 days";
  return "Older";
}
function fullDate(ts) { const d = new Date(ts * 1000); return d.toLocaleDateString(undefined, { month: "short", day: "numeric" }) + " " + clock(ts); }
