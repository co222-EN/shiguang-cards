const $ = (selector) => document.querySelector(selector);
const timeline = $("#timeline");
const template = $("#recordTemplate");
const photoInput = $("#photoInput");
const statusText = $("#statusText");
const draftCount = $("#draftCount");
const unlockPanel = $("#unlockPanel");
const captureBand = $("#captureBand");

let records = [];
let pendingPollTimer = null;

const categoryLabels = {
  food: "食物",
  daily: "日常",
  object: "物品",
  place: "地点",
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({ detail: "请求失败" }));
    throw new Error(detail.detail || "请求失败");
  }
  return response.json();
}

async function init() {
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/service-worker.js").catch(() => {});
  }
  bindEvents();
  await refreshDraftCount();
  const session = await api("/api/session").catch(() => ({ passcode_required: false, unlocked: true }));
  if (session.passcode_required && !session.unlocked) {
    unlockPanel.classList.remove("hidden");
    captureBand.classList.add("hidden");
    return;
  }
  await loadRecords();
  syncDrafts();
}

function bindEvents() {
  $("#captureButton").addEventListener("click", () => photoInput.click());
  photoInput.addEventListener("change", onPhotoSelected);
  $("#searchInput").addEventListener("input", debounce(loadRecords, 250));
  $("#categorySelect").addEventListener("change", loadRecords);
  $("#syncButton").addEventListener("click", syncDrafts);
  $("#unlockButton").addEventListener("click", unlock);
  $("#passcodeInput").addEventListener("keydown", (event) => {
    if (event.key === "Enter") unlock();
  });
  $("#cancelEdit").addEventListener("click", () => $("#editDialog").close());
  $("#saveEdit").addEventListener("click", saveEdit);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) loadRecords();
  });
  window.addEventListener("focus", loadRecords);
}

async function unlock() {
  try {
    await api("/api/session", {
      method: "POST",
      body: JSON.stringify({ passcode: $("#passcodeInput").value }),
    });
    unlockPanel.classList.add("hidden");
    captureBand.classList.remove("hidden");
    await loadRecords();
  } catch (error) {
    setStatus(error.message);
  }
}

async function onPhotoSelected(event) {
  const file = event.target.files[0];
  event.target.value = "";
  if (!file) return;
  setStatus("正在把这一刻整理成卡片...");
  const form = new FormData();
  form.append("photo", file);
  try {
    const response = await fetch("/api/records", { method: "POST", body: form, credentials: "same-origin" });
    if (!response.ok) throw new Error(await readError(response));
    const record = await response.json();
    records = [record, ...records.filter((item) => item.id !== record.id)];
    renderRecords(records);
    setStatus(record.ai_status === "ok" ? "已经保存好了。" : "照片已先出现，正在后台识别。你可以继续拍下一张。");
  } catch (error) {
    await saveDraft(file);
    setStatus(`网络不稳，已先存在手机草稿里。${error.message || ""}`);
  }
  await refreshDraftCount();
}

async function loadRecords() {
  const q = $("#searchInput").value.trim();
  const category = $("#categorySelect").value;
  const query = new URLSearchParams();
  if (q) query.set("q", q);
  if (category) query.set("category", category);
  try {
    records = await api(`/api/records?${query.toString()}`);
    renderRecords(records);
    schedulePendingPoll(records);
  } catch (error) {
    setStatus(error.message);
  }
}

function renderRecords(items) {
  timeline.innerHTML = "";
  if (!items.length) {
    timeline.innerHTML = '<p class="empty">还没有记录。先拍一张，让今天留下一个小证据。</p>';
    return;
  }
  for (const item of items) {
    const node = template.content.firstElementChild.cloneNode(true);
    node.style.borderTop = `5px solid ${item.mood_color || "#f3a6a6"}`;
    node.querySelector("img").src = withVersion(item.image_url, item.updated_at);
    node.querySelector("img").alt = item.title;
    node.querySelector("time").textContent = formatDate(item.created_at);
    node.querySelector("h2").textContent = item.title;
    node.querySelector(".category-pill").textContent = categoryLabels[item.category] || item.category || "记录";
    node.querySelector(".caption").textContent = item.caption || "这一刻被好好收起来了。";
    if (isAnalyzing(item)) {
      node.classList.add("is-analyzing");
      node.querySelector(".category-pill").textContent = "识别中";
      node.querySelector(".caption").textContent = item.caption || "照片已保存，AI 正在补上细节。";
    }
    const calories = node.querySelector(".calories");
    if (item.is_food && item.calories_estimate) {
      calories.textContent = `约 ${item.calories_estimate} 千卡 · ${item.portion_guess || "份量由照片估算"} · 仅作生活记录参考`;
      calories.classList.remove("hidden");
    }
    const tags = node.querySelector(".tags");
    for (const tag of item.tags || []) {
      const span = document.createElement("span");
      span.textContent = `#${tag}`;
      span.addEventListener("click", () => {
        $("#searchInput").value = tag;
        loadRecords();
      });
      tags.appendChild(span);
    }
    node.querySelector(".edit").addEventListener("click", () => openEdit(item));
    node.querySelector(".delete").addEventListener("click", () => deleteRecord(item));
    timeline.appendChild(node);
  }
}

function openEdit(item) {
  $("#editId").value = item.id;
  $("#editTitle").value = item.title || "";
  $("#editCaption").value = item.caption || "";
  $("#editTags").value = (item.tags || []).join(", ");
  $("#editNotes").value = item.notes || "";
  $("#editCalories").value = item.calories_estimate || "";
  $("#editPortion").value = item.portion_guess || "";
  $("#editDialog").showModal();
}

async function saveEdit(event) {
  event.preventDefault();
  const id = $("#editId").value;
  const body = {
    title: $("#editTitle").value.trim(),
    caption: $("#editCaption").value.trim(),
    tags: $("#editTags").value.split(",").map((tag) => tag.trim()).filter(Boolean),
    notes: $("#editNotes").value.trim(),
    portion_guess: $("#editPortion").value.trim() || null,
  };
  const calories = $("#editCalories").value.trim();
  body.calories_estimate = calories ? Number(calories) : null;
  try {
    const updated = await api(`/api/records/${id}`, { method: "PATCH", body: JSON.stringify(body) });
    records = records.map((item) => (item.id === id ? updated : item));
    renderRecords(records);
    $("#editDialog").close();
    setStatus("修改已经保存。");
  } catch (error) {
    setStatus(error.message);
  }
}

async function deleteRecord(item) {
  if (!confirm(`删除「${item.title}」吗？`)) return;
  try {
    await api(`/api/records/${item.id}`, { method: "DELETE" });
    records = records.filter((record) => record.id !== item.id);
    renderRecords(records);
    setStatus("记录已删除。");
  } catch (error) {
    setStatus(error.message);
  }
}

function setStatus(text) {
  statusText.textContent = text;
}

function formatDate(value) {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "long",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function withVersion(url, version) {
  if (!url) return "";
  const separator = url.includes("?") ? "&" : "?";
  return `${url}${separator}v=${encodeURIComponent(version || "")}`;
}

async function readError(response) {
  const payload = await response.json().catch(() => null);
  return payload?.detail || "保存失败";
}

function debounce(fn, wait) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), wait);
  };
}

function openDraftDb() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open("shiguang-drafts", 1);
    request.onupgradeneeded = () => request.result.createObjectStore("drafts", { keyPath: "id" });
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function withDraftStore(mode, callback) {
  const db = await openDraftDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("drafts", mode);
    const store = tx.objectStore("drafts");
    const result = callback(store);
    tx.oncomplete = () => resolve(result);
    tx.onerror = () => reject(tx.error);
  });
}

async function saveDraft(file) {
  const draft = { id: crypto.randomUUID(), file, created_at: new Date().toISOString() };
  await withDraftStore("readwrite", (store) => store.put(draft));
}

async function listDrafts() {
  const db = await openDraftDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("drafts", "readonly");
    const request = tx.objectStore("drafts").getAll();
    request.onsuccess = () => resolve(request.result || []);
    request.onerror = () => reject(request.error);
  });
}

async function deleteDraft(id) {
  await withDraftStore("readwrite", (store) => store.delete(id));
}

async function refreshDraftCount() {
  const drafts = await listDrafts().catch(() => []);
  draftCount.textContent = String(drafts.length);
}

async function syncDrafts() {
  const drafts = await listDrafts().catch(() => []);
  if (!drafts.length || !navigator.onLine) {
    await refreshDraftCount();
    return;
  }
  setStatus("正在同步手机里的离线草稿...");
  for (const draft of drafts) {
    const form = new FormData();
    form.append("photo", draft.file, `draft-${draft.id}.jpg`);
    try {
      const response = await fetch("/api/records", { method: "POST", body: form, credentials: "same-origin" });
      if (!response.ok) throw new Error(await readError(response));
      const record = await response.json();
      records = [record, ...records.filter((item) => item.id !== record.id)];
      await deleteDraft(draft.id);
    } catch {
      break;
    }
  }
  renderRecords(records);
  schedulePendingPoll(records);
  await refreshDraftCount();
  setStatus("同步完成。");
}

function isAnalyzing(item) {
  return item.ai_status === "analyzing" || item.ai_status === "pending";
}

function schedulePendingPoll(items = records) {
  if (pendingPollTimer) {
    clearTimeout(pendingPollTimer);
    pendingPollTimer = null;
  }
  if (!items.some(isAnalyzing)) return;
  pendingPollTimer = setTimeout(async () => {
    await loadRecords();
    if (records.some(isAnalyzing)) {
      setStatus("还在识别中，结果好了会自动出现。");
    } else {
      setStatus("识别完成，卡片已经更新。");
    }
  }, 3000);
}

init();
