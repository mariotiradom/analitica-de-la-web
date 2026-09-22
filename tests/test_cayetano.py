from university_scraper.cayetano import extract_careers, extract_courses


def test_extract_cayetano_careers_from_all_careers_listing() -> None:
    html = """
    <main>
      <a href="/pregrado/carreras/ingenieria-informatica/"><h3>Ingeniería Informática</h3></a>
      <a href="/pregrado/carreras/medicina/">Medicina</a>
      <a href="/pregrado/carreras/area/salud/">Salud</a>
      <a href="/pregrado/carreras/?query-0-page=2">Página siguiente</a>
    </main>
    """
    careers = extract_careers(html)
    assert [(career.name, career.url) for career in careers] == [
        ("Ingeniería Informática", "https://cayetano.edu.pe/pregrado/carreras/ingenieria-informatica"),
        ("Medicina", "https://cayetano.edu.pe/pregrado/carreras/medicina"),
    ]


def test_extract_cayetano_courses_by_cycle_and_modality() -> None:
    html = """
    <section id="malla-curricular">
      <div class="wp-block-getwid-content-slider-slide">
        <p>CICLO</p><p><strong>1</strong></p>
        <ul><li>COMUNICACIÓN (NP)</li><li>CÁLCULO (P)</li></ul>
      </div>
    </section>
    """
    courses = extract_courses(html)
    assert [(course.name, course.cycle, course.modality) for course in courses] == [
        ("COMUNICACIÓN", "Ciclo 1", "NP"),
        ("CÁLCULO", "Ciclo 1", "P"),
    ]