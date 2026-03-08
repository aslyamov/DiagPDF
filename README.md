# DiagPDF — Chess Diagram PDF Generator

Converts PGN / FEN / EPD files to A4 PDF pages with chess diagrams,
using the Chess Alpha DG font family.

## Features

- Reads `.pgn`, `.fen`, `.epd` files
- 7 page layouts: 1–4 columns, up to 20 diagrams per page
- 4 chess diagram fonts: AlphaDG, LeipzigDG, CondalDG, KingdomDG
- Board coordinates, auto-flip for Black-to-move
- To-move indicator: square, circle, triangle
- Position titles centered over the board (from PGN comment or position number)
- Notation lines under diagrams: plain or numbered (1–5 lines per diagram)
- Black-to-move: first line omitted in numbered mode
- Diagrams vertically centered on the page
- Header / footer with page numbers
- Cyrillic and Unicode titles (via system fonts)
- Clickable Lichess analysis links embedded in PDF
- GUI (Tkinter, clam theme) + full CLI

## Requirements

```
pip install fpdf2 fonttools sv-ttk
```

## Usage

```bash
# GUI
python fen2rtf.py --gui

# CLI
python fen2rtf.py input.pgn -o output.pdf
python fen2rtf.py input.pgn --layout 3 --font LeipzigDG --lines 2 --lines-numbered
python fen2rtf.py input.pgn --title-mode comment --lichess-link
```

## Build exe (Windows)

```bash
pip install pyinstaller
pyinstaller fen2pdf.spec
# Output: dist/DiagPDF.exe
```

## Fonts

Place the four `.ttf` files in the `Fonts/` directory.
Patched copies (`*_patch.ttf`) are created automatically on first run.

| File           | Description                    |
|----------------|--------------------------------|
| AlphaDG.ttf    | Main font (auto-patched VDMX)  |
| LeipzigDG.ttf  | Leipzig style                  |
| CondalDG.ttf   | Condensed style                |
| KingdomDG.ttf  | Kingdom style                  |

## File structure

```
fen2rtf.py        Main script (GUI + CLI + PDF generation)
fen2pdf.spec      PyInstaller build config
test_batch.py     Batch test: generates PDFs for all setting combinations
requirements.txt  Python dependencies
Fonts/            Chess diagram TTF fonts
Example/          Sample PGN and generated demo PDFs
```
