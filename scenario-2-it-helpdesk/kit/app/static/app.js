// Chat page: sidebar with saved conversations, the message thread, and the ticket-draft card.
"use strict";
(function () {
  initTheme();

  // ── state ──────────────────────────────────────────────────────────────────
  let conversationId = null;
  let pendingAction = null;
  let sending = false;
  const MSG = document.getElementById("messages");
  const WELCOME = document.getElementById("welcome");
  const INPUT = document.getElementById("input");
  const SEND = document.getElementById("send");

  // ── load the signed-in user ─────────────────────────────────────────────
  api("/web/me").then((data) => {
    const u = data.user;
    document.getElementById("myName").textContent = u.name;
    document.getElementById("myEmail").textContent = u.email;
    document.getElementById("initials").textContent = u.name.split(" ").map((p) => p[0]).join("").slice(0, 2);
  });

  // ── sign out ────────────────────────────────────────────────────────────
  document.getElementById("logoutBtn").addEventListener("click", async () => {
    await api("/web/logout", { method: "POST" });
    location.href = "/login";
  });

  // ── mobile sidebar toggle ────────────────────────────────────────────────
  const menuBtn = document.getElementById("menuBtn");
  const scrim = document.getElementById("scrim");
  function closeNav() { document.body.classList.remove("nav-open"); menuBtn.setAttribute("aria-expanded", "false"); }
  menuBtn.addEventListener("click", () => {
    const open = document.body.classList.toggle("nav-open");
    menuBtn.setAttribute("aria-expanded", String(open));
  });
  scrim.addEventListener("click", closeNav);

  // ── conversation list ─────────────────────────────────────────────────
  const CONVS = document.getElementById("convs");

  async function loadSidebar() {
    const data = await api("/web/conversations");
    CONVS.innerHTML = "";
    if (!data.conversations.length) {
      CONVS.append(h("p", { class: "empty-list" }, "No saved chats yet"));
      return;
    }
    let lastGroup = null;
    for (const c of data.conversations) {
      const group = dayLabel(c.updated_at);
      if (group !== lastGroup) {
        CONVS.append(h("div", { class: "group", "aria-hidden": "true" }, group));
        lastGroup = group;
      }
      CONVS.append(h("button", {
        class: "conv" + (c.id === conversationId ? " active" : ""),
        type: "button", "data-id": c.id,
        onclick: () => { openConversation(c.id); closeNav(); },
      }, h("b", {}, c.title), h("small", {}, fullDate(c.updated_at))));
    }
  }

  function markActive(id) {
    CONVS.querySelectorAll(".conv").forEach((b) => b.classList.toggle("active", b.dataset.id === id));
  }

  // ── open or continue a conversation ──────────────────────────────────────
  async function openConversation(id) {
    conversationId = id;
    markActive(id);
    pendingAction = null;
    MSG.innerHTML = "";
    WELCOME.hidden = true;
    document.getElementById("chatTitle").textContent = "Loading…";
    document.getElementById("chatState").textContent = "";
    try {
      const data = await api("/web/conversations/" + id);
      document.getElementById("chatTitle").textContent = data.conversation.title;
      for (const m of data.messages) renderMessage(m);
      if (data.pending_action) {
        pendingAction = data.pending_action;
        renderDraft(pendingAction, false);
      }
      MSG.scrollTop = MSG.scrollHeight;
    } catch (err) {
      appendError("Could not load this conversation.");
    }
  }

  // ── new chat ─────────────────────────────────────────────────────────────
  document.getElementById("newChat").addEventListener("click", () => {
    conversationId = null;
    pendingAction = null;
    MSG.innerHTML = "";
    WELCOME.hidden = false;
    document.getElementById("chatTitle").textContent = "New chat";
    document.getElementById("chatState").textContent = "";
    markActive(null);
    INPUT.focus();
    closeNav();
  });

  // ── welcome suggestions ──────────────────────────────────────────────────
  WELCOME.querySelectorAll("[data-msg]").forEach((btn) => {
    btn.addEventListener("click", () => { INPUT.value = btn.dataset.msg; autoResize(); sendMessage(); });
  });

  // ── composer ──────────────────────────────────────────────────────────────
  function autoResize() {
    INPUT.style.height = "auto";
    INPUT.style.height = Math.min(INPUT.scrollHeight, 160) + "px";
    SEND.disabled = !INPUT.value.trim() || sending;
  }
  INPUT.addEventListener("input", autoResize);
  INPUT.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); if (!SEND.disabled) sendMessage(); }
  });
  SEND.addEventListener("click", sendMessage);

  async function sendMessage() {
    const text = INPUT.value.trim();
    if (!text || sending) return;
    sending = true; SEND.disabled = true;
    WELCOME.hidden = true;
    appendMsg("user", text, Date.now() / 1000);
    INPUT.value = ""; autoResize();
    const typing = appendTyping();
    try {
      const data = await api("/web/chat", {
        method: "POST",
        body: JSON.stringify({ conversation_id: conversationId, message: text }),
      });
      conversationId = data.conversation.id;
      document.getElementById("chatTitle").textContent = data.conversation.title;
      markActive(conversationId);
      typing.remove();
      renderMessage(data.message);
      if (data.message.meta?.pending_action) {
        pendingAction = data.message.meta.pending_action;
        renderDraft(pendingAction, false);
      } else if (data.message.meta?.result) {
        pendingAction = null;
      }
      setStateLabel(data.message.meta?.state);
      MSG.scrollTop = MSG.scrollHeight;
      await loadSidebar();
    } catch (err) {
      typing.remove();
      appendError(err.message || "Something went wrong. Nothing was created.");
    } finally {
      sending = false; SEND.disabled = !INPUT.value.trim();
    }
  }

  // ── approval (Approve / Reject) ───────────────────────────────────────────
  async function decide(approved) {
    if (!pendingAction || !conversationId) return;
    const prev = pendingAction;
    pendingAction = null;
    sealDraft(prev.action_id, approved ? "Approving…" : "Rejecting…");
    try {
      const data = await api("/web/approve", {
        method: "POST",
        body: JSON.stringify({ conversation_id: conversationId, action_id: prev.action_id, approved }),
      });
      sealDraft(prev.action_id, approved ? "Approved" : "Rejected", approved ? "done" : "closed");
      renderMessage(data.message);
      if (data.message.meta?.result?.ticket_id) {
        setStateLabel("ticket_created");
      }
      MSG.scrollTop = MSG.scrollHeight;
    } catch (err) {
      appendError(err.message || "Could not complete the request.");
    }
  }

  // ── renderers ─────────────────────────────────────────────────────────────
  function appendMsg(role, content, ts) {
    const row = h("div", { class: "msg " + role },
      role === "assistant" ? h("div", { class: "bot-avatar" },
        h("svg", { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": "1.5", "stroke-linecap": "round" },
          h("path", { d: "M12 21V10" }),
          h("path", { d: "M12 10C10 6 6 5 3 6c3 0 5 1.5 6 4" }),
          h("path", { d: "M12 10c2-4 6-5 9-4-3 0-5 1.5-6 4" }))) : false,
      h("div", { class: "stack" },
        h("div", { class: "bubble" }, content),
        ts ? h("span", { class: "time" }, clock(ts)) : false));
    MSG.append(row);
    return row;
  }

  function appendError(msg) {
    const row = h("div", { class: "msg bot" },
      h("div", { class: "bot-avatar" }),
      h("div", { class: "stack" }, h("div", { class: "bubble err" }, msg)));
    MSG.append(row);
  }

  function appendTyping() {
    const row = h("div", { class: "msg bot", id: "typing" },
      h("div", { class: "bot-avatar" }),
      h("div", { class: "stack" }, h("div", { class: "bubble" },
        h("div", { class: "typing" }, h("i"), h("i"), h("i")))));
    MSG.append(row); MSG.scrollTop = MSG.scrollHeight;
    return row;
  }

  function renderMessage(m) {
    if (!m || !m.role) return;
    if (m.meta?.decision) {
      MSG.append(h("div", { class: "decision" }, h("span", {}, m.content)));
      return;
    }
    const row = appendMsg(m.role, m.content, m.at);
    if (m.role === "assistant") {
      const stack = row.querySelector(".stack");
      const meta = m.meta || {};
      if (meta.citations?.length) {
        const cites = h("div", { class: "cites", role: "list" });
        meta.citations.forEach((c) => cites.append(
          h("span", { class: "cite", role: "listitem", title: c.title }, h("b", {}, c.id), h("span", {}, c.title))));
        stack.append(cites);
      }
      if (meta.tool_calls?.length) {
        const details = h("details", { class: "trace" },
          h("summary", {}, "Tool calls (" + meta.tool_calls.length + ")"),
          h("ul", {}, ...meta.tool_calls.map((t) =>
            h("li", { class: t.ok ? "" : "bad" }, t.tool + " · " + (t.ok ? "ok" : "FAILED") + " · " + t.ms + " ms"))));
        stack.append(details);
      }
    }
    return row;
  }

  function renderDraft(pa, closed) {
    if (!pa || !pa.payload) return;
    const pl = pa.payload;
    const draft = h("div", { class: "draft" + (closed ? " closed" : ""), id: "draft-" + pa.action_id },
      h("header", {},
        h("svg", { class: "i", viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": "1.8", "stroke-linecap": "round", "stroke-linejoin": "round" },
          h("path", { d: "M4 8a2 2 0 0 0 0 4v0a2 2 0 0 1 0 4v2h16v-2a2 2 0 0 1 0-4v0a2 2 0 0 0 0-4V6H4z" }),
          h("path", { d: "M14 6v12", "stroke-dasharray": "2 3" })),
        pa.summary || "Ticket draft · waiting for approval"),
      h("dl", {},
        h("dt", {}, "Subject"), h("dd", {}, pl.subject || "—"),
        h("dt", {}, "Category"), h("dd", {}, pl.category || "—"),
        h("dt", {}, "Priority"), h("dd", {}, h("span", { class: "pill " + (pl.priority || "") }, pl.priority || "—")),
        h("dt", {}, "Department"), h("dd", {}, pl.department || "—"),
        pl.attempted_steps?.length
          ? [h("dt", {}, "Steps tried"), h("dd", {}, h("ul", {}, ...pl.attempted_steps.map((s) => h("li", {}, s))))]
          : [],
        pl.kb_refs?.length ? [h("dt", {}, "KB refs"), h("dd", {}, pl.kb_refs.join(", "))] : []),
      pl.description ? h("p", { class: "desc" }, pl.description) : false,
      !closed ? h("footer", {},
        h("button", { class: "btn ok", onclick: () => decide(true) }, "✓  Approve"),
        h("button", { class: "btn ghost", onclick: () => decide(false) }, "✕  Reject")) : false);
    const lastBot = [...MSG.querySelectorAll(".msg.bot")].pop();
    if (lastBot) lastBot.querySelector(".stack").append(draft);
    else MSG.append(draft);
  }

  function sealDraft(actionId, label, cls) {
    const el = document.getElementById("draft-" + actionId);
    if (!el) return;
    el.className = "draft " + (cls || "closed");
    const header = el.querySelector("header");
    if (header) header.lastChild.textContent = label;
    const footer = el.querySelector("footer");
    if (footer) footer.remove();
  }

  function setStateLabel(state) {
    const labels = { awaiting_approval: "Waiting for approval", ticket_created: "Ticket created", answered: "", not_documented: "", needs_info: "", refused: "Refused", off_topic: "" };
    document.getElementById("chatState").textContent = labels[state] || "";
  }

  // ── boot ─────────────────────────────────────────────────────────────────
  loadSidebar();
  const cid = new URLSearchParams(location.search).get("c");
  if (cid) openConversation(cid);
})();
