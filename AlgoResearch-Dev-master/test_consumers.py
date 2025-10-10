# dashboard/tests/test_consumers.py
import json
import pytest
from channels.testing import WebsocketCommunicator
from asgiref.sync import sync_to_async

@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_chat_send_receive_text(application, conversation, user):
    ws = WebsocketCommunicator(application, f"/ws/chat/{conversation.id}/")
    # Inject the authenticated user into the ASGI scope
    ws.scope["user"] = user

    connected, _ = await ws.connect()
    assert connected

    await ws.send_to(text_data=json.dumps({
        "type": "message",
        "message": "Hello world",
    }))

    # Expect a broadcast from the consumer
    data = json.loads(await ws.receive_from())
    assert data["type"] in {"chat_message", "message"}
    assert "Hello" in data.get("message", "")

    await ws.disconnect()

@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_notifications_receive(application, user):
    notif = WebsocketCommunicator(application, f"/ws/notifications/user_{user.id}/")
    notif.scope["user"] = user
    assert (await notif.connect())[0]

    # Simulate server->group message by calling group_send from inside the test
    from channels.layers import get_channel_layer
    layer = get_channel_layer()
    await layer.group_send(
        f"user_{user.id}",
        {
            "type": "notification_message",
            "message": "Ping!",
            "org_id": 1,
            "conversation_id": 999,
            "sender": "system",
            "sender_profile_picture": "/static/img/default-profile.jpg",
            "conversation_url": f"/{1}/conversation/{999}/",
        }
    )

    payload = json.loads(await notif.receive_from())
    # Your NotificationConsumer typically normalizes to {"type": "message", ...}
    assert payload.get("message") == "Ping!"
    await notif.disconnect()
