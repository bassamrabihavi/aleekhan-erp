"""Server-side content checks of the upload allow-list (DEC-053 APPROVED, SEC-03).

The declared extension selects an ``UploadType`` row (allow-list: pdf, png, jpg/jpeg, dxf, xlsx); its
``content_check`` names the check below. A file whose bytes do not match its type, an OOXML workbook that
carries macros (``vbaProject.bin`` / macro-enabled content type) or a container that looks like a parser bomb
is refused with 415 ``FILE_TYPE_NOT_ALLOWED`` before anything is stored. Nothing is ever executed, rendered or
extracted: the zip check reads the central directory and at most :data:`MAX_CONTENT_TYPES_BYTES` of
``[Content_Types].xml``.
"""

from __future__ import annotations

import io
import os
import unicodedata
import zipfile
from typing import Final

from platform_core.engine.errors import FieldError, FileTypeNotAllowed

PNG_MAGIC: Final = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC: Final = b"\xff\xd8\xff"
PDF_MAGIC: Final = b"%PDF-"
ZIP_MAGIC: Final = b"PK\x03\x04"
DXF_BINARY_MAGIC: Final = b"AutoCAD Binary DXF\r\n\x1a\x00"
# zip-bomb / parser-bomb guards (TECHNICAL limits, not business rules)
MAX_ZIP_MEMBERS: Final = 10_000
MAX_ZIP_RATIO: Final = 200  # total uncompressed / compressed
MAX_ZIP_UNCOMPRESSED: Final = 512 * 1024 * 1024
MAX_CONTENT_TYPES_BYTES: Final = 1024 * 1024
MACRO_MEMBER_NAMES: Final = ("vbaproject.bin", "vbadata.xml", "vbaprojectsignature.bin")


def _refuse(code: str) -> FileTypeNotAllowed:
    return FileTypeNotAllowed(f"refused by content check {code}", errors=[FieldError("file", code)])


def sanitise_filename(name: str) -> str:
    """Basename only, no control characters, <= 255 characters (CHECK ck_document_revision_name_basename)."""
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    clean = "".join(ch for ch in base if unicodedata.category(ch)[0] != "C").strip().strip(".")
    if not clean:
        raise _refuse("FILENAME_INVALID")
    stem, ext = os.path.splitext(clean)
    if len(clean) > 255:
        clean = stem[: 255 - len(ext)] + ext
    return clean


def extension_of(name: str) -> str:
    _stem, ext = os.path.splitext(name)
    return ext[1:].lower()


def _check_pdf(data: bytes) -> None:
    if not data.startswith(PDF_MAGIC):
        raise _refuse("MAGIC_MISMATCH")


def _check_png(data: bytes) -> None:
    if not data.startswith(PNG_MAGIC):
        raise _refuse("MAGIC_MISMATCH")


def _check_jpeg(data: bytes) -> None:
    if not data.startswith(JPEG_MAGIC):
        raise _refuse("MAGIC_MISMATCH")


def _check_dxf(data: bytes) -> None:
    if data.startswith(DXF_BINARY_MAGIC):
        return
    head = data[:512].decode("latin-1")
    lines = [ln.strip() for ln in head.splitlines() if ln.strip()]
    if len(lines) < 2 or lines[0] != "0" or lines[1].upper() != "SECTION":
        raise _refuse("MAGIC_MISMATCH")
    if b"\x00" in data[:4096]:
        raise _refuse("MAGIC_MISMATCH")  # text DXF never contains NUL bytes


def _check_ooxml_no_macro(data: bytes) -> None:
    if not data.startswith(ZIP_MAGIC):
        raise _refuse("MAGIC_MISMATCH")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            infos = zf.infolist()
            if len(infos) > MAX_ZIP_MEMBERS:
                raise _refuse("CONTAINER_TOO_COMPLEX")
            total = sum(i.file_size for i in infos)
            packed = max(1, sum(i.compress_size for i in infos))
            if total > MAX_ZIP_UNCOMPRESSED or total / packed > MAX_ZIP_RATIO:
                raise _refuse("CONTAINER_TOO_COMPLEX")
            names = {i.filename.replace("\\", "/").lower() for i in infos}
            if any(n.rsplit("/", 1)[-1] in MACRO_MEMBER_NAMES for n in names):
                raise _refuse("MACRO_CONTENT")
            if "[content_types].xml" not in names or "xl/workbook.xml" not in names:
                raise _refuse("MAGIC_MISMATCH")
            ct_info = next(i for i in infos if i.filename.lower() == "[content_types].xml")
            if ct_info.file_size > MAX_CONTENT_TYPES_BYTES:
                raise _refuse("CONTAINER_TOO_COMPLEX")
            with zf.open(ct_info) as fh:
                content_types = fh.read(MAX_CONTENT_TYPES_BYTES + 1).decode("utf-8", "replace").lower()
    except FileTypeNotAllowed:
        raise
    except (zipfile.BadZipFile, ValueError, OSError, RuntimeError, NotImplementedError, EOFError):
        raise _refuse("MAGIC_MISMATCH") from None
    if "macroenabled" in content_types or "vbaproject" in content_types:
        raise _refuse("MACRO_CONTENT")


CHECKS: Final = {
    "PDF": _check_pdf,
    "PNG": _check_png,
    "JPEG": _check_jpeg,
    "DXF": _check_dxf,
    "OOXML_NO_MACRO": _check_ooxml_no_macro,
}


def check_content(content_check: str, data: bytes) -> None:
    check = CHECKS.get(content_check)
    if check is None:  # unknown check name: refuse (deny by default)
        raise _refuse("UNKNOWN_CONTENT_CHECK")
    if not data:
        raise _refuse("EMPTY_FILE")
    check(data)
