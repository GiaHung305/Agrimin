import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from app.api import chat


def test_only_stream_chat_route_is_exposed():
    paths = {route.path for route in chat.router.routes}
    assert "/chat/stream" in paths
    assert "/chat" not in paths
