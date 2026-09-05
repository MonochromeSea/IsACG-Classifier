const state = {
  files: [],
  objectUrls: [],
};

const dropZone = document.querySelector("#dropZone");
const fileInput = document.querySelector("#fileInput");
const classifyButton = document.querySelector("#classifyButton");
const clearButton = document.querySelector("#clearButton");
const modelSelect = document.querySelector("#modelSelect");
const moveAllButton = document.querySelector("#moveAllButton");
const statusPill = document.querySelector("#statusPill");
const statusText = document.querySelector("#statusText");
const queueBlock = document.querySelector("#queueBlock");
const queueGrid = document.querySelector("#queueGrid");
const queueCount = document.querySelector("#queueCount");
const resultGrid = document.querySelector("#resultGrid");
const resultCount = document.querySelector("#resultCount");
const emptyState = document.querySelector("#emptyState");
const queueItemTemplate = document.querySelector("#queueItemTemplate");
const resultCardTemplate = document.querySelector("#resultCardTemplate");

const MAX_FILES = 40;

function releaseObjectUrls() {
  state.objectUrls.forEach((url) => URL.revokeObjectURL(url));
  state.objectUrls = [];
}

function setFiles(fileList) {
  const incoming = Array.from(fileList).filter((file) => file.type.startsWith("image/"));
  if (!incoming.length) {
    return;
  }

  const available = MAX_FILES - state.files.length;
  state.files.push(...incoming.slice(0, available));
  renderQueue();
}

function renderQueue() {
  releaseObjectUrls();
  queueGrid.innerHTML = "";
  resultGrid.innerHTML = "";
  emptyState.hidden = false;
  resultCount.textContent = "暂无";
  moveAllButton.disabled = true;

  if (!state.files.length) {
    queueBlock.hidden = true;
    classifyButton.disabled = true;
    return;
  }

  queueBlock.hidden = false;
  classifyButton.disabled = false;
  queueCount.textContent = `${state.files.length} 张`;

  state.files.forEach((file, index) => {
    const item = queueItemTemplate.content.cloneNode(true);
    const image = item.querySelector("img");
    const name = item.querySelector(".queue-name");
    const removeButton = item.querySelector(".remove-button");
    const objectUrl = URL.createObjectURL(file);
    state.objectUrls.push(objectUrl);

    image.src = objectUrl;
    image.alt = file.name;
    name.textContent = file.name;
    removeButton.addEventListener("click", () => {
      state.files.splice(index, 1);
      renderQueue();
    });
    queueGrid.appendChild(item);
  });
}

function setStatus(text, mode = "ready") {
  statusText.textContent = text;
  statusPill.classList.remove("busy", "error");
  if (mode !== "ready") {
    statusPill.classList.add(mode);
  }
}

function markMoved(card, target, path) {
  card.classList.add("moved");
  const stateElement = card.querySelector(".move-state");
  const targetLabel = target === "acg" ? "ACG" : "非 ACG";
  stateElement.textContent = `已移动 · ${targetLabel} · ${path}`;
  card.querySelector(".move-acg-button").disabled = true;
  card.querySelector(".move-nonacg-button").disabled = true;
  updateMoveAllState();
}

function updateMoveAllState() {
  const moveableCards = resultGrid.querySelectorAll(
    ".result-card:not(.error):not(.moved)",
  ).length;
  moveAllButton.disabled = moveableCards === 0;
}

async function moveSingle(result, card, target) {
  if (!result.file_id || card.classList.contains("moved")) {
    return;
  }

  card.classList.add("moving");
  setStatus("正在移动图片...", "busy");

  try {
    const response = await fetch("/api/move", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file_id: result.file_id, target }),
    });
    const payload = await response.json();

    if (!response.ok || !payload.success) {
      throw new Error(payload.error || "移动失败");
    }

    markMoved(card, target, payload.path);
    setStatus(`已移动：${result.filename}`);
  } catch (error) {
    setStatus(error.message || "移动失败", "error");
  } finally {
    card.classList.remove("moving");
  }
}

function createResultCard(result, index) {
  const card = resultCardTemplate.content.cloneNode(true);
  const image = card.querySelector(".result-image img");
  const label = card.querySelector(".result-label");
  const confidence = card.querySelector(".result-confidence");
  const meterFill = card.querySelector(".meter-fill");
  const model = card.querySelector(".result-model");
  const elapsed = card.querySelector(".result-time");
  const filename = card.querySelector(".result-filename");
  const moveAcgButton = card.querySelector(".move-acg-button");
  const moveNonacgButton = card.querySelector(".move-nonacg-button");
  const article = card.querySelector(".result-card");

  filename.textContent = result.filename || "未命名图片";

  if (result.error) {
    article.classList.add("error");
    label.textContent = "无法识别";
    confidence.textContent = "错误";
    model.textContent = "请检查图片格式";
    elapsed.textContent = "";
    moveAcgButton.disabled = true;
    moveNonacgButton.disabled = true;
    meterFill.style.width = "0";
    return card;
  }

  const sourceFile = state.files[index] || state.files.find((file) => file.name === result.filename);
  const objectUrl = URL.createObjectURL(sourceFile);
  state.objectUrls.push(objectUrl);
  image.src = objectUrl;
  image.alt = result.filename || "分类图片";

  article.classList.add(result.is_acg ? "acg" : "not-acg");
  article.__result = result;
  label.textContent = result.label;
  confidence.textContent = `${(result.confidence * 100).toFixed(2)}%`;
  model.textContent = result.model.toUpperCase();
  elapsed.textContent = `${result.elapsed_ms} ms`;
  moveAcgButton.addEventListener("click", () => moveSingle(result, article, "acg"));
  moveNonacgButton.addEventListener("click", () => moveSingle(result, article, "non_acg"));

  requestAnimationFrame(() => {
    meterFill.style.width = `${Math.max(0, Math.min(100, result.confidence * 100))}%`;
  });

  return card;
}

async function classify() {
  if (!state.files.length) {
    return;
  }

  classifyButton.disabled = true;
  setStatus("正在分类...", "busy");

  const formData = new FormData();
  state.files.forEach((file) => formData.append("files", file));
  formData.append("model", modelSelect.value);

  try {
    const response = await fetch("/api/predict", {
      method: "POST",
      body: formData,
    });
    const payload = await response.json();

    if (!response.ok || !payload.success) {
      throw new Error(payload.error || "分类失败");
    }

    resultGrid.innerHTML = "";
    payload.results.forEach((result, index) => {
      resultGrid.appendChild(createResultCard(result, index));
    });
    emptyState.hidden = true;
    resultCount.textContent = `${payload.results.length} 张`;
    updateMoveAllState();
    setStatus(`分类完成 · ${payload.model.toUpperCase()}`);
  } catch (error) {
    setStatus(error.message || "分类失败", "error");
  } finally {
    classifyButton.disabled = false;
  }
}

async function moveAllByResult() {
  const cards = Array.from(
    resultGrid.querySelectorAll(".result-card:not(.error):not(.moved)"),
  );
  if (!cards.length) {
    return;
  }

  const items = cards.map((card) => {
    const result = card.__result;
    return {
      file_id: result.file_id,
      target: result.is_acg ? "acg" : "non_acg",
    };
  });

  moveAllButton.disabled = true;
  setStatus("正在按结果移动图片...", "busy");

  try {
    const response = await fetch("/api/move-batch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items }),
    });
    const payload = await response.json();

    if (!response.ok || !payload.success) {
      throw new Error(payload.error || "批量移动失败");
    }

    payload.moved.forEach((movedItem) => {
      const card = cards.find((item) => item.__result.file_id === movedItem.file_id);
      if (card) {
        markMoved(card, movedItem.target, movedItem.path);
      }
    });

    if (payload.failed.length) {
      setStatus(`已移动 ${payload.moved.length} 张，${payload.failed.length} 张失败`, "error");
    } else {
      setStatus(`已按结果移动 ${payload.moved.length} 张图片`);
    }
  } catch (error) {
    setStatus(error.message || "批量移动失败", "error");
  } finally {
    updateMoveAllState();
  }
}

function clearAll() {
  state.files = [];
  releaseObjectUrls();
  fileInput.value = "";
  renderQueue();
  setStatus("模型已就绪");
}

dropZone.addEventListener("click", () => fileInput.click());
dropZone.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    fileInput.click();
  }
});
fileInput.addEventListener("change", (event) => {
  setFiles(event.target.files);
  fileInput.value = "";
});

["dragenter", "dragover"].forEach((eventName) => {
  dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.add("dragging");
  });
});

["dragleave", "drop"].forEach((eventName) => {
  dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.remove("dragging");
  });
});

dropZone.addEventListener("drop", (event) => {
  setFiles(event.dataTransfer.files);
});

classifyButton.addEventListener("click", classify);
moveAllButton.addEventListener("click", moveAllByResult);
clearButton.addEventListener("click", clearAll);

renderQueue();
