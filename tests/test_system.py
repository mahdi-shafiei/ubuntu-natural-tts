from natural_tts.system import EXIT_NOT_FOUND, EXIT_TIMEOUT, Result, run


class TestRun:
    def test_captures_stdout_and_code(self):
        r = run(["printf", "héllo"])
        assert r.ok and r.returncode == 0 and r.text == "héllo"

    def test_feeds_stdin(self):
        assert run(["cat"], stdin=b"\x00bytes").stdout == b"\x00bytes"

    def test_nonzero_exit_is_reported_not_raised(self):
        r = run(["sh", "-c", "echo oops >&2; exit 3"])
        assert not r.ok and r.returncode == 3 and r.stderr == b"oops\n"

    def test_missing_program(self):
        r = run(["no-such-program-xyz"])
        assert r.returncode == EXIT_NOT_FOUND and not r.ok

    def test_timeout(self):
        r = run(["sleep", "5"], timeout=0.2)
        assert r.returncode == EXIT_TIMEOUT and not r.ok


class TestResult:
    def test_text_decodes_invalid_utf8_safely(self):
        assert Result(0, b"ok \xff", b"").text == "ok �"

    def test_describe_includes_stderr(self):
        r = Result(2, b"", b"boom\n")
        assert r.describe(["prog", "arg"]) == "prog arg failed (exit 2): boom"

    def test_describe_without_stderr(self):
        assert Result(1, b"", b"").describe(["x"]) == "x failed (exit 1)"
