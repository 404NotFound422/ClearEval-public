# Local latexmk configuration
# Overleaf uses its own latexmk defaults, so this file mainly affects local builds.

$pdf_mode = 1;        # use pdflatex
$bibtex_use = 1.5;    # run bibtex/biber when needed
$out_dir = 'build';   # put build files in build/ subdirectory
$preview_continuous_mode = 0;

# Clean extensions
$clean_ext = "aux bbl blg fdb_latexmk fls log nav out snm synctex.gz toc vrb run.xml bcf";
