from __future__ import annotations

import argparse
from pathlib import Path

from .up import CATALOG_URL, PAGE_URL, PDF_URL, UpStudyPlanDownloader


def main() -> None:
    parser = argparse.ArgumentParser(description="Descarga mallas de pregrado de la Universidad del Pacifico")
    parser.add_argument("--all", action="store_true", help="Descubre y descarga todas las carreras del catalogo")
    parser.add_argument("--catalog-url", default=CATALOG_URL, help="URL del catalogo de carreras")
    parser.add_argument("--url", default=PAGE_URL, help="URL de la pagina del plan")
    parser.add_argument("--pdf-url", default=PDF_URL, help="URL del PDF oficial")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true", help="Verifica robots.txt sin descargar")
    args = parser.parse_args()

    output_dir = args.output_dir or (Path("data/up") if args.all else Path("data/up/ingenieria-de-la-informacion"))
    downloader = UpStudyPlanDownloader(output_dir)
    try:
        urls = (("catalogo", args.catalog_url),) if args.all else (("pagina", args.url), ("pdf", args.pdf_url))
        for label, url in urls:
            print(f"{label}: {url} | permitido={downloader.allowed(url)}")
        if args.dry_run:
            return
        if args.all:
            metadata = downloader.download_all(args.catalog_url)
            print(f"Carreras descubiertas: {metadata['career_count']}")
        else:
            metadata = downloader.download(args.url, args.pdf_url)
            print(f"Descarga completada: {metadata['course_count']} cursos HTML")
        print(f"Archivos: {output_dir}")
    finally:
        downloader.close()


if __name__ == "__main__":
    main()
