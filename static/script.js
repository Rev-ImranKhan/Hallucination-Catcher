// ============================================================
// Hallucination Catcher - frontend logic
// ============================================================

const fileInput = document.getElementById("fileInput");
const dropzone = document.getElementById("dropzone");
const dzText = document.getElementById("dzText");
const uploadForm = document.getElementById("uploadForm");
const uploadBtn = document.getElementById("uploadBtn");
const uploadResult = document.getElementById("uploadResult");
const docStatusPill = document.getElementById("docStatusPill");

const questionsSection = document.getElementById("questionsSection");
const questionList = document.getElementById("questionList");
const customQuestionInput = document.getElementById("customQuestionInput");
const addQuestionBtn = document.getElementById("addQuestionBtn");
const runEvalBtn = document.getElementById("runEvalBtn");

const progressWrap = document.getElementById("progressWrap");
const progressFill = document.getElementById("progressFill");
const progressLabel = document.getElementById("progressLabel");

const emptyState = document.getElementById("emptyState");
const dashboard = document.getElementById("dashboard");
const resultsList = document.getElementById("resultsList");

let summaryChart = null;
let customQuestionCounter = 0;

// ---------------- Dropzone interactions ----------------
dropzone.addEventListener("click", () => fileInput.click());

fileInput.addEventListener("change", () => {
  if (fileInput.files.length > 0) {
    dzText.textContent = fileInput.files[0].name;
  }
});

["dragover", "dragleave", "drop"].forEach((evt) => {
  dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    if (evt === "dragover") dropzone.classList.add("drag-over");
    else dropzone.classList.remove("drag-over");
  });
});

dropzone.addEventListener("drop", (e) => {
  const file = e.dataTransfer.files[0];
  if (file) {
    fileInput.files = e.dataTransfer.files;
    dzText.textContent = file.name;
  }
});

// ---------------- Upload ----------------
uploadForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!fileInput.files.length) {
    showUploadResult("Please choose a file first.", true);
    return;
  }

  const formData = new FormData();
  formData.append("document", fileInput.files[0]);

  uploadBtn.disabled = true;
  uploadBtn.textContent = "Processing...";
  uploadResult.classList.add("hidden");

  try {
    const res = await fetch("/upload", { method: "POST", body: formData });
    const data = await res.json();

    if (!res.ok) {
      showUploadResult(data.error || "Upload failed.", true);
      return;
    }

    showUploadResult(`"${data.filename}" processed into ${data.chunk_count} chunks.`, false);
    docStatusPill.textContent = data.filename;
    docStatusPill.classList.add("active");

    renderQuestionList(data.default_questions);
    questionsSection.classList.remove("hidden");
  } catch (err) {
    showUploadResult("Network error: " + err.message, true);
  } finally {
    uploadBtn.disabled = false;
    uploadBtn.textContent = "Process Document";
  }
});

function showUploadResult(message, isError) {
  uploadResult.textContent = message;
  uploadResult.classList.remove("hidden");
  uploadResult.classList.toggle("error", isError);
}

// ---------------- Question list ----------------
function renderQuestionList(questions) {
  questionList.innerHTML = "";
  questions.forEach((q, i) => addQuestionItem(q, `default_${i}`, false));
}

function addQuestionItem(text, id, isCustom) {
  const item = document.createElement("label");
  item.className = "question-item" + (isCustom ? " custom" : "");
  item.innerHTML = `
    <input type="checkbox" checked data-qid="${id}">
    <span>${escapeHtml(text)}</span>
  `;
  questionList.appendChild(item);
}

addQuestionBtn.addEventListener("click", () => {
  const text = customQuestionInput.value.trim();
  if (!text) return;
  customQuestionCounter++;
  addQuestionItem(text, `custom_${customQuestionCounter}`, true);
  customQuestionInput.value = "";
});

customQuestionInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    addQuestionBtn.click();
  }
});

// ---------------- Run evaluation ----------------
runEvalBtn.addEventListener("click", async () => {
  const checked = Array.from(questionList.querySelectorAll("input[type=checkbox]:checked"));
  const questions = checked.map((cb) => cb.parentElement.querySelector("span").textContent);

  if (questions.length === 0) {
    alert("Select at least one question to run.");
    return;
  }

  runEvalBtn.disabled = true;
  runEvalBtn.textContent = "Starting...";
  progressWrap.classList.remove("hidden");
  progressFill.style.width = "0%";
  progressLabel.textContent = `Evaluating 0 / ${questions.length}`;

  try {
    const res = await fetch("/run-evaluation", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ questions }),
    });
    const data = await res.json();

    if (!res.ok) {
      alert(data.error || "Failed to start evaluation.");
      resetRunButton();
      return;
    }

    pollJobStatus(data.job_id);
  } catch (err) {
    alert("Network error: " + err.message);
    resetRunButton();
  }
});

function resetRunButton() {
  runEvalBtn.disabled = false;
  runEvalBtn.textContent = "Run Evaluation";
}

function pollJobStatus(jobId) {
  const interval = setInterval(async () => {
    try {
      const res = await fetch(`/run-evaluation/status/${jobId}`);
      const data = await res.json();

      const pct = data.total ? Math.round((data.completed / data.total) * 100) : 0;
      progressFill.style.width = pct + "%";
      progressLabel.textContent = `Evaluating ${data.completed} / ${data.total}`;

      if (data.status === "done") {
        clearInterval(interval);
        resetRunButton();
        progressLabel.textContent = `Done — ${data.total} / ${data.total}`;
        renderResults(data.results, data.summary);
      }
    } catch (err) {
      clearInterval(interval);
      resetRunButton();
      alert("Lost connection while polling evaluation status.");
    }
  }, 900);
}

// ---------------- Render results ----------------
function renderResults(results, summary) {
  emptyState.classList.add("hidden");
  dashboard.classList.remove("hidden");

  document.getElementById("statYes").textContent = summary.Yes;
  document.getElementById("statPartial").textContent = summary.Partially;
  document.getElementById("statNo").textContent = summary.No;

  const errorCard = document.getElementById("statErrorCard");
  const errorCount = summary.Error || 0;
  document.getElementById("statError").textContent = errorCount;
  errorCard.classList.toggle("hidden", errorCount === 0);

  resultsList.innerHTML = "";
  results.forEach((r, i) => resultsList.appendChild(buildResultCard(r, i)));

  try {
    renderChart(summary);
  } catch (err) {
    console.error("Chart rendering failed (cards are unaffected):", err);
  }
}

function renderChart(summary) {
  const ctx = document.getElementById("summaryChart").getContext("2d");
  const data = [summary.Yes, summary.Partially, summary.No];

  if (summaryChart) {
    summaryChart.data.datasets[0].data = data;
    summaryChart.update();
    return;
  }

  summaryChart = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels: ["Fully Grounded", "Partially Grounded", "Hallucinated"],
      datasets: [{
        data: data,
        backgroundColor: ["#3ddc84", "#ffc861", "#ff5266"],
        borderColor: "#15171b",
        borderWidth: 3,
      }],
    },
    options: {
      responsive: false,
      cutout: "68%",
      plugins: {
        legend: {
          position: "bottom",
          labels: { color: "#9a9ea6", font: { size: 11, family: "Inter" }, padding: 12, boxWidth: 10 },
        },
      },
    },
  });
}

function buildResultCard(result, index) {
  const card = document.createElement("div");
  card.className = "result-card";

  const chunksHtml = (result.source_chunks || [])
    .map((c) => `<div class="chunk-box">${escapeHtml(c)}</div>`)
    .join("");

  card.innerHTML = `
    <div class="result-card-header" data-index="${index}">
      <span class="verdict-dot ${result.verdict}"></span>
      <span class="result-question">${escapeHtml(result.question)}</span>
      <span class="score-tag">${result.score}/100</span>
      <span class="verdict-badge ${result.verdict}">${result.verdict === "No" ? "Hallucinated" : result.verdict === "Error" ? "Error" : result.verdict}</span>
      <span class="chevron">&#9656;</span>
    </div>
    <div class="result-card-body">
      <div class="result-card-body-inner">
        <div class="detail-block">
          <h4>Generated Answer</h4>
          <p>${escapeHtml(result.answer)}</p>
        </div>
        ${result.unsupported_part ? `
        <div class="detail-block">
          <h4>Unsupported Part</h4>
          <p class="unsupported-text">${escapeHtml(result.unsupported_part)}</p>
        </div>` : ""}
        <div class="detail-block">
          <h4>Judge's Reasoning</h4>
          <p>${escapeHtml(result.reasoning || "")}</p>
        </div>
        <div class="detail-block">
          <h4>Retrieved Source Chunks</h4>
          ${chunksHtml || "<p>No chunks retrieved.</p>"}
        </div>
      </div>
    </div>
  `;

  const header = card.querySelector(".result-card-header");
  const body = card.querySelector(".result-card-body");

  header.addEventListener("click", () => {
    const isOpen = card.classList.contains("open");
    if (isOpen) {
      body.style.maxHeight = null;
      card.classList.remove("open");
    } else {
      card.classList.add("open");
      body.style.maxHeight = body.scrollHeight + "px";
    }
  });

  return card;
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str == null ? "" : str;
  return div.innerHTML;
}
