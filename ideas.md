# Project Ideas & Future Expansions: Zero-Cost Voice AI

---

## 1. Zero-Cost Instagram Voice Calling Agent (Powered by Gemini Spark)

### Core Principle: The "Zero API Cost" Gemini Spark Engine
- **No Paid APIs**: Completely avoids paid APIs (like Gemini Live API or OpenAI Realtime API) that charge per audio token or require billing credits.
- **Autonomous Gemini Spark**: Leverages the free autonomous reasoning engine directly inside Google's cloud ecosystem at `gemini.google.com` via Model Context Protocol (**MCP**).
- **Free Audio Pipeline**: Combines free local/browser speech processing with Gemini Spark's native intelligence.

---

## 2. Voice Calling System Architecture

```
[ Customer Audio on Instagram ]
             │
             ▼
[ Free Audio Capture (WebRTC / Web Audio API) ]
             │
             ▼
[ Free Fast STT (Edge-STT / Local Whisper / Browser Speech API) ]
             │
             ▼
[ Model Context Protocol (MCP) Message Queue ]
             │
             ▼
[ Google Gemini Spark Autonomous Agent (gemini.google.com) ]
  • 100% Free Cloud Compute & Reasoning
  • Zero API Keys Required
  • Grounded with Juvelle Boutique Knowledge Base
             │
             ▼
[ Free High-Speed TTS (Edge-TTS / Kokoro / Web Speech Synthesis) ]
             │
             ▼
[ Real-Time Voice Output to Customer (Instagram Call / WebRTC Stream) ]
```

---

## 3. Implementation Approaches

### Approach A: Live Web Audio Call in Instagram DMs (Recommended)
- **Workflow**:
  - Customer asks for voice assistance in Instagram DM or clicks call.
  - The bot automatically sends a one-click live call link in chat.
  - Customer taps the link to open an in-app WebRTC voice room with zero lag and instant interruptions.
- **Why It's Superior**:
  - 100% free from any phone number or Twilio charges.
  - Completely safe from Instagram session restrictions or account bans.

### Approach B: Direct Instagram Web Auto-Answer & Virtual Audio Cable
- **Workflow**:
  - A headless browser session runs on PC logged into Instagram Web (`/direct/inbox`).
  - An automation script auto-clicks **"Accept Call"** on incoming Instagram Direct calls.
  - **VB-Audio Virtual Cable** routes call speaker audio into the free transcription pipeline.
  - Gemini Spark generates the response, which is converted to speech and fed into the virtual microphone.

---

## 4. Next Steps for Implementation
1. Integrate free **Edge-TTS / Kokoro** local voice synthesis into the MCP server.
2. Build the lightweight WebRTC browser audio room for one-click calling from Instagram DMs.
3. Wire the real-time audio transcript directly into `mcp_inbox.db` for Gemini Spark autonomous resolution.
