# natural-tts-mathcat

A small helper that speaks MathML with [MathCAT](https://github.com/daisy/MathCAT) for the
natural-tts read-aloud hotkey. One expression per line in, one SSML line out; `@SpeechStyle=ClearSpeak
Medium` switches style and verbosity; `MC_LANG` picks the rules language. The MathCAT rules
are embedded, so the binary has no files to install next to it.

`natural-tts setup` downloads a prebuilt binary for the release in use and verifies it
against the release's `SHA256SUMS`; if that fails and `cargo` is available, it builds this
crate locally. Build by hand with `cargo build --release`; test with `cargo test --release`.
