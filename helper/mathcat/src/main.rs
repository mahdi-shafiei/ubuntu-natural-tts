//! natural-tts-mathcat: speak MathML with MathCAT, one expression per line.
//!
//! Protocol (stdin → stdout, line by line):
//!   `@<SpeechStyle> <Verbosity>`  switch preferences (e.g. `@ClearSpeak Verbose`)
//!   `<math …>…</math>`             one expression, no newlines → one SSML line
//!   anything invalid               → one line starting with `ERROR `
//!
//! Environment: `MC_LANG` (MathCAT language, default `en`; unknown languages
//! fall back to English inside MathCAT). The rules are embedded; MathCAT needs
//! the virtual rules path `Rules`, and the rules dir must be set before any
//! preference. `--version` prints the crate version and exits.

use libmathcat::interface::{get_spoken_text, set_mathml, set_preference, set_rules_dir};
use std::io::{self, BufRead, Write};

const RULES: &str = "Rules";

fn fail(what: &str, err: impl std::fmt::Display) -> ! {
    eprintln!("natural-tts-mathcat: {what}: {err}");
    std::process::exit(2);
}

fn configure(language: &str) {
    if let Err(e) = set_rules_dir(RULES) {
        fail("rules", e);
    }
    let prefs = [
        ("Language", language),
        ("SpeechStyle", "ClearSpeak"),
        ("Verbosity", "Medium"),
        ("TTS", "SSML"),
    ];
    for (name, value) in prefs {
        if let Err(e) = set_preference(name, value) {
            fail(name, e);
        }
    }
}

fn set(spec: &str) -> Result<(), String> {
    let (name, value) = spec
        .split_once('=')
        .filter(|(n, v)| !n.is_empty() && !v.is_empty())
        .ok_or_else(|| format!("expected '@Name=Value', got '@{spec}'"))?;
    set_preference(name.trim(), value.trim()).map_err(|e| e.to_string())
}

fn speak(mathml: &str) -> String {
    match set_mathml(mathml) {
        Ok(_) => match get_spoken_text() {
            Ok(text) => text.split_whitespace().collect::<Vec<_>>().join(" "),
            Err(e) => format!("ERROR {}", e.to_string().replace('\n', " ")),
        },
        Err(e) => format!("ERROR {}", e.to_string().replace('\n', " ")),
    }
}

fn main() {
    if std::env::args().any(|a| a == "--version") {
        println!("natural-tts-mathcat {}", env!("CARGO_PKG_VERSION"));
        return;
    }
    let language = std::env::var("MC_LANG").unwrap_or_else(|_| "en".to_string());
    configure(&language);
    let stdin = io::stdin();
    let mut out = io::stdout();
    for line in stdin.lock().lines() {
        let line = match line {
            Ok(line) => line,
            Err(_) => break,
        };
        let line = line.trim();
        if line.is_empty() {
            continue;
        }
        let reply = match line.strip_prefix('@') {
            Some(spec) => match set(spec) {
                Ok(()) => "OK".to_string(),
                Err(e) => format!("ERROR {e}"),
            },
            None => speak(line),
        };
        if writeln!(out, "{reply}").and_then(|_| out.flush()).is_err() {
            break;
        }
    }
}
