"""A stand-in for the natural-tts-mathcat helper, driven by its input.

Replies follow the real protocol: `@Style Verbosity` -> "OK", an
expression -> one SSML line. Special expressions steer the fake:
`<math>crash</math>` exits, `<math>hang</math>` sleeps 10 s,
`<math>bad</math>` yields an ERROR line, anything else echoes a canned
SSML line that embeds the current style so tests can see switches.
"""

import sys
import time

style = "ClearSpeak Medium"
for raw in sys.stdin:
    line = raw.strip()
    if not line:
        continue
    if line.startswith("@"):
        style = line[1:]
        print("OK", flush=True)
        continue
    if line == "<math>crash</math>":
        sys.exit(3)
    if line == "<math>hang</math>":
        time.sleep(10)
    if line == "<math>bad</math>":
        print("ERROR Invalid MathML input", flush=True)
        continue
    print(
        f"[{style}] cap <say-as interpret-as='characters'>A</say-as> over "
        f"<break time='128ms'/> <say-as interpret-as='characters'>b</say-as> "
        f"<break time='400ms'/> end",
        flush=True,
    )
