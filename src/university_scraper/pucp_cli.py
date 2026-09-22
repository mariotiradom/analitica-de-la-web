from __future__ import annotations

import argparse
from pathlib import Path

from .pucp import CATALOG_URL, PucpCurriculumDownloader


def main() -> None:
    parser = argparse.ArgumentParser(description="Descarga mallas de pregrado de la PUCP por facultad")
    parser.add_argument(
        "--faculty",
        default="arquitectura",
        help="Facultad a descargar (por defecto: arquitectura)",
    )
    parser.add_argument("--catalog-url", default=CATALOG_URL, help="URL del catalogo de carreras por facultad")
    parser.add_argument("--output-dir", type=Path, default=Path("data/pucp"), help="Directorio de salida")
    parser.add_argument("--skip-pdf", action="store_true", help="Omitir la descarga del PDF oficial")
    parser.add_argument("--dry-run", action="store_true", help="Comprueba las URLs del catalogo sin descargar mallas")
    args = parser.parse_args()

    downloader = PucpCurriculumDownloader(args.output_dir)
    try:
        if args.dry_run:
            print(f"Catalogo: {args.catalog_url}")
            _, careers = downloader.download_catalog(args.catalog_url)
            print(f"Carreras descubiertas en el catalogo: {len(careers)}")
            for career in careers:
                print(f"  [{career.faculty}] {career.name} -> {career.plan_url}")
            return

        print(f"Descargando catalogo general y procesando facultad: '{args.faculty}'...")
        metadata = downloader.download_faculty(args.faculty, download_pdf=not args.skip_pdf)
        if "careers" in metadata:
            print(f"Descarga completada para: {metadata['faculty']} ({metadata['career_count']} carreras)")
            for item in metadata["careers"]:
                url_display = item.get("plan_url") or item.get("fci_pdf_url") or ""
                if "specializations" in item:
                    print(f"  - {item['name']}: {len(item['specializations'])} menciones ({item.get('pdf_count', 0)} PDFs)")
                elif "course_count" in item:
                    print(f"  - {item['name']}: {item['course_count']} cursos ({url_display})")
                else:
                    pdf_info = f"PDF oficial ({item.get('pdf_size_bytes', 0)} bytes)" if item.get("pdf_url") else "Sin PDF"
                    print(f"  - {item['name']}: {pdf_info} ({url_display})")
        else:
            print(f"Descarga completada para: {metadata['career']} ({metadata['faculty']})")
            print(f"Cursos extraidos: {metadata['course_count']}")
            print(f"Etapas: {metadata.get('stages')}")
            if "pdf" in metadata.get("files", {}):
                print(f"PDF descargado: {metadata['files']['pdf']} ({metadata.get('pdf_size_bytes', 0)} bytes)")
        print(f"Archivos guardados en: {args.output_dir}")
    finally:
        downloader.close()


if __name__ == "__main__":
    main()

