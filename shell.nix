# shell.nix
# Uses the system's nixpkgs channel without pinning a specific version.
# Optimized to use the binary cache, avoiding lengthy compilations.
{ pkgs ? import <nixpkgs> {} }:

let
  # We create a specific derivation for OpenCV with GTK support.
  # Compiling only this package (if necessary) is much faster
  # than compiling an entire Python environment.
  opencvWithGtk = pkgs.python3Packages.opencv4.override {
    enableGtk3 = true;
  };

in
pkgs.mkShell {
  # We use buildInputs to compose the environment from individual packages.
  # This is the most "cache-friendly" approach.
  buildInputs = [
    # System tools
    pkgs.enscript
    pkgs.ghostscript
    pkgs.tesseract      # The OCR engine
    pkgs.poppler-utils  # For pdftoppm
    pkgs.qpdf           # For PDF manipulation (extracting pages)
    pkgs.gtk3           # GUI library dependency for OpenCV
    #pkgs.texlive.combined.scheme-full # LaTeX toolchain, including latexmk/lualatex/minted deps


    # The Python interpreter
    pkgs.python3

    # Individual Python packages
    pkgs.python3Packages.pandas
    pkgs.python3Packages.pytesseract
    pkgs.python3Packages.numpy
    pkgs.python3Packages.pillow
    #pkgs.python3Packages.pygments # Provides pygmentize for minted
    
    # Our custom OpenCV package with GTK support
    opencvWithGtk
  ];
}
