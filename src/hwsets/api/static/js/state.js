// Application state, an event bus, the per-page token cache and field addressing.

import { api } from "./api.js";
import { LOW, isEmpty } from "./util.js";

export const COLUMNS = [
  { key: "qty", label: "Qty", long: "quantity", field: true, cls: "c-qty" },
  { key: "qty_unit", label: "Unit", long: "unit", field: false, cls: "c-unit" },
  { key: "description", label: "Description", long: "description", field: true, cls: "c-desc" },
  { key: "catalog_number", label: "Catalog", long: "catalog number", field: true, cls: "c-cat" },
  { key: "mfr", label: "Mfr", long: "manufacturer", field: true, cls: "c-mfr" },
  { key: "finish", label: "Finish", long: "finish", field: true, cls: "c-fin" },
  { key: "notes", label: "Notes", long: "notes", field: true, cls: "c-notes" },
];

export const SET_FIELDS = [
  { key: "set_number", label: "Set number" },
  { key: "description", label: "Description" },
  { key: "notes", label: "Set notes" },
];

export const state = {
  docs: [],
  docId: null,
  result: null, // DocumentResult being edited (working copy)
  saved: [], // last saved/loaded copy of each set, for dirty tracking and revert
  pages: null, // { dpi, scale, pages: PageInfo[] }
  pageInfo: new Map(), // page -> PageInfo
  setIdx: -1,
  dirty: new Set(),
  filter: "",
  mode: "all",
  focusPath: null, // path of the focused field, e.g. "components.2.mfr"
};

// -- event bus -----------------------------------------------------------------------
const listeners = new Map();
export function on(evt, fn) {
  if (!listeners.has(evt)) listeners.set(evt, new Set());
  listeners.get(evt).add(fn);
}
export function emit(evt, payload) {
  for (const fn of listeners.get(evt) || []) fn(payload);
}

// -- tokens --------------------------------------------------------------------------
const tokenCache = new Map(); // `${doc}:${page}` -> Promise<Token[]>
export function pageTokens(page) {
  const key = `${state.docId}:${page}`;
  if (!tokenCache.has(key)) {
    const p = api.tokens(state.docId, page).catch((err) => {
      tokenCache.delete(key);
      throw err;
    });
    tokenCache.set(key, p);
  }
  return tokenCache.get(key);
}
export function resetTokens() {
  tokenCache.clear();
}

/** Resolve token ids to Token objects (grouped lookups, cached per page). */
export async function resolveTokens(ids) {
  const byPage = new Map();
  for (const id of ids) {
    const m = /^p(\d+)_w(\d+)$/.exec(id);
    if (!m) continue;
    const page = Number(m[1]);
    if (!byPage.has(page)) byPage.set(page, []);
    byPage.get(page).push({ id, index: Number(m[2]) });
  }
  const out = [];
  await Promise.all(
    [...byPage].map(async ([page, refs]) => {
      let toks;
      try {
        toks = await pageTokens(page);
      } catch {
        return;
      }
      for (const { id, index } of refs) {
        const t = toks[index]?.id === id ? toks[index] : toks.find((x) => x.id === id);
        if (t) out.push(t);
      }
    }),
  );
  return out.sort((a, b) => a.page - b.page || a.bbox[1] - b.bbox[1] || a.bbox[0] - b.bbox[0]);
}

// -- fields --------------------------------------------------------------------------
export const currentSet = () => state.result?.sets[state.setIdx] ?? null;

export function getAt(set, path) {
  return path.split(".").reduce((o, k) => (o == null ? o : o[k]), set);
}

export function setAt(set, path, value) {
  const keys = path.split(".");
  const last = keys.pop();
  const parent = keys.reduce((o, k) => o[k], set);
  parent[last] = value;
}

export function fieldLabel(path) {
  const parts = path.split(".");
  if (parts[0] === "components") {
    const col = COLUMNS.find((c) => c.key === parts[2]);
    return `Row ${Number(parts[1]) + 1} · ${col ? col.label : parts[2]}`;
  }
  return SET_FIELDS.find((f) => f.key === parts[0])?.label ?? path;
}

/** All Field paths of a set in visual (reading) order. */
export function fieldPaths(set) {
  const out = SET_FIELDS.map((f) => f.key);
  set.components.forEach((_, i) => {
    for (const c of COLUMNS) if (c.field) out.push(`components.${i}.${c.key}`);
  });
  return out;
}

export function isLowField(f) {
  return !!f && f.source !== "human" && !isEmpty(f.value) && f.confidence < LOW;
}

export function lowFieldCount(set) {
  return fieldPaths(set).filter((p) => isLowField(getAt(set, p))).length;
}

export function hasHumanEdits(set) {
  return fieldPaths(set).some((p) => getAt(set, p)?.source === "human");
}

export function needsReview(set) {
  return set.status !== "not_used" && (set.confidence < LOW || lowFieldCount(set) > 0);
}
