# DiagPDF — Chess Diagram PDF Generator

Convert PGN / FEN / EPD files to professional A4 PDF pages with chess diagrams,
using the Chess Alpha DG font family.

## Download

Grab the latest **DiagPDF.exe** from [Releases](../../releases) — no Python required.

---

## Features

- Reads `.pgn`, `.fen`, `.epd` files
- 7 page layouts: 1–4 columns, up to 20 diagrams per page
- 4 board fonts: AlphaDG, LeipzigDG, CondalDG, KingdomDG
- To-move indicator: square □■, circle ○●, triangle △▲
- Auto-flip board when Black is to move
- Board coordinates (optional)
- Flexible diagram titles via template: `{number}`, `{event}`, `{white}`, `{black}`, `{date}`, `{comment}`
- Notation lines under diagrams: plain or numbered (1–5 lines)
- **Position range filter**: generate only positions N–M from the file (`--from` / `--to`)
- **Answers section** at the end of the document with figurine notation (Hastings / Zurich / Linares fonts), 1 or 2 columns
- **Clickable links**: diagram title → answer, answer number → diagram
- **Lichess analysis links** embedded in the to-move symbol
- Header / footer with `{page}`, `{total}`, `{chapter}` variables
- Chapter support via `[Chapter "..."]` PGN tag
- Cyrillic and Unicode titles (via system fonts)
- GUI (Windows, Tkinter) + full CLI
- Bilingual interface: English / Russian

---

## Installation

### Option A — Executable (Windows, no Python needed)

1. Download `DiagPDF.exe` from [Releases](../../releases)
2. Place it anywhere and run

### Option B — From source

```bash
pip install fpdf2 fonttools sv-ttk pillow
python fen2rtf.py --gui
```

---

## GUI Usage

Launch the GUI:
```bash
python fen2rtf.py --gui
# or
DiagPDF.exe --gui
```

| Field | Description |
|-------|-------------|
| **Input file** | Click `…` to pick a `.pgn`, `.fen`, or `.epd` file |
| **Output PDF** | Auto-filled; click `…` to change |
| **Positions (from / to)** | Generate only a range of positions (auto-filled with 1 and total count after file selection) |
| **Renumber from 1** | When checked, positions in range are numbered 1, 2, 3… instead of their original file numbers |
| **Header / Footer** | Text with `{page}`, `{total}`, `{chapter}` |
| **Layout** | Page grid preset (columns × rows) |
| **Font** | Board font (AlphaDG recommended) |
| **Board font size** | 0 = auto-fit; or enter a specific pt value |
| **Symbol** | To-move indicator shape |
| **Lines** | Notation lines per diagram (0–5), plain or numbered |
| **Orientation** | Auto / White at bottom / Black at bottom |
| **Show coordinates** | Toggle board coordinate letters/numbers |
| **Title template** | Pattern for diagram titles — click `?` for variables |
| **Lichess links** | Embed analysis link in the to-move symbol |
| **Add answers section** | Append a solutions section at the end |
| **Answers heading** | Title of the answers section |
| **Answer columns** | 1 or 2 columns in the answers section |
| **Figurine font** | Font used for piece symbols in answers (Zurich recommended) |

Press **Generate PDF**, then **Open PDF** to view the result.

---

## CLI Reference

```bash
python fen2rtf.py input.pgn [options]
```

| Option | Default | Description |
|--------|---------|-------------|
| `-o OUTPUT` | `<input>.pdf` | Output PDF path |
| `-l, --layout N` | `2` | Layout preset 0–6 |
| `-f, --font NAME` | `AlphaDG` | Board font |
| `--font-size N` | `0` | Board font size in pt (0 = auto) |
| `--no-coords` | — | Hide board coordinates |
| `--flip` | — | Flip board (Black at bottom) |
| `--no-auto-flip` | — | Disable auto-flip on Black to move |
| `--symbol NAME` | `square` | `square` / `circle` / `triangle` |
| `--lines N` | `0` | Notation lines per diagram |
| `--lines-numbered` | — | Use numbered lines (1. ___ ___) |
| `--header TEXT` | filename | Header text |
| `--footer TEXT` | `{page}` | Footer text |
| `--title-template TPL` | `{number} {comment}` | Title pattern |
| `--lichess-link` | — | Embed Lichess links |
| `--answers` | — | Add answers section |
| `--answers-title TEXT` | `Solutions` | Answers heading |
| `--answers-cols N` | `1` | Answer columns (1 or 2) |
| `--figurine-font NAME` | `Zurich` | Figurine font for answers |
| `--from N` | — | First position to include (1-based) |
| `--to N` | — | Last position to include (1-based) |
| `--no-renumber` | — | Keep original position numbers instead of renumbering from 1 |
| `--version` | — | Print version and exit |
| `--gui` | — | Launch GUI |

---

## PGN Format Tips

### Diagram titles

DiagPDF reads position data from PGN tags and the first comment.
Use the title template to compose any title you need:

```
--title-template "{number}. {event} ({date})"
--title-template "{number} {comment}"
```

### Chapters

Add a `[Chapter "Chapter name"]` tag before a group of games.
Use `{chapter}` in the header/footer to display the current chapter:

```pgn
[Chapter "Tactics — Pin"]
[Event "1.1 Example"]
[FEN "..."]

1. Ng7! 1-0
```

### Answers section

Moves in the PGN game body become the answers.
Comments `{...}` and NAG codes `$1` are automatically stripped.
Variations in parentheses `(2...Ke8 3.Rb8#)` are preserved.

---

## File Structure

```
fen2rtf.py          Main script (GUI + CLI + PDF generation)
fen2pdf.spec        PyInstaller build config
test_batch.py       Batch test: all setting combinations
requirements.txt    Python dependencies
icon.ico            Application icon
Fonts/              Chess diagram fonts (TTF)
Example/            Sample PGN and demo PDFs
```

---

## Building the Executable

```bash
pip install pyinstaller pillow
pyinstaller fen2pdf.spec
# Output: dist/DiagPDF.exe
```

---

## Fonts

| File | Style |
|------|-------|
| `AlphaDG.ttf` | Main (VDMX auto-patched on first run) |
| `LeipzigDG.ttf` | Leipzig style |
| `CondalDG.ttf` | Condensed style |
| `KingdomDG.ttf` | Kingdom style |
| `ZurichFigurine.TTF` | Figurine notation — balanced (default) |
| `HastingsFigurine.TTF` | Figurine notation — classic, detailed |
| `LinaresFigurine.TTF` | Figurine notation — simplified, modern |

Patched copies (`*_patch.ttf`) are created automatically on first run.
