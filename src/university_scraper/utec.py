from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup


PAGE_URL = "https://utec.edu.pe/carreras/ciencia-de-datos-e-inteligencia-artificial"
CURRICULUM_IMAGE = "/sites/default/files/2024-07/image%20%2815%29.png"


@dataclass(slots=True)
class CurriculumCourse:
    name: str
    credits: int | None
    prerequisite: str | None
    cycle: str | None


class UtecCurriculumDownloader:
    def __init__(self, output_dir: Path, timeout: float = 30.0) -> None:
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": "AnaliticaWebResearch/0.1 (+contacto-del-proyecto)"},
        )
        self.robots = RobotFileParser("https://utec.edu.pe/robots.txt")
        self.robots.read()

    def close(self) -> None:
        self.client.close()

    def allowed(self, url: str) -> bool:
        return self.robots.can_fetch(self.client.headers["User-Agent"], url)

    def download(self, page_url: str = PAGE_URL, image_path: str = CURRICULUM_IMAGE) -> dict[str, object]:
        image_url = urljoin(page_url, image_path)
        urls = {"page": page_url, "curriculum_image": image_url}
        blocked = [url for url in urls.values() if not self.allowed(url)]
        if blocked:
            raise PermissionError(f"robots.txt no permite: {', '.join(blocked)}")

        page_response = self.client.get(page_url)
        page_response.raise_for_status()
        image_response = self.client.get(image_url)
        image_response.raise_for_status()

        page_file = self.output_dir / "source.html"
        image_file = self.output_dir / "page-decoration.png"
        metadata_file = self.output_dir / "metadata.json"
        courses_file = self.output_dir / "courses.json"
        page_file.write_bytes(page_response.content)
        image_file.write_bytes(image_response.content)

        courses = extract_courses(page_response.text)
        captured_at = datetime.now(timezone.utc).isoformat()
        metadata = {
            "source": "utec",
            "page_url": page_url,
            "curriculum_image_url": image_url,
            "captured_at": captured_at,
            "robots_checked": True,
            "files": {
                "html": str(page_file),
                "page_decoration": str(image_file),
                "courses": str(courses_file),
            },
            "course_count": len(courses),
        }
        metadata_file.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        courses_file.write_text(
            json.dumps([asdict(course) for course in courses], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return metadata


def extract_courses(html: str) -> list[CurriculumCourse]:
    soup = BeautifulSoup(html, "html.parser")
    curriculum_heading = soup.find(
        lambda tag: tag.name in {"h2", "h3"}
        and "malla curricular" in tag.get_text(" ", strip=True).lower()
    )
    if curriculum_heading is None:
        return []
    courses: list[CurriculumCourse] = []
    for name_node in curriculum_heading.find_all_next("h5"):
        course_item = name_node.find_parent("li")
        if course_item is None:
            continue
        name = _clean(name_node.get_text(" ", strip=True))
        item_text = _clean(course_item.get_text(" ", strip=True))
        credit_match = re.search(r"(\d+)\s+cr[eé]ditos", item_text, re.IGNORECASE)
        if not credit_match:
            continue
        prerequisite_match = re.search(r"Prerrequisito:\s*(.+)$", item_text, re.IGNORECASE)
        courses.append(CurriculumCourse(
            name=name,
            credits=int(credit_match.group(1)),
            prerequisite=_clean(prerequisite_match.group(1)) if prerequisite_match else None,
            cycle=_cycle_for(course_item),
        ))
    return courses


def _cycle_for(course_item: object) -> str | None:
    for ancestor in course_item.parents:  # type: ignore[attr-defined]
        if getattr(ancestor, "name", None) != "li":
            continue
        cycle_match = re.search(r"\bCiclo\s+(\d+)\b", ancestor.get_text(" ", strip=True), re.IGNORECASE)
        if cycle_match:
            return f"Ciclo {cycle_match.group(1)}"
    return None


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" -:;,")
