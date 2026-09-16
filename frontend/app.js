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
const consultationCheckpointEl = document.getElementById("consultation-checkpoint");
let consultationSessionId = null;

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
  consultationStatusEl.hidden = true;
  questionEl.value = "";
  questionEl.focus();
}

function updateConsultationStatus(data) {
  const readableStage = (data.stage || "DIAGNOSTICO")
    .toLocaleLowerCase("pt-BR")
    .replaceAll("_", " ");
  consultationStageEl.textContent = `Etapa: ${readableStage}`;
  consultationCheckpointEl.textContent = data.checkpoint || "";
  consultationStatusEl.hidden = false;
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
