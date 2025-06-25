let pendingQuestion = null;
let lastQuestion = null;
let lastAnswer = null;
let isSpeaking = false;
let synth = window.speechSynthesis;
let currentUtterance = null;

// === Upload Fruit ===
document.getElementById('uploadForm').onsubmit = async (e) => {
  e.preventDefault();
  const formData = new FormData(e.target);
  const res = await fetch('/add-fruit', { method: 'POST', body: formData });
  const data = await res.json();
  const result = document.getElementById('uploadResult');
  result.innerHTML = data.error
    ? `<p style="color:red">${data.error}</p>`
    : `<p style="color:green">${data.message}</p><img src="${data.image_url}" />`;
};

// === Predict via Voice ===
async function startVoicePrediction() {
  if (cancelIfSpeaking()) return;
  speak("Please say the fruit name.", () => {
    listenVoice(async (spokenText) => {
      const res = await fetch('/predict', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: spokenText })
      });
      const data = await res.json();
      const result = document.getElementById('predictResult');
      if (data.error) {
        speak("Sorry, I could not recognize the fruit.");
        result.innerHTML = `<p style="color:red">${data.error}</p>`;
      } else {
        speak(`It looks like ${data.prediction}`);
        result.innerHTML = `<p style="color:blue">Prediction: ${data.prediction}</p><img src="${data.image_url}" />`;
      }
    });
  });
}

// === Ask a Question ===
async function startAsking() {
  if (cancelIfSpeaking()) return;
  updateAskButton("Listening...");
  speak("Please ask your question.", () => {
    listenVoice(handleAsk);
  });
}

// === Handle Voice or Chat Ask ===
async function handleAsk(question) {
  updateAskButton("Processing...");
  pendingQuestion = question;
  const res = await fetch('/ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      question,
      last_question: lastQuestion,
      last_answer: lastAnswer
    })
  });
  const data = await res.json();
  const qaResult = document.getElementById('qaResult');
  lastQuestion = pendingQuestion;

  if (data.answer) {
    lastAnswer = data.answer;
    qaResult.innerHTML = `Answer: ${data.answer} (${data.source})`;
    speak(data.answer);
  } else {
    qaResult.innerHTML = `
      <p>❌ I don't know the answer.</p>
      <button onclick="searchNow()">🔍 Search</button>
      <button onclick="teachNow()">✏️ Teach</button>
    `;
    speak("I don't know the answer. You can search or teach me.");
  }

  updateAskButton("Ask a Question");
}

// === Search Now ===
async function searchNow(fromChat = false) {
  if (!pendingQuestion) return;

  const expandPhrases = ["describe more", "more details", "explain more", "expand"];
  const isExpand = expandPhrases.includes(pendingQuestion.toLowerCase());
  const searchQuery = isExpand && lastQuestion ? lastQuestion : pendingQuestion;

  const res = await fetch('/search', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question: searchQuery, last_question: lastQuestion })
  });

  const data = await res.json();
  const qaResult = document.getElementById('qaResult');

  if (data.answer) {
    qaResult.innerHTML = `🔍 Found on Wiki: ${data.answer}`;

    // If triggered from voice, speak. If from chat, only add to chat.
    if (fromChat) {
      addChatMessage("Assistant", `${data.answer} (${data.source})`);
    } else {
      speak(data.answer);
    }
  } else {
    qaResult.innerHTML = `❌ Still couldn't find the answer.`;
    speak("Sorry, I still couldn't find the answer.");
  }
}


// === Teach Now ===
async function teachNow() {
  if (!pendingQuestion) return;
  speak("Please tell me the answer now.", () => {
    listenVoice(async (response) => {
      if (response.toLowerCase().includes("stop")) {
        speak("Okay, cancelled.");
        pendingQuestion = null;
        return;
      }

      await saveAnswer(pendingQuestion, response);
      document.getElementById('qaResult').innerHTML = `✅ Learned: "${pendingQuestion}" → "${response}"`;
      speak("Thanks! I have learned the new answer.");
      pendingQuestion = null;
    });
  });
}

// === Save Answer ===
async function saveAnswer(question, answer) {
  const res = await fetch('/teach', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, answer })
  });
  const data = await res.json();
  speak(data.message || "Answer saved successfully.");
}

// === Teach via Form ===
async function submitTeaching() {
  const question = document.getElementById('teachQuestion').value.trim();
  const answer = document.getElementById('teachAnswer').value.trim();
  const result = document.getElementById('teachResult');

  if (!question || !answer) {
    result.innerText = "❌ Please provide both question and answer.";
    return;
  }

  const res = await fetch('/teach', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, answer })
  });

  const data = await res.json();
  result.innerText = data.message || "✅ Learned.";
  speak("Thanks, I have learned that.");
  document.getElementById('teachQuestion').value = "";
  document.getElementById('teachAnswer').value = "";
  pendingQuestion = null;
}

// === Speak ===
function speak(text, callback) {
  stopSpeaking();
  const msg = new SpeechSynthesisUtterance(text);
  msg.lang = 'en-US';
  currentUtterance = msg;
  isSpeaking = true;
  updateAskButton("Speaking...");
  synth.speak(msg);
  msg.onend = () => {
    isSpeaking = false;
    updateAskButton("Ask a Question");
    if (callback) callback();
  };
}
function stopSpeaking() {
  if (isSpeaking) {
    synth.cancel();
    isSpeaking = false;
    updateAskButton("Ask a Question");
  }
}
function cancelIfSpeaking() {
  if (isSpeaking) {
    stopSpeaking();
    return true;
  }
  return false;
}

// === Listen ===
function listenVoice(callback, duration = 8000) {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    alert("Speech recognition not supported.");
    return;
  }
  const recognition = new SpeechRecognition();
  recognition.lang = 'en-US';
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;
  let responded = false;

  recognition.onresult = (event) => {
    const transcript = event.results[0][0].transcript.trim();
    responded = true;
    callback(transcript);
  };
  recognition.onerror = () => {
    speak("Sorry, I didn't catch that.");
  };
  recognition.onend = () => {
    if (!responded) updateAskButton("Ask a Question");
  };

  recognition.start();
  setTimeout(() => {
    if (!responded) recognition.stop();
  }, duration);
}

// === Ask Button Label ===
function updateAskButton(label) {
  const btn = document.querySelector("button[onclick='startAsking()']");
  if (btn) btn.innerText = label;
}

// === Chat Functionality ===
function sendMessage() {
  const input = document.getElementById("chatInput");
  const message = input.value.trim();
  if (!message) return;

  addChatMessage("You", message);
  input.value = "";
  pendingQuestion = message;

  fetch("/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question: message,
      last_question: lastQuestion,
      last_answer: lastAnswer
    })
  })
    .then(res => res.json())
    .then(data => {
      lastQuestion = message;
      if (data.answer) {
        lastAnswer = data.answer;
        addChatMessage("Assistant", `${data.answer} (${data.source})`);
      } else {
        addChatMessage("Assistant", `❌ I don't know. <button onclick="searchNow(true)">Search</button> <button onclick="teachNow()">Teach</button>`);

      }
    });
}

// === Add Chat Message ===
function addChatMessage(sender, text) {
  const chatBox = document.getElementById("chatBox");
  const message = document.createElement("div");
  message.className = `message ${sender === "You" ? "user-msg" : "bot-msg"}`;
  message.innerHTML = `<strong>${sender}:</strong> ${text}`;
  chatBox.appendChild(message);
  chatBox.scrollTop = chatBox.scrollHeight;
}
