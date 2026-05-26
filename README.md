# MCQ Grader Suite

An automated suite of tools for grading multiple-choice question (MCQ) answer sheets, covering the entire workflow from LaTeX source to the final graded results.

## Overview

This project leverages a combination of LaTeX processing, computer vision with OpenCV, and Python scripts to achieve a high degree of automation and accuracy in grading exams. It combines LaTeX-generated zone metadata, OpenCV-based sheet alignment, Optical Mark Recognition (OMR), OCR for header fields, CSV processing.

The entire workflow is orchestrated by a `Makefile` and can run in a reproducible Nix environment, ensuring consistency and ease of use.

The bundled example under `sample-data/exams/` was generated with [ExamForge](https://github.com/romildo/ExamForge). It contains 10 exam variants, one answer key CSV with one row per variant, and an anonymized scanned answer-sheet PDF.

## Key Features

  * **Automated zoning via LaTeX**: zone coordinates for answer bubbles, header fields, and bubble-encoded registration numbers are extracted directly from LaTeX compilation (`.aux` and `.zonas`) files, eliminating the need for manual mapping.
  * **High-precision alignment**: utilizes fiducial markers (marks in the corners of the page) when available for precise geometric alignment, accurately correcting rotation and scale distortions.
  * **Robust fallback alignment**: for older answer sheets without markers, the system automatically falls back to a robust affine alignment method based on image features.
  * **Image caching**: the conversion of PDFs to images (the slowest step) is performed only once. Images are saved to a cache directory for instant reuse in subsequent runs.
  * **Bubble-encoded registration numbers**: newer ExamForge answer sheets can encode the student registration number as digit bubbles (`id_1_0` through `id_N_9`), avoiding fragile OCR for student identifiers.
  * **Complex grading logic**: supports questions with multiple correct answers using distinct modes:
      * **Inclusive OR** (e.g., `A+B`): the student is correct if they mark any non-empty subset of the correct answers, without marking any incorrect ones.
      * **Exclusive AND** (e.g., `AB`): the student must mark *exactly* all correct answers and no others.
      * **Single exact answers** (e.g., `B`).
  * **Makefile-driven workflow**: the entire process is managed by a `Makefile`, ensuring that only the necessary steps are executed based on file dependencies.
  * **Optional reproducible environment**: system and package dependencies are defined in `shell.nix` for users who want a Nix-based development shell.

## Project Structure

```text
mcq-grader/
|-- .gitignore
|-- LICENSE
├── Makefile                # Main workflow orchestrator
├── README.md               # This documentation
├── shell.nix               # Optional Nix development environment
├── scripts/                # Python source code
│   ├── generate_zones.py
│   ├── grade_exams.py
│   ├── map_zones_manually.py
│   ├── omr_utils.py
│   ├── process_sheets.py
│   └── verify_zones.py
└── sample-data/            # Example files to demonstrate the tool
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

## How It Works

The system follows a clear data processing pipeline:

1.  **LaTeX compilation:** the `.tex` source file is compiled, generating a main PDF and auxiliary files (`.aux`, `.zonas`) containing precise coordinate data for all defined zones.
2.  **Zone generation:** `generate_zones.py` parses the auxiliary files and creates an image-coordinate `zones.json` map from the LaTeX metadata. If the LaTeX metadata contains `registration_digits` and `id_<position>_<digit>` zones, the generated map includes a registration bubble grid.
3.  **Answer extraction:** `process_sheets.py` reads the scanned student sheets, uses the `zones.json` map to align the image and locate the answers, performs Optical Mark Recognition (OMR), decodes bubble registration numbers when present, and saves the results to a CSV file.
4.  **Grading:** `grade_exams.py` compares the extracted answers with the answer key, applies the grading logic, and produces the final CSV with scores.

## Prerequisites

* Python with OpenCV, pandas, Pillow, pytesseract, NumPy, Poppler tools, qpdf, and Tesseract available.
* LaTeX tooling is required when generating zones from `.tex` sources. The bundled ExamForge sample uses `minted`, so it needs shell escape and Pygments.
* Optional: use `nix-shell` to enter the reproducible environment declared in `shell.nix`.


System tools:

```bash
latexmk
lualatex
qpdf
pdftoppm
tesseract
pygmentize
```

Python packages:

```bash
opencv-python
numpy
pandas
Pillow
pytesseract
```

With Nix installed, enter the provided environment with:

```bash
nix-shell
```

## Bundled Example

The default `Makefile` configuration runs the bundled ExamForge example:

```make
EXAMS_DIR   := sample-data/exams
EXAM_PREFIX := $(EXAMS_DIR)/EE1
LATEX_SRC   := EE1-01.tex
```

`EE1.keys.csv` contains keys for variants `1` through `10`. The selected LaTeX source is used to generate the blank answer-sheet template. The scanned student-sheet PDF contains anonymized sample sheets from the same exam family.

Because the example uses `minted`, the Makefile enables shell escape through:

```make
LATEXMK_FLAGS ?= -shell-escape
```

## Usage Guide

### 1\. Preparation

* Place the Python scripts in the directory defined by the `SCRIPTS_DIR` variable in the `Makefile` (e.g., `scripts/`).
* Place your exam source files in the `EXAMS_DIR` (e.g., `sample-data/exams/`). This includes:
    * The main `.tex` file for your exam.
    * The `provastyle.sty` file (ensure it contains the fiducial marker definitions).
    * The answer key `.csv` file.
    * The scanned PDF of the filled-out student answer sheets.
    * For bubble registration, the LaTeX-generated `.zonas` data must include `registration_digits` and zones named `id_1_0` through `id_N_9`.

### 2\. Configuration

* Open the `Makefile` in a text editor.
* Adjust the variables in the "Project Configuration" section to match your filenames (e.g., `EXAM_PREFIX`, `LATEX_SRC`).
* Adjust the "Fine-tuning Parameters" (`PADDING`, `THRESHOLD`, `CONF_RATIO`, `REG_CONF_RATIO`) as needed for your scanning conditions.

### 3\. Execution

* Open your terminal in the project's root directory.
* If you use Nix, start the development environment:
  ```bash
  nix-shell
  ```
* To run the entire workflow and generate the final graded spreadsheet:
  ```bash
  make grade
  # or simply:
  make
  ```
* To generate a visual verification PDF before trusting results (highly recommended):
  ```bash
  make verify
  ```
* To clean generated CSVs, verification PDFs, template PDFs, and LaTeX build output:
  ```bash
  make clean
  ```
* To clean generated files and the image cache:
  ```bash
  make clean-all
  ```
* For another exam, override or edit the Makefile variables:
  ```bash
  make \
    EXAMS_DIR=path/to/exams \
    EXAM_PREFIX=path/to/exams/my-exam \
    LATEX_SRC=My-Exam-01.tex
  ```

### Fine-Tuning and Special Cases

* **Tuning parameters:** you can experiment with different `PADDING`, `THRESHOLD`, `CONF_RATIO`, and registration confidence values without editing the `Makefile` by passing them on the command line:
  ```bash
  make PADDING=5 THRESHOLD=1500
  make CONF_RATIO=0.75
  make REG_CONF_RATIO=0.85
  ```
  Registration bubbles automatically cap their effective padding so tightly spaced digit bubbles do not overlap neighboring rows or columns.
* **Manual zone adjustment:** if you need to manually fix a zone for sheets without proper LaTeX metadata:
  1.  Run `make map-manual`.
  2.  Capture the coordinates for the desired zone.
  3.  Manually edit the generated `.zones.json` file, replacing the coordinates for the relevant key.
  4.  Run `make` again. The `Makefile` will not overwrite an edited `.zones.json` unless the source metadata is regenerated (e.g., the LaTeX files are modified).

### Answer Key Format for Multiple Answers

The answer key CSV file (`.keys.csv`) supports a special syntax for complex questions:

* **`A+C` (Inclusive OR):** The student is correct if they mark `A`, `C`, or `A,C`, but no other options.
* **`AC` (Exclusive AND):** The student is correct **only** if they mark both `A` and `C`, and no other options.
* **`B` (Exact single answer):** The student is correct only if they mark `B`.
