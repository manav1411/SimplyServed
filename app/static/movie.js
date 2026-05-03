document.addEventListener("DOMContentLoaded", () => {
  const video = document.getElementById("player");
  const playPauseBtn = document.getElementById("playPauseBtn");
  const playIcon = document.getElementById("playIcon");
  const pauseIcon = document.getElementById("pauseIcon");
  const rewindBtn = document.getElementById("rewindBtn");
  const forwardBtn = document.getElementById("forwardBtn");
  const subBtn = document.getElementById("subBtn");
  const subPanel = document.getElementById("sub-panel");
  const subToggleBtn = document.getElementById("sub-toggle-btn");
  const subDelayInput = document.getElementById("sub-delay-input");
  const fullscreenBtn = document.getElementById("fullscreenBtn");
  const progressContainer = document.getElementById("progress-container");
  const progressBar = document.getElementById("progress");
  const loadingSpinner = document.getElementById("loadingSpinner");
  const movieName = document.body.dataset.movieName;
  const subBase = document.body.dataset.subBase || "";
  const subtitleData = JSON.parse(document.getElementById("subtitle-data")?.textContent || "[]");

  let autoplayHandled = false;
  let hideTimeout;
  let subsEnabled = false;
  let currentTrackIndex = 0;
  let subDelay = 0;
  let cueOriginals = [];

  const subtitleOnIcon = `<svg viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg" fill="#ffffff"><title>subtitles-solid</title><g><rect width="48" height="48" fill="none"></rect></g><path d="M44,6H4A2,2,0,0,0,2,8V40a2,2,0,0,0,2,2H44a2,2,0,0,0,2-2V8A2,2,0,0,0,44,6ZM12,26h4a2,2,0,0,1,0,4H12a2,2,0,0,1,0-4ZM26,36H12a2,2,0,0,1,0-4H26a2,2,0,0,1,0,4Zm10,0H32a2,2,0,0,1,0-4h4a2,2,0,0,1,0,4Zm0-6H22a2,2,0,0,1,0-4H36a2,2,0,0,1,0,4Z"></path></svg>`;
  const subtitleOffIcon = `<svg viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg" fill="#ffffff"><title>subtitles</title><g><rect width="48" height="48" fill="none"></rect></g><path d="M44,6H4A2,2,0,0,0,2,8V40a2,2,0,0,0,2,2H44a2,2,0,0,0,2-2V8A2,2,0,0,0,44,6ZM42,38H6V10H42Z"></path><path d="M12,36H26a2,2,0,0,0,0-4H12a2,2,0,0,0,0,4Z"></path><path d="M36,32H32a2,2,0,0,0,0,4h4a2,2,0,0,0,0-4Z"></path><path d="M22,30H36a2,2,0,0,0,0-4H22a2,2,0,0,0,0,4Z"></path><path d="M12,30h4a2,2,0,0,0,0-4H12a2,2,0,0,0,0,4Z"></path></svg>`;

  document.getElementById("backBtn").addEventListener("click", () => {
    window.location.href = "/";
  });

  video.addEventListener("waiting", () => { loadingSpinner.style.display = "block"; });
  video.addEventListener("canplay", () => { loadingSpinner.style.display = "none"; });
  video.addEventListener("playing", () => { loadingSpinner.style.display = "none"; });

  const hideUI = () => {
    if (!subPanel.classList.contains("hidden")) return;
    document.getElementById("backBtn").classList.add("hide-ui");
    document.getElementById("controls").classList.add("hide-ui");
  };
  const showUI = () => {
    document.getElementById("backBtn").classList.remove("hide-ui");
    document.getElementById("controls").classList.remove("hide-ui");
  };
  const resetTimer = () => {
    showUI();
    clearTimeout(hideTimeout);
    hideTimeout = setTimeout(hideUI, 2000);
  };
  document.addEventListener("mousemove", resetTimer);
  subPanel.addEventListener("mousemove", resetTimer);
  resetTimer();

  function updatePlayPauseButton() {
    if (video.paused) {
      playIcon.style.display = "block";
      pauseIcon.style.display = "none";
      playPauseBtn.setAttribute("aria-label", "Play video");
    } else {
      playIcon.style.display = "none";
      pauseIcon.style.display = "block";
      playPauseBtn.setAttribute("aria-label", "Pause video");
    }
  }

  playPauseBtn.addEventListener("click", () => {
    if (video.paused) video.play();
    else video.pause();
  });

  rewindBtn.addEventListener("click", () => {
    rewindBtn.disabled = true;
    forwardBtn.disabled = true;
    video.currentTime = Math.max(0, video.currentTime - 10);
    setTimeout(() => { rewindBtn.disabled = false; forwardBtn.disabled = false; }, 300);
  });

  forwardBtn.addEventListener("click", () => {
    rewindBtn.disabled = true;
    forwardBtn.disabled = true;
    video.currentTime = Math.min(video.duration, video.currentTime + 10);
    setTimeout(() => { rewindBtn.disabled = false; forwardBtn.disabled = false; }, 300);
  });

  fullscreenBtn.addEventListener("click", () => {
    if (!document.fullscreenElement) video.requestFullscreen();
    else document.exitFullscreen();
  });

  video.addEventListener("timeupdate", () => {
    const percent = (video.currentTime / video.duration) * 100 || 0;
    progressBar.style.width = `${percent}%`;
    progressContainer.setAttribute("aria-valuenow", percent.toFixed(0));
    progressContainer.setAttribute("aria-valuetext", `${percent.toFixed(0)}% played`);
    updatePlayPauseButton();
  });

  progressContainer.addEventListener("click", (event) => {
    const rect = progressContainer.getBoundingClientRect();
    video.currentTime = ((event.clientX - rect.left) / rect.width) * video.duration;
  });

  progressContainer.addEventListener("keydown", (event) => {
    if (event.key === "ArrowLeft") { video.currentTime = Math.max(0, video.currentTime - 5); event.preventDefault(); }
    else if (event.key === "ArrowRight") { video.currentTime = Math.min(video.duration, video.currentTime + 5); event.preventDefault(); }
  });

  document.getElementById("video-container").addEventListener("click", () => {
    if (!autoplayHandled) {
      video.muted = false;
      video.play();
      autoplayHandled = true;
    } else if (video.paused) {
      video.play();
    } else {
      video.pause();
    }
  });

  fetch(`/progress?movie=${encodeURIComponent(movieName)}`)
    .then((res) => res.json())
    .then((data) => { if (data.time) video.currentTime = data.time; });

  function saveProgress(keepalive = false) {
    return fetch("/progress", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ movie: movieName, time: video.currentTime }),
      keepalive,
    });
  }

  setInterval(saveProgress, 5000);
  window.addEventListener("beforeunload", () => saveProgress(true));

  // ---- Subtitle panel ----

  function getTrackEl() { return document.getElementById("subTrack"); }
  function getTextTrack() { const el = getTrackEl(); return el ? el.track : null; }

  function captureOriginals(textTrack) {
    cueOriginals = [];
    if (!textTrack || !textTrack.cues) return;
    for (const cue of textTrack.cues) {
      cueOriginals.push({ start: cue.startTime, end: cue.endTime });
    }
  }

  function applyDelay(textTrack) {
    if (!textTrack || !textTrack.cues || !cueOriginals.length) return;
    for (let i = 0; i < textTrack.cues.length; i++) {
      if (cueOriginals[i]) {
        textTrack.cues[i].startTime = Math.max(0, cueOriginals[i].start + subDelay);
        textTrack.cues[i].endTime = Math.max(0, cueOriginals[i].end + subDelay);
      }
    }
  }

  function setSubsEnabled(enabled) {
    subsEnabled = enabled;
    const tt = getTextTrack();
    if (tt) tt.mode = enabled ? "showing" : "disabled";
    subToggleBtn.textContent = enabled ? "Subtitles: ON" : "Subtitles: OFF";
    subToggleBtn.classList.toggle("subs-off", !enabled);
    subBtn.innerHTML = enabled ? subtitleOnIcon : subtitleOffIcon;
    subBtn.setAttribute("aria-pressed", String(enabled));
  }

  function updateTrackListUI(activeIndex) {
    document.querySelectorAll(".sub-option").forEach((btn, i) => {
      btn.classList.toggle("active", i === activeIndex);
    });
  }

  function switchSubtitle(index) {
    const sub = subtitleData[index];
    if (!sub) return;
    currentTrackIndex = index;
    cueOriginals = [];

    const existing = getTrackEl();
    if (existing) existing.remove();

    const trackEl = document.createElement("track");
    trackEl.id = "subTrack";
    trackEl.kind = "subtitles";
    trackEl.srclang = "en";
    trackEl.label = sub.label;
    trackEl.src = `${subBase}/${sub.filename}`;

    trackEl.addEventListener("load", () => {
      const tt = trackEl.track;
      tt.mode = "hidden"; // must not be disabled to access cues
      captureOriginals(tt);
      applyDelay(tt);
      tt.mode = subsEnabled ? "showing" : "disabled";
    });

    video.appendChild(trackEl);
    updateTrackListUI(index);
  }

  function buildTrackList() {
    const list = document.getElementById("sub-list");
    if (!subtitleData.length) {
      list.innerHTML = '<p class="sub-none">No subtitles available</p>';
      return;
    }
    list.innerHTML = "";
    subtitleData.forEach((sub, i) => {
      const btn = document.createElement("button");
      btn.className = "sub-option" + (i === currentTrackIndex ? " active" : "");
      btn.textContent = sub.label;
      btn.title = sub.label;
      btn.addEventListener("click", () => switchSubtitle(i));
      list.appendChild(btn);
    });
  }

  // Capture originals from the initial server-rendered track
  const initTrackEl = getTrackEl();
  if (initTrackEl) {
    const onInitLoad = () => {
      const tt = initTrackEl.track;
      const prevMode = tt.mode;
      if (prevMode === "disabled") tt.mode = "hidden";
      captureOriginals(tt);
      tt.mode = prevMode;
    };
    if (initTrackEl.readyState === 2) onInitLoad();
    else initTrackEl.addEventListener("load", onInitLoad);
  }

  // Initialise enabled state from what the browser set on the default track
  const initTT = getTextTrack();
  if (initTT) {
    subsEnabled = initTT.mode === "showing";
  }
  subToggleBtn.textContent = subsEnabled ? "Subtitles: ON" : "Subtitles: OFF";
  subToggleBtn.classList.toggle("subs-off", !subsEnabled);
  subBtn.innerHTML = subsEnabled ? subtitleOnIcon : subtitleOffIcon;

  buildTrackList();

  // Sub button: open/close panel
  subBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    subPanel.classList.toggle("hidden");
    resetTimer();
  });

  // Close panel on outside click
  document.addEventListener("click", (e) => {
    if (!subPanel.classList.contains("hidden") && !subPanel.contains(e.target) && e.target !== subBtn) {
      subPanel.classList.add("hidden");
    }
  });

  subToggleBtn.addEventListener("click", () => setSubsEnabled(!subsEnabled));

  subDelayInput.addEventListener("input", () => {
    subDelay = parseFloat(subDelayInput.value) || 0;
    const tt = getTextTrack();
    if (tt) {
      const prevMode = tt.mode;
      if (prevMode === "disabled") tt.mode = "hidden";
      applyDelay(tt);
      tt.mode = prevMode;
    }
  });

  // Keep panel input from propagating clicks to video
  subPanel.addEventListener("click", (e) => e.stopPropagation());

  updatePlayPauseButton();

  document.addEventListener("keydown", (event) => {
    if (["INPUT", "TEXTAREA"].includes(document.activeElement.tagName)) return;
    switch (event.key.toLowerCase()) {
      case " ":
        event.preventDefault();
        playPauseBtn.click();
        break;
      case "arrowleft":
        rewindBtn.click();
        break;
      case "arrowright":
        forwardBtn.click();
        break;
      case "f":
        fullscreenBtn.click();
        break;
      case "c":
        setSubsEnabled(!subsEnabled);
        break;
    }
  });
});
