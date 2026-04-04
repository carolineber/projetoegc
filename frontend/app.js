const chatEl = document.getElementById("chat");
const formEl = document.getElementById("chat-form");
const questionEl = document.getElementById("question");
const quickQuestionsEl = document.querySelector(".quick-questions-list");
const sendButtonEl = document.querySelector(".send-btn");

function addMessage(text, role, sources = []) {
  const item = document.createElement("div");
  item.className = `message ${role}`;
  item.textContent = text;

  if (sources.length > 0) {
    const sourceEl = document.createElement("div");
    sourceEl.className = "sources";
    sourceEl.textContent = `Fontes: ${sources.join(", ")}`;
    item.appendChild(sourceEl);
  }

  chatEl.appendChild(item);
  chatEl.scrollTop = chatEl.scrollHeight;
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
      body: JSON.stringify({ question }),
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "Falha no chat.");
    }

    addMessage(data.answer, "bot", data.sources || []);
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
