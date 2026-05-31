import socket

from app.launcher import build_launch_message, choose_start_path, choose_start_url, find_available_port


def test_choose_start_path_opens_setup_until_onboarding_done():
    assert choose_start_path(lambda: True) == "/setup"
    assert choose_start_path(lambda: False) == "/"


def test_choose_start_url_uses_localhost_port_and_start_path():
    assert choose_start_url(8123, lambda: True) == "http://127.0.0.1:8123/setup"


def test_build_launch_message_names_status_and_stop_action():
    message = build_launch_message("http://127.0.0.1:8000/")

    assert "http://127.0.0.1:8000/" in message
    assert "/status" in message
    assert "/logs" in message
    assert "Close this window to stop FeedsAI." in message


def test_build_launch_message_status_link_stays_at_root_for_setup_url():
    message = build_launch_message("http://127.0.0.1:8000/setup")

    assert "Status page: http://127.0.0.1:8000/status" in message


def test_find_available_port_skips_bound_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        bound_port = sock.getsockname()[1]

        assert find_available_port(bound_port) != bound_port
