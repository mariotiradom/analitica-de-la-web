from __future__ import annotations

import json
import re
import subprocess
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup


CATALOG_URL = "https://www.pucp.edu.pe/pregrado/carreras/por-facultad/"
ARQUITECTURA_PLAN_URL = "https://arquitectura.pucp.edu.pe/estudios/pregrado/plan-de-estudios/"


@dataclass(slots=True)
class PucpCourse:
    name: str
    code: str | None = None
    credits: int | None = None
    stage: str | None = None
    cycle: str | None = None
    url: str | None = None


@dataclass(slots=True)
class PucpCareer:
    name: str
    faculty: str
    career_url: str
    plan_url: str
    modality: str | None = None
    description: str | None = None


class PucpCurriculumDownloader:
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
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
            },
            event_hooks={"response": [_rewrite_redirect_to_https]},
        )

    def close(self) -> None:
        self.client.close()

    def download_catalog(self, catalog_url: str = CATALOG_URL) -> tuple[Path, list[PucpCareer]]:
        response = self.client.get(catalog_url)
        response.raise_for_status()

        catalog_file = self.output_dir / "catalog.html"
        catalog_file.write_bytes(response.content)

        careers = extract_catalog_careers(response.text, catalog_url)
        metadata = {
            "source": "pontificia_universidad_catolica_del_peru",
            "catalog_url": catalog_url,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "career_count": len(careers),
            "faculties": sorted({career.faculty for career in careers}),
            "careers": [asdict(career) for career in careers],
            "files": {"catalog_html": str(catalog_file)},
        }
        (self.output_dir / "metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return catalog_file, careers

    def download_arquitectura(
        self,
        career: PucpCareer | None = None,
        plan_url: str | None = None,
        download_pdf: bool = True,
    ) -> dict[str, object]:
        target_url = normalize_pucp_url(plan_url or (career.plan_url if career else ARQUITECTURA_PLAN_URL))
        response = self.client.get(target_url)
        response.raise_for_status()

        courses = extract_arquitectura_courses(response.text, str(response.url))
        pdf_url = extract_arquitectura_pdf_url(response.text, str(response.url))

        career_dir = self.output_dir / "arquitectura"
        career_dir.mkdir(parents=True, exist_ok=True)

        source_file = career_dir / "source.html"
        courses_file = career_dir / "courses.json"
        metadata_file = career_dir / "metadata.json"

        source_file.write_bytes(response.content)
        courses_file.write_text(
            json.dumps([asdict(c) for c in courses], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        files_map: dict[str, str] = {
            "html": str(source_file),
            "courses": str(courses_file),
        }

        pdf_size_bytes = None
        if download_pdf and pdf_url:
            pdf_file = career_dir / "plan-estudios.pdf"
            try:
                pdf_response = self.client.get(pdf_url)
                pdf_response.raise_for_status()
                pdf_file.write_bytes(pdf_response.content)
                files_map["pdf"] = str(pdf_file)
                pdf_size_bytes = len(pdf_response.content)
            except Exception as e:
                files_map["pdf_error"] = str(e)

        stages_breakdown: dict[str, int] = {}
        for c in courses:
            key = c.stage or "Sin etapa"
            stages_breakdown[key] = stages_breakdown.get(key, 0) + 1

        metadata: dict[str, object] = {
            "source": "pontificia_universidad_catolica_del_peru",
            "faculty": career.faculty if career else "Facultad de Arquitectura y Urbanismo",
            "career": career.name if career else "Arquitectura",
            "career_url": career.career_url if career else "https://www.pucp.edu.pe/carrera/arquitectura/",
            "plan_url": target_url,
            "final_url": str(response.url),
            "pdf_url": pdf_url,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "files": files_map,
            "course_count": len(courses),
            "stages": stages_breakdown,
        }
        if pdf_size_bytes is not None:
            metadata["pdf_size_bytes"] = pdf_size_bytes

        metadata_file.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        return metadata

    def download_arte_diseno(
        self,
        careers: list[PucpCareer] | None = None,
    ) -> dict[str, object]:
        if careers is None:
            _, all_careers = self.download_catalog()
            careers = [c for c in all_careers if c.faculty == "Facultad de Arte y Diseño"]

        downloaded: list[dict[str, object]] = []
        for career in careers:
            target_url = normalize_pucp_url(career.plan_url)
            response = self.client.get(target_url)
            response.raise_for_status()

            final_url_str = str(response.url)
            if not final_url_str.rstrip("/").endswith("plan-estudios"):
                plan_candidate = final_url_str.rstrip("/") + "/plan-estudios/"
                try:
                    cand_resp = self.client.get(plan_candidate)
                    if cand_resp.status_code == 200:
                        response = cand_resp
                        final_url_str = str(response.url)
                except Exception:
                    pass

            courses = extract_arte_diseno_courses(response.text, final_url_str)

            career_dir = self.output_dir / slugify(career.name)
            career_dir.mkdir(parents=True, exist_ok=True)

            source_file = career_dir / "source.html"
            courses_file = career_dir / "courses.json"
            metadata_file = career_dir / "metadata.json"

            source_file.write_bytes(response.content)
            courses_file.write_text(
                json.dumps([asdict(c) for c in courses], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            career_meta = {
                "source": "pontificia_universidad_catolica_del_peru",
                "faculty": career.faculty,
                "career": career.name,
                "career_url": career.career_url,
                "plan_url": target_url,
                "final_url": final_url_str,
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "files": {
                    "html": str(source_file),
                    "courses": str(courses_file),
                },
                "course_count": len(courses),
            }
            metadata_file.write_text(json.dumps(career_meta, ensure_ascii=False, indent=2), encoding="utf-8")
            downloaded.append({
                "name": career.name,
                "plan_url": final_url_str,
                "course_count": len(courses),
            })

        faculty_metadata = {
            "source": "pontificia_universidad_catolica_del_peru",
            "faculty": "Facultad de Arte y Diseño",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "career_count": len(downloaded),
            "careers": downloaded,
        }
        (self.output_dir / "arte-y-diseno-metadata.json").write_text(
            json.dumps(faculty_metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return faculty_metadata

    def download_ciencias_ingenieria(
        self,
        careers: list[PucpCareer] | None = None,
        download_pdf: bool = True,
    ) -> dict[str, object]:
        if careers is None:
            _, all_careers = self.download_catalog()
            careers = [c for c in all_careers if "ingenier" in c.faculty.lower()]

        downloaded: list[dict[str, object]] = []
        for career in careers:
            career_slug = slugify(re.sub(r"\s+PUCP$", "", career.name, flags=re.IGNORECASE))
            fci_plan_url = normalize_pucp_url(career.plan_url) or f"https://facultad-ciencias-ingenieria.pucp.edu.pe/carreras/{career_slug}/plan-de-estudios/"

            career_dir = self.output_dir / career_slug
            career_dir.mkdir(parents=True, exist_ok=True)

            files_map: dict[str, str] = {}
            fci_pdf_url = None

            try:
                fci_response = self.client.get(fci_plan_url)
                if fci_response.status_code == 200:
                    fci_file = career_dir / "source.html"
                    fci_file.write_bytes(fci_response.content)
                    files_map["html"] = str(fci_file)
                    fci_pdf_url = extract_fci_pdf_url(fci_response.text, str(fci_response.url))
            except Exception as e:
                files_map["fci_error"] = str(e)

            # Estudios Generales Ciencias (EE.GG.CC.) para niveles 1 al 4
            eeggcc_plan_url = f"https://estudios-generales-ciencias.pucp.edu.pe/plan_estudio/{career_slug}/"
            eeggcc_pdf_url = None
            courses: list[PucpCourse] = []

            try:
                eeggcc_resp = self.client.get(eeggcc_plan_url)
                if eeggcc_resp.status_code == 200:
                    eeggcc_file = career_dir / "eeggcc_source.html"
                    eeggcc_file.write_bytes(eeggcc_resp.content)
                    files_map["eeggcc_html"] = str(eeggcc_file)
                    courses = extract_eeggcc_courses(eeggcc_resp.text, str(eeggcc_resp.url))
                    eeggcc_pdf_url = extract_eeggcc_pdf_url(eeggcc_resp.text, str(eeggcc_resp.url))
            except Exception as e:
                files_map["eeggcc_error"] = str(e)

            courses_file = career_dir / "courses.json"
            courses_file.write_text(
                json.dumps([asdict(c) for c in courses], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            files_map["courses"] = str(courses_file)

            # Descarga de PDFs si aplica
            if download_pdf:
                if fci_pdf_url:
                    fci_pdf_file = career_dir / "plan-estudios-fci.pdf"
                    try:
                        pdf_resp = self.client.get(fci_pdf_url)
                        if pdf_resp.status_code == 200:
                            fci_pdf_file.write_bytes(pdf_resp.content)
                            files_map["fci_pdf"] = str(fci_pdf_file)
                    except Exception as e:
                        files_map["fci_pdf_error"] = str(e)

                if eeggcc_pdf_url:
                    eeggcc_pdf_file = career_dir / "plan-estudios-eeggcc.pdf"
                    try:
                        pdf_resp = self.client.get(eeggcc_pdf_url)
                        if pdf_resp.status_code == 200:
                            eeggcc_pdf_file.write_bytes(pdf_resp.content)
                            files_map["eeggcc_pdf"] = str(eeggcc_pdf_file)
                    except Exception as e:
                        files_map["eeggcc_pdf_error"] = str(e)

            metadata_file = career_dir / "metadata.json"
            career_meta = {
                "source": "pontificia_universidad_catolica_del_peru",
                "faculty": "Facultad de Ciencias e Ingeniería",
                "career": career.name,
                "career_url": career.career_url,
                "fci_plan_url": fci_plan_url,
                "eeggcc_plan_url": eeggcc_plan_url,
                "fci_pdf_url": fci_pdf_url,
                "eeggcc_pdf_url": eeggcc_pdf_url,
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "files": files_map,
                "course_count": len(courses),
                "notes": "Niveles 1 al 4 en HTML de Estudios Generales Ciencias (EEGGCC); niveles 5 en adelante en PDF de Facultad de Ciencias e Ingeniería (FCI).",
            }
            metadata_file.write_text(json.dumps(career_meta, ensure_ascii=False, indent=2), encoding="utf-8")
            downloaded.append({
                "name": career.name,
                "plan_url": fci_plan_url,
                "fci_pdf_url": fci_pdf_url,
                "eeggcc_pdf_url": eeggcc_pdf_url,
                "course_count": len(courses),
            })

        faculty_metadata = {
            "source": "pontificia_universidad_catolica_del_peru",
            "faculty": "Facultad de Ciencias e Ingeniería",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "career_count": len(downloaded),
            "careers": downloaded,
        }
        (self.output_dir / "ciencias-e-ingenieria-metadata.json").write_text(
            json.dumps(faculty_metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return faculty_metadata

    def download_ciencias_sociales(
        self,
        careers: list[PucpCareer] | None = None,
        download_pdf: bool = True,
    ) -> dict[str, object]:
        if careers is None:
            _, all_careers = self.download_catalog()
            careers = [c for c in all_careers if "social" in c.faculty.lower()]

        sociales_plan_urls = {
            "antropologia": "https://facultad-ciencias-sociales.pucp.edu.pe/carreras/antropologia/planes-de-estudio/",
            "ciencia-politica-y-gobierno": "https://facultad-ciencias-sociales.pucp.edu.pe/carreras/ciencia-politica-y-gobierno/planes-de-estudio/",
            "economia": "https://facultad-ciencias-sociales.pucp.edu.pe/carreras/economia/plan-de-estudio/",
            "finanzas": "https://facultad-ciencias-sociales.pucp.edu.pe/carreras/finanzas/planes-de-estudio/plan-de-estudios-07/",
            "relaciones-internacionales": "https://facultad-ciencias-sociales.pucp.edu.pe/carreras/relaciones-internacionales/planes-de-estudio/",
            "sociologia": "https://facultad-ciencias-sociales.pucp.edu.pe/carreras/sociologia/planes-de-estudio/nuevo-plan-de-estudio/",
        }

        downloaded: list[dict[str, object]] = []
        for career in careers:
            career_slug = slugify(career.name)
            target_url = sociales_plan_urls.get(career_slug) or normalize_pucp_url(career.plan_url)

            career_dir = self.output_dir / career_slug
            career_dir.mkdir(parents=True, exist_ok=True)

            files_map: dict[str, str] = {}
            pdf_url = None
            pdf_size_bytes = None

            try:
                response = self.client.get(target_url)
                if response.status_code == 200:
                    source_file = career_dir / "source.html"
                    source_file.write_bytes(response.content)
                    files_map["html"] = str(source_file)
                    pdf_url = extract_sociales_pdf_url(response.text, str(response.url))
            except Exception as e:
                files_map["error"] = str(e)

            if download_pdf and pdf_url:
                pdf_file = career_dir / "plan-estudios.pdf"
                try:
                    pdf_resp = self.client.get(pdf_url)
                    if pdf_resp.status_code == 200:
                        pdf_file.write_bytes(pdf_resp.content)
                        files_map["pdf"] = str(pdf_file)
                        pdf_size_bytes = len(pdf_resp.content)
                except Exception as e:
                    files_map["pdf_error"] = str(e)

            metadata_file = career_dir / "metadata.json"
            career_meta = {
                "source": "pontificia_universidad_catolica_del_peru",
                "faculty": "Facultad de Ciencias Sociales",
                "career": career.name,
                "career_url": career.career_url,
                "plan_url": target_url,
                "pdf_url": pdf_url,
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "files": files_map,
                "pdf_size_bytes": pdf_size_bytes,
                "notes": "La Facultad de Ciencias Sociales publica sus mallas curriculares mediante documento oficial en formato PDF.",
            }
            metadata_file.write_text(json.dumps(career_meta, ensure_ascii=False, indent=2), encoding="utf-8")
            downloaded.append({
                "name": career.name,
                "plan_url": target_url,
                "pdf_url": pdf_url,
                "pdf_size_bytes": pdf_size_bytes,
            })

        faculty_metadata = {
            "source": "pontificia_universidad_catolica_del_peru",
            "faculty": "Facultad de Ciencias Sociales",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "career_count": len(downloaded),
            "careers": downloaded,
        }
        (self.output_dir / "ciencias-sociales-metadata.json").write_text(
            json.dumps(faculty_metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return faculty_metadata

    def download_artes_escenicas(
        self,
        careers: list[PucpCareer] | None = None,
        download_pdf: bool = True,
    ) -> dict[str, object]:
        if careers is None:
            _, all_careers = self.download_catalog()
            careers = [c for c in all_careers if "esc" in c.faculty.lower()]

        fares_plan_urls = {
            "creacion-y-produccion-escenica": "https://facultad-artes-escenicas.pucp.edu.pe/carreras/creacion-y-produccion-escenicas/plan-de-estudio-creacion-y-produccion-escenica/",
            "danza": "https://facultad-artes-escenicas.pucp.edu.pe/carreras/danza/plan-de-estudio-v2-danza/",
            "teatro": "https://facultad-artes-escenicas.pucp.edu.pe/carreras/teatro/plan-de-estudio-teatro/",
        }

        musica_specializations = [
            {
                "name": "Canto",
                "slug": "canto",
                "url": "https://facultad-artes-escenicas.pucp.edu.pe/carreras/musica/plan-de-estudio/plan-de-estudio-canto/",
                "pdf_filename": "plan-estudios-canto.pdf",
            },
            {
                "name": "Composición Musical",
                "slug": "composicion-musical",
                "url": "https://facultad-artes-escenicas.pucp.edu.pe/carreras/musica/plan-de-estudio/plan-de-estudio-composicion-musical/",
                "pdf_filename": "plan-estudios-composicion-musical.pdf",
            },
            {
                "name": "Ejecución Musical",
                "slug": "ejecucion-musical",
                "url": "https://facultad-artes-escenicas.pucp.edu.pe/carreras/musica/plan-de-estudio/plan-de-estudio-ejecucion-musical/",
                "pdf_filename": "plan-estudios-ejecucion-musical.pdf",
            },
            {
                "name": "Producción Musical",
                "slug": "produccion-musical",
                "url": "https://facultad-artes-escenicas.pucp.edu.pe/carreras/musica/plan-de-estudio/plan-de-estudio-produccion-musical/",
                "pdf_filename": "plan-estudios-produccion-musical.pdf",
            },
        ]

        downloaded: list[dict[str, object]] = []
        for career in careers:
            career_slug = slugify(career.name)
            career_dir = self.output_dir / career_slug
            career_dir.mkdir(parents=True, exist_ok=True)

            if career_slug == "musica":
                spec_results = []
                files_map: dict[str, str] = {}
                main_source_saved = False

                for spec in musica_specializations:
                    spec_url = spec["url"]
                    spec_pdf_url = None
                    spec_pdf_size = None
                    try:
                        resp = self.client.get(spec_url)
                        if resp.status_code == 200:
                            if not main_source_saved:
                                source_file = career_dir / "source.html"
                                source_file.write_bytes(resp.content)
                                files_map["html"] = str(source_file)
                                main_source_saved = True
                            spec_pdf_url = extract_artes_escenicas_pdf_url(resp.text, str(resp.url))
                    except Exception as e:
                        files_map[f"error_{spec['slug']}"] = str(e)

                    if download_pdf and spec_pdf_url:
                        pdf_file = career_dir / spec["pdf_filename"]
                        try:
                            pdf_resp = self.client.get(spec_pdf_url)
                            if pdf_resp.status_code == 200:
                                pdf_file.write_bytes(pdf_resp.content)
                                files_map[f"pdf_{spec['slug']}"] = str(pdf_file)
                                spec_pdf_size = len(pdf_resp.content)
                        except Exception as e:
                            files_map[f"pdf_error_{spec['slug']}"] = str(e)

                    spec_results.append({
                        "specialization": spec["name"],
                        "plan_url": spec_url,
                        "pdf_url": spec_pdf_url,
                        "pdf_file": files_map.get(f"pdf_{spec['slug']}"),
                        "pdf_size_bytes": spec_pdf_size,
                    })

                metadata_file = career_dir / "metadata.json"
                career_meta = {
                    "source": "pontificia_universidad_catolica_del_peru",
                    "faculty": "Facultad de Artes Escénicas",
                    "career": career.name,
                    "career_url": career.career_url,
                    "captured_at": datetime.now(timezone.utc).isoformat(),
                    "specializations": spec_results,
                    "files": files_map,
                    "notes": "La carrera de Música en la Facultad de Artes Escénicas cuenta con 4 menciones oficiales (Canto, Composición Musical, Ejecución Musical y Producción Musical), cada una con su plan de estudios oficial en PDF.",
                }
                metadata_file.write_text(json.dumps(career_meta, ensure_ascii=False, indent=2), encoding="utf-8")
                downloaded.append({
                    "name": career.name,
                    "specializations": [s["specialization"] for s in spec_results],
                    "pdf_count": len([s for s in spec_results if s.get("pdf_size_bytes")]),
                })
            else:
                target_url = fares_plan_urls.get(career_slug) or normalize_pucp_url(career.plan_url)
                files_map: dict[str, str] = {}
                pdf_url = None
                pdf_size_bytes = None

                try:
                    response = self.client.get(target_url)
                    if response.status_code == 200:
                        source_file = career_dir / "source.html"
                        source_file.write_bytes(response.content)
                        files_map["html"] = str(source_file)
                        pdf_url = extract_artes_escenicas_pdf_url(response.text, str(response.url))
                except Exception as e:
                    files_map["error"] = str(e)

                if download_pdf and pdf_url:
                    pdf_file = career_dir / "plan-estudios.pdf"
                    try:
                        pdf_resp = self.client.get(pdf_url)
                        if pdf_resp.status_code == 200:
                            pdf_file.write_bytes(pdf_resp.content)
                            files_map["pdf"] = str(pdf_file)
                            pdf_size_bytes = len(pdf_resp.content)
                    except Exception as e:
                        files_map["pdf_error"] = str(e)

                metadata_file = career_dir / "metadata.json"
                career_meta = {
                    "source": "pontificia_universidad_catolica_del_peru",
                    "faculty": "Facultad de Artes Escénicas",
                    "career": career.name,
                    "career_url": career.career_url,
                    "plan_url": target_url,
                    "pdf_url": pdf_url,
                    "captured_at": datetime.now(timezone.utc).isoformat(),
                    "files": files_map,
                    "pdf_size_bytes": pdf_size_bytes,
                    "notes": "La Facultad de Artes Escénicas publica sus mallas curriculares mediante documento oficial en formato PDF.",
                }
                metadata_file.write_text(json.dumps(career_meta, ensure_ascii=False, indent=2), encoding="utf-8")
                downloaded.append({
                    "name": career.name,
                    "plan_url": target_url,
                    "pdf_url": pdf_url,
                    "pdf_size_bytes": pdf_size_bytes,
                })

        faculty_metadata = {
            "source": "pontificia_universidad_catolica_del_peru",
            "faculty": "Facultad de Artes Escénicas",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "career_count": len(downloaded),
            "careers": downloaded,
        }
        (self.output_dir / "artes-escenicas-metadata.json").write_text(
            json.dumps(faculty_metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return faculty_metadata

    def download_comunicacion(
        self,
        careers: list[PucpCareer] | None = None,
        download_pdf: bool = True,
    ) -> dict[str, object]:
        if careers is None:
            _, all_careers = self.download_catalog()
            careers = [c for c in all_careers if "comunicaci" in c.faculty.lower()]

        eeggll_plan_url = "https://estudios-generales-letras.pucp.edu.pe/planes/plan-de-estudios-a-partir-del-2026-1/"
        eeggll_pdf_url = "https://estudios-generales-letras.pucp.edu.pe/wp-content/uploads/2026/06/Plan-de-estudios-2026-version-web-editable-19-JUNIO.pdf"
        eeggll_genially_url = "https://view.genially.com/6644de6aea2afd001405944b"

        eeggll_content: bytes | None = None
        eeggll_pdf_content: bytes | None = None
        try:
            eeggll_resp = self.client.get(eeggll_plan_url)
            if eeggll_resp.status_code == 200:
                eeggll_content = eeggll_resp.content
        except Exception:
            pass

        if download_pdf:
            try:
                pdf_resp = self.client.get(eeggll_pdf_url)
                if pdf_resp.status_code == 200:
                    eeggll_pdf_content = pdf_resp.content
            except Exception:
                pass

        downloaded: list[dict[str, object]] = []
        for career in careers:
            career_slug = slugify(career.name)
            career_dir = self.output_dir / career_slug
            career_dir.mkdir(parents=True, exist_ok=True)

            target_url = normalize_pucp_url(career.plan_url)
            files_map: dict[str, str] = {}
            pdf_url = None
            pdf_size_bytes = None
            courses: list[PucpCourse] = []

            if eeggll_content:
                eeggll_file = career_dir / "eeggll_source.html"
                eeggll_file.write_bytes(eeggll_content)
                files_map["eeggll_html"] = str(eeggll_file)

            if download_pdf and eeggll_pdf_content:
                eeggll_pdf_file = career_dir / "plan-estudios-eeggll.pdf"
                eeggll_pdf_file.write_bytes(eeggll_pdf_content)
                files_map["eeggll_pdf"] = str(eeggll_pdf_file)

            try:
                response = self.client.get(target_url)
                if response.status_code == 200:
                    source_file = career_dir / "source.html"
                    source_file.write_bytes(response.content)
                    files_map["html"] = str(source_file)
                    pdf_url = extract_comunicacion_pdf_url(response.text, str(response.url))
            except Exception as e:
                files_map["error"] = str(e)

            if download_pdf and pdf_url:
                pdf_file = career_dir / "plan-estudios.pdf"
                try:
                    pdf_resp = self.client.get(pdf_url)
                    if pdf_resp.status_code == 200:
                        pdf_file.write_bytes(pdf_resp.content)
                        files_map["pdf"] = str(pdf_file)
                        pdf_size_bytes = len(pdf_resp.content)
                        courses = extract_comunicacion_pdf_courses(pdf_file)
                except Exception as e:
                    files_map["pdf_error"] = str(e)

            if courses:
                courses_file = career_dir / "courses.json"
                courses_file.write_text(
                    json.dumps([asdict(c) for c in courses], ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                files_map["courses"] = str(courses_file)

            metadata_file = career_dir / "metadata.json"
            career_meta = {
                "source": "pontificia_universidad_catolica_del_peru",
                "faculty": "Facultad de Ciencias y Artes de la Comunicación",
                "career": career.name,
                "career_url": career.career_url,
                "plan_url": target_url,
                "pdf_url": pdf_url,
                "eeggll_plan_url": eeggll_plan_url,
                "eeggll_pdf_url": eeggll_pdf_url,
                "eeggll_interactive_map_url": eeggll_genially_url,
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "files": files_map,
                "pdf_size_bytes": pdf_size_bytes,
                "course_count": len(courses),
                "notes": (
                    "Los niveles 1 al 4 corresponden a Estudios Generales Letras (EEGGLL), cuyo plan se preserva "
                    "en plan-estudios-eeggll.pdf y mapa interactivo en Genially. Los niveles 5 al 10 corresponden "
                    "a la Facultad de Ciencias y Artes de la Comunicación, expuestos como imágenes en la web y "
                    "preservados en plan-estudios.pdf descargado del hipervínculo oficial 'aquí'."
                ),
            }
            metadata_file.write_text(json.dumps(career_meta, ensure_ascii=False, indent=2), encoding="utf-8")
            downloaded.append({
                "name": career.name,
                "plan_url": target_url,
                "pdf_url": pdf_url,
                "pdf_size_bytes": pdf_size_bytes,
                "course_count": len(courses),
            })

        faculty_metadata = {
            "source": "pontificia_universidad_catolica_del_peru",
            "faculty": "Facultad de Ciencias y Artes de la Comunicación",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "career_count": len(downloaded),
            "careers": downloaded,
        }
        (self.output_dir / "ciencias-y-artes-de-la-comunicacion-metadata.json").write_text(
            json.dumps(faculty_metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return faculty_metadata

    def download_letras_humanas(
        self,
        careers: list[PucpCareer] | None = None,
        download_pdf: bool = True,
    ) -> dict[str, object]:
        if careers is None:
            _, all_careers = self.download_catalog()
            careers = [
                c for c in all_careers
                if "humanas" in c.faculty.lower() or "letras y ciencias humanas" in c.faculty.lower()
            ]

        eeggll_plan_url = "https://estudios-generales-letras.pucp.edu.pe/planes/plan-de-estudios-a-partir-del-2026-1/"
        eeggll_pdf_url = "https://estudios-generales-letras.pucp.edu.pe/wp-content/uploads/2026/06/Plan-de-estudios-2026-version-web-editable-19-JUNIO.pdf"
        eeggll_genially_url = "https://view.genially.com/6644de6aea2afd001405944b"

        eeggll_content: bytes | None = None
        eeggll_pdf_content: bytes | None = None
        try:
            eeggll_resp = self.client.get(eeggll_plan_url)
            if eeggll_resp.status_code == 200:
                eeggll_content = eeggll_resp.content
        except Exception:
            pass

        if download_pdf:
            try:
                pdf_resp = self.client.get(eeggll_pdf_url)
                if pdf_resp.status_code == 200:
                    eeggll_pdf_content = pdf_resp.content
            except Exception:
                pass

        planes_urls = {
            "arqueologia": ["https://planesllcchhpucp.com/arqueologia"],
            "ciencias-de-la-informacion": ["https://planesllcchhpucp.com/cienciasdelainformacion"],
            "filosofia": ["https://planesllcchhpucp.com/filosofia"],
            "geografia-y-medio-ambiente": ["https://planesllcchhpucp.com/geografiaymedioambiente"],
            "historia": ["https://planesllcchhpucp.com/historia"],
            "linguistica-y-literatura": [
                "https://planesllcchhpucp.com/linguistica",
                "https://planesllcchhpucp.com/literaturahispanica",
            ],
        }

        downloaded: list[dict[str, object]] = []
        for career in careers:
            career_slug = slugify(career.name)
            career_dir = self.output_dir / career_slug
            career_dir.mkdir(parents=True, exist_ok=True)

            target_url = normalize_pucp_url(career.plan_url)
            files_map: dict[str, str] = {}
            courses: list[PucpCourse] = []

            if eeggll_content:
                eeggll_file = career_dir / "eeggll_source.html"
                eeggll_file.write_bytes(eeggll_content)
                files_map["eeggll_html"] = str(eeggll_file)

            if download_pdf and eeggll_pdf_content:
                eeggll_pdf_file = career_dir / "plan-estudios-eeggll.pdf"
                eeggll_pdf_file.write_bytes(eeggll_pdf_content)
                files_map["eeggll_pdf"] = str(eeggll_pdf_file)

            try:
                response = self.client.get(target_url)
                if response.status_code == 200:
                    source_file = career_dir / "source.html"
                    source_file.write_bytes(response.content)
                    files_map["html"] = str(source_file)
            except Exception as e:
                files_map["error"] = str(e)

            pdf_url = None
            pdf_size_bytes = None
            if career_slug == "geografia-y-medio-ambiente" and download_pdf:
                geo_pdf_url = "https://facultad.pucp.edu.pe/letras-ciencias-humanas/wp-content/uploads/2017/11/1.-Malla-curricular-1.pdf"
                try:
                    pdf_resp = self.client.get(geo_pdf_url)
                    if pdf_resp.status_code == 200:
                        pdf_file = career_dir / "plan-estudios.pdf"
                        pdf_file.write_bytes(pdf_resp.content)
                        files_map["pdf"] = str(pdf_file)
                        pdf_url = geo_pdf_url
                        pdf_size_bytes = len(pdf_resp.content)
                except Exception as e:
                    files_map["pdf_error"] = str(e)

            ext_urls = planes_urls.get(career_slug, [])
            for idx, ext_url in enumerate(ext_urls):
                try:
                    ext_resp = self.client.get(ext_url)
                    if ext_resp.status_code == 200:
                        suffix = f"_{idx+1}" if len(ext_urls) > 1 else ""
                        planes_file = career_dir / f"planes_source{suffix}.html"
                        planes_file.write_bytes(ext_resp.content)
                        files_map[f"planes_html{suffix}"] = str(planes_file)
                        stage_label = (
                            f"Facultad de Letras y Ciencias Humanas - {ext_url.split('/')[-1].capitalize()}"
                            if len(ext_urls) > 1
                            else "Facultad de Letras y Ciencias Humanas"
                        )
                        parsed = parse_canva_courses(ext_resp.text, stage_label)
                        courses.extend(parsed)
                except Exception as e:
                    files_map[f"planes_error_{idx}"] = str(e)

            courses = _deduplicate(courses)
            if courses:
                courses_file = career_dir / "courses.json"
                courses_file.write_text(
                    json.dumps([asdict(c) for c in courses], ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                files_map["courses"] = str(courses_file)

            metadata_file = career_dir / "metadata.json"
            career_meta = {
                "source": "pontificia_universidad_catolica_del_peru",
                "faculty": "Facultad de Letras y Ciencias Humanas",
                "career": career.name,
                "career_url": career.career_url,
                "plan_url": target_url,
                "external_plan_urls": ext_urls,
                "pdf_url": pdf_url,
                "eeggll_plan_url": eeggll_plan_url,
                "eeggll_pdf_url": eeggll_pdf_url,
                "eeggll_interactive_map_url": eeggll_genially_url,
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "files": files_map,
                "course_count": len(courses),
                "pdf_size_bytes": pdf_size_bytes,
                "notes": (
                    "Los niveles 1 al 4 corresponden a Estudios Generales Letras (EEGGLL), cuyo plan se preserva "
                    "en plan-estudios-eeggll.pdf. Los niveles a partir del quinto ciclo corresponden a la Facultad "
                    "de Letras y Ciencias Humanas y están publicados en HTML (planesllcchhpucp.com)."
                ),
            }
            metadata_file.write_text(json.dumps(career_meta, ensure_ascii=False, indent=2), encoding="utf-8")
            downloaded.append({
                "name": career.name,
                "plan_url": target_url,
                "course_count": len(courses),
                "external_plan_urls": ext_urls,
                "pdf_url": pdf_url,
            })

        faculty_metadata = {
            "source": "pontificia_universidad_catolica_del_peru",
            "faculty": "Facultad de Letras y Ciencias Humanas",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "career_count": len(downloaded),
            "careers": downloaded,
        }
        (self.output_dir / "letras-y-ciencias-humanas-metadata.json").write_text(
            json.dumps(faculty_metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return faculty_metadata

    def download_ciencias_contables(
        self,
        careers: list[PucpCareer] | None = None,
        download_pdf: bool = True,
    ) -> dict[str, object]:
        if careers is None:
            _, all_careers = self.download_catalog()
            careers = [c for c in all_careers if "contab" in c.faculty.lower()]

        downloaded: list[dict[str, object]] = []
        for career in careers:
            career_slug = slugify(career.name)
            career_dir = self.output_dir / career_slug
            career_dir.mkdir(parents=True, exist_ok=True)

            target_url = normalize_pucp_url(career.plan_url)
            response = self.client.get(target_url)
            response.raise_for_status()

            source_file = career_dir / "source.html"
            source_file.write_bytes(response.content)

            files_map: dict[str, str] = {
                "source_html": str(source_file),
            }

            plan_2026_url = "https://facultad-ciencias-contables.pucp.edu.pe/carrera/plan-de-estudios/plan-2026/"
            plan_2021_url = "https://facultad-ciencias-contables.pucp.edu.pe/carrera/plan-de-estudios/plan-2021/"

            try:
                r_2026 = self.client.get(plan_2026_url)
                if r_2026.status_code == 200:
                    f_2026 = career_dir / "plan_2026_source.html"
                    f_2026.write_bytes(r_2026.content)
                    files_map["plan_2026_source_html"] = str(f_2026)
            except Exception as e:
                files_map["plan_2026_error"] = str(e)

            try:
                r_2021 = self.client.get(plan_2021_url)
                if r_2021.status_code == 200:
                    f_2021 = career_dir / "plan_2021_source.html"
                    f_2021.write_bytes(r_2021.content)
                    files_map["plan_2021_source_html"] = str(f_2021)
            except Exception as e:
                files_map["plan_2021_error"] = str(e)

            pdf_size_bytes: int | None = None
            pdf_2021_url = "https://drive.google.com/uc?export=download&id=1J98u86jp8BzZ1XfBkUPXJgaSccpHX2Nx"
            img_2026_url = "https://drive.google.com/uc?export=download&id=14F2SEZCVz_lshT6rcL24r8Kt0qUPg-ES"
            eeggll_pdf_url = "https://estudios-generales-letras.pucp.edu.pe/wp-content/uploads/2026/06/Plan-de-estudios-2026-version-web-editable-19-JUNIO.pdf"

            if download_pdf:
                # 1. Plan 2021 vector PDF
                try:
                    pdf_resp = self.client.get(pdf_2021_url)
                    if pdf_resp.status_code == 200:
                        pdf_file = career_dir / "plan-estudios.pdf"
                        pdf_file.write_bytes(pdf_resp.content)
                        files_map["pdf"] = str(pdf_file)
                        pdf_size_bytes = len(pdf_resp.content)
                except Exception as e:
                    files_map["pdf_error"] = str(e)

                # 2. Plan 2026 imagen oficial
                try:
                    img_resp = self.client.get(img_2026_url)
                    if img_resp.status_code == 200:
                        img_file = career_dir / "plan-estudios-2026.png"
                        img_file.write_bytes(img_resp.content)
                        files_map["plan_2026_image"] = str(img_file)
                except Exception as e:
                    files_map["plan_2026_image_error"] = str(e)

                # 3. Plan Estudios Generales Letras (Niveles 1 al 4)
                try:
                    eeggll_resp = self.client.get(eeggll_pdf_url)
                    if eeggll_resp.status_code == 200:
                        eeggll_file = career_dir / "plan-estudios-eeggll.pdf"
                        eeggll_file.write_bytes(eeggll_resp.content)
                        files_map["pdf_eeggll"] = str(eeggll_file)
                except Exception as e:
                    files_map["pdf_eeggll_error"] = str(e)

            metadata_file = career_dir / "metadata.json"
            career_meta = {
                "source": "pontificia_universidad_catolica_del_peru",
                "faculty": "Facultad de Ciencias Contables",
                "career": career.name,
                "career_url": career.career_url,
                "plan_url": target_url,
                "plan_2026_url": plan_2026_url,
                "plan_2021_url": plan_2021_url,
                "pdf_url": "https://drive.google.com/file/d/1J98u86jp8BzZ1XfBkUPXJgaSccpHX2Nx/view?usp=sharing",
                "plan_2026_image_url": "https://drive.google.com/file/d/14F2SEZCVz_lshT6rcL24r8Kt0qUPg-ES/view?usp=sharing",
                "eeggll_pdf_url": eeggll_pdf_url,
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "files": files_map,
                "pdf_size_bytes": pdf_size_bytes,
                "notes": (
                    "El plan de Contabilidad consta de 10 semestres: 4 semestres en Estudios Generales Letras "
                    "(EEGGLL, preservado en plan-estudios-eeggll.pdf) y 6 semestres en la Facultad de Ciencias "
                    "Contables (preservado en plan-estudios.pdf para el plan 2021 y plan-estudios-2026.png para el plan 2026). "
                    "La facultad no publica tablas de cursos en HTML."
                ),
            }
            metadata_file.write_text(json.dumps(career_meta, ensure_ascii=False, indent=2), encoding="utf-8")
            downloaded.append({
                "name": career.name,
                "plan_url": target_url,
                "pdf_url": career_meta["pdf_url"],
                "pdf_size_bytes": pdf_size_bytes,
            })

        faculty_metadata = {
            "source": "pontificia_universidad_catolica_del_peru",
            "faculty": "Facultad de Ciencias Contables",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "career_count": len(downloaded),
            "careers": downloaded,
        }
        (self.output_dir / "ciencias-contables-metadata.json").write_text(
            json.dumps(faculty_metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return faculty_metadata

    def download_faculty(self, faculty_query: str, download_pdf: bool = True) -> dict[str, object]:
        _, careers = self.download_catalog()
        query_norm = slugify(faculty_query)

        # 1. Buscar si coincide con arquitectura
        if "arquitectura" in query_norm:
            arq_career = next((c for c in careers if "arquitectura" in slugify(c.name)), None)
            return self.download_arquitectura(arq_career, download_pdf=download_pdf)

        # 2. Buscar si coincide con artes escénicas (antes de arte y diseño por la palabra 'arte')
        if any(w in query_norm for w in ["escenic", "fares", "teatro", "danza", "musica"]):
            fares_careers = [c for c in careers if "esc" in c.faculty.lower()]
            return self.download_artes_escenicas(fares_careers, download_pdf=download_pdf)

        # 3. Buscar si coincide con ciencias y artes de la comunicación (antes de arte y diseño y ciencias)
        if any(w in query_norm for w in ["comunicacion", "comunicaciones", "fcac", "periodismo", "publicidad"]):
            com_careers = [c for c in careers if "comunicaci" in c.faculty.lower()]
            return self.download_comunicacion(com_careers, download_pdf=download_pdf)

        # 4. Buscar si coincide con letras y ciencias humanas
        if any(w in query_norm for w in ["humanas", "letras-y-ciencias-humanas", "llch", "arqueologia", "filosofia", "historia"]):
            llch_careers = [
                c for c in careers
                if "humanas" in c.faculty.lower() or "letras y ciencias humanas" in c.faculty.lower()
            ]
            return self.download_letras_humanas(llch_careers, download_pdf=download_pdf)

        # 5. Buscar si coincide con ciencias contables
        if any(w in query_norm for w in ["contab", "contabilidad"]):
            contab_careers = [c for c in careers if "contab" in c.faculty.lower()]
            return self.download_ciencias_contables(contab_careers, download_pdf=download_pdf)

        # 6. Buscar si coincide con arte y diseño
        if "arte" in query_norm or "diseno" in query_norm:
            arte_careers = [c for c in careers if c.faculty == "Facultad de Arte y Diseño"]
            return self.download_arte_diseno(arte_careers)

        # 7. Buscar si coincide con ciencias sociales (antes de ciencias e ingenieria)
        if "social" in query_norm:
            social_careers = [c for c in careers if "social" in c.faculty.lower()]
            return self.download_ciencias_sociales(social_careers, download_pdf=download_pdf)

        # 8. Buscar si coincide con ciencias e ingeniería
        if "ingenieria" in query_norm or ("ciencias" in query_norm and "social" not in query_norm and "contab" not in query_norm):
            fci_careers = [c for c in careers if "ingenier" in c.faculty.lower()]
            return self.download_ciencias_ingenieria(fci_careers, download_pdf=download_pdf)

        matched_careers = [
            c for c in careers
            if query_norm in slugify(c.faculty) or query_norm in slugify(c.name)
        ]
        if not matched_careers:
            raise ValueError(f"No se encontraron carreras para la facultad/búsqueda: {faculty_query}")

        raise NotImplementedError(
            f"El scraper para la facultad '{matched_careers[0].faculty}' aún no está implementado. "
            "Actualmente están implementadas: Arquitectura, Arte y Diseño, Artes Escénicas, Ciencias y Artes de la Comunicación, Ciencias Contables, Ciencias e Ingeniería, Ciencias Sociales, Letras y Ciencias Humanas."
        )


def extract_catalog_careers(html: str, base_url: str = CATALOG_URL) -> list[PucpCareer]:
    soup = BeautifulSoup(html, "html.parser")
    careers: list[PucpCareer] = []

    for h2 in soup.find_all("h2"):
        faculty_name = _clean(h2.get_text(" ", strip=True))
        if not faculty_name:
            continue

        carreras_div = h2.find_next_sibling("div", class_="carreras")
        if not carreras_div:
            continue

        for item in carreras_div.select("ul.lista > li"):
            name_node = item.select_one("a.eventShow")
            if not name_node:
                continue
            name = _clean(name_node.get_text(" ", strip=True))
            if not name:
                continue

            bloque = item.select_one(".bloque") or item
            modality_node = bloque.select_one(".mod-fac")
            modality = _clean(modality_node.get_text(" ", strip=True)) if modality_node else None

            desc_node = bloque.select_one("p")
            description = _clean(desc_node.get_text(" ", strip=True)) if desc_node else None

            info_node = bloque.select_one(".doc-btn a")
            career_url = normalize_pucp_url(urljoin(base_url, info_node["href"])) if info_node and info_node.get("href") else ""

            plan_node = bloque.select_one(".btn-flecha-az a")
            plan_url = normalize_pucp_url(urljoin(base_url, plan_node["href"])) if plan_node and plan_node.get("href") else ""

            careers.append(
                PucpCareer(
                    name=name,
                    faculty=faculty_name,
                    career_url=career_url,
                    plan_url=plan_url,
                    modality=modality,
                    description=description,
                )
            )

    return careers


def extract_arquitectura_courses(html: str, base_url: str = ARQUITECTURA_PLAN_URL) -> list[PucpCourse]:
    soup = BeautifulSoup(html, "html.parser")
    courses: list[PucpCourse] = []

    # Secciones correspondientes a los 3 niveles
    panels = soup.select(".panel-default")
    if not panels:
        # Fallback por si la estructura de panels varía
        panels = soup.select("[id^='collapse-']")

    for panel in panels:
        stage_name = None
        heading_node = panel.select_one(".panel-heading .panel-title, h3")
        if heading_node:
            stage_name = _clean(heading_node.get_text(" ", strip=True))
        elif panel.get("id") and "collapse-" in panel.get("id", ""):
            collapse_id = panel["id"]
            heading_id = collapse_id.replace("collapse-", "heading-")
            corr_heading = soup.find(id=heading_id)
            if corr_heading:
                stage_name = _clean(corr_heading.get_text(" ", strip=True))

        for col in panel.select(".plan"):
            cycle_node = col.select_one(".hd")
            cycle_name = _clean(cycle_node.get_text(" ", strip=True)) if cycle_node else None

            for td in col.select(".td"):
                classes = td.get("class") or []
                if "total" in classes:
                    continue

                h2_node = td.select_one("h2")
                if not h2_node:
                    continue

                raw_name = _clean(h2_node.get_text(" ", strip=True))
                if not raw_name or "total de cr" in raw_name.lower():
                    continue

                link_node = h2_node.find("a", href=True)
                course_url = urljoin(base_url, link_node["href"]) if link_node else None

                code = None
                credits_val = None

                span_node = td.select_one("span")
                if span_node:
                    span_code_link = span_node.find("a")
                    if span_code_link:
                        code = _clean(span_code_link.get_text(strip=True))

                    span_text = _clean(span_node.get_text(" ", strip=True))
                    if not code and "/" in span_text:
                        possible_code = span_text.split("/", 1)[0].strip()
                        if re.match(r"^[A-Z0-9]+$", possible_code):
                            code = possible_code

                    credit_match = re.search(r"(\d+)\s+cr[eé]dito", span_text, re.IGNORECASE)
                    if credit_match:
                        credits_val = int(credit_match.group(1))

                courses.append(
                    PucpCourse(
                        name=raw_name,
                        code=code,
                        credits=credits_val,
                        stage=stage_name,
                        cycle=cycle_name,
                        url=course_url,
                    )
                )

    return _deduplicate(courses)


def extract_arte_diseno_courses(html: str, base_url: str = "") -> list[PucpCourse]:
    soup = BeautifulSoup(html, "html.parser")
    courses: list[PucpCourse] = []

    for table in soup.find_all("table"):
        headers: list[str] = []
        thead = table.find("thead")
        if thead:
            headers = [_clean(th.get_text(" ", strip=True)) for th in thead.find_all("th")]
        else:
            first_tr = table.find("tr")
            if first_tr:
                headers = [_clean(th.get_text(" ", strip=True)) for th in first_tr.find_all(["th", "td"])]

        tbody = table.find("tbody") or table
        rows = tbody.find_all("tr")
        if not thead and rows:
            rows = rows[1:]

        for row in rows:
            cells = row.find_all(["td", "th"])
            for idx, cell in enumerate(cells):
                raw_text = _clean(cell.get_text(" ", strip=True))
                if not raw_text or raw_text in {"-", "–", "—", "TOTAL", "Total"}:
                    continue
                cycle = headers[idx] if idx < len(headers) else None

                credit_match = re.search(r"\((\d+)\s*cr\.?\)", raw_text, re.IGNORECASE)
                credits_val = int(credit_match.group(1)) if credit_match else None
                name = re.sub(r"\s*\(\d+\s*cr\.?\)", "", raw_text, flags=re.IGNORECASE).strip()

                if not name or name in {"-", "–", "—"}:
                    continue

                courses.append(
                    PucpCourse(
                        name=name,
                        code=None,
                        credits=credits_val,
                        stage="Plan de estudios por semestre académico",
                        cycle=cycle,
                        url=None,
                    )
                )

    return _deduplicate(courses)


def extract_eeggcc_courses(html: str, base_url: str = "") -> list[PucpCourse]:
    soup = BeautifulSoup(html, "html.parser")
    courses: list[PucpCourse] = []

    for h5 in soup.find_all("h5"):
        cycle_text = _clean(h5.get_text(" ", strip=True))
        if not cycle_text.startswith("Nivel"):
            continue

        for a in h5.find_all_next(["a", "div"], class_=lambda c: c and "curso" in c):
            if a.find_previous("h5") != h5:
                break
            name = _clean(a.get_text(" ", strip=True))
            if not name:
                continue
            href = a.get("href")
            course_url = normalize_pucp_url(urljoin(base_url, href)) if href else None
            courses.append(
                PucpCourse(
                    name=name,
                    code=None,
                    credits=None,
                    stage="Estudios Generales Ciencias",
                    cycle=cycle_text,
                    url=course_url,
                )
            )

    return _deduplicate(courses)


def extract_fci_pdf_url(html: str, base_url: str = "") -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        text = _clean(a.get_text(" ", strip=True)).lower()
        if "descargar plan de estudios" in text or (href.lower().endswith(".pdf") and "ppee" in href.lower()):
            return normalize_pucp_url(urljoin(base_url, href))
    return None


def extract_eeggcc_pdf_url(html: str, base_url: str = "") -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.lower().endswith(".pdf") and "pe_" in href.lower():
            return normalize_pucp_url(urljoin(base_url, href))
    return None


def extract_sociales_pdf_url(html: str, base_url: str = "") -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.lower().endswith(".pdf"):
            full_url = normalize_pucp_url(urljoin(base_url, href))
            candidates.append(full_url)
    if not candidates:
        return None
    for c in reversed(candidates):
        if "plan" in c.lower():
            return c
    return candidates[-1]


def extract_artes_escenicas_pdf_url(html: str, base_url: str = "") -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    btn = soup.find("a", class_=lambda c: c and "download__btn" in c)
    if btn and btn.get("href"):
        return normalize_pucp_url(urljoin(base_url, btn["href"].strip()))
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.lower().split("?", 1)[0].endswith(".pdf"):
            return normalize_pucp_url(urljoin(base_url, href))
    return None


def extract_comunicacion_pdf_url(html: str, base_url: str = "") -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        text = _clean(a.get_text(" ", strip=True)).lower()
        parent_text = _clean(a.parent.get_text(" ", strip=True)).lower() if a.parent else ""
        if href.lower().split("?", 1)[0].endswith(".pdf"):
            if "aquí" in text or "aqui" in text or "plan de estudios" in parent_text:
                return normalize_pucp_url(urljoin(base_url, href))
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.lower().split("?", 1)[0].endswith(".pdf") and "plan" in href.lower():
            return normalize_pucp_url(urljoin(base_url, href))
    return None


def extract_comunicacion_pdf_courses(pdf_path: Path) -> list[PucpCourse]:
    try:
        txt = subprocess.check_output(
            ["pdftotext", "-layout", str(pdf_path), "-"],
            stderr=subprocess.DEVNULL,
        ).decode("utf-8", errors="ignore")
        return parse_comunicacion_pdf_text(txt)
    except Exception:
        return []


def parse_comunicacion_pdf_text(text: str) -> list[PucpCourse]:
    courses: list[PucpCourse] = []
    current_level = None
    level_regex = re.compile(r"^[….\s]*(QUINTO|SEXTO|S[EÉ]PTIMO|OCTAVO|NOVENO|D[EÉ]CIMO)\s+NIVEL", re.IGNORECASE)
    course_regex = re.compile(
        r"^\s*([0-9]?[A-Z]{3}[0-9]{2,3})?\s*([A-Za-zÁÉÍÓÚáéíóúñÑ][A-Za-zÁÉÍÓÚáéíóúñÑ0-9\s,\.\(\)\-]+?)\s+(\d+)\s+(\d+)",
        re.UNICODE,
    )

    for line in text.splitlines():
        line_clean = line.strip()
        m_level = level_regex.search(line_clean)
        if m_level:
            current_level = f"{m_level.group(1).capitalize()} Nivel"
            continue
        m_course = course_regex.match(line)
        if m_course and current_level:
            code = m_course.group(1).strip() if m_course.group(1) else None
            name = m_course.group(2).strip()
            if any(k in name.lower() for k in ["total", "crédito", "credito", "horas", "requisito", "detalle"]):
                continue
            credits_val = int(m_course.group(3))
            courses.append(
                PucpCourse(
                    name=name,
                    code=code,
                    credits=credits_val,
                    stage="Facultad de Ciencias y Artes de la Comunicación",
                    cycle=current_level,
                )
            )
    return _deduplicate(courses)


def parse_canva_courses(html: str, faculty_name: str = "Facultad de Letras y Ciencias Humanas") -> list[PucpCourse]:
    raw = re.findall(r"\"A\":\"([^\"]+)\"", html)
    cleaned = [s.replace("\\n", " ").replace("\\", "").strip() for s in raw]
    courses: list[PucpCourse] = []

    level_indices: list[tuple[int, str]] = []
    for i, s in enumerate(cleaned):
        m = re.search(r"\bNivel\s+(\d+)\b", s, re.IGNORECASE)
        if m and "sumilla" not in s.lower():
            level_indices.append((i, f"Nivel {m.group(1)}"))

    for idx, (pos, level_name) in enumerate(level_indices):
        end_pos = level_indices[idx + 1][0] if idx + 1 < len(level_indices) else len(cleaned)
        chunk = cleaned[pos:end_pos]

        codes = [s for s in chunk if re.match(r"^[0-9]?[A-Z]{3}[0-9]{2,3}$", s)]
        names: list[str] = []
        for s in chunk:
            if s.isupper() and len(s) > 3 and not re.match(r"^[0-9]?[A-Z]{3}[0-9]{2,3}$", s):
                if not any(
                    k in s
                    for k in [
                        "NIVEL",
                        "CÓDIGO",
                        "CODIGO",
                        "NOMBRE",
                        "HORAS",
                        "CRÉD",
                        "CRED",
                        "PRE REQUISITOS",
                        "REQUISITOS",
                        "VER SUMILLAS",
                        "ELECTIVO",
                        "M0 0H",
                        "SHADOW",
                    ]
                ):
                    names.append(s)

        paired_count = min(len(codes), len(names))
        for j in range(paired_count):
            courses.append(
                PucpCourse(
                    name=names[j].title(),
                    code=codes[j],
                    credits=None,
                    stage=faculty_name,
                    cycle=level_name,
                )
            )

    return _deduplicate(courses)




def extract_arquitectura_pdf_url(html: str, base_url: str = ARQUITECTURA_PLAN_URL) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href.lower().split("?", 1)[0].endswith(".pdf"):
            continue
        text = _clean(a.get_text(" ", strip=True)).lower()
        if "plan" in text or "estudios" in text or "malla" in text or "plan-de-estudios" in href.lower():
            return normalize_pucp_url(urljoin(base_url, href))
    return None


def normalize_pucp_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    # Si viene con http:// y pertenece a pucp.edu.pe, actualizar a https://
    if parsed.scheme == "http" and "pucp.edu.pe" in parsed.netloc:
        parsed = parsed._replace(scheme="https")
    return urlunparse(parsed)


def _rewrite_redirect_to_https(response: httpx.Response) -> None:
    if response.is_redirect and "location" in response.headers:
        loc = response.headers["location"]
        if loc.startswith("http://") and "pucp.edu.pe" in loc:
            response.headers["location"] = loc.replace("http://", "https://", 1)


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.lower()).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _deduplicate(courses: list[PucpCourse]) -> list[PucpCourse]:
    unique: dict[tuple[str, str | None, str | None], PucpCourse] = {}
    for course in courses:
        unique.setdefault((course.name, course.code, course.cycle), course)
    return list(unique.values())
