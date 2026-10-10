// Thin client for the review API. Every call throws an Error with the server's detail.

const enc = encodeURIComponent;

async function request(method, url, body) {
  const init = { method, headers: {} };
  if (body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  const res = await fetch(url, init);
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const j = await res.json();
      if (typeof j.detail === "string") detail = j.detail;
      else if (Array.isArray(j.detail)) {
        detail = j.detail.map((d) => `${(d.loc || []).slice(1).join(".")}: ${d.msg}`).join("; ");
      }
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail);
  }
  return res.json();
}

export const api = {
  listDocs: () => request("GET", "/api/docs/list"),
  result: (id) => request("GET", `/api/docs/${enc(id)}/result`),
  pages: (id) => request("GET", `/api/docs/${enc(id)}/pages`),
  tokens: (id, page) => request("GET", `/api/docs/${enc(id)}/tokens?page=${page}`),
  saveSet: (id, idx, set) => request("PUT", `/api/docs/${enc(id)}/sets/${idx}`, set),
  revertSet: (id, idx) => request("DELETE", `/api/docs/${enc(id)}/sets/${idx}`),
  exportGold: (id) => request("POST", `/api/docs/${enc(id)}/export-gold`),
  pngUrl: (id, page) => `/api/docs/${enc(id)}/page/${page}.png`,
};
