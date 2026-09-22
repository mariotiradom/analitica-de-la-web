from __future__ import annotations

import argparse
from pathlib import Path

from .utec import PAGE_URL, UtecCurriculumDownloader


def main() -> None:
    parser = argparse.ArgumentParser(description="Descarga la malla curricular publica de UTEC")
    parser.add_argument("--url", default=PAGE_URL, help="URL de la carrera")
    parser.add_argument("--output-dir", type=Path, default=Path("data/utec/ciencia-de-datos"))
    parser.add_argument("--dry-run", action="store_true", help="Verifica robots.txt sin descargar")
    args = parser.parse_args()

    downloader = UtecCurriculumDownloader(args.output_dir)
    try:
        image_url = "https://utec.edu.pe/sites/default/files/2024-07/image%20%2815%29.png"
        urls = [args.url, image_url]
        for url in urls:
            print(f"{url} | permitido={downloader.allowed(url)}")
        if args.dry_run:
            return
        metadata = downloader.download(args.url)
        print(f"Descarga completada: {metadata['course_count']} cursos")
        print(f"Archivos: {args.output_dir}")
    finally:
        downloader.close()


if __name__ == "__main__":
    main()
