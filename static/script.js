let pendingQuestion = null;

// Upload Fruit
const uploadForm = document.getElementById('uploadForm');
uploadForm.onsubmit = async (e) => {
  e.preventDefault();
  const formData = new FormData(uploadForm);
  const res = await fetch('/add-fruit', { method: 'POST', body: formData });
  const data = await res.json();
  document.getElementById('uploadResult').innerHTML = data.error
    ? `<p style="color:red">${data.error}</p>`
    : `<p style="color:green">${data.message}</p><img src="${data.image_url}" />`;
};

// Predict Fruit via Voice
async function startVoicePrediction() {
  speak("Please say the fruit name.", () => {
    listenVoice(async (spokenText) => {
      const res = await fetch('/predict', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: spokenText })
      });
      const data = await res.json();
      if (data.error) {
        speak("Sorry, I could not recognize the fruit.");
        document.getElementById('predictResult').innerHTML = `<p style="color:red">${data.error}</p>`;
      } else {
        speak(`It looks like ${data.prediction}`);
        document.getElementById('predictResult').innerHTML = `
          <p style="color:blue">Prediction: ${data.prediction}</p>
          <img src="${data.image_url}" />
        `;
      }
    });
  });
}

// Ask via Voice
async function startAsking() {
  speak("Please ask your question.", () => {
    listenVoice(async (question) => {
      pendingQuestion = question;

      const res = await fetch('/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question })
      });

      const data = await res.json();

      if (data.answer) {
        document.getElementById('qaResult').innerText = `Answer: ${data.answer} (source: ${data.source})`;

        speak(`${data.answer}`, () => {
          setTimeout(() => {
            speak("Do you want a different explanation? Say yes or no.", () => {
              setTimeout(() => {
                listenVoice(async (reply) => {
                  const response = reply.toLowerCase();

                  if (response.includes("yes")) {
                    const regenRes = await fetch('/regenerate-answer', {
                      method: 'POST',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({ question: pendingQuestion, exclude: data.answer })
                    });

                    const regenData = await regenRes.json();

                    if (regenData.answer && regenData.answer !== data.answer) {
                      speak(`Here is another explanation: ${regenData.answer}`);
                      document.getElementById('qaResult').innerText = `Alternate Answer: ${regenData.answer} (regenerated)`;
                    } else {
                      speak("Sorry, I couldn't find a different explanation.");
                    }
                  } else {
                    speak("Okay.");
                  }
                }, 8000);
              }, 1000);
            });
          }, 1000);
        });
      }

      else {
        speak("I don't know the answer. You can tell me or say stop.", () => {
          setTimeout(() => {
            listenVoice(async (response) => {
              const input = response.toLowerCase();

              if (input.includes("stop")) {
                speak("Okay, cancelled.");
                pendingQuestion = null;
                return;
              }

              await saveAnswer(pendingQuestion, response);
              speak("Thanks! I have learned the new answer.");
              document.getElementById('qaResult').innerText = `Learned: "${pendingQuestion}" → "${response}"`;
              pendingQuestion = null;
            }, 10000);
          }, 1000);
        });
      }
    }, 8000);
  });
}

// Teach Answer
async function startTeaching() {
  if (!pendingQuestion) {
    speak("Say the question you want to teach.", () => {
      listenVoice((question) => {
        pendingQuestion = question;
        speak("Now say the answer.", () => {
          listenVoice((answer) => saveAnswer(pendingQuestion, answer));
        });
      });
    });
  } else {
    speak("Say the answer for your earlier question.", () => {
      listenVoice((answer) => saveAnswer(pendingQuestion, answer));
    });
  }
}

async function saveAnswer(question, answer) {
  const res = await fetch('/teach', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, answer })
  });
  const data = await res.json();
  speak("Answer saved successfully.");
  document.getElementById('qaResult').innerText = data.message || "Learned.";
  pendingQuestion = null;
}

// Speak
function speak(text, callback) {
  const msg = new SpeechSynthesisUtterance(text);
  msg.lang = 'en-US';
  speechSynthesis.speak(msg);
  msg.onend = () => {
    if (callback) callback();
  };
}

// Listen
function listenVoice(callback, duration = 8000) {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    alert("Your browser does not support speech recognition.");
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

  recognition.onerror = (event) => {
    console.error("Voice error:", event.error);
    speak("Sorry, I didn't catch that. Please try again.");
  };

  recognition.start();

  setTimeout(() => {
    if (!responded) recognition.stop();
  }, duration);
}

//
// 🧠 Chat Interface
//

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
    body: JSON.stringify({ question: message })
  })
    .then(res => res.json())
    .then(async data => {
      if (data.answer) {
        addChatMessage("Assistant", `${data.answer} (${data.source})`);
      } else {
        addChatMessage("Assistant", "I don't know. Please teach me.");
        const userAnswer = await promptAnswer();
        if (userAnswer) {
          await saveAnswer(message, userAnswer);
          addChatMessage("Assistant", "Thanks! I have learned it.");
        }
      }
    })
    .catch(err => {
      console.error(err);
      addChatMessage("Assistant", "⚠️ Server error.");
    });
}

function addChatMessage(sender, text) {
  const chatBox = document.getElementById("chatBox");
  const message = document.createElement("div");
  message.style.margin = "8px 0";
  message.style.padding = "8px 12px";
  message.style.borderRadius = "10px";
  message.style.maxWidth = "80%";
  message.style.wordWrap = "break-word";
  message.style.background = sender === "You" ? "#d1e7ff" : "#e2e3e5";
  message.innerHTML = `<strong>${sender}:</strong> ${text}`;
  message.style.alignSelf = sender === "You" ? "flex-end" : "flex-start";

  chatBox.appendChild(message);
  chatBox.scrollTop = chatBox.scrollHeight;
}

async function promptAnswer() {
  return new Promise((resolve) => {
    const reply = prompt("Please type the answer to teach me:");
    resolve(reply && reply.trim() ? reply.trim() : null);
  });
}
