# Changelog

All notable changes are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.6.2] - 2026-10-25

### Fixed

- Installation broke on 2026-10-24 when `preshed` 3.0.14 was released: every
  `spacy.load()` (used by Kokoro's phonemizer) raised "OverflowError: Python
  int too large to convert to C ssize_t". The Kokoro extra pins
  `preshed<3.0.14` until the upstream fix ships (spaCy issue 14058).


## [0.6.1] - 2026-10-22

### Fixed

- A call with several arguments (`f(x, y)`, `N(\mu, \sigma^2)`) was spoken
  with "open paren … close paren"; it is "f of x, y" now.
- An abbreviation read as words at the end of a sentence (`p.o.`)
  swallowed the full stop, running two sentences together.
- A variant or enzyme name followed by sentence punctuation was left
  unread.

### Changed

- The MathCAT helper's version is tracked separately from the package's,
  so a package patch release no longer downloads a new helper.
- The README is written as a product page; the release history lives in
  this changelog.


## [0.6.0] - 2026-10-22

### Added

- Formulas are read the way experts read them. Conditional probability
  is "probability of theta given D" for `P`, `Pr` and `p` (the bar
  `\mid` was read "divides"); expectation, variance, covariance,
  correlation, standard deviation, transpose, inverse, norm and binomial
  coefficients are named; `X \sim N(\mu, \sigma^2)` is "X is distributed
  as", `\perp` "is independent of", `\arg\max_\theta` "arg max over theta
  of", `\nabla \cdot` "the divergence of", `\nabla^2` "the Laplacian of",
  `|\psi\rangle` "ket psi", `\langle A \rangle` "the expectation value
  of A", a two-sided Dirac bracket its contents only. Capital letters are
  no longer announced ("cap p"), every fraction is "a over b" ("end
  fraction" only when nested), juxtaposed factors drop "times", compound
  exponents are "e to the negative x squared", and `\ln` is "natural
  log". Units inside formulas are read as words ("5 meters per second").
  All of this is written into the MathML by `reading.intent` and spoken
  by the unchanged MathCAT helper, which now takes any preference on its
  protocol (`@Name=Value`).
- Life-science notation: HGVS variants ("c dot one twenty-three, A to
  G", "p dot arg one seventy-five his"), karyotypes ("forty-six, X Y,
  translocation between nine and twenty-two, q thirty-four, q eleven"),
  chromosome bands, genotypes ("knockout", "heterozygous"), restriction
  enzymes ("Eco R one"), three-digit identifiers as said ("HEK two
  ninety-three"), GWAS and SNP as words, flox alleles, Black 6 strains,
  dosing abbreviations by their ISMP replacements ("twice daily", "by
  mouth"), and h bar.
- Chemistry: common compounds are named in prose (carbon dioxide,
  sulfuric acid, glucose, ethanol, and thirty more from the UEfAP list);
  equations keep the spelled register.
- Units come from one table generated from MathCAT's definitions (NIST
  spellings): 117 units, every SI prefix, pressure, astronomy and lab
  units included; single letters other than the few written attached
  need a space after the number.

### Changed

- The helper protocol is `@Name=Value`; the 0.4.0 `@Style Verbosity`
  form is gone. Helper 0.6.0 is required (`setup` installs it).
- Compound exponents, the natural log and the conditional bar are no
  longer rewritten in the LaTeX; the MathML producer handles them.


## [0.5.0] - 2026-10-22

### Added

- Company and product names are read the way the engine reads them:
  LinkedIn, GitHub, PyTorch, NumPy and OpenAI are no longer split and
  spelled ("Linked I n", "P y Torch"). Nineteen names the engine still
  misread (Xiaomi, Huawei, Jupyter, Qt, Keras, Shein, Airbnb, SUSE, …) and
  IEEE ("I triple E") come from the packaged lexicon.
- Two- and three-letter initialisms (ODE, PDE, DNA, US, SEM), their plurals
  and possessives, dotted ones (U.S., Ph.D.) and the letters of chemical
  formulas are spoken as one word with the stress on the last letter, the
  engine's own convention, instead of three separate stressed letters.
- A heading or sentence written in capitals is read as words, not spelled.
- Alphanumeric codes read the capital run and short digit groups as
  numbers (GPT-4o is "G P T four o"); Roman numerals after Chapter,
  Section, Part and similar words are read as numbers; `.NET` is "dot net";
  `70B` and `3.5M` keep their letter, while `$18.5M` is "eighteen point five
  million dollars".
- Tables are read as their caption, "Table with N rows and M columns", the
  column names once, each row as "Heading. Column: value." sentences with
  "blank" for empty cells, and "End of table"; rows get a longer pause.
  HTML captions, two-row headers, spanning cells and row headers are
  understood; a Markdown table's first column names the row.
- `doctor` checks that the engine's espeak fallback imports, since
  camel-case names depend on it.

### Fixed

- The gsettings integration test ran on the developer's own D-Bus session
  and its cleanup reset the desktop's whole custom-shortcut list. It now
  runs on a private session with a private dconf database and checks that
  the desktop's list is untouched.
- The normaliser throughput test used an absolute budget that a shared CI
  runner could miss by a few milliseconds; it is a ratio test now.

## [0.4.0] - 2026-10-22

### Added

- Formulas are read aloud on the hotkey path. LaTeX between `$…$`,
  `$$…$$`, `\(…\)`, `\[…\]` and in equation environments, Unicode
  formulas such as `E = mc²` on their own line, MathML on web pages and
  MathJax annotations are converted to MathML and spoken by MathCAT in
  ClearSpeak (`reading.math_style = "simplespeak"` switches). Inline
  formulas stay inside their sentence; display formulas become their own
  segments with MathCAT's pauses. Nested expressions get the verbose
  closers ("end fraction", "end root"). The MathCAT language follows the
  Kokoro voice for Spanish, French, Portuguese and Chinese.
- `natural-tts-mathcat`, a small helper binary built from the MathCAT
  crate with its rules embedded. `setup` and `apply` download the
  release's binary for the machine's architecture and verify its
  checksum; `setup --helper-source helper/mathcat` builds it with cargo
  when the download is not possible. `doctor` reports the helper's
  version. Without the helper formulas are read as words.
- `P(A \mid B)` is spoken as "given", also inside longer equations;
  `\ln` as "natural log of".

### Changed

- Formula delimiters are found in one linear pass, so text full of
  unmatched `$` or `\[` no longer slows the first segment.
- Ubuntu 22.04 or newer is required for the helper binary (glibc 2.34).


## [0.3.0] - 2026-10-22

### Added

- Structure on the hotkey path: headings, list items (numbered when the
  list is), quotes and tables are spoken as their own segments with
  pauses and a slower heading rate; tables announce their shape first.
  Markdown is read from its block structure, and the selection's HTML is
  used when the application offers it (Firefox does; Chromium offers
  plain text), parsed with the standard library and never fetched.
- Code blocks are read aloud at `reading.code_level` 1, 2 or 3:
  identifiers split into words, numbers spoken, strings and comments read
  as words, operators by name, brackets and indentation from level 2.
  Code is recognised in Markdown fences and indented blocks, HTML `pre`,
  reStructuredText literal blocks and code directives, LaTeX verbatim,
  lstlisting and minted, Org mode and AsciiDoc source blocks, Python and
  IPython prompts, terminal transcripts, unified diffs, a shebang, and
  dense unmarked code. Inline code is read the same way inside prose.
- Messages between the hotkey and the daemon carry their format.

### Changed

- Non-English Kokoro voices now get the structure (segments, pauses,
  code reading) while the English word rules stay English-only.
- `markdown-it-py` and `Pygments`, already present through Kokoro's
  dependencies, are declared in the `kokoro` and `dev` extras. The core
  package and the Speech Dispatcher path stay standard-library only,
  which a test now proves.
- The code voice is the reading voice; there is no `code_voice` setting.

## [0.2.1] - 2026-10-22

### Fixed

- The first segment of a long selection no longer waits for the whole
  text to be cleaned: windows are cut on the raw text and cleaned one at
  a time, and the built-in lexicon is compiled once. On a slow machine
  the 1 MiB case took 76 ms before the first word; it now takes about
  5 ms.

## [0.2.0] - 2026-10-22

### Added

- Content-aware reading on the Kokoro hotkey path (`[reading]` in
  `settings.toml`, on by default for English voices): numbers, dates,
  times, versions, currency, units with SI prefixes, ranges, scientific
  notation, scholarly and general abbreviations (`Fig. 3` is "Figure
  three", `et al.` stays "et al", `St. Louis` is "Saint Louis"), math
  symbols and Greek letters, chemical formulas and gene-style tokens are
  spoken as words; URLs read as their domain and path; citation markers
  such as `[12]` are skipped (`citations = "read"` says them). Markdown
  links no longer vanish into Kokoro's pronunciation syntax.
- A pronunciation lexicon for species names, Latin phrases and gene or
  method names (`E. coli`, `in vitro`, `Cas9`), with a user file at
  `~/.config/natural-tts/lexicon.toml` merged on top.
- Segments: the engine speaks typed segments with their own pause, speed
  and voice, prepared lazily so a long selection starts as fast as a
  short one.

### Changed

- `natural-tts setup` writes booleans as TOML literals in the settings
  template.

## [0.1.2] - 2026-10-21

### Fixed

- `natural-tts setup` (and so `./install.sh`) restarts the Piper and
  Kokoro services instead of only enabling them, so an upgrade with
  `git pull && ./install.sh` takes effect without a reboot. A service
  that fails to restart is now reported instead of ignored.
- The Kokoro chunker no longer ends a chunk after English
  abbreviations such as `Dr.`, `Fig.`, `Eq.` and `et al.`, after a
  single-letter initial, or at punctuation inside matched brackets, so
  `(n = 3; p < 0.05)` is read in one breath.

## [0.1.1] - 2026-10-21

### Changed

- README: each engine's sample now plays inline as a waveform video
  that lights up as it is spoken, followed by a table comparing the
  engines' sound, role, hardware, model size and license.
- `scripts/make-samples.sh` regenerates the MP3 samples and calls the
  new `scripts/render_samples.py`, which renders the three videos with
  ffmpeg alone (from PATH, `--ffmpeg`, or the `imageio-ffmpeg` package).

## [0.1.0] - 2026-10-21

### Added

- `install.sh`: one-command installation on Ubuntu with CPU or CUDA
  PyTorch; the ALSA plugin package is chosen to match the running sound
  server (PipeWire or PulseAudio).
- Piper as the system-wide Speech Dispatcher voice, served from a
  localhost-only HTTP server so each sentence starts quickly; the
  speed slider in Firefox Reader View controls Piper's speed.
- Kokoro read-aloud daemon with GNOME hotkeys: Super+Alt+R (highlighted
  text), Super+Alt+C (clipboard) and Super+Alt+S (stop).
- PDF-aware text chunking: hyphenated line breaks are re-joined and
  chunks are sized for natural Kokoro prosody.
- `natural-tts doctor`: checks every component and prints fixes.
- `natural-tts setup`, `apply` and `teardown`, driven by a single
  `~/.config/natural-tts/settings.toml`.

[Unreleased]: https://github.com/mahdi-shafiei/ubuntu-natural-tts/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/mahdi-shafiei/ubuntu-natural-tts/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/mahdi-shafiei/ubuntu-natural-tts/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/mahdi-shafiei/ubuntu-natural-tts/compare/v0.1.2...v0.2.0
[0.1.2]: https://github.com/mahdi-shafiei/ubuntu-natural-tts/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/mahdi-shafiei/ubuntu-natural-tts/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/mahdi-shafiei/ubuntu-natural-tts/releases/tag/v0.1.0
