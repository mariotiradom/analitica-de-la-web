from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup


CATALOG_URL = "https://www.ulima.edu.pe/pregrado"

CAREER_NAMES = {
    "administracion": "Administración",
    "arquitectura": "Arquitectura",
    "comunicacion": "Comunicación",
    "contabilidad_y_finanzas": "Contabilidad y Finanzas",
    "derecho": "Derecho",
    "economia": "Economía",
    "ing_ambiental": "Ingeniería Ambiental",
    "ing_civil": "Ingeniería Civil",
    "ing_industrial": "Ingeniería Industrial",
    "ing_sistemas": "Ingeniería de Sistemas",
    "ing_mecatronica": "Ingeniería Mecatrónica",
    "marketing": "Marketing",
    "negocios_int": "Negocios Internacionales",
    "psicologia": "Psicología",
}


@dataclass(slots=True)
class UlimaCareer:
    name: str
    pdf_url: str


class UlimaCurriculumDownloader:
    def __init__(self, output_dir: Path, timeout: float = 30.0) -> None:
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
            },
        )

    def close(self) -> None:
        self.client.close()

    def download_all(self, catalog_url: str = CATALOG_URL) -> dict[str, object]:
        response = self.client.get(catalog_url)
        response.raise_for_status()
        careers = extract_careers(response.text, catalog_url)
        catalog_file = self.output_dir / "source.html"
        catalog_file.write_bytes(response.content)

        downloaded: list[dict[str, object]] = []
        for career in careers:
            pdf_response = self.client.get(career.pdf_url)
            pdf_response.raise_for_status()
            career_dir = self.output_dir / slugify(career.name)
            career_dir.mkdir(parents=True, exist_ok=True)
            pdf_file = career_dir / "malla.pdf"
            metadata_file = career_dir / "metadata.json"
            pdf_file.write_bytes(pdf_response.content)
            metadata = {
                "source": "universidad_de_lima",
                "career": career.name,
                "catalog_url": catalog_url,
                "pdf_url": career.pdf_url,
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "files": {"pdf": str(pdf_file)},
                "content_type": pdf_response.headers.get("content-type"),
                "size_bytes": len(pdf_response.content),
            }
            metadata_file.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
            downloaded.append({"name": career.name, "pdf_url": career.pdf_url, "size_bytes": len(pdf_response.content)})

        metadata = {
            "source": "universidad_de_lima",
            "catalog_url": catalog_url,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "career_count": len(careers),
            "careers": downloaded,
            "files": {"catalog_html": str(catalog_file)},
        }
        (self.output_dir / "metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return metadata


def extract_careers(html: str, base_url: str = CATALOG_URL) -> list[UlimaCareer]:
    soup = BeautifulSoup(html, "html.parser")
    careers: list[UlimaCareer] = []
    seen_urls: set[str] = set()
    for link in soup.find_all("a", href=True):
        label = _clean(link.get_text(" ", strip=True))
        if "malla" not in label.lower():
            continue
        pdf_url = urljoin(base_url, link["href"])
        if pdf_url in seen_urls or not pdf_url.lower().split("?", 1)[0].endswith(".pdf"):
            continue
        name = _career_name(link)
        if name:
            careers.append(UlimaCareer(name=name, pdf_url=pdf_url))
            seen_urls.add(pdf_url)
    return careers


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.lower()).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")


def _career_name(link: object) -> str:
    pdf_stem = Path(urlparse(link.get("href", "")).path).stem
    if pdf_stem.startswith("malla_"):
        career_key = re.sub(r"_20\d{2}(?:[_-].*)?$", "", pdf_stem.removeprefix("malla_"))
        if career_key in CAREER_NAMES:
            return CAREER_NAMES[career_key]
    for ancestor in getattr(link, "parents", []):
        if "ulima-simple-info-content" in (ancestor.get("class") or []):
            heading = ancestor.select_one("h3.ulima-tabs-info--title")
            if heading is not None:
                return _clean(heading.get_text(" ", strip=True))
        heading = ancestor.find(["h2", "h3", "h4"], recursive=True)
        if heading is not None:
            name = _clean(heading.get_text(" ", strip=True))
            if name and "malla" not in name.lower():
                return name
        text = _clean(ancestor.get_text(" ", strip=True))
        if len(text) < 180:
            candidate = re.sub(r"\s*(?:descargar\s+)?malla\s*$", "", text, flags=re.IGNORECASE).strip()
            if candidate and "malla" not in candidate.lower():
                return candidate
    return ""


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()