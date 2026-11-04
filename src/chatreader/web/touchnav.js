// Touch style navigation: 4 big buttons, then a submenu, then the page. Mouse style keeps the tabs and ignores all of this.
(() => {
  const { $, $$ } = App;
  const root = document.documentElement;
  const basic = (label, tab, sect) => ({ label, tab, sect, level: "basic" });
  const advanced = (label, tab, sect) => ({ label, tab, sect, level: "advanced" });
  const visible = (g) => g.pages.filter((p) => p.level === "basic" || root.dataset.level === "advanced");  // Basic lists only the basic pages
  const GROUPS = {
    live: { title: "Live", pages: [basic("Queue & controls", "live"), basic("Console", "console")] },
    sources: { title: "Sources", pages: [basic("Sources", "settings", "sect-sources"), basic("OBS", "settings", "sect-obs")] },
    voice: {
      title: "Voice",
      pages: [
        basic("Voices", "settings", "sect-voices"), advanced("Reading", "settings", "sect-reading"),
        advanced("Events", "settings", "sect-events"), advanced("Ignored users", "settings", "sect-ignored"), advanced("Pronunciations", "settings", "sect-pronunciations"),
      ],
    },
    system: { title: "Overlay & system", pages: [advanced("Chat overlay", "settings", "sect-overlay"), advanced("System", "settings", "sect-system")] },
  };
  let group = null;

  function show(view, title) {
    root.dataset.view = view;
    $("#title").textContent = title;
    $("#back").hidden = view === "home";
    window.scrollTo(0, 0);
  }

  function open(p) {
    App.showTab(p.tab);
    $$(".sect").forEach((s) => {
      s.classList.toggle("cur", s.id === p.sect);
      if (s.id === p.sect) s.open = true;  // settings.js folds every section but the first on narrow screens
    });
    show("page", p.label);
  }

  function openGroup(name) {
    group = GROUPS[name];
    const pages = visible(group);
    if (pages.length === 1) return open(pages[0]);
    $("#subs").replaceChildren(...pages.map((p) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "sub";
      b.textContent = p.label;
      b.onclick = () => open(p);
      return b;
    }));
    show("sub", group.title);
  }

  $$("[data-group]").forEach((b) => { b.onclick = () => openGroup(b.dataset.group); });
  $$("button[data-ui]").forEach((b) => b.addEventListener("click", () => show("home", "ChatReader")));  // a style switch starts over, so the title never says "System" in Mouse style
  $$("button[data-level-switch]").forEach((b) => b.addEventListener("click", () => show("home", "ChatReader")));  // the menu changes, so start over
  $("#back").onclick = () => {
    if (root.dataset.view === "page" && visible(group).length > 1) show("sub", group.title);
    else show("home", "ChatReader");
  };
})();
