/*
 * Shared backend access for the calculator pages.
 *
 * Locally (localhost, 127.0.0.1 or file://) pages call the backend started by
 * `mise run start` on port 8000, which needs no token. On GitHub Pages they call
 * the hosted backend, which expects the token pasted into #api-token (kept in
 * localStorage).
 */
(function () {
  "use strict";

  const IS_LOCAL = ["localhost", "127.0.0.1", ""].includes(window.location.hostname);
  const URL = IS_LOCAL ? "http://localhost:8000" : "https://python-trading-mlfz.onrender.com";

  function getToken() {
    try { return localStorage.getItem("api_token") || ""; } catch (e) { return ""; }
  }

  // GET or POST `path` on the backend; returns parsed JSON or throws with a readable message.
  async function call(path, options = {}) {
    let response;
    try {
      response = await fetch(`${URL}${path}`, { ...options, headers: { ...(options.headers || {}), "X-API-Token": getToken() } });
    } catch (e) {
      throw new Error(IS_LOCAL
        ? "Could not reach the local backend on port 8000. Start it with: mise run start"
        : "Could not reach the backend. It may be waking up; try again in a minute.");
    }
    if (!response.ok) {
      const body = await response.text();
      throw new Error(response.status === 401 ? "Unauthorized: check the API token." : `Server returned ${response.status}: ${body}`);
    }
    return response.json();
  }

  document.addEventListener("DOMContentLoaded", () => {
    const el = document.getElementById("api-token");
    if (!el) return;
    el.value = getToken();
    el.addEventListener("input", () => { try { localStorage.setItem("api_token", el.value); } catch (e) {} });
    const hint = document.getElementById("api-token-hint");
    if (hint) {
      hint.textContent = IS_LOCAL
        ? "Using the local backend (localhost:8000); no token needed."
        : "Required by the hosted backend. Stored only in this browser.";
    }
  });

  window.Backend = { url: URL, isLocal: IS_LOCAL, call };
})();
