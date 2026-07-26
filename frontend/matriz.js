const PAGE_SIZE = 20;
const fields = {
  competency: "Competências (capacidades de/para)",
  category: "Categoria",
  subcategory: "Subcategoria",
  role: "Cargo",
  axis: "Eixo Funcional",
  unit: "Unidade Temática",
  knowledge: "Conhecimento Crítico e para Prática",
  objective: "Objetivo de Aprendizagem",
  objectiveType: "Tipologia de Objetivo de Aprendizagem",
  reference: "Matriz de Referência",
};

const bodyEl = document.getElementById("matrix-body");
const emptyStateEl = document.getElementById("empty-state");
const resultsCountEl = document.getElementById("results-count");
const pageIndicatorEl = document.getElementById("page-indicator");
const previousPageEl = document.getElementById("previous-page");
const nextPageEl = document.getElementById("next-page");
const clearFiltersEl = document.getElementById("clear-filters");
const searchEl = document.getElementById("search");
const categoryFilterEl = document.getElementById("category-filter");
const axisFilterEl = document.getElementById("axis-filter");
const unitFilterEl = document.getElementById("unit-filter");

let records = [];
let filteredRecords = [];
let currentPage = 1;

function normalize(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase("pt-BR");
}

function text(record, field) {
  return String(record[field] || "").trim();
}

function uniqueValues(field) {
  return [...new Set(records.map((record) => text(record, field)).filter(Boolean))]
    .sort((left, right) => left.localeCompare(right, "pt-BR"));
}

function fillSelect(select, field) {
  const fragment = document.createDocumentFragment();
  for (const value of uniqueValues(field)) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    fragment.appendChild(option);
  }
  select.appendChild(fragment);
}

function createCell(content, className = "") {
  const cell = document.createElement("td");
  if (className) {
    cell.className = className;
  }
  cell.textContent = content || "—";
  return cell;
}

function createDetailItem(label, value) {
  const wrapper = document.createElement("div");
  wrapper.className = "detail-item";
  const term = document.createElement("dt");
  term.textContent = label;
  const description = document.createElement("dd");
  description.textContent = value || "Não informado";
  wrapper.append(term, description);
  return wrapper;
}

function createRecordRows(record) {
  const row = document.createElement("tr");

  row.appendChild(createCell(text(record, fields.competency), "competency-cell"));

  const axisCell = document.createElement("td");
  axisCell.className = "axis-cell";
  const axis = document.createElement("strong");
  axis.textContent = text(record, fields.axis) || "—";
  const unit = document.createElement("span");
  unit.textContent = text(record, fields.unit) || "—";
  axisCell.append(axis, unit);
  row.appendChild(axisCell);

  row.appendChild(createCell(text(record, fields.knowledge)));
  row.appendChild(createCell(text(record, fields.objective)));

  const actionCell = document.createElement("td");
  const detailButton = document.createElement("button");
  detailButton.type = "button";
  detailButton.className = "detail-button";
  detailButton.textContent = "Detalhes";
  detailButton.setAttribute("aria-expanded", "false");
  actionCell.appendChild(detailButton);
  row.appendChild(actionCell);

  const detailRow = document.createElement("tr");
  detailRow.className = "detail-row";
  detailRow.hidden = true;
  const detailCell = document.createElement("td");
  detailCell.colSpan = 5;
  const detailList = document.createElement("dl");
  detailList.className = "detail-grid";

  const detailFields = [
    ["Categoria", fields.category],
    ["Subcategoria", fields.subcategory],
    ["Cargo", fields.role],
    ["Eixo funcional", fields.axis],
    ["Unidade temática", fields.unit],
    ["Tipologia do objetivo", fields.objectiveType],
    ["Matriz de referência", fields.reference],
    ["Competência", fields.competency],
    ["Conhecimento crítico e para prática", fields.knowledge],
    ["Objetivo de aprendizagem", fields.objective],
  ];
  for (const [label, field] of detailFields) {
    detailList.appendChild(createDetailItem(label, text(record, field)));
  }
  detailCell.appendChild(detailList);
  detailRow.appendChild(detailCell);

  detailButton.addEventListener("click", () => {
    detailRow.hidden = !detailRow.hidden;
    detailButton.textContent = detailRow.hidden ? "Detalhes" : "Fechar";
    detailButton.setAttribute("aria-expanded", String(!detailRow.hidden));
  });

  return [row, detailRow];
}

function render() {
  bodyEl.replaceChildren();
  const pageCount = Math.max(1, Math.ceil(filteredRecords.length / PAGE_SIZE));
  currentPage = Math.min(currentPage, pageCount);
  const start = (currentPage - 1) * PAGE_SIZE;
  const pageRecords = filteredRecords.slice(start, start + PAGE_SIZE);
  const fragment = document.createDocumentFragment();

  for (const record of pageRecords) {
    const [row, detailRow] = createRecordRows(record);
    fragment.append(row, detailRow);
  }
  bodyEl.appendChild(fragment);

  emptyStateEl.hidden = filteredRecords.length !== 0;
  resultsCountEl.textContent = `${filteredRecords.length} registro(s) encontrado(s)`;
  pageIndicatorEl.textContent = `Página ${currentPage} de ${pageCount}`;
  previousPageEl.disabled = currentPage <= 1;
  nextPageEl.disabled = currentPage >= pageCount;
}

function applyFilters() {
  const query = normalize(searchEl.value);
  const category = categoryFilterEl.value;
  const axis = axisFilterEl.value;
  const unit = unitFilterEl.value;

  filteredRecords = records.filter((record) => {
    const matchesQuery = !query
      || Object.values(record).some((value) => normalize(value).includes(query));
    return matchesQuery
      && (!category || text(record, fields.category) === category)
      && (!axis || text(record, fields.axis) === axis)
      && (!unit || text(record, fields.unit) === unit);
  });
  currentPage = 1;
  render();
}

function clearFilters() {
  searchEl.value = "";
  categoryFilterEl.value = "";
  axisFilterEl.value = "";
  unitFilterEl.value = "";
  applyFilters();
  searchEl.focus();
}

async function loadMatrix() {
  try {
    const response = await fetch("/api/mcn");
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "Falha ao carregar a matriz.");
    }
    records = data;
    filteredRecords = records;
    fillSelect(categoryFilterEl, fields.category);
    fillSelect(axisFilterEl, fields.axis);
    fillSelect(unitFilterEl, fields.unit);
    render();
  } catch (error) {
    resultsCountEl.textContent = "Não foi possível carregar os registros.";
    emptyStateEl.textContent = error.message;
    emptyStateEl.hidden = false;
  }
}

searchEl.addEventListener("input", applyFilters);
categoryFilterEl.addEventListener("change", applyFilters);
axisFilterEl.addEventListener("change", applyFilters);
unitFilterEl.addEventListener("change", applyFilters);
clearFiltersEl.addEventListener("click", clearFilters);
previousPageEl.addEventListener("click", () => {
  currentPage -= 1;
  render();
  window.scrollTo({ top: document.querySelector(".matrix-board").offsetTop, behavior: "smooth" });
});
nextPageEl.addEventListener("click", () => {
  currentPage += 1;
  render();
  window.scrollTo({ top: document.querySelector(".matrix-board").offsetTop, behavior: "smooth" });
});

loadMatrix();
