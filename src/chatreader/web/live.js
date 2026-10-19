// Live tab: status rows, controls and the queue.
(() => {
  const { $, api } = App;
  let paused = false, lastQueue = "", quitTimer = 0, quitArmed = false;

  function say(text) { $("#live-msg").textContent = text; }

  function row(name, text, level) {
    $("#st-" + name).textContent = text;
    $("#d-" + name).className = "dot " + level;
  }

  function renderStatus(s) {
    for (const name of ["twitch", "youtube"]) {
      const x = s.sources[name];
      if (!x.configured) row(name, "off", "");
      else row(name, x.state, x.state === "connected" ? "ok" : ["failed", "error"].includes(x.state) ? "err" : "warn");
    }
    row("overlay", s.overlay ? "connected" : "not connected", s.overlay ? "ok" : "warn");
    row("model", s.model, s.model === "ready" ? "ok" : s.model === "error" ? "err" : "warn");
    paused = s.paused;
    $("#btn-pause").textContent = paused ? "Resume" : "Pause";
  }
  App.onStatus(renderStatus);
  if (App.status) renderStatus(App.status);

  function item(i, playing) {
    const li = document.createElement("li");
    if (playing) li.className = "playing";
    const who = document.createElement("span"); who.className = "who"; who.textContent = i.user || "—";
    const what = document.createElement("span"); what.className = "what"; what.textContent = i.text;
    li.append(who, what);
    if (playing) {
      const tag = document.createElement("span"); tag.className = "now-tag"; tag.textContent = "now";
      li.append(tag);
    } else {
      const x = document.createElement("button");
      x.type = "button"; x.className = "x"; x.textContent = "×"; x.title = "Remove"; x.setAttribute("aria-label", "Remove message from " + (i.user || "unknown"));
      x.onclick = () => removeItem(i.id);
      li.append(x);
    }
    return li;
  }

  async function loadQueue() {
    if (App.tab !== "live") return false;
    const q = await api("/api/queue");
    const key = JSON.stringify(q);
    if (key === lastQueue) return true;  // keep the DOM (and focus) still while nothing changed
    lastQueue = key;
    const rows = [];
    if (q.playing) rows.push(item(q.playing, true));
    rows.push(...q.waiting.map((i) => item(i, false)));
    $("#queue-list").replaceChildren(...rows);
    $("#queue-empty").hidden = rows.length > 0;
    $("#queue-count").textContent = q.waiting.length ? q.waiting.length + " waiting" : "";
    $("#btn-clear").disabled = q.waiting.length === 0;
  }

  async function removeItem(id) {
    try { await api("/api/queue/remove", { body: { id } }); }
    catch (e) { if (e.status !== 404) say("Could not remove that message"); }  // 404: it already played
    lastQueue = ""; loadQueue().catch(() => {});
  }

  $("#btn-clear").onclick = async () => {
    try { const r = await api("/api/queue/clear", { body: {} }); say(r.removed ? "Cleared " + r.removed + " waiting" : ""); }
    catch { say("Could not clear the queue"); }
    lastQueue = ""; loadQueue().catch(() => {});
  };

  async function control(action) {
    try { await api("/api/control", { body: { action } }); say(""); }
    catch { say("That did not work"); }
    App.status && api("/api/status").then(renderStatus).catch(() => {});
  }
  $("#btn-pause").onclick = () => control(paused ? "resume" : "pause");
  $("#btn-skip").onclick = () => control("skip");

  $("#btn-copy").onclick = async () => {
    const url = location.origin + "/overlay", box = $("#overlay-url");
    try { await navigator.clipboard.writeText(url); box.hidden = true; say("Overlay URL copied"); }
    catch { box.value = url; box.hidden = false; box.focus(); box.select(); say("Copy it from the box below"); }
  };

  $("#btn-quit").onclick = async () => {
    const b = $("#btn-quit");
    if (!quitArmed) {
      quitArmed = true; b.textContent = "Really quit?"; b.classList.add("armed");
      quitTimer = setTimeout(() => { quitArmed = false; b.textContent = "Quit"; b.classList.remove("armed"); }, 4000);
      return;
    }
    clearTimeout(quitTimer);
    try { await api("/api/control", { body: { action: "quit" } }); } catch { /* the server may die before answering */ }
    App.stopAll("ChatReader stopped");
    say("ChatReader stopped. Start it again from the Start menu or your shortcut.");
    for (const id of ["btn-pause", "btn-skip", "btn-copy", "btn-quit", "btn-clear"]) $("#" + id).disabled = true;
  };

  App.poll(loadQueue, 1000);
  App.onTab((t) => { if (t === "live") loadQueue().catch(() => {}); });
})();
