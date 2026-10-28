// Touch style navigation: 4 big buttons, then a submenu, then the page. Mouse style keeps the tabs and ignores all of this.
(() => {
  const { $, $$ } = App;
  const root = document.documentElement;
  const page = (label, tab, sect) => ({ label, tab, sect });
  const GROUPS = {
    live: { title: "Live", pages: [page("Queue & controls", "live"), page("Console", "console")] },
    sources: { title: "Sources", pages: [page("Sources", "settings", "sect-sources")] },
    voice: {
      title: "Voice",
      pages: [
        page("Voices", "settings", "sect-voices"), page("Reading", "settings", "sect-reading"),
        page("Events", "settings", "sect-events"), page("Ignored users", "settings", "sect-ignored"),
      ],
    },
    system: { title: "Overlay & system", pages: [page("Chat overlay", "settings", "sect-overlay"), page("System", "settings", "sect-system")] },
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
    $$(".sect").forEach((s) => s.classList.toggle("cur", s.id === p.sect));
    show("page", p.label);
  }

  function openGroup(name) {
    group = GROUPS[name];
    if (group.pages.length === 1) return open(group.pages[0]);
    $("#subs").replaceChildren(...group.pages.map((p) => {
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
  $("#back").onclick = () => {
    if (root.dataset.view === "page" && group.pages.length > 1) show("sub", group.title);
    else show("home", "ChatReader");
  };
})();
