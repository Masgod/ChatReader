// Shell: tab routing, API helper, pollers, header status. Tabs register themselves via App.onTab.
(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const TABS = ["live", "console", "settings"];
  const listeners = { tab: [], status: [] };
  const stops = [];
  let failing = 0;

  const App = {
    tab: "live",
    stopped: false,
    status: null,
    $,
    $$: (s, r = document) => [...r.querySelectorAll(s)],

    async api(path, opts = {}) {
      const init = { method: opts.method || (opts.body === undefined ? "GET" : "POST"), headers: {} };
      if (opts.body !== undefined) {
        init.headers["Content-Type"] = "application/json";
        init.body = JSON.stringify(opts.body);
      }
      const r = await fetch(path, init);
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw Object.assign(new Error(data.errors ? data.errors.join(" ") : r.statusText), { status: r.status, data });
      return data;
    },

    // Runs fn now and every ms while the page is visible; a throw marks the server unreachable.
    // fn returns false when it skipped (no request made), which says nothing about reachability.
    poll(fn, ms) {
      let timer = 0, dead = false, busy = false;
      const run = async () => {
        if (busy) return;
        clearTimeout(timer);
        if (dead) return;
        if (!document.hidden) {
          busy = true;
          try { if ((await fn()) !== false) App.reachable(true); } catch { App.reachable(false); }
          busy = false;
        }
        if (!dead) timer = setTimeout(run, ms);
      };
      const onVis = () => { if (!document.hidden) run(); };
      document.addEventListener("visibilitychange", onVis);
      run();
      const stop = () => { dead = true; clearTimeout(timer); document.removeEventListener("visibilitychange", onVis); };
      stops.push(stop);
      return stop;
    },

    reachable(ok) {
      failing = ok ? 0 : failing + 1;
      if (App.stopped) return;
      $("#banner").hidden = failing === 0;
    },

    stopAll(text) {
      App.stopped = true;
      stops.forEach((s) => s());
      $("#banner").hidden = true;
      $("#status-text").textContent = text;
      $("#dot").style.background = "var(--off)";
    },

    onTab(fn) { listeners.tab.push(fn); },
    onStatus(fn) { listeners.status.push(fn); },
    showTab,
  };
  window.App = App;

  function initialTab() {
    const hash = location.hash.slice(1);
    if (TABS.includes(hash)) return hash;
    if (location.pathname === "/dock") return "live";
    if (location.pathname === "/settings") return "settings";
    try { const t = localStorage.getItem("chatreader.tab"); if (TABS.includes(t)) return t; } catch { /* storage may be blocked */ }
    return "live";
  }

  function showTab(name, fromHash) {
    if (!TABS.includes(name)) name = "live";
    App.tab = name;
    for (const t of TABS) {
      const on = t === name;
      $("#tab-" + t).setAttribute("aria-selected", on);
      $("#tab-" + t).tabIndex = on ? 0 : -1;
      $("#panel-" + t).hidden = !on;
    }
    if (!fromHash && location.hash !== "#" + name) history.replaceState(null, "", "#" + name);
    try { localStorage.setItem("chatreader.tab", name); } catch { /* ignore */ }
    listeners.tab.forEach((fn) => fn(name));
  }

  for (const b of document.querySelectorAll("[data-tab]")) {
    b.onclick = () => showTab(b.dataset.tab);
    b.onkeydown = (e) => {
      const i = TABS.indexOf(App.tab) + (e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0);
      if (i !== TABS.indexOf(App.tab) && i >= 0 && i < TABS.length) { showTab(TABS[i]); $("#tab-" + TABS[i]).focus(); }
    };
  }
  window.addEventListener("hashchange", () => showTab(location.hash.slice(1), true));

  function headerStatus(s) {
    const live = Object.entries(s.sources).filter(([, x]) => x.configured && x.state === "connected").map(([n]) => n);
    $("#dot").style.background = live.length ? "var(--ok)" : "#5a5b60";
    const text = live.length ? "listening · " + live.join(" + ") : "idle";
    $("#status-text").textContent = (s.paused ? "paused · " : "") + text + (s.queue ? " · " + s.queue + " waiting" : "");
  }

  const uiButtons = document.querySelectorAll("button[data-ui]");
  const markUi = () => uiButtons.forEach((b) => b.setAttribute("aria-pressed", b.dataset.ui === document.documentElement.dataset.ui));
  uiButtons.forEach((b) => b.onclick = () => {
    document.documentElement.dataset.ui = b.dataset.ui;
    try { localStorage.setItem("ui", b.dataset.ui); } catch { /* private window: the choice lasts until the page closes */ }
    markUi();
  });
  markUi();

  showTab(initialTab(), true);
  App.poll(async () => {
    const s = await App.api("/api/status");
    if (s.error) throw new Error(s.error);
    App.status = s;
    headerStatus(s);
    listeners.status.forEach((fn) => fn(s));
  }, 2000);
})();
