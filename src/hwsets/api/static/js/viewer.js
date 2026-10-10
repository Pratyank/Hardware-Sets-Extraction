// Centre panel: stacked page images with set regions and source-token highlights.
//
// Overlays are positioned in percentages of the page's size in PDF points
// (left = x0 / width), which equals scaling by (rendered px / page width pt) at any zoom
// or window size without recomputation.

import { api } from "./api.js";
import { emit, resolveTokens, state } from "./state.js";
import { $, h, prefersReducedMotion, setPages } from "./util.js";

const ZOOMS = [0.5, 0.67, 0.8, 1, 1.25, 1.5, 2, 2.5, 3, 4];
let zoom = 1;
let fitWidth = 600;
let pageEls = new Map(); // page -> { fig, overlay, hl }
let io = null;
let hlSeq = 0;
let scrollTimer = 0;

const viewer = () => $("#viewer");

const pct = (v, total) => `${(v / total) * 100}%`;

function place(el, bbox, info, pad = 0) {
  const [x0, y0, x1, y1] = bbox;
  el.style.left = pct(x0 - pad, info.width);
  el.style.top = pct(y0 - pad, info.height);
  el.style.width = pct(x1 - x0 + 2 * pad, info.width);
  el.style.height = pct(y1 - y0 + 2 * pad, info.height);
  return el;
}

/** Pages shown: hardware pages plus every page a set region touches. */
function stackPages(result) {
  const pages = new Set(result.hardware_pages);
  for (const s of result.sets) for (const r of s.location.regions) pages.add(r.page);
  return [...pages].filter((p) => state.pageInfo.has(p)).sort((a, b) => a - b);
}

export function renderDocument() {
  const host = $("#pages");
  host.replaceChildren();
  pageEls = new Map();
  io?.disconnect();
  const result = state.result;
  $("#viewer-empty").hidden = !!result;
  if (!result) return;

  io = new IntersectionObserver(onIntersect, { root: viewer(), rootMargin: "1200px 0px" });
  const pages = stackPages(result);
  const regionsByPage = new Map();
  result.sets.forEach((s, idx) => {
    for (const r of s.location.regions) {
      if (!regionsByPage.has(r.page)) regionsByPage.set(r.page, []);
      regionsByPage.get(r.page).push({ idx, set: s, bbox: r.bbox });
    }
  });

  for (const n of pages) {
    const info = state.pageInfo.get(n);
    const img = h("img.page-img", { alt: `Page ${n}`, decoding: "async", draggable: "false" });
    const overlay = h("div.overlay");
    const hl = h("div.hl-layer", { "aria-hidden": "true" });
    for (const { idx, set, bbox } of regionsByPage.get(n) || []) {
      const label = `Set ${set.set_number.value ?? "?"}`;
      overlay.append(
        place(
          h(
            "button.region",
            {
              type: "button",
              class: set.status === "not_used" ? "not-used" : "",
              dataset: { set: idx },
              "aria-label": `Select ${label}`,
              tabindex: "-1",
              onclick: () => emit("select", { idx, scroll: false }),
            },
            h("span.region-tag", {}, set.set_number.value ?? "?"),
          ),
          bbox,
          info,
          2,
        ),
      );
    }
    const page = h(
      "div.page.loading",
      { dataset: { page: n }, style: { aspectRatio: `${info.width} / ${info.height}` } },
      img,
      overlay,
      hl,
    );
    img.addEventListener("load", () => page.classList.remove("loading"));
    img.addEventListener("error", () => {
      page.classList.remove("loading");
      page.classList.add("failed");
    });
    const fig = h(
      "figure.page-fig",
      { dataset: { page: n } },
      h("figcaption.page-cap", {}, `Page ${n}`),
      page,
    );
    host.append(fig);
    pageEls.set(n, { fig, page, img, overlay, hl });
    io.observe(fig);
  }
  layout();
  updateSelection();
}

function onIntersect(entries) {
  for (const e of entries) {
    if (!e.isIntersecting) continue;
    const n = Number(e.target.dataset.page);
    const el = pageEls.get(n);
    if (el && !el.img.src) el.img.src = api.pngUrl(state.docId, n);
  }
  updatePosition();
}

export function layout() {
  const v = viewer();
  fitWidth = Math.max(240, v.clientWidth - 48);
  const w = Math.round(fitWidth * zoom);
  document.documentElement.style.setProperty("--page-w", `${w}px`);
  $("#zoom-fit").textContent = `${Math.round(zoom * 100)}%`;
}

export function setZoom(dir) {
  const v = viewer();
  const cy = (v.scrollTop + v.clientHeight / 2) / Math.max(1, v.scrollHeight);
  const cx = (v.scrollLeft + v.clientWidth / 2) / Math.max(1, v.scrollWidth);
  if (dir === 0) zoom = 1;
  else {
    const i = ZOOMS.findIndex((z) => z >= zoom - 1e-6);
    const next = dir > 0 ? ZOOMS.find((z) => z > zoom + 1e-6) : [...ZOOMS].reverse().find((z) => z < zoom - 1e-6);
    zoom = next ?? ZOOMS[i] ?? zoom;
  }
  layout();
  v.scrollTop = cy * v.scrollHeight - v.clientHeight / 2;
  v.scrollLeft = cx * v.scrollWidth - v.clientWidth / 2;
}

export function updateSelection() {
  for (const el of document.querySelectorAll(".region")) {
    const sel = Number(el.dataset.set) === state.setIdx;
    el.classList.toggle("selected", sel);
    el.setAttribute("aria-pressed", sel ? "true" : "false");
  }
}

function updatePosition() {
  const v = viewer();
  const mid = v.scrollTop + v.clientHeight * 0.3;
  let current = null;
  for (const [n, { fig }] of pageEls) {
    if (fig.offsetTop <= mid) current = n;
  }
  const total = state.pages?.pages.length ?? 0;
  $("#viewer-pos").textContent = current ? `Page ${current} of ${total}` : "";
}

/** Scroll the viewer so the target box (page-relative, in points) is comfortably in view. */
function scrollToBox(page, bbox, { force = false, smooth = true } = {}) {
  const el = pageEls.get(page);
  const info = state.pageInfo.get(page);
  if (!el || !info) return;
  const v = viewer();
  const k = el.page.clientWidth / info.width;
  // Page origin in the viewer's scroll coordinates (independent of offsetParent chains).
  const pr = el.page.getBoundingClientRect();
  const vr = v.getBoundingClientRect();
  const originY = pr.top - vr.top + v.scrollTop;
  const originX = pr.left - vr.left + v.scrollLeft;
  const top = originY + bbox[1] * k;
  const bottom = originY + bbox[3] * k;
  const left = originX + bbox[0] * k;
  const right = originX + bbox[2] * k;
  const margin = 48;
  const visibleY = top >= v.scrollTop + margin && bottom <= v.scrollTop + v.clientHeight - margin;
  const visibleX = left >= v.scrollLeft && right <= v.scrollLeft + v.clientWidth;
  if (!force && visibleY && visibleX) return;
  const behavior = smooth && !prefersReducedMotion() ? "smooth" : "auto";
  const y = bottom - top > v.clientHeight * 0.6 ? top - margin : top - v.clientHeight * 0.32;
  v.scrollTo({
    top: Math.max(0, y),
    left: visibleX ? v.scrollLeft : Math.max(0, left - v.clientWidth * 0.2),
    behavior,
  });
}

export function scrollToSet(idx, { smooth = true } = {}) {
  const set = state.result?.sets[idx];
  const region = set?.location.regions[0];
  if (!region) {
    const p = set ? setPages(set)[0] : null;
    if (p) pageEls.get(p)?.fig.scrollIntoView({ block: "start" });
    return;
  }
  const [x0, y0, x1] = region.bbox;
  scrollToBox(region.page, [x0, y0 - 24, x1, y0 + 60], { force: true, smooth });
}

export function clearHighlight() {
  hlSeq++;
  clearTimeout(scrollTimer);
  for (const { hl } of pageEls.values()) {
    for (const c of [...hl.children]) {
      c.classList.add("leaving");
      setTimeout(() => c.remove(), 140);
    }
  }
}

/**
 * Highlight source tokens of a field. `scroll`: "now" | "lazy" (after a short dwell, for
 * hover sweeps) | "none". Returns the resolved tokens (for the inspector).
 */
export async function highlight(tokenIds, { label = "", level = "", scroll = "lazy" } = {}) {
  const seq = ++hlSeq;
  clearTimeout(scrollTimer);
  const tokens = tokenIds.length ? await resolveTokens(tokenIds) : [];
  if (seq !== hlSeq) return tokens;
  for (const { hl } of pageEls.values()) hl.replaceChildren();
  if (!tokens.length) return tokens;

  const byPage = new Map();
  for (const t of tokens) {
    if (!byPage.has(t.page)) byPage.set(t.page, []);
    byPage.get(t.page).push(t);
  }
  let first = null;
  for (const [page, toks] of byPage) {
    const el = pageEls.get(page);
    const info = state.pageInfo.get(page);
    if (!el || !info) continue;
    const union = [
      Math.min(...toks.map((t) => t.bbox[0])),
      Math.min(...toks.map((t) => t.bbox[1])),
      Math.max(...toks.map((t) => t.bbox[2])),
      Math.max(...toks.map((t) => t.bbox[3])),
    ];
    first ??= { page, union };
    const spot = place(h("div.hl-spot"), union, info, 3);
    if (label) spot.append(h(`span.hl-label.lvl-${level || "none"}`, {}, label));
    el.hl.append(spot, ...toks.map((t) => place(h("div.hl-tok"), t.bbox, info, 1)));
    // Start the image fetch if a highlight lands on a page not yet scrolled near.
    if (!el.img.src) el.img.src = api.pngUrl(state.docId, page);
  }
  if (first && scroll !== "none") {
    const go = () => seq === hlSeq && scrollToBox(first.page, first.union);
    if (scroll === "now") go();
    else scrollTimer = setTimeout(go, 160);
  }
  return tokens;
}

export function initViewer() {
  const v = viewer();
  new ResizeObserver(() => layout()).observe(v);
  v.addEventListener("scroll", () => requestAnimationFrame(updatePosition), { passive: true });
  let wheelAcc = 0; // accumulate trackpad pinch deltas so one gesture is one zoom step
  v.addEventListener(
    "wheel",
    (e) => {
      if (!e.ctrlKey && !e.metaKey) return;
      e.preventDefault();
      wheelAcc += e.deltaY;
      if (Math.abs(wheelAcc) < 40) return;
      setZoom(wheelAcc < 0 ? 1 : -1);
      wheelAcc = 0;
    },
    { passive: false },
  );
  $("#zoom-in").addEventListener("click", () => setZoom(1));
  $("#zoom-out").addEventListener("click", () => setZoom(-1));
  $("#zoom-fit").addEventListener("click", () => setZoom(0));
}
