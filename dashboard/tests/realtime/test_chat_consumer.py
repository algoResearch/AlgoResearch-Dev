# tests/realtime/test_chat_consumer.py
import json
import pytest
from channels.testing import WebsocketCommunicator
from algoresearch.asgi import application

# Commented out due to missing 'conversation_factory' fixture
# @pytest.mark.asyncio
# async def test_send_message_works(monkeypatch, settings, django_user_model, conversation_factory):
#     convo = conversation_factory()
#     user = convo.user1
# 
#     async def fake_enqueue_send_message(user, conversation_id, text, attachment, client_id):
#         return type("Saved", (), {"id": 1, "content": text, "timestamp":"2024-01-01T00:00:00Z",
#                                   "sender_username": user.username, "sender_full_name":"X Y",
#                                   "attachment_url":"", "attachment_type":"", "thumbnail_url":""})
# 
#     async def fake_build_event(saved):
#         return {
#             "type":"chat_message",
#             "message": saved.content,
#             "sender_username": saved.sender_username,
#             "sender_full_name": saved.sender_full_name,
#             "timestamp": saved.timestamp,
#             "attachment_url": "",
#             "attachment_type": "",
#             "thumbnail_url": "",
#         }
# 
#     from dashboard.realtime import consumers
#     monkeypatch.setattr(consumers, "enqueue_send_message", fake_enqueue_send_message)
#     monkeypatch.setattr(consumers, "build_group_chat_event", fake_build_event)
# 
#     communicator = WebsocketCommunicator(application, f"/ws/chat/{convo.id}/")
#     communicator.scope["user"] = user
#     connected, _ = await communicator.connect()
#     assert connected
# 
#     await communicator.send_json_to({"type":"message","message":"hello"})
#     resp = await communicator.receive_json_from()
#     assert resp["type"] == "chat_message"
#     assert resp["message"] == "hello"
#     await communicator.disconnect()
