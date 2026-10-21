import threading
import time
from contextlib import contextmanager

from natural_tts.daemon import serve
from natural_tts.ipc import STOP_MESSAGE, MessageServer, send_message
from tests.fakes import make_settings


class RecordingEngine:
    def __init__(self):
        self.events = []

    def submit(self, text):
        self.events.append(("submit", text))

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


def test_blank_messages_only_stop(tmp_path):
    engine = RecordingEngine()
    run_serve(tmp_path / "s/k.sock", engine, ["   "])
    assert engine.events == [("stop",)]


class FakeSynth:
    def __init__(self):
        self.warmed = False

    def warm_up(self):
        self.warmed = True

    def synthesize(self, chunks):
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
        return calls[0] == 1  # handle exactly one message

    def on_ready(msg):
        assert synth.warmed  # model loaded before the socket opens
        ready.append(msg)
        threading.Thread(
            target=send_message, args=(paths.kokoro_socket, STOP_MESSAGE)
        ).start()

    run(
        settings,
        synth,
        NullSink(),
        on_ready=on_ready,
        keep_running=keep_running,
    )
    assert ready == ["natural-tts ready (voice af_heart, speed 1.0)"]
    assert not paths.kokoro_socket.exists()
