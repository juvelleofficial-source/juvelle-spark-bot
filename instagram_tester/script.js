document.addEventListener('DOMContentLoaded', async () => {
    // Load Config with safe defaults
    let CONFIG = {
        webhook_url: "http://127.0.0.1:8000/webhook/instagram-test",
        health_url: "http://127.0.0.1:8000/api/health",
        burst_count: 5,
        user_profile: {
            username: "tester_01",
            avatar_url: "https://ui-avatars.com/api/?name=User&background=random"
        },
        bot_profile: {
            username: "Juvelle Support",
            avatar_url: "https://ui-avatars.com/api/?name=Juvelle&background=000&color=fff"
        }
    };

    try {
        const response = await fetch('config.json');
        if (response.ok) {
            const data = await response.json();
            CONFIG = { ...CONFIG, ...data };
        }
    } catch (e) {
        console.warn('Could not load config.json, using safe local defaults:', CONFIG.webhook_url);
    }

    // Session Continuity Management
    let currentSessionId = sessionStorage.getItem('juvelle_tester_session_id');
    if (!currentSessionId) {
        currentSessionId = 'tester_' + Math.floor(100000 + Math.random() * 900000);
        sessionStorage.setItem('juvelle_tester_session_id', currentSessionId);
    }

    // Elements
    const chatArea = document.getElementById('chatArea');
    const messageInput = document.getElementById('messageInput');
    const sendBtn = document.getElementById('sendBtn');
    const micBtn = document.getElementById('micBtn');
    const fileInput = document.getElementById('fileInput');
    const resetChatBtn = document.getElementById('resetChatBtn');
    const settingsBtn = document.getElementById('settingsBtn');
    const settingsModal = document.getElementById('settingsModal');
    const saveSettingsBtn = document.getElementById('saveSettingsBtn');
    const closeSettingsBtn = document.getElementById('closeSettingsBtn');
    const sendBurstBtn = document.getElementById('sendBurstBtn');
    const webhookUrlInput = document.getElementById('webhookUrlInput');
    const burstCountInput = document.getElementById('burstCount');
    const typingIndicator = document.getElementById('typingIndicator');

    // Reset Chat Button Handler
    if (resetChatBtn) {
        resetChatBtn.addEventListener('click', () => {
            currentSessionId = 'tester_' + Math.floor(100000 + Math.random() * 900000);
            sessionStorage.setItem('juvelle_tester_session_id', currentSessionId);
            const messages = chatArea.querySelectorAll('.message');
            messages.forEach(m => m.remove());
            console.log("Started fresh conversation session:", currentSessionId);
        });
    }

    // Connection Health Elements
    const connOverlay = document.getElementById('connOverlay');
    const connStatus = document.getElementById('connStatus');
    const connOfflineBox = document.getElementById('connOfflineBox');
    const connRetryBtn = document.getElementById('connRetryBtn');
    const headerActiveDot = document.getElementById('headerActiveDot');
    const headerStatusText = document.getElementById('headerStatusText');

    // Voice Elements
    const voiceOverlay = document.getElementById('voiceOverlay');
    const voiceTimer = document.getElementById('voiceTimer');
    let mediaRecorder;
    let audioChunks = [];
    let recordStartTime;
    let recordInterval;

    // Initialize inputs
    if (webhookUrlInput) webhookUrlInput.value = CONFIG.webhook_url;
    if (burstCountInput) burstCountInput.value = CONFIG.burst_count;

    // --- Backend Health Check & Auto-Connection Logic ---
    let healthPollInterval = null;
    let pollAttempts = 0;
    const MAX_ATTEMPTS = 12; // ~6 seconds

    async function checkBackendHealth() {
        try {
            const healthUrl = CONFIG.health_url || "http://127.0.0.1:8000/api/health";
            const res = await fetch(healthUrl, { method: 'GET', mode: 'cors' });
            if (res.ok) {
                const data = await res.json();
                if (data.status === "healthy" || data.status === "ok") {
                    onBackendConnected();
                    return true;
                }
            }
        } catch (e) {
            // Still starting or offline
        }
        return false;
    }

    function onBackendConnected() {
        if (healthPollInterval) clearInterval(healthPollInterval);
        if (connOverlay) {
            connOverlay.classList.add('connected');
            setTimeout(() => {
                connOverlay.style.display = 'none';
            }, 400);
        }
        if (headerActiveDot) headerActiveDot.classList.remove('offline');
        if (headerStatusText) headerStatusText.innerText = "Active now";
        console.log("Juvelle Backend Connected successfully!");
    }

    function onBackendOffline() {
        if (connStatus) connStatus.innerHTML = "<span>⚠️ Unable to reach backend</span>";
        if (connOfflineBox) connOfflineBox.classList.remove('hidden');
        if (connRetryBtn) connRetryBtn.classList.remove('hidden');
        if (connOverlay) connOverlay.style.display = 'flex';
        if (headerActiveDot) headerActiveDot.classList.add('offline');
        if (headerStatusText) headerStatusText.innerText = "Offline";
    }

    function startHealthPolling() {
        pollAttempts = 0;
        if (connStatus) connStatus.innerHTML = '<span class="conn-spinner"></span><span>Connecting to Juvelle Neural Engine...</span>';
        if (connOfflineBox) connOfflineBox.classList.add('hidden');
        if (connRetryBtn) connRetryBtn.classList.add('hidden');

        // Immediate first check
        checkBackendHealth().then(connected => {
            if (connected) return;

            healthPollInterval = setInterval(async () => {
                pollAttempts++;
                const isHealthy = await checkBackendHealth();
                if (isHealthy) {
                    clearInterval(healthPollInterval);
                } else if (pollAttempts >= MAX_ATTEMPTS) {
                    clearInterval(healthPollInterval);
                    onBackendOffline();
                }
            }, 600);
        });
    }

    if (connRetryBtn) {
        connRetryBtn.addEventListener('click', () => {
            startHealthPolling();
        });
    }

    // Start auto-connecting immediately
    startHealthPolling();

    // Background heartbeat every 15s to keep active dot synchronized
    setInterval(async () => {
        const isHealthy = await checkBackendHealth();
        if (!isHealthy) {
            if (headerActiveDot) headerActiveDot.classList.add('offline');
            if (headerStatusText) headerStatusText.innerText = "Reconnecting...";
        } else {
            if (headerActiveDot) headerActiveDot.classList.remove('offline');
            if (headerStatusText) headerStatusText.innerText = "Active now";
        }
    }, 15000);

    // --- Mode Toggle Logic ---
    const modeToggle = document.getElementById('modeToggle');
    const modeLabel = document.getElementById('modeLabel');
    const PUBLIC_WEBHOOK_URL = "http://127.0.0.1:8000/webhook/ed03d435-639b-4018-b0be-829891736771";
    let TEST_WEBHOOK_URL = CONFIG.webhook_url;

    if (modeToggle && modeLabel) {
        modeToggle.addEventListener('change', () => {
            if (modeToggle.checked) {
                TEST_WEBHOOK_URL = CONFIG.webhook_url;
                CONFIG.webhook_url = PUBLIC_WEBHOOK_URL;
                modeLabel.innerText = "Public";
                modeLabel.style.color = "#3797F0";
            } else {
                CONFIG.webhook_url = TEST_WEBHOOK_URL;
                modeLabel.innerText = "Test";
                modeLabel.style.color = "var(--text-primary)";
            }
            if (webhookUrlInput) webhookUrlInput.value = CONFIG.webhook_url;
            console.log(`Switched to ${modeLabel.innerText} Mode: ${CONFIG.webhook_url}`);
        });

        if (CONFIG.webhook_url === PUBLIC_WEBHOOK_URL) {
            modeToggle.checked = true;
            modeLabel.innerText = "Public";
            modeLabel.style.color = "#3797F0";
        }
    }

    // Typing Toggle
    messageInput.addEventListener('input', () => {
        if (messageInput.value.trim().length > 0) {
            sendBtn.classList.remove('hidden');
            sendBtn.innerText = 'Send';
            micBtn.classList.add('hidden');
        } else {
            sendBtn.classList.add('hidden');
            micBtn.classList.remove('hidden');
        }
    });

    // Send Message
    async function sendMessage(text = null, type = 'text', file = null) {
        let content = text || messageInput.value.trim();
        if (!content && !file) return;

        // UI: Add User Message
        addMessageToUI(content, 'sent', type, file);

        // Clear input
        if (type === 'text') {
            messageInput.value = '';
            sendBtn.classList.add('hidden');
            micBtn.classList.remove('hidden');
        }

        // Show typing indicator for bot
        showTyping(true);

        try {
            if (type === 'audio' && file) {
                // Route Voice Note to Dedicated Multimodal Endpoint
                const voiceEndpoint = "http://127.0.0.1:8000/api/voice-message";
                const formData = new FormData();
                formData.append('audio', file, 'voice_msg.webm');
                formData.append('sessionId', currentSessionId);
                formData.append('userName', CONFIG.user_profile.username);

                const res = await fetch(voiceEndpoint, {
                    method: 'POST',
                    body: formData
                });

                if (!res.ok) {
                    throw new Error(`Voice server error HTTP ${res.status}`);
                }

                const data = await res.json();
                showTyping(false);

                // Display transcribed reply
                if (data.reply_text) {
                    addMessageToUI(data.reply_text, 'received', 'text');
                }

                // If assistant returned a voice note playback
                if (data.has_audio_reply && data.audio_data) {
                    addMessageToUI(data.audio_data, 'received', 'audio_reply');
                }
                return;
            }

            let body;
            let headers = {};

            if (type === 'text') {
                headers['Content-Type'] = 'application/json';
                body = JSON.stringify({
                    chatInput: content,
                    sessionId: currentSessionId,
                    userId: currentSessionId
                });
            } else if (type === 'file') {
                const formData = new FormData();
                if (file) {
                    formData.append('file', file);
                }
                formData.append('chatInput', '[File Attachment]');
                formData.append('sessionId', currentSessionId);
                formData.append('userId', currentSessionId);
                body = formData;
            }

            const res = await fetch(CONFIG.webhook_url, {
                method: 'POST',
                headers: headers,
                body: body
            });

            if (!res.ok) {
                throw new Error(`Server returned HTTP ${res.status}: ${res.statusText}`);
            }

            const responseData = await res.json();
            showTyping(false);

            if (responseData.output) {
                if (Array.isArray(responseData.output)) {
                    responseData.output.forEach((msg, idx) => {
                        setTimeout(() => addMessageToUI(msg, 'received'), idx * 300);
                    });
                } else {
                    addMessageToUI(responseData.output, 'received');
                }
            } else if (Array.isArray(responseData)) {
                responseData.forEach(item => {
                    if (item.output) {
                        if (Array.isArray(item.output)) {
                            item.output.forEach(msg => addMessageToUI(msg, 'received'));
                        } else {
                            addMessageToUI(item.output, 'received');
                        }
                    } else {
                        addMessageToUI(JSON.stringify(item), 'received');
                    }
                });
            } else {
                addMessageToUI(JSON.stringify(responseData), 'received');
            }

        } catch (error) {
            showTyping(false);
            console.error(error);
            addMessageToUI("Error: " + error.message, 'received');
        }
    }

    sendBtn.addEventListener('click', () => sendMessage());

    messageInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendMessage();
    });

    // --- File Upload ---
    fileInput.addEventListener('change', (e) => {
        if (fileInput.files.length > 0) {
            Array.from(fileInput.files).forEach(file => {
                sendMessage(null, 'file', file);
            });
            fileInput.value = '';
        }
    });

    // --- Toast Notification Helper ---
    function showToast(message, isError = true, duration = 6000) {
        const toast = document.getElementById('toastNotification');
        const toastText = document.getElementById('toastText');
        const toastIcon = document.getElementById('toastIcon');
        const toastClose = document.getElementById('toastCloseBtn');
        if (!toast || !toastText) return;

        toastText.innerText = message;
        if (isError) {
            toast.classList.remove('success-toast');
            if (toastIcon) toastIcon.className = 'fa-solid fa-circle-exclamation toast-icon';
        } else {
            toast.classList.add('success-toast');
            if (toastIcon) toastIcon.className = 'fa-solid fa-circle-check toast-icon';
        }
        toast.classList.remove('hidden');

        if (toastClose) {
            toastClose.onclick = () => toast.classList.add('hidden');
        }
        setTimeout(() => {
            toast.classList.add('hidden');
        }, duration);
    }

    // --- Voice Recording State & Handlers ---
    let isDiscardingVoice = false;
    let voiceStream = null;

    const voiceCancelBtn = document.getElementById('voiceCancelBtn');
    const voiceSendBtn = document.getElementById('voiceSendBtn');
    const voiceActiveMicBtn = document.getElementById('voiceActiveMicBtn');

    async function startRecording() {
        if (mediaRecorder && mediaRecorder.state === "recording") {
            return;
        }

        try {
            if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                showToast("Microphone not supported in this browser. Please allow microphone permissions or use Chrome/Edge.", true);
                return;
            }

            isDiscardingVoice = false;
            voiceStream = await navigator.mediaDevices.getUserMedia({ audio: true });
            
            const recorderOptions = { mimeType: 'audio/webm;codecs=opus', audioBitsPerSecond: 128000 };
            try {
                mediaRecorder = new MediaRecorder(voiceStream, recorderOptions);
            } catch (e) {
                try {
                    mediaRecorder = new MediaRecorder(voiceStream, { mimeType: 'audio/webm' });
                } catch (e2) {
                    mediaRecorder = new MediaRecorder(voiceStream);
                }
            }

            audioChunks = [];
            mediaRecorder.ondataavailable = event => {
                if (event.data && event.data.size > 0) {
                    audioChunks.push(event.data);
                }
            };

            mediaRecorder.onstop = async () => {
                voiceOverlay.classList.add('hidden');
                clearInterval(recordInterval);
                if (voiceStream) {
                    voiceStream.getTracks().forEach(track => track.stop());
                    voiceStream = null;
                }

                if (!isDiscardingVoice && audioChunks.length > 0) {
                    const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
                    const audioFile = new File([audioBlob], "voice_msg.webm", { type: 'audio/webm' });
                    sendMessage(null, 'audio', audioFile);
                }
            };

            mediaRecorder.start(250);
            voiceOverlay.classList.remove('hidden');
            if (voiceTimer) voiceTimer.innerText = "0:00";
            recordStartTime = Date.now();
            recordInterval = setInterval(() => {
                const diff = Math.floor((Date.now() - recordStartTime) / 1000);
                const mins = Math.floor(diff / 60);
                const secs = diff % 60;
                if (voiceTimer) voiceTimer.innerText = `${mins}:${secs.toString().padStart(2, '0')}`;
            }, 1000);

        } catch (err) {
            console.warn("Mic Error:", err);
            voiceOverlay.classList.add('hidden');
            showToast("🎙️ Mic permission needed. Click the lock/mic icon in the address bar to Allow Microphone.", true, 7000);
        }
    }

    function stopAndSendRecording() {
        isDiscardingVoice = false;
        if (mediaRecorder && mediaRecorder.state === "recording") {
            mediaRecorder.stop();
        }
    }

    function cancelRecording() {
        isDiscardingVoice = true;
        if (mediaRecorder && mediaRecorder.state === "recording") {
            mediaRecorder.stop();
        } else {
            voiceOverlay.classList.add('hidden');
            clearInterval(recordInterval);
            if (voiceStream) {
                voiceStream.getTracks().forEach(track => track.stop());
                voiceStream = null;
            }
        }
        showToast("Voice recording cancelled.", false, 2500);
    }

    // Tap or click mic button to start recording
    micBtn.addEventListener('click', startRecording);

    // Cancel Button click
    if (voiceCancelBtn) {
        voiceCancelBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            cancelRecording();
        });
    }

    // Send Button click
    if (voiceSendBtn) {
        voiceSendBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            stopAndSendRecording();
        });
    }

    // Active Center Mic Button click (also sends)
    if (voiceActiveMicBtn) {
        voiceActiveMicBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            stopAndSendRecording();
        });
    }

    // Global Key listener for recording: Escape to Cancel, Enter to Send
    document.addEventListener('keydown', (e) => {
        if (!voiceOverlay.classList.contains('hidden')) {
            if (e.key === 'Escape') {
                cancelRecording();
            } else if (e.key === 'Enter') {
                stopAndSendRecording();
            }
        }
    });

    // --- Helper to append messages to UI ---
    function addMessageToUI(content, direction = 'sent', msgType = 'text', file = null) {
        const msgDiv = document.createElement('div');
        msgDiv.classList.add('message', direction);

        let innerHTML = '';

        if (direction === 'received') {
            innerHTML += `<div class="avatar">J</div>`;
        }

        innerHTML += `<div class="message-content">`;

        if (msgType === 'text') {
            innerHTML += content;
        } else if (msgType === 'file' && file) {
            if (file.type.startsWith('image/')) {
                const url = URL.createObjectURL(file);
                innerHTML += `<img src="${url}" class="message-image" onload="URL.revokeObjectURL(this.src)">`;
            } else if (file.type.startsWith('video/')) {
                const url = URL.createObjectURL(file);
                innerHTML += `<video src="${url}" class="message-image" controls></video>`;
            } else {
                innerHTML += `📁 ${file.name}`;
            }
        } else if (msgType === 'audio') {
            const url = file ? URL.createObjectURL(file) : null;
            innerHTML += `
                <div class="voice-msg-player">
                    <button class="voice-play-btn" onclick="const a = new Audio('${url}'); a.play();">▶</button>
                    <div class="voice-wave-bars"><span></span><span></span><span></span><span></span><span></span><span></span><span></span></div>
                    <span style="font-size: 11px; opacity: 0.8;">Voice Note</span>
                </div>
            `;
        } else if (msgType === 'audio_reply') {
            innerHTML += `
                <div class="voice-msg-player">
                    <button class="voice-play-btn" onclick="const a = new Audio('${content}'); a.play();">▶</button>
                    <div class="voice-wave-bars"><span></span><span></span><span></span><span></span><span></span><span></span><span></span></div>
                    <span style="font-size: 11px; opacity: 0.8;">Juvelle Voice</span>
                </div>
            `;
        }

        innerHTML += `</div>`;
        msgDiv.innerHTML = innerHTML;

        chatArea.insertBefore(msgDiv, typingIndicator);
        chatArea.scrollTop = chatArea.scrollHeight;
    }

    function showTyping(show) {
        if (show) {
            typingIndicator.classList.remove('hidden');
            chatArea.scrollTop = chatArea.scrollHeight;
        } else {
            typingIndicator.classList.add('hidden');
        }
    }

    // --- DIRECT GEMINI SPARK LIVE CONTROLLER ---
    class LiveCallController {
        constructor() {
            this.callBtn = document.getElementById('callBtn');
            this.callOverlay = document.getElementById('callOverlay');
            this.init();
        }

        init() {
            if (this.callBtn) {
                this.callBtn.addEventListener('click', (e) => {
                    e.preventDefault();
                    this.openGeminiSparkLive();
                });
            }
        }

        openGeminiSparkLive() {
            showToast("✨ Opening Gemini Spark Live Voice Assistant...", false, 3500);
            const sparkUrl = "https://gemini.google.com/";
            const windowFeatures = "width=480,height=720,menubar=no,toolbar=no,location=no,status=no,resizable=yes,scrollbars=yes";
            try {
                const liveWindow = window.open(sparkUrl, "GeminiSparkLive", windowFeatures);
                if (!liveWindow || liveWindow.closed || typeof liveWindow.closed === 'undefined') {
                    window.open(sparkUrl, "_blank");
                }
            } catch (err) {
                window.open(sparkUrl, "_blank");
            }
        }
    }

    // Initialize Call Controller
    const callController = new LiveCallController();

    // --- Settings & Burst Mode ---
    if (settingsBtn && settingsModal) {
        settingsBtn.addEventListener('click', () => settingsModal.classList.remove('hidden'));
        if (closeSettingsBtn) closeSettingsBtn.addEventListener('click', () => settingsModal.classList.add('hidden'));

        if (saveSettingsBtn) {
            saveSettingsBtn.addEventListener('click', () => {
                CONFIG.webhook_url = webhookUrlInput.value;
                CONFIG.burst_count = parseInt(burstCountInput.value);
                settingsModal.classList.add('hidden');
                alert("Settings saved: " + CONFIG.webhook_url);
            });
        }
    }

    if (sendBurstBtn) {
        sendBurstBtn.addEventListener('click', async () => {
            const count = CONFIG.burst_count || 5;
            const baseMsg = "Burst Test Message ";
            if (settingsModal) settingsModal.classList.add('hidden');

            for (let i = 1; i <= count; i++) {
                sendMessage(`${baseMsg} ${i}`);
                await new Promise(r => setTimeout(r, 300));
            }
        });
    }
});
