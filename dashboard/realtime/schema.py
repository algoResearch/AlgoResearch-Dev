# dashboard/realtime/schema.py
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field, validator

# ---------------------------------------------------------------------
# Client -> Server (incoming over WebSocket)
# ---------------------------------------------------------------------

class _BaseIncoming(BaseModel):
    type: str


class ClientMessageSend(_BaseIncoming):
    """
    { "type": "message",
      "message": "hello",
      "message_client_id": "uuid-optional",
      "attachment": {...}  # optional, if you support it
    }
    """
    type: Literal["message"]
    message: Optional[str] = None
    message_client_id: Optional[str] = Field(None, alias="message_client_id")
    attachment: Optional[Dict[str, Any]] = None  # keep flexible


class ClientEditMessage(_BaseIncoming):
    """
    { "type": "edit_message",
      "message_id": 123,
      "content": "new text"
    }
    """
    type: Literal["edit_message"]
    message_id: int
    content: str


class ClientTyping(_BaseIncoming):
    """
    { "type": "typing",
      "is_typing": true
    }
    """
    type: Literal["typing"]
    is_typing: bool


class ClientUnsupported(_BaseIncoming):
    """Fallback for unknown types (lets us return a structured error)."""
    pass


IncomingEvent = Union[ClientMessageSend, ClientEditMessage, ClientTyping, ClientUnsupported]


def parse_incoming(payload: Dict[str, Any]) -> IncomingEvent:
    """
    Safe parser for incoming WS JSON.
    Returns a validated model. Unknown `type` -> ClientUnsupported.
    """
    t = payload.get("type")
    try:
        if t == "message":
            return ClientMessageSend.parse_obj(payload)
        if t == "edit_message":
            return ClientEditMessage.parse_obj(payload)
        if t == "typing":
            return ClientTyping.parse_obj(payload)
        # default fallback
        return ClientUnsupported.parse_obj(payload)
    except Exception:
        # If validation fails, still surface a structured 'unsupported'
        return ClientUnsupported(type=str(t) if t else "unknown")


# ---------------------------------------------------------------------
# Server -> Client (outgoing frames)
#   These are exactly what ChatConsumer sends via send_json(...)
# ---------------------------------------------------------------------

class _BaseFrame(BaseModel):
    type: str


class ChatMessageFrame(_BaseFrame):
    """
    {
      "type": "chat_message",
      "id": 1029,
      "message": "hello",
      "sender_username": "Rc10283",
      "sender_full_name": "Ryan Christopher",
      "sender_profile_picture": "/media/...",
      "timestamp": "2025-10-15T15:20:43.932991+00:00",
      "timestamp_display": "Oct 15, 2025 03:20 PM",
      "is_edited": false,
      "attachment_url": "",
      "attachment_type": "",
      "thumbnail_url": ""
    }
    """
    type: Literal["chat_message"]
    id: int
    message: str
    sender_username: str
    sender_full_name: str
    sender_profile_picture: str
    timestamp: str
    timestamp_display: str
    is_edited: bool = False
    attachment_url: str = ""
    attachment_type: str = ""
    thumbnail_url: str = ""


class EditMessageFrame(_BaseFrame):
    """
    {
      "type": "edit_message",
      "message_id": 1029,
      "content": "new text",
      "is_edited": true,
      "timestamp": "2025-10-15T15:21:43.932991+00:00"
    }
    """
    type: Literal["edit_message"]
    message_id: int
    content: str
    is_edited: bool = True
    timestamp: str


class UserTypingFrame(_BaseFrame):
    """
    { "type": "user_typing", "typing_users": ["Rc10283"] }
    """
    type: Literal["user_typing"]
    typing_users: List[str] = []


class ErrorFrame(_BaseFrame):
    """
    { "type": "error", "message": "Something went wrong" }
    """
    type: Literal["error"]
    message: str


OutgoingFrame = Union[ChatMessageFrame, EditMessageFrame, UserTypingFrame, ErrorFrame]


def ensure_outgoing_dict(frame: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate a dict 'frame' against the union above.
    - Keeps performance: just parse/return dict; pydantic will raise on mismatch.
    - If invalid, raise ValueError to let caller log/DLQ appropriately.
    """
    t = frame.get("type")
    if t == "chat_message":
        ChatMessageFrame.parse_obj(frame)
    elif t == "edit_message":
        EditMessageFrame.parse_obj(frame)
    elif t == "user_typing":
        UserTypingFrame.parse_obj(frame)
    elif t == "error":
        ErrorFrame.parse_obj(frame)
    else:
        raise ValueError(f"Unsupported outgoing frame type: {t}")
    return frame


# ---------------------------------------------------------------------
# Stream payloads (Redis Streams)
#   What the dispatcher reads (produced by your service layer)
# ---------------------------------------------------------------------

class StreamPrebuiltFrame(BaseModel):
    """
    Preferred producer payload:
    {
      "conversation_id": 3,
      "frame": { ... one of outgoing frames ... }
    }
    """
    conversation_id: int
    frame: Dict[str, Any]  # validated at dispatch via ensure_outgoing_dict

    @validator("frame")
    def _frame_must_be_valid(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        ensure_outgoing_dict(v)
        return v


class StreamIdentifiers(BaseModel):
    """
    Minimal producer payload (dispatcher builds the DTO):
    {
      "conversation_id": 3,
      "message_id": 1029,
      "event_type": "chat_message" | "edit_message"
    }
    """
    conversation_id: int
    message_id: int
    event_type: Literal["chat_message", "edit_message"] = "chat_message"


StreamPayload = Union[StreamPrebuiltFrame, StreamIdentifiers]


def parse_stream_payload(data: Dict[str, Any]) -> StreamPayload:
    """
    Accepts decoded JSON (e.g., parsed from XREADGROUP fields['payload']).
    Returns a validated StreamPayload.
    """
    if "frame" in data:
        return StreamPrebuiltFrame.parse_obj(data)
    return StreamIdentifiers.parse_obj(data)


# ---------------------------------------------------------------------
# Utility factories (optional but handy)
# ---------------------------------------------------------------------

def make_error(message: str) -> Dict[str, Any]:
    """Build a valid error frame dict."""
    return ErrorFrame(type="error", message=message).dict()


def make_typing(users: List[str]) -> Dict[str, Any]:
    """Build a valid typing frame dict."""
    return UserTypingFrame(type="user_typing", typing_users=users).dict()
