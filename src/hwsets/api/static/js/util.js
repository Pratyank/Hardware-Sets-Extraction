// Small shared helpers: DOM building, confidence levels, toasts, formatting.

export const LOW = 0.6;
export const HIGH = 0.85;

/** h('div.cls#id', {attrs}, ...children) — tiny hyperscript. */
export function h(tag, attrs = {}, ...children) {
  const [name, ...rest] = tag.split(/(?=[.#])/);
  const el = document.createElement(name || "div");
  for (const part of rest) {
    if (part[0] === ".") el.classList.add(part.slice(1));
    else el.id = part.slice(1);
  }
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === "class") el.className += ` ${v}`;
    else if (k === "dataset") {
      for (const [dk, dv] of Object.entries(v)) if (dv !== null && dv !== undefined) el.dataset[dk] = dv;
    }
    else if (k === "style" && typeof v === "object") Object.assign(el.style, v);
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (v === true) el.setAttribute(k, "");
    else el.setAttribute(k, String(v));
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

export function isEmpty(v) {
  return v === null || v === undefined || v === "";
}

/** Confidence level of a Field for colouring: hi | mid | lo | null | human. */
export function level(field) {
  if (!field) return "null";
  if (field.source === "human") return "human";
  if (isEmpty(field.value)) return "null";
  if (field.confidence >= HIGH) return "hi";
  if (field.confidence >= LOW) return "mid";
  return "lo";
}

export function confLevel(c) {
  if (c === null || c === undefined) return "null";
  return c >= HIGH ? "hi" : c >= LOW ? "mid" : "lo";
}

export const fmtConf = (c) => (c === null || c === undefined ? "–" : c.toFixed(2));
export const pct = (c) => (c === null || c === undefined ? "–" : `${Math.round(c * 100)}%`);

export function pageRange(pages) {
  if (!pages.length) return "";
  const lo = Math.min(...pages);
  const hi = Math.max(...pages);
  return lo === hi ? `p. ${lo}` : `p. ${lo}–${hi}`;
}

export function setPages(set) {
  return [...new Set(set.location.regions.map((r) => r.page))].sort((a, b) => a - b);
}

export function parseTokenId(id) {
  const m = /^p(\d+)_w(\d+)$/.exec(id);
  return m ? { page: Number(m[1]), index: Number(m[2]) } : null;
}

export const clone = (o) => structuredClone(o);

export function debounce(fn, ms) {
  let t = 0;
  const wrapped = (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
  wrapped.cancel = () => clearTimeout(t);
  return wrapped;
}

export const prefersReducedMotion = () =>
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/** Toast notifications (aria-live region in index.html). */
export function toast(message, { kind = "info", detail = "", timeout = 3800 } = {}) {
  const host = $("#toasts");
  const icon = { success: "✓", error: "!", info: "i" }[kind] || "i";
  const el = h(
    `div.toast.toast-${kind}`,
    { role: kind === "error" ? "alert" : null },
    h("span.toast-icon", { "aria-hidden": "true" }, icon),
    h("div.toast-body", {}, h("div.toast-msg", {}, message), detail && h("div.toast-detail", {}, detail)),
    h("button.toast-close", { type: "button", "aria-label": "Dismiss", onclick: () => dismiss() }, "×"),
  );
  host.append(el);
  requestAnimationFrame(() => el.classList.add("in"));
  let timer = setTimeout(dismiss, kind === "error" ? timeout * 2 : timeout);
  el.addEventListener("mouseenter", () => clearTimeout(timer));
  el.addEventListener("mouseleave", () => (timer = setTimeout(dismiss, 1500)));
  function dismiss() {
    clearTimeout(timer);
    el.classList.remove("in");
    el.classList.add("out");
    setTimeout(() => el.remove(), 220);
  }
}

export function isTyping(el) {
  if (!el) return false;
  const tag = el.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || el.isContentEditable;
}
