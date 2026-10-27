// Settings tab: form state, dirty tracking, save, voice pickers.
(() => {
  const { $, $$, api } = App;
  const SAMPLES = {
    pt: "Olá, este é um teste de voz.", en: "Hello, this is a voice test.", es: "Hola, esta es una prueba de voz.",
    fr: "Bonjour, ceci est un test de voix.", it: "Ciao, questa è una prova della voce.",
  };
  let state = null, saved = "", savedPort = null, savedThreads = null, flashTimer = 0;
  let voices = {}, languages = [];  // languages: [{code, name, beta}] from /api/languages

  const snap = () => JSON.stringify(state);
  const clamp = (n, lo, hi) => Math.min(hi, Math.max(lo, n));
  const dirty = () => state !== null && snap() !== saved;

  function flash(text, cls = "ok") {
    const m = $("#msg"); m.textContent = text; m.className = cls;
    clearTimeout(flashTimer);
    flashTimer = setTimeout(refresh, 2200);
  }

  function setNum(key, raw, lo, hi) {
    const n = parseInt(String(raw).replace(/\D/g, ""), 10);
    state[key] = isNaN(n) ? state[key] : clamp(n, lo, hi);
    refresh();
  }

  function refresh() {
    if (!state) return;
    for (const el of $$("[data-key]")) if (document.activeElement !== el) el.value = state[el.dataset.key] ?? "";
    for (const b of $$("[data-toggle]")) b.setAttribute("aria-checked", !!state[b.dataset.toggle]);
    for (const b of $$("[data-lang]")) {
      b.setAttribute("aria-pressed", state.default_lang === b.dataset.lang);
      b.hidden = !state.languages.includes(b.dataset.lang);
    }
    for (const b of $$("[data-lang-toggle]")) b.setAttribute("aria-pressed", state.languages.includes(b.dataset.langToggle));
    for (const r of $$("[data-voice-row]")) r.hidden = !state.languages.includes(r.dataset.voiceRow);
    for (const box of $$("[data-num]")) $("input", box).value = state[box.dataset.num];
    for (const b of $$("[data-choice]")) b.setAttribute("aria-pressed", state[b.dataset.choice] === b.dataset.value);
    for (const g of $$("[data-roles]")) {
      const list = state[g.dataset.roles] || [];
      for (const b of $$("[data-role]", g)) b.setAttribute("aria-pressed", b.dataset.role ? list.includes(b.dataset.role) : list.length === 0);
    }
    $("#port").value = state.port;

    $("#chips").replaceChildren(...state.ignored_users.map((name) => {
      const c = document.createElement("div"); c.className = "chip"; c.append(name);
      const x = document.createElement("button");
      x.type = "button"; x.textContent = "×"; x.title = "Remove"; x.setAttribute("aria-label", "Remove " + name);
      x.onclick = () => { state.ignored_users = state.ignored_users.filter((u) => u !== name); refresh(); };
      c.append(x); return c;
    }));
    $("#ignored-count").textContent = state.ignored_users.length;
    $("#speed-val").textContent = Number(state.speed).toFixed(2).replace(/0$/, "") + "×";

    const hint = (id, changed, base) => {
      const h = $(id); h.textContent = changed ? "Restart required to apply" : base; h.className = "hint" + (changed ? " warn" : "");
    };
    hint("#threads-hint", state.cpu_threads !== savedThreads, "Used for speech · restart required to change");
    hint("#port-hint", state.port !== savedPort, "Local server · restart required to change");

    const d = dirty();
    $("#btn-save").disabled = !d;
    const m = $("#msg"); m.textContent = d ? "Unsaved changes" : "All changes saved"; m.className = d ? "dirty" : "";
  }

  function load(cfg) {
    state = cfg; saved = snap(); savedPort = cfg.port; savedThreads = cfg.cpu_threads;
    fillVoices();
    fillThemes();
    refresh();
  }

  function bindKey(el) {
    const onChange = () => {
      const k = el.dataset.key;
      state[k] = el.dataset.type === "number" ? Number(el.value)
        : k === "twitch_channel" ? el.value.replace(/^.*twitch\.tv\//i, "").trim() : el.value;
      refresh();
    };
    el.addEventListener("input", onChange);
    el.addEventListener("change", onChange);
  }
  $$("[data-key]").forEach(bindKey);

  // --- languages: toggles, default-language buttons and one voice row per supported language (built once) ---
  function el(tag, cls, text) {
    const e = document.createElement(tag); if (cls) e.className = cls; if (text) e.textContent = text; return e;
  }

  function voiceRow({ code, name }) {
    const row = el("div", "row grid"); row.dataset.voiceRow = code;
    const label = el("label"); label.htmlFor = "voice_" + code;
    label.append(el("div", "name", name + " voice"), el("div", "hint", "Kokoro voice"));
    const select = el("select"); select.id = "voice_" + code; select.dataset.key = "voice_" + code; select.dataset.voice = code;
    const wrap = el("div", "field grow"); wrap.id = "wrap-voice_" + code; wrap.append(select); bindKey(select);
    const play = el("button", "btn icon", "▶"); play.type = "button"; play.dataset.preview = code;
    play.title = "Preview the saved " + name + " voice"; play.setAttribute("aria-label", "Preview " + name + " voice");
    play.onclick = () => speak(code);
    const pick = el("div", "pick"); pick.append(wrap, play);
    row.append(label, pick);
    return row;
  }

  function toggleLang(code) {
    const on = state.languages.includes(code);
    if (on && state.languages.length === 1) return;  // at least one language stays on
    state.languages = languages.map((l) => l.code).filter((c) => (c === code ? !on : state.languages.includes(c)));
    if (!state.languages.includes(state.default_lang)) state.default_lang = state.languages[0];
    refresh();
  }

  function buildLanguages() {
    const checks = $("#lang-checks"), def = $("#default-lang"), rows = $("#voice-rows");
    checks.replaceChildren(); def.replaceChildren(); rows.replaceChildren();
    for (const l of languages) {
      const toggle = el("button", "", l.name); toggle.type = "button"; toggle.dataset.langToggle = l.code;
      if (l.beta) toggle.append(el("span", "tag", "beta"));
      toggle.onclick = () => toggleLang(l.code);
      const pick = el("button", "", l.name); pick.type = "button"; pick.dataset.lang = l.code;
      pick.onclick = () => { state.default_lang = l.code; refresh(); };
      checks.append(toggle); def.append(pick); rows.append(voiceRow(l));
    }
  }

  // --- voices: a grouped <select> per language, or a plain text box when the list is unavailable ---
  function fillVoices() {
    for (const { code: lang, name } of languages) {
      const wrap = $("#wrap-voice_" + lang), id = "voice_" + lang, list = voices[lang] || [];
      let el = $("#" + id);
      if (!list.length) {
        if (el.tagName !== "INPUT") {
          const input = document.createElement("input");
          input.type = "text"; input.id = id; input.dataset.key = id; input.dataset.voice = lang;
          input.autocomplete = "off"; input.spellcheck = false; input.setAttribute("aria-label", name + " voice");
          wrap.replaceChildren(input); bindKey(input);
        }
        continue;
      }
      if (el.tagName !== "SELECT") {
        el = document.createElement("select"); el.id = id; el.dataset.key = id; el.dataset.voice = lang;
        wrap.replaceChildren(el); bindKey(el);
      }
      const groups = { female: [], male: [] }, known = new Set();
      for (const v of list) {
        known.add(v.id);
        const o = document.createElement("option"); o.value = v.id; o.textContent = v.label;
        groups[/\(male\)/.test(v.label) ? "male" : "female"].push(o);
      }
      const parts = [];
      for (const [name, opts] of Object.entries(groups)) {
        if (!opts.length) continue;
        const g = document.createElement("optgroup"); g.label = name === "female" ? "Female" : "Male"; g.append(...opts); parts.push(g);
      }
      const cur = state && state[id];
      if (cur && !known.has(cur)) {  // a hand-edited voice stays selectable instead of silently changing
        const o = document.createElement("option"); o.value = cur; o.textContent = cur + " (custom)"; parts.unshift(o);
      }
      el.replaceChildren(...parts);
    }
  }

  // --- chat overlay: theme list, position buttons, URL and test bubble ---
  let themes = [];
  function fillThemes() {
    const sel = $("#overlay_theme"), cur = state && state.overlay_theme, known = new Set();
    const opts = themes.map((t) => {
      known.add(t.name);
      const o = el("option", "", t.valid ? t.title : t.name + " — " + t.error); o.value = t.name; o.disabled = !t.valid; return o;
    });
    if (cur && !known.has(cur)) { const o = el("option", "", cur + " (not found)"); o.value = cur; opts.unshift(o); }
    sel.replaceChildren(...opts);
  }
  const loadThemes = () => api("/api/themes").then((t) => { themes = t; fillThemes(); refresh(); }).catch(() => {});

  for (const b of $$("[data-choice]")) b.onclick = () => { state[b.dataset.choice] = b.dataset.value; refresh(); };
  $("#chat-overlay-url").value = location.origin + "/chat-overlay";
  $("#copy-chat-url").onclick = async () => {
    const box = $("#chat-overlay-url");
    try { await navigator.clipboard.writeText(box.value); flash("Chat overlay URL copied"); }
    catch { box.focus(); box.select(); flash("Copy it from the box"); }
  };
  $("#test-bubble").onclick = async () => {
    try { await api("/api/view-test", { body: {} }); flash("Test bubble sent · it uses the saved settings"); }
    catch { flash("Test failed", "bad"); }
  };

  for (const b of $$("[data-toggle]")) b.onclick = () => { state[b.dataset.toggle] = !state[b.dataset.toggle]; refresh(); };
  for (const g of $$("[data-roles]")) for (const b of $$("[data-role]", g)) b.onclick = () => {
    const key = g.dataset.roles, role = b.dataset.role, list = state[key];
    state[key] = !role ? [] : list.includes(role) ? list.filter((r) => r !== role) : [...list, role];
    refresh();
  };
  for (const box of $$("[data-num]")) {
    const { num, min, max, step } = box.dataset, [lo, hi, st] = [+min, +max, +step];
    $("input", box).onchange = (e) => setNum(num, e.target.value, lo, hi);
    for (const b of $$("button", box)) b.onclick = () => { state[num] = clamp(state[num] + st * +b.dataset.d, lo, hi); refresh(); };
  }
  $("#port").onchange = (e) => setNum("port", e.target.value, 1, 65535);

  $("#add").onsubmit = (e) => {
    e.preventDefault();
    const input = $("#new-user");
    const names = input.value.split(/[\s,]+/).map((x) => x.toLowerCase().replace(/^@/, "")).filter((x) => x && !state.ignored_users.includes(x));
    if (names.length) state.ignored_users = [...state.ignored_users, ...new Set(names)];
    input.value = ""; refresh();
  };

  async function speak(lang) {
    const name = languages.find((l) => l.code === lang).name;
    if (!JSON.parse(saved).languages.includes(lang)) { flash("Save first, then preview the " + name + " voice"); return; }
    try {
      await api("/api/test", { body: { text: SAMPLES[lang], lang } });
      flash("Playing the saved " + name + " voice…");
    } catch { flash("Test failed", "bad"); }
  }
  $("#btn-test").onclick = () => speak(state.default_lang);

  $("#btn-save").onclick = async () => {
    const errors = $("#errors"); errors.replaceChildren();
    try {
      // The Console debug switch saves on its own; do not let this form silently undo it.
      const live = await api("/api/config");
      if (state.debug === JSON.parse(saved).debug) state.debug = live.debug;
      await api("/api/config", { method: "PUT", body: state });
      const portWas = savedPort, cfg = await api("/api/config");
      load(cfg);
      flash(cfg.port !== portWas ? "Saved · restart to apply new port" : "Saved");
    } catch (e) {
      if (e.status === 422 || e.status === 500) {
        for (const msg of (e.data && e.data.errors) || ["Save failed"]) { const li = document.createElement("li"); li.textContent = msg; errors.append(li); }
        flash("Not saved", "bad");
      } else flash("Not saved · server unreachable", "bad");
    }
  };

  App.onStatus((s) => {
    const anySource = Object.values(s.sources).some((x) => x.configured);
    const items = { "chk-model": s.model === "ready", "chk-source": anySource, "chk-overlay": s.overlay };
    for (const [id, ok] of Object.entries(items)) {
      const li = $("#" + id); li.dataset.ok = ok; $(".mark", li).textContent = ok ? "✓" : "○";
    }
    $("#checklist").hidden = Object.values(items).every(Boolean);
  });

  // Sections: open by default, collapsed below 480 px except the first.
  if (matchMedia("(max-width: 479px)").matches) $$("details.sect").slice(1).forEach((d) => d.removeAttribute("open"));

  // The Console debug switch can change config behind this form's back; re-read when coming back if nothing is unsaved.
  App.onTab((t) => {
    if (t !== "settings") return;
    loadThemes();  // a theme folder may have been added while the page was open
    if (state && !dirty()) api("/api/config").then(load).catch(() => {});
  });

  Promise.all([api("/api/voices").catch(() => ({})), api("/api/config"), api("/api/languages"), api("/api/themes").catch(() => [])])
    .then(([v, cfg, langs, t]) => { voices = v; languages = langs; themes = t; buildLanguages(); load(cfg); })
    .catch(() => {});
})();
