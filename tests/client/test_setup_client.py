import json

from client.platform.setup_client import setup


def _answers(*answers):
    replies = iter(answers)
    return lambda prompt="": next(replies, "")  # Enter for anything not answered


def test_a_new_client_answers_server_look_and_osd(tmp_path):
    path = tmp_path / "client.json"
    setup(str(path), input=_answers("http://homelab:4242", "3", "3", "2"), print=lambda *a: None)
    assert json.loads(path.read_text()) == {
        "server_url": "http://homelab:4242", "look": "crt", "resolution": "480", "osd_style": "cable",
        "media": {"method": "http"}, "main_config": {}}


def test_enter_keeps_what_is_there(tmp_path):
    path = tmp_path / "client.json"
    path.write_text(json.dumps({"server_url": "http://old:4242", "look": "original", "osd_style": "kids",
                                "main_config": {"start_channel": 3}, "local_api_port": 4243}))
    setup(str(path), input=_answers("", "", "", ""), print=lambda *a: None)
    config = json.loads(path.read_text())
    assert (config["server_url"], config["look"], config["osd_style"]) == ("http://old:4242", "original", "kids")
    assert config["main_config"] == {"start_channel": 3} and config["local_api_port"] == 4243


def test_new_clients_default_to_broadcast_576_and_vcr(tmp_path):
    path = tmp_path / "client.json"
    setup(str(path), input=_answers("http://h:4242", "", "", ""), print=lambda *a: None)
    config = json.loads(path.read_text())
    assert (config["look"], config["resolution"], config["osd_style"]) == ("broadcast", "576", "vcr")


def test_the_original_look_suggests_no_ceiling(tmp_path):
    path = tmp_path / "client.json"
    setup(str(path), input=_answers("http://h:4242", "1", "", ""), print=lambda *a: None)
    assert json.loads(path.read_text())["resolution"] == "native"


def test_a_wrong_answer_asks_again(tmp_path):
    path = tmp_path / "client.json"
    setup(str(path), input=_answers("", "http://h:4242", "9", "crt", "1", "", ""), print=lambda *a: None)
    config = json.loads(path.read_text())
    assert (config["look"], config["osd_style"]) == ("original", "vcr")


def test_the_installer_passes_web_pages(tmp_path):
    path = tmp_path / "client.json"
    setup(str(path), input=_answers("http://h:4242", "", "", ""), print=lambda *a: None, web_pages=True)
    assert json.loads(path.read_text())["web_pages"] is True


def test_a_cloudflare_access_token_can_be_given(tmp_path):
    path = tmp_path / "client.json"
    setup(str(path), input=_answers("https://tv.example", "", "", "", "tv.access", "s3cret"), print=lambda *a: None)
    assert json.loads(path.read_text())["server_headers"] == {
        "CF-Access-Client-Id": "tv.access", "CF-Access-Client-Secret": "s3cret"}


def test_enter_keeps_the_token_and_no_token_adds_nothing(tmp_path):
    path = tmp_path / "client.json"
    setup(str(path), input=_answers("http://h:4242"), print=lambda *a: None)
    assert "server_headers" not in json.loads(path.read_text())
    path.write_text(json.dumps({"server_url": "https://tv.example", "server_headers": {
        "CF-Access-Client-Id": "tv.access", "CF-Access-Client-Secret": "s3cret"}}))
    setup(str(path), input=_answers(), print=lambda *a: None)
    assert json.loads(path.read_text())["server_headers"]["CF-Access-Client-Id"] == "tv.access"
