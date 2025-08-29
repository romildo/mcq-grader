# ==============================================================================
# Makefile for the MCQ Grader Suite
# ==============================================================================

# --- Project Configuration ---
# Adjust these variables for a new exam.

# Directory where the Python scripts are located
SCRIPTS_DIR     := scripts

# Base directory and prefix for the exam files
EXAMS_DIR       := sample_data/exams
EXAM_PREFIX     := $(EXAMS_DIR)/exam-b

# LaTeX source files for the answer sheet template
LATEX_SRC       := Exam-B-01.tex
STYLE_FILE      := $(EXAMS_DIR)/provastyle.sty
LATEX_BASE      := $(basename $(LATEX_SRC))

# Output and cache directories
BUILD_DIR       := $(EXAMS_DIR)/_build
CACHE_DIR       := $(EXAMS_DIR)/image-cache

# --- Fine-tuning Parameters ---
# These can be overridden from the command line, e.g., `make PADDING=5 THRESHOLD=1500`
PADDING         ?= 10
THRESHOLD       ?= 1000
CONF_RATIO      ?= 0.7

# --- Key Source Files (Inputs) ---
ZONES_JSON      := $(EXAM_PREFIX).zones.json
ANSWER_SHEETS_PDF := $(EXAM_PREFIX).student-sheets.pdf
ANSWER_KEYS_CSV   := $(EXAM_PREFIX).keys.csv

# --- Generated Files (Outputs) ---
MAIN_PDF        := $(BUILD_DIR)/$(LATEX_BASE).pdf
TEMPLATE_PDF    := $(EXAM_PREFIX).template-sheet.pdf
RESULTS_CSV     := $(EXAM_PREFIX).results.csv
GRADED_CSV      := $(EXAM_PREFIX).graded-results.csv
VERIFICATION_PDF:= $(EXAM_PREFIX).verification.pdf

# Python interpreter command
PYTHON          := python

# ==============================================================================
# Main Targets
# ==============================================================================

.PHONY: all grade verify clean clean-all map-manual

# Default target: Run the full grading process.
all: grade

# 'grade' is a more explicit name for the default target.
grade: $(GRADED_CSV)

# Generates the visual verification PDF.
verify: $(VERIFICATION_PDF)

# Cleans up generated results and LaTeX build files, but preserves the zones.json and image cache.
clean:
	@echo "Cleaning up result files and LaTeX build directory..."
	@rm -f $(RESULTS_CSV) $(GRADED_CSV) $(VERIFICATION_PDF) $(TEMPLATE_PDF)
	@rm -rf $(BUILD_DIR)

# A full clean, including the image cache.
clean-all: clean
	@echo "Cleaning image cache..."
	@rm -rf $(CACHE_DIR)

# Helper target for manual zone mapping if needed.
map-manual: $(TEMPLATE_PDF)
	@echo "Running manual zone mapper on the generated template..."
	$(PYTHON) $(SCRIPTS_DIR)/map_zones_manually.py --images-dir $(CACHE_DIR) --template-pdf $(TEMPLATE_PDF)

# ==============================================================================
# Build Rules
# ==============================================================================

# 1. Generate the final graded CSV file
$(GRADED_CSV): $(RESULTS_CSV) $(ANSWER_KEYS_CSV) $(SCRIPTS_DIR)/grade_exams.py
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
		--confidence-ratio=$(CONF_RATIO)

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
$(MAIN_PDF): $(EXAMS_DIR)/$(LATEX_SRC) $(STYLE_FILE)
	@echo "--> Compiling main LaTeX document..."
	@mkdir -p $(BUILD_DIR)
	latexmk -pdf -pdflatex=lualatex \
		-output-directory=$(BUILD_DIR) \
		$(EXAMS_DIR)/$(LATEX_SRC)

# 6. Extract the blank answer sheet from the main PDF
# 'r2' syntax means "the second page from the end".
$(TEMPLATE_PDF): $(MAIN_PDF)
	@echo "--> Extracting blank answer sheet (penultimate page) from main PDF..."
	qpdf $< --pages . r2 -- $@

# Implicit dependency for LaTeX auxiliary files
$(BUILD_DIR)/$(LATEX_BASE).aux: $(MAIN_PDF)
$(BUILD_DIR)/$(LATEX_BASE).zonas: $(MAIN_PDF)