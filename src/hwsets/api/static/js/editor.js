// Right panel: the selected set's fields and components as an editable, confidence-coloured
// table. Hovering or focusing a field highlights its source tokens on the page.

import {
  COLUMNS,
  currentSet,
  emit,
  fieldLabel,
  getAt,
  hasHumanEdits,
  lowFieldCount,
  resolveTokens,
  state,
} from "./state.js";
import { $, confLevel, fmtConf, h, isEmpty, level, pageRange, pct, setPages } from "./util.js";
import { clearHighlight, highlight } from "./viewer.js";

const panel = () => $("#panel-set");
let hoverPath = null;

// -- cells ---------------------------------------------------------------------------
function cellText(v) {
  return isEmpty(v) ? "" : String(v);
}

function ariaFor(path, f) {
  const lvl = f ? (f.source === "human" ? "edited by you" : `confidence ${fmtConf(f.confidence)}`) : "";
  return `${fieldLabel(path)}${lvl ? `, ${lvl}` : ""}`;
}

/** An editable cell bound to `path` (a Field path, or a plain string like qty_unit). */
function cell(set, path, { tag = "td", cls = "", plain = false, secondary = null } = {}) {
  const f = plain ? null : getAt(set, path);
  const value = plain ? getAt(set, path) : f?.value;
  const lvl = plain ? "plain" : level(f);
  const input = h("div.cell-input", {
    contenteditable: "plaintext-only",
    role: "textbox",
    spellcheck: "false",
    "aria-label": plain ? fieldLabel(path) : ariaFor(path, f),
    dataset: { path },
  });
  input.textContent = cellText(value);
  if (input.contentEditable !== "plaintext-only") input.contentEditable = "true";
  return h(
    `${tag}.cell.lvl-${lvl}`,
    { class: cls, dataset: { path, plain: plain ? "1" : null } },
    input,
    secondary,
  );
}

function setLevelClass(wrapper, lvl) {
  wrapper.className = wrapper.className.replace(/\blvl-\S+/g, "").trim();
  wrapper.classList.add(`lvl-${lvl}`);
}

// -- rendering -------------------------------------------------------------------------
function setHeader(set, idx) {
  const notUsed = set.status === "not_used";
  const low = lowFieldCount(set);
  const corrected = hasHumanEdits(set) || state.dirty.has(idx);
  return h(
    "div.set-head",
    {},
    h(
      "div.set-title",
      {},
      h("span.set-title-kicker", {}, "Set"),
      cell(set, "set_number", { tag: "div", cls: "set-no-cell" }),
      notUsed && h("span.tag.tag-muted", {}, set.status_text || "NOT USED"),
      h(
        `span.badge.lg.lvl-${notUsed ? "null" : confLevel(set.confidence)}`,
        { title: "Set-level confidence" },
        pct(set.confidence),
      ),
      h("span.spacer"),
      corrected &&
        h(
          "button.btn.btn-ghost.btn-sm",
          { type: "button", onclick: () => emit("revert", idx), title: "Discard corrections for this set" },
          "Revert to extracted",
        ),
    ),
    h(
      "div.set-fields",
      {},
      h("label.field-label", {}, "Description"),
      cell(set, "description", { tag: "div", cls: "wide" }),
      h("label.field-label", {}, "Notes"),
      cell(set, "notes", { tag: "div", cls: "wide" }),
    ),
    h(
      "div.set-sub",
      {},
      h("span", {}, pageRange(setPages(set))),
      h("span", {}, `lines ${set.location.line_range[0]} → ${set.location.line_range[1]}`),
      h("span", {}, `${set.components.length} components`),
      low > 0 && h("span.low", {}, `${low} low-confidence`),
    ),
  );
}

function componentRow(set, i) {
  const c = set.components[i];
  const cells = COLUMNS.map((col) => {
    const path = `components.${i}.${col.key}`;
    let secondary = null;
    if (col.key === "mfr" && c.mfr_resolved) {
      secondary = h("div.secondary", { title: `Resolved manufacturer: ${c.mfr_resolved}` }, c.mfr_resolved);
    }
    if (col.key === "description" && c.resolved_from_code) {
      secondary = h("div.secondary", {}, `from code ${c.resolved_from_code}`);
    }
    return cell(set, path, { cls: col.cls, plain: !col.field, secondary });
  });
  return h(
    "tr",
    { dataset: { row: i } },
    h("th.c-idx", { scope: "row" }, String(i + 1)),
    ...cells,
    h(
      "td.c-act",
      {},
      h(
        "button.row-del",
        {
          type: "button",
          "aria-label": `Delete row ${i + 1}`,
          title: "Delete row",
          onclick: () => deleteRow(i),
        },
        "×",
      ),
    ),
  );
}

export function renderEditor() {
  const p = panel();
  const set = currentSet();
  if (!set) {
    p.replaceChildren(
      h(
        "div.empty-card.inset",
        {},
        h("div.empty-title", {}, state.result ? "Select a set" : "No document"),
        h("div.empty-body", {}, "Pick a set on the left, or press j / k."),
      ),
    );
    return;
  }
  const idx = state.setIdx;
  const table = h(
    "table.grid",
    { "aria-label": `Components of set ${set.set_number.value ?? ""}` },
    h(
      "thead",
      {},
      h(
        "tr",
        {},
        h("th.c-idx", { scope: "col" }, h("span.sr-only", {}, "Row")),
        ...COLUMNS.map((c) => h(`th.${c.cls}`, { scope: "col" }, c.label)),
        h("th.c-act", { scope: "col" }, h("span.sr-only", {}, "Actions")),
      ),
    ),
    h("tbody", {}, set.components.map((_, i) => componentRow(set, i))),
  );
  const body = set.components.length
    ? h("div.grid-wrap", {}, table)
    : h(
        "div.empty-inline",
        {},
        set.status === "not_used" ? "Not used — no components expected." : "No components extracted.",
      );
  p.replaceChildren(
    setHeader(set, idx),
    body,
    h(
      "div.grid-foot",
      {},
      h("button.btn.btn-ghost.btn-sm", { type: "button", onclick: addRow }, "+ Add component"),
    ),
  );
  p.scrollTop = 0;
}

// -- editing ---------------------------------------------------------------------------
function parseValue(path, text) {
  const t = text.replace(/\s+/g, " ").trim();
  if (!t) return null;
  if (path.endsWith(".qty")) return /^\d+$/.test(t) ? Number(t) : t;
  return t;
}

function markDirty() {
  const first = !state.dirty.has(state.setIdx);
  state.dirty.add(state.setIdx);
  emit("dirty", { first });
}

function commit(input) {
  const set = currentSet();
  const path = input.dataset.path;
  const wrapper = input.closest(".cell");
  const value = parseValue(path, input.textContent);
  if (wrapper.dataset.plain) {
    if (getAt(set, path) === value) return;
    const keys = path.split(".");
    set.components[Number(keys[1])][keys[2]] = value;
  } else {
    const f = getAt(set, path);
    if (f.value === value || parseValue(path, cellText(f.value)) === value) return;
    f.value = value;
    f.source = "human";
    setLevelClass(wrapper, "human");
    input.setAttribute("aria-label", ariaFor(path, f));
  }
  markDirty();
  if (path === state.focusPath) inspect(path, null);
}

function emptyField() {
  return { value: null, token_ids: [], confidence: 0, source: "human" };
}

function addRow() {
  const set = currentSet();
  set.components.push({
    qty: emptyField(),
    qty_unit: null,
    description: emptyField(),
    catalog_number: emptyField(),
    mfr: emptyField(),
    mfr_resolved: null,
    finish: emptyField(),
    notes: emptyField(),
    resolved_from_code: null,
  });
  markDirty();
  renderEditor();
  focusField(`components.${set.components.length - 1}.qty`);
}

function deleteRow(i) {
  const set = currentSet();
  set.components.splice(i, 1);
  markDirty();
  renderEditor();
  clearHighlight();
}

export function focusField(path) {
  const input = panel().querySelector(`.cell-input[data-path="${path}"]`);
  if (!input) return false;
  input.focus({ preventScroll: true });
  input.closest(".cell").scrollIntoView({ block: "nearest", inline: "nearest" });
  const sel = window.getSelection();
  sel.selectAllChildren(input);
  sel.collapseToEnd();
  return true;
}

function moveRow(input, delta) {
  const parts = input.dataset.path.split(".");
  if (parts[0] !== "components") return;
  const next = `components.${Number(parts[1]) + delta}.${parts[2]}`;
  focusField(next);
}

// -- provenance: highlight + inspector ----------------------------------------------------
async function inspect(path, scroll) {
  const set = currentSet();
  if (!set) return;
  const f = getAt(set, path);
  const insp = $("#inspector");
  if (!f || typeof f !== "object") {
    clearHighlight();
    insp.replaceChildren(h("strong", {}, fieldLabel(path)), h("span.muted", {}, "plain text · no source tokens"));
    return;
  }
  const lvl = level(f);
  const col = path.split(".").pop();
  const label = `${(COLUMNS.find((c) => c.key === col)?.label ?? fieldLabel(path)).toUpperCase()} · ${
    f.source === "human" ? "edited" : fmtConf(f.confidence)
  }`;
  const toks =
    scroll === null
      ? await resolveTokens(f.token_ids)
      : await highlight(f.token_ids, { label, level: lvl, scroll });
  if (state.focusPath !== path && hoverPath !== path) return;
  const original = getAt(state.saved[state.setIdx] ?? {}, path);
  const src = toks.map((t) => t.text).join(" ");
  const parts = [
    h("strong", {}, fieldLabel(path)),
    h(`span.pill.src-${f.source}`, {}, f.source),
    h(`span.conf.lvl-${lvl}`, {}, f.source === "human" ? "verified" : fmtConf(f.confidence)),
    h("span.muted", {}, `${f.token_ids.length} token${f.token_ids.length === 1 ? "" : "s"}`),
  ];
  if (src) parts.push(h("span.src-text", { title: "Text on the page" }, `“${src}”`));
  if (!f.token_ids.length) parts.push(h("span.muted", {}, "not grounded on the page"));
  if (original && typeof original === "object" && original.value !== f.value) {
    parts.push(h("span.muted", {}, `was “${cellText(original.value) || "empty"}”`));
  }
  insp.dataset.path = path;
  insp.replaceChildren(...parts);
}

function resetInspector() {
  const insp = $("#inspector");
  delete insp.dataset.path;
  insp.replaceChildren(h("span.inspector-hint", {}, "Hover or focus a field to see where it came from."));
}

export function initEditor() {
  const p = panel();
  p.addEventListener("focusin", (e) => {
    const input = e.target.closest(".cell-input");
    if (!input) return;
    state.focusPath = input.dataset.path;
    p.querySelectorAll(".cell.focused").forEach((c) => c.classList.remove("focused"));
    input.closest(".cell").classList.add("focused");
    inspect(state.focusPath, "now");
  });
  p.addEventListener("focusout", (e) => {
    const input = e.target.closest(".cell-input");
    if (!input) return;
    input.closest(".cell").classList.remove("focused");
    commit(input);
    setTimeout(() => {
      if (!document.activeElement?.closest?.(".cell-input")) {
        state.focusPath = null;
        if (!hoverPath) {
          clearHighlight();
          resetInspector();
        }
      }
    }, 0);
  });
  p.addEventListener("input", (e) => {
    const input = e.target.closest(".cell-input");
    if (input) commit(input);
  });
  p.addEventListener("paste", (e) => {
    const input = e.target.closest(".cell-input");
    if (!input || input.contentEditable === "plaintext-only") return;
    e.preventDefault();
    const text = (e.clipboardData?.getData("text/plain") ?? "").replace(/\s+/g, " ");
    document.execCommand("insertText", false, text);
  });
  p.addEventListener("keydown", (e) => {
    const input = e.target.closest(".cell-input");
    if (!input) return;
    if (e.key === "Enter") {
      e.preventDefault();
      commit(input);
      moveRow(input, e.shiftKey ? -1 : 1);
    } else if (e.key === "Escape") {
      e.preventDefault();
      input.blur();
    }
  });
  const endHover = () => {
    if (!hoverPath) return;
    hoverPath = null;
    if (state.focusPath) inspect(state.focusPath, "none");
    else {
      clearHighlight();
      resetInspector();
    }
  };
  p.addEventListener("mouseover", (e) => {
    const path = e.target.closest(".cell")?.dataset.path ?? null;
    if (!path) return endHover();
    if (path === hoverPath) return;
    hoverPath = path;
    inspect(path, "lazy");
  });
  p.addEventListener("mouseleave", endHover);
}

export { resetInspector };
