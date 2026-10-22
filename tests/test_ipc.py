import os
import socket
import stat
import threading

import pytest

from natural_tts.ipc import (
    HTML_FORMAT,
    MAX_MESSAGE_BYTES,
    STOP_MESSAGE,
    DaemonNotRunningError,
    MessageServer,
    frame,
    send_message,
    unframe,
)


@pytest.fixture
def sock_path(tmp_path):
    # AF_UNIX paths are limited to ~107 bytes; keep it short.
    d = tmp_path / "r"
    return d / "k.sock"


def serve_one(
    server: MessageServer,
) -> tuple[list[str], threading.Thread]:
    received: list[str] = []
    t = threading.Thread(target=lambda: received.append(server.receive()))
    t.start()
    return received, t


class TestMessageServer:
    def test_round_trip_utf8(self, sock_path):
        with MessageServer(sock_path) as server:
            received, t = serve_one(server)
            send_message(sock_path, "Café — “quoted” ünïcode")
            t.join(5)
        assert received == ["Café — “quoted” ünïcode"]

    def test_socket_and_directory_are_private(self, sock_path):
        with MessageServer(sock_path):
            assert stat.S_IMODE(os.stat(sock_path).st_mode) == 0o600
            assert stat.S_IMODE(os.stat(sock_path.parent).st_mode) == 0o700

    def test_stale_socket_file_is_replaced(self, sock_path):
        sock_path.parent.mkdir(mode=0o700)
        sock_path.write_text("stale")
        with MessageServer(sock_path) as server:
            received, t = serve_one(server)
            send_message(sock_path, "hello")
            t.join(5)
        assert received == ["hello"]

    def test_socket_removed_on_close(self, sock_path):
        with MessageServer(sock_path):
            pass
        assert not sock_path.exists()

    def test_oversized_message_is_truncated_at_limit(self, sock_path):
        big = "a" * (MAX_MESSAGE_BYTES + 1000)
        with MessageServer(sock_path) as server:
            received, t = serve_one(server)
            send_message(sock_path, big)
            t.join(5)
        assert len(received[0]) == MAX_MESSAGE_BYTES

    def test_invalid_utf8_is_replaced_not_fatal(self, sock_path):
        with MessageServer(sock_path) as server:
            received, t = serve_one(server)
            with socket.socket(socket.AF_UNIX) as c:
                c.connect(str(sock_path))
                c.sendall(b"ok \xff end")
            t.join(5)
        assert received == ["ok � end"]


class TestSendMessage:
    def test_missing_daemon_raises_clear_error(self, sock_path):
        with pytest.raises(DaemonNotRunningError, match="not running"):
            send_message(sock_path, "hi")

    def test_stop_message_is_distinct_from_text(self):
        assert STOP_MESSAGE.startswith("\x00")


class TestPrivateDir:
    def test_loose_permissions_are_tightened(self, sock_path):
        sock_path.parent.mkdir(mode=0o755)
        os.chmod(sock_path.parent, 0o755)
        with MessageServer(sock_path):
            assert stat.S_IMODE(os.stat(sock_path.parent).st_mode) == 0o700

    @pytest.mark.skipif(os.getuid() != 0, reason="needs root to chown")
    def test_directory_owned_by_someone_else_is_refused(self, sock_path):
        sock_path.parent.mkdir(mode=0o700)
        os.chown(sock_path.parent, 65534, 65534)
        with pytest.raises(PermissionError, match="another user"):
            MessageServer(sock_path).__enter__()

    def test_receive_outside_context_is_an_error(self, sock_path):
        with pytest.raises(RuntimeError, match="outside its context"):
            MessageServer(sock_path).receive()


class TestFormatHeader:
    def test_plain_text_is_sent_as_is(self):
        assert frame("hello", None) == "hello"
        assert unframe("hello") == ("hello", None)

    def test_html_gets_a_nul_header_that_text_cannot_contain(self):
        message = frame("<p>hi</p>", HTML_FORMAT)
        assert message.startswith("\x00FORMAT text/html\n")
        assert unframe(message) == ("<p>hi</p>", HTML_FORMAT)

    def test_stop_is_not_a_format(self):
        assert unframe(STOP_MESSAGE) == (STOP_MESSAGE, None)

    def test_unknown_nul_header_is_an_empty_message(self):
        # A future or corrupt header must stop speech, not be spoken.
        assert unframe("\x00FORMAT image/png\nblob") == ("", None)
        assert unframe("\x00garbage") == ("", None)

    def test_round_trip_over_the_socket(self, sock_path):
        with MessageServer(sock_path) as server:
            received, t = serve_one(server)
            send_message(sock_path, frame("<b>x</b>", HTML_FORMAT))
            t.join(5)
        assert unframe(received[0]) == ("<b>x</b>", HTML_FORMAT)
