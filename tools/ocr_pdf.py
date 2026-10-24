"""Text from official PDFs, OCR-ing scanned ones.

    py tools/ocr_pdf.py file1.pdf [file2.pdf ...]
    py tools/ocr_pdf.py --ocr --pages 3406-3413 --out ee.txt guide.pdf

For each PDF, writes <name>.txt next to it: the embedded text layer when it has
one (pdftotext), otherwise Tesseract OCR of 300-dpi page renders. Many county
measure documents (impartial analyses, arguments) are posted as scans.

--pages renders only that page range; --ocr skips the text layer (some county
guides embed fonts with a broken text mapping, e.g. Alameda's, where letters come
out shifted and word spaces vanish); --out names the output file (same folder).

Tesseract runs locally when installed; otherwise inside a throwaway container
from the congress_trader backend image (which ships tesseract + pdftoppm), with
the PDF's folder mounted read-write. Nothing is sent anywhere.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

IMAGE = "congress_trader-backend:latest"
MIN_TEXT = 200   # fewer characters than this in the text layer means it's a scan

# $1 dir, $2 pdf name, $3 output name, $4 optional "-f N -l M" page range.
OCR_SCRIPT = r'''set -e
cd "$1"; f="$2"; out="$3"; range="$4"; tmp=".ocr_$f"
rm -rf "$tmp"; mkdir "$tmp"
pdftoppm -r 300 -gray $range -png "$f" "$tmp/p"
for p in $(ls "$tmp"/p*.png | sort -V); do tesseract "$p" - --psm 4 2>/dev/null; printf '\f'; done > "$out"
rm -rf "$tmp"
'''


def text_layer(pdf: Path) -> str:
    try:
        return subprocess.run(["pdftotext", "-enc", "UTF-8", "-layout", str(pdf), "-"],
                              capture_output=True, check=True).stdout.decode("utf-8")
    except (OSError, subprocess.CalledProcessError):
        return ""


def ocr(pdf: Path, out: Path, pages: str | None = None) -> None:
    rng = ""
    if pages:
        first, _, last = pages.partition("-")
        rng = f"-f {int(first)} -l {int(last or first)}"
    args = [pdf.name, out.name, rng]
    if shutil.which("tesseract") and shutil.which("pdftoppm"):
        subprocess.run(["sh", "-c", OCR_SCRIPT, "sh", str(pdf.parent), *args], check=True)
        return
    vol = str(pdf.parent.resolve()).replace("\\", "/")
    subprocess.run(["docker", "run", "--rm", "--entrypoint", "sh", "-v", f"{vol}:/w", IMAGE,
                    "-c", OCR_SCRIPT, "sh", "/w", *args],
                   check=True, env={**os.environ, "MSYS_NO_PATHCONV": "1"})


def main(argv: list[str]) -> None:
    force, pages, out, paths = False, None, None, []
    it = iter(argv)
    for a in it:
        if a == "--ocr":
            force = True
        elif a == "--pages":
            pages = next(it)
        elif a == "--out":
            out = next(it)
        else:
            paths.append(a)
    if out and len(paths) != 1:
        sys.exit("--out takes exactly one PDF")
    for p in map(Path, paths):
        txt = p.parent / out if out else p.with_suffix(".txt")
        layer = "" if (force or pages) else text_layer(p)
        if len(layer.strip()) >= MIN_TEXT:
            txt.write_text(layer, encoding="utf-8")
            how = "text layer"
        else:
            ocr(p, txt, pages)
            how = "OCR" + (f" pages {pages}" if pages else "")
        print(f"{p.name}: {how} -> {txt.name}, {len(txt.read_text(encoding='utf-8', errors='replace'))} chars")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1:])
