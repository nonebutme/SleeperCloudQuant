(function () {
  "use strict";

  const root = document.documentElement;
  const storageKey = "scq-quant-ui-standard-theme";

  function currentTheme() {
    return root.dataset.theme === "dark" ? "dark" : "light";
  }

  function updateThemeButton(button) {
    if (!button) return;
    const dark = currentTheme() === "dark";
    button.textContent = dark ? "☀ 切换亮色" : "◐ 暗色盯盘";
    button.setAttribute("aria-label", dark ? "切换到亮色主题" : "切换到暗色盯盘主题");
    button.setAttribute("aria-pressed", String(dark));
  }

  function refreshVTables() {
    if (!window.AppVTable) return;
    window.AppVTable.releaseAll();
    window.requestAnimationFrame(() => window.AppVTable.enhanceAll(document));
  }

  function applyTheme(theme, persist = true) {
    root.dataset.theme = theme === "dark" ? "dark" : "light";
    updateThemeButton(document.querySelector(".quant-ui-theme-toggle"));
    if (persist) {
      try {
        localStorage.setItem(storageKey, currentTheme());
      } catch (_error) {
        // Theme persistence is optional in restricted browser environments.
      }
    }
    refreshVTables();
  }

  function preferredTheme() {
    try {
      const saved = localStorage.getItem(storageKey);
      if (saved === "dark" || saved === "light") return saved;
    } catch (_error) {
      // Fall through to the operating-system preference.
    }
    return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }

  function mountTopbarControls() {
    const topbar = document.querySelector(".topbar");
    const feedback = document.querySelector("#global-feedback");
    if (!topbar || !feedback || topbar.querySelector(".quant-ui-top-actions")) return;

    const actions = document.createElement("div");
    actions.className = "quant-ui-top-actions";

    const badge = document.createElement("span");
    badge.className = "quant-ui-standard-badge";
    badge.textContent = "量化 UI 规范 · 全局生效";

    const themeButton = document.createElement("button");
    themeButton.type = "button";
    themeButton.className = "quant-ui-theme-toggle";
    themeButton.addEventListener("click", () => applyTheme(currentTheme() === "dark" ? "light" : "dark"));

    actions.append(badge, feedback, themeButton);
    topbar.append(actions);
    updateThemeButton(themeButton);
  }

  function updateBreadcrumb() {
    const eyebrow = document.querySelector(".topbar .eyebrow");
    const title = document.querySelector("#page-title")?.textContent?.trim();
    if (eyebrow && title) eyebrow.textContent = `量化研究平台 / ${title}`;
  }

  function markFinancialState(element) {
    if (!(element instanceof HTMLElement) || element.dataset.quantA11y === "true") return;
    const positive = element.classList.contains("market-rise") || element.classList.contains("is-rise");
    const negative = element.classList.contains("market-fall") || element.classList.contains("is-fall");
    if (!positive && !negative) return;
    element.dataset.quantA11y = "true";
    const direction = positive ? "上涨或盈利" : "下跌或亏损";
    if (!element.getAttribute("aria-label")) {
      element.setAttribute("aria-label", `${direction}：${element.textContent.trim()}`);
    }
  }

  function enhanceSemantics(scope = document) {
    scope.querySelectorAll?.(".market-rise, .market-fall, .is-rise, .is-fall").forEach(markFinancialState);
  }

  function start() {
    root.classList.add("quant-ui-standard");
    applyTheme(preferredTheme(), false);
    mountTopbarControls();
    updateBreadcrumb();
    enhanceSemantics(document);

    const pageTitle = document.querySelector("#page-title");
    if (pageTitle) new MutationObserver(updateBreadcrumb).observe(pageTitle, { childList: true, subtree: true });
    new MutationObserver((records) => {
      records.forEach((record) => record.addedNodes.forEach((node) => {
        if (node instanceof HTMLElement) {
          markFinancialState(node);
          enhanceSemantics(node);
        }
      }));
    }).observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
  else start();
})();
