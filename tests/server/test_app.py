import sys
from unittest.mock import MagicMock

sys.modules.setdefault("ffmpeg", MagicMock())
sys.modules.setdefault("moviepy", MagicMock())
sys.modules.setdefault("moviepy.editor", MagicMock())

from server.api.app import build_app  # noqa: E402


def test_server_app_has_the_console_data_and_client_routes_but_no_player():
    paths = set(build_app().openapi()["paths"])
    assert {"/", "/remote", "/client/version", "/client/rundown", "/client/media", "/schedules/{network_name}",
            "/ppv/{channel_number}"} <= paths
    assert not any(path.startswith("/player") for path in paths)
    assert "/ppv/{channel_number}/play_file" not in paths
