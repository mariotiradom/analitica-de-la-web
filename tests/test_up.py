from university_scraper.up import extract_careers, extract_courses, slugify


def test_extract_up_courses_by_cycle() -> None:
    html = """
    <section><div class="wp-acordeon"><ul class="collapsible">
      <li><div class="collapsible-header">Ciclo I</div><div class="collapsible-body">
        <ul><li>Matemáticas I</li><li>Programación</li></ul>
      </div></li>
      <li><div class="collapsible-header">Ciclo II</div><div class="collapsible-body">
        <ul><li>Estadística</li></ul>
      </div></li>
    </ul></div></section>
    """
    courses = extract_courses(html)
    assert [(course.name, course.cycle) for course in courses] == [
        ("Matemáticas I", "Ciclo I"),
        ("Programación", "Ciclo I"),
        ("Estadística", "Ciclo II"),
    ]


def test_extract_up_careers_and_plan_urls() -> None:
    html = """
    <nav>
      <a href="/carreras-postgrado-idiomas/carreras-pregrado/administracion">Administración</a>
      <a href="/carreras-postgrado-idiomas/carreras-pregrado/ingenieriainformacion">Ingeniería de la Información</a>
      <a href="/carreras-postgrado-idiomas/carreras-pregrado/administracion/Paginas/plan-estudios.aspx">Cursos</a>
      <a href="/otra-seccion/">No es carrera</a>
    </nav>
    """
    careers = extract_careers(html)
    assert [(career.name, career.plan_url) for career in careers] == [
        ("Administración", "https://www.up.edu.pe/carreras-postgrado-idiomas/carreras-pregrado/administracion/Paginas/plan-estudios.aspx"),
        ("Ingeniería de la Información", "https://www.up.edu.pe/carreras-postgrado-idiomas/carreras-pregrado/ingenieriainformacion/Paginas/plan-estudios.aspx"),
    ]


def test_slugify_career_name() -> None:
    assert slugify("Ingeniería de la Información") == "ingenieria-de-la-informacion"
