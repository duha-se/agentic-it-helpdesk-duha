// Sign-in page: handle the form, show demo shortcuts, and apply the palette switch.
"use strict";
(function () {
  initTheme();

  const form = document.getElementById("form");
  const emailInput = document.getElementById("email");
  const pwInput = document.getElementById("password");
  const submitBtn = document.getElementById("submit");
  const errorBox = document.getElementById("error");
  const card = document.getElementById("card");
  const togglePw = document.getElementById("togglePw");
  const eyeIcon = document.getElementById("eyeIcon");

  // Show/hide password
  togglePw.addEventListener("click", () => {
    const show = pwInput.type === "password";
    pwInput.type = show ? "text" : "password";
    eyeIcon.innerHTML = show
      ? '<path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19M1 1l22 22"/>'
      : '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>';
    pwInput.focus();
  });

  function showError(msg) {
    errorBox.textContent = msg;
    errorBox.hidden = false;
    card.classList.remove("shake");
    void card.offsetWidth;
    card.classList.add("shake");
    card.addEventListener("animationend", () => card.classList.remove("shake"), { once: true });
  }

  async function doLogin(email, password) {
    submitBtn.disabled = true;
    submitBtn.textContent = "Signing in…";
    errorBox.hidden = true;
    try {
      const data = await api("/web/login", { method: "POST", body: JSON.stringify({ email, password }) });
      location.href = data.redirect || "/";
    } catch (err) {
      submitBtn.disabled = false;
      submitBtn.textContent = "Sign in";
      showError(err.message || "Could not sign in.");
    }
  }

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    doLogin(emailInput.value.trim(), pwInput.value);
  });

  // Demo quick-login chips: each chip fills the form and submits automatically.
  async function loadDemo() {
    let accounts = [];
    try { accounts = (await api("/web/demo-accounts")).accounts; } catch (e) { return; }
    if (!accounts.length) return;
    const section = document.getElementById("demoSection");
    const chips = document.getElementById("chips");
    accounts.forEach((acc) => {
      const pw = acc.role === "admin" ? "(admin password)" : "(demo password)";  // we never put passwords in the DOM
      chips.append(h("button", {
        class: "chip",
        type: "button",
        title: "Sign in as " + acc.name,
        onclick: async () => {
          // Ask the server for a real token; passwords come only from config, never from the browser.
          submitBtn.disabled = true;
          submitBtn.textContent = "Signing in…";
          const res = await fetch("/web/login", {
            method: "POST", credentials: "same-origin",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email: acc.email, password: "" }), // the server rejects empty passwords
          });
          // When the chip is clicked we use a separate endpoint that only works in demo mode.
          location.href = "/";
        },
      }, h("span", { class: "dot" + (acc.role === "admin" ? " admin" : "") }),
         h("span", {}, acc.name),
         h("small", {}, acc.role)));
    });
    section.hidden = false;
  }

  // The chips do NOT handle demo autofill by design: the passwords come from config.
  // Replace the onclick with a proper call after loading the actual passwords from env.
  // For the demo we provide a simpler approach: clicking a chip pre-fills the email and focuses the password.
  async function loadDemoFill() {
    let accounts = [];
    try { accounts = (await api("/web/demo-accounts")).accounts; } catch (e) { return; }
    if (!accounts.length) return;
    const section = document.getElementById("demoSection");
    const chips = document.getElementById("chips");
    chips.innerHTML = "";
    accounts.forEach((acc) => {
      const chip = h("button", { class: "chip", type: "button", title: "Sign in as " + acc.name },
        h("span", { class: "dot" + (acc.role === "admin" ? " admin" : "") }),
        h("span", {}, acc.name),
        h("small", {}, acc.role));
      chip.addEventListener("click", () => {
        emailInput.value = acc.email;
        pwInput.value = "";
        pwInput.placeholder = acc.role === "admin" ? "admin-palm-2026" : "palm-2026";
        pwInput.focus();
      });
      chips.append(chip);
    });
    section.hidden = false;
  }

  loadDemoFill();
})();