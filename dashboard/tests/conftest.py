# dashboard/tests/conftest.py
import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from model_bakery import baker
from django.conf import settings
from channels.routing import URLRouter
from django.urls import re_path
from channels.layers import get_channel_layer

# 👇 update these to your real consumer module paths
from dashboard.realtime.consumers import ChatConsumer, NotificationConsumer

User = get_user_model()

@pytest.fixture(autouse=True)
def _media_tmp(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.STATIC_ROOT = tmp_path / "static"
    yield

@pytest.fixture(autouse=True)
def _channels_inmemory(settings):
    settings.CHANNEL_LAYERS = {
        "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
    }
    yield

@pytest.fixture
def user(db):
    return baker.make(User)

@pytest.fixture
def other_user(db):
    return baker.make(User)

@pytest.fixture
def org(db):
    # Update to your real Organization model path if different
    return baker.make("dashboard.Organization")

@pytest.fixture
def conversation(db, org, user, other_user):
    # Update to your real Conversation model & fields
    conv = baker.make("dashboard.Conversation", organization=org)
    # If you use M2M membership:
    if hasattr(conv, "members"):
        conv.members.add(user, other_user)
    return conv

@pytest.fixture
def application():
    """
    Minimal ASGI router that mirrors your WS endpoints used by the front-end:
    /ws/chat/<conversation_id>/ and /ws/notifications/user_<id>/
    """
    return URLRouter([
        re_path(r"^ws/chat/(?P<conversation_id>\d+)/$", ChatConsumer.as_asgi()),
        re_path(r"^ws/notifications/user_(?P<uid>\d+)/$", NotificationConsumer.as_asgi()),
    ])
