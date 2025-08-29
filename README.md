# MCQ Grader Suite

An automated suite of tools for grading multiple-choice question (MCQ) answer sheets, covering the entire workflow from LaTeX source to the final graded results.

## Overview

This project leverages a combination of LaTeX processing, computer vision with OpenCV, and Python scripts to achieve a high degree of automation and accuracy in grading exams. The entire workflow is orchestrated by a `Makefile` and runs in a reproducible Nix environment, ensuring consistency and ease of use.

## Key Features

  * **100% Automated Zoning via LaTeX**: Zone coordinates for all answer bubbles and header fields are extracted directly from LaTeX compilation files, eliminating the need for manual mapping.
  * **High-Precision Alignment**: Utilizes fiducial markers (marks in the corners of the page) for precise geometric alignment, accurately correcting rotation and scale distortions.
  * **Robust Fallback Alignment**: For older answer sheets without markers, the system automatically falls back to a robust affine alignment method based on image features.
  * **Image Caching**: The conversion of PDFs to images (the slowest step) is performed only once. Images are saved to a cache directory for instant reuse in subsequent runs.
  * **Complex Grading Logic**: Supports questions with multiple correct answers using two distinct modes:
      * **Inclusive OR** (e.g., `A+B`): The student is correct if they mark any non-empty subset of the correct answers, without marking any incorrect ones.
      * **Exclusive AND** (e.g., `AB`): The student must mark *exactly* all correct answers and no others.
  * **Makefile-Driven Workflow**: The entire process is managed by a `Makefile`, ensuring that only the necessary steps are executed based on file dependencies.
  * **Reproducible Environment**: All system and package dependencies are defined in a `shell.nix` file, guaranteeing that the project runs identically on any machine with Nix.

## Project Structure

```
mcq-grader/
|
|-- .gitignore
|-- LICENSE
|-- Makefile                # Main workflow orchestrator
|-- README.md               # This documentation
|-- shell.nix               # Nix development environment definition
|
|-- scripts/                # All Python source code
|   |-- omr_utils.py
|   |-- generate_zones.py
|   |-- process_sheets.py
|   |-- verify_zones.py
|   |-- grade_exams.py
|   `-- map_zones_manually.py
|
`-- sample_data/            # Example files to demonstrate the tool
    |-- exams/
    |   |-- exam-b.keys.csv
    |   |-- exam-b.student-sheets.pdf
    |   |-- Exam-B-01.tex
    |   `-- provastyle.sty
    |
    `-- image-cache/
        `-- .gitkeep
```

## How It Works

The system follows a clear data processing pipeline:

1.  **LaTeX Compilation:** The `.tex` source file is compiled, generating a main PDF and auxiliary files (`.aux`, `.zonas`) containing precise coordinate data for all defined zones.
2.  **Zone Generation:** `generate_zones.py` parses the auxiliary files and creates a `zones.json` map.
3.  **Answer Extraction:** `process_sheets.py` reads the scanned student sheets, uses the `zones.json` map to align the image and locate the answers, performs Optical Mark Recognition (OMR), and saves the results to a CSV file.
4.  **Grading:** `grade_exams.py` compares the extracted answers with the answer key, applies the grading logic, and produces the final CSV with scores.

## Prerequisites

  * A system with the [Nix package manager](https://nixos.org/) installed (includes NixOS, or Nix on Linux/macOS).

## Usage Guide

### 1\. Preparation

  * Place the Python scripts in the directory defined by the `SCRIPTS_DIR` variable in the `Makefile` (e.g., `scripts/`).
  * Place your exam source files in the `EXAMS_DIR` (e.g., `sample_data/exams/`). This includes:
      * The main `.tex` file for your exam.
      * The `provastyle.sty` file (ensure it contains the fiducial marker definitions).
      * The answer key `.csv` file.
      * The scanned PDF of the filled-out student answer sheets.

### 2\. Configuration

  * Open the `Makefile` in a text editor.
  * Adjust the variables in the "Project Configuration" section to match your filenames (e.g., `EXAM_PREFIX`, `LATEX_SRC`).
  * Adjust the "Fine-tuning Parameters" (`PADDING`, `THRESHOLD`, `CONF_RATIO`) as needed for your scanning conditions.

### 3\. Execution

  * Open your terminal in the project's root directory.
  * Start the development environment:
    ```bash
    nix-shell
    ```
  * To run the entire workflow and generate the final graded spreadsheet:
    ```bash
    make grade
    # or simply:
    make
    ```
  * To generate a visual verification PDF (highly recommended):
    ```bash
    make verify
    ```

### Fine-Tuning and Special Cases

  * **Tuning Parameters:** You can experiment with different `PADDING` and `THRESHOLD` values without editing the `Makefile` by passing them on the command line:
    ```bash
    make PADDING=5 THRESHOLD=1500
    ```
  * **Manual Zone Adjustment:** If you need to manually fix a zone for sheets without proper LaTeX metadata:
    1.  Run `make map-manual`.
    2.  Capture the coordinates for the desired zone.
    3.  Manually edit the generated `.zones.json` file, replacing the coordinates for the relevant key.
    4.  Run `make` again. The `Makefile` will not overwrite your edited `.zones.json` unless the source LaTeX files are modified.

### Answer Key Format for Multiple Answers

The answer key CSV file (`.keys.csv`) supports a special syntax for complex questions:

  * **`A+C` (Inclusive OR):** The student is correct if they mark `A`, `C`, or `A,C`, but no other options.
  * **`AC` (Exclusive AND):** The student is correct **only** if they mark both `A` and `C`, and no other options.
  * **`B` (Single Answer):** The student is correct only if they mark `B`.
