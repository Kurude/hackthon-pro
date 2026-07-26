// ===================== CONFIG =====================
const API_BASE = window.location.origin; // backend served from same origin
let TOKEN = null;
let CURRENT_USER = null;
let MEDIA_RECORDER = null;
let AUDIO_CHUNKS = [];

// Live meeting state
const LIVE_SEGMENT_MS = 10000; // record in ~10s segments so each chunk is an independently decodable webm file
let liveMeetingId = null;
let liveStream = null;
let liveSegmentRecorder = null;
let liveSegmentChunks = [];
let liveRecordingActive = false;
let liveTimerInterval = null;
let liveStartTime = null;

// ===================== HELPERS =====================
async function api(path, options = {}) {
  const headers = options.headers || {};
  if (TOKEN) headers["Authorization"] = `Bearer ${TOKEN}`;
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!res.ok) {
    let detail = "Something went wrong";
    try {
      const errBody = await res.json();
      detail = errBody.detail || detail;
    } catch (_) {}
    throw new Error(detail);
  }
  const contentType = res.headers.get("content-type") || "";
  return contentType.includes("application/json") ? res.json() : res;
}

function el(id) { return document.getElementById(id); }

// ===================== AUTH TABS =====================
document.querySelectorAll(".auth-tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".auth-tab").forEach((t) => t.classList.remove("active"));
    tab.classList.add("active");
    const target = tab.dataset.tab;
    el("login-form").classList.toggle("hidden", target !== "login");
    el("register-form").classList.toggle("hidden", target !== "register");
  });
});

// ===================== LOGIN =====================
el("login-email").addEventListener("focus", () => window.RobotApp.setMode("attentive", 3));
el("login-password").addEventListener("focus", () => window.RobotApp.setMode("coverEyes", 6));
el("login-password").addEventListener("blur", () => window.RobotApp.setMode("idle", 0.2));

el("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  el("login-error").textContent = "";
  const form = new URLSearchParams();
  form.append("username", el("login-email").value);
  form.append("password", el("login-password").value);
  try {
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: form,
    });
    if (!res.ok) throw new Error((await res.json()).detail || "Login failed");
    const data = await res.json();
    window.RobotApp.setMode("celebrate", 2.2);
    onAuthSuccess(data);
  } catch (err) {
    window.RobotApp.setMode("confused", 1.6);
    el("login-error").textContent = err.message;
  }
});

// ===================== REGISTER =====================
el("register-email").addEventListener("focus", () => window.RobotApp.setMode("attentive", 3));
el("register-password").addEventListener("focus", () => window.RobotApp.setMode("coverEyes", 6));
el("register-password").addEventListener("blur", () => window.RobotApp.setMode("idle", 0.2));

el("register-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  el("register-error").textContent = "";
  try {
    const data = await api("/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: el("register-name").value,
        email: el("register-email").value,
        password: el("register-password").value,
      }),
    });
    window.RobotApp.setMode("thumbsUp", 2);
    onAuthSuccess(data);
  } catch (err) {
    window.RobotApp.setMode("confused", 1.6);
    el("register-error").textContent = err.message;
  }
});

function onAuthSuccess(data) {
  TOKEN = data.access_token;
  CURRENT_USER = data.user;
  sessionStorage.setItem("copilot_token", TOKEN);
  sessionStorage.setItem("copilot_user", JSON.stringify(CURRENT_USER));
  showApp();
}

el("logout-btn").addEventListener("click", () => {
  TOKEN = null;
  CURRENT_USER = null;
  sessionStorage.clear();
  el("app").classList.add("hidden");
  el("auth-screen").classList.remove("hidden");
});

function showApp() {
  el("auth-screen").classList.add("hidden");
  el("app").classList.remove("hidden");
  el("user-name").textContent = CURRENT_USER.name;
  el("user-email").textContent = CURRENT_USER.email;
  el("user-avatar").textContent = CURRENT_USER.name.charAt(0).toUpperCase();
  loadDocuments();
  loadMeetings();
  loadTasks();
  loadHistory();
}

// Try restoring session
(function restoreSession() {
  const savedToken = sessionStorage.getItem("copilot_token");
  const savedUser = sessionStorage.getItem("copilot_user");
  if (savedToken && savedUser) {
    TOKEN = savedToken;
    CURRENT_USER = JSON.parse(savedUser);
    showApp();
  }
})();

// ===================== NAVIGATION =====================
document.querySelectorAll(".nav-item").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".nav-item").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
    btn.classList.add("active");
    el(`view-${btn.dataset.view}`).classList.add("active");
  });
});

// ===================== CHAT =====================
function appendMessage(container, role, content, sources = []) {
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  div.textContent = content;
  if (sources.length) {
    const src = document.createElement("span");
    src.className = "sources";
    src.textContent = `Sources: ${sources.join(", ")}`;
    div.appendChild(src);
  }
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
  return div;
}

el("chat-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const input = el("chat-input");
  const message = input.value.trim();
  if (!message) return;
  const chatWindow = el("chat-window");
  appendMessage(chatWindow, "user", message);
  input.value = "";
  const thinking = appendMessage(chatWindow, "assistant", "Thinking...");
  try {
    const data = await api("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });
    thinking.textContent = data.reply;
    if (data.sources && data.sources.length) {
      const src = document.createElement("span");
      src.className = "sources";
      src.textContent = `Sources: ${data.sources.join(", ")}`;
      thinking.appendChild(src);
    }
  } catch (err) {
    thinking.textContent = `Error: ${err.message}`;
  }
});

async function loadHistory() {
  try {
    const history = await api("/chat/history");
    const container = el("history-list");
    container.innerHTML = "";
    history.forEach((h) => appendMessage(container, h.role, h.content));
  } catch (err) {
    console.error(err);
  }
}

// ===================== VOICE ASSISTANT =====================
el("record-btn").addEventListener("click", async () => {
  const btn = el("record-btn");
  if (!MEDIA_RECORDER || MEDIA_RECORDER.state === "inactive") {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      MEDIA_RECORDER = new MediaRecorder(stream);
      AUDIO_CHUNKS = [];
      MEDIA_RECORDER.ondataavailable = (e) => AUDIO_CHUNKS.push(e.data);
      MEDIA_RECORDER.onstop = handleVoiceStop;
      MEDIA_RECORDER.start();
      btn.classList.add("recording");
      el("record-status").textContent = "Recording... tap again to stop";
    } catch (err) {
      el("record-status").textContent = "Microphone access denied";
    }
  } else {
    MEDIA_RECORDER.stop();
    btn.classList.remove("recording");
    el("record-status").textContent = "Processing your question...";
  }
});

async function handleVoiceStop() {
  const blob = new Blob(AUDIO_CHUNKS, { type: "audio/webm" });
  const formData = new FormData();
  formData.append("file", blob, "question.webm");
  try {
    const data = await api("/voice/chat", { method: "POST", body: formData });
    el("voice-result").classList.remove("hidden");
    el("voice-transcript").textContent = data.transcript;
    el("voice-reply").textContent = data.reply;
    el("voice-audio").src = `${API_BASE}${data.audio_url}`;
    el("voice-audio").play();
    el("record-status").textContent = "Tap to record another question";
  } catch (err) {
    el("record-status").textContent = `Error: ${err.message}`;
  }
}

// ===================== DOCUMENTS =====================
el("doc-upload-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fileInput = el("doc-file");
  if (!fileInput.files.length) return;
  const formData = new FormData();
  formData.append("file", fileInput.files[0]);
  el("doc-upload-status").textContent = "Uploading & ingesting into knowledge base...";
  try {
    await api("/documents/upload", { method: "POST", body: formData });
    el("doc-upload-status").textContent = "Document ingested successfully!";
    fileInput.value = "";
    loadDocuments();
  } catch (err) {
    el("doc-upload-status").textContent = `Error: ${err.message}`;
  }
});

async function loadDocuments() {
  try {
    const docs = await api("/documents");
    const tbody = document.querySelector("#documents-table tbody");
    tbody.innerHTML = "";
    docs.forEach((d) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${d.filename}</td><td>${d.doc_type}</td><td>${d.char_count}</td><td>${new Date(d.uploaded_at).toLocaleString()}</td>`;
      tbody.appendChild(tr);
    });
  } catch (err) {
    console.error(err);
  }
}

// ===================== MEETINGS =====================
el("meeting-upload-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fileInput = el("meeting-file");
  if (!fileInput.files.length) return;
  const formData = new FormData();
  formData.append("file", fileInput.files[0]);
  const title = encodeURIComponent(el("meeting-title").value || "Untitled Meeting");
  el("meeting-upload-status").textContent = "Transcribing & analyzing meeting... this may take a moment";
  try {
    await api(`/meetings/upload-notes?title=${title}`, { method: "POST", body: formData });
    el("meeting-upload-status").textContent = "Meeting analyzed successfully!";
    el("meeting-title").value = "";
    fileInput.value = "";
    loadMeetings();
    loadTasks();
  } catch (err) {
    el("meeting-upload-status").textContent = `Error: ${err.message}`;
  }
});

async function loadMeetings() {
  try {
    const meetings = await api("/meetings");
    const container = el("meetings-list");
    container.innerHTML = "";
    meetings.forEach((m) => {
      const card = document.createElement("div");
      card.className = "meeting-card";
      const badge = m.source === "live" ? "Live Capture" : "Uploaded Recording";
      card.innerHTML = `
        <h3>${m.title}</h3>
        <div class="meta">${badge} · ${new Date(m.created_at).toLocaleString()}</div>
        <div class="summary">${m.summary}</div>
        <div class="actions">
          <button class="btn-ghost" data-email="${m.id}">Draft Follow-up Email</button>
        </div>
      `;
      container.appendChild(card);
    });
    container.querySelectorAll("[data-email]").forEach((btn) => {
      btn.addEventListener("click", () => generateEmail(btn.dataset.email));
    });
  } catch (err) {
    console.error(err);
  }
}

async function generateEmail(meetingId) {
  try {
    const data = await api("/meetings/generate-email", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ meeting_id: parseInt(meetingId), tone: "professional" }),
    });
    el("email-subject").value = data.subject;
    el("email-body").value = data.body;
    el("email-modal").classList.remove("hidden");
  } catch (err) {
    alert(`Error generating email: ${err.message}`);
  }
}

el("email-close").addEventListener("click", () => el("email-modal").classList.add("hidden"));
el("email-copy").addEventListener("click", () => {
  const text = `Subject: ${el("email-subject").value}\n\n${el("email-body").value}`;
  navigator.clipboard.writeText(text);
  el("email-copy").textContent = "Copied!";
  setTimeout(() => (el("email-copy").textContent = "Copy to Clipboard"), 1500);
});

// ===================== TASKS =====================
async function loadTasks() {
  try {
    const tasks = await api("/tasks");
    const container = el("tasks-list");
    container.innerHTML = "";
    if (!tasks.length) {
      container.innerHTML = `<p style="color:var(--text-dim);font-size:14px;">No tasks yet — upload a meeting to auto-extract action items.</p>`;
      return;
    }
    tasks.forEach((t) => {
      const row = document.createElement("div");
      row.className = `task-row ${t.status === "done" ? "done" : ""}`;
      row.innerHTML = `
        <input type="checkbox" ${t.status === "done" ? "checked" : ""} data-task="${t.id}" />
        <span class="task-desc">${t.description}</span>
        <span class="task-assignee">${t.assignee}</span>
      `;
      container.appendChild(row);
    });
    container.querySelectorAll("[data-task]").forEach((cb) => {
      cb.addEventListener("change", async () => {
        const status = cb.checked ? "done" : "pending";
        await api(`/tasks/${cb.dataset.task}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ status }),
        });
        loadTasks();
      });
    });
  } catch (err) {
    console.error(err);
  }
}

// ===================== LIVE BUSINESS MEETING =====================
// Records the mic in short ~10s segments so each segment is an independently
// decodable webm file. Every segment is uploaded and transcribed as soon as
// it's captured, so the transcript builds up live while the meeting runs.
// Ending the meeting triggers the same summarize + extract-action-items
// pipeline used for uploaded recordings.

el("live-start-btn").addEventListener("click", async () => {
  const title = el("live-meeting-title").value.trim() || "Untitled Meeting";
  try {
    const meeting = await api("/meetings/live/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    });
    liveMeetingId = meeting.id;

    liveStream = await navigator.mediaDevices.getUserMedia({ audio: true });

    liveRecordingActive = true;
    el("live-start-row").classList.add("hidden");
    el("live-active").classList.remove("hidden");
    el("live-indicator").classList.remove("hidden");
    el("live-transcript").innerHTML = `<p class="live-placeholder">Listening… speak naturally, the transcript will appear here as the meeting proceeds.</p>`;
    el("live-status-msg").textContent = "";

    liveStartTime = Date.now();
    liveTimerInterval = setInterval(updateLiveTimer, 1000);

    recordLiveSegment();
  } catch (err) {
    alert(`Could not start the live meeting: ${err.message}`);
  }
});

function updateLiveTimer() {
  const elapsed = Math.floor((Date.now() - liveStartTime) / 1000);
  const mm = String(Math.floor(elapsed / 60)).padStart(2, "0");
  const ss = String(elapsed % 60).padStart(2, "0");
  el("live-timer").textContent = `${mm}:${ss}`;
}

function recordLiveSegment() {
  if (!liveRecordingActive || !liveStream) return;

  liveSegmentChunks = [];
  liveSegmentRecorder = new MediaRecorder(liveStream);
  liveSegmentRecorder.ondataavailable = (e) => liveSegmentChunks.push(e.data);
  liveSegmentRecorder.onstop = async () => {
    const blob = new Blob(liveSegmentChunks, { type: "audio/webm" });
    // upload in the background; keep recording the next segment regardless
    uploadLiveSegment(blob);
    if (liveRecordingActive) recordLiveSegment();
  };
  liveSegmentRecorder.start();
  setTimeout(() => {
    if (liveSegmentRecorder && liveSegmentRecorder.state !== "inactive") {
      liveSegmentRecorder.stop();
    }
  }, LIVE_SEGMENT_MS);
}

async function uploadLiveSegment(blob) {
  if (blob.size < 500) return; // skip near-empty segments (silence)
  const formData = new FormData();
  formData.append("file", blob, "segment.webm");
  try {
    const data = await api(`/meetings/live/${liveMeetingId}/chunk`, { method: "POST", body: formData });
    if (data.chunk_transcript) {
      const container = el("live-transcript");
      const placeholder = container.querySelector(".live-placeholder");
      if (placeholder) placeholder.remove();
      const p = document.createElement("p");
      p.textContent = data.chunk_transcript;
      container.appendChild(p);
      container.scrollTop = container.scrollHeight;
    }
  } catch (err) {
    el("live-status-msg").textContent = `Segment upload issue: ${err.message}`;
  }
}

el("live-end-btn").addEventListener("click", async () => {
  if (!liveMeetingId) return;
  el("live-status-msg").textContent = "Finalizing transcript…";
  liveRecordingActive = false;
  clearInterval(liveTimerInterval);

  if (liveSegmentRecorder && liveSegmentRecorder.state !== "inactive") {
    liveSegmentRecorder.stop(); // uploads the final in-progress segment
  }
  if (liveStream) {
    liveStream.getTracks().forEach((t) => t.stop());
  }

  // give the final segment a moment to finish uploading before ending
  await new Promise((resolve) => setTimeout(resolve, 1200));

  el("live-status-msg").textContent = "Generating summary & action items…";
  try {
    await api(`/meetings/live/${liveMeetingId}/end`, { method: "POST" });
    el("live-status-msg").textContent = "";
    resetLiveMeetingUI();
    loadMeetings();
    loadTasks();
  } catch (err) {
    el("live-status-msg").textContent = `Error finalizing meeting: ${err.message}`;
  }
});

function resetLiveMeetingUI() {
  liveMeetingId = null;
  el("live-meeting-title").value = "";
  el("live-start-row").classList.remove("hidden");
  el("live-active").classList.add("hidden");
  el("live-indicator").classList.add("hidden");
  el("live-timer").textContent = "00:00";
}
