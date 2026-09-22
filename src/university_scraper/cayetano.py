from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup


CATALOG_URL = "https://cayetano.edu.pe/pregrado/carreras/"
CAREERS_PATH = "/pregrado/carreras/"


@dataclass(slots=True)
class CayetanoCourse:
    name: str
    cycle: str | None
    modality: str | None


@dataclass(slots=True)
class CayetanoCareer:
    name: str
    url: str


class CayetanoCurriculumDownloader:
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
        careers: list[CayetanoCareer] = []
        catalog_pages: list[str] = []
        page_number = 1
        while True:
            page_url = catalog_url if page_number == 1 else f"{catalog_url}?query-0-page={page_number}"
            response = self.client.get(page_url)
            response.raise_for_status()
            page_careers = extract_careers(response.text, page_url)
            if not page_careers:
                break
            catalog_pages.append(page_url)
            for career in page_careers:
                if all(existing.url != career.url for existing in careers):
                    careers.append(career)
            page_number += 1

        catalog_file = self.output_dir / "catalog.html"
        catalog_file.write_text(
            self.client.get(catalog_url).text, encoding="utf-8"
        )
        downloaded: list[dict[str, object]] = []
        for career in careers:
            page_response = self.client.get(career.url)
            page_response.raise_for_status()
            courses = extract_courses(page_response.text)
            brochure_url = extract_brochure_url(page_response.text, career.url)
            career_dir = self.output_dir / slugify(career.name)
            career_dir.mkdir(parents=True, exist_ok=True)
            page_file = career_dir / "source.html"
            courses_file = career_dir / "courses.json"
            metadata_file = career_dir / "metadata.json"
            page_file.write_bytes(page_response.content)
            courses_file.write_text(
                json.dumps([asdict(course) for course in courses], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            metadata = {
                "source": "universidad_peruana_cayetano_heredia",
                "career": career.name,
                "page_url": career.url,
                "brochure_url": brochure_url,
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "files": {"html": str(page_file), "courses": str(courses_file)},
                "course_count": len(courses),
            }
            metadata_file.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
            downloaded.append({"name": career.name, "url": career.url, "course_count": len(courses)})

        metadata = {
            "source": "universidad_peruana_cayetano_heredia",
            "catalog_url": catalog_url,
            "catalog_pages": catalog_pages,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "career_count": len(careers),
            "careers": downloaded,
        }
        (self.output_dir / "metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return metadata


def extract_careers(html: str, base_url: str = CATALOG_URL) -> list[CayetanoCareer]:
    soup = BeautifulSoup(html, "html.parser")
    careers: dict[str, CayetanoCareer] = {}
    for link in soup.find_all("a", href=True):
        url = _absolute_url(link["href"], base_url)
        parsed = urlparse(url)
        path = parsed.path.rstrip("/") + "/"
        relative = path[len(CAREERS_PATH):].strip("/") if path.startswith(CAREERS_PATH) else ""
        if not relative or "/" in relative or parsed.netloc != urlparse(CATALOG_URL).netloc:
            continue
        name = _clean(link.get_text(" ", strip=True))
        if name and name.lower() not in {"todas las carreras", "ver más"}:
            careers.setdefault(url, CayetanoCareer(name=name, url=url))
    return list(careers.values())


def extract_courses(html: str) -> list[CayetanoCourse]:
    soup = BeautifulSoup(html, "html.parser")
    section = soup.select_one("#malla-curricular")
    if section is None:
        return []
    courses: list[CayetanoCourse] = []
    for slide in section.select(".wp-block-getwid-content-slider-slide"):
        cycle_node = slide.select_one("p strong")
        cycle = f"Ciclo {_clean(cycle_node.get_text())}" if cycle_node else None
        for item in slide.select("ul > li"):
            text = _clean(item.get_text(" ", strip=True))
            modality_match = re.search(r"\((P|SP|NP)\)\s*$", text, re.IGNORECASE)
            modality = modality_match.group(1).upper() if modality_match else None
            name = re.sub(r"\s*\((?:P|SP|NP)\)\s*$", "", text, flags=re.IGNORECASE).strip()
            if name:
                courses.append(CayetanoCourse(name=name, cycle=cycle, modality=modality))
    return _deduplicate(courses)


def extract_brochure_url(html: str, base_url: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for link in soup.find_all("a", href=True):
        href = _absolute_url(link["href"], base_url)
        if "brochure" in href.lower() and href.lower().endswith(".pdf"):
            return href
    return None


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.lower()).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")


def _absolute_url(href: str, base_url: str) -> str:
    parsed = urlparse(urljoin(base_url, href))._replace(query="", fragment="")
    return urlunparse(parsed).rstrip("/")


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _deduplicate(courses: list[CayetanoCourse]) -> list[CayetanoCourse]:
    unique: dict[tuple[str, str | None, str | None], CayetanoCourse] = {}
    for course in courses:
        unique.setdefault((course.name, course.cycle, course.modality), course)
    return list(unique.values())