from university_scraper.ulima import extract_careers, slugify


def test_extract_ulima_careers_from_malla_links() -> None:
    html = """
    <section><h3>Administración</h3><a href="/sites/default/files/malla_administracion.pdf">Descargar malla</a></section>
    <section><h3>Ingeniería Industrial</h3><a href="https://www.ulima.edu.pe/sites/default/files/malla_industrial.pdf">DESCARGAR MALLA</a></section>
    <a href="/politica.pdf">Política de privacidad</a>
    """
    careers = extract_careers(html)
    assert [(career.name, career.pdf_url) for career in careers] == [
        ("Administración", "https://www.ulima.edu.pe/sites/default/files/malla_administracion.pdf"),
        ("Ingeniería Industrial", "https://www.ulima.edu.pe/sites/default/files/malla_industrial.pdf"),
    ]


def test_slugify_ulima_career_name() -> None:
    assert slugify("Ingeniería Industrial") == "ingenieria-industrial"