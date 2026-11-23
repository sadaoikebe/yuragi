"""Load Mozc OSS text dictionary + connection matrix for token-lattice Viterbi."""

from __future__ import annotations

from array import array
from contextlib import suppress
import hashlib
import json
import os
import pickle
import re
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Literal

ROOT = Path(__file__).resolve().parents[2]
DICT_DIR = ROOT / "third_party" / "mozc_oss_dict"
MANIFEST = ROOT / "data" / "dictionary-manifest.json"
CACHE_FORMAT = "mozc_lex_v6"


def files_digest(manifest: Path = MANIFEST) -> str:
    """The hash of the manifest's file list (names, sizes, SHA-256): another dictionary, another digest.

    It names the installer's shared copy of the dictionary (DESIGN「置き場所」) and the cache.
    """
    files = json.loads(Path(manifest).read_text(encoding="utf-8"))["files"]
    return hashlib.sha256(json.dumps(files, sort_keys=True).encode("ascii")).hexdigest()[:16]


def cache_name(manifest: Path = MANIFEST) -> str:
    """The cache file's name: the format and the hash of the manifest's file list.

    A cache is read for the dictionary the manifest names; the installer verifies the
    files against it (DESIGN「起動時の読み込み」). Text changed by hand in a working
    tree keeps the old cache: delete it.
    """
    return f"{CACHE_FORMAT}-{files_digest(manifest)}.pkl"


CACHE_DIR = ROOT / "data" / "cache"
USER_LEX = ROOT / "data" / "user_lexicon.jsonl"


class DictionaryFormatError(ValueError):
    """A dictionary line that is not reading/lid/rid/cost/surface (DESIGN「起動時の読み込み」).

    The files are checked against the manifest's hashes, so this never happens
    with an intact dictionary; when it does, loading stops instead of skipping.
    """


class CacheWriteError(OSError):
    """The rebuilt dictionary cache could not be written (disk space etc.)."""
DEFAULT_NOUN_ID = 1851  # 名詞,一般 in Mozc id.def

BOS_ID = 0
NUMBER_ID = 2044  # 名詞,数,アラビア数字
COUNTER_IDS = range(2011, 2019)  # 名詞,接尾,助数詞 (including 月)
NUMBER_UNIT_IDS = range(2047, 2056)  # 名詞,数,漢数字 for units like 千 and 百
MONTH_COUNTER_ID = 2016
PARTICLE_IDS = range(268, 434)  # 助詞
RANGE_PARTICLE_IDS = (314, 368)  # まで and から
ARITHMETIC_OPERATORS = frozenset(("プラス", "マイナス"))
# An unqualified numeral gets a larger penalty at the end of a run. Keep the
# smaller penalty inside a run so more compound candidates stay in range.
DIGIT_PENALTY = 2500
UNQUALIFIED_NUMERAL_PENALTY = 3500
UNK_LID = 1  # その他,間投
UNK_COST = 12000
MAX_WORD_MORA = 16
POS_KEEP = 12  # surviving (rid, score) per token position

NumeralPos = tuple[Literal["digit", "day", "month", "after_month", "operator",
                          "after_operator"], int]


@dataclass(slots=True)
class Entry:
    surface: str
    reading: str
    lid: int
    rid: int
    cost: int


@dataclass
class MozcLex:
    by_reading: dict[str, list[Entry]]
    prefixes: set[str]
    connect: array  # int16
    pos_size: int
    numeral_pos: tuple[NumeralPos, ...] = ()  # IDs after the raw Mozc matrix

    def base_pos(self, pos: int) -> int:
        return self.numeral_pos[pos - self.pos_size][1] if pos >= self.pos_size else pos

    def transition(self, rid: int, lid: int) -> int:
        size = self.pos_size
        if rid < size and lid < size:
            return self.connect[rid * size + lid]
        prev_kind, rid = self.numeral_pos[rid - size] if rid >= size else (None, rid)
        next_kind, lid = self.numeral_pos[lid - size] if lid >= size else (None, lid)
        cost = self.connect[rid * size + lid]
        if (prev_kind == "digit" and next_kind != "operator" and lid not in COUNTER_IDS
                and lid not in NUMBER_UNIT_IDS and lid not in RANGE_PARTICLE_IDS):
            cost += UNQUALIFIED_NUMERAL_PENALTY if lid == BOS_ID else DIGIT_PENALTY
        if prev_kind == "day" and lid not in PARTICLE_IDS:
            cost += UNQUALIFIED_NUMERAL_PENALTY
        # The alternate arcs have the same word cost and bypass the outgoing
        # penalty in these contexts. Otherwise the regular arc stays cheaper.
        if next_kind == "after_month" and prev_kind != "month" and rid != MONTH_COUNTER_ID:
            cost += UNQUALIFIED_NUMERAL_PENALTY + 1
        if next_kind == "after_operator" and prev_kind != "operator":
            cost += UNQUALIFIED_NUMERAL_PENALTY + 1
        return cost


def left_id_after(literal: str, lex: MozcLex | None) -> int:
    """POS context for a kana run after a literal: a digit reads as a numeral.

    Any other literal (punctuation, Latin) is a sentence boundary.
    Small test lexicons have no Mozc numeral POS and keep the boundary.
    """
    digit = literal and ("0" <= literal[-1] <= "9" or "０" <= literal[-1] <= "９")
    return NUMBER_ID if digit and lex is not None and NUMBER_ID < lex.pos_size else BOS_ID


# What load_lex parses to build the cache. A missing one must stop the build:
# skipping it would pickle an incomplete lexicon that is then trusted as is.
LOADER_FILES = ([f"dictionary{i:02d}.txt" for i in range(10)]
                + ["suffix.txt", "connection_single_column.txt"])
FETCH_HINT = "Run: python -m tools.eval.fetch_mozc_dict"


def require_dict_files(names: list[str], directory: Path | None = None) -> None:
    """Raise FileNotFoundError naming every missing file and how to fetch it."""
    directory = DICT_DIR if directory is None else directory
    missing = [name for name in names if not (directory / name).exists()]
    if missing:
        raise FileNotFoundError(
            f"Mozc dict files missing in {directory}: {', '.join(missing)}. {FETCH_HINT}")


def _parse_dict_files() -> tuple[dict[str, list[Entry]], set[str]]:
    by_reading: dict[str, list[Entry]] = {}
    prefixes: set[str] = set()
    # A glob's order is up to the OS: the same reading and cost would come out in another order.
    files = sorted(DICT_DIR.glob("dictionary*.txt")) + [DICT_DIR / "suffix.txt"]
    for path in files:
        with path.open(encoding="utf-8") as f:
            for number, line in enumerate(f, 1):
                line = line.rstrip("\n")
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                try:
                    reading, lid_s, rid_s, cost_s, surface = parts[:5]
                    lid, rid, cost = int(lid_s), int(rid_s), int(cost_s)
                except ValueError:  # fewer than five columns, or not numbers
                    raise DictionaryFormatError(f"{path.name}:{number}: not a dictionary "
                                                "line") from None
                if not reading or not surface:
                    raise DictionaryFormatError(f"{path.name}:{number}: empty reading "
                                                "or surface")
                e = Entry(surface, reading, lid, rid, cost)
                bucket = by_reading.setdefault(reading, [])
                bucket.append(e)
                for i in range(1, len(reading) + 1):
                    prefixes.add(reading[:i])
    # Candidate enumeration needs every homonym, including POS variants.
    for bucket in by_reading.values():
        bucket.sort(key=lambda e: e.cost)
    return by_reading, prefixes


def _parse_connection() -> tuple[array, int]:
    path = DICT_DIR / "connection_single_column.txt"
    with path.open(encoding="utf-8") as f:
        try:
            pos_size = int(f.readline().strip())
            vals = array("h", map(int, f))
        except ValueError:
            raise DictionaryFormatError(f"{path.name}: not a number") from None
    expected = pos_size * pos_size
    if len(vals) != expected:
        raise DictionaryFormatError(f"connection size {len(vals)} != {pos_size}^2")
    return vals, pos_size


def apply_user_lex(lex: MozcLex, path: Path | None = None) -> int:
    """Overlay the bundled corrections from data/user_lexicon.jsonl in memory.

    A spelling already in the dictionary only gets the lower cost: the row's
    lid/rid are not read. The file is part of the program, so a broken row
    stops loading like a broken dictionary line (DESIGN「起動時の読み込み」).
    """
    p = path or USER_LEX
    if not p.exists():
        return 0
    n = 0
    for line_no, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            row = json.loads(line)
            reading = row["reading"]
            surface = row["surface"]
            cost = int(row["cost"])
            lid = int(row.get("lid", DEFAULT_NOUN_ID))
            rid = int(row.get("rid", lid))
        except (ValueError, KeyError, TypeError):
            raise DictionaryFormatError(f"{p.name}:{line_no}: not a user lexicon row") from None
        bucket = lex.by_reading.setdefault(reading, [])
        replaced = False
        for e in bucket:
            if e.surface == surface:
                e.cost = min(e.cost, cost)
                replaced = True
                break
        if not replaced:
            bucket.append(Entry(surface, reading, lid, rid, cost))
        bucket.sort(key=lambda e: e.cost)
        for i in range(1, len(reading) + 1):
            lex.prefixes.add(reading[:i])
        n += 1
    return n


NUMERAL_MAX = 9999
NUMERAL_COST = 1500  # two digits; near a single kana digit (753-2181), under the 4-5k of a 重/中 counter reading
NUMERAL_COST_PER_DIGIT = 1000  # each digit more: long numbers are rarer than words like 戦後
_ONES = ["", "いち", "に", "さん", "よん", "ご", "ろく", "なな", "はち", "きゅう"]
_TENS = ["", "じゅう", "にじゅう", "さんじゅう", "よんじゅう", "ごじゅう", "ろくじゅう",
         "ななじゅう", "はちじゅう", "きゅうじゅう"]
_HUNDREDS = ["", "ひゃく", "にひゃく", "さんびゃく", "よんひゃく", "ごひゃく", "ろっぴゃく",
             "ななひゃく", "はっぴゃく", "きゅうひゃく"]
_THOUSANDS = ["", "せん", "にせん", "さんぜん", "よんせん", "ごせん", "ろくせん",
              "ななせん", "はっせん", "きゅうせん"]
_DAY = re.compile(r"[1-9一二三四五六七八九]日")
_MONTH = re.compile(r"(?:[1-9]|1[0-2]|[一二三四五六七八九]|十[一二]?)月")


def apply_numeral_context(lex: MozcLex) -> None:
    """Use Mozc's connections, with a penalty for ambiguous digits and days.

    Use the original cost when adjacent words indicate a number or date.
    Assign private IDs only to the connection sides that need the distinction.
    """
    left: list[tuple[Entry, NumeralPos]] = []
    right: list[tuple[Entry, NumeralPos]] = []
    for bucket in lex.by_reading.values():
        alternatives = []
        for entry in bucket:
            surface = entry.surface
            if entry.rid == NUMBER_ID and len(surface) == 1 and "0" <= surface <= "9":
                right.append((entry, ("digit", entry.rid)))
                alternate = replace(entry)
                left.append((alternate, ("after_operator", entry.lid)))
                alternatives.append(alternate)
            elif surface.endswith("日") and _DAY.fullmatch(surface):
                right.append((entry, ("day", entry.rid)))
                alternate = replace(entry)
                left.append((alternate, ("after_month", entry.lid)))
                alternatives.append(alternate)
            elif surface.endswith("月") and _MONTH.fullmatch(surface):
                right.append((entry, ("month", entry.rid)))
            elif surface in ARITHMETIC_OPERATORS:
                left.append((entry, ("operator", entry.lid)))
                right.append((entry, ("operator", entry.rid)))
        bucket.extend(alternatives)

    lex.numeral_pos = tuple(sorted({pos for _, pos in left + right}))
    ids = {pos: i for i, pos in enumerate(lex.numeral_pos, lex.pos_size)}
    for entry, pos in left:
        entry.lid = ids[pos]
    for entry, pos in right:
        entry.rid = ids[pos]


def numeral_reading(n: int) -> str:
    """The kana reading of 1..9999 (4 as よん, 7 as なな, 9 as きゅう; 1 is not dropped before 十)."""
    t, rest = divmod(n, 1000)
    h, rest = divmod(rest, 100)
    d, o = divmod(rest, 10)
    return _THOUSANDS[t] + _HUNDREDS[h] + _TENS[d] + _ONES[o]


def apply_numerals(lex: MozcLex) -> None:
    """Add 10..9999 as Arabic numerals read as a whole.

    The Mozc dictionary has only the single digits as Arabic numerals, and a
    digit cannot follow a digit (13820), so じゅうさん could never be 13:
    the lattice took a counter reading (さんじゅう as 3+重, じゅうご as 中5)
    instead. Like a numeral POS word, the new entries connect as 数 (NUMBER_ID).
    """
    for n in range(10, NUMERAL_MAX + 1):
        reading = numeral_reading(n)
        bucket = lex.by_reading.setdefault(reading, [])
        bucket.append(Entry(str(n), reading, NUMBER_ID, NUMBER_ID,
                            NUMERAL_COST + NUMERAL_COST_PER_DIGIT * (len(str(n)) - 2)))
        bucket.sort(key=lambda e: e.cost)
        for i in range(1, len(reading) + 1):
            lex.prefixes.add(reading[:i])


def load_cache(cache: Path, *, allow_legacy: bool = False) -> MozcLex:
    """Read a trusted dictionary cache, raising if it cannot be decoded."""
    with cache.open("rb") as f:
        data = pickle.load(f)
    if allow_legacy and isinstance(data, MozcLex):
        return data
    readings, counts, surfaces, lids, rids, costs, extra_prefixes, connect, pos_size = data
    if (not isinstance(connect, array) or connect.typecode != "h"
            or pos_size <= 0 or len(connect) != pos_size * pos_size):
        raise ValueError("dictionary cache has an invalid connection matrix")
    numbers: dict[int, int] = {}
    rows = zip(surfaces, lids, rids, costs, strict=True)
    by_reading: dict[str, list[Entry]] = {}
    for reading, count in zip(readings, counts, strict=True):
        bucket = []
        for _ in range(count):
            surface, lid, rid, cost = next(rows)
            bucket.append(Entry(surface, reading, numbers.setdefault(lid, lid),
                                numbers.setdefault(rid, rid), numbers.setdefault(cost, cost)))
        by_reading[reading] = bucket
    if next(rows, None) is not None:
        raise ValueError("dictionary cache has extra entries")
    prefixes = set(extra_prefixes)
    prefixes.update(by_reading)
    return MozcLex(by_reading, prefixes, connect, pos_size)


def read_cache(cache: Path) -> MozcLex | None:
    """The cached lexicon; None when there is none or it cannot be read.

    Whatever is wrong with the file (written halfway, empty, from another
    format), the answer is the same: build it again from the text (DESIGN「起動時の読み込み」).
    """
    try:
        return load_cache(cache)
    except FileNotFoundError:
        return None
    except Exception as exc:  # any decoding failure: the cache is rebuilt
        print(f"dictionary cache unreadable ({type(exc).__name__}); rebuilding",
              file=sys.stderr, flush=True)
        return None


def write_cache(cache: Path, lex: MozcLex) -> None:
    """Write the raw dictionary in columns, then atomically replace the cache."""
    readings = list(lex.by_reading)
    counts = array("I")
    surfaces = []
    lids, rids, costs = array("H"), array("H"), array("i")
    for bucket in lex.by_reading.values():
        counts.append(len(bucket))
        for entry in bucket:
            surfaces.append(entry.surface)
            lids.append(entry.lid)
            rids.append(entry.rid)
            costs.append(entry.cost)
    extra_prefixes = [p for p in lex.prefixes if p not in lex.by_reading]
    tmp = None
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(dir=cache.parent, prefix=f"{cache.name}.", suffix=".tmp",
                                delete=False) as f:
            tmp = Path(f.name)
            pickle.dump((readings, counts, surfaces, lids, rids, costs, extra_prefixes,
                         lex.connect, lex.pos_size), f, protocol=5)
        os.replace(tmp, cache)
        tmp = None
    except OSError as exc:
        raise CacheWriteError(exc.errno, f"cannot write the dictionary cache {cache}: "
                                         f"{exc.strerror}") from exc
    finally:
        if tmp is not None:
            with suppress(OSError):
                tmp.unlink(missing_ok=True)


def load_lex(*, user_lexicon: bool = True) -> MozcLex:
    """The lexicon from the cache, or parsed from the text and cached."""
    cache = CACHE_DIR / cache_name()
    lex = read_cache(cache)
    if lex is None:
        require_dict_files(LOADER_FILES)
        print("parsing Mozc OSS dictionary (first run)...", file=sys.stderr, flush=True)
        by_reading, prefixes = _parse_dict_files()
        connect, pos_size = _parse_connection()
        lex = MozcLex(by_reading, prefixes, connect, pos_size)
        write_cache(cache, lex)
        print(
            f"  readings={len(by_reading)} prefixes={len(prefixes)} "
            f"pos={pos_size} cache={cache}",
            file=sys.stderr,
        )
    finish_lex(lex, USER_LEX if user_lexicon else None)
    return lex


def finish_lex(lex: MozcLex, user: Path | None) -> None:
    """What every reader applies to the raw (cached) dictionary, in memory.

    Numerals, the user lexicon `user` (None: without it) and the zero-row
    penalty. load_lex and the evaluation tools both use this one function.
    """
    apply_numeral_context(lex)
    apply_numerals(lex)
    n = apply_user_lex(lex, user) if user is not None else 0
    if n:
        print(f"  user lexicon: {n} entries from {user.name}", file=sys.stderr)
    # Apply only after saving/loading the raw cache. Include column 0 (EOS),
    # so a zero-row entry pays the same penalty even at the end of input.
    penalty = int(os.environ.get("ZERO_ROW_PENALTY", "3000"))
    if penalty:
        for start in range(0, len(lex.connect), lex.pos_size):
            end = start + lex.pos_size
            if not any(lex.connect[start:end]):
                lex.connect[start:end] = array("h", [penalty]) * lex.pos_size
