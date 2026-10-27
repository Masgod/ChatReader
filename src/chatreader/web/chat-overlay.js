"use strict";
// Chat overlay: a bubble appears when its voice starts and goes away after the hold time.
// Every viewer string goes through textContent, never HTML.
const stack = document.getElementById("stack");
const bubbles = new Map(); // id -> {el, timer}
const EXIT_MS = 350;
const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
let overlay = null;
let ready = Promise.resolve();
let fontUrl = null;

const EVENT_NOTES = {
  bits: (d) => "cheered " + (d ? d + " " : "") + "bits",
  subs: (d) => "subscribed" + (d ? " (" + d + ")" : ""),
  gifts: (d) => "gifted " + (d || "a sub"),
  raids: (d) => "raided with " + (d || "a crowd"),
  superchat: (d) => "sent a Super Chat" + (d ? " " + d : ""),
  members: (d) => "became a member" + (d ? " (" + d + ")" : ""),
};

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

async function loadOverlay() {
  try {
    const r = await fetch("/api/overlay");
    overlay = await r.json();
    applyTheme();
  } catch (e) {
    console.warn("overlay settings unavailable", e);
  }
}

function applyTheme() {
  const { config, theme, warning } = overlay;
  if (warning) console.warn(warning);
  const animation = reduced ? "fade" : theme.bubble.animation;
  stack.className = "pos-" + config.overlay_position + " anim-" + animation + " layout-" + theme.bubble.layout;
  const s = stack.style;
  s.setProperty("--bg", theme.bubble.background);
  s.setProperty("--fg", theme.bubble.color);
  s.setProperty("--radius", theme.bubble.radius + "px");
  s.setProperty("--ev-bg", theme.events.background);
  s.setProperty("--ev-fg", theme.events.color);
  s.setProperty("--name-fg", theme.sender.color);
  s.setProperty("--name-line", theme.sender.outline);
  s.setProperty("--pw", theme.bubble.portrait.width + "px");
  s.setProperty("--ph", theme.bubble.portrait.height + "px");
  s.setProperty("--s", config.overlay_scale / 100);
  if (theme.font && theme.font !== fontUrl) {
    fontUrl = theme.font;
    new FontFace("ThemeFont", "url(" + JSON.stringify(theme.font) + ")").load().then((f) => {
      document.fonts.add(f);
      s.setProperty("--font", '"ThemeFont", system-ui, sans-serif');
    }).catch(() => {});
  } else if (!theme.font) {
    fontUrl = null;
    s.removeProperty("--font");
  }
}

function rollExpression(theme) {
  let roll = Math.random();
  for (const e of theme.expressions) {
    if (roll < e.chance) return e.name;
    roll -= e.chance;
  }
  return theme.fallback;
}

function makeAvatar(m, theme) {
  const box = el("div", "avatar");
  const hero = theme.heroes.length ? theme.heroes[m.slot % theme.heroes.length] : null;
  const names = hero ? [rollExpression(theme), theme.fallback].filter((n, i, a) => n && hero.images[n] && a.indexOf(n) === i) : [];
  const initial = () => {
    box.className = "avatar initial";
    box.replaceChildren(document.createTextNode((m.user.trim()[0] || "?").toUpperCase()));
  };
  const tryImage = (i) => {
    if (i >= names.length) return initial();
    const img = new Image();
    img.alt = "";
    img.onerror = () => tryImage(i + 1);
    img.src = hero.images[names[i]];
    box.replaceChildren(img);
  };
  tryImage(0);
  return box;
}

function remove(id) {
  const b = bubbles.get(id);
  if (!b) return;
  bubbles.delete(id);
  clearTimeout(b.timer);
  b.el.classList.remove("speaking");
  b.el.classList.add("leaving");
  setTimeout(() => b.el.remove(), EXIT_MS);
}

function show(m) {
  if (!overlay || bubbles.has(m.id)) return;
  const { theme, config } = overlay;
  const isEvent = m.kind !== "chat";
  const bubble = el("div", "bubble speaking" + (isEvent ? " event" : ""));
  const body = el("div", "body");
  const content = el("div", "content");  // the text box in the "top" layout
  if (isEvent && EVENT_NOTES[m.kind]) content.append(el("div", "note", EVENT_NOTES[m.kind](m.detail)));
  if (m.text) content.append(el("div", "text", m.text));
  body.append(el("div", "name", m.user), content);
  bubble.append(makeAvatar(m, theme), body);
  stack.append(bubble);
  bubbles.set(m.id, { el: bubble, timer: null });
  while (bubbles.size > config.overlay_max_bubbles) remove(bubbles.keys().next().value);
}

function finish(m) {
  const b = bubbles.get(m.id);
  if (!b) return;
  b.el.classList.remove("speaking");
  const hold = overlay ? overlay.config.overlay_hold_seconds : 4;
  if (m.outcome === "skipped" || hold === 0) remove(m.id);
  else b.timer = setTimeout(() => remove(m.id), hold * 1000);
}

function connect() {
  const ws = new WebSocket("ws://" + location.host + "/ws/view");
  ws.onmessage = (e) => {
    let m;
    try { m = JSON.parse(e.data); } catch (err) { return; }
    if (m.t === "hello") {  // a fresh connection: bubbles from the old one will never get their end
      for (const id of [...bubbles.keys()]) remove(id);
      ready = loadOverlay();
    } else if (m.t === "config") ready = loadOverlay();
    else if (m.t === "start") ready.then(() => show(m));
    else if (m.t === "end") ready.then(() => finish(m));
  };
  ws.onclose = () => setTimeout(connect, 2000);
}
connect();
