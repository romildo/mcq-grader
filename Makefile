# ==============================================================================
# Makefile for the MCQ Grader Suite
# ==============================================================================

# Locate project scripts relative to this Makefile, not to the current directory.
MCQ_GRADER_DIR := $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))
SCRIPTS_DIR     ?= $(MCQ_GRADER_DIR)/scripts

# ==============================================================================
# Exam Configuration
# ==============================================================================

# Canonical exam prefix. For example:
#   make EXAM_PREFIX=bcc222.2026-1/exams/exams/EE2 verify
#
# Conventional input and output names are derived from this path. Individual
# variables remain overridable for exams that do not follow the convention.
EXAM_PREFIX ?= sample-data/exams/E1
EXAM_DIR    := $(patsubst %/,%,$(dir $(EXAM_PREFIX)))
EXAM_NAME   := $(notdir $(EXAM_PREFIX))

# LaTeX inputs
LATEX_SRC     ?= $(EXAM_PREFIX)-01.tex
STYLE_FILE    ?= $(EXAM_DIR)/provastyle.sty
LATEX_BASE    := $(basename $(notdir $(LATEX_SRC)))
LATEXMK_FLAGS ?= -shell-escape
LATEX_INPUTS  ?= $(EXAM_DIR)//:

# Shared output/cache directories. Files inside them are namespaced by the exam.
BUILD_DIR ?= $(EXAM_DIR)/_build
CACHE_DIR ?= $(EXAM_DIR)/image-cache

# Exam inputs
ANSWER_SHEETS_PDF ?= $(EXAM_PREFIX).student-sheets.pdf
ANSWER_KEYS_CSV   ?= $(EXAM_PREFIX).keys.csv

# Generated files
MAIN_PDF         ?= $(BUILD_DIR)/$(LATEX_BASE).pdf
ZONES_JSON       ?= $(EXAM_PREFIX).zones.json
TEMPLATE_PDF     ?= $(EXAM_PREFIX).template-sheet.pdf
RESULTS_CSV      ?= $(EXAM_PREFIX).results.csv
GRADED_CSV       ?= $(EXAM_PREFIX).graded-results.csv
VERIFICATION_PDF ?= $(EXAM_PREFIX).verification.pdf

# Cache filename stems produced by pdftoppm.
TEMPLATE_CACHE_NAME := $(basename $(notdir $(TEMPLATE_PDF)))
STUDENT_CACHE_NAME  := $(basename $(notdir $(ANSWER_SHEETS_PDF)))

# --- Fine-tuning Parameters ---
# Override from the command line, e.g.:
#   make EXAM_PREFIX=path/to/EE2 PADDING=5 THRESHOLD=1500
PADDING        ?= 10
THRESHOLD      ?= 1000
CONF_RATIO     ?= 0.7
REG_CONF_RATIO ?= 0.8

# Python interpreter command
PYTHON ?= python

# ==============================================================================
# Main Targets
# ==============================================================================

.PHONY: all grade verify clean clean-all map-manual show-config

# Default target: run the full grading process.
all: grade

grade: $(GRADED_CSV)

verify: $(VERIFICATION_PDF)

# Display all paths derived from EXAM_PREFIX.
show-config:
	@printf '%-20s %s\n' \
		'MCQ_GRADER_DIR' '$(MCQ_GRADER_DIR)' \
		'SCRIPTS_DIR' '$(SCRIPTS_DIR)' \
		'EXAM_PREFIX' '$(EXAM_PREFIX)' \
		'EXAM_DIR' '$(EXAM_DIR)' \
		'EXAM_NAME' '$(EXAM_NAME)' \
		'LATEX_SRC' '$(LATEX_SRC)' \
		'STYLE_FILE' '$(STYLE_FILE)' \
		'BUILD_DIR' '$(BUILD_DIR)' \
		'CACHE_DIR' '$(CACHE_DIR)' \
		'ANSWER_SHEETS_PDF' '$(ANSWER_SHEETS_PDF)' \
		'ANSWER_KEYS_CSV' '$(ANSWER_KEYS_CSV)' \
		'ZONES_JSON' '$(ZONES_JSON)' \
		'TEMPLATE_PDF' '$(TEMPLATE_PDF)' \
		'RESULTS_CSV' '$(RESULTS_CSV)' \
		'GRADED_CSV' '$(GRADED_CSV)' \
		'VERIFICATION_PDF' '$(VERIFICATION_PDF)'

# Remove generated results and LaTeX artifacts for this exam only. Preserve the
# zones JSON and cached images.
clean:
	@echo "Cleaning generated files for $(EXAM_NAME)..."
	@rm -f \
		"$(RESULTS_CSV)" \
		"$(GRADED_CSV)" \
		"$(VERIFICATION_PDF)" \
		"$(TEMPLATE_PDF)"
	@rm -f "$(BUILD_DIR)/$(LATEX_BASE)".*
	@rm -rf "$(BUILD_DIR)/_minted-$(LATEX_BASE)"
	@rmdir "$(BUILD_DIR)" 2>/dev/null || true

# Also remove cached images for this exam, without affecting other exams that
# share the same image-cache directory.
clean-all: clean
	@echo "Cleaning image cache for $(EXAM_NAME)..."
	@rm -f \
		"$(CACHE_DIR)/$(TEMPLATE_CACHE_NAME)"-*.png \
		"$(CACHE_DIR)/$(STUDENT_CACHE_NAME)"-*.png
	@rmdir "$(CACHE_DIR)" 2>/dev/null || true

# Helper target for manual zone mapping if needed.
map-manual: $(TEMPLATE_PDF)
	@echo "Running manual zone mapper on the generated template..."
	$(PYTHON) $(SCRIPTS_DIR)/map_zones_manually.py \
		--images-dir $(CACHE_DIR) \
		--template-pdf $(TEMPLATE_PDF)

# ==============================================================================
# Build Rules
# ==============================================================================

# 1. Generate the final graded CSV file
$(GRADED_CSV): $(RESULTS_CSV) $(ANSWER_KEYS_CSV) $(SCRIPTS_DIR)/grade_exams.py $(SCRIPTS_DIR)/omr_utils.py
	@echo "--> Grading exams..."
	$(PYTHON) $(SCRIPTS_DIR)/grade_exams.py \
		--answers-csv $(RESULTS_CSV) \
		--keys-csv $(ANSWER_KEYS_CSV) \
		--output-csv $(GRADED_CSV)

# 2. Extract data from student answer sheets
$(RESULTS_CSV): $(ZONES_JSON) $(ANSWER_SHEETS_PDF) $(TEMPLATE_PDF) $(SCRIPTS_DIR)/process_sheets.py $(SCRIPTS_DIR)/omr_utils.py
	@echo "--> Processing answer sheets (Padding: $(PADDING)px, Threshold: $(THRESHOLD))"
	$(PYTHON) $(SCRIPTS_DIR)/process_sheets.py \
		--zones-file $(ZONES_JSON) \
		--output-csv $(RESULTS_CSV) \
		--images-dir $(CACHE_DIR) \
		--template-pdf $(TEMPLATE_PDF) \
		--student-sheets-pdf $(ANSWER_SHEETS_PDF) \
		--padding=$(PADDING) \
		--threshold=$(THRESHOLD) \
		--confidence-ratio=$(CONF_RATIO) \
		--registration-confidence-ratio=$(REG_CONF_RATIO)

# 3. Generate the visual verification PDF
$(VERIFICATION_PDF): $(ZONES_JSON) $(ANSWER_SHEETS_PDF) $(TEMPLATE_PDF) $(SCRIPTS_DIR)/verify_zones.py $(SCRIPTS_DIR)/omr_utils.py
	@echo "--> Generating visual verification PDF (Padding: $(PADDING)px)..."
	$(PYTHON) $(SCRIPTS_DIR)/verify_zones.py \
		--zones-file $(ZONES_JSON) \
		--output $(VERIFICATION_PDF) \
		--images-dir $(CACHE_DIR) \
		--template-pdf $(TEMPLATE_PDF) \
		--student-sheets-pdf $(ANSWER_SHEETS_PDF) \
		--padding=$(PADDING)

# 4. Generate the JSON zones map from LaTeX auxiliary files
$(ZONES_JSON): $(BUILD_DIR)/$(LATEX_BASE).aux $(BUILD_DIR)/$(LATEX_BASE).zonas $(SCRIPTS_DIR)/generate_zones.py
	@echo "--> Generating zones map from LaTeX data..."
	$(PYTHON) $(SCRIPTS_DIR)/generate_zones.py \
		--output-file $(ZONES_JSON) \
		$(BUILD_DIR)/$(LATEX_BASE).aux \
		$(BUILD_DIR)/$(LATEX_BASE).zonas

# 5. Compile the main LaTeX document
$(MAIN_PDF): $(LATEX_SRC) $(STYLE_FILE)
	@echo "--> Compiling main LaTeX document..."
	@mkdir -p $(BUILD_DIR)
	TEXINPUTS="$(LATEX_INPUTS)" TEXMF_OUTPUT_DIRECTORY="$(BUILD_DIR)" \
		latexmk -pdf -pdflatex="lualatex $(LATEXMK_FLAGS) %O %S" \
		-output-directory=$(BUILD_DIR) \
		$(LATEX_SRC)

# 6. Extract the blank answer sheet from the main PDF.
# qpdf's r2 syntax means "the second page from the end".
$(TEMPLATE_PDF): $(MAIN_PDF)
	@echo "--> Extracting blank answer sheet (penultimate page) from main PDF..."
	qpdf $< --pages . r2 -- $@

# Implicit dependencies for LaTeX auxiliary files.
$(BUILD_DIR)/$(LATEX_BASE).aux: $(MAIN_PDF)
$(BUILD_DIR)/$(LATEX_BASE).zonas: $(MAIN_PDF)
