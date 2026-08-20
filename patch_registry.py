import sys

filename = "mcp_server/tools_registry.py"
with open(filename, "r") as f:
    content = f.read()

# Add the new tool to MCP_TOOLS_MANIFEST
new_tool_json = """    {
        "name": "transcribe_audio_url",
        "description": "Downloads and transcribes an audio voice note from a URL. Returns the exact transcribed text in the spoken language.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "audio_url": {
                    "type": "string",
                    "description": "The URL of the audio file to transcribe."
                }
            },
            "required": ["audio_url"]
        }
    },
"""

content = content.replace("MCP_TOOLS_MANIFEST = [", "MCP_TOOLS_MANIFEST = [\n" + new_tool_json)

# Add the implementation logic to execute_mcp_tool
new_impl = """
    elif tool_name == "transcribe_audio_url":
        audio_url = arguments.get("audio_url")
        if not audio_url:
            return {"error": "audio_url is required"}
            
        try:
            from core.audio_processor import download_audio_bytes, transcribe_and_understand_voice_note
            audio_data, mime = download_audio_bytes(audio_url)
            if audio_data:
                transcript = transcribe_and_understand_voice_note(audio_data, mime)
                return {
                    "audio_url": audio_url,
                    "transcript": transcript,
                    "status": "success" if transcript else "failed_transcription"
                }
            else:
                return {"error": "Could not download audio from URL"}
        except Exception as e:
            return {"error": str(e)}
"""

content = content.replace("    else:\n        return {\"error\": f\"Unknown tool: {tool_name}\"}", new_impl + "\n    else:\n        return {\"error\": f\"Unknown tool: {tool_name}\"}")

# Also update the description of get_pending_facebook_messages to indicate using the transcribe tool
content = content.replace(
    "Returns text messages as well as audio_url for customer voice notes so Gemini Spark can listen and transcribe natively with zero API keys.",
    "Returns text messages as well as audio_url for customer voice notes. For voice notes, use the transcribe_audio_url tool to transcribe the audio_url."
)

with open(filename, "w") as f:
    f.write(content)
print("Updated tools_registry.py")
