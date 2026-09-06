const state = {
  settings: null,
  scannedPaths: [],
  results: [],
  browseTarget: null,
  browserCurrent: "",
  viewMode: "grid",
  folderRows: [],
  currentPage: 1,
  pageSize: 20,
  logs: [],
  watcherLogCount: 0,
  watcherLogKey: "",
  jobLogKeys: {},
  activeJobId: null,
  classifyRunning: false,
  moveRunning: false,
  undoRunning: false,
};

const sourceDirInput = document.querySelector("#sourceDirInput");
const acgOutputDirInput = document.querySelector("#acgOutputDirInput");
const nonAcgOutputDirInput = document.querySelector("#nonAcgOutputDirInput");
const browseSourceButton = document.querySelector("#browseSourceButton");
const browseAcgOutputButton = document.querySelector("#browseAcgOutputButton");
const browseNonAcgOutputButton = document.querySelector("#browseNonAcgOutputButton");
const modelSelect = document.querySelector("#modelSelect");
const threadCountInput = document.querySelector("#threadCountInput");
const pathLayersInput = document.querySelector("#pathLayersInput");
const watchIntervalInput = document.querySelector("#watchIntervalInput");
const moveModeSelect = document.querySelector("#moveModeSelect");
const recursiveInput = document.querySelector("#recursiveInput");
const autoMoveInput = document.querySelector("#autoMoveInput");
const watchAutoMoveInput = document.querySelector("#watchAutoMoveInput");
const watchInitialModeSelect = document.querySelector("#watchInitialModeSelect");
const saveSettingsButton = document.querySelector("#saveSettingsButton");
const scanButton = document.querySelector("#scanButton");
const classifyFolderButton = document.querySelector("#classifyFolderButton");
const moveBatchButton = document.querySelector("#moveBatchButton");
const undoMoveButton = document.querySelector("#undoMoveButton");
const scanSummary = document.querySelector("#scanSummary");
const folderResultBody = document.querySelector("#folderResultBody");
const folderResultGrid = document.querySelector("#folderResultGrid");
const resultTableWrap = document.querySelector("#resultTableWrap");
const gridViewButton = document.querySelector("#gridViewButton");
const listViewButton = document.querySelector("#listViewButton");
const pageInfo = document.querySelector("#pageInfo");
const pageSizeInput = document.querySelector("#pageSizeInput");
const prevPageButton = document.querySelector("#prevPageButton");
const nextPageButton = document.querySelector("#nextPageButton");
const taskProgress = document.querySelector("#taskProgress");
const taskMessage = document.querySelector("#taskMessage");
const taskPercent = document.querySelector("#taskPercent");
const taskProgressFill = document.querySelector("#taskProgressFill");
const logList = document.querySelector("#logList");
const clearLogsButton = document.querySelector("#clearLogsButton");
const pauseJobButton = document.querySelector("#pauseJobButton");
const resumeJobButton = document.querySelector("#resumeJobButton");
const cancelJobButton = document.querySelector("#cancelJobButton");
const watcherState = document.querySelector("#watcherState");
const watcherProcessed = document.querySelector("#watcherProcessed");
const watcherLastScan = document.querySelector("#watcherLastScan");
const watcherScanned = document.querySelector("#watcherScanned");
const watcherPending = document.querySelector("#watcherPending");
const watcherCurrentFile = document.querySelector("#watcherCurrentFile");
const watcherMode = document.querySelector("#watcherMode");
const watcherMessage = document.querySelector("#watcherMessage");
const watcherProgressText = document.querySelector("#watcherProgressText");
const watcherProgressFill = document.querySelector("#watcherProgressFill");
const startWatcherButton = document.querySelector("#startWatcherButton");
const stopWatcherButton = document.querySelector("#stopWatcherButton");
const browseModal = document.querySelector("#browseModal");
const browserPathInput = document.querySelector("#browserPathInput");
const browserGoButton = document.querySelector("#browserGoButton");
const browserList = document.querySelector("#browserList");
const closeBrowseButton = document.querySelector("#closeBrowseButton");
const cancelBrowseButton = document.querySelector("#cancelBrowseButton");
const confirmBrowseButton = document.querySelector("#confirmBrowseButton");

async function api(url, options = {}) {
  const response = await fetch(url, options);
  let payload;
  try {
    payload = await response.json();
  } catch {
    payload = {};
  }
  if (!response.ok) {
    throw new Error(payload.error || "请求失败");
  }
  return payload;
}

function appendLogs(logs) {
  if (!logs || !logs.length) {
    return;
  }
  state.logs.push(...logs);
  state.logs = state.logs.slice(-200);
  renderLogs();
}

function renderLogs() {
  logList.innerHTML = "";
  if (!state.logs.length) {
    const empty = document.createElement("div");
    empty.className = "log-entry";
    empty.textContent = "暂无运行日志。";
    logList.appendChild(empty);
    return;
  }
  state.logs.forEach((entry) => {
    const item = document.createElement("div");
    item.className = "log-entry";
    const time = document.createElement("span");
    time.className = "log-entry-time";
    time.textContent = new Date((entry.time || Date.now() / 1000) * 1000).toLocaleTimeString();
    const message = document.createElement("span");
    message.textContent = entry.message;
    item.append(time, message);
    logList.appendChild(item);
  });
  logList.scrollTop = logList.scrollHeight;
}

function appendJobLogs(job) {
  if (!job || !job.id) {
    return;
  }
  const logs = job.logs || [];
  const previousKey = state.jobLogKeys[job.id];
  let newLogs = logs;
  if (previousKey) {
    const previousIndex = logs.findIndex((entry) => logKey(entry) === previousKey);
    newLogs = previousIndex >= 0 ? logs.slice(previousIndex + 1) : logs;
  }
  appendLogs(newLogs);
  if (logs.length) {
    state.jobLogKeys[job.id] = logKey(logs[logs.length - 1]);
  }
}

function logKey(entry) {
  return `${entry.time || ""}:${entry.message || ""}`;
}

function showProgress(progress, total, message) {
  taskProgress.hidden = false;
  taskMessage.textContent = message || "处理中...";
  const percent = total ? Math.min(100, Math.round((progress / total) * 100)) : 0;
  taskPercent.textContent = `${percent}%`;
  taskProgressFill.style.width = `${percent}%`;
}

function setJobControls(active, paused = false) {
  pauseJobButton.disabled = !active || paused;
  resumeJobButton.disabled = !active || !paused;
  cancelJobButton.disabled = !active;
}

function hideProgress() {
  taskProgress.hidden = true;
  taskProgressFill.style.width = "0";
  taskPercent.textContent = "0%";
  setJobControls(false);
}

async function pollJob(jobId, onDone) {
  state.activeJobId = jobId;
  setJobControls(true);
  while (true) {
    const payload = await api(`/api/jobs/${encodeURIComponent(jobId)}?summary=1`);
    const job = payload.job;
    appendJobLogs(job);
    showProgress(job.progress || 0, job.total || 0, job.message || "处理中...");
    setJobControls(true, job.status === "paused");
    if (job.status === "done") {
      const finalPayload = await api(`/api/jobs/${encodeURIComponent(jobId)}`);
      const finalJob = finalPayload.job;
      if (onDone) {
        onDone(finalJob);
      }
      setJobControls(false);
      return finalJob;
    }
    if (job.status === "cancelled" || job.status === "interrupted") {
      const finalPayload = await api(`/api/jobs/${encodeURIComponent(jobId)}`);
      const finalJob = finalPayload.job;
      if (onDone) {
        onDone(finalJob);
      }
      setJobControls(false);
      return finalJob;
    }
    if (job.status === "error") {
      setJobControls(false);
      throw new Error(job.error || job.message || "任务失败");
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
}

function currentSettings() {
  const watchStartMode = watchInitialModeSelect ? watchInitialModeSelect.value : "unprocessed";
  return {
    source_dir: sourceDirInput.value.trim(),
    output_dir_acg: acgOutputDirInput.value.trim(),
    output_dir_non_acg: nonAcgOutputDirInput.value.trim(),
    model: modelSelect.value,
    thread_count: Math.max(1, Math.min(32, Number(threadCountInput.value) || 2)),
    path_layers: Math.max(0, Number(pathLayersInput.value) || 0),
    watch_interval: Math.max(1, Math.min(60, Number(watchIntervalInput.value) || 3)),
    move_mode: moveModeSelect ? moveModeSelect.value : "move",
    recursive: recursiveInput.checked,
    auto_move: autoMoveInput.checked,
    auto_move_watch: watchAutoMoveInput.checked,
    watch_start_mode: watchStartMode,
    watch_existing_files: watchStartMode !== "new",
  };
}

function populateSettings(settings) {
  sourceDirInput.value = settings.source_dir || "";
  acgOutputDirInput.value = settings.output_dir_acg || "";
  nonAcgOutputDirInput.value = settings.output_dir_non_acg || "";
  modelSelect.value = settings.model || "v1s";
  threadCountInput.value = settings.thread_count || 2;
  pathLayersInput.value = settings.path_layers || 0;
  watchIntervalInput.value = settings.watch_interval || 3;
  if (moveModeSelect) {
    moveModeSelect.value = settings.move_mode || "move";
  }
  recursiveInput.checked = settings.recursive !== false;
  autoMoveInput.checked = settings.auto_move !== false;
  watchAutoMoveInput.checked = settings.auto_move_watch !== false;
  if (watchInitialModeSelect) {
    const watchStartMode = settings.watch_start_mode || (settings.watch_existing_files === false ? "new" : "unprocessed");
    watchInitialModeSelect.value = ["new", "unprocessed", "all"].includes(watchStartMode)
      ? watchStartMode
      : "unprocessed";
  }
}

function setButtonLoading(button, loading, text) {
  if (loading) {
    button.dataset.originalText = button.textContent;
    button.textContent = text || "处理中...";
    button.disabled = true;
  } else {
    button.textContent = button.dataset.originalText || button.textContent;
    button.disabled = false;
  }
}

async function loadSettings() {
  const settings = await api("/api/settings");
  state.settings = settings;
  populateSettings(settings);
  updateWatcherUI();
}

async function saveSettings(extra = {}) {
  const payload = { ...currentSettings(), ...extra };
  const response = await api("/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  state.settings = response.settings;
  populateSettings(response.settings);
  updateWatcherUI();
}

async function openBrowser(target) {
  state.browseTarget = target;
  const currentPath =
    target === "source"
      ? sourceDirInput.value
      : target === "acg-output"
        ? acgOutputDirInput.value
        : nonAcgOutputDirInput.value;
  state.browserCurrent = currentPath;
  await loadBrowser(currentPath);
  browseModal.hidden = false;
}

function closeBrowser() {
  browseModal.hidden = true;
  state.browseTarget = null;
}

async function loadBrowser(path) {
  let data;
  try {
    data = await api(`/api/fs/browse?path=${encodeURIComponent(path || "")}`);
  } catch {
    data = await api(`/api/fs/browse?path=${encodeURIComponent("")}`);
  }
  state.browserCurrent = data.current || "";
  browserPathInput.value = data.current || "";
  renderBrowser(data);
}

function renderBrowser(data) {
  browserList.innerHTML = "";

  if (data.parent && data.parent !== data.current) {
    browserList.appendChild(createBrowserItem("..", data.parent, "dir", "up-item"));
  }

  data.entries.forEach((entry) => {
    browserList.appendChild(
      createBrowserItem(entry.name, entry.path, entry.type, entry.type === "dir" ? "" : "file-item"),
    );
  });
}

function createBrowserItem(name, path, type, extraClass = "") {
  const button = document.createElement("button");
  button.type = "button";
  button.className = `browser-item ${extraClass}`.trim();
  const visual = document.createElement("span");
  visual.className = "browser-visual";
  if (type === "dir") {
    const mark = document.createElement("span");
    mark.className = "browser-mark";
    mark.textContent = "▸";
    visual.appendChild(mark);
  } else {
    const image = document.createElement("img");
    image.className = "browser-thumb";
    image.alt = name;
    image.src = `/api/fs/thumbnail?path=${encodeURIComponent(path)}&size=64`;
    visual.appendChild(image);
  }
  const label = document.createElement("span");
  label.textContent = name;
  button.append(visual, label);

  if (type === "dir") {
    button.addEventListener("click", () => loadBrowser(path));
  } else {
    button.addEventListener("click", () => {
      window.open(`/api/fs/preview?path=${encodeURIComponent(path)}`, "_blank", "noopener");
    });
  }
  return button;
}

function confirmBrowserSelection() {
  if (!state.browseTarget) {
    return;
  }
  if (state.browseTarget === "source") {
    sourceDirInput.value = state.browserCurrent;
  } else if (state.browseTarget === "acg-output") {
    acgOutputDirInput.value = state.browserCurrent;
  } else {
    nonAcgOutputDirInput.value = state.browserCurrent;
  }
  closeBrowser();
}

function renderFolderRows(rows) {
  folderResultBody.innerHTML = "";
  if (!rows.length) {
    const row = document.createElement("tr");
    row.className = "empty-table-row";
    const cell = document.createElement("td");
    cell.colSpan = 6;
    cell.textContent = "暂无图片。";
    row.appendChild(cell);
    folderResultBody.appendChild(row);
    return;
  }

  rows.forEach((rowData) => {
    const row = document.createElement("tr");
    const previewCell = document.createElement("td");
    const preview = document.createElement("img");
    preview.className = "result-thumb";
    preview.alt = rowData.filename || "图片预览";
    preview.src = `/api/fs/thumbnail?path=${encodeURIComponent(getPreviewPath(rowData))}&size=72`;
    previewCell.appendChild(preview);

    const nameCell = document.createElement("td");
    nameCell.textContent = rowData.filename || "未知文件";

    const pathCell = document.createElement("td");
    pathCell.className = "path-cell";
    pathCell.textContent = rowData.path || "";
    pathCell.title = rowData.path || "";

    const resultCell = document.createElement("td");
    const resultPill = document.createElement("span");
    resultPill.className = "result-pill";
    if (rowData.error) {
      resultPill.classList.add("error");
      resultPill.textContent = rowData.error;
    } else if (rowData.is_acg) {
      resultPill.classList.add("acg");
      resultPill.textContent = "ACG";
    } else {
      resultPill.classList.add("non-acg");
      resultPill.textContent = "非 ACG";
    }
    resultCell.appendChild(resultPill);

    const confidenceCell = document.createElement("td");
    confidenceCell.textContent = rowData.error
      ? ""
      : `${(rowData.confidence * 100).toFixed(2)}%`;

    const moveCell = document.createElement("td");
    moveCell.className = "path-cell";
    moveCell.title = "";
    if (rowData.undo && rowData.undo.undone) {
      moveCell.textContent = `已撤销 · ${rowData.undo.destination || ""}`;
      moveCell.title = rowData.undo.destination || "";
    } else if (rowData.move && rowData.move.moved) {
      moveCell.textContent = `已移动 · ${rowData.move.destination}`;
      moveCell.title = rowData.move.destination;
    } else if (rowData.move && rowData.move.reason === "exists") {
      moveCell.textContent = "目标已存在，跳过";
    } else if (rowData.move && rowData.move.error) {
      moveCell.textContent = `处理失败 · ${rowData.move.error}`;
      moveCell.title = rowData.move.error;
    } else if (rowData.error) {
      moveCell.textContent = "未处理";
    } else {
      moveCell.textContent = "待移动";
    }

    row.append(previewCell, nameCell, pathCell, resultCell, confidenceCell, moveCell);
    folderResultBody.appendChild(row);
  });
}

function getFolderMoveLabel(rowData) {
  if (rowData.undo && rowData.undo.undone) {
    return {
      text: "已撤销",
      detail: rowData.undo.destination || "",
      tone: "muted",
    };
  }
  if (rowData.move && rowData.move.moved) {
    return {
      text: "已处理",
      detail: rowData.move.destination || "",
      tone: "success",
    };
  }
  if (rowData.move && rowData.move.reason === "exists") {
    return { text: "目标已存在", detail: "", tone: "muted" };
  }
  if (rowData.move && rowData.move.error) {
    return { text: "处理失败", detail: rowData.move.error, tone: "error" };
  }
  if (rowData.error) {
    return { text: "未处理", detail: "", tone: "muted" };
  }
  return { text: "待处理", detail: "", tone: "muted" };
}

function renderFolderGrid(rows) {
  folderResultGrid.innerHTML = "";
  if (!rows.length) {
    const empty = document.createElement("div");
    empty.className = "folder-grid-empty";
    empty.textContent = "暂无图片。";
    folderResultGrid.appendChild(empty);
    return;
  }

  rows.forEach((rowData) => {
    const card = document.createElement("article");
    card.className = "folder-result-card";
    card.title = rowData.path || "";

    const imageWrap = document.createElement("div");
    imageWrap.className = "folder-result-image";
    const image = document.createElement("img");
    image.alt = rowData.filename || "图片预览";
    image.loading = "lazy";
    image.src = `/api/fs/thumbnail?path=${encodeURIComponent(getPreviewPath(rowData))}&size=360`;
    imageWrap.appendChild(image);

    const body = document.createElement("div");
    body.className = "folder-result-body";

    const topLine = document.createElement("div");
    topLine.className = "folder-result-topline";
    const name = document.createElement("span");
    name.className = "folder-result-name";
    name.textContent = rowData.filename || "未知文件";

    const result = document.createElement("span");
    result.className = "result-pill";
    if (rowData.error) {
      result.classList.add("error");
      result.textContent = "无法识别";
    } else if (rowData.is_acg) {
      result.classList.add("acg");
      result.textContent = "ACG";
    } else {
      result.classList.add("non-acg");
      result.textContent = "非 ACG";
    }
    topLine.append(name, result);

    const meta = document.createElement("div");
    meta.className = "folder-result-meta";
    if (!rowData.error && typeof rowData.confidence === "number") {
      meta.textContent = `${(rowData.confidence * 100).toFixed(2)}%`;
    }

    const move = getFolderMoveLabel(rowData);
    const status = document.createElement("div");
    status.className = `folder-result-status ${move.tone}`;
    status.textContent = move.text;
    status.title = move.detail || "";

    body.append(topLine, meta, status);
    card.append(imageWrap, body);
    folderResultGrid.appendChild(card);
  });
}

function renderFolderResults(rows) {
  state.folderRows = rows || [];
  state.currentPage = 1;
  renderCurrentPage();
}

function getPreviewPath(rowData) {
  if (rowData.undo && rowData.undo.undone) {
    return rowData.path || "";
  }
  if (rowData.move && rowData.move.moved && rowData.move.destination) {
    return rowData.move.destination;
  }
  return rowData.path || "";
}

function updateBatchActionState() {
  const hasPending = state.results.some(
    (result) =>
      !result.error &&
      (!(result.move && result.move.moved) || (result.undo && result.undo.undone)),
  );
  const hasUndoable = state.results.some(
    (result) => result.move && result.move.moved && !(result.undo && result.undo.undone),
  );
  moveBatchButton.disabled = state.classifyRunning || state.moveRunning || !hasPending;
  undoMoveButton.disabled =
    state.classifyRunning || state.moveRunning || state.undoRunning || !hasUndoable;
}

function renderCurrentPage() {
  const total = state.folderRows.length;
  const totalPages = Math.max(1, Math.ceil(total / state.pageSize));
  if (state.currentPage > totalPages) {
    state.currentPage = totalPages;
  }
  const start = (state.currentPage - 1) * state.pageSize;
  const pageRows = state.folderRows.slice(start, start + state.pageSize);

  renderFolderRows(pageRows);
  renderFolderGrid(pageRows);
  updateViewMode();

  pageInfo.textContent = total
    ? `第 ${state.currentPage} / ${totalPages} 页 · 共 ${total} 张`
    : "暂无图片";
  prevPageButton.disabled = state.currentPage <= 1;
  nextPageButton.disabled = state.currentPage >= totalPages || total === 0;
}

function updateViewMode() {
  const grid = state.viewMode === "grid";
  folderResultGrid.hidden = !grid;
  resultTableWrap.hidden = grid;
  gridViewButton.classList.toggle("active", grid);
  listViewButton.classList.toggle("active", !grid);
}

async function scanFolder() {
  const settings = currentSettings();
  if (!settings.source_dir) {
    alert("请先选择源文件夹");
    return;
  }

  setButtonLoading(scanButton, true, "扫描中...");
  try {
    const startResponse = await api(
      `/api/folder/scan-job?path=${encodeURIComponent(settings.source_dir)}&recursive=${settings.recursive}&output_dir_acg=${encodeURIComponent(settings.output_dir_acg)}&output_dir_non_acg=${encodeURIComponent(settings.output_dir_non_acg)}`,
    );
    await pollJob(startResponse.job_id, (job) => {
      state.scannedPaths = (job.result && job.result.paths) || [];
      state.results = [];
      scanSummary.textContent = `${state.scannedPaths.length} 张图片`;
      classifyFolderButton.disabled = state.scannedPaths.length === 0;
      updateBatchActionState();
      renderFolderResults(
        state.scannedPaths.map((path) => ({
          path,
          filename: path.split(/[\\/]/).pop(),
        })),
      );
    });
  } catch (error) {
    alert(error.message || "扫描失败");
  } finally {
    setButtonLoading(scanButton, false);
    hideProgress();
  }
}

async function classifyFolder() {
  const settings = currentSettings();
  if (!settings.source_dir) {
    alert("请先选择源文件夹");
    return;
  }
  if (!state.scannedPaths.length) {
    await scanFolder();
    if (!state.scannedPaths.length) {
      return;
    }
  }

  state.classifyRunning = true;
  updateBatchActionState();
  setButtonLoading(classifyFolderButton, true, "识别中...");
  try {
    const startResponse = await api("/api/folder/classify-job", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...settings,
        paths: state.scannedPaths,
      }),
    });
    await pollJob(startResponse.job_id, (job) => {
      state.results = (job.result && job.result.results) || [];
      renderFolderResults(state.results);
      scanSummary.textContent = `${state.results.length} 张已识别`;
      updateBatchActionState();
    });
  } catch (error) {
    alert(error.message || "批量识别失败");
  } finally {
    setButtonLoading(classifyFolderButton, false);
    state.classifyRunning = false;
    updateBatchActionState();
    hideProgress();
  }
}

async function moveCurrentResults() {
  const settings = currentSettings();
  if (!settings.output_dir_acg || !settings.output_dir_non_acg || !state.results.length) {
    alert("请先完成识别，并填写 ACG 与非 ACG 两个输出文件夹");
    return;
  }

  state.moveRunning = true;
  updateBatchActionState();
  setButtonLoading(moveBatchButton, true, "移动中...");
  try {
    const startResponse = await api("/api/folder/move-job", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source_dir: settings.source_dir,
        output_dir_acg: settings.output_dir_acg,
        output_dir_non_acg: settings.output_dir_non_acg,
        path_layers: settings.path_layers,
        move_mode: settings.move_mode,
        results: state.results.filter(
          (result) =>
            !result.error &&
            (!(result.move && result.move.moved) || (result.undo && result.undo.undone)),
        ),
      }),
    });
    await pollJob(startResponse.job_id, (job) => {
      const moveMap = new Map(
        ((job.result && job.result.moved) || []).map((item) => [item.path, item]),
      );
      state.results.forEach((result) => {
        if (moveMap.has(result.path)) {
          result.move = moveMap.get(result.path);
        }
      });
      renderFolderResults(state.results);
      updateBatchActionState();
    });
  } catch (error) {
    alert(error.message || "移动失败");
  } finally {
    setButtonLoading(moveBatchButton, false);
    state.moveRunning = false;
    updateBatchActionState();
    hideProgress();
  }
}

async function undoCurrentMoves() {
  const settings = currentSettings();
  const undoable = state.results.filter(
    (result) => result.move && result.move.moved && !(result.undo && result.undo.undone),
  );
  if (!settings.source_dir || !undoable.length) {
    return;
  }

  state.undoRunning = true;
  updateBatchActionState();
  setButtonLoading(undoMoveButton, true, "撤销中...");
  try {
    const startResponse = await api("/api/folder/undo-job", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source_dir: settings.source_dir,
        output_dir_acg: settings.output_dir_acg,
        output_dir_non_acg: settings.output_dir_non_acg,
        results: undoable,
      }),
    });
    await pollJob(startResponse.job_id, (job) => {
      const undoMap = new Map(
        ((job.result && job.result.undone) || []).map((item) => [item.path, item]),
      );
      state.results.forEach((result) => {
        if (undoMap.has(result.path)) {
          result.undo = undoMap.get(result.path);
        }
      });
      renderFolderResults(state.results);
      updateBatchActionState();
    });
  } catch (error) {
    alert(error.message || "撤销移动失败");
  } finally {
    setButtonLoading(undoMoveButton, false);
    state.undoRunning = false;
    updateBatchActionState();
    hideProgress();
  }
}

function applyJobResult(job) {
  const result = job && job.result ? job.result : null;
  if (!result) {
    return;
  }

  if (job.kind === "scan" && Array.isArray(result.paths)) {
    state.scannedPaths = result.paths;
    state.results = [];
    scanSummary.textContent = `${state.scannedPaths.length} 张图片`;
    classifyFolderButton.disabled = state.scannedPaths.length === 0;
    updateBatchActionState();
    renderFolderResults(
      state.scannedPaths.map((path) => ({
        path,
        filename: path.split(/[\\/]/).pop(),
      })),
    );
  }

  if (job.kind === "classify" && Array.isArray(result.results)) {
    state.results = result.results;
    scanSummary.textContent = `${state.results.length} 张已识别`;
    renderFolderResults(state.results);
    updateBatchActionState();
  }

  if (job.kind === "move" && Array.isArray(result.moved)) {
    const moveMap = new Map(result.moved.map((item) => [item.path, item]));
    state.results.forEach((item) => {
      if (moveMap.has(item.path)) {
        item.move = moveMap.get(item.path);
      }
    });
    renderFolderResults(state.results);
    updateBatchActionState();
  }

  if (job.kind === "undo" && Array.isArray(result.undone)) {
    const undoMap = new Map(result.undone.map((item) => [item.path, item]));
    state.results.forEach((item) => {
      if (undoMap.has(item.path)) {
        item.undo = undoMap.get(item.path);
      }
    });
    renderFolderResults(state.results);
    updateBatchActionState();
  }
}

async function recoverRecentJob() {
  try {
    const payload = await api("/api/jobs/recent");
    const job = payload.job;
    if (!job) {
      return;
    }
    appendJobLogs(job);
    applyJobResult(job);

    if (job.status === "running" || job.status === "paused") {
      state.activeJobId = job.id;
      showProgress(job.progress || 0, job.total || 0, job.message || "恢复任务中...");
      await pollJob(job.id, applyJobResult);
    } else if (["done", "cancelled", "interrupted"].includes(job.status)) {
      showProgress(job.progress || 0, job.total || 0, job.message || "");
      setJobControls(false);
    }
  } catch {
    // Recovery is best-effort on initial page load.
  }
}

function updateWatcherUI(status) {
  if (!status) {
    return;
  }
  const progress = Number(status.batch_progress || 0);
  const total = Number(status.batch_total || 0);
  const pending = Number(status.pending_count || 0);
  const working = status.running && (["baselining", "filtering", "scanning", "processing", "starting"].includes(status.phase) || pending > 0);
  const modeLabels = {
    event: "事件模式",
    polling: "轮询模式",
    idle: "暂无",
  };
  watcherState.textContent = status.running ? (working ? "处理中" : "运行中") : "未运行";
  watcherState.classList.toggle("running", status.running);
  watcherState.classList.toggle("working", working);
  watcherProcessed.textContent = status.processed_count || 0;
  watcherLastScan.textContent = status.last_scan || "暂无";
  watcherScanned.textContent = status.scan_count || 0;
  watcherPending.textContent = pending;
  watcherCurrentFile.textContent = status.current_file || "暂无";
  watcherMode.textContent = modeLabels[status.monitor_mode] || status.monitor_mode || "暂无";
  watcherMessage.textContent = status.message || (status.running ? "自动监控运行中" : "监控未运行");
  watcherProgressText.textContent = total ? `${progress}/${total}` : "0/0";
  watcherProgressFill.style.width = total ? `${Math.min(100, Math.round((progress / total) * 100))}%` : "0%";
  startWatcherButton.disabled = status.running;
  stopWatcherButton.disabled = !status.running;
}

async function refreshWatcherStatus() {
  try {
    const status = await api("/api/watcher/status");
    updateWatcherUI(status);
    const watcherLogs = status.logs || [];
    if (watcherLogs.length) {
      let newLogs = watcherLogs;
      if (state.watcherLogKey) {
        const previousIndex = watcherLogs.findIndex((entry) => logKey(entry) === state.watcherLogKey);
        newLogs = previousIndex >= 0 ? watcherLogs.slice(previousIndex + 1) : watcherLogs.slice(-20);
      }
      appendLogs(newLogs);
      state.watcherLogKey = logKey(watcherLogs[watcherLogs.length - 1]);
      state.watcherLogCount = watcherLogs.length;
    }
  } catch {
    // The watcher endpoint can fail briefly during startup; keep the old state.
  }
}

async function startWatcher() {
  try {
    const status = await api("/api/watcher/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(currentSettings()),
    });
    updateWatcherUI(status.status || status);
    refreshWatcherStatus();
  } catch (error) {
    alert(error.message || "启动监控失败");
  }
}

async function stopWatcher() {
  try {
    const status = await api("/api/watcher/stop", { method: "POST" });
    updateWatcherUI(status.status || status);
    refreshWatcherStatus();
    await loadSettings();
  } catch (error) {
    alert(error.message || "停止监控失败");
  }
}

browseSourceButton.addEventListener("click", () => openBrowser("source"));
browseAcgOutputButton.addEventListener("click", () => openBrowser("acg-output"));
browseNonAcgOutputButton.addEventListener("click", () => openBrowser("non-acg-output"));
closeBrowseButton.addEventListener("click", closeBrowser);
cancelBrowseButton.addEventListener("click", closeBrowser);
confirmBrowseButton.addEventListener("click", confirmBrowserSelection);
browserGoButton.addEventListener("click", () => loadBrowser(browserPathInput.value));
browserPathInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    loadBrowser(browserPathInput.value);
  }
});
saveSettingsButton.addEventListener("click", async () => {
  try {
    setButtonLoading(saveSettingsButton, true, "保存中...");
    await saveSettings();
  } catch (error) {
    alert(error.message || "保存失败");
  } finally {
    setButtonLoading(saveSettingsButton, false);
  }
});
scanButton.addEventListener("click", scanFolder);
classifyFolderButton.addEventListener("click", classifyFolder);
moveBatchButton.addEventListener("click", moveCurrentResults);
undoMoveButton.addEventListener("click", undoCurrentMoves);
startWatcherButton.addEventListener("click", startWatcher);
stopWatcherButton.addEventListener("click", stopWatcher);
gridViewButton.addEventListener("click", () => {
  state.viewMode = "grid";
  updateViewMode();
});
listViewButton.addEventListener("click", () => {
  state.viewMode = "list";
  updateViewMode();
});
pageSizeInput.addEventListener("change", () => {
  const value = Math.max(1, Math.min(500, Number(pageSizeInput.value) || 20));
  state.pageSize = value;
  pageSizeInput.value = value;
  renderCurrentPage();
});
prevPageButton.addEventListener("click", () => {
  if (state.currentPage > 1) {
    state.currentPage -= 1;
    renderCurrentPage();
  }
});
nextPageButton.addEventListener("click", () => {
  const totalPages = Math.max(1, Math.ceil(state.folderRows.length / state.pageSize));
  if (state.currentPage < totalPages) {
    state.currentPage += 1;
    renderCurrentPage();
  }
});
clearLogsButton.addEventListener("click", () => {
  state.logs = [];
  renderLogs();
});
pauseJobButton.addEventListener("click", async () => {
  if (!state.activeJobId) {
    return;
  }
  await api(`/api/jobs/${encodeURIComponent(state.activeJobId)}/pause`, { method: "POST" });
  setJobControls(true, true);
});
resumeJobButton.addEventListener("click", async () => {
  if (!state.activeJobId) {
    return;
  }
  await api(`/api/jobs/${encodeURIComponent(state.activeJobId)}/resume`, { method: "POST" });
  setJobControls(true, false);
});
cancelJobButton.addEventListener("click", async () => {
  if (!state.activeJobId) {
    return;
  }
  await api(`/api/jobs/${encodeURIComponent(state.activeJobId)}/cancel`, { method: "POST" });
  setJobControls(false);
});

loadSettings();
renderLogs();
refreshWatcherStatus();
recoverRecentJob();
setInterval(refreshWatcherStatus, 3000);
