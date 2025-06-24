
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

      // ✅ Answer found
      if (data.answer) {
        document.getElementById('qaResult').innerText = `Answer: ${data.answer} (source: ${data.source})`;

        speak(`${data.answer}`, () => {
          // Add delay to ensure speak finishes before listen
          setTimeout(() => {
            speak("Do you want a different explanation? Say yes or no.", () => {
              setTimeout(() => {
                listenVoice(async (reply) => {
                  const response = reply.toLowerCase();

                  if (response.includes("yes i need")) {
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
                });
              }, 500); // Delay before listening
            });
          }, 500); // Delay after first speak
        });
      }

      // ❌ No answer found
      else if (data.needs_search) {
        speak("I don't know the answer. Say 'search' to find online, 'stop' to cancel, or tell me the answer directly.", () => {
          setTimeout(() => {
            listenVoice(async (response) => {
              const input = response.toLowerCase();

              if (input.includes("stop")) {
                speak("Okay, cancelled.");
                pendingQuestion = null;
                return;
              }

              if (input.includes("search")) {
                const searchRes = await fetch('/search-and-learn', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ question: pendingQuestion })
                });

                const result = await searchRes.json();

                if (result.answer) {
                  speak(`I found this answer: ${result.answer}`);
                  document.getElementById('qaResult').innerText = `Answer: ${result.answer} (from wiki)`;
                } else {
                  speak("Sorry, I couldn't find anything useful online.");
                }

                pendingQuestion = null;
              } else {
                await saveAnswer(pendingQuestion, response);
                speak("Thanks! I have learned the new answer.");
                document.getElementById('qaResult').innerText = `Learned: "${pendingQuestion}" → "${response}"`;
                pendingQuestion = null;
              }
            });
          }, 600); // Delay before listening
        });
      }
    });
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
    function listenVoice(callback) {
      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!SpeechRecognition) {
        alert("Your browser does not support speech recognition.");
        return;
      }

      const recognition = new SpeechRecognition();
      recognition.lang = 'en-US';
      recognition.interimResults = false;
      recognition.maxAlternatives = 1;

      recognition.start();
      recognition.onresult = (event) => {
        const transcript = event.results[0][0].transcript.trim();
        console.log(transcript)
        callback(transcript);
      };
      recognition.onerror = (event) => {
        console.error("Voice error:", event.error);
        speak("Sorry, I didn't catch that. Please try again.");
      };
    }
  