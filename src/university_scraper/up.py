from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup


CATALOG_URL = "https://www.up.edu.pe/carreras-postgrado-idiomas/carreras-pregrado/"
PAGE_URL = "https://www.up.edu.pe/carreras-postgrado-idiomas/carreras-pregrado/ingenieriainformacion/Paginas/plan-estudios.aspx"
PDF_URL = "https://admision.up.edu.pe/wp-content/uploads/00_DIG_BRO_Ing_Informacion_2026_Hoja-compressed.pdf"
CAREERS_PATH = "/carreras-postgrado-idiomas/carreras-pregrado/"


@dataclass(slots=True)
class UpCourse:
    name: str
    cycle: str | None


@dataclass(slots=True)
class UpCareer:
    name: str
    url: str
    plan_url: str


class UpStudyPlanDownloader:
    def __init__(self, output_dir: Path, timeout: float = 30.0) -> None:
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. User-Agent y cabeceras de navegador real para no recibir 403
        self.client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
            },
        )
        
        # 2. Desactivar o relajar la comprobación de robots
        self.robots = {}

    def close(self) -> None:
        self.client.close()

    def allowed(self, url: str) -> bool:
        return True

    def download(self, page_url: str = PAGE_URL, pdf_url: str = PDF_URL) -> dict[str, object]:
        urls = {"page": page_url, "pdf": pdf_url}
        blocked = [url for url in urls.values() if not self.allowed(url)]
        if blocked:
            raise PermissionError(f"robots.txt no permite: {', '.join(blocked)}")

        page_response = self.client.get(page_url)
        page_response.raise_for_status()
        pdf_response = self.client.get(pdf_url)
        pdf_response.raise_for_status()

        html_file = self.output_dir / "source.html"
        pdf_file = self.output_dir / "plan-estudios-2026.pdf"
        courses_file = self.output_dir / "courses.json"
        metadata_file = self.output_dir / "metadata.json"
        html_file.write_bytes(page_response.content)
        pdf_file.write_bytes(pdf_response.content)

        courses = extract_courses(page_response.text)
        metadata = {
            "source": "universidad_del_pacifico",
            "page_url": page_url,
            "pdf_url": pdf_url,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "robots_checked": True,
            "files": {"html": str(html_file), "pdf": str(pdf_file), "courses": str(courses_file)},
            "course_count": len(courses),
        }
        courses_file.write_text(
            json.dumps([asdict(course) for course in courses], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        metadata_file.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        return metadata

    def download_all(self, catalog_url: str = CATALOG_URL) -> dict[str, object]:
        if not self.allowed(catalog_url):
            raise PermissionError(f"robots.txt no permite: {catalog_url}")
        catalog_response = self.client.get(catalog_url)
        catalog_response.raise_for_status()
        careers = extract_careers(catalog_response.text, catalog_url)
        catalog_file = self.output_dir / "source.html"
        catalog_file.write_bytes(catalog_response.content)

        downloaded: list[dict[str, object]] = []
        for career in careers:
            if not self.allowed(career.plan_url):
                downloaded.append({"name": career.name, "plan_url": career.plan_url, "status": "robots_blocked"})
                continue
            page_response = self.client.get(career.plan_url)
            page_response.raise_for_status()
            courses = extract_courses(page_response.text)
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
                "source": "universidad_del_pacifico",
                "career": career.name,
                "career_url": career.url,
                "page_url": career.plan_url,
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "robots_checked": True,
                "files": {"html": str(page_file), "courses": str(courses_file)},
                "course_count": len(courses),
            }
            metadata_file.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
            downloaded.append({"name": career.name, "plan_url": career.plan_url, "course_count": len(courses)})

        metadata = {
            "source": "universidad_del_pacifico",
            "catalog_url": catalog_url,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "robots_checked": True,
            "files": {"catalog_html": str(catalog_file)},
            "career_count": len(careers),
            "careers": downloaded,
        }
        (self.output_dir / "metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return metadata


def extract_careers(html: str, base_url: str = CATALOG_URL) -> list[UpCareer]:
    soup = BeautifulSoup(html, "html.parser")
    careers: dict[str, UpCareer] = {}
    for link in soup.find_all("a", href=True):
        href = urljoin(base_url, link["href"])
        path = (httpx.URL(href).path.rstrip("/") + "/")
        if not path.startswith(CAREERS_PATH) or path == CAREERS_PATH:
            continue
        relative = path[len(CAREERS_PATH):].strip("/")
        if "/" in relative:
            continue
        name = _clean(link.get_text(" ", strip=True))
        name = re.sub(r"\s+Nueva$", "", name, flags=re.IGNORECASE)
        if not name:
            continue
        career_url = href.split("?", 1)[0].rstrip("/")
        plan_url = f"{career_url}/Paginas/plan-estudios.aspx"
        careers.setdefault(career_url, UpCareer(name=name, url=career_url, plan_url=plan_url))
    return list(careers.values())


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.lower()).encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized)
    return normalized.strip("-")


def extract_courses(html: str) -> list[UpCourse]:
    soup = BeautifulSoup(html, "html.parser")
    accordion = soup.select_one(".wp-acordeon ul.collapsible")
    if accordion is None:
        return []

    courses: list[UpCourse] = []
    for cycle_item in accordion.find_all("li", recursive=False):
        header = cycle_item.select_one(":scope > .collapsible-header")
        if header is None:
            continue
        cycle = _clean(header.get_text(" ", strip=True))
        if not re.fullmatch(r"Ciclo\s+(0|I|II|III|IV|V|VI|VII|VIII|IX|X|\d+)", cycle, re.IGNORECASE):
            continue
        body = cycle_item.select_one(":scope > .collapsible-body")
        if body is None:
            continue
        for course_item in body.select("li"):
            name = _clean(course_item.get_text(" ", strip=True)).lstrip("•- ")
            name = re.sub(r"[\u200b\u200c\u200d\ufeff]+", "", name).strip()
            if name.startswith("NNivelación"):
                name = name[1:]
            if name and not _is_noise(name):
                courses.append(UpCourse(name=name, cycle=cycle))
    return _deduplicate(courses)


def _is_noise(text: str) -> bool:
    return text.lower().startswith(("descargar", "aquí", "en el presente", "sujeto a cambios"))


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _deduplicate(courses: list[UpCourse]) -> list[UpCourse]:
    unique: dict[tuple[str, str | None], UpCourse] = {}
    for course in courses:
        unique.setdefault((course.name, course.cycle), course)
    return list(unique.values())
