from university_scraper.utec import extract_courses


def test_extract_courses_from_curriculum_section() -> None:
    html = """
    <section><h2>Malla Curricular de la carrera</h2>
      <ul><li><p>Ciclo 1</p><ul>
        <li><h5>Fundamentos del Cálculo</h5><span>3 créditos</span></li>
        <li><h5>Programación I</h5><span>4 créditos</span></li>
        <li><h5>Programación II</h5><span>4 créditos</span><div>Prerrequisito: Programación I</div></li>
      </ul></li></ul>
    </section>
    """
    courses = extract_courses(html)
    assert [course.name for course in courses] == [
        "Fundamentos del Cálculo", "Programación I", "Programación II"
    ]
    assert courses[-1].prerequisite == "Programación I"
    assert courses[-1].cycle == "Ciclo 1"
