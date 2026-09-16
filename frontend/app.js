const chatEl = document.getElementById("chat");
const formEl = document.getElementById("chat-form");
const questionEl = document.getElementById("question");
const quickQuestionsEl = document.querySelector(".quick-questions-list");
const sendButtonEl = document.querySelector(".send-btn");
const moduleSelectorEl = document.getElementById("module-selector");
const agentWorkspaceEl = document.getElementById("agent-workspace");
const openNeoprofessorEl = document.getElementById("open-neoprofessor");
const backToModulesEl = document.getElementById("back-to-modules");
const newConsultationEl = document.getElementById("new-consultation");
const openMatrixEl = document.getElementById("open-matrix");
const consultationStatusEl = document.getElementById("consultation-status");
const consultationStageEl = document.getElementById("consultation-stage");
const consultationStageDescriptionEl = document.getElementById("consultation-stage-description");
const consultationCheckpointEl = document.getElementById("consultation-checkpoint");
const consultationProgressEl = document.getElementById("consultation-progress");
let consultationSessionId = null;
const consultationStages = [
  "DIAGNOSTICO",
  "DELIMITACAO",
  "ALTERNATIVAS",
  "VALIDACAO",
  "PLANEJAMENTO",
];
const consultationStageLabels = {
  DIAGNOSTICO: "diagnóstico",
  DELIMITACAO: "delimitação",
  ALTERNATIVAS: "alternativas",
  VALIDACAO: "validação",
  PLANEJAMENTO: "plano de ensino",
};
const consultationStageDescriptions = {
  DIAGNOSTICO: "Compreender o problema, o público e o desempenho esperado.",
  DELIMITACAO: "Definir objetivos, condições e limites da ação educativa.",
  ALTERNATIVAS: "Comparar caminhos pedagógicos e suas consequências.",
  VALIDACAO: "Confirmar com você a alternativa que deverá ser desenvolvida.",
  PLANEJAMENTO: "Organizar a trilha e produzir o plano de ensino.",
};

function openAgent() {
  moduleSelectorEl.hidden = true;
  agentWorkspaceEl.hidden = false;
  window.scrollTo({ top: 0, behavior: "smooth" });
  questionEl.focus();
}

function closeAgent() {
  agentWorkspaceEl.hidden = true;
  moduleSelectorEl.hidden = false;
  window.scrollTo({ top: 0, behavior: "smooth" });
  openNeoprofessorEl.focus();
}

function resetConsultation() {
  consultationSessionId = null;
  chatEl.replaceChildren();
  updateConsultationStatus({ stage: "DIAGNOSTICO", checkpoint: "" });
  questionEl.value = "";
  questionEl.focus();
}

function updateConsultationStatus(data) {
  const currentStage = data.stage || "DIAGNOSTICO";
  const readableStage = consultationStageLabels[currentStage] || currentStage
    .toLocaleLowerCase("pt-BR")
    .replaceAll("_", " ");
  consultationStageEl.textContent = `Etapa atual: ${readableStage}`;
  consultationStageDescriptionEl.textContent = consultationStageDescriptions[currentStage] || "";
  consultationCheckpointEl.textContent = data.checkpoint || "";
  consultationStatusEl.hidden = false;

  const currentIndex = consultationStages.indexOf(currentStage);
  consultationProgressEl.querySelectorAll(".progress-step").forEach((step) => {
    const stepIndex = consultationStages.indexOf(step.dataset.stage);
    step.classList.toggle("progress-step-current", stepIndex === currentIndex);
    step.classList.toggle("progress-step-complete", stepIndex < currentIndex);
    step.setAttribute("aria-current", stepIndex === currentIndex ? "step" : "false");
  });
}

function appendInlineMarkdown(parent, text) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  for (const part of parts) {
    if (part.startsWith("**") && part.endsWith("**")) {
      const strong = document.createElement("strong");
      strong.textContent = part.slice(2, -2);
      parent.appendChild(strong);
    } else if (part) {
      parent.appendChild(document.createTextNode(part));
    }
  }
}

function renderMarkdown(container, markdown) {
  const lines = markdown.replaceAll("\r\n", "\n").split("\n");
  let currentList = null;

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line) {
      currentList = null;
      continue;
    }

    const numberedHeading = line.match(/^(\d+)\.\s+\*\*(.+?)\*\*:?\s*$/);
    if (numberedHeading) {
      currentList = null;
      const heading = document.createElement("h3");
      heading.textContent = `${numberedHeading[1]}. ${numberedHeading[2]}`;
      container.appendChild(heading);
      continue;
    }

    const markdownHeading = line.match(/^(#{1,6})\s+(.+)$/);
    if (markdownHeading) {
      currentList = null;
      const heading = document.createElement("h3");
      appendInlineMarkdown(heading, markdownHeading[2]);
      container.appendChild(heading);
      continue;
    }

    const bullet = line.match(/^[-*]\s+(.+)$/);
    if (bullet) {
      if (!currentList) {
        currentList = document.createElement("ul");
        container.appendChild(currentList);
      }
      const item = document.createElement("li");
      appendInlineMarkdown(item, bullet[1]);
      currentList.appendChild(item);
      continue;
    }

    currentList = null;
    const paragraph = document.createElement("p");
    appendInlineMarkdown(paragraph, line);
    container.appendChild(paragraph);
  }
}

function addMessage(text, role) {
  const item = document.createElement("div");
  item.className = `message ${role}`;
  if (role === "bot") {
    renderMarkdown(item, text);
  } else {
    item.textContent = text;
  }

  chatEl.appendChild(item);
  chatEl.scrollTop = chatEl.scrollHeight;
  return item;
}

function addFeedbackControls(messageEl, responseId, sessionId) {
  const controls = document.createElement("div");
  controls.className = "feedback-controls";

  const prompt = document.createElement("span");
  prompt.className = "feedback-prompt";
  prompt.textContent = "Esta resposta foi útil?";
  controls.appendChild(prompt);

  const status = document.createElement("span");
  status.className = "feedback-status";
  status.setAttribute("aria-live", "polite");

  for (const [rating, symbol, label] of [
    ["up", "👍", "Resposta útil"],
    ["down", "👎", "Resposta não útil"],
  ]) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "feedback-button";
    button.dataset.rating = rating;
    button.textContent = symbol;
    button.setAttribute("aria-label", label);
    button.setAttribute("aria-pressed", "false");
    button.addEventListener("click", async () => {
      const buttons = controls.querySelectorAll(".feedback-button");
      buttons.forEach((item) => { item.disabled = true; });
      status.textContent = "Salvando...";

      try {
        const response = await fetch("/api/feedback", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            session_id: sessionId,
            response_id: responseId,
            rating,
          }),
        });
        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.detail || "Falha ao salvar a avaliação.");
        }

        buttons.forEach((item) => {
          item.classList.toggle("feedback-button-selected", item.dataset.rating === rating);
          item.setAttribute("aria-pressed", String(item.dataset.rating === rating));
        });
        status.textContent = "Avaliação registrada";
      } catch (error) {
        status.textContent = "Não foi possível registrar";
      } finally {
        buttons.forEach((item) => { item.disabled = false; });
      }
    });
    controls.appendChild(button);
  }

  controls.appendChild(status);
  messageEl.appendChild(controls);
}

function teachingPlanClipboardContent(planText) {
  const container = document.createElement("div");
  container.className = "clipboard-content";
  renderMarkdown(container, planText);
  document.body.appendChild(container);
  const content = {
    html: container.innerHTML,
    text: container.innerText,
  };
  container.remove();
  return content;
}

async function copyTeachingPlan(planText, button) {
  const originalLabel = button.textContent;
  const content = teachingPlanClipboardContent(planText);
  try {
    if (navigator.clipboard.write && window.ClipboardItem) {
      await navigator.clipboard.write([
        new ClipboardItem({
          "text/html": new Blob([content.html], { type: "text/html" }),
          "text/plain": new Blob([content.text], { type: "text/plain" }),
        }),
      ]);
    } else {
      await navigator.clipboard.writeText(content.text);
    }
    button.textContent = "Plano copiado";
  } catch (error) {
    const temporary = document.createElement("textarea");
    temporary.value = content.text;
    temporary.setAttribute("readonly", "");
    temporary.className = "clipboard-fallback";
    document.body.appendChild(temporary);
    temporary.select();
    const copied = document.execCommand("copy");
    temporary.remove();
    button.textContent = copied ? "Plano copiado" : "Não foi possível copiar";
  }
  window.setTimeout(() => { button.textContent = originalLabel; }, 2200);
}

function addTeachingPlanActions(container, planText, responseId, sessionId) {
  const actions = document.createElement("div");
  actions.className = "plan-actions";
  actions.setAttribute("aria-label", "Ações do plano de ensino");

  const copyButton = document.createElement("button");
  copyButton.type = "button";
  copyButton.className = "plan-action-button";
  copyButton.textContent = "Copiar plano";
  copyButton.addEventListener("click", () => {
    copyTeachingPlan(planText, copyButton);
  });

  const exportMenu = document.createElement("details");
  exportMenu.className = "export-menu";
  const exportSummary = document.createElement("summary");
  exportSummary.className = "plan-action-button";
  exportSummary.textContent = "Exportar";
  exportMenu.appendChild(exportSummary);

  const exportOptions = document.createElement("div");
  exportOptions.className = "export-options";
  for (const [format, label] of [
    ["docx", "Word (.docx)"],
    ["pdf", "PDF (.pdf)"],
  ]) {
    const link = document.createElement("a");
    const params = new URLSearchParams({ session_id: sessionId, format });
    link.href = `/api/exports/${responseId}?${params}`;
    link.textContent = label;
    link.className = "export-option";
    link.setAttribute("download", `plano-de-ensino.${format}`);
    link.addEventListener("click", () => { exportMenu.open = false; });
    exportOptions.appendChild(link);
  }
  exportMenu.appendChild(exportOptions);

  actions.append(copyButton, exportMenu);
  container.appendChild(actions);
}

function appendExplanationList(panel, title, values) {
  if (!Array.isArray(values) || values.length === 0) {
    return;
  }

  const heading = document.createElement("h4");
  heading.textContent = title;
  panel.appendChild(heading);

  const list = document.createElement("ul");
  for (const value of values) {
    const item = document.createElement("li");
    item.textContent = value;
    list.appendChild(item);
  }
  panel.appendChild(list);
}

function renderExplanation(panel, explanation) {
  panel.replaceChildren();

  const summary = document.createElement("p");
  summary.className = "explanation-summary";
  summary.textContent = explanation.summary;
  panel.appendChild(summary);

  appendExplanationList(panel, "Informações consideradas", explanation.confirmed_inputs);
  appendExplanationList(panel, "Fontes e evidências utilizadas", explanation.evidence);
  appendExplanationList(panel, "Critérios pedagógicos", explanation.pedagogical_criteria);
  appendExplanationList(panel, "Escolhas e consequências", explanation.tradeoffs);
  appendExplanationList(panel, "Limites e validações pendentes", explanation.limitations);
}

function addExplanationControl(container, responseId, sessionId) {
  const wrapper = document.createElement("div");
  wrapper.className = "explanation-control";

  const button = document.createElement("button");
  button.type = "button";
  button.className = "explanation-button";
  button.textContent = "Por que a IA recomendou isso?";
  button.setAttribute("aria-expanded", "false");

  const panel = document.createElement("div");
  panel.className = "explanation-panel";
  panel.hidden = true;

  button.addEventListener("click", async () => {
    if (button.dataset.loaded === "true") {
      const willOpen = panel.hidden;
      panel.hidden = !willOpen;
      button.setAttribute("aria-expanded", String(willOpen));
      button.textContent = willOpen
        ? "Ocultar justificativa"
        : "Por que a IA recomendou isso?";
      return;
    }

    button.disabled = true;
    button.textContent = "Carregando justificativa...";
    try {
      const params = new URLSearchParams({ session_id: sessionId });
      const response = await fetch(`/api/explanations/${responseId}?${params}`);
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "Falha ao carregar a justificativa.");
      }

      renderExplanation(panel, data);
      panel.hidden = false;
      button.dataset.loaded = "true";
      button.setAttribute("aria-expanded", "true");
      button.textContent = "Ocultar justificativa";
    } catch (error) {
      panel.replaceChildren();
      const errorMessage = document.createElement("p");
      errorMessage.className = "explanation-error";
      errorMessage.textContent = error.message;
      panel.appendChild(errorMessage);
      panel.hidden = false;
      button.textContent = "Tentar carregar a justificativa novamente";
    } finally {
      button.disabled = false;
    }
  });

  wrapper.append(button, panel);
  container.appendChild(wrapper);
}

async function submitQuestion(rawQuestion) {
  const question = rawQuestion.trim();
  if (!question) {
    return;
  }

  if (sendButtonEl) {
    sendButtonEl.disabled = true;
  }

  addMessage(question, "user");
  questionEl.value = "";

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question,
        session_id: consultationSessionId,
      }),
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "Falha no chat.");
    }

    consultationSessionId = data.session_id;
    const answerEl = addMessage(data.answer, "bot");
    if (data.has_teaching_plan || data.has_explanation) {
      const responseActions = document.createElement("div");
      responseActions.className = "response-actions";
      if (data.has_explanation) {
        addExplanationControl(
          responseActions,
          data.response_id,
          data.session_id,
        );
      }
      if (data.has_teaching_plan) {
        addTeachingPlanActions(
          responseActions,
          data.answer,
          data.response_id,
          data.session_id,
        );
      }
      answerEl.appendChild(responseActions);
    }
    addFeedbackControls(answerEl, data.response_id, data.session_id);
    updateConsultationStatus(data);
  } catch (error) {
    addMessage(`Erro: ${error.message}`, "bot");
  } finally {
    if (sendButtonEl) {
      sendButtonEl.disabled = false;
    }
  }
}

async function sendQuestion(event) {
  event.preventDefault();
  await submitQuestion(questionEl.value);
}

formEl.addEventListener("submit", sendQuestion);
questionEl.addEventListener("keydown", (event) => {
  if (
    event.key === "Enter"
    && !event.shiftKey
    && !event.isComposing
  ) {
    event.preventDefault();
    if (!sendButtonEl.disabled) {
      formEl.requestSubmit();
    }
  }
});
openNeoprofessorEl.addEventListener("click", openAgent);
backToModulesEl.addEventListener("click", closeAgent);
newConsultationEl.addEventListener("click", resetConsultation);
openMatrixEl.addEventListener("click", () => {
  window.open("/matriz", "_blank", "noopener,noreferrer");
});

if (quickQuestionsEl) {
  quickQuestionsEl.addEventListener("click", async (event) => {
    const button = event.target.closest(".quick-question-btn");
    if (!button) {
      return;
    }

    const question = button.dataset.question || "";
    questionEl.value = question;
    await submitQuestion(question);
    questionEl.focus();
  });
}
