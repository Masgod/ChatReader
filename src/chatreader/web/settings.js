// Settings tab: form state, dirty tracking, save, voice pickers.
(() => {
  const { $, $$, api } = App;
  const SAMPLES = { pt: "Olá, este é um teste de voz.", en: "Hello, this is a voice test." };
  let state = null, saved = "", savedPort = null, savedThreads = null, flashTimer = 0;
  let voices = { pt: [], en: [] };

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
    for (const b of $$("[data-lang]")) b.setAttribute("aria-pressed", state.default_lang === b.dataset.lang);
    for (const box of $$("[data-num]")) $("input", box).value = state[box.dataset.num];
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

  // --- voices: a grouped <select> per language, or a plain text box when the list is unavailable ---
  function fillVoices() {
    for (const lang of ["pt", "en"]) {
      const wrap = $("#wrap-voice_" + lang), id = "voice_" + lang, list = voices[lang];
      let el = $("#" + id);
      if (!list.length) {
        if (el.tagName !== "INPUT") {
          const input = document.createElement("input");
          input.type = "text"; input.id = id; input.dataset.key = id; input.dataset.voice = lang;
          input.autocomplete = "off"; input.spellcheck = false; input.setAttribute("aria-label", lang === "pt" ? "Portuguese voice" : "English voice");
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

  for (const b of $$("[data-toggle]")) b.onclick = () => { state[b.dataset.toggle] = !state[b.dataset.toggle]; refresh(); };
  for (const b of $$("[data-lang]")) b.onclick = () => { state.default_lang = b.dataset.lang; refresh(); };
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
    try {
      await api("/api/test", { body: { text: SAMPLES[lang] } });
      flash("Playing the saved " + (lang === "pt" ? "Portuguese" : "English") + " voice…");
    } catch { flash("Test failed", "bad"); }
  }
  $("#btn-test").onclick = () => speak(state.default_lang);
  for (const b of $$("[data-preview]")) b.onclick = () => speak(b.dataset.preview);

  $("#btn-save").onclick = async () => {
    const errors = $("#errors"); errors.replaceChildren();
    try {
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
  App.onTab((t) => { if (t === "settings" && state && !dirty()) api("/api/config").then(load).catch(() => {}); });

  Promise.all([api("/api/voices").catch(() => ({ pt: [], en: [] })), api("/api/config")])
    .then(([v, cfg]) => { voices = { pt: v.pt || [], en: v.en || [] }; load(cfg); })
    .catch(() => {});
})();
