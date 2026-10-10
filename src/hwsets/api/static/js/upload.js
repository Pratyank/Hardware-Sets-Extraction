// "Upload PDF": posts a PDF to /api/docs/upload with progress, then opens the new document.
// Self-contained: after a successful upload it points the hash at the new doc and reloads,
// so the document list is refreshed by the normal boot path in app.js.

import { $, toast } from "./util.js";

const MAX_BYTES = 100 * 1024 * 1024;

function post(file, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const form = new FormData();
    form.append("file", file, file.name);
    xhr.open("POST", "/api/docs/upload");
    xhr.responseType = "json";
    xhr.upload.addEventListener("progress", (e) => {
      if (e.lengthComputable) onProgress(e.loaded / e.total);
    });
    xhr.upload.addEventListener("load", () => onProgress(1));
    xhr.addEventListener("load", () => {
      const body = xhr.response || {};
      if (xhr.status >= 200 && xhr.status < 300) resolve(body);
      else reject(new Error(typeof body.detail === "string" ? body.detail : `${xhr.status} ${xhr.statusText}`));
    });
    xhr.addEventListener("error", () => reject(new Error("network error")));
    xhr.send(form);
  });
}

function setBusy(btn, label) {
  btn.disabled = label !== null;
  btn.textContent = label ?? "Upload PDF";
}

async function onFile(input, btn) {
  const file = input.files && input.files[0];
  input.value = "";
  if (!file) return;
  if (file.size > MAX_BYTES) {
    toast("File too large", { kind: "error", detail: "The limit is 100 MB." });
    return;
  }
  if (file.type && file.type !== "application/pdf") {
    toast("Not a PDF", { kind: "error", detail: file.name });
    return;
  }
  setBusy(btn, "Uploading 0%");
  try {
    const res = await post(file, (f) => {
      setBusy(btn, f < 1 ? `Uploading ${Math.round(f * 100)}%` : "Extracting…");
    });
    toast(`Extracted ${res.n_sets} sets from ${file.name}`, {
      kind: "success",
      detail: `${res.doc_id} · ${res.n_pages} pages`,
    });
    location.hash = `doc=${encodeURIComponent(res.doc_id)}&set=0`;
    setTimeout(() => location.reload(), 600);
  } catch (err) {
    toast("Upload failed", { kind: "error", detail: err.message });
    setBusy(btn, null);
  }
}

export function initUpload() {
  const btn = $("#btn-upload");
  const input = $("#upload-input");
  if (!btn || !input) return;
  btn.addEventListener("click", () => input.click());
  input.addEventListener("change", () => onFile(input, btn));
}

initUpload();
