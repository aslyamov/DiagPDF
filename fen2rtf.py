#!/usr/bin/env python3
"""
Chess Diagram PDF Generator
Converts PGN/FEN/EPD files to PDF with diagrams using Chess Alpha DG family fonts.

Usage:
    python fen2rtf.py input.pgn [options]
    python fen2rtf.py --gui
"""

__version__ = '0.2.1'

import os
import re
import sys
import json
import argparse
from pathlib import Path
from dataclasses import dataclass
from typing import Any, TypedDict


class _PositionRequired(TypedDict):
    fen: str


class PositionDict(_PositionRequired, total=False):
    """Position data shared by all three parsers (PGN / FEN file / EPD)."""
    white:   str
    black:   str
    event:   str
    date:    str
    chapter: str
    comment: str
    moves:   str


def _resource(rel: str) -> Path:
    """Return absolute path to a bundled resource.

    Works both when running from source (relative to this file)
    and when frozen by PyInstaller (via sys._MEIPASS).
    """
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))
    return base / rel

# ─────────────────────────────────────────────────────────────────────────────
# Chess Alpha DG character mapping
# Square dark = (file + rank) % 2 == 0 ;  file: 0=a..7=h, rank: 0=rank1..7=rank8
# ─────────────────────────────────────────────────────────────────────────────
ALPHA_DG: dict[tuple, str] = {
    ('K', False): 'k',  ('K', True): 'K',
    ('Q', False): 'q',  ('Q', True): 'Q',
    ('R', False): 'r',  ('R', True): 'R',
    ('B', False): 'b',  ('B', True): 'B',
    ('N', False): 'h',  ('N', True): 'H',
    ('P', False): 'p',  ('P', True): 'P',
    ('k', False): 'l',  ('k', True): 'L',
    ('q', False): 'w',  ('q', True): 'W',
    ('r', False): 't',  ('r', True): 'T',
    ('b', False): 'n',  ('b', True): 'N',
    ('n', False): 'j',  ('n', True): 'J',
    ('p', False): 'o',  ('p', True): 'O',
    (None, False): ' ', (None, True): '+',
}

BDR_NW = '!'; BDR_N = 'z'; BDR_NE = '#'
BDR_SW = '&'; BDR_S = "'"; BDR_SE = '('
BDR_E  = '%'
RANK_CHARS = [chr(0xE0 + i) for i in range(8)]   # rank 1..8 with left border
FILE_CHARS = [chr(0xE8 + i) for i in range(8)]   # file a..h with bottom border

# ─────────────────────────────────────────────────────────────────────────────
# To-move symbol chars  (white-to-move, black-to-move)
# Verified: 'square' = I/M.  Others are best-guess from font path analysis.
# ─────────────────────────────────────────────────────────────────────────────
SYMBOL_CHARS: dict[str, tuple[str, str]] = {
    # sym_w = hollow/outline (visually white) = white to move
    # sym_b = solid/filled  (visually black) = black to move
    'square':   ('I', 'M'),   # confirmed: I=hollow□ white, M=solid■ black
    'circle':   ('F', 'G'),   # F=hollow○ white, G=solid● black (font analysis)
    'triangle': ('f', 'i'),   # f=hollow△ white, i=solid△ black (font analysis)
}
SYMBOL_KEYS = list(SYMBOL_CHARS.keys())

# ─────────────────────────────────────────────────────────────────────────────
# Layout presets
# (label_en, label_ru, cols, rows_plain, rows_lined)
# Layout tuple: (label_en, label_ru, cols, rows_plain, rows_lined, default_chess_pt, title_pt, title_offset)
#   default_chess_pt   = chess font size (pt) for plain mode; lined mode recalculates to fit
#   title_pt      = title font size (pt); cell height = title_pt * 0.388 must be < chess_pt * 0.353
#   title_offset  = vertical shift (mm) from centered position: + toward rank-8, − toward top frame
# ─────────────────────────────────────────────────────────────────────────────
LAYOUTS: list[tuple[str, str, int, int, int, int, int, float]] = [
    ('1 - 1/1 dg/pg',    '1 - 1/1 на стр.',   1, 1, 1,  52,  20,  0.0),
    ('1 - 1/2 dg/pg',    '1 - 1/2 на стр.',   1, 1, 2,  52,  20,  0.0),
    ('2 - 6/4 dg/pg',    '2 - 6/4 на стр.',   2, 3, 2,  23,  10,  - 1.0),
    ('3 - 12/9 dg/pg',   '3 - 12/9 на стр.',  3, 4, 3,  16,   8,  - 1.0),
    ('4 - 20/16 dg/pg',  '4 - 20/16 на стр.', 4, 5, 4,  13,   6,  - 1.0),
    ('3 - 15/12 dg/pg',  '3 - 15/12 на стр.', 3, 5, 4,  13,   6,  - 1.0),
    ('3 - 12 max',       '3 - 12 макс.',       3, 4, 4,  16,   8,  - 1.0),
]
DEFAULT_LAYOUT = 2  # "2 - 6/4 dg/pg"

# ─────────────────────────────────────────────────────────────────────────────
# Supported chess fonts
# ─────────────────────────────────────────────────────────────────────────────
FONT_FILES: dict[str, str] = {
    'AlphaDG':  'AlphaDG.ttf',
    'LeipzigDG': 'LeipzigDG.ttf',
    'CondalDG': 'CondalDG.ttf',
    'KingdomDG': 'KingdomDG.ttf',
}
FONT_NAMES = list(FONT_FILES.keys())

# Figurine fonts for the answers section (piece letters only, standard ASCII)
# Encoding: K/Q/R/B/N/P = white pieces (uppercase), k/q/r/b/n/p = black (lowercase)
# In move notation we only render uppercase piece initials (K Q R B N).
FIGURINE_FILES: dict[str, str] = {
    'Hastings': 'HastingsFigurine.TTF',
    'Zurich':   'ZurichFigurine.TTF',
    'Linares':  'LinaresFigurine.TTF',
}
FIGURINE_NAMES = list(FIGURINE_FILES.keys())
# Letters in SAN move text that should be drawn with the figurine font
FIGURINE_PIECE_CHARS = frozenset('KQRBN')

# ─────────────────────────────────────────────────────────────────────────────
# Localization strings
# ─────────────────────────────────────────────────────────────────────────────
# Translations: T[key] = ('English', 'Русский')
T: dict[str, tuple] = {
    #                              EN                             RU
    'section_files':    ('Files',                        'Файлы'),
    'section_page':     ('Page',                         'Страница'),
    'section_diagram':  ('Diagram',                      'Диаграмма'),
    'input_file':       ('Input file:',                  'Исходный файл:'),
    'output_pdf':       ('Output PDF:',                  'Выходной PDF:'),
    'header_text':      ('Header:',                      'Верхний:'),
    'footer_text':      ('Footer:',                      'Нижний:'),
    'show_header':      ('Show',                         'Показать'),
    'show_footer':      ('Show',                         'Показать'),
    'layout':           ('Layout:',                      'Макет:'),
    'font':             ('Font:',                        'Шрифт:'),
    'symbol':           ('Move indicator:',              'Символ хода:'),
    'lines_count':      ('Lines per diagram:',           'Строк под диаграммой:'),
    'lines_plain':      ('Plain',                        'Пустые'),
    'lines_numbered':   ('Numbered',                     'С нумерацией'),
    'orient':           ('Orientation:',                 'Ориентация:'),
    'orient_auto':      ('Auto',                         'Авто'),
    'orient_white':     ('White \u2193',                 'Белые \u2193'),
    'orient_black':     ('Black \u2193',                 'Чёрные \u2193'),
    'coords':           ('Show coordinates',             'Показать координаты'),
    'title_source':     ('Title template:',               'Шаблон заголовка:'),
    'tpl_help_title':   ('Title template variables',     'Переменные шаблона заголовка'),
    'tpl_help_body':    (
        '{number}  — diagram number          e.g.  42\n'
        '{event}   — [Event "…"] tag         e.g.  Hastings 1895\n'
        '{white}   — [White "…"] tag         e.g.  Steinitz, W.\n'
        '{black}   — [Black "…"] tag         e.g.  Lasker, Em.\n'
        '{date}    — [Date "…"] tag          e.g.  1895.01.03\n'
        '{comment} — first comment in game   e.g.  White to move and win\n\n'
        'Example:  {number}. {event} ({date})\n'
        '→  42. Hastings 1895 (1895.01.03)',
        '{number}  — номер диаграммы         напр.  42\n'
        '{event}   — тег [Event "…"]         напр.  Гастингс 1895\n'
        '{white}   — тег [White "…"]         напр.  Steinitz, W.\n'
        '{black}   — тег [Black "…"]         напр.  Lasker, Em.\n'
        '{date}    — тег [Date "…"]          напр.  1895.01.03\n'
        '{comment} — первый коммент. партии  напр.  Белые ходят и выигрывают\n\n'
        'Пример:  {number}. {event} ({date})\n'
        '→  42. Гастингс 1895 (1895.01.03)'
    ),
    'sym_square':       ('Square',                       'Квадрат'),
    'sym_circle':       ('Circle',                       'Круг'),
    'sym_triangle':     ('Triangle',                     'Треугольник'),
    'font_size_lbl':    ('Board font size (0=auto)',      'Размер шрифта доски (0=авто)'),
    'lichess_link':     ('Lichess links',                'Ссылки Lichess'),
    'answers_section':  ('Add answers section',          'Добавить раздел ответов'),
    'answers_title_lbl':('Answers heading',              'Заголовок раздела ответов'),
    'answers_cols_lbl': ('Answer columns',               'Колонок ответов'),
    'figurine_font_lbl':('Figurine font',                'Шрифт фигур'),
    'convert':          ('Generate PDF',                 'Сгенерировать PDF'),
    'open_pdf':         ('Open PDF',                     'Открыть PDF'),
    'open_title':       ('Open chess file',              'Открыть шахматный файл'),
    'save_title':       ('Save PDF as',                  'Сохранить PDF как'),
    'open_types':       ([('Chess files', '*.pgn *.fen *.epd'), ('All files', '*.*')],
                         [('Шахматные файлы', '*.pgn *.fen *.epd'), ('Все файлы', '*.*')]),
    'save_types':       ([('PDF files', '*.pdf'), ('All files', '*.*')],
                         [('PDF файлы', '*.pdf'), ('Все файлы', '*.*')]),
    'err_not_found':    ('Input file not found:\n{}',    'Файл не найден:\n{}'),
    'err_unknown':      ('Unknown file type: {}',        'Неизвестный тип файла: {}'),
    'err_no_pos':       ('No positions found in file.',  'В файле не найдено позиций.'),
    'done':             ('Done: {} position(s) \u2192 {}', 'Готово: {} позиц. \u2192 {}'),
    'error':            ('Error: {}',                    'Ошибка: {}'),
    'ready':            ('Ready.',                       'Готово.'),
    'lang_btn':         ('RU',                           'EN'),
}


# ─────────────────────────────────────────────────────────────────────────────
# FEN parsing & diagram rendering
# ─────────────────────────────────────────────────────────────────────────────

def parse_fen(fen_str: str) -> tuple[list[list[str | None]], str]:
    """Parse a FEN string into an 8x8 board array and side-to-move ('w'/'b')."""
    parts = fen_str.strip().split()
    board_str = parts[0]
    side = parts[1].lower() if len(parts) > 1 else 'w'
    board: list[list[str | None]] = [[None] * 8 for _ in range(8)]
    rank, file = 7, 0
    for ch in board_str:
        if ch == '/':
            rank -= 1; file = 0
        elif ch.isdigit():
            file += int(ch)
        else:
            if 0 <= rank <= 7 and 0 <= file <= 7:
                board[rank][file] = ch
            file += 1
    return board, side


def fen_to_diagram(fen_str: str, coords: bool = True, flip: bool = False,
                   flip_auto: bool = False, symbol: str = 'square') -> list[str]:
    """Convert a FEN string to a list of 10 character strings for the Chess Alpha DG font.

    Each character maps to a glyph via Unicode PUA (chr(0xF000 + ord(c))).
    Returns 10 rows: top border, 8 rank rows, bottom border.
    """
    board, side = parse_fen(fen_str)
    actual_flip = flip
    if flip_auto and side == 'b':
        actual_flip = not flip
    sym_w, sym_b = SYMBOL_CHARS.get(symbol, SYMBOL_CHARS['square'])
    # Character depends on side to move: sym_w=hollow(white), sym_b=solid(black)
    # Placement depends on orientation: always at visual bottom row
    hg_char = sym_w if side == 'w' else sym_b
    rank_order = range(7, -1, -1) if not actual_flip else range(0, 8)
    file_order = list(range(0, 8)) if not actual_flip else list(range(7, -1, -1))
    file_labels = FILE_CHARS if not actual_flip else list(reversed(FILE_CHARS))

    visual_bottom_ri = 0 if not actual_flip else 7  # rank at visual bottom row
    lines = []
    if coords:
        lines.append(BDR_NW + BDR_N * 8 + BDR_NE)
        for ri in rank_order:
            row = RANK_CHARS[ri]
            for fi in file_order:
                piece = board[ri][fi]
                dark = (fi + ri) % 2 == 0
                row += ALPHA_DG.get((piece, dark), ' ')
            row += hg_char if ri == visual_bottom_ri else BDR_E
            lines.append(row)
        lines.append(BDR_SW + ''.join(file_labels) + BDR_SE)
    else:
        lines.append('!' + BDR_N * 8 + '#')
        for ri in rank_order:
            row = '$'
            for fi in file_order:
                piece = board[ri][fi]
                dark = (fi + ri) % 2 == 0
                row += ALPHA_DG.get((piece, dark), ' ')
            row += hg_char if ri == visual_bottom_ri else BDR_E
            lines.append(row)
        lines.append('&' + BDR_S * 8 + '(')
    return lines


# ─────────────────────────────────────────────────────────────────────────────
# Input file parsers
# ─────────────────────────────────────────────────────────────────────────────

def _first_text_comment(moves_raw: str) -> str:
    """Return first non-markup comment from PGN game text, or empty string."""
    for m in re.finditer(r'\{([^}]*)\}', moves_raw):
        text = re.sub(r'\[%[^\]]+\]', '', m.group(1)).strip()
        if text:
            return text
    return ''


def _clean_moves(moves_raw: str) -> str:
    """Extract clean move text from a raw PGN game body.

    Removes {comments}, NAG glyphs ($1, !?, etc.) and result tokens.
    Preserves move numbers, moves, and parenthesised variations.

    Example input:
        1. Qxd8+ {тактический удар} $1 Kxd8 2. Ne4+ Kc8 (2... Ke8 3. Rb8#) 3. Rd8# 1-0
    Example output:
        1. Qxd8+ Kxd8 2. Ne4+ Kc8 (2... Ke8 3. Rb8#) 3. Rd8#
    """
    # Strip {comments} (including multi-line)
    text = re.sub(r'\{[^}]*\}', ' ', moves_raw)
    # Strip NAG codes ($1 .. $255)
    text = re.sub(r'\$\d+', '', text)
    # Strip annotation glyphs (!, ?, !!, ??, !?, ?!)
    text = re.sub(r'[!?]+', '', text)
    # Strip result tokens
    text = re.sub(r'\b(1-0|0-1|1/2-1/2|\*)\s*$', '', text.rstrip())
    # Normalize whitespace (but keep structure intact)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\(\s+', '(', text)
    text = re.sub(r'\s+\)', ')', text)
    return text.strip()


def _apply_title_template(template: str, pos: PositionDict, num: int) -> str:
    """Expand a title template with position metadata.

    Variables: {number}, {event}, {white}, {black}, {date}, {comment}.
    Empty substitutions collapse surrounding whitespace automatically.
    """
    vals = {
        'number':  str(num),
        'event':   pos.get('event', ''),
        'white':   pos.get('white', ''),
        'black':   pos.get('black', ''),
        'date':    pos.get('date', ''),
        'comment': pos.get('comment', '').strip(),
    }
    result = template
    for key, val in vals.items():
        result = result.replace(f'{{{key}}}', val)
    return ' '.join(result.split())   # collapse whitespace from empty substitutions


def parse_pgn(content: str) -> list[PositionDict]:
    """Parse a PGN file and return a list of position dicts.

    Each dict contains: fen, white, black, event, chapter, comment, moves.
    Only games that include a FEN tag are included.
    The 'comment' field is the first text comment from the game body (used as title).
    """
    positions = []
    tag_re = re.compile(r'\[(\w+)\s+"([^"]*)"\]')
    game_re = re.compile(r'(?=^\[Event\b)', re.IGNORECASE | re.MULTILINE)
    for block in game_re.split(content):
        if not block.strip():
            continue
        tags = dict(tag_re.findall(block))
        fen = tags.get('FEN')
        if not fen:
            continue
        tag_end = 0
        for m in tag_re.finditer(block):
            tag_end = m.end()
        moves_raw = re.sub(r'\s*(1-0|0-1|1/2-1/2|\*)\s*$', '', block[tag_end:].strip()).strip()
        positions.append({
            'fen':     fen,
            'white':   tags.get('White', ''),
            'black':   tags.get('Black', ''),
            'event':   tags.get('Event', ''),
            'date':    tags.get('Date', ''),
            'chapter': tags.get('Chapter', ''),
            'comment': _first_text_comment(moves_raw),
            'moves':   moves_raw,
        })
    return positions


def parse_fen_file(content: str) -> list[PositionDict]:
    """Parse a .fen file containing [FEN "..."] tags and return position dicts."""
    return [{'fen': m.group(1), 'white': '', 'black': '', 'event': '',
             'date': '', 'chapter': '', 'comment': '', 'moves': ''}
            for m in re.finditer(r'\[FEN\s+"([^"]*)"\]', content)]


def parse_epd(content: str) -> list[PositionDict]:
    """Parse an EPD file (one position per line) and return position dicts.

    Extracts 'id' operand as white, 'bm' operand as black. FEN is reconstructed
    with placeholder move counters (0 1).
    """
    positions = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith(';'):
            continue
        parts = line.split(None, 4)
        if len(parts) < 4:
            continue
        fen = ' '.join(parts[:4]) + ' 0 1'
        rest = parts[4] if len(parts) > 4 else ''
        id_m = re.search(r'id\s+"([^"]*)"', rest)
        bm_m = re.search(r'bm\s+([^;]+)', rest)
        positions.append({
            'fen':     fen,
            'white':   id_m.group(1).strip() if id_m else '',
            'black':   bm_m.group(1).strip().rstrip(';') if bm_m else '',
            'event':   '', 'date': '', 'chapter': '', 'comment': '', 'moves': '',
        })
    return positions


# ─────────────────────────────────────────────────────────────────────────────
# Font patching  (removes broken VDMX table that crashes fpdf2)
# ─────────────────────────────────────────────────────────────────────────────

def _ensure_chess_font_patched(font_orig: Path, font_patched: Path) -> str:
    """Remove the broken VDMX table from a chess font TTF if present.

    fpdf2 crashes on fonts with a malformed VDMX table (AlphaDG.ttf).
    The patched copy is saved once and reused on subsequent runs.
    Returns the path to the usable font file (patched or original).
    """
    if font_patched.exists():
        return str(font_patched)
    if not font_orig.exists():
        raise FileNotFoundError(f'Chess font not found: {font_orig}')
    try:
        from fontTools import ttLib
        fnt = ttLib.TTFont(str(font_orig))
        if 'VDMX' not in fnt:
            return str(font_orig)   # no patching needed for this font
        del fnt['VDMX']
        fnt.save(str(font_patched))
    except Exception:
        font_patched.unlink(missing_ok=True)   # remove partial/corrupted file
        return str(font_orig)
    return str(font_patched if font_patched.exists() else font_orig)


def get_chess_font_path(font_name: str, fonts_dir: Path) -> str:
    """Resolve the path to a chess font, patching it if necessary."""
    fname = FONT_FILES.get(font_name, FONT_FILES['AlphaDG'])
    orig    = fonts_dir / fname
    patched = fonts_dir / (Path(fname).stem + '_patch.ttf')
    return _ensure_chess_font_patched(orig, patched)


class FontManager:
    """Loads and registers chess, text, and figurine fonts into an fpdf2 PDF object."""

    def __init__(self, script_dir: Path) -> None:
        self.fonts_dir = script_dir / 'Fonts'

    def load_chess(self, pdf, font_name: str) -> None:
        """Register chess font as 'Chess' in pdf."""
        path = get_chess_font_path(font_name, self.fonts_dir)
        pdf.add_font('Chess', fname=path)

    def load_text(self, pdf) -> str:
        """Register best available Unicode text font as 'TextUni' in pdf.

        Returns the font name to use: 'TextUni' on success, 'helvetica' as fallback.
        """
        for candidate in _get_text_font_candidates():
            try:
                pdf.add_font('TextUni', fname=candidate)
            except Exception as e:
                print(f'TextUni regular load failed ({candidate}): {e}', file=sys.stderr)
                continue
            try:
                pdf.add_font('TextUni', style='B', fname=candidate)
            except Exception:
                pass
            return 'TextUni'
        return 'helvetica'

    def load_figurine(self, pdf, figurine_font: str, fallback: str) -> str:
        """Register figurine font as 'Figurine' in pdf.

        Returns 'Figurine' on success, fallback font name otherwise.
        """
        if not FIGURINE_NAMES:
            return fallback
        fname = FIGURINE_FILES.get(figurine_font, next(iter(FIGURINE_FILES.values())))
        path  = self.fonts_dir / fname
        if path.exists():
            try:
                pdf.add_font('Figurine', fname=str(path))
                return 'Figurine'
            except Exception as e:
                print(f'Figurine font load failed ({path.name}): {e}', file=sys.stderr)
        return fallback


# ─────────────────────────────────────────────────────────────────────────────
# PDF generator
# ─────────────────────────────────────────────────────────────────────────────

_PT = 25.4 / 72   # 1 pt in mm


@dataclass
class _Geometry:
    """Computed page/layout geometry passed between PDF rendering functions."""
    # A4 page
    PW: float; PH: float
    ML: float; MR: float; MT: float
    HY: float; FY: float
    USABLE_W: float; USABLE_H: float
    LINE_H: float
    # layout grid
    cols: int; max_rows: int; per_page: int
    col_w: float; x_pad: float; y_top: float; row_h: float
    lines_h: float
    # chess font
    chess_pt: int; chess_mm: float
    diag_w: float; char_w: float; inner_w: float
    # text
    txt_size: int; title_lh: float
    title_offset: float   # lay[7]: vertical nudge for title inside top border


def _compute_geometry(opts: dict) -> _Geometry:
    """Parse opts and compute all layout/geometry values (pure, no side effects)."""
    layout_idx  = max(0, min(opts.get('layout_idx', DEFAULT_LAYOUT), len(LAYOUTS) - 1))
    lines_count = int(opts.get('lines_count', 0))
    txt_size_opt = opts.get('text_size', 0)

    PW, PH   = PAGE_W, PAGE_H
    ML = MR  = MARGIN_LR
    MT       = MARGIN_TB
    HY = FY  = HDR_FTR_Y
    USABLE_W = PW - ML - MR
    USABLE_H = PH - MT - MT
    LINE_H   = NOTATION_LINE_H

    lay      = LAYOUTS[layout_idx]
    cols     = lay[2]
    max_rows = lay[4] if lines_count > 0 else lay[3]
    per_page = cols * max_rows

    lines_h   = lines_count * LINE_H
    requested = opts.get('font_size', 0)
    if requested > 0:
        chess_pt = requested
    elif lines_count == 0:
        chess_pt = lay[5]
    else:
        chess_pt_v = (USABLE_H / max_rows - ROW_OVERHEAD - lines_h) / (10 * _PT)
        chess_pt_h = (USABLE_W / cols) / 10 / _PT
        chess_pt = max(MIN_FONT_PT, min(lay[5], int(min(chess_pt_v, chess_pt_h))))

    chess_mm = chess_pt * _PT
    col_w    = USABLE_W / cols
    txt_size = txt_size_opt if txt_size_opt > 0 else lay[6]
    title_lh = txt_size * _PT * TITLE_LH_FACTOR
    row_h    = 10 * chess_mm + lines_h + ROW_OVERHEAD
    content_h = max_rows * row_h
    y_top    = MT + max(0.0, (USABLE_H - content_h) / 2)

    # diag_w and char_w require font metrics — set to 0 as placeholders;
    # generate_pdf fills them after loading the chess font into the PDF.
    return _Geometry(
        PW=PW, PH=PH, ML=ML, MR=MR, MT=MT, HY=HY, FY=FY,
        USABLE_W=USABLE_W, USABLE_H=USABLE_H, LINE_H=LINE_H,
        cols=cols, max_rows=max_rows, per_page=per_page,
        col_w=col_w, x_pad=0.0, y_top=y_top, row_h=row_h, lines_h=lines_h,
        chess_pt=chess_pt, chess_mm=chess_mm,
        diag_w=0.0, char_w=0.0, inner_w=0.0,
        txt_size=txt_size, title_lh=title_lh,
        title_offset=lay[7],
    )

# ─────────────────────────────────────────────────────────────────────────────
# Page geometry constants (A4, mm)
# ─────────────────────────────────────────────────────────────────────────────
PAGE_W          = 210.0   # A4 width
PAGE_H          = 297.0   # A4 height
MARGIN_LR       = 10.0    # left and right page margins
MARGIN_TB       = 15.0    # top and bottom page margins
HDR_FTR_Y       = 10.0    # header/footer distance from page edge
NOTATION_LINE_H = 6.0     # mm per notation line below diagram
ROW_OVERHEAD    = 3.0     # extra mm per row (inter-row spacing)
MIN_FONT_PT     = 8       # minimum chess font size (pt)
TITLE_LH_FACTOR = 1.1     # title line-height multiplier


def _make_title(pos: PositionDict, num: int, template: str, mode: str, custom: str) -> str:
    """Build the diagram title from position data."""
    if template:
        return _apply_title_template(template, pos, num)
    comment = pos.get('comment', '').strip()
    if mode == 'number':
        return str(num)
    if mode == 'custom':
        return f'{num} {custom}' if custom else str(num)
    return f'{num} {comment}' if comment else str(num)  # 'comment' mode


def _get_text_font_candidates() -> list[str]:
    """Return system font paths to try as the Unicode text font."""
    candidates: list[str] = []
    if sys.platform == 'win32':
        wf = Path(os.environ.get('SystemRoot', os.environ.get('WINDIR', r'C:\Windows'))) / 'Fonts'
        uf = Path(os.environ.get('LOCALAPPDATA', '')) / 'Microsoft' / 'Windows' / 'Fonts'
        for name in ('arial.ttf', 'Arial.ttf', 'arialuni.ttf',
                     'calibri.ttf', 'Calibri.ttf',
                     'segoeui.ttf', 'SegoeUI.ttf',
                     'tahoma.ttf', 'Tahoma.ttf',
                     'verdana.ttf', 'Verdana.ttf'):
            for base in (wf, uf):
                p = base / name
                if p.exists():
                    candidates.append(str(p))
    elif sys.platform == 'darwin':
        for p in (Path('/Library/Fonts/Arial.ttf'),
                  Path('/Library/Fonts/Tahoma.ttf'),
                  Path('/System/Library/Fonts/Geneva.ttf')):
            if p.exists():
                candidates.append(str(p))
    else:
        for p in (Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'),
                  Path('/usr/share/fonts/TTF/DejaVuSans.ttf'),
                  Path('/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf'),
                  Path('/usr/share/fonts/truetype/freefont/FreeSans.ttf')):
            if p.exists():
                candidates.append(str(p))
    return candidates


def _rerender_with_total(
    pdf, pgnum: int, page_chapters: dict[int, str],
    header: str, footer: str, show_hdr: bool, show_ftr: bool,
    text_font: str, txt_size: int, g: _Geometry,
) -> None:
    """Re-render page headers/footers that contain {total} once the total page count is known.

    fpdf2 appends to page content streams, so we blank the old area with a white
    rectangle before redrawing with the resolved total.
    """
    if pgnum == 0 or ('{total}' not in header and '{total}' not in footer):
        return
    _saved_page = pdf.page
    for _pn in range(1, pgnum + 1):
        pdf.page = _pn
        pdf.set_fill_color(255, 255, 255)
        _chap  = page_chapters.get(_pn, '')
        _pg_s  = str(_pn)
        _tot_s = str(pgnum)
        if show_hdr and header and '{total}' in header:
            pdf.rect(g.ML, g.HY - 2, g.USABLE_W, 6, style='F')
            txt = header.replace('{chapter}', _chap).replace('{page}', _pg_s).replace('{total}', _tot_s)
            pdf.set_font(text_font, 'B', size=txt_size)
            pdf.set_xy(g.ML, g.HY - 1)
            pdf.cell(w=g.USABLE_W, h=4, text=txt, align='C')
        if show_ftr and footer and '{total}' in footer:
            pdf.rect(g.ML, g.PH - g.FY - 2, g.USABLE_W, 6, style='F')
            txt = footer.replace('{chapter}', _chap).replace('{page}', _pg_s).replace('{total}', _tot_s)
            pdf.set_font(text_font, size=txt_size)
            pdf.set_xy(g.ML, g.PH - g.FY - 1)
            pdf.cell(w=g.USABLE_W, h=4, text=txt, align='C')
    pdf.page = _saved_page


def generate_pdf(positions: list[PositionDict], opts: dict, out_path, progress=None) -> None:
    """Render a list of chess positions to a PDF file.

    Args:
        positions: List of dicts from parse_pgn / parse_fen_file / parse_epd.
                   Each dict must have a 'fen' key; 'comment' is used for titles.
        opts:      Settings dict. Keys:
                     layout_idx   int   Layout preset index (see LAYOUTS).
                     font         str   Chess font name (see FONT_FILES).
                     font_size    int   Chess font pt, 0 = auto.
                     text_size    int   Title/text pt, 0 = auto (proportional).
                     coords       bool  Show board coordinates.
                     flip         bool  Always show board from Black's side.
                     flip_auto    bool  Auto-flip when Black is to move.
                     header       str   Page header text.
                     footer       str   Page footer prefix (page number appended).
                     show_header  bool  Render header.
                     show_footer  bool  Render footer.
                     symbol       str   To-move indicator key (see SYMBOL_CHARS).
                     lines_count  int   Notation lines below each diagram (0–5).
                     lines_mode   str   'plain' or 'numbered'.
                     title_mode   str   'number', 'comment', or 'custom'.
                     title_custom str   Custom title text (used when title_mode='custom').
                     lichess_link bool  Embed Lichess analysis hyperlinks in titles.
        out_path:  Output PDF path (str or Path).
    """
    try:
        from fpdf import FPDF
    except ImportError:
        raise RuntimeError('fpdf2 required — install with: pip install fpdf2')

    coords      = opts.get('coords', True)
    flip        = opts.get('flip', False)
    flip_auto   = opts.get('flip_auto', True)
    header      = opts.get('header', '')
    footer      = opts.get('footer', '')
    show_hdr    = opts.get('show_header', bool(header))
    show_ftr    = opts.get('show_footer', True)
    symbol       = opts.get('symbol', 'square')
    font_name    = opts.get('font', 'AlphaDG')
    lines_count  = int(opts.get('lines_count', 0))
    lines_mode   = opts.get('lines_mode', 'plain')
    title_template  = opts.get('title_template', '')     # e.g. '{number} {comment}'
    title_mode      = opts.get('title_mode', 'comment') # legacy fallback
    title_custom    = opts.get('title_custom', '')       # legacy fallback
    lichess_link    = opts.get('lichess_link', False)
    answers_section = opts.get('answers_section', False)
    figurine_font   = opts.get('figurine_font', 'Zurich' if 'Zurich' in FIGURINE_NAMES else (FIGURINE_NAMES[0] if FIGURINE_NAMES else ''))
    answers_title   = opts.get('answers_title', 'Solutions')
    answers_cols    = min(max(1, int(opts.get('answers_cols', 1))), 2)

    script_dir = _resource('.')   # works in both .py and frozen .exe
    fm = FontManager(script_dir)
    g  = _compute_geometry(opts)

    # Unpack geometry into local names (matches rest of function)
    PW, PH   = g.PW, g.PH
    ML, MR   = g.ML, g.MR
    MT       = g.MT
    HY, FY   = g.HY, g.FY
    USABLE_W = g.USABLE_W
    LINE_H   = g.LINE_H
    cols     = g.cols
    max_rows = g.max_rows
    per_page = g.per_page
    col_w    = g.col_w
    y_top    = g.y_top
    row_h    = g.row_h
    lines_h  = g.lines_h
    chess_pt     = g.chess_pt
    chess_mm     = g.chess_mm
    txt_size     = g.txt_size
    title_lh     = g.title_lh
    title_offset = g.title_offset

    def chess_str(s: str) -> str:
        return ''.join(chr(0xF000 + ord(c)) for c in s)

    pdf = FPDF(unit='mm', format='A4')
    pdf.set_margins(ML, MT, MR)
    pdf.set_auto_page_break(auto=False)
    fm.load_chess(pdf, font_name)

    # Measure actual board width from font metrics (10 chars per row).
    # diag_w = 10 * chess_mm only holds for perfectly monospace fonts;
    # Chess Alpha DG glyph advances may differ slightly from the em square.
    pdf.set_font('Chess', size=chess_pt)
    _sample_row = chess_str(BDR_NW + BDR_N * 8 + BDR_NE)   # representative 10-char board row
    diag_w  = pdf.get_string_width(_sample_row) or (10 * chess_mm)
    x_pad   = (col_w - diag_w) / 2
    char_w  = diag_w / 10          # width of one border/square character
    inner_w = diag_w - 2 * char_w  # width spanning exactly 8 board squares

    _text_font     = fm.load_text(pdf)
    _fig_font_name = fm.load_figurine(pdf, figurine_font, _text_font) if answers_section else _text_font

    pgnum = 0

    def draw_decorations(chapter: str = '') -> None:
        if show_hdr and header:
            txt = header.replace('{chapter}', chapter).replace('{page}', str(pgnum))
            pdf.set_font(_text_font, 'B', size=txt_size)
            pdf.set_xy(ML, HY - 1)
            pdf.cell(w=USABLE_W, h=4, text=txt, align='C')
        if show_ftr and footer:
            txt = footer.replace('{chapter}', chapter).replace('{page}', str(pgnum))
            pdf.set_font(_text_font, size=txt_size)
            pdf.set_xy(ML, PH - FY - 1)
            pdf.cell(w=USABLE_W, h=4, text=txt, align='C')

    valid = [p for p in positions if p.get('fen', '').strip()]

    # Pre-create link IDs so both directions (diag→ans, ans→diag) can reference each other.
    # ans_links[i] == 0 means the position has no moves → no link created.
    # fpdf2 raises ValueError if pdf.cell(link=id) is called before pdf.set_link(id, page, y),
    # so we assign a placeholder (page=1) immediately; the answers section overwrites with real page.
    diag_links: list[int] = []
    ans_links:  list[int] = []
    if answers_section:
        for _p in valid:
            diag_links.append(pdf.add_link())
            _al = pdf.add_link() if _clean_moves(_p.get('moves', '')) else 0
            if _al:
                pdf.set_link(_al, page=1, y=0)   # placeholder; updated in answers section
            ans_links.append(_al)

    total = len(valid)
    slot = 0
    current_chapter = ''
    _page_chapters: dict[int, str] = {}   # pgnum → chapter name (for {total} re-render)

    for pos_idx, pos in enumerate(valid):
        if progress and total > 0:
            progress(int((pos_idx + 1) * 100 / total))

        pos_chapter = pos.get('chapter', '')
        if pos_chapter and pos_chapter != current_chapter:
            current_chapter = pos_chapter
            if pos_idx > 0:
                slot = 0   # force page break on chapter change

        if slot == 0:
            pgnum += 1
            _page_chapters[pgnum] = current_chapter
            pdf.add_page()
            draw_decorations(current_chapter)

        col_idx = slot % cols
        row_idx = slot // cols
        x = ML + col_idx * col_w + x_pad
        y = y_top + row_idx * row_h

        # ── Title (above diagram) ─────────────────────────────────────────────
        fen     = pos.get('fen', '').strip()
        num     = pos_idx + 1
        title = _make_title(pos, num, title_template, title_mode, title_custom)

        _side = parse_fen(fen)[1] if (lichess_link or lines_count > 0) else ''
        link_url = ''
        if lichess_link:
            _color = 'black' if _side == 'b' else 'white'
            link_url = f'https://lichess.org/analysis/{fen.strip().replace(" ", "_")}?color={_color}'

        y_diag = y   # board at row top; title embeds in top border row

        # Set diagram anchor (for links from answers section back to this diagram)
        if diag_links:
            pdf.set_link(diag_links[pos_idx], page=pgnum, y=y_diag)

        # ── Diagram ───────────────────────────────────────────────────────────
        try:
            diag_lines = fen_to_diagram(fen, coords=coords, flip=flip,
                                        flip_auto=flip_auto, symbol=symbol)
            pdf.set_font('Chess', size=chess_pt)
            for i, ln in enumerate(diag_lines):
                pdf.set_xy(x, y_diag + i * chess_mm)
                pdf.cell(w=diag_w, h=chess_mm, text=chess_str(ln))
            # Lichess link overlaid on the side-to-move symbol (right border, visual bottom rank).
            # The symbol is always in diag_lines[8] (last rank row before bottom border).
            if lichess_link and link_url:
                pdf.link(x=x + diag_w - char_w, y=y_diag + 8 * chess_mm,
                         w=char_w, h=chess_mm, link=link_url)
        except Exception as e:
            print(f'Warning: FEN render error ({fen!r}): {e}', file=sys.stderr)
            pdf.set_font(_text_font, size=8)
            pdf.set_xy(x, y_diag)
            pdf.cell(w=diag_w, h=5, text='[FEN error]')

        # ── Title (centered in top border row, over inner 8 squares) ─────────
        # When answers section is active: title links to answer; Lichess goes on symbol.
        # When no answers section: title links to Lichess (if enabled).
        _title_link: int | str = ans_links[pos_idx] if ans_links else link_url
        title_cy = y_diag + (chess_mm - title_lh) / 2 + title_offset
        pdf.set_font(_text_font, 'B', size=txt_size)
        pdf.set_xy(x + char_w, title_cy)
        pdf.cell(w=inner_w, h=title_lh, text=title, align='C', link=_title_link)

        # ── Notation lines ───────────────────────────────────────────────────
        if lines_count > 0:
            base_y  = y_diag + 10 * chess_mm + 0.5
            lx      = x + char_w                       # start after left border
            gap_w   = min(2.0, inner_w * 0.06)         # gap between the two blanks
            pdf.set_line_width(0.2)
            for li in range(lines_count):
                ly = base_y + li * LINE_H + LINE_H - 1
                if lines_mode == 'numbered':
                    move_num = li + 1
                    pdf.set_font(_text_font, size=7)
                    num_text = f'{move_num}.'
                    num_w = pdf.get_string_width(num_text) + 0.8   # +0.8mm gap after label
                    blank_w = (inner_w - num_w - gap_w) / 2
                    pdf.text(lx, ly, num_text)
                    x0 = lx + num_w
                    x1 = x0 + blank_w
                    x2 = x1 + gap_w
                    x3 = x2 + blank_w
                    if li == 0 and _side == 'b':
                        # Black to move: skip white's blank, draw only black's blank
                        pdf.line(x2, ly, x3, ly)
                    else:
                        pdf.line(x0, ly, x1, ly)
                        pdf.line(x2, ly, x3, ly)
                else:
                    # plain mode: single full-width line
                    pdf.line(lx, ly, lx + inner_w, ly)

        slot += 1
        if slot >= per_page:
            slot = 0

    if pgnum == 0:
        pdf.add_page()

    # ── Answers section ───────────────────────────────────────────────────────
    if answers_section and any(_clean_moves(v.get('moves', '')) for v in valid):
        _ans_fsize = txt_size
        _ans_lh    = title_lh + 0.5   # slightly taller line height
        _col_w     = USABLE_W / answers_cols

        def _ans_col_x(ci: int) -> float:
            return ML + ci * _col_w

        def _set_ans_margins(ci: int) -> None:
            pdf.set_left_margin(_ans_col_x(ci))
            pdf.set_right_margin(PW - (_ans_col_x(ci) + _col_w))

        # Section heading text — also used as {chapter} on all answers pages
        _head = answers_title.strip() or 'Solutions'

        def _ans_new_page() -> None:
            nonlocal pgnum
            pgnum += 1
            _page_chapters[pgnum] = _head
            pdf.add_page()
            draw_decorations(_head)
            pdf.set_y(MT)

        pgnum += 1
        _page_chapters[pgnum] = _head
        pdf.add_page()
        draw_decorations(_head)
        pdf.set_font(_text_font, 'B', size=_ans_fsize + 2)
        pdf.set_xy(ML, MT)
        pdf.cell(w=USABLE_W, h=_ans_lh + 2, text=_head, align='C', new_x='LMARGIN', new_y='NEXT')
        pdf.ln(3)

        _cur_col   = 0
        _col_top_y = pdf.get_y()   # content start Y (after heading on first page)
        _set_ans_margins(_cur_col)

        for _ai, _pos in enumerate(valid):
            _moves_raw = _pos.get('moves', '').strip()
            if not _moves_raw:
                continue
            _moves = _clean_moves(_moves_raw)
            if not _moves:
                continue

            # Column/page overflow: need at least 2 line heights remaining
            if pdf.get_y() > PH - MT - _ans_lh * 2:
                if answers_cols > 1 and _cur_col == 0:
                    # Switch to right column on the same page
                    _cur_col = 1
                    _set_ans_margins(_cur_col)
                    pdf.set_y(_col_top_y)
                else:
                    # Start a new page, back to left column
                    _ans_new_page()
                    _cur_col = 0
                    _col_top_y = MT
                    _set_ans_margins(_cur_col)

            # Set answer anchor (links from diagram titles point here)
            if ans_links:
                pdf.set_link(ans_links[_ai], page=pgnum, y=pdf.get_y())

            # Number label — bold, links back to diagram
            _num_label = f'{_ai + 1}. '
            _diag_link: int | str = diag_links[_ai] if diag_links else ''
            pdf.set_font(_text_font, 'B', size=_ans_fsize)
            _nl_w = pdf.get_string_width(_num_label) + 1.0
            pdf.set_x(_ans_col_x(_cur_col))
            pdf.cell(w=_nl_w, h=_ans_lh, text=_num_label, link=_diag_link)

            # Moves text — build segments, switching to figurine font for piece letters
            _segs: list[tuple[str, str]] = []
            _cur_font = _text_font
            _buf = ''
            for _ch in _moves:
                _want = _fig_font_name if _ch in FIGURINE_PIECE_CHARS else _text_font
                if _want != _cur_font:
                    if _buf:
                        _segs.append((_cur_font, _buf))
                    _buf = _ch
                    _cur_font = _want
                else:
                    _buf += _ch
            if _buf:
                _segs.append((_cur_font, _buf))

            for _seg_font, _seg_text in _segs:
                pdf.set_font(_seg_font, size=_ans_fsize)
                pdf.write(h=_ans_lh, text=_seg_text)

            pdf.ln(_ans_lh)

        # Restore page margins
        pdf.set_left_margin(ML)
        pdf.set_right_margin(MR)

    # ── Re-render headers/footers with {total} resolved ──────────────────────
    _rerender_with_total(pdf, pgnum, _page_chapters,
                         header, footer, show_hdr, show_ftr,
                         _text_font, txt_size, g)

    pdf.output(str(out_path))


# ─────────────────────────────────────────────────────────────────────────────
# GUI helpers
# ─────────────────────────────────────────────────────────────────────────────

def _setup_theme(root, ttk) -> tuple[str, str, str, str]:
    """Apply sv-ttk (if available) or a custom clam theme to *root*.

    Returns (OK, ERR, ACCENT, FONT_FAMILY) — colour/font constants needed
    by the rest of the GUI for status labels and logo text.
    """
    BG     = '#F0F4F8'
    CARD   = '#FFFFFF'
    BDR    = '#CBD5E1'
    ACCENT = '#2563EB'
    AHOV   = '#1D4ED8'
    ADIS   = '#94A3B8'
    FG     = '#0F172A'
    FG2    = '#64748B'
    OK     = '#15803D'
    ERR    = '#B91C1C'
    F      = 'Segoe UI'

    st = ttk.Style(root)
    try:
        import sv_ttk  # type: ignore[import]
        sv_ttk.set_theme('light')
    except ImportError:
        if 'clam' in st.theme_names():
            st.theme_use('clam')
        root.configure(bg=BG)
        st.configure('.',            background=BG, foreground=FG, font=(F, 9))
        st.configure('TFrame',       background=BG)
        st.configure('TLabel',       background=BG, foreground=FG, font=(F, 9))
        st.configure('TCheckbutton', background=BG, foreground=FG, font=(F, 9))
        st.configure('TRadiobutton', background=BG, foreground=FG, font=(F, 9))
        st.configure('TEntry',       fieldbackground=CARD, foreground=FG,
                     insertcolor=FG, bordercolor=BDR, lightcolor=BDR, darkcolor=BDR)
        st.configure('TCombobox',    fieldbackground=CARD, background=CARD,
                     foreground=FG, selectbackground=ACCENT, selectforeground=CARD,
                     bordercolor=BDR, arrowcolor=FG2)
        st.map('TCombobox', fieldbackground=[('readonly', CARD)])

    st.configure('SectionHdr.TLabel', foreground=ACCENT, font=(F, 8, 'bold'))
    st.configure('Accent.TButton',
                 background=ACCENT, foreground='white',
                 font=(F, 10, 'bold'), relief='flat', borderwidth=0,
                 focuscolor=ACCENT, padding=(20, 8))
    st.map('Accent.TButton',
           background=[('active', AHOV), ('disabled', ADIS)],
           foreground=[('disabled', '#E2E8F0')])
    st.configure('Browse.TButton',
                 foreground=ACCENT, font=(F, 9), relief='flat',
                 borderwidth=1, bordercolor=BDR, padding=(6, 3))
    st.map('Browse.TButton', background=[('active', '#EFF6FF')])

    return OK, ERR, ACCENT, F


_CONFIG_PATH = Path.home() / '.diagpdf.json'

def _load_config() -> dict:
    try:
        return json.loads(_CONFIG_PATH.read_text(encoding='utf-8'))
    except Exception:
        return {}

def _save_config(data: dict) -> None:
    try:
        _CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding='utf-8')
    except Exception as e:
        print(f'Warning: could not save settings: {e}', file=sys.stderr)


def run_gui():
    try:
        import tkinter as tk
        from tkinter import ttk, filedialog, messagebox
    except ImportError:
        print('tkinter not available. Use command-line mode.', file=sys.stderr)
        sys.exit(1)

    cfg  = _load_config()
    lang: str = cfg.get('lang', 'en')

    root = tk.Tk()
    root.resizable(False, False)
    OK, ERR, ACCENT, F = _setup_theme(root, ttk)

    FG2 = '#64748B'  # secondary text colour (used for status label)

    # ── Variables ──────────────────────────────────────────────────────────────
    v_input       = tk.StringVar()
    v_output      = tk.StringVar()
    v_layout      = tk.IntVar(value=cfg.get('layout', DEFAULT_LAYOUT))
    v_font        = tk.StringVar(value=cfg.get('font', FONT_NAMES[0]))
    v_coords      = tk.BooleanVar(value=cfg.get('coords', True))
    v_orient      = tk.StringVar(value=cfg.get('orient', 'auto'))
    v_header      = tk.StringVar(value=cfg.get('header', ''))
    v_footer      = tk.StringVar(value=cfg.get('footer', '{page}'))
    v_sh_hdr      = tk.BooleanVar(value=cfg.get('show_header', True))
    v_sh_ftr      = tk.BooleanVar(value=cfg.get('show_footer', True))
    v_symbol      = tk.StringVar(value=cfg.get('symbol', 'square'))
    v_lines_count = tk.IntVar(value=cfg.get('lines_count', 0))
    v_lines_mode  = tk.StringVar(value=cfg.get('lines_mode', 'plain'))
    v_font_size   = tk.IntVar(value=cfg.get('font_size', 0))
    v_title_template = tk.StringVar(value=cfg.get('title_template', '{number} {comment}'))
    v_lichess       = tk.BooleanVar(value=cfg.get('lichess', False))
    v_answers       = tk.BooleanVar(value=cfg.get('answers_section', False))
    v_answers_title = tk.StringVar(value=cfg.get('answers_title', 'Solutions'))
    v_answers_cols  = tk.IntVar(value=cfg.get('answers_cols', 1))
    v_fig_font      = tk.StringVar(value=cfg.get('figurine_font', 'Zurich' if 'Zurich' in FIGURINE_NAMES else (FIGURINE_NAMES[0] if FIGURINE_NAMES else '')))
    v_status        = tk.StringVar(value='')

    widgets: dict[str, Any] = {}

    def t(key: str) -> Any:
        entry = T.get(key)
        if entry is None:
            return key
        return entry[0] if lang == 'en' else entry[1]

    _last_pdf:  Path = Path()
    _generated: bool = False   # True after successful generation

    def set_status(msg: str, ok: bool = True) -> None:
        v_status.set(msg)
        status_lbl.config(foreground=OK if ok else ERR)

    def on_setting_change(*_) -> None:
        nonlocal _generated
        if _generated:
            _generated = False
            set_status(t('ready'))

    def open_last_pdf() -> None:
        import subprocess
        p = _last_pdf
        if p.exists():
            subprocess.Popen(['start', '', str(p)], shell=True)

    root.title(f'DiagPDF {__version__}')
    _ico = _resource('icon.ico')
    if _ico.exists():
        try:
            root.iconbitmap(str(_ico))
        except Exception:
            pass

    def apply_lang() -> None:
        for key, w in widgets.items():
            try:
                w.config(text=t(key))
            except Exception:
                pass
        lbl_idx = 1 if lang == 'ru' else 0
        layout_cb['values'] = [str(lay[lbl_idx]) for lay in LAYOUTS]
        layout_cb.current(v_layout.get())
        set_status(t('ready'))

    def toggle_lang() -> None:
        nonlocal lang
        lang = 'ru' if lang == 'en' else 'en'
        apply_lang()

    def update_btn_state(*_) -> None:
        state = 'normal' if v_input.get().strip() else 'disabled'
        widgets['convert'].config(state=state)

    def browse_input() -> None:
        f = filedialog.askopenfilename(title=t('open_title'), filetypes=t('open_types'))
        if f:
            v_input.set(str(Path(f)))
            v_output.set(str(Path(f).with_suffix('.pdf')))
            try:
                _content = Path(f).read_text(encoding='utf-8-sig', errors='replace')
                _has_ch = bool(re.search(r'^\[Chapter\s+"[^"]+"\]', _content, re.MULTILINE))
            except Exception:
                _has_ch = False
            v_header.set('{chapter}' if _has_ch else Path(f).stem)

    def browse_output() -> None:
        f = filedialog.asksaveasfilename(title=t('save_title'), defaultextension='.pdf',
                                         filetypes=t('save_types'))
        if f:
            v_output.set(f)

    def convert() -> None:
        nonlocal _last_pdf, _generated
        in_path = Path(v_input.get().strip())
        out_str = v_output.get().strip()
        out_path = Path(out_str).with_suffix('.pdf') if out_str else in_path.with_suffix('.pdf')
        if not in_path.exists():
            messagebox.showerror('Error', t('err_not_found').format(in_path))
            return
        ext = in_path.suffix.lower()
        try:
            content = in_path.read_text(encoding='utf-8-sig', errors='replace')
            if ext == '.pgn':
                positions = parse_pgn(content)
            elif ext == '.fen':
                positions = parse_fen_file(content)
            elif ext == '.epd':
                positions = parse_epd(content)
            else:
                messagebox.showerror('Error', t('err_unknown').format(ext))
                return
            if not positions:
                messagebox.showerror('Error', t('err_no_pos'))
                return
            orient = v_orient.get()
            opts = {
                'layout_idx':  v_layout.get(),
                'font':        v_font.get(),
                'font_size':   v_font_size.get(),
                'text_size':   0,
                'coords':      v_coords.get(),
                'flip':        orient == 'black',
                'flip_auto':   orient == 'auto',
                'header':      v_header.get(),
                'footer':      v_footer.get(),
                'show_header': v_sh_hdr.get(),
                'show_footer': v_sh_ftr.get(),
                'symbol':       v_symbol.get(),
                'lines_count':  v_lines_count.get(),
                'lines_mode':   v_lines_mode.get(),
                'title_template':  v_title_template.get(),
                'lichess_link':    v_lichess.get(),
                'answers_section': v_answers.get(),
                'answers_title':   v_answers_title.get(),
                'answers_cols':    v_answers_cols.get(),
                'figurine_font':   v_fig_font.get(),
            }
            def on_progress(pct: int) -> None:
                set_status(f'{pct}%')
                root.update()
            generate_pdf(positions, opts, out_path, progress=on_progress)
            _last_pdf = out_path
            _generated = True
            widgets['open_pdf'].config(state='normal')
            set_status(t('done').format(len(positions), out_path.name))
        except Exception as e:
            messagebox.showerror('Error', str(e))
            set_status(t('error').format(e), ok=False)

    # ══════════════════════════════════════════════════════════════════════════
    # Layout — flat form, no card borders
    # ══════════════════════════════════════════════════════════════════════════
    root.configure(padx=20, pady=16)
    main = ttk.Frame(root)
    main.pack(fill='both', expand=True)

    # ── Top bar ────────────────────────────────────────────────────────────────
    top = ttk.Frame(main)
    top.pack(fill='x', pady=(0, 10))
    ttk.Label(top, text='DiagPDF',
              font=(F, 13, 'bold'), foreground=ACCENT).pack(side='left')
    lang_btn = ttk.Button(top, command=toggle_lang, width=4)
    lang_btn.pack(side='right')
    widgets['lang_btn'] = lang_btn

    # ── Section helper: bold label + separator line ────────────────────────────
    def section(key: str) -> None:
        lbl = ttk.Label(main, style='SectionHdr.TLabel')
        lbl.pack(fill='x', pady=(4, 2))
        widgets[key] = lbl
        ttk.Separator(main, orient='horizontal').pack(fill='x', pady=(0, 8))

    # ── FILES ──────────────────────────────────────────────────────────────────
    section('section_files')
    files_fr = ttk.Frame(main)
    files_fr.pack(fill='x', pady=(0, 6))
    files_fr.columnconfigure(1, weight=1)
    files_fr.columnconfigure(0, minsize=105)

    lbl = ttk.Label(files_fr, anchor='w')
    lbl.grid(row=0, column=0, sticky='w', padx=(0, 8), pady=(0, 5))
    widgets['input_file'] = lbl
    ttk.Entry(files_fr, textvariable=v_input).grid(
        row=0, column=1, sticky='ew', padx=(0, 6), pady=(0, 5))
    ttk.Button(files_fr, text='\u2026', command=browse_input,
               style='Browse.TButton', width=3).grid(row=0, column=2, pady=(0, 5))

    lbl = ttk.Label(files_fr, anchor='w')
    lbl.grid(row=1, column=0, sticky='w', padx=(0, 8))
    widgets['output_pdf'] = lbl
    ttk.Entry(files_fr, textvariable=v_output).grid(
        row=1, column=1, sticky='ew', padx=(0, 6))
    ttk.Button(files_fr, text='\u2026', command=browse_output,
               style='Browse.TButton', width=3).grid(row=1, column=2)

    # ── PAGE ───────────────────────────────────────────────────────────────────
    section('section_page')
    page_fr = ttk.Frame(main)
    page_fr.pack(fill='x', pady=(0, 6))
    page_fr.columnconfigure(1, weight=1)
    page_fr.columnconfigure(4, weight=1)

    lbl = ttk.Label(page_fr, anchor='w')
    lbl.grid(row=0, column=0, sticky='w', padx=(0, 6), pady=(0, 5))
    widgets['header_text'] = lbl
    ttk.Entry(page_fr, textvariable=v_header).grid(
        row=0, column=1, sticky='ew', padx=(0, 4), pady=(0, 5))
    cb = ttk.Checkbutton(page_fr, variable=v_sh_hdr)
    cb.grid(row=0, column=2, padx=(0, 20), pady=(0, 5))
    widgets['show_header'] = cb
    lbl = ttk.Label(page_fr, anchor='w')
    lbl.grid(row=0, column=3, sticky='w', padx=(0, 6), pady=(0, 5))
    widgets['layout'] = lbl
    lbl_idx = 1 if lang == 'ru' else 0
    layout_cb = ttk.Combobox(page_fr, width=20, state='readonly',
                              values=[str(lay[lbl_idx]) for lay in LAYOUTS])
    layout_cb.current(DEFAULT_LAYOUT)
    layout_cb.grid(row=0, column=4, sticky='ew', pady=(0, 5))
    layout_cb.bind('<<ComboboxSelected>>', lambda _: v_layout.set(layout_cb.current()))

    lbl = ttk.Label(page_fr, anchor='w')
    lbl.grid(row=1, column=0, sticky='w', padx=(0, 6))
    widgets['footer_text'] = lbl
    ttk.Entry(page_fr, textvariable=v_footer).grid(
        row=1, column=1, sticky='ew', padx=(0, 4))
    cb = ttk.Checkbutton(page_fr, variable=v_sh_ftr)
    cb.grid(row=1, column=2, padx=(0, 20))
    widgets['show_footer'] = cb
    lbl = ttk.Label(page_fr, anchor='w')
    lbl.grid(row=1, column=3, sticky='w', padx=(0, 6))
    widgets['font'] = lbl
    ttk.Combobox(page_fr, textvariable=v_font, width=20, state='readonly',
                 values=FONT_NAMES).grid(row=1, column=4, sticky='ew')

    # Font size (row 2)
    widgets['font_size_lbl'] = ttk.Label(page_fr, anchor='w')
    widgets['font_size_lbl'].grid(row=2, column=3, sticky='w', padx=(0, 6), pady=(4, 0))
    ttk.Spinbox(page_fr, textvariable=v_font_size, from_=0, to=36, width=5,
                ).grid(row=2, column=4, sticky='w', pady=(4, 0))

    # ── DIAGRAM ────────────────────────────────────────────────────────────────
    section('section_diagram')
    diag_fr = ttk.Frame(main)
    diag_fr.pack(fill='x')
    diag_fr.columnconfigure(0, minsize=140)
    diag_fr.columnconfigure(1, weight=1)

    # Move indicator — single row (square / circle / triangle)
    lbl = ttk.Label(diag_fr, anchor='w')
    lbl.grid(row=0, column=0, sticky='w', padx=(0, 8), pady=(0, 6))
    widgets['symbol'] = lbl
    sym_fr = ttk.Frame(diag_fr)
    sym_fr.grid(row=0, column=1, sticky='w', pady=(0, 6))
    for _sk, _wkey in [('square', 'sym_square'), ('circle', 'sym_circle'), ('triangle', 'sym_triangle')]:
        rb = ttk.Radiobutton(sym_fr, variable=v_symbol, value=_sk)
        rb.pack(side='left', padx=(0, 6))
        widgets[_wkey] = rb

    # Lines per diagram: count (row 1), mode (row 2 indented — avoids overflow in RU)
    lbl = ttk.Label(diag_fr, anchor='w')
    lbl.grid(row=1, column=0, sticky='w', padx=(0, 8), pady=(0, 3))
    widgets['lines_count'] = lbl
    lc_fr = ttk.Frame(diag_fr)
    lc_fr.grid(row=1, column=1, sticky='w', pady=(0, 3))
    for _n in range(6):
        ttk.Radiobutton(lc_fr, text=str(_n),
                        variable=v_lines_count, value=_n).pack(side='left', padx=(0, 4))

    lm_fr = ttk.Frame(diag_fr)
    lm_fr.grid(row=2, column=1, sticky='w', pady=(0, 6))
    rb = ttk.Radiobutton(lm_fr, variable=v_lines_mode, value='plain')
    rb.pack(side='left', padx=(0, 4))
    widgets['lines_plain'] = rb
    rb = ttk.Radiobutton(lm_fr, variable=v_lines_mode, value='numbered')
    rb.pack(side='left', padx=(0, 4))
    widgets['lines_numbered'] = rb

    # Orientation + coordinates on same row
    lbl = ttk.Label(diag_fr, anchor='w')
    lbl.grid(row=3, column=0, sticky='w', padx=(0, 8), pady=(0, 6))
    widgets['orient'] = lbl
    or_fr = ttk.Frame(diag_fr)
    or_fr.grid(row=3, column=1, sticky='w', pady=(0, 6))
    for _val, _key in (('auto', 'orient_auto'), ('white', 'orient_white'), ('black', 'orient_black')):
        rb = ttk.Radiobutton(or_fr, variable=v_orient, value=_val)
        rb.pack(side='left', padx=(0, 4))
        widgets[_key] = rb
    ttk.Frame(or_fr, width=10).pack(side='left')
    cb = ttk.Checkbutton(or_fr, variable=v_coords)
    cb.pack(side='left')
    widgets['coords'] = cb

    # Title template field
    lbl = ttk.Label(diag_fr, anchor='w')
    lbl.grid(row=4, column=0, sticky='w', padx=(0, 8), pady=(0, 6))
    widgets['title_source'] = lbl
    tpl_fr = ttk.Frame(diag_fr)
    tpl_fr.grid(row=4, column=1, sticky='ew', pady=(0, 6))
    tpl_fr.columnconfigure(0, weight=1)
    ttk.Entry(tpl_fr, textvariable=v_title_template).grid(row=0, column=0, sticky='ew')

    def _show_template_help() -> None:
        messagebox.showinfo(t('tpl_help_title'), t('tpl_help_body'))

    ttk.Button(tpl_fr, text='?', width=2, command=_show_template_help).grid(
        row=0, column=1, padx=(4, 0))

    # Lichess
    cb = ttk.Checkbutton(diag_fr, variable=v_lichess)
    cb.grid(row=5, column=0, columnspan=2, sticky='w', pady=(0, 6))
    widgets['lichess_link'] = cb

    # Answers section
    ans_cb = ttk.Checkbutton(diag_fr, variable=v_answers)
    ans_cb.grid(row=6, column=0, columnspan=2, sticky='w', pady=(0, 4))
    widgets['answers_section'] = ans_cb

    # Answers heading label + entry
    widgets['answers_title_lbl'] = ttk.Label(diag_fr)
    widgets['answers_title_lbl'].grid(row=7, column=0, sticky='w', pady=(0, 4))
    ttk.Entry(diag_fr, textvariable=v_answers_title).grid(row=7, column=1, sticky='ew', pady=(0, 4))

    # Answer columns label + combobox (1 or 2)
    widgets['answers_cols_lbl'] = ttk.Label(diag_fr)
    widgets['answers_cols_lbl'].grid(row=8, column=0, sticky='w', pady=(0, 4))
    ttk.Combobox(diag_fr, textvariable=v_answers_cols, values=['1', '2'],
                 state='readonly', width=4).grid(row=8, column=1, sticky='w', pady=(0, 4))

    # Figurine font label + combobox
    widgets['figurine_font_lbl'] = ttk.Label(diag_fr)
    widgets['figurine_font_lbl'].grid(row=9, column=0, sticky='w', pady=(0, 6))
    ttk.Combobox(diag_fr, textvariable=v_fig_font, values=FIGURINE_NAMES,
                 state='readonly', width=14).grid(row=9, column=1, sticky='w', pady=(0, 6))

    # ── Generate PDF button ────────────────────────────────────────────────────
    ttk.Separator(main, orient='horizontal').pack(fill='x', pady=(6, 10))
    btn_fr = ttk.Frame(main)
    btn_fr.pack()
    conv_btn = ttk.Button(btn_fr, command=convert, style='Accent.TButton', state='disabled')
    conv_btn.pack(side='left', ipadx=8, ipady=2)
    widgets['convert'] = conv_btn
    open_btn = ttk.Button(btn_fr, command=open_last_pdf, state='disabled')
    open_btn.pack(side='left', padx=(8, 0), ipadx=8, ipady=2)
    widgets['open_pdf'] = open_btn

    # ── Status bar ─────────────────────────────────────────────────────────────
    status_lbl = ttk.Label(main, textvariable=v_status, font=(F, 8), foreground=FG2)
    status_lbl.pack(pady=(6, 0))

    def on_close() -> None:
        _save_config({
            'lang':         lang,
            'layout':       v_layout.get(),
            'font':         v_font.get(),
            'font_size':    v_font_size.get(),
            'coords':       v_coords.get(),
            'orient':       v_orient.get(),
            'header':       v_header.get(),
            'footer':       v_footer.get(),
            'show_header':  v_sh_hdr.get(),
            'show_footer':  v_sh_ftr.get(),
            'symbol':       v_symbol.get(),
            'lines_count':  v_lines_count.get(),
            'lines_mode':   v_lines_mode.get(),
            'title_template':  v_title_template.get(),
            'lichess':         v_lichess.get(),
            'answers_section': v_answers.get(),
            'answers_title':   v_answers_title.get(),
            'answers_cols':    v_answers_cols.get(),
            'figurine_font':   v_fig_font.get(),
        })
        root.destroy()

    v_input.trace_add('write', update_btn_state)
    for _sv in (v_layout, v_font, v_font_size, v_coords, v_orient, v_header, v_footer,
                v_sh_hdr, v_sh_ftr, v_symbol, v_lines_count, v_lines_mode,
                v_title_template, v_lichess, v_answers, v_answers_title, v_answers_cols, v_fig_font):
        _sv.trace_add('write', on_setting_change)
    root.protocol('WM_DELETE_WINDOW', on_close)
    # Measure both languages and fix window to the larger size
    # so that toggling language never resizes the window.
    apply_lang()
    root.update_idletasks()
    _w, _h = root.winfo_reqwidth(), root.winfo_reqheight()
    toggle_lang()
    root.update_idletasks()
    _w = max(_w, root.winfo_reqwidth())
    _h = max(_h, root.winfo_reqheight())
    toggle_lang()   # restore original language
    root.geometry(f'{_w}x{_h}')
    root.resizable(False, False)
    root.mainloop()


# ─────────────────────────────────────────────────────────────────────────────
# CLI entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Convert PGN/FEN/EPD chess files to PDF diagrams (Chess Alpha DG fonts).'
    )
    parser.add_argument('--version', action='version', version=f'DiagPDF {__version__}')
    parser.add_argument('input', nargs='?', help='Input file (.pgn, .fen, .epd)')
    parser.add_argument('-o', '--output', help='Output PDF (default: <input>.pdf)')
    parser.add_argument('-l', '--layout', type=int, default=DEFAULT_LAYOUT,
                        help=f'Layout preset 0–{len(LAYOUTS)-1} (default {DEFAULT_LAYOUT}: 2-col 6/4)')
    parser.add_argument('-f', '--font', choices=FONT_NAMES, default='AlphaDG',
                        help='Chess font (default: AlphaDG)')
    parser.add_argument('--no-coords', action='store_true', help='Hide board coordinates')
    parser.add_argument('--flip', action='store_true', help='Flip board (black at bottom)')
    parser.add_argument('--no-auto-flip', action='store_true',
                        help='Disable auto-flip when Black is to move')
    parser.add_argument('--header', default='', help='Header text (default: filename stem)')
    parser.add_argument('--footer', default='', help='Footer prefix (default: page number only)')
    parser.add_argument('--no-header', action='store_true', help='Suppress header')
    parser.add_argument('--no-footer', action='store_true', help='Suppress footer')
    parser.add_argument('--symbol', choices=SYMBOL_KEYS, default='square',
                        help='To-move indicator symbol (default: square)')
    parser.add_argument('--lines', type=int, default=0, choices=range(6),
                        help='Notation lines per diagram (default: 0)')
    parser.add_argument('--lines-numbered', action='store_true',
                        help='Prefix notation lines with move numbers')
    parser.add_argument('--title-template', default='',
                        help='Title template, e.g. "{number} {comment}" (vars: number, event, white, black, date, comment)')
    parser.add_argument('--font-size', type=int, default=0,
                        help='Board font size in pt (0 = auto)')
    parser.add_argument('--lichess-link', action='store_true',
                        help='Embed clickable Lichess analysis links in position titles')
    parser.add_argument('--answers', action='store_true',
                        help='Append answers section at the end of the document')
    parser.add_argument('--answers-title', default='Solutions',
                        help='Heading for the answers section (default: Solutions)')
    parser.add_argument('--answers-cols', type=int, default=1, choices=[1, 2],
                        help='Columns in the answers section (1 or 2, default: 1)')
    parser.add_argument('--figurine-font', default='Zurich',
                        choices=FIGURINE_NAMES if FIGURINE_NAMES else ['Zurich'],
                        help='Figurine font for piece symbols in answers (default: Zurich)')
    parser.add_argument('--gui', action='store_true', help='Launch GUI')

    args = parser.parse_args()

    if args.gui or args.input is None:
        run_gui()
        return

    in_path = Path(args.input)
    if not in_path.exists():
        print(f'Error: file not found: {args.input}', file=sys.stderr)
        sys.exit(1)

    out_path = Path(args.output) if args.output else in_path.with_suffix('.pdf')
    ext = in_path.suffix.lower()

    try:
        content = in_path.read_text(encoding='utf-8-sig', errors='replace')
    except OSError as e:
        print(f'Error reading file: {e}', file=sys.stderr)
        sys.exit(1)

    if ext == '.pgn':
        positions = parse_pgn(content)
    elif ext == '.fen':
        positions = parse_fen_file(content)
    elif ext == '.epd':
        positions = parse_epd(content)
    else:
        print(f'Error: unknown extension "{ext}" (expected .pgn, .fen, .epd)', file=sys.stderr)
        sys.exit(1)

    if not positions:
        print('Warning: no positions found.', file=sys.stderr)

    opts = {
        'layout_idx':  max(0, min(args.layout, len(LAYOUTS) - 1)),
        'font':        args.font,
        'font_size':   0,
        'text_size':   0,
        'coords':      not args.no_coords,
        'flip':        args.flip,
        'flip_auto':   not args.no_auto_flip,
        'header':      args.header or in_path.stem,
        'footer':      args.footer or '{page}',
        'show_header': not args.no_header,
        'show_footer': not args.no_footer,
        'symbol':      args.symbol,
        'lines_count':  args.lines,
        'lines_mode':   'numbered' if args.lines_numbered else 'plain',
        'title_template': args.title_template or '{number} {comment}',
        'lichess_link': args.lichess_link,
        'answers_section': args.answers,
        'answers_title':   args.answers_title,
        'answers_cols':    args.answers_cols,
        'figurine_font':   args.figurine_font,
    }

    try:
        generate_pdf(positions, opts, out_path)
    except OSError as e:
        print(f'Error writing output: {e}', file=sys.stderr)
        sys.exit(1)

    print(f'Converted {len(positions)} position(s) -> {out_path}')


if __name__ == '__main__':
    main()
