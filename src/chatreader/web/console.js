// Console tab: chat outcomes and the app log, polled with a cursor.
(() => {
  const { $, api } = App;
  const MAX = 500;
  const box = $("#console-lines");
  let since = 0, following = true, scrollPaused = false;

  const GOOD = new Set(["queued", "played"]);
  const BAD = new Set(["failed"]);
  const tagClass = (o) => (GOOD.has(o) ? "good" : BAD.has(o) ? "bad" : "mid");

  const span = (cls, text) => { const s = document.createElement("span"); s.className = cls; s.textContent = text; return s; };
  const clock = (ts) => new Date(ts * 1000).toLocaleTimeString([], { hour12: false });

  function line(e) {
    const div = document.createElement("div");
    div.className = "line"; div.dataset.kind = e.kind; div.dataset.level = e.level;
    div.append(span("t", clock(e.ts)));
    if (e.kind === "chat") {
      div.append(span("u", e.user || "—"), span("m", e.text), span("tag " + tagClass(e.outcome), e.outcome));
    } else {
      div.append(span("lvl", e.level), span("lg", e.logger || ""), span("m", e.message));
    }
    return div;
  }

  const atBottom = () => box.scrollHeight - box.scrollTop - box.clientHeight < 24;

  function add(events) {
    if (!events.length) return;
    const stick = following && !scrollPaused;
    box.append(...events.map(line));
    while (box.childElementCount > MAX) box.firstElementChild.remove();
    if (stick) box.scrollTop = box.scrollHeight;
  }

  async function load() {
    if (App.tab !== "console") return false;
    const r = await api("/api/events?since=" + since);
    since = r.last;  // also follows the counter back down if the app restarted
    add(r.events);
  }

  box.addEventListener("scroll", () => { following = atBottom(); $("#btn-jump").hidden = following; });
  $("#btn-jump").onclick = () => { box.scrollTop = box.scrollHeight; following = true; $("#btn-jump").hidden = true; };

  for (const f of ["all", "chat", "log"]) {
    $("#filter-" + f).onclick = () => {
      box.dataset.filter = f;
      for (const g of ["all", "chat", "log"]) $("#filter-" + g).setAttribute("aria-pressed", g === f);
    };
  }
  box.dataset.filter = "all";

  $("#btn-pause-scroll").onclick = (e) => {
    scrollPaused = !scrollPaused;
    e.target.textContent = scrollPaused ? "Resume scrolling" : "Pause scrolling";
    if (!scrollPaused && following) box.scrollTop = box.scrollHeight;
  };
  $("#btn-clear-view").onclick = () => { box.replaceChildren(); $("#btn-jump").hidden = true; following = true; };

  const dbg = $("#toggle-debug");
  async function loadDebug() {
    try { dbg.setAttribute("aria-checked", !!(await api("/api/config")).debug); } catch { /* the banner covers an unreachable server */ }
  }
  dbg.onclick = async () => {
    const want = dbg.getAttribute("aria-checked") !== "true";
    dbg.setAttribute("aria-checked", want);
    try { await api("/api/toggle", { body: { name: "debug", value: want } }); }
    catch { dbg.setAttribute("aria-checked", !want); }
  };

  App.poll(load, 1000);
  App.onTab((t) => { if (t === "console") { loadDebug(); load().catch(() => {}); } });
  if (App.tab === "console") loadDebug();
})();
