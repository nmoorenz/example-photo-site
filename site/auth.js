/**
 * auth.js — Simple client-side password gate
 *
 * The password is stored as an environment variable in Netlify and injected
 * into a generated config.js at build time (see netlify.toml build command).
 *
 * This is lightweight protection — suitable for a personal photo site.
 * It does NOT protect the S3 URLs directly; anyone with a direct S3 URL
 * can still access images. For stronger protection, put CloudFront + signed
 * URLs in front of S3 (see README for details).
 */

(function () {
  const SESSION_KEY = "photos_auth";
  const HASH_KEY    = "photos_pw_hash";

  // ── Helpers ────────────────────────────────────────────────────────────────

  async function sha256(str) {
    const buf = await crypto.subtle.digest(
      "SHA-256",
      new TextEncoder().encode(str)
    );
    return Array.from(new Uint8Array(buf))
      .map(b => b.toString(16).padStart(2, "0"))
      .join("");
  }

  function getExpectedHash() {
    // Injected by Netlify build: window.PHOTO_SITE_CONFIG = { pwHash: "..." }
    return window.PHOTO_SITE_CONFIG?.pwHash || null;
  }

  function isAuthenticated() {
    return sessionStorage.getItem(SESSION_KEY) === "1";
  }

  function showApp() {
    document.getElementById("gate")?.classList.add("hidden");
    document.getElementById("app")?.classList.remove("hidden");
  }

  function showError(msg) {
    const el = document.getElementById("gate-error");
    if (el) el.textContent = msg;
  }

  // ── Boot ───────────────────────────────────────────────────────────────────

  const hash = getExpectedHash();

  // If no password is configured, skip the gate entirely
  if (!hash) {
    showApp();
    return;
  }

  // Already authenticated in this session
  if (isAuthenticated()) {
    showApp();
    return;
  }

  // Show gate and wire up input
  const input = document.getElementById("gate-input");
  if (!input) return;

  input.focus();

  input.addEventListener("keydown", async (e) => {
    if (e.key !== "Enter") return;

    const value = input.value.trim();
    if (!value) return;

    const entered = await sha256(value);
    if (entered === hash) {
      sessionStorage.setItem(SESSION_KEY, "1");
      showApp();
    } else {
      showError("incorrect password");
      input.value = "";
      input.focus();
      setTimeout(() => showError(""), 2000);
    }
  });
})();
