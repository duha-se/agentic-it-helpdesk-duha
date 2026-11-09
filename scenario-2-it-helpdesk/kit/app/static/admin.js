// Admin page: overview stats, tickets table, accounts, audit log.
"use strict";
(function () {
  initTheme();

  document.getElementById("logoutBtn").addEventListener("click", async () => {
    await api("/web/logout", { method: "POST" });
    location.href = "/login";
  });

  // ── tabs ─────────────────────────────────────────────────────────────────
  const tabBtns = [...document.querySelectorAll("[role=tab]")];
  tabBtns.forEach((btn) => btn.addEventListener("click", () => {
    tabBtns.forEach((b) => { b.setAttribute("aria-selected", String(b === btn)); });
    document.querySelectorAll("[id^=tab-]").forEach((panel) => {
      panel.hidden = panel.id !== "tab-" + btn.dataset.tab;
    });
  }));

  // ── load ──────────────────────────────────────────────────────────────────
  let allTickets = [];

  async function load() {
    document.getElementById("lead").textContent = "Loading…";
    try {
      const data = await api("/web/admin/overview");
      document.getElementById("adminName").textContent = "Admin";

      // stats
      const s = data.stats;
      const STATS = document.getElementById("stats");
      STATS.innerHTML = "";
      [
        [s.tickets_total ?? "—", "Total tickets"],
        [s.tickets_open ?? "—", "Open tickets"],
        [s.created_by_agent ?? 0, "Created via agent"],
        [s.conversations ?? 0, "Conversations"],
        [s.logins ?? 0, "Sign-ins"],
      ].forEach(([v, label]) => STATS.append(h("div", { class: "stat" }, h("b", {}, String(v)), h("span", {}, label))));

      document.getElementById("lead").textContent = data.tickets_error ||
        (new Date().toLocaleString(undefined, { weekday: "long", month: "long", day: "numeric", hour: "2-digit", minute: "2-digit" }));

      // tickets
      allTickets = data.tickets;
      renderTickets(allTickets);

      // users
      const UB = document.getElementById("userBody");
      UB.innerHTML = "";
      (data.users || []).forEach((u) => {
        UB.append(h("tr", {},
          h("td", {}, u.name),
          h("td", { class: "mono" }, u.email),
          h("td", {}, h("span", { class: "pill st" + (u.role === "admin" ? "" : " open") }, u.role)),
          h("td", {}, String(u.conversations || 0))));
      });

      // audit
      const AB = document.getElementById("auditBody");
      AB.innerHTML = "";
      (data.audit || []).forEach((e) => {
        const detail = e.detail && Object.keys(e.detail).length
          ? Object.entries(e.detail).map(([k, v]) => k + "=" + v).join(", ")
          : "";
        AB.append(h("tr", {},
          h("td", { class: "mono" }, fullDate(e.at)),
          h("td", {}, h("code", {}, e.event)),
          h("td", { class: "mono muted" }, (e.session_id || "").slice(0, 14)),
          h("td", { class: "muted" }, detail)));
      });
    } catch (err) {
      document.getElementById("lead").textContent = "Could not load: " + err.message;
    }
  }

  function renderTickets(tickets) {
    const TB = document.getElementById("ticketBody");
    TB.innerHTML = "";
    if (!tickets.length) { TB.append(h("tr", {}, h("td", { colspan: "8", class: "note" }, "No tickets."))); return; }
    tickets.forEach((t) => {
      TB.append(h("tr", {},
        h("td", { class: "mono" }, t.ticket_id),
        h("td", {}, h("span", { class: "pill " + (t.priority || "") }, t.priority || "—")),
        h("td", {}, h("span", { class: "pill st" + (t.status === "open" ? " open" : "") }, t.status || "—")),
        h("td", {}, t.category || "—"),
        h("td", { class: "mono muted" }, (t.requester_email || "").replace("@nakhla.example", "")),
        h("td", { class: "muted" }, (t.assigned_team || "").replace(/ (Operations|Management|Services|Engineering)$/, "…")),
        h("td", {}, t.subject || "—"),
        h("td", { class: "mono muted" }, t.created_at ? fullDate(parseFloat(t.created_at)) || t.created_at.slice(0, 10) : "—")));
    });
  }

  // ticket search
  document.getElementById("ticketSearch").addEventListener("input", (e) => {
    const q = e.target.value.toLowerCase().trim();
    renderTickets(q ? allTickets.filter((t) => JSON.stringify(t).toLowerCase().includes(q)) : allTickets);
  });

  document.getElementById("refreshBtn").addEventListener("click", load);
  load();
})();

// =====================  ADMIN CHAT  =====================
(function () {
  let adminConvId = null;
  let adminSending = false;
  const AMSG  = document.getElementById("adminMessages");
  const INPUT = document.getElementById("adminInput");
  const SEND  = document.getElementById("adminSend");
  const CONVS = document.getElementById("adminConvs");

  if (!AMSG) return;   // panel not in DOM yet

  // auto-resize textarea
  function resize() {
    INPUT.style.height = "auto";
    INPUT.style.height = Math.min(INPUT.scrollHeight, 140) + "px";
    SEND.disabled = !INPUT.value.trim() || adminSending;
  }
  INPUT.addEventListener("input", resize);
  INPUT.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); if (!SEND.disabled) adminSend(); }
  });
  SEND.addEventListener("click", adminSend);

  document.getElementById("adminNewChat").addEventListener("click", () => {
    adminConvId = null;
    AMSG.innerHTML = '<p style="color:var(--muted);text-align:center;margin-top:3rem">New admin chat started. Ask anything.</p>';
    CONVS.querySelectorAll(".admin-conv").forEach((b) => b.classList.remove("active"));
    INPUT.focus();
  });

  async function loadAdminConvs() {
    try {
      const data = await api("/web/conversations");
      CONVS.innerHTML = "";
      if (!data.conversations.length) {
        CONVS.innerHTML = '<p style="color:var(--muted);font-size:.85rem;padding:.5rem">No conversations yet.</p>';
        return;
      }
      data.conversations.forEach((c) => {
        const btn = h("button", { class: "admin-conv" + (c.id === adminConvId ? " active" : ""), type: "button",
          "data-id": c.id, onclick: () => openAdminConv(c.id) },
          h("b", {}, c.title || "New chat"),
          h("small", {}, (c.owner ? c.owner.replace("@nakhla.example","") + " · " : "") + fullDate(c.updated_at)));
        CONVS.append(btn);
      });
    } catch (e) { /* silent */ }
  }

  async function openAdminConv(id) {
    adminConvId = id;
    CONVS.querySelectorAll(".admin-conv").forEach((b) => b.classList.toggle("active", b.dataset.id === id));
    AMSG.innerHTML = "";
    try {
      const data = await api("/web/conversations/" + id);
      for (const m of data.messages) adminRenderMsg(m);
      AMSG.scrollTop = AMSG.scrollHeight;
    } catch (e) { AMSG.innerHTML = '<p style="color:var(--danger)">Could not load.</p>'; }
  }

  async function adminSend() {
    const text = INPUT.value.trim();
    if (!text || adminSending) return;
    adminSending = true; SEND.disabled = true;
    adminAppend("user", text);
    INPUT.value = ""; resize();
    const typing = adminTyping();
    try {
      const data = await api("/web/chat", { method: "POST",
        body: JSON.stringify({ conversation_id: adminConvId, message: text }) });
      adminConvId = data.conversation.id;
      typing.remove();
      adminRenderMsg(data.message);
      AMSG.scrollTop = AMSG.scrollHeight;
      await loadAdminConvs();
    } catch (err) {
      typing.remove();
      adminAppend("error", err.message || "Something went wrong.");
    } finally { adminSending = false; SEND.disabled = !INPUT.value.trim(); }
  }

  function adminAppend(role, text) {
    const cls = role === "user" ? "msg user" : "msg bot";
    const row = h("div", { class: cls },
      role === "bot" ? h("div", { class: "bot-avatar" },
        h("svg", { viewBox:"0 0 24 24",fill:"none",stroke:"currentColor","stroke-width":"1.5","stroke-linecap":"round" },
          h("path",{d:"M12 21V10"}), h("path",{d:"M12 10C10 6 6 5 3 6c3 0 5 1.5 6 4"}),
          h("path",{d:"M12 10c2-4 6-5 9-4-3 0-5 1.5-6 4"}))) : false,
      h("div", { class: "stack" }, h("div", { class: "bubble" + (role === "error" ? " err" : "") }, text)));
    AMSG.append(row); return row;
  }

  function adminTyping() {
    const row = h("div", { class: "msg bot" },
      h("div", { class: "bot-avatar" }),
      h("div", { class: "stack" }, h("div", { class: "bubble" },
        h("div", { class: "typing" }, h("i"), h("i"), h("i")))));
    AMSG.append(row); AMSG.scrollTop = AMSG.scrollHeight; return row;
  }

  function adminRenderMsg(m) {
    if (!m || !m.role) return;
    if (m.meta?.decision) { AMSG.append(h("div",{class:"decision"},h("span",{},m.content))); return; }
    const row = adminAppend(m.role, m.content);
    if (m.role === "assistant" && m.meta?.citations?.length) {
      const cites = h("div", { class: "cites" });
      m.meta.citations.forEach((c) => cites.append(
        h("span", { class: "cite" }, h("b", {}, c.id), h("span", {}, c.title))));
      row.querySelector(".stack").append(cites);
    }
  }

  // Load convs when the Chat tab is first opened
  document.querySelectorAll("[data-tab='chat']").forEach((btn) => {
    btn.addEventListener("click", loadAdminConvs, { once: true });
  });
})();