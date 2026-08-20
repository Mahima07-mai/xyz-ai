"""
The Conversation Orchestrator ("XYZ AI core"). Calls an OpenRouter-hosted
model with the tool schemas from tools.py and the persona for the caller's
VERIFIED role, then runs the standard tool-use loop: ask -> if the model
requests a tool -> run it through the Authorization layer -> feed the
(possibly denied) result back -> get the final natural-language answer.

OpenRouter (https://openrouter.ai) exposes an OpenAI-compatible
`/chat/completions` endpoint, so this module uses the `openai` SDK pointed
at OpenRouter's base URL rather than a Gemini-specific SDK.
"""
import json
import logging

from openai import OpenAI
from sqlalchemy.orm import Session

from .config import settings
from .model import AuditLog
from .personas import PERSONA_BY_ROLE, ROLES_WITH_WORKING_TOOLS
from .security import detect_injection_attempt, sanitize_reply
from .tools import TOOL_SCHEMAS, run_tool, ToolError

logger = logging.getLogger("xyz_ai.llm_client")

MAX_TOOL_ITERATIONS = 6

# --- Client Initialization ---
# OpenRouter speaks the OpenAI Chat Completions protocol, so the official
# `openai` client works unmodified -- only base_url + api_key change.
client = OpenAI(
    base_url=settings.OPENROUTER_BASE_URL,
    api_key=settings.OPENROUTER_API_KEY,
    default_headers={
        # Optional, OpenRouter-specific attribution headers (safe to omit,
        # but recommended so requests show up correctly on their dashboard).
        "HTTP-Referer": settings.OPENROUTER_SITE_URL,
        "X-Title": settings.OPENROUTER_APP_NAME,
    },
)


def hello_world_check() -> str:
    """The Day-1-morning 'get LLM API access working end-to-end' smoke
    test. Run via: python -m app.llm_client"""
    response = client.chat.completions.create(
        model=settings.OPENROUTER_MODEL,
        messages=[{"role": "user", "content": "Reply with exactly: XYZ AI backend is connected."}],
        max_tokens=50,
    )
    return response.choices[0].message.content


def _convert_schema_to_openai_tool(tool_schema: dict) -> dict:
    """Helper to convert the Anthropic-shaped JSON tool schemas in tools.py
    into OpenAI/OpenRouter-style `tools` entries."""
    return {
        "type": "function",
        "function": {
            "name": tool_schema["name"],
            "description": tool_schema["description"],
            "parameters": tool_schema.get("input_schema"),
        },
    }


def run_chat_turn(db: Session, caller: dict, conversation_history: list[dict], user_message: str) -> dict:
    """
    caller: {"id": str, "role": str, "name": str} -- from the verified JWT
        (auth.get_current_user()). "id" is a per-role string primary key
        (teacher_id/student_id/principal_id) or a UUID string (parent_id) --
        there is no single integer user_id under the Phase 2 schema.
    conversation_history: list of OpenAI-style message dicts
        ({"role": ..., "content": ...}, optionally with "tool_calls" /
        "tool_call_id" / "name") persisted from earlier turns in this session.
    user_message: the new message to answer.

    Returns {"reply": str, "conversation_history": list} so the caller can
    persist the updated history for the next turn.
    """
    # Non-blocking security heuristic (see security.py docstring for why
    # this doesn't block): just makes injection/extraction attempts
    # visible in the audit log for the Day 3 security test suite/demo.
    matched_pattern = detect_injection_attempt(user_message)
    if matched_pattern:
        logger.warning("Possible injection attempt from caller_id=%s: pattern=%r", caller["id"], matched_pattern)
        db.add(AuditLog(
            actor_id=str(caller["id"]),
            actor_role=caller["role"],
            tool_name="prompt_injection_heuristic",
            target_description=matched_pattern,
            allowed=True,  # flag only -- nothing was blocked at this layer
            detail="Heuristic match on incoming message; authorization layer still enforces normally.",
        ))
        db.commit()

    persona_prompt = PERSONA_BY_ROLE.get(caller["role"])
    if persona_prompt is None:
        return {
            "reply": "Your account role is not recognized. Please contact the school office.",
            "conversation_history": conversation_history,
        }

    tools_for_this_role = None
    if caller["role"] in ROLES_WITH_WORKING_TOOLS:
        tools_for_this_role = [_convert_schema_to_openai_tool(s) for s in TOOL_SCHEMAS]

    messages = [{"role": "system", "content": persona_prompt}]
    messages.extend(conversation_history)
    messages.append({"role": "user", "content": user_message})

    for _ in range(MAX_TOOL_ITERATIONS):
        create_kwargs = {
            "model": settings.OPENROUTER_MODEL,
            "messages": messages,
            "max_tokens": 1024,
        }
        if tools_for_this_role:
            create_kwargs["tools"] = tools_for_this_role

        response = client.chat.completions.create(**create_kwargs)
        message = response.choices[0].message

        if not message.tool_calls:
            # Model produced a final natural-language answer. Screen it
            # through the system-prompt-leak guard (security.py) BEFORE
            # it is persisted to history or returned -- so a leak never
            # re-enters the conversation as something the model "already
            # said" on a later turn either.
            final_text = sanitize_reply(message.content or "")
            messages.append({"role": "assistant", "content": final_text})

            # Drop the leading system prompt before persisting -- it's
            # re-added from personas.py on the next turn.
            history_out = messages[1:]
            return {"reply": final_text, "conversation_history": history_out}

        # Model wants to call one or more tools. Record the assistant's
        # tool-call message, then run each one through the Authorization
        # layer (tools.py) and feed back a matching "tool" message.
        messages.append({
            "role": "assistant",
            "content": message.content,
            "tool_calls": [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.function.name, "arguments": call.function.arguments},
                }
                for call in message.tool_calls
            ],
        })

        for call in message.tool_calls:
            try:
                tool_input = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                tool_input = {}

            try:
                result = run_tool(db, caller, call.function.name, tool_input)
                tool_result_content = json.dumps({"result": result})
            except ToolError as e:
                # Denied, invalid, and clarification-needed calls are all
                # returned to the model as a tool result too, so it can
                # explain the denial or ask the clarifying question
                # in-character, rather than guessing or retrying blindly.
                if e.options:
                    tool_result_content = json.dumps({
                        "clarification_needed": e.message,
                        "options": e.options,
                    })
                else:
                    tool_result_content = json.dumps({"error": f"DENIED: {e.message}"})

            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": tool_result_content,
            })

    return {
        "reply": "I'm having trouble completing that request right now. Please try rephrasing, or ask a school staff member for help.",
        "conversation_history": conversation_history,
    }


if __name__ == "__main__":
    print(hello_world_check())
