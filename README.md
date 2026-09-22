# University Curriculum Scraper

Coleccion de scrapers reproducibles para mallas curriculares universitarias del Peru. El proyecto conserva HTML, PDF y metadatos de captura cuando la fuente los publica, para que los resultados puedan auditarse y procesarse despues con NLP y LLM.

## Universidades

- Universidad Tecnologica del Peru (UTEC): cursos publicados en HTML.
- Universidad del Pacifico (UP): planes publicados en HTML y PDF.
- Universidad Peruana Cayetano Heredia (UPCH): mallas publicadas en HTML.
- Universidad de Lima (Ulima): mallas publicadas en PDF.
- Pontificia Universidad Catolica del Peru (PUCP): catalogo por facultades. Soporta Arquitectura y Urbanismo (HTML por etapas y PDF), Arte y Diseño (tablas semestrales en HTML), Ciencias e Ingeniería (híbrido HTML EEGGCC + PDFs oficiales), Ciencias Sociales (PDFs oficiales por carrera), Artes Escénicas (FARES, PDFs oficiales por carrera y mención), Ciencias y Artes de la Comunicación (híbrido EEGGLL + PDFs vectoriales oficiales e imágenes), Letras y Ciencias Humanas (híbrido EEGGLL + HTML interactivo de facultad desde nivel 5) y Ciencias Contables (híbrido EEGGLL + vector PDF y gráficos oficiales de planes 2021 y 2026).

## Instalacion

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

## Uso

Cada comando descarga la fuente oficial y escribe resultados bajo `data/`:

```bash
utec-download-curriculum
up-download-study-plan --all
cayetano-download-curriculum
ulima-download-curriculum
pucp-download-curriculum --faculty arquitectura
pucp-download-curriculum --faculty "arte y diseño"
pucp-download-curriculum --faculty "artes escénicas"
pucp-download-curriculum --faculty "ciencias y artes de la comunicación"
pucp-download-curriculum --faculty "letras y ciencias humanas"
pucp-download-curriculum --faculty "ciencias contables"
pucp-download-curriculum --faculty "ciencias sociales"
pucp-download-curriculum --faculty "ciencias e ingeniería"
```

Las URLs y selectores de cada universidad se mantienen en su modulo correspondiente dentro de `src/university_scraper/`. Los datos generados incluyen metadatos de fecha, URL de origen y conteos; los archivos grandes y HTML crudo quedan ignorados por Git para facilitar una primera publicacion del codigo.

## Desarrollo

```bash
python -m pytest -q
```

La etapa de clasificacion de skills no forma parte de estos scrapers. Primero se preservan nombres, cursos y documentos originales; despues puede añadirse normalizacion NLP, matching con taxonomias y clasificacion asistida por LLM con validacion manual.

## Estructura

```text
src/university_scraper/
  cayetano.py       # catalogo general y mallas HTML de UPCH
  pucp.py           # catalogo general y mallas de la PUCP por facultad
  ulima.py          # catalogo y descarga de mallas PDF de Ulima
  up.py             # catalogo y planes de estudio de la UP
  utec.py           # malla de UTEC

tests/              # pruebas unitarias de los extractores
data/               # resultados locales de las capturas
```

## Alcance y uso responsable

Las fuentes son sitios institucionales publicos. Antes de ejecutar una captura, revisa los terminos de uso, la politica de acceso y la frecuencia de solicitudes de cada sitio. El repositorio no incluye credenciales ni datos personales.
