document.addEventListener("DOMContentLoaded", () => {
    const chatForm = document.getElementById("chat-form");
    const userInput = document.getElementById("user-input");
    const messagesContainer = document.getElementById("messages-container");
    const citationsContainer = document.getElementById("citations-container");
    const citationsList = document.getElementById("citations-list");
    const vectorCountDisplay = document.getElementById("vector-count");
    
    // Modal Elements
    const memoryModal = document.getElementById("memory-modal");
    const btnInspectMemory = document.getElementById("btn-inspect-memory");
    const closeModal = document.getElementById("close-modal");
    const modalBackdrop = document.getElementById("modal-backdrop");
    const shortTermJson = document.getElementById("short-term-memory-json");
    const userProfileDisplay = document.getElementById("user-profile-display");

    // Operations buttons
    const btnRunSpark = document.getElementById("btn-run-spark");
    const btnConsolidateMemory = document.getElementById("btn-consolidate-memory");

    const currentSessionId = "default_session";
    const currentUserId = "user_default";

    // 1. Fetch Initial Health & Metrics
    async function loadHealthMetrics() {
        try {
            const res = await fetch("/api/health");
            if (res.ok) {
                const data = await res.json();
                vectorCountDisplay.textContent = `${data.indexed_vectors} vectors`;
            }
        } catch (e) {
            console.error("Health check error:", e);
            vectorCountDisplay.textContent = "Offline";
        }
    }
    loadHealthMetrics();

    // 2. Chat Streaming Logic
    async function sendMessage(text) {
        if (!text || !text.trim()) return;

        // Append User Message
        appendMessage("user", text);
        userInput.value = "";
        citationsContainer.style.display = "none";
        citationsList.innerHTML = "";

        // Create Assistant Message Placeholder
        const assistantMsgEl = createAssistantMessageElement();
        messagesContainer.appendChild(assistantMsgEl);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;

        const contentEl = assistantMsgEl.querySelector(".message-content");

        try {
            const response = await fetch("/api/chat/stream", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    query: text,
                    session_id: currentSessionId,
                    user_id: currentUserId
                })
            });

            if (!response.ok) {
                contentEl.innerHTML = `<span style="color: #ef4444;">Error connecting to assistant server.</span>`;
                return;
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder("utf-8");
            let accumulatedText = "";

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;

                const chunk = decoder.decode(value, { stream: true });
                const lines = chunk.split("\n\n");

                for (const line of lines) {
                    if (line.startsWith("data: ")) {
                        try {
                            const payload = JSON.parse(line.replace("data: ", ""));
                            
                            if (payload.event === "metadata") {
                                renderCitations(payload.data.citations);
                            } else if (payload.event === "token") {
                                accumulatedText += payload.data;
                                contentEl.innerHTML = formatMarkdown(accumulatedText);
                                messagesContainer.scrollTop = messagesContainer.scrollHeight;
                            }
                        } catch (err) {
                            // Non-json chunk or partial
                        }
                    }
                }
            }
        } catch (err) {
            console.error("Stream error:", err);
            contentEl.innerHTML += `<br><span style="color: #ef4444;">[Stream disconnected]</span>`;
        }
    }

    function appendMessage(role, text) {
        const msgDiv = document.createElement("div");
        msgDiv.className = `message ${role}-message`;
        msgDiv.innerHTML = `
            <div class="message-content">
                <p>${escapeHtml(text)}</p>
            </div>
        `;
        messagesContainer.appendChild(msgDiv);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    function createAssistantMessageElement() {
        const msgDiv = document.createElement("div");
        msgDiv.className = "message assistant-message";
        msgDiv.innerHTML = `
            <div class="avatar">✨</div>
            <div class="message-content">
                <span class="pulse-dot"></span> Thinking and retrieving knowledge...
            </div>
        `;
        return msgDiv;
    }

    function renderCitations(citations) {
        if (!citations || citations.length === 0) {
            citationsContainer.style.display = "none";
            return;
        }

        citationsContainer.style.display = "block";
        citationsList.innerHTML = "";

        citations.forEach(c => {
            const chip = document.createElement("div");
            chip.className = "citation-chip";
            chip.innerHTML = `
                <div class="citation-chip-title">📌 ${c.doc_id}: ${c.doc_title}</div>
                <div class="citation-chip-snippet">${c.snippet}</div>
            `;
            citationsList.appendChild(chip);
        });
    }

    function formatMarkdown(text) {
        return text
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/`([^`]+)`/g, '<code style="background: rgba(255,255,255,0.1); padding: 2px 5px; border-radius: 4px; font-family: monospace;">$1</code>')
            .replace(/\n\n/g, '<br><br>')
            .replace(/\n- /g, '<br>• ');
    }

    function escapeHtml(unsafe) {
        return unsafe
             .replace(/&/g, "&amp;")
             .replace(/</g, "&lt;")
             .replace(/>/g, "&gt;");
    }

    // Chat Form Submit
    chatForm.addEventListener("submit", (e) => {
        e.preventDefault();
        const text = userInput.value;
        sendMessage(text);
    });

    // Quick Prompts
    document.querySelectorAll(".quick-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            const query = btn.getAttribute("data-query");
            userInput.value = query;
            sendMessage(query);
        });
    });

    // Run Spark Ingestion
    btnRunSpark.addEventListener("click", async () => {
        btnRunSpark.disabled = true;
        btnRunSpark.innerHTML = `<span class="pulse-dot"></span> Spark Ingestion Running...`;
        try {
            const res = await fetch("/api/ingest", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({})
            });
            const data = await res.json();
            alert(`⚡ Apache Spark Ingestion Complete!\nIndexed ${data.chunks_indexed} document chunks.`);
            loadHealthMetrics();
        } catch (e) {
            alert("Spark Ingestion Error: " + e.message);
        } finally {
            btnRunSpark.disabled = false;
            btnRunSpark.innerHTML = `<span class="icon">⚡</span> Run Spark Ingestion`;
        }
    });

    // Consolidate Memory via Spark
    btnConsolidateMemory.addEventListener("click", async () => {
        btnConsolidateMemory.disabled = true;
        btnConsolidateMemory.innerHTML = `<span class="pulse-dot"></span> Consolidating...`;
        try {
            const res = await fetch("/api/memory/consolidate", { method: "POST" });
            const data = await res.json();
            alert(`🧠 Spark Memory Consolidation Complete!\nUpdated ${data.users_consolidated} user profiles.`);
        } catch (e) {
            alert("Memory Consolidation Error: " + e.message);
        } finally {
            btnConsolidateMemory.disabled = false;
            btnConsolidateMemory.innerHTML = `<span class="icon">🧠</span> Consolidate Memory`;
        }
    });

    // Inspect Memory Modal
    btnInspectMemory.addEventListener("click", async () => {
        memoryModal.classList.add("active");
        shortTermJson.textContent = "Loading active memory...";
        userProfileDisplay.textContent = "Loading profile...";

        try {
            const res = await fetch(`/api/memory?session_id=${currentSessionId}&user_id=${currentUserId}`);
            const data = await res.json();
            shortTermJson.textContent = JSON.stringify(data.short_term_turns, null, 2);
            if (data.user_profile) {
                userProfileDisplay.innerHTML = `
                    <p><strong>Profile Summary:</strong> ${data.user_profile.profile_summary}</p>
                    <p style="margin-top: 6px;"><strong>Key Topics:</strong> ${data.user_profile.key_topics.join(", ")}</p>
                    <p style="margin-top: 6px;"><strong>Total Interactions:</strong> ${data.user_profile.interaction_count}</p>
                `;
            } else {
                userProfileDisplay.textContent = "No consolidated long-term profile yet. Engage in chat and run 'Consolidate Memory'!";
            }
        } catch (e) {
            shortTermJson.textContent = "Error loading memory state.";
        }
    });

    closeModal.addEventListener("click", () => memoryModal.classList.remove("active"));
    modalBackdrop.addEventListener("click", () => memoryModal.classList.remove("active"));
});
