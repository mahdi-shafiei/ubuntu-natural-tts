import threading
import time
from contextlib import contextmanager

from natural_tts.daemon import serve
from natural_tts.ipc import STOP_MESSAGE, MessageServer, send_message
from tests.fakes import make_settings


class RecordingEngine:
    def __init__(self):
        self.events = []

    def submit(self, text, format=None):
        self.events.append(
            ("submit", text) if format is None else ("submit", text, format)
        )

    def stop(self):
        self.events.append(("stop",))


def run_serve(sock_path, engine, messages):
    remaining = [len(messages)]

    def keep_running():
        remaining[0] -= 1
        return remaining[0] >= 0

    with MessageServer(sock_path) as server:
        t = threading.Thread(target=serve, args=(server, engine, keep_running))
        t.start()
        for m in messages:
            send_message(sock_path, m)
            time.sleep(0.01)
        t.join(5)
        assert not t.is_alive()


def test_text_is_submitted_and_stop_stops(tmp_path):
    engine = RecordingEngine()
    run_serve(
        tmp_path / "s/k.sock", engine, ["Hello there.", STOP_MESSAGE, "Again."]
    )
    assert engine.events == [
        ("submit", "Hello there."),
        ("stop",),
        ("submit", "Again."),
    ]


def test_html_messages_reach_the_engine_with_their_format(tmp_path):
    from natural_tts.ipc import HTML_FORMAT, frame

    engine = RecordingEngine()
    run_serve(tmp_path / "s/k.sock", engine, [frame("<p>Hi</p>", HTML_FORMAT)])
    assert engine.events == [("submit", "<p>Hi</p>", HTML_FORMAT)]


def test_unknown_header_only_stops(tmp_path):
    engine = RecordingEngine()
    run_serve(tmp_path / "s/k.sock", engine, ["\x00FORMAT image/png\nblob"])
    assert engine.events == [("stop",)]


def test_blank_messages_only_stop(tmp_path):
    engine = RecordingEngine()
    run_serve(tmp_path / "s/k.sock", engine, ["   "])
    assert engine.events == [("stop",)]


class FakeSynth:
    def __init__(self):
        self.warmed = False
        self.spoken = []

    def warm_up(self):
        self.warmed = True

    def synthesize(self, segments):
        self.spoken += [segment.text for segment in segments]
        return iter([])


class NullSink:
    @contextmanager
    def open(self):
        yield self

    def write(self, samples):
        pass


def test_run_warms_up_before_listening_and_reports_ready(tmp_path):
    from natural_tts.daemon import run

    settings = make_settings(tmp_path)
    paths = settings.paths
    synth, ready = FakeSynth(), []
    calls = [0]

    def keep_running():
        calls[0] += 1
        return calls[0] <= 2  # one text, then the stop message

    def send_both():
        send_message(paths.kokoro_socket, "See Fig. 3 in E. coli.")
        send_message(paths.kokoro_socket, STOP_MESSAGE)

    def on_ready(msg):
        assert synth.warmed  # model loaded before the socket opens
        ready.append(msg)
        threading.Thread(target=send_both).start()

    run(
        settings,
        synth,
        NullSink(),
        on_ready=on_ready,
        keep_running=keep_running,
    )
    assert ready == ["natural-tts ready (voice af_heart, speed 1.0)"]
    assert not paths.kokoro_socket.exists()
    # The reading front end is wired in: words and pronunciation markup.
    assert synth.spoken == ["See Figure three in [E. coli](/ˌi kˈOlI/)."]  # noqa: RUF001


def test_ready_message_is_flushed_for_the_journal(monkeypatch):
    # Under systemd, stdout is a pipe and block-buffered: an unflushed
    # "ready" line would never reach `journalctl --user -u ...`.
    from natural_tts import daemon

    class Stream:
        def __init__(self):
            self.text, self.flushed = "", False

        def write(self, s):
            self.text += s
            self.flushed = False

        def flush(self):
            self.flushed = True

    stream = Stream()
    monkeypatch.setattr("sys.stdout", stream)
    daemon.announce("natural-tts ready")
    assert stream.text == "natural-tts ready\n" and stream.flushed
