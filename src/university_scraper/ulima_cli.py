from __future__ import annotations

import argparse
from pathlib import Path

from .ulima import CATALOG_URL, UlimaCurriculumDownloader


def main() -> None:
    parser = argparse.ArgumentParser(description="Descarga mallas PDF de pregrado de la Universidad de Lima")
    parser.add_argument("--catalog-url", default=CATALOG_URL)
    parser.add_argument("--output-dir", type=Path, default=Path("data/ulima"))
    args = parser.parse_args()

    downloader = UlimaCurriculumDownloader(args.output_dir)
    try:
        metadata = downloader.download_all(args.catalog_url)
        print(f"Carreras descubiertas: {metadata['career_count']}")
        print(f"Archivos: {args.output_dir}")
    finally:
        downloader.close()


if __name__ == "__main__":
    main()