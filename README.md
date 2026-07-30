# MCQ Grader Suite

MCQ Grader automates the grading of multiple-choice answer sheets, from a
LaTeX exam source to a final CSV with per-question results and scores.

The workflow combines LaTeX-derived zone metadata, PDF rendering, OpenCV
alignment, Optical Mark Recognition (OMR), limited OCR for header fields, and
CSV-based grading. A `Makefile` orchestrates the complete pipeline.

The bundled example under `sample-data/exams/` was generated with
[ExamForge](https://github.com/romildo/ExamForge). It contains ten exam
variants, an answer-key CSV, and anonymized scanned answer sheets.

## Features

- **LaTeX-derived zones:** extracts answer, header, and registration-grid
  geometry from `.aux` and `.zonas` files.
- **Three-marker alignment:** detects the printed top-left, top-right, and
  bottom-left fiducial markers and computes a full affine transform. This
  corrects translation, rotation, shear, and independent horizontal and
  vertical scaling.
- **Feature-based fallback:** uses ORB feature matching when direct fiducial
  detection is unavailable.
- **Bubble registration numbers:** reads student registration numbers from
  digit grids such as `id_1_0` through `id_N_9`.
- **Legacy header OCR:** keeps text-based student ID and name extraction as a
  fallback for older answer sheets.
- **Exam-type normalization:** normalizes OCR/CSV values such as `01`, `o1`,
  and `O1` before answer-key lookup.
- **PDF image caching:** renders template and student PDFs at 300 DPI and reuses
  namespaced PNG files on later runs.
- **Multiple-answer grading:** supports exact single answers, exclusive AND,
  and inclusive OR answer-key semantics.
- **Makefile workflow:** rebuilds only targets whose file dependencies are
  newer.
- **Optional Nix environment:** `shell.nix` provides the development and
  runtime dependencies without making Nix mandatory.

## Project Structure

```text
mcq-grader/
├── .gitignore
├── LICENSE
├── Makefile
├── README.md
├── shell.nix
├── scripts/
│   ├── generate_zones.py
│   ├── grade_exams.py
│   ├── map_zones_manually.py
│   ├── omr_utils.py
│   ├── process_sheets.py
│   └── verify_zones.py
└── sample-data/
    └── exams/
        ├── E1-01.tex
        ├── E1-02.tex
        ├── ...
        ├── E1-10.tex
        ├── E1.keys.csv
        ├── E1.student-sheets.pdf
        ├── provastyle.sty
        └── image-cache/
            └── .gitkeep
```

Generated files such as `_build/`, cached PNG files, zone maps, template PDFs,
verification PDFs, extracted results, and graded results are not intended to be
committed.

## Processing Pipeline

1. **Compile LaTeX.** `latexmk` runs LuaLaTeX and produces the exam PDF plus
   `.aux`, `.zonas`, and `.log` metadata.
2. **Generate zones.** `generate_zones.py` converts TeX coordinates to 300-DPI
   image coordinates and writes `*.zones.json`.
3. **Extract the template.** `qpdf` copies the penultimate page of the generated
   exam PDF to `*.template-sheet.pdf`.
4. **Render PDFs.** `pdftoppm` converts the template and scanned student PDF to
   cached PNG images.
5. **Align sheets.** MCQ Grader detects the three printed fiducials and warps
   each student sheet into template coordinates. Feature matching is used as a
   fallback.
6. **Read headers and bubbles.** The scripts decode registration bubbles,
   normalize the exam type, and classify answer bubbles.
7. **Write extracted results.** `*.results.csv` contains identifiers, exam type,
   answers, and per-question confidence columns.
8. **Grade.** `grade_exams.py` compares the extracted answers with
   `*.keys.csv`, annotates incorrect answers, removes confidence columns, and
   writes `*.graded-results.csv`.

## Prerequisites

System tools:

```text
latexmk
lualatex
qpdf
pdfinfo
pdftoppm
tesseract
pygmentize
```

Python packages:

```text
opencv-python
numpy
pandas
Pillow
pytesseract
Pygments
```

The bundled ExamForge example uses `minted`, so its LaTeX build requires shell
escape and the `pygmentize`/`latexminted` tooling provided by a suitable TeX and
Pygments installation.

Nix is optional. With Nix installed, enter the provided environment with:

```bash
nix-shell
```

Otherwise, use an existing Python/LaTeX environment containing the
dependencies above.

## Quick Start

Run the bundled example from the repository root:

```bash
make verify
make grade
```

`make` and `make all` are aliases for the grading workflow:

```bash
make
```

Inspect the final files under `sample-data/exams/`:

```text
E1.verification.pdf
E1.results.csv
E1.graded-results.csv
```

Review `E1.verification.pdf` before trusting the grading output. The rectangles
should remain centered on the printed fields and bubbles from the top to the
bottom of every page.

## Exam Prefix and File Convention

`EXAM_PREFIX` is the canonical location of an exam. It contains both the
directory and the common filename prefix.

For example:

```bash
make EXAM_PREFIX=bcc222.2026-1/exams/exams/EE2 show-config
```

Given the prefix:

```text
bcc222.2026-1/exams/exams/EE2
```

the Makefile derives these defaults:

| Purpose | Derived path |
|---|---|
| First LaTeX variant | `bcc222.2026-1/exams/exams/EE2-01.tex` |
| Style file | `bcc222.2026-1/exams/exams/provastyle.sty` |
| Answer keys | `bcc222.2026-1/exams/exams/EE2.keys.csv` |
| Scanned sheets | `bcc222.2026-1/exams/exams/EE2.student-sheets.pdf` |
| Zone map | `bcc222.2026-1/exams/exams/EE2.zones.json` |
| Blank template | `bcc222.2026-1/exams/exams/EE2.template-sheet.pdf` |
| Extracted answers | `bcc222.2026-1/exams/exams/EE2.results.csv` |
| Graded results | `bcc222.2026-1/exams/exams/EE2.graded-results.csv` |
| Verification PDF | `bcc222.2026-1/exams/exams/EE2.verification.pdf` |
| LaTeX intermediates | `bcc222.2026-1/exams/exams/_build/` |
| Rendered images | `bcc222.2026-1/exams/exams/image-cache/` |

Cached files include the exam name, avoiding collisions when multiple exams
share the same directory:

```text
EE2.template-sheet-1.png
EE2.student-sheets-1.png
EE2.student-sheets-2.png
```

For a conventional exam, only `EXAM_PREFIX` is needed:

```bash
make EXAM_PREFIX=bcc222.2026-1/exams/exams/EE2 verify
make EXAM_PREFIX=bcc222.2026-1/exams/exams/EE2 grade
```

Use `show-config` whenever a path is unexpected:

```bash
make EXAM_PREFIX=path/to/EE2 show-config
```

### Nonstandard file locations

Derived paths remain overridable. For example:

```bash
make \
  EXAM_PREFIX=bcc222.2026-1/exams/exams/EE2 \
  STYLE_FILE=bcc222.2026-1/latex/provastyle.sty \
  ANSWER_KEYS_CSV=bcc222.2026-1/keys/EE2.csv \
  verify
```

Common path overrides are:

```text
LATEX_SRC
STYLE_FILE
BUILD_DIR
CACHE_DIR
ANSWER_SHEETS_PDF
ANSWER_KEYS_CSV
ZONES_JSON
TEMPLATE_PDF
RESULTS_CSV
GRADED_CSV
VERIFICATION_PDF
SCRIPTS_DIR
PYTHON
```

The scripts are resolved relative to the Makefile rather than the current
directory. MCQ Grader can therefore be used from another project without
copying its scripts:

```bash
make -f /path/to/mcq-grader/Makefile \
  EXAM_PREFIX="$PWD/exams/EE2" \
  verify
```

Use an absolute `EXAM_PREFIX` in that form.

## Make Targets

| Target | Result |
|---|---|
| `make`, `make all`, `make grade` | Run the complete pipeline and produce the graded CSV |
| `make verify` | Produce the visual zone-verification PDF |
| `make show-config` | Print all paths derived from `EXAM_PREFIX` |
| `make map-manual` | Open the template in the OpenCV manual zone mapper |
| `make clean` | Remove generated results, verification/template PDFs, and LaTeX artifacts for the selected exam |
| `make clean-all` | Run `clean` and also remove cached PNG files for the selected exam |

Cleanup is scoped by `EXAM_PREFIX`; it does not delete another exam's
namespaced cache files or build artifacts.

## Fine-Tuning and Special Cases

The defaults are defined in the Makefile:

```make
PADDING        ?= 10
THRESHOLD      ?= 1000
CONF_RATIO     ?= 0.7
REG_CONF_RATIO ?= 0.8
```

Override them on the command line rather than editing the Makefile:

```bash
make EXAM_PREFIX=path/to/EE2 PADDING=5 THRESHOLD=1500 grade
make EXAM_PREFIX=path/to/EE2 CONF_RATIO=0.75 REG_CONF_RATIO=0.85 grade
```

### `PADDING`

`PADDING` is the number of pixels added around every mapped rectangle before
OCR or bubble scoring. The same value is also used when drawing the answer and
header rectangles in the verification PDF.

Default:

```text
10 pixels
```

Effects:

- Increasing it tolerates small residual alignment or zone-coordinate errors.
- Increasing it also includes more printed borders, text, noise, or neighboring
  bubbles and can create false marks.
- Decreasing it isolates the intended bubble more tightly.
- Decreasing it too far can crop part of a filled mark.

Registration bubbles are often closer together than answer bubbles. Their
effective padding is automatically capped so one registration ROI does not
overlap adjacent digit rows or columns.

Start with `PADDING=10`. If verification rectangles are centered but bubble
outlines from adjacent options enter the ROI, try `PADDING=5` or a nearby
value.

### `THRESHOLD`

`THRESHOLD` is the minimum absolute bubble score needed to consider a question
or registration position marked.

For each candidate bubble, MCQ Grader:

1. expands the zone by `PADDING`;
2. converts it to grayscale;
3. applies inverted Otsu thresholding;
4. counts the resulting nonzero, dark pixels.

If the highest score in a bubble group is below `THRESHOLD`, the result is
`BLANK`.

Default:

```text
1000 dark pixels
```

Tuning direction:

- Increase `THRESHOLD` when empty printed bubbles, scanner noise, or shadows are
  being interpreted as marks.
- Decrease `THRESHOLD` when valid light or incomplete marks are being reported
  as blank.

The score is an absolute pixel count. It depends on the rendered resolution,
bubble size, and padding. Zone generation and PDF rendering currently assume
300 DPI, so changing image resolution requires retuning and may invalidate the
zone geometry.

### `CONF_RATIO`

`CONF_RATIO` controls which answer options count as marked relative to the
strongest option for that question.

After the absolute threshold is passed, an option is selected when:

```text
option_score >= strongest_score * CONF_RATIO
```

Default:

```text
0.7
```

Expected range:

```text
0.0 to 1.0
```

Tuning direction:

- Increase it to reject weak secondary marks, erasures, or nearby noise.
- Decrease it when legitimately selected options in multi-answer questions
  differ noticeably in fill strength.
- A value that is too high can hide a lightly filled second answer.
- A value that is too low can turn noise into an unintended multiple answer.

Example: with `CONF_RATIO=0.7` and a strongest score of `2000`, every option
scoring at least `1400` is considered marked.

### `REG_CONF_RATIO`

`REG_CONF_RATIO` applies the same relative-score rule to each column of the
bubble-encoded registration number.

Default:

```text
0.8
```

It is intentionally stricter than the answer ratio because exactly one digit
should be selected per registration position.

- Increase it when neighboring or partially erased registration bubbles create
  ambiguous digits.
- Decrease it only when clearly filled registration digits are being lost
  because mark strength varies substantially.

A blank or ambiguous registration position is written as `?` and reported as
a warning. Review such rows before using the results.

### Recommended tuning workflow

1. Run `make ... verify` and inspect alignment and zone placement.
2. Fix geometry/alignment problems before changing OMR thresholds.
3. Adjust `PADDING` until each rectangle covers the intended mark without
   including neighboring bubbles.
4. Adjust `THRESHOLD` to separate blank bubbles from genuinely filled bubbles.
5. Adjust `CONF_RATIO` only after the absolute threshold behaves correctly.
6. Tune `REG_CONF_RATIO` separately if registration digits remain ambiguous.
7. Regenerate `*.results.csv`, then grade again.

Make tracks file timestamps, not command-line variable values. If a result
already exists, changing only `PADDING`, `THRESHOLD`, `CONF_RATIO`, or
`REG_CONF_RATIO` may leave the target up to date. Remove the affected outputs
or clean the selected exam before rerunning. For example:

```bash
rm -f path/to/EE2.results.csv path/to/EE2.graded-results.csv
make EXAM_PREFIX=path/to/EE2 PADDING=5 THRESHOLD=1500 grade
```

For verification-only changes:

```bash
rm -f path/to/EE2.verification.pdf
make EXAM_PREFIX=path/to/EE2 PADDING=5 verify
```

### Fiducial alignment

The preferred alignment path detects three black square markers directly in
the template and scanned images:

```text
top-left
top-right
bottom-left
```

Successful runs print messages indicating detected-fiducial alignment. If a
marker cannot be detected, MCQ Grader tries legacy marker-zone alignment and
then feature-based affine alignment.

When verification rectangles drift progressively down or across the page,
check the alignment messages first. A feature-based fallback may be less
precise for scanner-induced non-uniform scaling than the three-marker full
affine transform.

Keep the corner markers:

- solid black;
- approximately square;
- unobstructed by handwriting, staples, clipping, or scanning;
- inside the scanned page;
- in the expected corner regions.

### Bubble-encoded registration numbers

When the LaTeX metadata contains:

```text
registration_digits
id_1_0 ... id_1_9
id_2_0 ... id_2_9
...
id_N_0 ... id_N_9
```

`generate_zones.py` writes a registration grid into the zone map and
`process_sheets.py` uses it in preference to OCR.

For these sheets:

- `Student_ID` contains the decoded digit string;
- `Student_Name` is left blank;
- blank or ambiguous digit positions become `?`.

When the registration grid is absent, legacy `student_id` and `student_name`
text zones are read with Tesseract OCR.

### Exam-type OCR normalization

The exam variant is still read from the `exam_type` text zone. Common OCR
confusions are normalized before writing results and again before answer-key
lookup. Examples include:

```text
01  -> 1
o1  -> 1
O1  -> 1
1O  -> 10
```

The answer key must contain one unique `Exam_Type` row after normalization.
Duplicate normalized variants are rejected.

### Cache invalidation

Cached images are reused whenever matching PNG filenames already exist. The
current cache check is filename-based; it does not compare PDF modification
times or content hashes.

After replacing either PDF, remove the selected exam's cached images:

```bash
make EXAM_PREFIX=path/to/EE2 clean-all
```

Then rerun `verify` or `grade`.

Do this especially after:

- rescanning student sheets;
- replacing the template PDF;
- changing page count or order;
- changing the exam prefix while reusing manually named cache files.

### Manual zone adjustment

Manual mapping is a fallback for missing or incorrect LaTeX metadata:

```bash
make EXAM_PREFIX=path/to/EE2 map-manual
```

In the OpenCV window:

1. drag a rectangle around the desired region;
2. copy the printed `[x, y, width, height]` coordinates;
3. edit the relevant entry in `*.zones.json`;
4. rerun verification before grading.

Press `r` to clear drawn rectangles and `q` to exit.

Manual edits may be overwritten when the `.aux` or `.zonas` dependencies
become newer and the zone map is regenerated. Prefer fixing the LaTeX zone
metadata when the problem affects every exam generated from the same style.

## Answer Key Format

The answer-key CSV contains one row per exam variant and columns named
`Exam_Type`, `Q1`, `Q2`, and so on.

Example:

```csv
Exam_Type,Q1,Q2,Q3
1,B,AC,A+C
2,D,B,C
```

Answer semantics:

- `B`: exact single answer; only `B` is correct.
- `AC`: exclusive AND; the student must mark exactly `A` and `C`.
- `A+C`: inclusive OR; the student may mark `A`, `C`, or both, but no incorrect
  option.

A blank key cell is not considered correct.

In the graded CSV, an incorrect answer is annotated as:

```text
student_answer~correct_answer
```

For example:

```text
B~C
BLANK~A
```

## Troubleshooting

### Verification uses feature-based fallback on every page

Check that all three fiducial markers are visible in both the blank template
and each scanned sheet. Cropped, gray, distorted, or obstructed markers may
prevent direct detection.

### Verification rectangles are consistently shifted

Inspect the template and generated `*.zones.json`. A uniform shift usually
indicates incorrect zone geometry or a template mismatch. Use `map-manual` to
measure the discrepancy, but fix the LaTeX metadata when possible.

### Verification rectangles drift from top to bottom

Confirm that direct three-marker alignment succeeded. The full affine
transform corrects independent vertical scaling; the feature-based fallback
may not correct it as accurately.

### Valid marks are reported as `BLANK`

Lower `THRESHOLD` gradually after confirming that alignment and `PADDING` are
correct.

### Empty bubbles are reported as selected

Raise `THRESHOLD`, reduce `PADDING`, or both.

### Too many multiple answers are detected

Increase `CONF_RATIO`. If this happens only in the registration grid, increase
`REG_CONF_RATIO`.

### Registration contains `?`

The corresponding digit position was blank or more than one bubble had a score
close to the strongest mark. Inspect the verification PDF and the original
scan, then adjust registration confidence only if the geometry is correct.

### Answer key not found for an exam type

Inspect the extracted `Exam_Type` in `*.results.csv` and the `Exam_Type` column
in `*.keys.csv`. Values are normalized, but the normalized result must still
match exactly one answer-key row.

### Updated PDFs are not reflected in the output

The cached PNGs are probably being reused. Run `clean-all` for the selected
exam and process it again.
