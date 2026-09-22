from university_scraper.pucp import (
    extract_arquitectura_courses,
    extract_arquitectura_pdf_url,
    extract_catalog_careers,
    normalize_pucp_url,
    slugify,
)


def test_extract_catalog_careers() -> None:
    html = """
    <h2>Facultad de Arquitectura y Urbanismo</h2>
    <div class="carreras">
      <ul class="lista">
        <li>
          <a class="eventShow" href="#">Arquitectura</a>
          <div class="bloque">
            <div class="mod-fac">Modalidad: Presencial</div>
            <p>Formación integral de arquitectos.</p>
            <div class="doc-btn"><a href="https://www.pucp.edu.pe/carrera/arquitectura/">Más información</a></div>
            <div class="btn-flecha-az"><a href="http://facultad.pucp.edu.pe/arquitectura/informacion-academica/plan-de-estudios/">Plan de Estudios</a></div>
          </div>
        </li>
      </ul>
    </div>
    <h2>Facultad de Derecho</h2>
    <div class="carreras">
      <ul class="lista">
        <li>
          <a class="eventShow" href="#">Derecho</a>
          <div class="bloque">
            <div class="mod-fac">Modalidad: Presencial</div>
            <div class="doc-btn"><a href="https://www.pucp.edu.pe/carrera/derecho/">Más información</a></div>
            <div class="btn-flecha-az"><a href="https://facultad-derecho.pucp.edu.pe/estudiantes/plan-de-estudios/">Plan de Estudios</a></div>
          </div>
        </li>
      </ul>
    </div>
    """
    careers = extract_catalog_careers(html)
    assert len(careers) == 2
    arq = careers[0]
    assert arq.name == "Arquitectura"
    assert arq.faculty == "Facultad de Arquitectura y Urbanismo"
    assert arq.modality == "Modalidad: Presencial"
    assert arq.description == "Formación integral de arquitectos."
    assert arq.career_url == "https://www.pucp.edu.pe/carrera/arquitectura/"
    assert arq.plan_url == "https://facultad.pucp.edu.pe/arquitectura/informacion-academica/plan-de-estudios/"

    der = careers[1]
    assert der.name == "Derecho"
    assert der.faculty == "Facultad de Derecho"
    assert der.plan_url == "https://facultad-derecho.pucp.edu.pe/estudiantes/plan-de-estudios/"


def test_extract_arquitectura_courses_three_stages() -> None:
    html = """
    <div class="panel-group" id="accordion">
      <div class="panel panel-default">
        <div class="panel-heading" id="heading-1">
          <h3 class="panel-title">Formación General</h3>
        </div>
        <div id="collapse-1" class="panel-collapse">
          <div class="row">
            <div class="col-xs-12 col-sm-3 plan">
              <div class="hd">Nivel 1</div>
              <div class="td">
                <h2><a href="/cursos/taller-1">Taller 1</a></h2>
                <span><a href="/cursos/?codcurso=1ARC58">1ARC58</a> / 8 Créditos</span>
              </div>
              <div class="td">
                <h2><a href="/cursos/representacion-1">Representación 1</a></h2>
                <span><a href="/cursos/?codcurso=1ARC52">1ARC52</a> / 3 Créditos</span>
              </div>
              <div class="td total">
                <h2>TOTAL DE CRÉDITOS</h2>
                <span>11 Créditos</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="panel panel-default">
        <div class="panel-heading" id="heading-2">
          <h3 class="panel-title">Nivel de profundización</h3>
        </div>
        <div id="collapse-2" class="panel-collapse">
          <div class="row">
            <div class="col-xs-12 col-sm-3 plan">
              <div class="hd">Nivel 5</div>
              <div class="td">
                <h2><a href="/cursos/taller-5">Taller 5</a></h2>
                <span><a href="/cursos/?codcurso=ARC225">ARC225</a> / 8 Créditos</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="panel panel-default">
        <div class="panel-heading" id="heading-3">
          <h3 class="panel-title">Nivel Avanzado</h3>
        </div>
        <div id="collapse-3" class="panel-collapse">
          <div class="row">
            <div class="col-xs-12 col-sm-3 plan">
              <div class="hd">Nivel 10</div>
              <div class="td">
                <h2><a href="/cursos/taller-9">Taller 9</a></h2>
                <span><a href="/cursos/?codcurso=1ARC71">1ARC71</a> / 11 Créditos</span>
              </div>
              <div class="td">
                <h2>Electivo-Obligatorio (EOB)</h2>
                <span>2 Créditos</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
    """
    courses = extract_arquitectura_courses(html, base_url="https://arquitectura.pucp.edu.pe/estudios/pregrado/plan-de-estudios/")
    assert len(courses) == 5

    # Cursos de Formación General
    assert courses[0].name == "Taller 1"
    assert courses[0].code == "1ARC58"
    assert courses[0].credits == 8
    assert courses[0].stage == "Formación General"
    assert courses[0].cycle == "Nivel 1"
    assert courses[0].url == "https://arquitectura.pucp.edu.pe/cursos/taller-1"

    assert courses[1].name == "Representación 1"
    assert courses[1].code == "1ARC52"
    assert courses[1].credits == 3
    assert courses[1].stage == "Formación General"

    # Curso de Nivel de profundización
    assert courses[2].name == "Taller 5"
    assert courses[2].code == "ARC225"
    assert courses[2].credits == 8
    assert courses[2].stage == "Nivel de profundización"
    assert courses[2].cycle == "Nivel 5"

    # Cursos de Nivel Avanzado
    assert courses[3].name == "Taller 9"
    assert courses[3].code == "1ARC71"
    assert courses[3].credits == 11
    assert courses[3].stage == "Nivel Avanzado"
    assert courses[3].cycle == "Nivel 10"

    assert courses[4].name == "Electivo-Obligatorio (EOB)"
    assert courses[4].code is None
    assert courses[4].credits == 2
    assert courses[4].stage == "Nivel Avanzado"


def test_extract_arquitectura_pdf_url() -> None:
    html = """
    <div>
      <a href="https://arquitectura.pucp.edu.pe/wp-content/uploads/2026/05/Plan-de-Estudios-2026-1.pdf" target="_blank">
        Plan de estudios completo
      </a>
      <a href="https://ejemplo.com/otro.pdf">Otro documento</a>
    </div>
    """
    pdf_url = extract_arquitectura_pdf_url(html)
    assert pdf_url == "https://arquitectura.pucp.edu.pe/wp-content/uploads/2026/05/Plan-de-Estudios-2026-1.pdf"


def test_normalize_pucp_url_and_slugify() -> None:
    assert normalize_pucp_url("http://facultad.pucp.edu.pe/arquitectura/") == "https://facultad.pucp.edu.pe/arquitectura/"
    assert normalize_pucp_url("https://facultad.pucp.edu.pe/arquitectura/") == "https://facultad.pucp.edu.pe/arquitectura/"
    assert slugify("Facultad de Arquitectura y Urbanismo") == "facultad-de-arquitectura-y-urbanismo"


def test_extract_arte_diseno_courses() -> None:
    html = """
    <table role="table">
      <thead>
        <tr>
          <th>Nivel 1</th>
          <th>Nivel 2</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td><p>Introducción al Dibujo (4 cr.)</p></td>
          <td><p>Figura Humana (4 cr.)</p></td>
        </tr>
        <tr>
          <td><p>Lenguaje Visual 1 (5 cr.)</p></td>
          <td><p>-</p></td>
        </tr>
      </tbody>
    </table>
    <table role="table">
      <thead>
        <tr>
          <th>Nivel 3</th>
          <th>Nivel 4</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td><p>Visualidad y Textualidad (2 cr.)</p></td>
          <td><p>Idiomas Arte 1 (0 cr.)</p></td>
        </tr>
      </tbody>
    </table>
    """
    from university_scraper.pucp import extract_arte_diseno_courses

    courses = extract_arte_diseno_courses(html)
    assert len(courses) == 5
    assert courses[0].name == "Introducción al Dibujo"
    assert courses[0].credits == 4
    assert courses[0].cycle == "Nivel 1"

    assert courses[1].name == "Figura Humana"
    assert courses[1].credits == 4
    assert courses[1].cycle == "Nivel 2"

    assert courses[2].name == "Lenguaje Visual 1"
    assert courses[2].credits == 5
    assert courses[2].cycle == "Nivel 1"

    assert courses[3].name == "Visualidad y Textualidad"
    assert courses[3].credits == 2
    assert courses[3].cycle == "Nivel 3"

    assert courses[4].name == "Idiomas Arte 1"
    assert courses[4].credits == 0
    assert courses[4].cycle == "Nivel 4"


def test_extract_eeggcc_courses() -> None:
    html = """
    <div>
      <h5>Nivel 1</h5>
      <a class="link-item-curso" href="/curso/calculo-1/">Cálculo 1</a>
      <a class="link-item-curso" href="/curso/fisica-1/">Física 1</a>
      <h5>Nivel 2</h5>
      <a class="link-item-curso" href="/curso/calculo-2/">Cálculo 2</a>
    </div>
    """
    from university_scraper.pucp import extract_eeggcc_courses

    courses = extract_eeggcc_courses(html, base_url="https://estudios-generales-ciencias.pucp.edu.pe")
    assert len(courses) == 3
    assert courses[0].name == "Cálculo 1"
    assert courses[0].cycle == "Nivel 1"
    assert courses[0].stage == "Estudios Generales Ciencias"
    assert courses[0].url == "https://estudios-generales-ciencias.pucp.edu.pe/curso/calculo-1/"

    assert courses[1].name == "Física 1"
    assert courses[1].cycle == "Nivel 1"

    assert courses[2].name == "Cálculo 2"
    assert courses[2].cycle == "Nivel 2"


def test_extract_ciencias_ingenieria_pdfs() -> None:
    from university_scraper.pucp import extract_eeggcc_pdf_url, extract_fci_pdf_url

    fci_html = """
    <div>
      <a href="https://facultad-ciencias-ingenieria.pucp.edu.pe/wp-content/uploads/2026/07/INDUSTRIAL_ppee_FCI-2026-2.pdf">
        Descargar plan de estudios
      </a>
    </div>
    """
    assert (
        extract_fci_pdf_url(fci_html)
        == "https://facultad-ciencias-ingenieria.pucp.edu.pe/wp-content/uploads/2026/07/INDUSTRIAL_ppee_FCI-2026-2.pdf"
    )

    eeggcc_html = """
    <div>
      <a href="https://estudios-generales-ciencias.pucp.edu.pe/wp-content/uploads/2026/07/PE_Industrial_26.pdf">
        descarga el plan
      </a>
    </div>
    """
    assert (
        extract_eeggcc_pdf_url(eeggcc_html)
        == "https://estudios-generales-ciencias.pucp.edu.pe/wp-content/uploads/2026/07/PE_Industrial_26.pdf"
    )


def test_extract_sociales_pdf_url() -> None:
    from university_scraper.pucp import extract_sociales_pdf_url

    html = """
    <div>
      <a href="https://facultad-ciencias-sociales.pucp.edu.pe/wp-content/uploads/2026/04/Plan-de-estudios-Economia-vf-08-abril-2026.docx.pdf">
        Descargar Plan de Estudios
      </a>
    </div>
    """
    assert (
        extract_sociales_pdf_url(html)
        == "https://facultad-ciencias-sociales.pucp.edu.pe/wp-content/uploads/2026/04/Plan-de-estudios-Economia-vf-08-abril-2026.docx.pdf"
    )


def test_extract_artes_escenicas_pdf_url_button() -> None:
    from university_scraper.pucp import extract_artes_escenicas_pdf_url

    html = """
    <div>
      <h2 class="download__title">Descarga el archivo completo de la malla curricular</h2>
      <a class="btn tipo-relleno download__btn" href="https://facultad-artes-escenicas.pucp.edu.pe/wp-content/uploads/2026/04/DANZA_PLAN-DE-ESTUDIOS.pdf" target="_blank">Descargar</a>
    </div>
    """
    assert (
        extract_artes_escenicas_pdf_url(html)
        == "https://facultad-artes-escenicas.pucp.edu.pe/wp-content/uploads/2026/04/DANZA_PLAN-DE-ESTUDIOS.pdf"
    )


def test_extract_artes_escenicas_pdf_url_fallback() -> None:
    from university_scraper.pucp import extract_artes_escenicas_pdf_url

    html = """
    <div>
      <a href="/wp-content/uploads/2026/04/CREPO_PLAN-DE-ESTUDIOS-1.pdf">Malla Curricular PDF</a>
    </div>
    """
    assert (
        extract_artes_escenicas_pdf_url(html, base_url="https://facultad-artes-escenicas.pucp.edu.pe")
        == "https://facultad-artes-escenicas.pucp.edu.pe/wp-content/uploads/2026/04/CREPO_PLAN-DE-ESTUDIOS-1.pdf"
    )


def test_extract_comunicacion_pdf_url() -> None:
    from university_scraper.pucp import extract_comunicacion_pdf_url

    html = """
    <div>
      <p>También puedes visualizar el Plan de Estudios de Comunicación Audiovisual <a href="https://facultad.pucp.edu.pe/comunicaciones/wp-content/uploads/2026/07/Nuevo-Plan-de-Estudios-Comunicacion-Audiovisual-desde-el-2025-1.pdf">aquí.</a></p>
    </div>
    """
    assert (
        extract_comunicacion_pdf_url(html)
        == "https://facultad.pucp.edu.pe/comunicaciones/wp-content/uploads/2026/07/Nuevo-Plan-de-Estudios-Comunicacion-Audiovisual-desde-el-2025-1.pdf"
    )


def test_parse_comunicacion_pdf_text() -> None:
    from university_scraper.pucp import parse_comunicacion_pdf_text

    text = """
    ……….QUINTO NIVEL
    CCO202 Teorías de la Comunicación 3 3 2 OC Sin requisito
    CCO203 Lenguaje de los Medios 4 4 2 OC Sin requisito
    1CCO19 Pensamiento Computacional para Comunicaciones 2 1 2 OC Sin requisito
    ……….SEXTO NIVEL
    CCO221 Métodos y Técnicas de Investigación 1 4 3 2 OC CCO202
    """
    courses = parse_comunicacion_pdf_text(text)
    assert len(courses) == 4
    assert courses[0].code == "CCO202"
    assert courses[0].name == "Teorías de la Comunicación"
    assert courses[0].credits == 3
    assert courses[0].cycle == "Quinto Nivel"
    assert courses[0].stage == "Facultad de Ciencias y Artes de la Comunicación"

    assert courses[2].code == "1CCO19"
    assert courses[2].name == "Pensamiento Computacional para Comunicaciones"
    assert courses[2].credits == 2

    assert courses[3].code == "CCO221"
    assert courses[3].cycle == "Sexto Nivel"


def test_parse_canva_courses() -> None:
    from university_scraper.pucp import parse_canva_courses

    sample_html = """
    {"A":"Nivel 5\\n"},{"A":"Código\\n"},{"A":"FIL205\\n"},{"A":"FIL219\\n"},
    {"A":"METAFÍSICA\\n"},{"A":"FILOSOFÍA MEDIEVAL\\n"},
    {"A":"Nivel 6\\n"},{"A":"FIL206\\n"},{"A":"TEORÍA DEL CONOCIMIENTO\\n"}
    """
    courses = parse_canva_courses(sample_html)
    assert len(courses) == 3
    assert courses[0].code == "FIL205"
    assert courses[0].name == "Metafísica"
    assert courses[0].cycle == "Nivel 5"

    assert courses[1].code == "FIL219"
    assert courses[1].name == "Filosofía Medieval"
    assert courses[1].cycle == "Nivel 5"

    assert courses[2].code == "FIL206"
    assert courses[2].name == "Teoría Del Conocimiento"
    assert courses[2].cycle == "Nivel 6"


def test_download_ciencias_contables_mock(tmp_path: Path) -> None:
    from university_scraper.pucp import PucpCurriculumDownloader, PucpCareer
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "plan-de-estudios" in url:
            return httpx.Response(200, text="<html><title>Plan Contabilidad</title></html>")
        if "drive.google.com" in url or "estudios-generales-letras" in url:
            return httpx.Response(200, content=b"%PDF-1.4 mock pdf content")
        return httpx.Response(200, text="ok")

    downloader = PucpCurriculumDownloader(output_dir=tmp_path)
    downloader.client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        mock_careers = [
            PucpCareer(
                name="Contabilidad",
                faculty="Facultad de Ciencias Contables",
                career_url="https://www.pucp.edu.pe/carrera/contabilidad/",
                plan_url="https://facultad.pucp.edu.pe/ciencias-contables/informacion-academica/plan-de-estudios/",
            )
        ]
        res = downloader.download_ciencias_contables(careers=mock_careers, download_pdf=True)
        assert res["faculty"] == "Facultad de Ciencias Contables"
        assert res["career_count"] == 1
        career_dir = tmp_path / "contabilidad"
        assert (career_dir / "source.html").exists()
        assert (career_dir / "plan-estudios.pdf").exists()
        assert (career_dir / "plan-estudios-eeggll.pdf").exists()
        assert (career_dir / "metadata.json").exists()
    finally:
        downloader.close()






