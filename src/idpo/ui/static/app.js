const fieldList = document.getElementById("field-list");
const addFieldBtn = document.getElementById("add-field");
const runForm = document.getElementById("run-form");
const statusPill = document.getElementById("status-pill");
const formHint = document.getElementById("form-hint");
const runMeta = document.getElementById("run-meta");
const downloadEntities = document.getElementById("download-entities");
const downloadDocs = document.getElementById("download-docs");
const downloadRun = document.getElementById("download-run");
const resultsTable = document.getElementById("results-table");
const viewTabs = document.querySelectorAll(".tab");

const docsBaseColumns = [
  "doc_id",
  "source",
  "doc_type",
  "vendor_cluster",
  "quality_bin",
  "complexity_bin",
  "content_profile",
  "summary",
];
let lastPayload = null;
let activeView = "entities";

function addFieldRow(name = "", description = "") {
  const row = document.createElement("div");
  row.className = "field-row";
  row.innerHTML = `
    <input type="text" placeholder="Field name" value="${name}" />
    <input type="text" placeholder="Description (optional)" value="${description}" />
    <button type="button" class="remove">x</button>
  `;
  row.querySelector(".remove").addEventListener("click", () => row.remove());
  fieldList.appendChild(row);
}

addFieldBtn.addEventListener("click", () => addFieldRow());

addFieldRow("invoice_number", "Unique invoice id or reference");
addFieldRow("invoice_date", "Issue date on the document");
addFieldRow("total_amount", "Total amount due");

runForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  formHint.textContent = "";
  statusPill.textContent = "Running...";
  statusPill.style.background = "rgba(217, 119, 65, 0.2)";

  const files = document.getElementById("files").files;
  if (!files.length) {
    formHint.textContent = "Add at least one document file.";
    statusPill.textContent = "Idle";
    return;
  }

  const fieldRows = Array.from(fieldList.querySelectorAll(".field-row"));
  const fields = fieldRows
    .map((row) => {
      const inputs = row.querySelectorAll("input");
      return {
        name: inputs[0].value.trim(),
        description: inputs[1].value.trim(),
      };
    })
    .filter((field) => field.name);

  const formData = new FormData();
  Array.from(files).forEach((file) => formData.append("files", file));
  formData.append("fields", JSON.stringify(fields));
  formData.append("config_path", document.getElementById("config-path").value.trim());

  try {
    const response = await fetch("/api/run", {
      method: "POST",
      body: formData,
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Run failed.");
    }
    renderRun(payload);
    statusPill.textContent = "Complete";
    statusPill.style.background = "rgba(68, 116, 119, 0.2)";
  } catch (error) {
    statusPill.textContent = "Error";
    formHint.textContent = error.message;
  }
});

function renderRun(payload) {
  lastPayload = payload;
  const metaItems = runMeta.querySelectorAll("strong");
  if (metaItems.length >= 3) {
    metaItems[0].textContent = payload.run_id;
    metaItems[1].textContent = payload.metrics?.doc_count ?? payload.docs.length;
    const duration = payload.metrics?.duration_ms
      ? `${Math.round(payload.metrics.duration_ms)} ms`
      : "--";
    metaItems[2].textContent = duration;
  }

  downloadEntities.href = `/api/runs/${payload.run_id}/entities.xlsx`;
  downloadDocs.href = `/api/runs/${payload.run_id}/docs.xlsx`;
  downloadRun.href = `/api/runs/${payload.run_id}/run.xlsx`;
  downloadEntities.setAttribute("aria-disabled", "false");
  downloadDocs.setAttribute("aria-disabled", "false");
  downloadRun.setAttribute("aria-disabled", "false");

  if (payload.warnings && payload.warnings.length) {
    formHint.textContent = `Preflight warnings: ${payload.warnings.join(" | ")}`;
  }

  renderActiveView();
}

function collectColumns(docs, baseColumns) {
  const set = new Set();
  docs.forEach((doc) => Object.keys(doc).forEach((key) => set.add(key)));
  const ordered = baseColumns.filter((key) => set.has(key));
  const remaining = Array.from(set).filter((key) => !ordered.includes(key));
  remaining.sort();
  return ordered.concat(remaining);
}

function renderActiveView() {
  if (!lastPayload) {
    return;
  }
  if (activeView === "docs") {
    const docs = lastPayload.docs || [];
    const columns = collectColumns(docs, docsBaseColumns);
    renderTable(columns, docs);
    return;
  }
  const entities = lastPayload.entities && lastPayload.entities.length
    ? lastPayload.entities
    : deriveEntities(lastPayload.docs || []);
  const baseColumns = ["doc_id"];
  const columns = collectColumns(entities, baseColumns);
  renderTable(columns, entities);
}

function deriveEntities(docs) {
  return docs.map((doc) => {
    const row = { doc_id: doc.doc_id };
    Object.keys(doc).forEach((key) => {
      if (key.startsWith("field_") && !key.includes("_confidence") && !key.includes("_page") && !key.includes("_span") && !key.includes("_source")) {
        row[key.replace("field_", "")] = doc[key];
      }
    });
    return row;
  });
}

function renderTable(columns, docs) {
  const thead = resultsTable.querySelector("thead");
  const tbody = resultsTable.querySelector("tbody");
  thead.innerHTML = "";
  tbody.innerHTML = "";

  const headerRow = document.createElement("tr");
  columns.forEach((col) => {
    const th = document.createElement("th");
    th.textContent = col;
    headerRow.appendChild(th);
  });
  thead.appendChild(headerRow);

  docs.forEach((doc) => {
    const row = document.createElement("tr");
    columns.forEach((col) => {
      const td = document.createElement("td");
      const value = doc[col];
      td.textContent = value === undefined || value === null ? "" : value;
      row.appendChild(td);
    });
    tbody.appendChild(row);
  });
}

viewTabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    viewTabs.forEach((btn) => btn.classList.remove("active"));
    tab.classList.add("active");
    activeView = tab.dataset.view;
    renderActiveView();
  });
});
