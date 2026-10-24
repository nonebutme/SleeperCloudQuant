(function () {
  "use strict";

  const instances = new Map();
  let enhancementScheduled = false;
  let observer = null;

  function normalizeText(value) {
    return String(value ?? "").replace(/\s+/g, " ").trim();
  }

  function integer(value, fallback) {
    const parsed = Math.round(Number(value));
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function cssToken(name, fallback) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
  }

  function designTokens() {
    return {
      primary: cssToken("--q-primary", "#1677ff"),
      profit: cssToken("--q-profit", "#f53f3f"),
      loss: cssToken("--q-loss", "#00b42a"),
      flat: cssToken("--q-flat", "#86909c"),
      text: cssToken("--q-text-1", "#1d2129"),
      textSecondary: cssToken("--q-text-2", "#4e5969"),
      card: cssToken("--q-bg-card", "#ffffff"),
      zebra: cssToken("--q-bg-zebra", "#f7f8fa"),
      border: cssToken("--q-border", "#e5e6eb"),
      selected: cssToken("--q-primary-soft", "#e8f3ff"),
    };
  }

  function tableMode(table) {
    const explicit = table.dataset.vtableMode;
    if (["market", "backtest", "factor", "edit", "governance"].includes(explicit)) return explicit;
    if (table.closest("#page-market")) return "market";
    if (table.closest("#page-factor")) return "factor";
    if (table.closest("#page-backtest, #page-reporting, #page-report-management")) return "backtest";
    return "standard";
  }

  function modeRowHeight(mode) {
    if (mode === "market") return 32;
    if (mode === "edit") return 48;
    if (mode === "governance") return 44;
    return 40;
  }

  function financialDirection(title, value) {
    const label = String(title || "").toLowerCase();
    if (!/(收益|涨跌|回报|盈亏|年化|超额|回撤|损失|return|profit|pnl|alpha|drawdown|loss)/i.test(label)) return 0;
    const number = Number(String(value ?? "").replace(/[,%↑↓→\s]/g, ""));
    if (!Number.isFinite(number) || number === 0) return 0;
    return number > 0 ? 1 : -1;
  }

  function formatFinancialValue(title, value) {
    const text = normalizeText(value);
    if (!text || /[↑↓→]$/.test(text)) return text;
    const direction = financialDirection(title, text);
    if (direction > 0) return `${text} ↑`;
    if (direction < 0) return `${text} ↓`;
    return text;
  }

  function tableSignature(table) {
    const rows = Array.from(table.rows)
      .map((row) => {
        const state = `${row.hidden ? "1" : "0"}:${row.className}:${row.getAttribute("aria-selected") || ""}`;
        const cells = Array.from(row.cells).map((cell) => {
          const controls = Array.from(cell.querySelectorAll("button, a[href]"))
            .map((control) => `${control.disabled ? "1" : "0"}:${normalizeText(control.textContent)}`)
            .join("\u001d");
          return `${normalizeText(cell.textContent)}:${controls}`;
        }).join("\u001f");
        return `${state}:${cells}`;
      })
      .join("\u001e");
    return `${document.documentElement.dataset.theme || "light"}:${rows}`;
  }

  function collectActions(cell) {
    return Array.from(cell.querySelectorAll("button, a[href]")).filter((element) => !element.disabled);
  }

  function parseNativeTable(table) {
    const headerRow = table.tHead?.rows?.[0] || table.rows?.[0];
    if (!headerRow) return null;
    const headerCells = Array.from(headerRow.cells);
    if (!headerCells.length) return null;
    const tokens = designTokens();
    const columns = headerCells.map((cell, index) => {
      const title = normalizeText(cell.textContent) || `列 ${index + 1}`;
      const cellType = cell.dataset.vtableCellType || "text";
      const buttonKind = cell.dataset.vtableButtonKind || "primary";
      return {
        field: `column_${index}`,
        title,
        minWidth: Math.max(88, Math.min(240, integer(cell.dataset.vtableWidth, 112))),
        sort: collectActions(cell).length === 0,
        ...(cellType === "button" ? { cellType: "button" } : {}),
        style: ({ value }) => {
          if (cellType === "button") {
            const primary = buttonKind === "primary";
            return {
              color: primary ? "#ffffff" : tokens.primary,
              fontWeight: 700,
              textAlign: "center",
              buttonStyle: {
                buttonColor: primary ? tokens.primary : tokens.card,
                buttonBorderColor: tokens.primary,
                buttonLineWidth: 1,
                buttonBorderRadius: 6,
                buttonHoverColor: primary ? cssToken("--q-primary-hover", "#4096ff") : tokens.selected,
                buttonHoverBorderColor: cssToken("--q-primary-hover", "#4096ff"),
                buttonTextHoverColor: primary ? "#ffffff" : tokens.primary,
                buttonPadding: 8,
              },
            };
          }
          const direction = financialDirection(title, value);
          return direction
            ? { color: direction > 0 ? tokens.profit : tokens.loss, fontWeight: 600 }
            : { color: tokens.text };
        },
      };
    });
    const sourceRows = table.tBodies.length
      ? Array.from(table.tBodies).flatMap((body) => Array.from(body.rows))
      : Array.from(table.rows).filter((row) => row !== headerRow);
    const visibleRows = sourceRows.filter((row) => !row.hidden);
    const actionMap = [];
    const records = visibleRows.map((row, rowIndex) => {
      const record = { __sourceRow: row, __selected: row.classList.contains("is-selected") };
      actionMap[rowIndex] = [];
      columns.forEach((column, columnIndex) => {
        const cell = row.cells[columnIndex];
        const actions = cell ? collectActions(cell) : [];
        const rawValue = normalizeText(cell?.dataset?.value ?? cell?.textContent ?? "");
        record[column.field] = actions.length
          ? actions.map((action) => normalizeText(action.textContent) || action.getAttribute("aria-label") || "操作").join(" · ")
          : formatFinancialValue(column.title, rawValue);
        actionMap[rowIndex][columnIndex] = actions;
      });
      return record;
    });
    const headerActions = headerCells.map(collectActions);
    return { columns, records, actionMap, headerActions };
  }

  function closeActionMenu() {
    document.querySelector(".app-vtable-action-menu")?.remove();
  }

  function invokeAction(action) {
    closeActionMenu();
    if (!action) return;
    action.click();
  }

  function showActionMenu(event, actions) {
    closeActionMenu();
    const point = event?.nativeEvent || event?.event || event;
    point?.stopPropagation?.();
    const menu = document.createElement("div");
    menu.className = "app-vtable-action-menu";
    menu.setAttribute("role", "menu");
    actions.forEach((action) => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = normalizeText(action.textContent) || action.getAttribute("aria-label") || "操作";
      button.addEventListener("click", () => invokeAction(action));
      menu.append(button);
    });
    menu.style.left = `${Math.max(8, integer(point?.clientX, 24))}px`;
    menu.style.top = `${Math.max(8, integer(point?.clientY, 24))}px`;
    document.body.append(menu);
    const rect = menu.getBoundingClientRect();
    if (rect.right > window.innerWidth - 8) menu.style.left = `${Math.max(8, window.innerWidth - rect.width - 8)}px`;
    if (rect.bottom > window.innerHeight - 8) menu.style.top = `${Math.max(8, window.innerHeight - rect.height - 8)}px`;
  }

  function handleActions(actions, event) {
    if (!actions?.length) return;
    if (actions.length === 1) invokeAction(actions[0]);
    else showActionMenu(event, actions);
  }

  function release(table) {
    const state = instances.get(table);
    if (!state) return;
    try {
      state.instance?.release?.();
    } catch (_error) {
      // VTable release failures must not block the rest of the page.
    }
    state.host?.remove();
    table.classList.remove("app-vtable-source");
    table.removeAttribute("aria-hidden");
    instances.delete(table);
  }

  function renderNativeTable(table) {
    if (!(table instanceof HTMLTableElement) || table.dataset.vtableDisabled === "true") return;
    const surface = table.closest(".table-wrap") || table.parentElement;
    if (table.closest("[hidden]") || !surface || surface.getBoundingClientRect().width < 40) return;
    const signature = tableSignature(table);
    const existing = instances.get(table);
    if (existing?.signature === signature && existing.host?.isConnected) return;
    const parsed = parseNativeTable(table);
    if (!parsed) return;
    if (!window.VTable?.ListTable) {
      table.closest(".table-wrap")?.classList.add("app-vtable-load-failed");
      return;
    }

    if (existing) release(table);
    const host = document.createElement("div");
    host.className = "app-vtable-host";
    host.dataset.vtableEnhanced = "true";
    host.setAttribute("role", "region");
    host.setAttribute("aria-label", table.getAttribute("aria-label") || "数据表格");
    const rowCount = Math.max(parsed.records.length, 1);
    const mode = tableMode(table);
    const rowHeight = modeRowHeight(mode);
    const tokens = designTokens();
    host.dataset.vtableMode = mode;
    host.style.height = `${Math.min(560, Math.max(152, 44 + rowCount * rowHeight))}px`;
    table.insertAdjacentElement("afterend", host);
    table.classList.add("app-vtable-source");

    const instance = new window.VTable.ListTable(host, {
      columns: parsed.columns,
      records: parsed.records,
      widthMode: "adaptive",
      heightMode: "standard",
      defaultRowHeight: rowHeight,
      defaultHeaderRowHeight: 44,
      autoWrapText: false,
      frozenColCount: parsed.columns.length > 4 ? 1 : 0,
      hover: { highlightMode: "row" },
      select: { disableSelect: true },
      emptyTip: { text: "暂无数据，请调整筛选条件" },
      theme: {
        headerStyle: {
          bgColor: tokens.zebra,
          color: tokens.text,
          fontSize: 14,
          fontFamily: 'Inter, Roboto, "Source Han Sans SC", "Microsoft YaHei"',
          fontWeight: "bold",
          borderColor: tokens.border,
          textAlign: "left",
        },
        bodyStyle: {
          bgColor: ({ row }) => parsed.records[Math.max(0, row - 1)]?.__selected
            ? tokens.selected
            : row % 2 === 0 ? tokens.card : tokens.zebra,
          color: tokens.text,
          fontSize: 14,
          fontFamily: 'Inter, Roboto, "Source Han Sans SC", "Microsoft YaHei"',
          borderColor: tokens.border,
          textAlign: "left",
        },
        frameStyle: {
          borderColor: tokens.border,
          borderLineWidth: 1,
        },
      },
    });
    const clickEvent = window.VTable.TABLE_EVENT_TYPE?.CLICK_CELL || "click_cell";
    instance.on?.(clickEvent, (event) => {
      const col = integer(event?.col, -1);
      const row = integer(event?.row, -1);
      if (col < 0 || row < 0) return;
      if (row === 0) {
        handleActions(parsed.headerActions[col], event);
        return;
      }
      const actions = parsed.actionMap[row - 1]?.[col];
      if (actions?.length) {
        handleActions(actions, event);
        return;
      }
      const sourceRow = parsed.records[row - 1]?.__sourceRow;
      if (sourceRow?.dataset?.vtableRowAction === "true") sourceRow.click();
    });
    instances.set(table, { instance, host, signature });
  }

  function enhanceAll(root = document) {
    root.querySelectorAll?.("table:not([data-vtable-disabled='true'])").forEach(renderNativeTable);
  }

  function scheduleEnhancement() {
    if (enhancementScheduled) return;
    enhancementScheduled = true;
    window.requestAnimationFrame(() => {
      enhancementScheduled = false;
      enhanceAll(document);
    });
  }

  function start() {
    enhanceAll(document);
    if (observer) return;
    observer = new MutationObserver((records) => {
      if (records.some((record) =>
        record.type === "childList"
        || record.attributeName === "hidden"
        || record.target.matches?.(".page-section, .dc-view")
      )) scheduleEnhancement();
    });
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["hidden", "class"],
    });
    document.addEventListener("click", (event) => {
      if (!event.target.closest(".app-vtable-action-menu")) closeActionMenu();
      scheduleEnhancement();
    });
    window.addEventListener("resize", scheduleEnhancement, { passive: true });
  }

  window.AppVTable = Object.freeze({
    version: "1.23.1",
    enhanceAll,
    renderNativeTable,
    release,
    releaseAll() {
      Array.from(instances.keys()).forEach(release);
    },
    instanceCount() {
      return instances.size;
    },
  });

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
  else start();
})();
