document.addEventListener("DOMContentLoaded", () => {
  const loading = document.getElementById("loading");
  const content = document.getElementById("content");

  function esc(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function fmtDuration(seconds) {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    if (h > 0) return `${h}h ${m}m`;
    return `${m}m`;
  }

  function fmtRelTime(isoStr) {
    const diff = (Date.now() - new Date(isoStr).getTime()) / 1000;
    if (diff < 60) return "just now";
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
  }

  function renderOnlineUsers(users) {
    const active = users.filter(u => u.is_active);
    const el = document.getElementById("online-users");
    if (!active.length) {
      el.innerHTML = '<p class="empty-msg">Nobody online right now.</p>';
      return;
    }
    el.innerHTML = `<div class="online-pills">${active.map(u => `
      <div class="online-pill">
        <span class="online-dot"></span>
        <span class="online-name">${esc(u.name)}</span>
        <span class="online-activity">${u.currently_watching ? "watching " + esc(u.currently_watching) : "browsing"}</span>
      </div>
    `).join("")}</div>`;
  }

  function renderUserProgress(progress) {
    if (!progress.length) {
      return '<p class="empty-msg" style="padding-top:8px">No watch history.</p>';
    }
    return `
      <table class="progress-table">
        <thead>
          <tr>
            <th>Movie</th>
            <th>Progress</th>
            <th>Last watched</th>
          </tr>
        </thead>
        <tbody>
          ${progress.map(p => `
            <tr>
              <td>${esc(p.title)}</td>
              <td>
                <div class="mini-bar-wrap">
                  <div class="mini-bar"><div class="mini-bar-fill" style="width:${p.percent}%"></div></div>
                  <span class="prog-label">${p.percent}% · ${fmtDuration(p.seconds)}</span>
                </div>
              </td>
              <td class="last-seen">${fmtRelTime(p.updated_at)}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    `;
  }

  function renderUsers(users) {
    const el = document.getElementById("users-list");
    if (!users.length) {
      el.innerHTML = '<p class="empty-msg">No users yet.</p>';
      return;
    }

    el.innerHTML = users.map((u, i) => `
      <div class="user-row ${u.is_active ? "user-active" : ""}">
        <div class="user-summary">
          <div class="user-identity">
            ${u.is_active ? '<span class="online-dot"></span>' : ""}
            <span class="user-name">${esc(u.name)}</span>
            <span class="user-email">${esc(u.email)}</span>
          </div>
          <div class="user-stats">
            <span>${u.total_hours}h watched</span>
            <span>${u.movies_started} movies</span>
            <span>${u.requests_made} requests</span>
            <span class="last-seen">seen ${fmtRelTime(u.last_seen_at)}</span>
          </div>
          <button class="expand-btn" data-index="${i}" aria-label="Toggle details">▾</button>
        </div>
        <div class="user-detail hidden" id="user-detail-${i}">
          ${renderUserProgress(u.progress)}
        </div>
      </div>
    `).join("");

    el.querySelectorAll(".expand-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        const detail = document.getElementById(`user-detail-${btn.dataset.index}`);
        const nowHidden = detail.classList.toggle("hidden");
        btn.textContent = nowHidden ? "▾" : "▴";
      });
    });
  }

  function renderDownloads(downloads) {
    const el = document.getElementById("downloads-list");
    if (!downloads.length) {
      el.innerHTML = '<p class="empty-msg">No downloads on record.</p>';
      return;
    }

    let rows = "";
    for (const d of downloads) {
      const progressCell = d.status === "downloading"
        ? `${Math.round(d.progress * 100)}%`
        : "—";
      rows += `
        <tr>
          <td>${esc(d.title)}</td>
          <td><span class="status-badge status-${esc(d.status)}">${esc(d.status)}</span></td>
          <td>${progressCell}</td>
          <td>${esc(d.requested_by)}</td>
          <td class="last-seen">${fmtRelTime(d.updated_at)}</td>
        </tr>
        ${d.error_message ? `<tr><td colspan="5" class="error-msg">${esc(d.error_message)}</td></tr>` : ""}
      `;
    }

    el.innerHTML = `
      <table class="downloads-table">
        <thead>
          <tr>
            <th>Title</th>
            <th>Status</th>
            <th>Progress</th>
            <th>Requested by</th>
            <th>Updated</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    `;
  }

  fetch("/admin/data")
    .then(r => {
      if (!r.ok) throw new Error(`${r.status}`);
      return r.json();
    })
    .then(data => {
      loading.classList.add("hidden");
      content.classList.remove("hidden");
      renderOnlineUsers(data.users);
      renderUsers(data.users);
      renderDownloads(data.downloads);
      document.getElementById("refresh-time").textContent =
        `as of ${new Date().toLocaleTimeString()}`;
    })
    .catch(err => {
      loading.textContent = `Failed to load: ${err.message}`;
    });
});
