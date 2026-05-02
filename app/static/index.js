document.addEventListener("DOMContentLoaded", () => {
  initializeProgressBars();
  initializeMovieCards();
  initializeGreeting();
  initializeRequests();
  initializeControlsPanel();
  initializeSearchForm();
  initializeGenreFilters();
});

function initializeProgressBars() {
  document.querySelectorAll(".progress-container").forEach((container) => {
    const seconds = parseFloat(container.dataset.seconds);
    const duration = parseFloat(container.dataset.duration);
    const bar = container.querySelector(".progress-bar");
    if (bar && duration > 0 && seconds > 0) {
      bar.style.width = `${Math.min((seconds / duration) * 100, 100)}%`;
    }
  });
}

function initializeMovieCards() {
  const isMobile = /Mobi|Android/i.test(navigator.userAgent);
  document.querySelectorAll(".movie").forEach((movieDiv) => {
    const link = movieDiv.querySelector("a");
    let tappedOnce = false;

    movieDiv.addEventListener("click", (event) => {
      const expanded = movieDiv.getAttribute("aria-expanded") === "true";
      if (isMobile && !expanded) {
        event.preventDefault();
        movieDiv.setAttribute("aria-expanded", "true");
        tappedOnce = true;
        movieDiv.scrollIntoView({ behavior: "smooth", block: "start" });
        setTimeout(() => {
          tappedOnce = false;
        }, 2000);
        return;
      }

      if (isMobile && tappedOnce && link) {
        window.location.href = link.href;
        return;
      }

      movieDiv.setAttribute("aria-expanded", expanded ? "false" : "true");
      if (!expanded) {
        movieDiv.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    });
  });
}

function initializeGreeting() {
  const greeting = document.getElementById("greeting");
  if (!greeting) return;

  const name = document.body.dataset.userName || "there";
  const hour = new Date().getHours();
  const avatars = ["🎬", "🍿", "🎥", "🌌", "🛸", "🤖", "🧙‍♂️"];
  const randomAvatar = avatars[Math.floor(Math.random() * avatars.length)];
  let timeOfDay = "Hello";
  if (hour < 12) timeOfDay = "Good morning";
  else if (hour < 18) timeOfDay = "Good afternoon";
  else timeOfDay = "Good evening";
  greeting.textContent = `${timeOfDay}, ${name} ${randomAvatar}`;
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
    const statusDiv = div.querySelector(".download-status");
    const progressBar = statusDiv.querySelector("progress");
    const statusText = statusDiv.querySelector(".status-text");

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
    const poll = setInterval(async () => {
      const response = await fetch(`/download_status/${encodeURIComponent(title)}`);
      const data = await response.json();
      if (!response.ok) {
        statusText.textContent = data.error || "Download not found";
        clearInterval(poll);
        return;
      }

      progressBar.value = data.progress;
      statusText.textContent = `${(data.progress * 100).toFixed(1)}% - ${data.state}`;
      if (data.progress >= 1.0 || data.state === "ready") {
        clearInterval(poll);
        div.remove();
        window.location.reload();
      }
    }, 3000);
  });
}

function initializeControlsPanel() {
  const toggleBtn = document.getElementById("controls-toggle");
  const panel = document.getElementById("controls-panel");
  if (!toggleBtn || !panel) return;

  toggleBtn.addEventListener("click", () => {
    panel.classList.toggle("hidden");
    if (panel.classList.contains("hidden")) return;

    fetch("/controls_info")
      .then((res) => res.json())
      .then((data) => {
        document.getElementById("storage-info").innerHTML =
          `<div style="text-align: center; font-size: 1.5em; font-weight: bold;">Library size: ${(data.total_size / 1024).toFixed(2)} GB</div>`;

        const ul = document.getElementById("media-directories");
        ul.innerHTML = "";
        data.directories.forEach((dir) => {
          const li = document.createElement("li");
          li.innerHTML = `<span>${dir.name} (${(dir.size / 1024).toFixed(2)} GB)</span><button data-folder="${dir.name}">Delete</button>`;
          ul.appendChild(li);
        });
      });
  });

  document.getElementById("reset-search-btn").addEventListener("click", () => {
    fetch("/reset_search", { method: "POST" }).then(() => location.reload());
  });

  document.getElementById("media-directories").addEventListener("click", (event) => {
    if (event.target.tagName !== "BUTTON") return;
    const folder = event.target.getAttribute("data-folder");
    if (confirm(`Delete ${folder}?`)) {
      fetch(`/delete_folder/${encodeURIComponent(folder)}`, { method: "POST" }).then(() => location.reload());
    }
  });
}

function initializeSearchForm() {
  const form = document.querySelector(".search-container form");
  const statusDiv = document.querySelector(".search-status");
  if (!form || !statusDiv) return;

  form.addEventListener("submit", () => {
    statusDiv.style.display = "block";
    const button = form.querySelector("button[type='submit']");
    if (button) button.disabled = true;
  });
}

function initializeGenreFilters() {
  const tags = document.querySelectorAll(".tag-filter");
  const movies = document.querySelectorAll(".movie-block");
  const genresInMovies = document.querySelectorAll(".movie-info .genre");

  function filterMoviesByGenre(selected) {
    movies.forEach((movie) => {
      const genres = Array.from(movie.querySelectorAll(".genre")).map((el) => el.textContent.trim());
      movie.style.display = selected === "all" || genres.includes(selected) ? "block" : "none";
    });
  }

  tags.forEach((tag) => {
    tag.addEventListener("click", () => {
      const selected = tag.dataset.tag;
      const isActive = tag.classList.contains("active");
      tags.forEach((item) => item.classList.remove("active"));
      if (isActive) {
        filterMoviesByGenre("all");
      } else {
        tag.classList.add("active");
        filterMoviesByGenre(selected);
      }
    });
  });

  genresInMovies.forEach((genreSpan) => {
    genreSpan.style.cursor = "pointer";
    genreSpan.addEventListener("click", () => {
      const selectedGenre = genreSpan.textContent.trim();
      const correspondingTag = Array.from(tags).find((tag) => tag.dataset.tag === selectedGenre);
      tags.forEach((tag) => tag.classList.remove("active"));
      if (correspondingTag) {
        correspondingTag.classList.add("active");
      }
      filterMoviesByGenre(selectedGenre);
      document.getElementById("tag-filter-wrapper").scrollIntoView({ behavior: "smooth" });
    });
  });
}

