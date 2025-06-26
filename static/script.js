// === Global State ===
let pendingQuestion = null;
let lastQuestion = null;
let lastAnswer = null;
let isSpeaking = false;
let synth = window.speechSynthesis;
let currentUtterance = null;
let isExpectingTeachingAnswer = false;

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


  async function submitTeaching() {
    const question = document.getElementById("teachQuestion").value.trim();
    const answer = document.getElementById("teachAnswer").value.trim();
    const resultBox = document.getElementById("teachResult");

    if (!question || !answer) {
      resultBox.textContent = "❌ Both question and answer are required.";
      resultBox.style.color = "red";
      return;
    }

    try {
      const response = await fetch("/teach", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ question, answer })
      });

      const data = await response.json();

      if (response.ok) {
        resultBox.textContent = data.message || "✅ Taught successfully!";
        resultBox.style.color = "green";
        // Optional: clear inputs after success
        document.getElementById("teachQuestion").value = "";
        document.getElementById("teachAnswer").value = "";
      } else {
        resultBox.textContent = data.error || "❌ Failed to teach.";
        resultBox.style.color = "red";
      }

    } catch (error) {
      console.error("Error:", error);
      resultBox.textContent = "❌ Something went wrong.";
      resultBox.style.color = "red";
    }
  }



async function startVoicePrediction() {
  if (cancelIfSpeaking()) return;

  const btn = document.querySelector("button[onclick='startVoicePrediction()']");
  if (btn) btn.innerText = "Speaking...";

  speak("Please say the fruit name.", () => {
    if (btn) btn.innerText = "Listening...";

    listenVoice(
      async (spokenText) => {
        if (btn) btn.innerText = "Predicting...";
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

        if (btn) btn.innerText = "Start Voice Prediction";
      },
      8000,
      () => {
        // ✅ Called when user says nothing
        if (btn) btn.innerText = "Start Voice Prediction";
      }
    );
  });
}



// === Start Asking via Voice ===
async function startAsking() {
  if (cancelIfSpeaking()) return;
  updateAskButton("Listening...");
  speak("Please ask your question.", () => {
    listenVoice(handleAsk);
  });
}

// === Handle Ask (Shared for Voice & Chat) ===
async function handleAsk(question, fromChat = false) {
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
  lastQuestion = question;

  if (data.source === "skip") return;

  if (data.source === "correction") {
    isExpectingTeachingAnswer = true;
    if (fromChat) {
      addChatMessage("Assistant", "❌ That may be wrong. Please provide the correct answer.");
    } else {
      document.getElementById('qaResult').innerHTML = `❌ That may be incorrect. Please tell me the correct answer.`;
      speak("Oops! Please tell me the correct answer so I can learn it.");
    }
    return;
  }

  if (data.source === "learned") {
    if (fromChat) {
      addChatMessage("Assistant", data.answer || "✅ Learned successfully.");
    } else {
      document.getElementById('qaResult').innerHTML = `✅ Thanks! I've learned that.`;
      speak("Thanks! I’ve updated my knowledge.");
    }
    return;
  }

  if (data.answer) {
    lastAnswer = data.answer;
    if (fromChat) {
      addChatMessage("Assistant", `${data.answer} (${data.source})`);
    } else {
      document.getElementById('qaResult').innerHTML = `Answer: ${data.answer} (${data.source})`;
      speak(data.answer);
    }
  } else {
    if (fromChat) {
      addChatMessage("Assistant", `❌ I don't know. <button id="searchButton" onclick="searchNow(true)">Search</button> <button onclick="teachNow(true)">Teach</button>`);
    } else {
      document.getElementById('qaResult').innerHTML = `
        <p>❌ I don't know the answer.</p>
        <button onclick="searchNow()">🔍 Search</button>
        <button onclick="teachNow()">✏️ Teach</button>
      `;
      speak("I don't know the answer. You can search or teach me.");
    }
  }
  updateAskButton("Ask a Question");
}

// === Unified Search Now ===
async function searchNow(fromChat = false) {
  if (!pendingQuestion) return;

  const btn = document.getElementById("searchButton");
  if (btn) btn.innerText = "Searching...";

  const expandPhrases = ["describe more", "more details", "explain more", "expand"];
  const isExpand = expandPhrases.includes(pendingQuestion.toLowerCase());
  const searchQuery = isExpand && lastQuestion ? lastQuestion : pendingQuestion;

  try {
    const res = await fetch('/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: searchQuery, last_question: lastQuestion })
    });
    const data = await res.json();

    if (data.answer) {
      const responseText = `${data.answer} (${data.source})`;
      if (fromChat) {
        addChatMessage("Assistant", responseText);
      } else {
        document.getElementById('qaResult').innerHTML = `🔍 Found on Wiki: ${data.answer}`;
        speak(data.answer);
      }
    } else {
      const msg = "❌ Still couldn't find the answer.";
      if (fromChat) {
        addChatMessage("Assistant", msg);
      } else {
        document.getElementById('qaResult').innerHTML = msg;
        speak("Sorry, I still couldn't find the answer.");
      }
    }
  } catch (e) {
    console.error("Search error:", e);
  } finally {
    if (btn) btn.innerText = "Search"; // Always reset
  }
}


// === Unified Teach Now ===
async function teachNow(fromChat = false) {
  if (!pendingQuestion) return;

  if (fromChat) {
    isExpectingTeachingAnswer = true;
    addChatMessage("Assistant", `✏️ Please type the correct answer for: "${pendingQuestion}"`);
  } else {
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

// === Chat Message Sender ===
function sendMessage() {
  const input = document.getElementById("chatInput");
  const message = input.value.trim();
  if (!message) return;
  addChatMessage("You", message);
  input.value = "";

  if (isExpectingTeachingAnswer && pendingQuestion) {
    isExpectingTeachingAnswer = false;
    fetch("/teach", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: pendingQuestion, answer: message })
    })
      .then(res => res.json())
      .then(data => {
        addChatMessage("Assistant", `✅ Learned: "${pendingQuestion}" → "${message}"`);
        pendingQuestion = null;
      })
      .catch(err => {
        console.error("Teach error:", err);
        addChatMessage("Assistant", "⚠️ Failed to teach. Try again.");
      });
    return;
  }

  handleAsk(message, true);
}

// === Utilities ===
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

function listenVoice(callback, duration = 8000, onEnd = null) {
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
    callback(transcript); // 🗣️ Text returned to handler
  };

  recognition.onerror = () => {
    speak("Sorry, I didn't catch that.");
  };

  recognition.onend = () => {
    if (!responded && typeof onEnd === "function") onEnd(); // ✅ Reset button if nothing heard
  };

  recognition.start();

  setTimeout(() => {
    if (!responded) {
      recognition.stop();
      if (typeof onEnd === "function") onEnd(); // ✅ Reset if timeout stops listening
    }
  }, duration);
}


function updateAskButton(label) {
  const btn = document.querySelector("button[onclick='startAsking()']");
  if (btn) btn.innerText = label;
}

function addChatMessage(sender, text) {
  const chatBox = document.getElementById("chatBox");
  const message = document.createElement("div");
  message.className = `message ${sender === "You" ? "user-msg" : "bot-msg"}`;
  message.innerHTML = `<strong>${sender}:</strong> ${text}`;
  chatBox.appendChild(message);
  chatBox.scrollTop = chatBox.scrollHeight;
}
