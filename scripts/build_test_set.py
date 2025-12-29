from __future__ import annotations

"""
Builds a test set with permutations of ISBN/metadata/image presence.
Copies (not moves) matched EPUB files into a structured destination folder.
"""
import sys

import os
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Tuple

from bs4 import BeautifulSoup
import ebooklib
from ebooklib import epub

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import settings
from src.tasks import extract

ITEMS_PERMUTATION = 3
ISBN_SCAN_DOCS = 2
MAX_WORKERS = max(12, (os.cpu_count() or 12))


def _purge_directory(path: Path) -> None:
    if not path.exists():
        return
    for entry in path.iterdir():
        if entry.is_dir():
            shutil.rmtree(entry)
        else:
            entry.unlink()


def _iter_epub_files(base_dir: Path) -> List[Path]:
    files: List[Path] = []
    for dirpath, _, filenames in os.walk(base_dir):
        for filename in filenames:
            if filename.lower().endswith(".epub"):
                files.append(Path(dirpath) / filename)
    return files


def _has_metadata(metadata_payload: Dict[str, object]) -> bool:
    if not metadata_payload:
        return False
    for value in metadata_payload.values():
        if value is None:
            continue
        if isinstance(value, str) and value.strip():
            return True
        if isinstance(value, list) and value:
            return True
        if not isinstance(value, (str, list)):
            return True
    return False


def _isbn_bucket(isbn_count: int) -> str:
    if isbn_count <= 0:
        return "none"
    if isbn_count == 1:
        return "single"
    return "multiple"


def _combo_key(isbn_bucket: str, has_metadata: bool, has_image: bool) -> str:
    return f"isbn-{isbn_bucket}_metadata-{'yes' if has_metadata else 'no'}_image-{'yes' if has_image else 'no'}"


def _has_image_items(book: epub.EpubBook) -> bool:
    for item in book.get_items_of_type(ebooklib.ITEM_IMAGE):
        filename = getattr(item, "file_name", "") or ""
        media_type = getattr(item, "media_type", "") or ""
        if "svg" in media_type.lower():
            continue
        if filename.lower().endswith(".svg"):
            continue
        return True
    return False


def _extract_isbns_fast(book: epub.EpubBook, file_path: Path) -> List[str]:
    try:
        identifiers = book.get_metadata("DC", "identifier")
        for identifier, _ in identifiers:
            if not identifier:
                continue
            if "isbn" in identifier.lower() or extract._is_valid_isbn(identifier):
                clean_isbn = extract._normalize_isbn(identifier.replace("urn:isbn:", "").strip())
                if extract._is_valid_isbn(clean_isbn):
                    return [clean_isbn]

        found: List[str] = []
        items_to_scan = list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))[:ISBN_SCAN_DOCS]
        for item in items_to_scan:
            content = item.get_content()
            soup = BeautifulSoup(content, "html.parser")
            found.extend(extract._find_isbns_in_text(soup.get_text()))
        return list(dict.fromkeys(found))
    except Exception as exc:
        print(f"ISBN scan failed for {file_path.name}: {exc}")
        return []


def build_test_set() -> None:
    source_dir = settings.epub_dir
    target_dir = settings.test_samples_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    _purge_directory(target_dir)

    combos = [
        (isbn_bucket, has_metadata, has_image)
        for isbn_bucket in ("none", "single", "multiple")
        for has_metadata in (False, True)
        for has_image in (False, True)
    ]
    combo_order = sorted(
        combos,
        key=lambda combo: (("none", "single", "multiple").index(combo[0]), combo[1], combo[2]),
    )
    quota = {combo: ITEMS_PERMUTATION for combo in combos}
    selected: Dict[Tuple[str, bool, bool], List[Path]] = {combo: [] for combo in combos}
    pending: Dict[Tuple[str, bool, bool], List[Path]] = {combo: [] for combo in combos}

    total_needed = len(combos) * ITEMS_PERMUTATION
    filled_total = 0
    total_files = 0

    logs_dir = PROJECT_ROOT / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    report_path = logs_dir / "test_set_report.md"
    with report_path.open("w", encoding="utf-8") as handle:
        handle.write("| book | permutation |\n")
        handle.write("| --- | --- |\n")

    lock = threading.Lock()
    stop_event = threading.Event()

    def _current_target_combo() -> Tuple[str, bool, bool] | None:
        for combo in combo_order:
            if len(selected[combo]) < quota[combo]:
                return combo
        return None

    def _process_file(file_path: Path) -> Tuple[Tuple[str, bool, bool] | None, Path | None]:
        if stop_event.is_set():
            return None, None
        try:
            book = epub.read_epub(file_path)
        except Exception:
            return None, None

        isbns = _extract_isbns_fast(book, file_path)
        isbn_count = len(isbns)
        isbn_bucket = _isbn_bucket(isbn_count)

        metadata_result = extract.extract_epub_metadata(book, file_path)
        metadata_payload = {}
        if metadata_result.metadata is not None:
            metadata_payload = metadata_result.metadata.model_dump()
        has_metadata = _has_metadata(metadata_payload)

        has_image = _has_image_items(book)
        return (isbn_bucket, has_metadata, has_image), file_path

    futures = []
    files = _iter_epub_files(source_dir)
    total_files = len(files)
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for file_path in files:
            if stop_event.is_set():
                break
            futures.append(executor.submit(_process_file, file_path))

        processed = 0
        for future in as_completed(futures):
            combo, file_path = future.result()
            processed += 1
            if file_path is not None:
                print(f"Processed {processed}/{total_files}: {file_path.name}")
            if combo is None or file_path is None:
                continue
            with lock:
                pending[combo].append(file_path)
                for ordered_combo in combo_order:
                    if len(selected[ordered_combo]) >= quota[ordered_combo]:
                        continue
                    if not pending[ordered_combo]:
                        continue
                    chosen = pending[ordered_combo].pop(0)
                    selected[ordered_combo].append(chosen)
                    filled_total += 1
                    print(f"Selected {filled_total}/{total_needed}: {chosen.name}")
                    folder_name = _combo_key(*ordered_combo)
                    combo_dir = target_dir / folder_name
                    combo_dir.mkdir(parents=True, exist_ok=True)
                    destination = combo_dir / chosen.name
                    shutil.copy2(chosen, destination)
                    with report_path.open("a", encoding="utf-8") as handle:
                        handle.write(f"| {chosen.name} | {folder_name} |\n")
                    if all(len(selected[c]) >= quota[c] for c in combos):
                        print("All permutations filled. Stopping early.")
                        stop_event.set()
                        break

    filled = sum(1 for combo in combos if len(selected[combo]) >= quota[combo])
    total_permutations = len(combos)
    print(f"Test set complete: {filled}/{total_permutations} permutations filled.")


if __name__ == "__main__":
    build_test_set()
