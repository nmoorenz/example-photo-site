/**
 * album.js — Album page: photo slider with thumbnails, captions + lightbox
 */

(function () {
  const MANIFEST_URL = window.PHOTO_SITE_CONFIG?.manifestUrl
    || "https://cdn.example.com/manifest.json";

  // ── Elements ───────────────────────────────────────────────────────────────
  const loading       = document.getElementById("loading");
  const sliderWrap    = document.getElementById("slider-wrap");
  const track         = document.getElementById("slider-track");
  const prevBtn       = document.getElementById("prev-btn");
  const nextBtn       = document.getElementById("next-btn");
  const counter       = document.getElementById("counter");
  const captionEl     = document.getElementById("caption");
  const thumbs        = document.getElementById("thumbnails");
  const lightbox      = document.getElementById("lightbox");
  const lbImg         = document.getElementById("lightbox-img");
  const lbCaption     = document.getElementById("lightbox-caption");
  const lbClose       = document.getElementById("lb-close");
  const lbPrev        = document.getElementById("lb-prev");
  const lbNext        = document.getElementById("lb-next");

  let photos  = [];
  let current = 0;

  // ── Slug from URL ──────────────────────────────────────────────────────────
  const params = new URLSearchParams(location.search);
  const slug   = params.get("album");

  if (!slug) {
    location.href = "index.html";
    return;
  }

  // ── Load ───────────────────────────────────────────────────────────────────
  async function loadAlbum() {
    const res = await fetch(MANIFEST_URL + "?t=" + Date.now());
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const album = (data.albums || []).find(a => a.slug === slug);
    if (!album) throw new Error("Album not found");
    return album;
  }

  // ── Render ─────────────────────────────────────────────────────────────────
  function renderAlbum(album) {
    document.title = `${album.title} — Photos`;
    document.getElementById("album-title").textContent       = album.title;
    document.getElementById("album-date").textContent        = album.date || "";
    document.getElementById("album-description").textContent = album.description || "";

    photos = album.photos;

    photos.forEach((photo, i) => {
      // Slide
      const slide = document.createElement("div");
      slide.className = "slide";
      slide.dataset.index = i;

      const img = document.createElement("img");
      img.alt = photo.caption || `${album.title} — ${i + 1}`;
      img.className = "loading-img";
      if (i < 3) {
        img.src = photo.url;
        img.onload = () => img.classList.replace("loading-img", "loaded-img");
      } else {
        img.dataset.src = photo.url;
      }
      img.addEventListener("click", () => openLightbox(i));

      slide.appendChild(img);
      track.appendChild(slide);

      // Thumbnail
      const thumb = document.createElement("img");
      thumb.className = "thumb" + (i === 0 ? " active" : "");
      thumb.alt = photo.caption || "";
      thumb.loading = "lazy";
      thumb.src = photo.url;
      thumb.title = photo.caption || "";
      thumb.addEventListener("click", () => goTo(i));
      thumbs.appendChild(thumb);
    });

    loading.classList.add("hidden");
    sliderWrap.classList.remove("hidden");
    updateUI();
  }

  // ── Slider nav ─────────────────────────────────────────────────────────────
  function goTo(index) {
    current = Math.max(0, Math.min(index, photos.length - 1));
    track.style.transform = `translateX(-${current * 100}%)`;
    lazyLoadAround(current);
    updateUI();
  }

  function lazyLoadAround(index) {
    [-1, 0, 1, 2].forEach(offset => {
      const i = index + offset;
      if (i < 0 || i >= photos.length) return;
      const img = track.children[i]?.querySelector("img");
      if (img && img.dataset.src) {
        img.src = img.dataset.src;
        img.onload = () => img.classList.replace("loading-img", "loaded-img");
        delete img.dataset.src;
      }
    });
  }

  function updateUI() {
    const photo = photos[current];

    counter.textContent = `${current + 1} / ${photos.length}`;
    prevBtn.disabled = current === 0;
    nextBtn.disabled = current === photos.length - 1;

    // Caption — show element only if there's text
    if (captionEl) {
      captionEl.textContent = photo?.caption || "";
      captionEl.classList.toggle("hidden", !photo?.caption);
    }

    // Thumbnails
    Array.from(thumbs.children).forEach((t, i) => {
      t.classList.toggle("active", i === current);
    });
    thumbs.children[current]?.scrollIntoView({ block: "nearest", inline: "center", behavior: "smooth" });
  }

  prevBtn?.addEventListener("click", () => goTo(current - 1));
  nextBtn?.addEventListener("click", () => goTo(current + 1));

  // Keyboard
  document.addEventListener("keydown", e => {
    if (lightbox && !lightbox.classList.contains("hidden")) {
      if (e.key === "ArrowLeft")  { goTo(current - 1); updateLightbox(); }
      if (e.key === "ArrowRight") { goTo(current + 1); updateLightbox(); }
      if (e.key === "Escape")     closeLightbox();
      return;
    }
    if (e.key === "ArrowLeft")  goTo(current - 1);
    if (e.key === "ArrowRight") goTo(current + 1);
  });

  // Touch / swipe
  let touchStartX = 0;
  track.addEventListener("touchstart", e => { touchStartX = e.touches[0].clientX; }, { passive: true });
  track.addEventListener("touchend", e => {
    const dx = e.changedTouches[0].clientX - touchStartX;
    if (Math.abs(dx) > 40) dx < 0 ? goTo(current + 1) : goTo(current - 1);
  });

  // ── Lightbox ───────────────────────────────────────────────────────────────
  function updateLightbox() {
    const photo = photos[current];
    lbImg.src = photo.url;
    if (lbCaption) {
      lbCaption.textContent = photo.caption || "";
      lbCaption.classList.toggle("hidden", !photo.caption);
    }
  }

  function openLightbox(index) {
    current = index;
    updateLightbox();
    lightbox.classList.remove("hidden");
    document.body.style.overflow = "hidden";
  }

  function closeLightbox() {
    lightbox.classList.add("hidden");
    document.body.style.overflow = "";
  }

  lbClose?.addEventListener("click", closeLightbox);
  lbPrev?.addEventListener("click",  () => { goTo(current - 1); updateLightbox(); });
  lbNext?.addEventListener("click",  () => { goTo(current + 1); updateLightbox(); });
  lightbox?.addEventListener("click", e => { if (e.target === lightbox) closeLightbox(); });

  // ── Boot ───────────────────────────────────────────────────────────────────
  loadAlbum()
    .then(renderAlbum)
    .catch(err => {
      loading.classList.add("hidden");
      console.error("Album load failed:", err);
    });
})();
