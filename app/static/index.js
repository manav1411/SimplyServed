console.log(
  "%cSimplyServed — made by Manav\nIf you're reading this, you're one of us.",
  "font-size:14px;font-weight:bold;color:#52ff80;"
);

document.addEventListener("DOMContentLoaded", () => {
  initializeProgressBars();
  initializeMovieCards();
  initializeGreeting();
  initializeRequests();
  initializeControlsPanel();
  initializeSearchForm();
  initializeGenreFilters();
  initializeEasterEggs();
});

function initializeProgressBar(container) {
  if (!container) return;
  const seconds = parseFloat(container.dataset.seconds);
  const duration = parseFloat(container.dataset.duration);
  const bar = container.querySelector(".progress-bar");
  if (bar && duration > 0 && seconds > 0) {
    bar.style.width = `${Math.min((seconds / duration) * 100, 100)}%`;
  }
}

function initializeProgressBars() {
  document.querySelectorAll(".progress-container").forEach(initializeProgressBar);
}

function initializeMovieCard(movieEl) {
  if (!movieEl) return;
  const isMobile = /Mobi|Android/i.test(navigator.userAgent);
  const link = movieEl.querySelector("a");
  let tappedOnce = false;

  movieEl.addEventListener("click", (event) => {
    const expanded = movieEl.getAttribute("aria-expanded") === "true";
    if (isMobile && !expanded) {
      event.preventDefault();
      movieEl.setAttribute("aria-expanded", "true");
      tappedOnce = true;
      movieEl.scrollIntoView({ behavior: "smooth", block: "start" });
      setTimeout(() => { tappedOnce = false; }, 2000);
      return;
    }
    if (isMobile && tappedOnce && link) {
      window.location.href = link.href;
      return;
    }
    movieEl.setAttribute("aria-expanded", expanded ? "false" : "true");
    if (!expanded) {
      movieEl.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  });
}

function initializeMovieCards() {
  document.querySelectorAll(".movie").forEach(initializeMovieCard);
}

function initializeGreeting() {
  const greeting = document.getElementById("greeting");
  if (!greeting) return;

  const name = document.body.dataset.userName || "there";
  const hour = new Date().getHours();
  const avatars = ["🎬", "🍿", "🎥", "🌌", "🛸", "🤖", "🧙‍♂️"];
  const randomAvatar = avatars[Math.floor(Math.random() * avatars.length)];
  const safeName = name.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const emojiSpan = `<span id="greeting-emoji">${randomAvatar}</span>`;

  if (hour >= 0 && hour < 5) {
    greeting.innerHTML = `bit late for a movie innit, ${safeName}? ${emojiSpan}`;
  } else {
    let timeOfDay = "Hello";
    if (hour < 12) timeOfDay = "Good morning";
    else if (hour < 18) timeOfDay = "Good afternoon";
    else timeOfDay = "Good evening";
    greeting.innerHTML = `${timeOfDay}, ${safeName} ${emojiSpan}`;
  }
}

function initializeRequests() {
  document.querySelectorAll("#searched-movies .close-btn").forEach((btn) => {
    btn.addEventListener("click", async (event) => {
      const movieDiv = event.target.closest(".tmdb-result");
      const movieId = movieDiv.dataset.id;
      try {
        const response = await fetch(`/cancel_download/${movieId}`, { method: "POST" });
        if (response.ok || response.status === 404) {
          movieDiv.remove();
        } else {
          alert("Failed to cancel");
        }
      } catch {
        alert("Error cancelling movie");
      }
    });
  });

  document.querySelectorAll(".tmdb-result").forEach(async (div) => {
    const tmdbId = div.dataset.id;
    const title = div.dataset.title;
    const initialState = div.dataset.state;
    const initialError = div.dataset.error;
    const statusDiv = div.querySelector(".download-status");
    const progressBar = statusDiv.querySelector("progress");
    const statusText = statusDiv.querySelector(".status-text");

    if (initialState === "failed") {
      statusText.textContent = initialError || "Request failed";
      return;
    }

    const stateResponse = await fetch(`/download_state/${tmdbId}`);
    const stateData = await stateResponse.json();
    if (stateData.state === "completed") {
      div.remove();
      return;
    }
    if (stateData.state === "failed") {
      statusText.textContent = stateData.error || "Request failed";
      return;
    }

    statusText.textContent = "Loading...";
    startPolling(div, tmdbId, title, progressBar, statusText);
  });
}

function pollIntervalMs(elapsedSeconds) {
  if (elapsedSeconds < 60) return 3000;
  if (elapsedSeconds < 300) return 5000;
  return 10000;
}

function startPolling(div, tmdbId, title, progressBar, statusText) {
  let elapsedSeconds = 0;
  const HARD_STOP_SECONDS = 30 * 60;

  async function tick() {
    if (elapsedSeconds >= HARD_STOP_SECONDS) {
      statusText.textContent = "Stalled — check qBittorrent";
      return;
    }

    let data, ok;
    try {
      const response = await fetch(`/download_status/${encodeURIComponent(title)}`);
      data = await response.json();
      ok = response.ok;
    } catch {
      statusText.textContent = "Connection error, retrying...";
      const ms = pollIntervalMs(elapsedSeconds);
      elapsedSeconds += ms / 1000;
      setTimeout(tick, ms);
      return;
    }

    if (!ok) {
      statusText.textContent = data.error || "Download not found";
      return;
    }

    progressBar.value = data.progress;
    if (data.state === "processing") {
      statusText.textContent = "Processing...";
    } else if (data.state === "searching") {
      statusText.textContent = "Searching for torrent...";
    } else {
      statusText.textContent = `${(data.progress * 100).toFixed(1)}% - ${data.state}`;
    }

    if (data.progress >= 1.0 && data.state === "ready") {
      div.remove();
      addMovieCard(tmdbId);
      return;
    }

    const ms = pollIntervalMs(elapsedSeconds);
    elapsedSeconds += ms / 1000;
    setTimeout(tick, ms);
  }

  const initialMs = pollIntervalMs(0);
  elapsedSeconds += initialMs / 1000;
  setTimeout(tick, initialMs);
}

async function addMovieCard(tmdbId) {
  try {
    const response = await fetch(`/movie_card/${tmdbId}`);
    if (!response.ok) { window.location.reload(); return; }
    const html = await response.text();
    const moviesDiv = document.querySelector(".movies");
    if (!moviesDiv) { window.location.reload(); return; }

    const temp = document.createElement("div");
    temp.innerHTML = html.trim();
    const card = temp.firstElementChild;
    if (!card) { window.location.reload(); return; }

    // Ensure CSS filter rules exist for any new genres on this card
    const slugs = (card.dataset.genresSlugs || "").split(" ").filter(Boolean);
    if (slugs.length) {
      let styleEl = document.getElementById("genre-filter-rules");
      if (!styleEl) {
        styleEl = document.createElement("style");
        styleEl.id = "genre-filter-rules";
        document.head.appendChild(styleEl);
      }
      slugs.forEach((slug) => {
        if (!styleEl.textContent.includes(`.filter-${slug}`)) {
          styleEl.textContent += `.filter-${slug} .movie-block:not([data-genres-slugs~="${slug}"]) { display: none; }\n`;
          styleEl.textContent += `.filter-${slug} .genre[data-genre-slug="${slug}"] { background-color: #cbcbcb; color: #000; }\n`;
        }
      });
    }

    moviesDiv.appendChild(card);
    initializeMovieCard(card.querySelector(".movie"));
    initializeProgressBar(card.querySelector(".progress-container"));
    attachGenreSpanListeners(card.querySelectorAll(".movie-info .genre"));
  } catch {
    window.location.reload();
  }
}

function initializeControlsPanel() {
  const toggleBtn = document.getElementById("controls-toggle");
  const panel = document.getElementById("controls-panel");
  if (!toggleBtn || !panel) return;

  let cachedStorageData = null;
  let cachedStatsData = null;
  let activeTab = "about";

  // --- Storage tab ---
  function renderStorageData(data) {
    cachedStorageData = data;
    document.getElementById("storage-info").innerHTML =
      `<div style="text-align: center; font-size: 1.5em; font-weight: bold;">Library size: ${(data.total_size / 1024).toFixed(2)} GB</div>`;
    const ul = document.getElementById("media-directories");
    ul.innerHTML = "";
    data.directories.forEach((dir) => {
      const li = document.createElement("li");
      li.innerHTML = `<span>${dir.name} (${(dir.size / 1024).toFixed(2)} GB)</span><button class="delete-btn" data-folder="${dir.name}">Delete</button>`;
      ul.appendChild(li);
    });
  }

  function loadStorage() {
    if (cachedStorageData) {
      renderStorageData(cachedStorageData);
      fetch("/controls_info").then((r) => r.json()).then((d) => { cachedStorageData = d; renderStorageData(d); }).catch(() => {});
    } else {
      fetch("/controls_info").then((r) => r.json()).then(renderStorageData).catch(() => {
        document.getElementById("storage-info").textContent = "Failed to load storage info";
      });
    }
  }

  // --- Stats tab ---
  function renderStatsData(data) {
    cachedStatsData = data;
    const topGenres = data.top_genres.length ? data.top_genres.join(", ") : "N/A";
    document.getElementById("stats-content").innerHTML = `
      <div class="stat-item"><span>Library</span><span class="stat-value">${data.total_movies} movies</span></div>
      <div class="stat-item"><span>Hours watched</span><span class="stat-value">${data.hours_watched} hrs</span></div>
      <div class="stat-item"><span>Movies started</span><span class="stat-value">${data.movies_started}</span></div>
      <div class="stat-item"><span>Your requests</span><span class="stat-value">${data.requests_made}</span></div>
      <div class="stat-item"><span>Top genres</span><span class="stat-value">${topGenres}</span></div>
    `;
  }

  function loadStats() {
    if (cachedStatsData) { renderStatsData(cachedStatsData); return; }
    document.getElementById("stats-content").textContent = "Loading...";
    fetch("/settings_stats").then((r) => r.json()).then(renderStatsData).catch(() => {
      document.getElementById("stats-content").textContent = "Failed to load stats";
    });
  }

  // --- Tab switching ---
  function activatePaneUI(tab) {
    panel.querySelectorAll(".settings-tab").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.tab === tab);
    });
    panel.querySelectorAll(".settings-pane").forEach((pane) => {
      pane.classList.toggle("hidden", pane.id !== `pane-${tab}`);
    });
  }

  function showTab(tab) {
    activeTab = tab;
    activatePaneUI(tab);
    if (tab === "storage") loadStorage();
    else if (tab === "stats") loadStats();
  }

  panel.querySelectorAll(".settings-tab").forEach((btn) => {
    btn.addEventListener("click", () => showTab(btn.dataset.tab));
  });

  // Set initial pane state immediately so it's correct before the panel is even opened
  activatePaneUI("about");

  // Pre-fetch storage so data is ready before the user opens the panel
  setTimeout(() => {
    fetch("/controls_info").then((r) => r.json()).then((d) => { cachedStorageData = d; }).catch(() => {});
  }, 1500);

  toggleBtn.addEventListener("click", () => {
    panel.classList.toggle("hidden");
    if (!panel.classList.contains("hidden")) showTab(activeTab);
  });

  // Close when clicking outside the panel or toggle button
  document.addEventListener("click", (event) => {
    if (panel.classList.contains("hidden")) return;
    if (!panel.contains(event.target) && !toggleBtn.contains(event.target)) {
      panel.classList.add("hidden");
    }
  });

  // Inline delete confirmation
  document.getElementById("media-directories").addEventListener("click", (event) => {
    const deleteBtn = event.target.closest(".delete-btn");
    if (!deleteBtn) return;
    const folder = deleteBtn.dataset.folder;
    const li = deleteBtn.closest("li");

    deleteBtn.hidden = true;
    const confirmEl = document.createElement("span");
    confirmEl.className = "delete-confirm";
    confirmEl.innerHTML = `Sure? <button class="confirm-yes">Yes</button><button class="confirm-no">No</button>`;
    li.appendChild(confirmEl);

    confirmEl.querySelector(".confirm-no").addEventListener("click", () => {
      confirmEl.remove();
      deleteBtn.hidden = false;
    });

    confirmEl.querySelector(".confirm-yes").addEventListener("click", () => {
      confirmEl.innerHTML = "<em>Deleting...</em>";
      fetch(`/delete_folder/${encodeURIComponent(folder)}`, { method: "POST" }).then(() => location.reload());
    });
  });

  const resetBtn = document.getElementById("reset-search-btn");
  if (resetBtn) {
    resetBtn.addEventListener("click", () => {
      fetch("/reset_search", { method: "POST" }).then(() => location.reload());
    });
  }
}

function initializeSearchForm() {
  const form = document.querySelector(".search-container form");
  const statusDiv = document.querySelector(".search-status");
  if (!form || !statusDiv) return;

  form.addEventListener("submit", (e) => {
    const query = (form.querySelector('input[name="query"]')?.value || "").trim().toLowerCase();
    if (query === "popcorn") {
      e.preventDefault();
      triggerPopcornRain();
      return;
    }
    statusDiv.style.display = "block";
    const button = form.querySelector("button[type='submit']");
    if (button) button.disabled = true;
  });
}

function applyGenreFilter(slug) {
  document.body.className = document.body.className.replace(/\bfilter-\S+/g, "").trim();
  if (slug && slug !== "all") {
    document.body.classList.add(`filter-${slug}`);
  }
}

function attachGenreSpanListeners(spans) {
  spans.forEach((genreSpan) => {
    genreSpan.style.cursor = "pointer";
    genreSpan.addEventListener("click", () => {
      const selectedGenre = genreSpan.textContent.trim();
      const slug = selectedGenre.toLowerCase().replace(/ /g, "-");
      const tags = document.querySelectorAll(".tag-filter");
      tags.forEach((tag) => tag.classList.remove("active"));
      if (document.body.classList.contains(`filter-${slug}`)) {
        applyGenreFilter("all");
        return;
      }
      const correspondingTag = Array.from(tags).find((tag) => tag.dataset.slug === slug);
      if (correspondingTag) correspondingTag.classList.add("active");
      applyGenreFilter(slug);
      document.getElementById("tag-filter-wrapper").scrollIntoView({ behavior: "smooth" });
    });
  });
}

function initializeGenreFilters() {
  const tags = document.querySelectorAll(".tag-filter");

  tags.forEach((tag) => {
    tag.addEventListener("click", () => {
      const slug = tag.dataset.slug || "all";
      const isActive = tag.classList.contains("active");
      tags.forEach((item) => item.classList.remove("active"));
      if (isActive) {
        applyGenreFilter("all");
      } else {
        tag.classList.add("active");
        applyGenreFilter(slug);
      }
    });
  });

  attachGenreSpanListeners(document.querySelectorAll(".movie-info .genre"));
}

// ---- Easter eggs ----

function initializeEasterEggs() {
  initializeEmojiEasterEgg();
  initializeAvatarEasterEgg();
}

function initializeEmojiEasterEgg() {
  const emojiEl = document.getElementById("greeting-emoji");
  if (!emojiEl) return;
  let clickCount = 0;
  let resetTimeout = null;
  emojiEl.addEventListener("click", () => {
    clickCount++;
    clearTimeout(resetTimeout);
    resetTimeout = setTimeout(() => { clickCount = 0; }, 3000);
    if (clickCount >= 5) {
      clickCount = 0;
      clearTimeout(resetTimeout);
      triggerCredits();
    }
  });
}

function triggerCredits() {
  if (document.getElementById("credits-overlay")) return;
  const overlay = document.createElement("div");
  overlay.id = "credits-overlay";
  overlay.innerHTML = `
    <div class="credits-scroll">
      <p class="credits-title">S I M P L Y S E R V E D</p>
      <div class="credits-row"><span>Written &amp; Directed by</span><span>Manav Dodia</span></div>
      <div class="credits-row"><span>Produced by</span><span>Manav Dodia</span></div>
      <div class="credits-row"><span>Cinematography</span><span>Manav Dodia</span></div>
      <div class="credits-row"><span>Visual Effects</span><span>Manav Dodia</span></div>
      <div class="credits-row"><span>Catering</span><span>Manav Dodia</span></div>
      <p class="credits-footer">Filmed entirely on a Raspberry Pi 400.<br>No movies were harmed.</p>
    </div>
  `;
  overlay.addEventListener("click", () => overlay.remove());
  document.body.appendChild(overlay);
  setTimeout(() => overlay.remove(), 9000);
}

function initializeAvatarEasterEgg() {
  const img = document.querySelector(".about-img");
  if (!img) return;
  const messages = ["Oi!", "Stop that!", "Scallywag..."];
  let index = 0;
  let bubble = null;
  let wobbleTimeout = null;
  img.style.cursor = "pointer";
  img.addEventListener("click", () => {
    img.classList.remove("avatar-wobble");
    clearTimeout(wobbleTimeout);
    void img.offsetWidth;
    img.classList.add("avatar-wobble");
    wobbleTimeout = setTimeout(() => img.classList.remove("avatar-wobble"), 500);

    if (bubble) bubble.remove();
    bubble = document.createElement("div");
    bubble.className = "speech-bubble";
    bubble.textContent = messages[index % messages.length];
    index++;
    const rect = img.getBoundingClientRect();
    bubble.style.cssText = `position:fixed;top:${rect.top - 44}px;left:${rect.left + rect.width / 2}px;transform:translateX(-50%);z-index:99999;`;
    document.body.appendChild(bubble);
    setTimeout(() => { if (bubble) { bubble.remove(); bubble = null; } }, 2000);
  });
}

function triggerPopcornRain() {
  const container = document.createElement("div");
  container.style.cssText = "position:fixed;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:99999;overflow:hidden;";
  document.body.appendChild(container);
  for (let i = 0; i < 35; i++) {
    const p = document.createElement("span");
    p.textContent = "🍿";
    p.style.cssText = `position:absolute;font-size:${1 + Math.random() * 1.2}em;left:${Math.random() * 100}%;top:-2em;animation:popcornFall ${1.5 + Math.random() * 2}s linear ${Math.random() * 2}s forwards;`;
    container.appendChild(p);
  }
  setTimeout(() => container.remove(), 6000);
}
