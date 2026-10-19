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


def test_redirects_stay_on_https_behind_a_reverse_proxy():
    # /summary redirects to /summary/; behind Cloudflare or another TLS proxy that redirect must stay
    # https, or browsers block it as mixed content and the console pages stay empty
    from fastapi.testclient import TestClient

    response = TestClient(build_app()).get("/summary", headers={"x-forwarded-proto": "https"},
                                           follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"].startswith("https://")
