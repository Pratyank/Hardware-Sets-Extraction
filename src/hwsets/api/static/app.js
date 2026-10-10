// hwsets review UI — entry point: loading, selection, saving, keyboard and deep links.

import { renderDiagnostics } from "./js/diagnostics.js";
import { focusField, initEditor, renderEditor, resetInspector } from "./js/editor.js";
import { api } from "./js/api.js";
import { initSidebar, renderSidebar, scrollSelectedIntoView, visibleSets } from "./js/sidebar.js";
import {
  currentSet,
  fieldPaths,
  getAt,
  isLowField,
  on,
  pageTokens,
  resetTokens,
  state,
} from "./js/state.js";
import { $, $$, clone, h, isTyping, pct, setPages, toast } from "./js/util.js";
import {
  clearHighlight,
  initViewer,
  renderDocument,
  scrollToSet,
  setZoom,
  updateSelection,
} from "./js/viewer.js";

// -- deep links ------------------------------------------------------------------------
function readHash() {
  const p = new URLSearchParams(location.hash.slice(1));
  const set = p.get("set");
  return { doc: p.get("doc"), set: set !== null && /^\d+$/.test(set) ? Number(set) : null };
}

function writeHash() {
  if (!state.docId) return;
  const p = new URLSearchParams({ doc: state.docId });
  if (state.setIdx >= 0) p.set("set", String(state.setIdx));
  const next = `#${p}`;
  if (location.hash !== next) history.replaceState(null, "", next);
}

// -- documents ---------------------------------------------------------------------------
function docLabel(d) {
  return `${d.doc_id}  ·  ${d.n_sets} sets${d.has_corrections ? "  ·  edited" : ""}`;
}

function renderDocMeta() {
  const d = state.docs.find((x) => x.doc_id === state.docId);
  const el = $("#doc-meta");
  if (!d) return el.replaceChildren();
  el.replaceChildren(
    h("span", {}, `${d.n_pages} pages`),
    h("span", {}, `${d.n_sets} sets`),
    h("span", {}, `mean ${pct(d.mean_confidence)}`),
    ...(d.has_corrections ? [h("span.edited", {}, "edited")] : []),
  );
}

async function loadDocs() {
  const select = $("#doc-select");
  try {
    state.docs = await api.listDocs();
  } catch (err) {
    select.replaceChildren(h("option", {}, "Failed to load"));
    toast("Could not load documents", { kind: "error", detail: err.message });
    return;
  }
  if (!state.docs.length) {
    select.replaceChildren(h("option", {}, "No extracted documents"));
    renderAll();
    return;
  }
  select.replaceChildren(...state.docs.map((d) => h("option", { value: d.doc_id }, docLabel(d))));
  select.disabled = false;
  const { doc, set } = readHash();
  const target = state.docs.some((d) => d.doc_id === doc) ? doc : state.docs[0].doc_id;
  await loadDoc(target, set ?? 0);
}

function confirmDiscard() {
  return !state.dirty.size || window.confirm("Discard unsaved changes?");
}

async function loadDoc(docId, setIdx = 0) {
  $("#doc-select").value = docId;
  document.body.classList.add("is-loading");
  try {
    const [result, pages] = await Promise.all([api.result(docId), api.pages(docId)]);
    state.docId = docId;
    state.result = result;
    state.saved = clone(result.sets);
    state.pages = pages;
    state.pageInfo = new Map(pages.pages.map((p) => [p.page, p]));
    state.dirty.clear();
    state.setIdx = -1;
    resetTokens();
  } catch (err) {
    toast(`Could not open ${docId}`, { kind: "error", detail: err.message });
    return;
  } finally {
    document.body.classList.remove("is-loading");
  }
  renderDocument();
  renderDiagnostics();
  renderDocMeta();
  updateDirty();
  const n = state.result.sets.length;
  select({ idx: n ? Math.min(Math.max(0, setIdx), n - 1) : -1, scroll: true, smooth: false });
}

function renderAll() {
  renderSidebar();
  renderEditor();
  renderDiagnostics();
  renderDocument();
}

// -- selection -------------------------------------------------------------------------
function select({ idx, scroll = true, smooth = true }) {
  if (!state.result) return;
  state.setIdx = idx;
  state.focusPath = null;
  clearHighlight();
  resetInspector();
  renderSidebar();
  renderEditor();
  updateSelection();
  writeHash();
  const set = currentSet();
  if (!set) return;
  if (scroll) requestAnimationFrame(() => scrollToSet(idx, { smooth }));
  for (const p of setPages(set)) pageTokens(p).catch(() => {}); // warm hover highlights
}

function step(delta) {
  const vis = visibleSets();
  if (!vis.length) return;
  const pos = vis.indexOf(state.setIdx);
  const next = pos < 0 ? vis[0] : vis[Math.min(vis.length - 1, Math.max(0, pos + delta))];
  if (next !== state.setIdx) select({ idx: next });
  scrollSelectedIntoView();
}

/** Focus the next low-confidence field after the current one, across sets (wrapping). */
function nextLow() {
  const sets = state.result?.sets ?? [];
  if (!sets.length) return;
  const start = Math.max(0, state.setIdx);
  for (let k = 0; k <= sets.length; k++) {
    const idx = (start + k) % sets.length;
    const paths = fieldPaths(sets[idx]);
    let from = 0;
    if (k === 0 && state.focusPath) from = paths.indexOf(state.focusPath) + 1;
    const hit = paths.slice(from).find((p) => isLowField(getAt(sets[idx], p)));
    if (hit) {
      if (idx !== state.setIdx) select({ idx });
      $("#tab-set").click();
      requestAnimationFrame(() => focusField(hit));
      return;
    }
  }
  toast("No low-confidence fields left", { kind: "success" });
}

// -- dirty state, saving, export ---------------------------------------------------------------
function updateDirty() {
  const n = state.dirty.size;
  $("#dirty-indicator").hidden = n === 0;
  $("#dirty-text").textContent = n === 1 ? "1 set unsaved" : `${n} sets unsaved`;
  $("#btn-save").disabled = n === 0;
  $("#btn-export").disabled = !state.result;
  document.title = `${n ? "● " : ""}hwsets review${state.docId ? ` — ${state.docId}` : ""}`;
}

let busy = false;
async function save({ quiet = false } = {}) {
  if (busy || !state.dirty.size) return true;
  busy = true;
  $("#btn-save").classList.add("busy");
  document.activeElement?.closest?.(".cell-input")?.blur();
  const ids = [...state.dirty].sort((a, b) => a - b);
  const failed = [];
  for (const idx of ids) {
    try {
      const { set } = await api.saveSet(state.docId, idx, state.result.sets[idx]);
      state.result.sets[idx] = set;
      state.saved[idx] = clone(set);
      state.dirty.delete(idx);
    } catch (err) {
      failed.push(`set ${state.result.sets[idx].set_number.value ?? idx}: ${err.message}`);
    }
  }
  busy = false;
  $("#btn-save").classList.remove("busy");
  const doc = state.docs.find((d) => d.doc_id === state.docId);
  if (doc && ids.length > failed.length) doc.has_corrections = true;
  updateDirty();
  renderDocMeta();
  renderSidebar();
  renderEditor();
  if (failed.length) {
    toast("Some corrections were not saved", { kind: "error", detail: failed.join("\n") });
    return false;
  }
  if (!quiet) {
    const n = ids.length;
    toast(n === 1 ? "Correction saved" : `${n} corrections saved`, {
      kind: "success",
      detail: `corrections/${state.docId}.json`,
    });
  }
  return true;
}

async function exportGold() {
  if (!state.result) return;
  if (state.dirty.size && !(await save({ quiet: true }))) return;
  const btn = $("#btn-export");
  btn.classList.add("busy");
  try {
    const flat = await api.exportGold(state.docId);
    const nComp = flat.sets.reduce((a, s) => a + s.components.length, 0);
    toast("Exported as gold draft", {
      kind: "success",
      detail: `${flat.sets.length} sets · ${nComp} components → corrections/${state.docId}.gold.json`,
    });
  } catch (err) {
    toast("Export failed", { kind: "error", detail: err.message });
  } finally {
    btn.classList.remove("busy");
  }
}

async function revert(idx) {
  const label = state.result.sets[idx].set_number.value ?? idx;
  if (!window.confirm(`Discard all corrections to set ${label} and restore the extracted values?`)) {
    return;
  }
  try {
    const { set } = await api.revertSet(state.docId, idx);
    state.result.sets[idx] = set;
    state.saved[idx] = clone(set);
    state.dirty.delete(idx);
    updateDirty();
    select({ idx, scroll: false });
    toast(`Set ${label} reverted to extracted values`, { kind: "info" });
  } catch (err) {
    toast("Revert failed", { kind: "error", detail: err.message });
  }
}

// -- keyboard ---------------------------------------------------------------------------
function onKey(e) {
  const help = $("#help");
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
    e.preventDefault();
    save();
    return;
  }
  if (e.key === "Escape") {
    if (help.open) return; // native dialog handles it
    if (isTyping(document.activeElement)) document.activeElement.blur();
    return;
  }
  if (isTyping(e.target) || e.ctrlKey || e.metaKey || e.altKey || help.open) return;
  const actions = {
    j: () => step(1),
    k: () => step(-1),
    n: () => nextLow(),
    "?": () => help.showModal(),
    "/": () => $("#set-filter").focus(),
    "+": () => setZoom(1),
    "=": () => setZoom(1),
    "-": () => setZoom(-1),
    0: () => setZoom(0),
  };
  const fn = actions[e.key];
  if (fn) {
    e.preventDefault();
    fn();
  }
}

// -- tabs -------------------------------------------------------------------------------
function initTabs() {
  const tabs = $$('[role="tab"]');
  const activate = (tab) => {
    for (const t of tabs) {
      const on = t === tab;
      t.setAttribute("aria-selected", on ? "true" : "false");
      t.tabIndex = on ? 0 : -1;
      $(`#${t.getAttribute("aria-controls")}`).hidden = !on;
    }
  };
  for (const t of tabs) {
    t.addEventListener("click", () => activate(t));
    t.addEventListener("keydown", (e) => {
      if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
      const i = tabs.indexOf(t);
      const next = tabs[(i + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length];
      next.focus();
      activate(next);
    });
  }
}

// -- boot -------------------------------------------------------------------------------
function init() {
  initViewer();
  initSidebar();
  initEditor();
  initTabs();
  on("select", (p) => select(p));
  on("step", (d) => step(d));
  on("revert", (idx) => revert(idx));
  on("dirty", ({ first }) => {
    updateDirty();
    if (first) renderSidebar();
  });

  $("#doc-select").addEventListener("change", (e) => {
    const id = e.target.value;
    if (!confirmDiscard()) {
      e.target.value = state.docId;
      return;
    }
    loadDoc(id, 0);
  });
  $("#btn-save").addEventListener("click", () => save());
  $("#btn-export").addEventListener("click", exportGold);
  $("#btn-help").addEventListener("click", () => $("#help").showModal());
  $("#help").addEventListener("click", (e) => {
    if (e.target.closest("[data-close]") || e.target === e.currentTarget) $("#help").close();
  });
  document.addEventListener("keydown", onKey);
  window.addEventListener("beforeunload", (e) => {
    if (state.dirty.size) e.preventDefault();
  });
  window.addEventListener("hashchange", () => {
    const { doc, set } = readHash();
    if (doc && doc !== state.docId && state.docs.some((d) => d.doc_id === doc)) {
      if (confirmDiscard()) loadDoc(doc, set ?? 0);
    } else if (set !== null && set !== state.setIdx && set < (state.result?.sets.length ?? 0)) {
      select({ idx: set });
    }
  });
  updateDirty();
  renderEditor();
  loadDocs();
}

init();
