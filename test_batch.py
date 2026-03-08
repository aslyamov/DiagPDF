#!/usr/bin/env python3
"""
Batch test: generates PDFs with various settings combinations.
Filenames: <PGN stem>_<font>_layout<N>_<orient>_<symbol>[_nocoords][_lines<N>_<mode>].pdf

Usage:
    python test_batch.py input.pgn [output_dir]
"""
import sys
from pathlib import Path

# ── import the main module ────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))
from fen2rtf import (
    parse_pgn, parse_fen_file, parse_epd,
    generate_pdf, FONT_NAMES, LAYOUTS,
)


def run_batch(input_path: Path, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    ext = input_path.suffix.lower()
    content = input_path.read_text(encoding='utf-8-sig', errors='replace')
    if ext == '.pgn':
        positions = parse_pgn(content)
    elif ext == '.fen':
        positions = parse_fen_file(content)
    elif ext == '.epd':
        positions = parse_epd(content)
    else:
        print(f'Unknown extension: {ext}', file=sys.stderr)
        sys.exit(1)

    if not positions:
        print('No positions found.', file=sys.stderr)
        sys.exit(1)

    stem = input_path.stem

    # Test matrix
    tests = []

    # ── Phase 1: All 4 fonts × 3 symbols, default layout, auto-orient, with coords
    for font in FONT_NAMES:
        for sym in ('square', 'circle', 'triangle'):
            tests.append(dict(
                group='P1_fonts_symbols',
                font=font, layout_idx=2, orient='auto',
                symbol=sym, coords=True, lines_count=0, lines_mode='plain',
            ))

    # ── Phase 1: No coordinates
    tests.append(dict(
        group='P1_nocoords',
        font='AlphaDG', layout_idx=2, orient='auto',
        symbol='square', coords=False, lines_count=0, lines_mode='plain',
    ))

    # ── Phase 2: Notation lines — lines_count 1..5, both modes, auto-orient
    for ln in range(1, 6):
        for mode in ('plain', 'numbered'):
            tests.append(dict(
                group='P2_lines_count',
                font='AlphaDG', layout_idx=2, orient='auto',
                symbol='square', coords=True, lines_count=ln, lines_mode=mode,
            ))

    # ── Phase 2: Numbered lines — black to move (first line should show "...")
    for orient in ('auto', 'black'):
        tests.append(dict(
            group='P2_black_to_move',
            font='AlphaDG', layout_idx=2, orient=orient,
            symbol='square', coords=True, lines_count=3, lines_mode='numbered',
        ))

    # ── Phase 2: Numbered lines on flipped board
    tests.append(dict(
        group='P2_flipped_numbered',
        font='AlphaDG', layout_idx=2, orient='black',
        symbol='square', coords=True, lines_count=3, lines_mode='numbered',
    ))

    # ── Phase 2: All layouts with notation lines (lines_count=2)
    for li in range(len(LAYOUTS)):
        tests.append(dict(
            group='P2_all_layouts',
            font='AlphaDG', layout_idx=li, orient='auto',
            symbol='square', coords=True, lines_count=2, lines_mode='numbered',
        ))

    # ── Phase 2: Lines without coords (verify alignment still correct)
    tests.append(dict(
        group='P2_lines_nocoords',
        font='AlphaDG', layout_idx=2, orient='auto',
        symbol='square', coords=False, lines_count=2, lines_mode='numbered',
    ))

    total = len(tests)
    print(f'Generating {total} PDFs into: {out_dir}')

    for i, cfg in enumerate(tests, 1):
        orient   = cfg['orient']
        lines_n  = cfg['lines_count']
        mode     = cfg['lines_mode']
        no_coords = '' if cfg['coords'] else '_nocoords'
        lines_s  = f'_lines{lines_n}_{mode}' if lines_n else ''

        name = (f"{stem}_{cfg['group']}"
                f"_{cfg['font']}"
                f"_layout{cfg['layout_idx']}"
                f"_{orient}"
                f"_{cfg['symbol']}"
                f"{no_coords}{lines_s}.pdf")

        out_path = out_dir / name

        opts = {
            'layout_idx':  cfg['layout_idx'],
            'font':        cfg['font'],
            'font_size':   0,
            'text_size':   10,
            'coords':      cfg['coords'],
            'flip':        orient == 'black',
            'flip_auto':   orient == 'auto',
            'header':      stem,
            'footer':      '',
            'show_header': True,
            'show_footer': True,
            'show_moves':  False,
            'symbol':      cfg['symbol'],
            'lines_count': lines_n,
            'lines_mode':  mode,
        }

        try:
            generate_pdf(positions, opts, out_path)
            print(f'  [{i:2d}/{total}] OK  {name}')
        except Exception as e:
            print(f'  [{i:2d}/{total}] ERR {name}: {e}')

    print('Done.')


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python test_batch.py input.pgn [output_dir]')
        sys.exit(1)

    inp = Path(sys.argv[1])
    if not inp.exists():
        print(f'File not found: {inp}', file=sys.stderr)
        sys.exit(1)

    out = Path(sys.argv[2]) if len(sys.argv) > 2 else inp.parent / f'test_{inp.stem}'
    run_batch(inp, out)
