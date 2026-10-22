# Natural text-to-speech for Ubuntu

**Make your Linux desktop read aloud in a natural voice.** Highlight text in
any app and press a key, or let Firefox, e-book readers and screen readers
use a modern neural voice instead of the robotic default. Everything runs
locally: no account, no cloud, no text leaves your machine.

[![CI](https://github.com/mahdi-shafiei/ubuntu-natural-tts/actions/workflows/ci.yml/badge.svg)](https://github.com/mahdi-shafiei/ubuntu-natural-tts/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Ubuntu 24.04+](https://img.shields.io/badge/Ubuntu-24.04%2B-E95420?logo=ubuntu&logoColor=white)
![Python 3.11 | 3.12](https://img.shields.io/badge/python-3.11%20%7C%203.12-3776AB?logo=python&logoColor=white)

## Hear the difference

The same sentence, read by each engine. Press play on each:

**espeak-ng**: what Linux uses out of the box

https://github.com/user-attachments/assets/4be1daea-9db4-4fcf-bbb6-1e283f1394a0

**Piper**: the natural-tts system voice

https://github.com/user-attachments/assets/6413770f-cfbd-47a1-9619-37454c34ae6d

**Kokoro**: the natural-tts read-anything hotkey

https://github.com/user-attachments/assets/07156e2c-69fa-446a-9be4-e507cbc39142

| | espeak-ng | Piper | Kokoro-82M |
|---|---|---|---|
| **Sound** | Robotic, formant synthesis | Natural, neural (VITS) | Most natural, neural (StyleTTS 2) |
| **Role here** | Ubuntu's default, replaced | System voice via Speech Dispatcher | Read-anything hotkey |
| **Used by** | Every Speech Dispatcher client | Firefox Reader View, Foliate, Orca | Any app with selectable text |
| **Runs on** | Any CPU | Any CPU, faster than real time | CPU; NVIDIA GPU optional |
| **Model size** | None | About 110 MB per voice | 82M parameters |
| **License** | GPL-3.0 | GPL-3.0 engine; voice license varies | Apache-2.0 |
| **Listen** | [espeak.mp3](docs/samples/espeak.mp3) | [piper.mp3](docs/samples/piper.mp3) | [kokoro.mp3](docs/samples/kokoro.mp3) |

## Hear the reading front end

Since 0.2.0 the hotkey reads technical text the way a person would. Each
clip plays the same sentence twice: first as 0.1.1 read it, then as
0.2.0 reads it. The red tick marks where the old chunker cut the
sentence.

**Numbers, units and symbols** in a methods sentence:

> We used a phosphate buffered saline solution at pH 7.4 and 37 °C
> (n = 3; p < 0.05), see Eq. 2: x = 1.


https://github.com/user-attachments/assets/13c415b6-30db-43bb-b606-b5bb1e233d87



**Abbreviations and names**:

> Our neighbour, Dr. Ana Ruiz, moved to St. Paul last spring; her
> brother, Mr. T. Ruiz, stayed behind.


https://github.com/user-attachments/assets/105e4e63-ce28-4e53-863e-1e195562aa34



<details>
<summary>Two more: a paper sentence and a citation-heavy one</summary>

> In E. coli the gene lacZ is expressed, as Dr. Smith et al. showed in
> Fig. 3 of the paper, which we read in detail.


https://github.com/user-attachments/assets/4de64001-b591-40fc-a225-a23f3bcbfa55



> The effect was first reported by Chen et al. in 2019 (see Ref. 4;
> cf. Sec. 3.2), and later confirmed, e.g. by Müller et al., with
> larger samples (n = 120; p < 0.01).


https://github.com/user-attachments/assets/789baf62-d685-4d0d-9a0a-da9d1c0647e7



</details>

| Written | Spoken |
|---|---|
| `p < 0.05`, `n = 3`, `5 ± 2` | p is less than zero point zero five, n equals three, five plus or minus two |
| `37 °C`, `10 µg/mL`, `3–5 mm` | thirty-seven degrees Celsius, ten micrograms per milliliter, three to five millimeters |
| `Fig. 3`, `Eq. 2`, `et al.`, `e.g.` | Figure three, Equation two, et al, for example |
| `Dr. Smith`, `St. Louis`, `Elm St.` | Doctor Smith, Saint Louis, Elm Street |
| `2026-10-21`, `14:30`, `$5.50`, `v2.1.0` | October twenty-first, twenty twenty-six; fourteen thirty; five dollars and fifty cents; version two point one point zero |
| `x²`, `1.5 × 10^-3`, `α` | x squared, one point five times ten to the power of minus three, alpha |
| `E. coli`, `in vitro`, `Cas9`, `H2O` | pronounced from the built-in lexicon; H two O |
| `[12]`, `(Smith et al., 2019)` | skipped (`citations = "read"` says them) |

Everything is a plain rule you can read in `src/natural_tts/reading/`,
and `reading.enabled = false` restores the raw reading.

### Structure and code

Since 0.3.0 the hotkey also hears the shape of what you selected. Each
clip plays the same selection twice: as 0.2.1 read it, then as 0.3.0
reads it. Green ticks mark segment boundaries.

**A README fragment** with a heading, a list and a table:

```markdown
## Quick start

Run the installer, then press a key:

- Super+Alt+R reads the highlighted text
- Super+Alt+C reads the clipboard

| Key | Action |
|---|---|
| Super+Alt+S | stop |
```


https://github.com/user-attachments/assets/96b9609a-6863-49bc-8433-bda4d9025f98



**A Python block** at `code_level = 1`:

```python
def get_user_name(users, idx):
    # the first match wins
    if idx >= len(users):
        return None
    return users[idx].name
```


https://github.com/user-attachments/assets/948609bc-0772-4764-8f97-f25dc3e93ca5



**An HTML selection**, as Firefox hands it over. The old version read the
tags aloud:

```html
<h2>Results</h2>
<p>Run <code>git add -A</code> at 37 °C, see Fig. 3.</p>
<ol><li>mix the buffer</li><li>incubate for 2 h</li></ol>
```


https://github.com/user-attachments/assets/41a6809b-6c8b-4a85-beda-5718b5203ff1



### Math

Since 0.4.0 formulas are spoken by MathCAT. Each clip plays the same
selection twice: as 0.3.0 read it (LaTeX read as words), then as 0.4.0
reads it. Green ticks mark segment boundaries.

**Inline formulas in a sentence**, as a paper source carries them:

```latex
We model the posterior as $P(\theta \mid D) = \frac{P(D \mid \theta)\, P(\theta)}{P(D)}$
and fit $\hat{y} = \beta_0 + \beta_1 x$, which is significant at $p < 0.05$.
```


https://github.com/user-attachments/assets/3aca0af4-e711-4c56-b03f-40c01981a542



**A display formula** between paragraphs, with MathCAT's own pauses:

```latex
The Gaussian integral

$$\int_{-\infty}^{\infty} e^{-x^2}\,dx = \sqrt{\pi}$$

follows from polar coordinates.
```


https://github.com/user-attachments/assets/bac34e82-d57f-4c80-a253-c441b13ae0b1



**A formula line from a PDF**, in plain Unicode:

```text
Energy is given by

E = mc²

where m is the mass, and x² + y² = r² describes a circle.
```


https://github.com/user-attachments/assets/88efb6a4-6564-43b6-b853-96e2169632ee



## Quick start

```bash
git clone https://github.com/mahdi-shafiei/ubuntu-natural-tts.git
cd ubuntu-natural-tts
./install.sh            # add --gpu on NVIDIA machines for CUDA PyTorch
```

The installer downloads about 1.6 GB (PyTorch and the voice models) and
needs no logout. Then:

| Keys | Action |
|---|---|
| <kbd>Super</kbd>+<kbd>Alt</kbd>+<kbd>R</kbd> | Read the highlighted text |
| <kbd>Super</kbd>+<kbd>Alt</kbd>+<kbd>C</kbd> | Read the clipboard (press <kbd>Ctrl</kbd>+<kbd>C</kbd> first; needed in ONLYOFFICE and other canvas-based editors) |
| <kbd>Super</kbd>+<kbd>Alt</kbd>+<kbd>S</kbd> | Stop |

New text interrupts whatever is playing. In Firefox, open Reader View
(<kbd>F9</kbd>) and press the headphones button; the speed slider works.

If something stays silent, run `natural-tts doctor`.

## Features

- **Natural voices, locally.** Kokoro for the hotkeys, Piper as the
  system-wide [Speech Dispatcher](https://github.com/brailcom/speechd)
  voice. CPU is enough; an NVIDIA GPU is optional.
- **Works in every app.** Highlighted text (X11 and Wayland), the
  clipboard, or any program that speaks through Speech Dispatcher.
- **Reads PDFs properly.** Words hyphenated across line breaks are
  re-joined and hard wraps removed before speaking.
- **Reads like a person.** Numbers, dates, units, abbreviations and
  symbols are spoken as words on the hotkey path: `p < 0.05` is "p is
  less than zero point zero five", `Fig. 3` is "Figure three", `E. coli`
  is pronounced correctly, and `[12]` citation markers are skipped. Add
  your own pronunciations in `~/.config/natural-tts/lexicon.toml`.
- **Reads structure and code.** Headings, lists, quotes and tables get
  their own pauses; a table is read caption first, then each row as
  "Heading. Column: value." sentences; code blocks in Markdown, HTML,
  reStructuredText, LaTeX, Org, AsciiDoc, prompts and diffs are read as
  words (`get_user_name(x)` is "get user name x"), with `code_level`
  choosing how much punctuation you hear.
- **Reads names and initialisms.** LinkedIn, PyTorch and OpenAI are left
  to the engine, which reads them whole; ODE, DNA and GPUs are spelled as
  one smooth word; IEEE is "I triple E"; a heading in capitals is read as
  words. Names the engine gets wrong go in your lexicon file.
- **Reads math.** LaTeX (`$…$`, `$$…$$`, equation environments), Unicode
  formulas and MathML on web pages are spoken the way a math teacher
  reads them, through [MathCAT](https://nsoiffer.github.io/MathCAT/):
  `\frac{a}{b}` is "a over b", `\int_0^1 f(x)\,dx` is "the integral
  from 0 to 1 of f of x d x", with "end fraction" and "end root" marking
  nested scope. `math_style` chooses ClearSpeak or SimpleSpeak.
- **Fast start, instant stop.** Speech starts after the first short chunk;
  stop takes effect within about a tenth of a second.
- **Self-healing.** Audio-device or synthesis errors are logged and
  recovered from; services restart automatically.
- **One settings file.** Change voices and speeds in
  `~/.config/natural-tts/settings.toml`, then run `natural-tts apply`.
- **Leaves your system alone.** Your other Speech Dispatcher voices and
  GNOME shortcuts are kept; `natural-tts teardown` reverts every change.
- **Private.** Nothing is sent anywhere; the Piper server listens on
  127.0.0.1 only.

## How it works

```mermaid
flowchart LR
    subgraph Apps
        FF[Firefox Reader View]
        FO[Foliate / Orca]
        HK[Super+Alt+R / C / S]
    end
    FF --> SD[Speech Dispatcher]
    FO --> SD
    SD -->|piper-generic module| PS[natural-tts piper-speak]
    PS -->|HTTP 127.0.0.1| PIPER[Piper server<br/>model kept loaded]
    HK --> RS[natural-tts read]
    RS -->|Unix socket| KD[Kokoro daemon<br/>model kept loaded]
    PIPER --> AU[PipeWire / PulseAudio]
    KD --> AU
```

- **Piper** handles Speech Dispatcher because it starts in well under a
  second per sentence. Its model stays loaded in a localhost-only HTTP
  server (a `systemd --user` service).
- **Kokoro** sounds more natural but takes a few seconds to load, so it
  runs as a background daemon. Hotkeys send it text over a private Unix
  socket.
- Both services and the Speech Dispatcher configuration are generated from
  the single `settings.toml`.
- **MathCAT** speaks formulas. The daemon starts `natural-tts-mathcat`
  (a helper built from the MathCAT crate, downloaded by `setup`) once and
  sends it MathML; its answer carries the pauses and spelled letters that
  become the spoken segments.

## Configuration

`~/.config/natural-tts/settings.toml` (created by `setup`):

```toml
[piper]
voice = "en_US-ljspeech-high"  # system voice
length_scale = 1.05            # higher is slower
sentence_silence = 0.25        # pause after each sentence, seconds
port = 5150

[kokoro]
voice = "af_heart"             # hotkey voice
speed = 1.0                    # 0.5 .. 2.0

[reading]
enabled = true                 # speak numbers, units, abbreviations and
                               # symbols as words (English voices only)
citations = "skip"             # or "read": citation markers such as [12]
code_level = 1                 # code blocks: 1 operators, 2 adds brackets
                               # and indentation, 3 every symbol
math_style = "clearspeak"      # or "simplespeak": how formulas are read
```

Run `natural-tts apply` after editing. A new Piper voice is downloaded
automatically.

Pronunciations the engine gets wrong go in
`~/.config/natural-tts/lexicon.toml`, which is merged over the built-in
list on the next `apply`. Phonemes use Kokoro's alphabet (`A` = ay,
`I` = eye, `O` = oh; `ˈ` marks stress):

```toml
[[entry]]
head = "Zymomonas"
misaki = "zˌImOmˈOnəs"

[[entry]]
head = "ACS"          # said as a word, not spelled
match = "exact"
misaki = "ˈæks"
```

### Voices

Kokoro voices, with the quality grades from its
[voice list](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md):

| Voice | Grade | |
|---|---|---|
| `af_heart` | A | US English, female (default) |
| `af_bella` | A- | US English, female |
| `af_nicole` | B- | US English, female, soft |
| `bf_emma` | B- | British English, female |
| `am_michael`, `am_fenrir`, `am_puck` | C+ | US English, male |
| `bm_fable`, `bm_george` | C | British English, male |

Piper voices: listen at
[rhasspy.github.io/piper-samples](https://rhasspy.github.io/piper-samples/)
and prefer `high` quality. **Check the dataset license** in each voice's
model card. The default `en_US-ljspeech-high` and `en_GB-cori-high` are
trained on public-domain data; the popular `en_US-lessac-high` uses a
research-only dataset and `en_US-ryan-high` a non-commercial one.

Other languages work too: Piper has voices for about 40 languages, and
Kokoro covers English, Spanish, French, Hindi, Italian, Japanese,
Portuguese and Mandarin.

## Commands

| Command | Purpose |
|---|---|
| `natural-tts setup` | Configure services, Speech Dispatcher and hotkeys |
| `natural-tts apply` | Apply `settings.toml` and restart services |
| `natural-tts doctor` | Check every component and print fixes |
| `natural-tts read selection` / `read clipboard` | Read aloud (what the hotkeys run) |
| `natural-tts say "text"` | Read text, or stdin, aloud |
| `natural-tts stop` | Stop reading |
| `natural-tts teardown` | Remove services, config changes and hotkeys |
| `./install.sh --uninstall` | Remove everything except settings |

## Troubleshooting

Start with:

```bash
natural-tts doctor
```

Each failing check prints the command that fixes it. Common cases:

| Symptom | Cause and fix |
|---|---|
| Hotkey does nothing right after login | Kokoro takes 10–20 s to load; a notification says so. Wait, or check `journalctl --user -u natural-tts-kokoro.service` for `natural-tts ready`. |
| Hotkey reads old text | The app never set the highlight (ONLYOFFICE, some Electron apps). Press <kbd>Ctrl</kbd>+<kbd>C</kbd>, then <kbd>Super</kbd>+<kbd>Alt</kbd>+<kbd>C</kbd>. |
| Firefox shows no natural voice | Fully quit and reopen Firefox after setup. The snap version works through `speech-dispatcher.socket`. |
| Only `piper-generic` is listed by `spd-say -O` | An active `AddModule` line in `~/.config/speech-dispatcher/speechd.conf` disables auto-detection; comment it out. |
| No sound at all | `doctor` checks that ALSA is routed to your sound server. On PipeWire the fix is `pipewire-alsa`; on PulseAudio it is `libasound2-plugins` (never install `pipewire-alsa` there: it replaces PulseAudio). |
| Gaps between sentences | Synthesis is slower than playback on this CPU. Reinstall with `./install.sh --gpu` on NVIDIA machines, or raise `kokoro.speed`. |
| Speech stopped after unplugging headphones | Errors are recovered automatically on the next request; if not, `systemctl --user restart natural-tts-kokoro.service`. |
| Hotkeys gone from Settings > Keyboard | `doctor` reports them missing; `natural-tts setup` adds them back without touching anything else. Before 0.4.1, running the project's own test suite on a desktop session removed every custom shortcut (the integration test now runs on a private D-Bus session). |
| "daemon is not running or still starting" right after an upgrade | `setup` restarts the daemon and the old socket file lingers for a few seconds. Wait for `natural-tts ready` in `journalctl --user -u natural-tts-kokoro.service`, then try again. |
| A number, unit, date or abbreviation is read in a way you do not want | The reading rules are plain code in `src/natural_tts/reading/`; `reading.enabled = false` in `settings.toml` restores the raw reading, and `reading.citations = "read"` says citation markers. Open an issue with the sentence and what you expected. |
| A name or term is mispronounced | Add it to `~/.config/natural-tts/lexicon.toml` (see [Configuration](#configuration)) and run `natural-tts apply`. Company and product names are read by the engine as written, so an entry with `match = "exact"` and the phonemes (or `words`) fixes one name without touching others. |
| A company name is spelled letter by letter, or an acronym is read as a word | Four-letter-and-longer capital runs are the engine's call: it spells what it does not know (TSMC, ASML) and reads the words it knows (NASA, COVID). Add an entry with `words` or phonemes for the exceptions (`SUSE`, `WHOOP` are packaged). Two- and three-letter runs are always spelled unless listed as words. |
| A table is read cell by cell with its headers and you would rather hear less | Every cell is read as "Column: value." so that long and wide tables stay followable; the caption and the shape come first and "End of table" closes it. There is no setting to shorten it yet; open an issue with the table. |
| Code is read with too much or too little punctuation | `reading.code_level` is 1 (operators only), 2 (adds brackets, separators and indentation) or 3 (every symbol). |
| A web page's headings and lists are read as one paragraph | Only Firefox puts the selection's HTML on the clipboard; Chromium-based browsers hand over plain text, so structure is recognised there only from Markdown markers. Copying with <kbd>Ctrl</kbd>+<kbd>C</kbd> and pressing <kbd>Super</kbd>+<kbd>Alt</kbd>+<kbd>C</kbd> can help, since the copy clipboard often carries HTML. |
| A formula is read as a jumble of words, or `doctor` says the Math helper is missing | `natural-tts apply` downloads the release's MathCAT helper (`~/.local/share/natural-tts/bin/natural-tts-mathcat`). Offline, or on a platform without a binary, build it: `natural-tts setup --helper-source /path/to/clone/helper/mathcat` (needs `cargo`). Until then formulas are read as words. |
| A formula is spoken in a way you do not want | `reading.math_style = "simplespeak"` is shorter; see the known misreadings under [FAQ](#faq). Formulas with unbalanced delimiters are read as words. |
| Upgrading left the old behaviour running | Since 0.1.2 `./install.sh` restarts the services. On an older install run `natural-tts apply` after `git pull && ./install.sh`. |

Logs: `journalctl --user -u natural-tts-kokoro.service` and
`journalctl --user -u natural-tts-piper.service`.

## FAQ

**How do I make text-to-speech on Linux sound natural?**
Replace the default espeak voice with a neural one. This project sets up
Piper as the system-wide Speech Dispatcher voice and Kokoro for a
read-anything hotkey, in one command.

**Why does Firefox "read aloud" sound robotic on Ubuntu?**
Firefox Reader View speaks through Speech Dispatcher, which uses espeak-ng
by default. After `./install.sh`, it uses Piper instead.

**Does it work offline? Is my text sent anywhere?**
After installation everything runs offline and on your machine. The
installer downloads the models once.

**Do I need a GPU?**
No. Kokoro is an 82M-parameter model and runs on a desktop CPU. With an
NVIDIA GPU, `./install.sh --gpu` uses CUDA.

**Does it work on Wayland? On KDE or other distributions?**
Wayland and X11 both work. Hotkeys are added automatically on GNOME;
on other desktops, bind `natural-tts read selection`, `natural-tts read
clipboard` and `natural-tts stop` in your keyboard settings. The installer
uses apt; other distributions need the equivalent packages.

**Can I use a different voice or language?**
Yes, see [Configuration](#configuration). The structure reading (headings,
lists, code) works with every Kokoro voice; the English word rules
(numbers, units, abbreviations, citations) run only for English voices.

**Why does it say "Figure three" when the text says "Fig. 3"?**
Because that is what a person reading aloud says. Since 0.2.0 the hotkey
rewrites numbers, dates, units, abbreviations and symbols into words
before Kokoro sees them, so `p < 0.05` is "p is less than zero point zero
five" rather than silence for the `<`. Everything is a readable rule; set
`reading.enabled = false` to hear the raw text instead.

**How do I fix the pronunciation of a word?**
Put it in `~/.config/natural-tts/lexicon.toml` with Kokoro's phonemes
(an example is in [Configuration](#configuration)) and run
`natural-tts apply`. The built-in list covers common species names,
Latin phrases and gene or method names.

**How is code read?**
Identifiers are split into words (`get_user_name` is "get user name"),
numbers are spoken, strings and comments are read as words, and operators
by name. `reading.code_level` decides how much punctuation you hear. Code
is recognised in Markdown, HTML, reStructuredText, LaTeX, Org, AsciiDoc,
shell transcripts, Python prompts, diffs and plain indented code. The code
voice is the reading voice.

**Does it read math?**
Yes, since 0.4.0. LaTeX between `$…$`, `$$…$$`, `\(…\)`, `\[…\]` or in
`equation`, `align` and similar environments, Unicode formulas on their
own line (`E = mc²`, as PDFs paste them), MathML on web pages (Firefox
hands it over; Wikipedia and MathJax pages carry the LaTeX too) are
converted to MathML and spoken by [MathCAT](https://nsoiffer.github.io/MathCAT/),
the engine behind NVDA's and Orca's math support, in ClearSpeak, the
style students understood best in the published comparison.
`reading.math_style = "simplespeak"` is terser. Nested fractions and
roots get spoken closers ("end fraction", "end root"). Spanish, French,
Portuguese and Chinese voices get MathCAT's rules for those languages;
other voices get English. Short fragments inside prose such as `x²`,
`5 ± 2` or `p < 0.05` keep the word rules. Known misreadings in this
release: the set-builder bar in `\{x \mid x > 2\}` is "divides",
`\mathbb{R}^n` is "the real numbers to the n-th power", the conditions
of a `cases` block run into their values, and `\text{m/s}` inside a
formula is spelled. Dollar amounts (`$5 and $10`) and shell variables
are never taken for formulas.

**What is the MathCAT helper?**
A 5 MB program, `natural-tts-mathcat`, built from the MathCAT Rust crate
with its speech rules embedded, started once by the daemon and kept
running. `setup` downloads it from this project's release for your
architecture and checks its SHA-256; `doctor` shows its version.

**How are company names, product names and acronyms read?**
As the speech engine reads them, since 0.5.0. Camel-case names (LinkedIn,
GitHub, PyTorch, OpenAI) and mixed tokens (mRNA, HbA1c, p53) go to the
engine whole; it looks the cased spelling up, splits what it does not
know and reads each half, so no list of brands is needed. Two- and
three-letter capital runs (ODE, DNA, GPU, US) are spelled as one word
with the stress on the last letter, the engine's own convention; longer
runs are the engine's: it spells what it does not know and says the
acronyms it knows as words (NASA, COVID, CRISPR). Mixed readings need an
entry: IEEE ("I triple E") and nineteen company names the engine misread
are packaged, and your `~/.config/natural-tts/lexicon.toml` takes the
rest. SQL stays "sequel". A sentence or heading written in capitals is
read as words.

**How are tables read?**
Caption first, then "Table with 3 rows and 3 columns", the column names
once, each row as "Row heading. Column: value. Column: value." with
"blank" for an empty cell, and "End of table". Rows get a longer pause
than cells. This follows the one published listening study of spoken
tables (header-value pairs with a pause hierarchy) and what NVDA reads in
say-all mode; two-row headers are joined ("Score, Dev"), spanning cells
repeat their value, and a Markdown table's first column names the row.

**Can I skip citation markers like [12] or (Smith et al., 2019)?**
They are skipped by default; `reading.citations = "read"` says them.

**How do I uninstall?**
`./install.sh --uninstall` removes services, configuration changes and
installed files. Settings in `~/.config/natural-tts` are kept.

## Development

```bash
uv venv --python 3.12 && uv pip install -e ".[dev]"
uv run pre-commit install
uv run pytest                      # unit tests with a coverage gate
dbus-run-session -- uv run pytest -m integration   # real gsettings
```

The code is test-driven, strictly typed (mypy `--strict`) and formatted
with ruff. All system access goes through small injectable interfaces, so
the unit tests run without audio hardware, Kokoro or a desktop session.
See [CONTRIBUTING.md](CONTRIBUTING.md).

## Credits

- [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) by hexgrad (Apache-2.0)
- [Piper](https://github.com/OHF-Voice/piper1-gpl) by the Open Home Foundation (GPL-3.0-or-later)
- [Speech Dispatcher](https://github.com/brailcom/speechd) (GPL-2.0-or-later)

natural-tts itself is released under the [MIT license](LICENSE).
