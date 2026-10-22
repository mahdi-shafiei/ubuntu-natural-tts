//! Smoke tests: the built binary speaks, switches styles, reports errors.
use std::io::Write;
use std::process::{Command, Stdio};

fn run(input: &str) -> Vec<String> {
    let mut child = Command::new(env!("CARGO_BIN_EXE_natural-tts-mathcat"))
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .spawn()
        .expect("spawn helper");
    child
        .stdin
        .take()
        .unwrap()
        .write_all(input.as_bytes())
        .unwrap();
    let out = child.wait_with_output().expect("helper output");
    assert!(out.status.success(), "helper exited with {}", out.status);
    String::from_utf8(out.stdout)
        .unwrap()
        .lines()
        .map(String::from)
        .collect()
}

const FRACTION: &str = "<math><mfrac><mi>a</mi><mi>b</mi></mfrac></math>";
// SSML mode marks single letters as characters; this is the exact line MathCAT 0.7.7 emits.
const FRACTION_SPOKEN: &str =
    "<say-as interpret-as='characters'>a</say-as> over <say-as interpret-as='characters'>b</say-as>";

#[test]
fn speaks_a_fraction_in_clearspeak_ssml() {
    let lines = run(&format!("{FRACTION}\n"));
    assert_eq!(lines, vec![FRACTION_SPOKEN]);
}

#[test]
fn switches_style_and_verbosity_on_request() {
    let sum = "<math><mrow><msubsup><mo>&#x2211;</mo><mrow><mi>i</mi><mo>=</mo><mn>1</mn></mrow><mi>n</mi></msubsup><msub><mi>x</mi><mi>i</mi></msub></mrow></math>";
    let lines = run(&format!(
        "@SimpleSpeak Terse\n{sum}\n@ClearSpeak Verbose\n{sum}\n"
    ));
    assert_eq!(lines[0], "OK");
    assert_eq!(lines[2], "OK");
    assert_ne!(lines[1], lines[3], "styles should differ");
    assert!(lines[3].contains("sum"), "{}", lines[3]);
}

#[test]
fn emits_ssml_breaks_and_characters() {
    let integral = "<math><mrow><msubsup><mo>&#x222B;</mo><mn>0</mn><mn>1</mn></msubsup><mi>f</mi><mo>(</mo><mi>x</mi><mo>)</mo><mi>d</mi><mi>x</mi></mrow></math>";
    let lines = run(&format!("{integral}\n"));
    assert!(lines[0].contains("<break time="), "{}", lines[0]);
    assert!(
        lines[0].contains("interpret-as='characters'"),
        "{}",
        lines[0]
    );
}

#[test]
fn invalid_input_is_an_error_line_not_a_crash() {
    let lines = run("<math><mrow>\nnot xml\n@nonsense\n");
    assert_eq!(lines.len(), 3);
    assert!(lines.iter().all(|l| l.starts_with("ERROR ")), "{lines:?}");
    let after = run(&format!("<math><mrow>\n{FRACTION}\n"));
    assert_eq!(after[1], FRACTION_SPOKEN);
}

#[test]
fn version_flag() {
    let out = Command::new(env!("CARGO_BIN_EXE_natural-tts-mathcat"))
        .arg("--version")
        .output()
        .unwrap();
    assert!(String::from_utf8_lossy(&out.stdout).starts_with("natural-tts-mathcat 0.4.0"));
}
