import asyncio
import re
from urllib.parse import urljoin
import pandas as pd
from playwright.async_api import async_playwright

URL_BUSQUEDA = 'https://pe.computrabajo.com/empleos-en-lima'
LIMITE_EXTRACCION = None  # número de ofertas a extraer; None = todas las de la página

# Encabezados tal como aparecen en la página de detalle (ver imagen de referencia)
PATRON_HEADING_DESCRIPCION = re.compile(r'Descripci[oó]n de la oferta', re.IGNORECASE)
PATRON_HEADING_REQUISITOS = re.compile(r'Requerimientos|Requisitos', re.IGNORECASE)
PATRON_HEADING_CORTE_FINAL = re.compile(r'Postularme|Denunciar empleo|Compartir', re.IGNORECASE)

PATRON_SALARIO = re.compile(
    r'S/\.?\s?[\d][\d.,]*(?:\s*(?:a|-|hasta)\s*S/\.?\s?[\d][\d.,]*)?', re.IGNORECASE
)
PATRON_MODALIDAD = re.compile(r'\b(Remoto|Presencial|H[ií]brido|Semipresencial)\b', re.IGNORECASE)


def dividir_bloques(texto_completo: str, titulo: str) -> dict:
    """
    Divide el texto completo de la página de detalle en tres bloques,
    replicando el orden visual que se ve en la oferta:
      1. resumen      -> entre el título y "Descripción de la oferta"
      2. descripcion  -> entre "Descripción de la oferta" y "Requerimientos"/"Requisitos"
      3. requisitos   -> entre "Requerimientos"/"Requisitos" y el siguiente corte (Postularme, etc.)
    """
    resumen, descripcion, requisitos = "", "", ""

    idx_titulo = texto_completo.find(titulo) if titulo else -1
    match_desc = PATRON_HEADING_DESCRIPCION.search(texto_completo)
    match_req = PATRON_HEADING_REQUISITOS.search(
        texto_completo, match_desc.end() if match_desc else 0
    )

    # --- Bloque RESUMEN: desde el final del título hasta el heading de Descripción ---
    if idx_titulo != -1 and match_desc:
        inicio = idx_titulo + len(titulo)
        resumen = texto_completo[inicio:match_desc.start()].strip()
    elif match_desc:
        resumen = texto_completo[:match_desc.start()].strip()

    # --- Bloque DESCRIPCIÓN: desde el final del heading de Descripción hasta Requerimientos ---
    if match_desc:
        fin_desc = match_req.start() if match_req else len(texto_completo)
        descripcion = texto_completo[match_desc.end():fin_desc].strip()

    # --- Bloque REQUISITOS: desde el final del heading de Requerimientos hasta el próximo corte ---
    if match_req:
        resto = texto_completo[match_req.end():]
        corte = PATRON_HEADING_CORTE_FINAL.search(resto)
        requisitos = resto[:corte.start()].strip() if corte else resto.strip()

    return {"resumen": resumen, "descripcion": descripcion, "requisitos": requisitos}


def buscar_con_prioridad(patron: re.Pattern, *bloques: str):
    """Busca 'patron' primero en el bloque de Resumen, y si no aparece, en Descripción."""
    for bloque in bloques:
        if not bloque:
            continue
        encontrado = patron.search(bloque)
        if encontrado:
            return encontrado.group(0).strip()
    return None


async def extraer_empleos():
    resultados = []

    async with async_playwright() as p:
        # Contexto persistente: guarda cookies/sesión en la carpeta "perfil_computrabajo"
        context = await p.chromium.launch_persistent_context(
            user_data_dir="./perfil_computrabajo",
            headless=False,
            args=['--start-maximized'],
            no_viewport=True
        )

        page = context.pages[0] if len(context.pages) > 0 else await context.new_page()

        print("Navegando a la página de búsquedas de Computrabajo...")
        await page.goto(URL_BUSQUEDA)

        print("⏳ Esperando 5 segundos por si aparece un aviso de cookies...")
        await page.wait_for_timeout(5000)

        try:
            boton_cookies = page.locator('text=Aceptar')
            if await boton_cookies.count() > 0:
                await boton_cookies.first.click(timeout=3000)
                print("✓ Banner de cookies cerrado.")
        except Exception:
            pass

        # Confirmado en el HTML real de la página: cada oferta está en <article class="box_offer ...">
        tarjetas = page.locator('article.box_offer')
        cantidad_tarjetas = await tarjetas.count()
        print(f"Encontradas {cantidad_tarjetas} ofertas de trabajo en el listado.")

        limite = cantidad_tarjetas if LIMITE_EXTRACCION is None else min(LIMITE_EXTRACCION, cantidad_tarjetas)
        print(f"Se extraerán {limite} ofertas.\n")

        # --- 1. Recolectamos los links del LISTADO primero ---
        urls_empleos = []
        for i in range(limite):
            tarjeta = tarjetas.nth(i)
            enlace_bruto = await tarjeta.locator('h2 a.js-o-link, a.js-o-link').first.get_attribute('href')
            if enlace_bruto:
                urls_empleos.append(urljoin('https://pe.computrabajo.com', enlace_bruto))

        # --- 2. Visitamos cada oferta y extraemos los datos ---
        for i, url_empleo in enumerate(urls_empleos):
            print(f"[{i+1}/{len(urls_empleos)}] Extrayendo datos de: {url_empleo}")

            page_empleo = await context.new_page()
            await page_empleo.goto(url_empleo)

            try:
                await page_empleo.wait_for_selector('h1', timeout=8000)
            except Exception:
                print("⚠️ La página tardó en cargar. Tienes 20 segundos por si aparece alguna verificación...")
                try:
                    await page_empleo.wait_for_selector('h1', timeout=20000)
                    print("✅ Contenido cargado. Continuando extracción...")
                except Exception:
                    print(f"❌ No cargó a tiempo. Guardando error_empleo_{i+1}.png")
                    await page_empleo.screenshot(path=f"error_empleo_{i+1}.png")
                    await page_empleo.close()
                    continue

            # --- Título (siempre en el h1, arriba del bloque de Resumen) ---
            try:
                titulo = (await page_empleo.locator('h1').first.inner_text()).strip()
            except Exception:
                titulo = "No especificado"

            # --- Texto completo de la página, para segmentar por encabezados ---
            texto_completo = await page_empleo.locator('body').inner_text()
            bloques = dividir_bloques(texto_completo, titulo)

            # --- Descripción: directamente el bloque "Descripción de la oferta" ---
            descripcion = bloques["descripcion"] or "No especificado"

            # --- Requisitos: prioridad al bloque "Requerimientos"; si no hay, se busca
            #     dentro de la Descripción cualquier línea relacionada con requisitos ---
            requisitos = bloques["requisitos"]
            if not requisitos:
                match_req_en_desc = re.search(
                    r'(requisitos?[^\n]*\n(?:.+\n?)*)', bloques["descripcion"], re.IGNORECASE
                )
                requisitos = match_req_en_desc.group(1).strip() if match_req_en_desc else None
            requisitos = requisitos or "No especificado"

            # --- Salario: primero en Resumen, luego en Descripción ---
            salario = buscar_con_prioridad(PATRON_SALARIO, bloques["resumen"], bloques["descripcion"])
            salario = salario or "No especificado"

            # --- Modalidad: primero en Resumen, luego en Descripción ---
            modalidad = buscar_con_prioridad(PATRON_MODALIDAD, bloques["resumen"], bloques["descripcion"])
            modalidad = modalidad or "No especificado"

            # --- Ubicación: fija, como se pidió ---
            ubicacion = "Lima, Perú"

            resultados.append({
                "titulo": titulo,
                "descripcion": descripcion,
                "requisitos": requisitos,
                "salario": salario,
                "ubicacion": ubicacion,
                "modalidad": modalidad,
                "url": url_empleo,
            })

            print(f"✓ Datos extraídos con éxito: {titulo}")

            await page_empleo.close()
            await page.wait_for_timeout(3000)

        await context.close()

    return resultados


def construir_dataframe(resultados: list) -> pd.DataFrame:
    """Convierte la lista de diccionarios en un DataFrame."""
    df = pd.DataFrame(resultados)
    return df


def exportar_a_excel(df: pd.DataFrame, ruta: str = "empleos_computrabajo.xlsx"):
    """Exporta el DataFrame a un archivo Excel (.xlsx)."""
    df.to_excel(ruta, index=False)
    print(f"📊 Datos exportados a: {ruta}")


if __name__ == '__main__':
    resultados = asyncio.run(extraer_empleos())

    print("\n=== RESULTADOS FINALES ===")
    for emp in resultados:
        print(f"Título: {emp['titulo']}")
        print(f"Ubicación: {emp['ubicacion']}")
        print(f"Modalidad: {emp['modalidad']}")
        print(f"Salario: {emp['salario']}")
        print(f"Requisitos: {emp['requisitos'][:200]}")
        print(f"Descripción: {emp['descripcion'][:200]}...")
        print(f"URL: {emp['url']}")
        print("-" * 40)

    df_final = construir_dataframe(resultados)
    print("\nVista previa de la tabla:")
    print(df_final.head())

    exportar_a_excel(df_final)