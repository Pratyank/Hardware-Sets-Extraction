// Left panel: filterable list of hardware sets.

import { COLUMNS, emit, hasHumanEdits, lowFieldCount, needsReview, state } from "./state.js";
import { $, $$, confLevel, h, pageRange, pct, setPages } from "./util.js";

function matches(set, q) {
  if (!q) return true;
  const hay = [
    set.set_number.value,
    set.description.value,
    set.status_text,
    ...set.components.flatMap((c) =>
      COLUMNS.map((col) => (col.field ? c[col.key]?.value : c[col.key])),
    ),
  ]
    .filter((v) => v !== null && v !== undefined)
    .join(" ")
    .toLowerCase();
  return q
    .toLowerCase()
    .split(/\s+/)
    .every((w) => hay.includes(w));
}

function inMode(set) {
  if (state.mode === "review") return needsReview(set);
  if (state.mode === "not_used") return set.status === "not_used";
  return true;
}

/** Indices of sets currently visible in the list, in order. */
export function visibleSets() {
  if (!state.result) return [];
  return state.result.sets
    .map((s, i) => [s, i])
    .filter(([s]) => inMode(s) && matches(s, state.filter.trim()))
    .map(([, i]) => i);
}

function item(set, idx) {
  const notUsed = set.status === "not_used";
  const low = lowFieldCount(set);
  const lvl = confLevel(set.confidence);
  const dirty = state.dirty.has(idx);
  const edited = hasHumanEdits(set);
  const n = set.components.length;
  const desc = set.description.value || (notUsed ? set.status_text || "Not used" : "No description");
  return h(
    "li.set-item",
    {
      role: "option",
      id: `set-opt-${idx}`,
      class: [notUsed && "not-used", dirty && "dirty"].filter(Boolean).join(" "),
      "aria-selected": idx === state.setIdx ? "true" : "false",
      dataset: { idx },
      onclick: () => emit("select", { idx, scroll: true }),
    },
    h(
      "div.set-row1",
      {},
      h("span.set-no", {}, set.set_number.value ?? "—"),
      dirty && h("span.dot.dot-dirty", { title: "Unsaved changes", "aria-label": "unsaved" }),
      edited && !dirty && h("span.edited", { title: "Has human corrections" }, "edited"),
      h(
        `span.badge.lvl-${notUsed ? "null" : lvl}`,
        { title: `Set confidence ${pct(set.confidence)}` },
        pct(set.confidence),
      ),
    ),
    h("div.set-desc", { title: desc }, desc),
    h(
      "div.set-meta",
      {},
      notUsed
        ? h("span.tag.tag-muted", {}, set.status_text || "NOT USED")
        : h("span", {}, `${n} item${n === 1 ? "" : "s"}`),
      h("span", {}, pageRange(setPages(set))),
      low > 0 && !notUsed && h("span.low", { title: `${low} low-confidence fields` }, `${low} low`),
    ),
  );
}

export function renderSidebar() {
  const list = $("#set-list");
  const sets = state.result?.sets ?? [];
  const vis = visibleSets();
  list.replaceChildren(...vis.map((i) => item(sets[i], i)));
  $("#set-empty").hidden = vis.length > 0 || !state.result;
  $("#set-empty").textContent = sets.length ? "No sets match." : "This document has no sets.";
  const counts = {
    all: sets.length,
    review: sets.filter(needsReview).length,
    not_used: sets.filter((s) => s.status === "not_used").length,
  };
  for (const el of $$("[data-count]")) el.textContent = counts[el.dataset.count];
  if (state.setIdx >= 0) list.setAttribute("aria-activedescendant", `set-opt-${state.setIdx}`);
  scrollSelectedIntoView();
}

export function scrollSelectedIntoView() {
  const el = $(`#set-opt-${state.setIdx}`);
  el?.scrollIntoView({ block: "nearest" });
}

export function initSidebar() {
  const input = $("#set-filter");
  input.addEventListener("input", () => {
    state.filter = input.value;
    renderSidebar();
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      const first = visibleSets()[0];
      if (first !== undefined) emit("select", { idx: first, scroll: true });
    }
  });
  for (const btn of $$(".segmented [data-mode]")) {
    btn.addEventListener("click", () => {
      state.mode = btn.dataset.mode;
      for (const b of $$(".segmented [data-mode]")) {
        b.setAttribute("aria-checked", b === btn ? "true" : "false");
      }
      renderSidebar();
    });
  }
  $("#set-list").addEventListener("keydown", (e) => {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    e.preventDefault();
    emit("step", e.key === "ArrowDown" ? 1 : -1);
  });
}
