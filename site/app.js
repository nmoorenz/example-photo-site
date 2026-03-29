/**
 * app.js — Homepage: loads manifest.json and renders the albums grid
 */

(function () {
  const MANIFEST_URL = window.PHOTO_SITE_CONFIG?.manifestUrl
    || "https://cdn.example.com/manifest.json";

  const grid    = document.getElementById("albums-grid");
  const loading = document.getElementById("loading");
  const errorEl = document.getElementById("error-msg");

  async function loadManifest() {
    const res = await fetch(MANIFEST_URL + "?t=" + Date.now());
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  }

  function renderAlbums(albums) {
    loading.classList.add("hidden");

    if (!albums.length) {
      errorEl.classList.remove("hidden");
      errorEl.textContent = "No albums found.";
      return;
    }

    albums.forEach((album, i) => {
      const a = document.createElement("a");
      a.className = "album-card";
      a.href = `album.html?album=${encodeURIComponent(album.slug)}`;
      a.style.animationDelay = `${i * 60}ms`;

      const img = document.createElement("img");
      img.className = "album-card__img";
      img.src = album.cover || "";
      img.alt = album.title;
      img.loading = "lazy";

      const overlay = document.createElement("div");
      overlay.className = "album-card__overlay";

      const title = document.createElement("div");
      title.className = "album-card__title";
      title.textContent = album.title;

      const meta = document.createElement("div");
      meta.className = "album-card__meta";
      meta.textContent = album.date || "";

      const count = document.createElement("div");
      count.className = "album-card__count";
      count.textContent = `${album.photos.length} photo${album.photos.length !== 1 ? "s" : ""}`;

      overlay.appendChild(title);
      overlay.appendChild(meta);
      a.appendChild(img);
      a.appendChild(overlay);
      a.appendChild(count);
      grid.appendChild(a);
    });
  }

  loadManifest()
    .then(data => renderAlbums(data.albums || []))
    .catch(err => {
      loading.classList.add("hidden");
      errorEl.classList.remove("hidden");
      errorEl.textContent = "Could not load albums. Check your S3 configuration.";
      console.error("Manifest load failed:", err);
    });
})();
