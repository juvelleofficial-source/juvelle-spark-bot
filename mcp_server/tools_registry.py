import logging
from typing import List, Dict, Any
from mcp_server.message_queue import (
    get_pending_messages,
    mark_message_replied,
    save_crm_note
)
from mcp_server.meta_client import send_meta_graph_reply
from retrieval.vector_retriever import retrieve_hybrid_context

logger = logging.getLogger(__name__)

# MCP Tools Schema Specification (JSON Schema compliant for Gemini Spark)
MCP_TOOLS_MANIFEST = [
    {
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

    {
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

    {
        "name": "get_pending_facebook_messages",
        "description": "Retrieves pending incoming customer messages received from Facebook Messenger, WhatsApp, or Instagram via Webhooks that require an AI response. Returns text messages as well as audio_url for customer voice notes. For voice notes, use the transcribe_audio_url tool to transcribe the audio_url.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of messages to fetch (default: 5)",
                    "default": 5
                }
            }
        }
    },
    {
        "name": "search_knowledge_base",
        "description": "Performs a hybrid semantic and keyword search across internal enterprise documents and policies to ground AI answers in accurate facts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query or topic to look up in the enterprise knowledge base."
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of relevant chunks to retrieve (default: 3)",
                    "default": 3
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "send_facebook_reply",
        "description": "Dispatches an AI-generated grounded reply back to the customer via Meta Graph API and marks the message as resolved in the queue.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "message_id": {
                    "type": "string",
                    "description": "The unique message_id of the inquiry from get_pending_facebook_messages."
                },
                "recipient_id": {
                    "type": "string",
                    "description": "The sender_id of the customer on Facebook/WhatsApp."
                },
                "reply_text": {
                    "type": "string",
                    "description": "The helpful, grounded response message to send to the customer."
                }
            },
            "required": ["message_id", "recipient_id", "reply_text"]
        }
    },
    {
        "name": "save_customer_note",
        "description": "Saves customer preferences, order inquiries, or important CRM context into long-term memory for future conversations.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sender_id": {
                    "type": "string",
                    "description": "The customer's unique ID."
                },
                "customer_name": {
                    "type": "string",
                    "description": "Customer name if known."
                },
                "notes": {
                    "type": "string",
                    "description": "Key facts or preferences learned during conversation."
                }
            },
            "required": ["sender_id", "notes"]
        }
    }
]

def execute_mcp_tool(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Executes the requested MCP tool and returns the structured result."""
    logger.info(f"Executing MCP Tool '{tool_name}' with args: {arguments}")

    if tool_name == "get_pending_facebook_messages":
        limit = arguments.get("limit", 5)
        messages = get_pending_messages(limit=limit)
        return {
            "total_pending": len(messages),
            "messages": messages
        }

    elif tool_name == "search_knowledge_base":
        query = arguments.get("query", "")
        top_k = arguments.get("top_k", 3)
        chunks = retrieve_hybrid_context(query=query, top_k=top_k)
        formatted_chunks = [
            {
                "doc_id": c["doc_id"],
                "doc_title": c["doc_title"],
                "content": c["content"],
                "score": round(float(c.get("score", c.get("rrf_score", 0.0))), 3)
            }
            for c in chunks
        ]
        return {
            "query": query,
            "results_count": len(formatted_chunks),
            "results": formatted_chunks
        }

    elif tool_name == "send_facebook_reply":
        msg_id = arguments.get("message_id")
        recipient_id = arguments.get("recipient_id")
        reply_text = arguments.get("reply_text")

        # 1. Dispatch via Meta Graph API
        dispatch_result = send_meta_graph_reply(recipient_id=recipient_id, message_text=reply_text)
        
        # 2. Update queue status
        if msg_id:
            mark_message_replied(message_id=msg_id, ai_reply=reply_text)

        return {
            "status": "delivered",
            "message_id": msg_id,
            "recipient_id": recipient_id,
            "dispatch_info": dispatch_result
        }

    elif tool_name == "save_crm_note":
        sender_id = arguments.get("sender_id")
        customer_name = arguments.get("customer_name", "Valued Customer")
        notes = arguments.get("notes")
        save_crm_note(sender_id=sender_id, customer_name=customer_name, profile_notes=notes)
        return {
            "status": "saved",
            "sender_id": sender_id,
            "message": "Customer profile note persisted successfully."
        }


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

    else:
        return {"error": f"Unknown tool: {tool_name}"}
