"""A stand-in for the natural-tts-mathcat helper, driven by its input.

Replies follow the real protocol: `@Name=Value` -> "OK" (or an ERROR for a
malformed line), an expression -> one SSML line. Special expressions steer
the fake: `<math>crash</math>` exits, `<math>hang</math>` sleeps 10 s,
`<math>bad</math>` yields an ERROR line, `<math>prefs</math>` lists the
preferences received so far, anything else echoes a canned SSML line that
embeds the current style and verbosity so tests can see switches.
"""

import sys
import time

prefs = {"SpeechStyle": "ClearSpeak", "Verbosity": "Medium"}
for raw in sys.stdin:
    line = raw.strip()
    if not line:
        continue
    if line.startswith("@"):
        name, sep, value = line[1:].partition("=")
        if not sep or not name or not value:
            print("ERROR expected '@Name=Value'", flush=True)
            continue
        prefs[name] = value
        print("OK", flush=True)
        continue
    if line == "<math>crash</math>":
        sys.exit(3)
    if line == "<math>hang</math>":
        time.sleep(10)
    if line == "<math>bad</math>":
        print("ERROR Invalid MathML input", flush=True)
        continue
    if line == "<math>prefs</math>":
        print(
            "prefs " + " ".join(f"{k}={v}" for k, v in sorted(prefs.items())),
            flush=True,
        )
        continue
    style = f"{prefs['SpeechStyle']} {prefs['Verbosity']}"
    print(
        f"[{style}] cap <say-as interpret-as='characters'>A</say-as> over "
        f"<break time='128ms'/> <say-as interpret-as='characters'>b</say-as> "
        f"<break time='400ms'/> end",
        flush=True,
    )
