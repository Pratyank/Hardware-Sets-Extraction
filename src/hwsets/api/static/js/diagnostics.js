// Diagnostics tab: document summary, column-role assignment with margins, and warnings.

import { lowFieldCount, state } from "./state.js";
import { $, confLevel, h, pct } from "./util.js";

const ROLE_RE = /^\s*([^()]+?)\s*(?:\(\s*margin\s*([-\d.]+)\s*\))?\s*$/i;

function parseRole(key, value) {
  const m = ROLE_RE.exec(value) || [];
  const x = Number((/(-?\d+(?:\.\d+)?)/.exec(key) || [])[1]);
  return {
    key,
    x: Number.isFinite(x) ? x : Number.POSITIVE_INFINITY,
    role: (m[1] || value).trim(),
    margin: m[2] !== undefined ? Number(m[2]) : null,
    raw: value,
  };
}

function stat(label, value, cls = "") {
  return h("div.stat", {}, h("div.stat-value", { class: cls }, value), h("div.stat-label", {}, label));
}

export function renderDiagnostics() {
  const panel = $("#panel-diag");
  const res = state.result;
  const warnCount = $("#warn-count");
  if (!res) {
    panel.replaceChildren();
    warnCount.hidden = true;
    return;
  }
  warnCount.hidden = res.warnings.length === 0;
  warnCount.textContent = String(res.warnings.length);

  const active = res.sets.filter((s) => s.status !== "not_used");
  const sets = res.sets;
  const mean = sets.length ? sets.reduce((a, s) => a + s.confidence, 0) / sets.length : null;
  const low = res.sets.reduce((a, s) => a + lowFieldCount(s), 0);
  const nComp = res.sets.reduce((a, s) => a + s.components.length, 0);
  const roles = Object.entries(res.column_roles)
    .map(([k, v]) => parseRole(k, v))
    .sort((a, b) => a.x - b.x);
  const hp = res.hardware_pages;

  panel.replaceChildren(
    h(
      "section.diag-section",
      {},
      h("h3", {}, "Document"),
      h("div.diag-source", { title: res.source_pdf }, res.source_pdf),
      h(
        "div.stats",
        {},
        stat("sets", String(res.sets.length)),
        stat("not used", String(res.sets.length - active.length)),
        stat("components", String(nComp)),
        stat("mean confidence", pct(mean), `lvl-text-${confLevel(mean)}`),
        stat("low fields", String(low), low ? "lvl-text-lo" : ""),
      ),
      h(
        "div.diag-line",
        {},
        "Hardware pages: ",
        hp.length ? h("span.mono", {}, compactRanges(hp)) : h("span.muted", {}, "none detected"),
      ),
    ),
    h(
      "section.diag-section",
      {},
      h("h3", {}, "Column roles"),
      h("p.diag-hint", {}, "Role assigned to each column band, with the margin over the runner-up role."),
      roles.length
        ? h(
            "ul.roles",
            {},
            roles.map((r) =>
              h(
                "li.role",
                { title: `${r.key} → ${r.raw}` },
                h("span.role-x.mono", {}, r.key),
                h("span.role-arrow", { "aria-hidden": "true" }, "→"),
                h("span.role-name", {}, r.role),
                r.margin !== null
                  ? h(
                      "span.role-margin",
                      { "aria-label": `margin ${r.margin.toFixed(2)}` },
                      h(
                        "span.meter",
                        {},
                        h(`span.meter-fill.lvl-${confLevel(r.margin)}`, {
                          style: { width: `${Math.max(4, Math.min(1, r.margin) * 100)}%` },
                        }),
                      ),
                      h("span.mono", {}, r.margin.toFixed(2)),
                    )
                  : h("span.muted", {}, ""),
              ),
            ),
          )
        : h("p.muted", {}, "No column-role diagnostics recorded."),
    ),
    h(
      "section.diag-section",
      {},
      h("h3", {}, `Warnings${res.warnings.length ? ` (${res.warnings.length})` : ""}`),
      res.warnings.length
        ? h(
            "ul.warnings",
            {},
            res.warnings.map((w) => h("li.warning", {}, h("span.warn-icon", { "aria-hidden": "true" }, "!"), w)),
          )
        : h("p.muted", {}, "No warnings."),
    ),
  );
}

function compactRanges(nums) {
  const out = [];
  let start = nums[0];
  let prev = nums[0];
  for (const n of [...nums.slice(1), null]) {
    if (n !== null && n === prev + 1) {
      prev = n;
      continue;
    }
    out.push(start === prev ? `${start}` : `${start}–${prev}`);
    start = prev = n;
  }
  return out.join(", ");
}
