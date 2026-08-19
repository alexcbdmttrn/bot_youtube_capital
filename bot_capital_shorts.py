import asyncio
from datetime import datetime
import json
import os
import random
import re
import sys
import time
import numpy as np
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from moviepy.editor import (
    AudioFileClip,
    CompositeAudioClip,
    ImageClip,
    concatenate_audioclips,
    concatenate_videoclips,
    AudioClip,
)
from PIL import Image, ImageOps, ImageDraw, ImageFont
import requests
import edge_tts
import pytz

# ================================================================
# CONFIGURACIÓN
# ================================================================
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
AGNES_API_KEY = os.getenv("AGNES_API_KEY")
YOUTUBE_USER_TOKEN = (
    json.loads(os.getenv("YOUTUBE_USER_TOKEN_CAPITAL"))
    if os.getenv("YOUTUBE_USER_TOKEN_CAPITAL")
    else {}
)
NEWSAPI_KEY = "4b320804dea242198b35a93c9374ed6e"
CANAL_LINK = "https://www.youtube.com/@CapitalDigitalInversiones"
ESTADO_FILE = "estado_capital_shorts.json"
TITULOS_FILE = "titulos_capital_shorts_publicados.json"
TEMAS_PUBLICADOS_FILE = "temas_publicados.json"
META_DIARIA_SHORTS = 3
DIAS_SIN_REPETIR_TEMA = 30

# ================================================================
# VOZ FIJA (Jorge)
# ================================================================
VOZ_FIJA = {"voz": "es-MX-JorgeNeural", "velocidad": "+8%", "tono": "-1Hz", "nombre": "Jorge (MX)"}
CONFIG_VOZ_ACTUAL = VOZ_FIJA

# ================================================================
# MÚSICA CORPORATE
# ================================================================
FONDOS_DISPONIBLES = [
    "The Ascent.mp3",
    "Binary Pulse.mp3",
    "Peak Momentum.mp3",
    "Forward Momentum.mp3"
]

def seleccionar_fondo_disponible(estado):
    fondos_disponibles = []
    for root, dirs, files in os.walk("."):
        if "/." in root or "\\." in root:
            continue
        for file in files:
            if file.lower() in [f.lower() for f in FONDOS_DISPONIBLES]:
                fondos_disponibles.append(os.path.join(root, file))
    if not fondos_disponibles:
        print("ℹ️ No se encontró música. Continuando sin fondo musical.")
        return None
    ultimo_fondo = estado.get("ultimo_fondo")
    if ultimo_fondo and ultimo_fondo in fondos_disponibles:
        fondos_disponibles.remove(ultimo_fondo)
    seleccionada = random.choice(fondos_disponibles) if fondos_disponibles else random.choice(FONDOS_DISPONIBLES)
    estado["ultimo_fondo"] = seleccionada
    print(f"🎵 Música seleccionada: {os.path.basename(seleccionada)}")
    return seleccionada

# ================================================================
# PALETAS Y ESTILOS VISUALES
# ================================================================
PALETAS_BASE = [
    "Corporate blue and silver, modern office",
    "Dark emerald and gold, financial district",
    "Slate gray and cyan, trading floor",
    "Deep navy and amber, executive office",
    "Muted teal and white, fintech office",
    "Black and gold, Wall Street style",
    "Steel blue and silver, high-tech trading",
]
PALETA_BASE_ACTUAL = random.choice(PALETAS_BASE)

COLORES_NEON = [
    "electric cyan neon glow",
    "neon magenta pulse",
    "vivid lime green neon",
    "hot pink neon reflection",
    "neon orange highlight",
    "electric purple neon aura",
    "neon blue-white flash"
]
COLOR_NEON_ACTUAL = random.choice(COLORES_NEON)

# ================================================================
# HASHTAGS ESTRATÉGICOS
# ================================================================
HASHTAGS_ALTO_VOLUMEN = ["#Finanzas", "#Inversiones", "#Bitcoin", "#Economia", "#Oro", "#Bancos"]
HASHTAGS_MEDIO_VOLUMEN = ["#CriptoHoy", "#OroInversion", "#EducacionFinanciera", "#MercadoFinanciero", "#Ahorros"]
HASHTAGS_BAJO_VOLUMEN = ["#ETFMexico", "#SegurosDeVida", "#ExchangeSeguro", "#CrisisFinanciera", "#FinanzasPersonalesMX"]

# ================================================================
# FUNCIONES DE ESTADO
# ================================================================
def cargar_estado():
    try:
        with open(ESTADO_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "publicaciones_hoy" not in data:
                data["publicaciones_hoy"] = None
            return data
    except:
        return {"ultimo_fondo": None, "publicaciones_hoy": None}

def guardar_estado(estado):
    with open(ESTADO_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "ultimo_fondo": estado.get("ultimo_fondo"),
            "publicaciones_hoy": estado.get("publicaciones_hoy")
        }, f, indent=2, ensure_ascii=False)

def cargar_titulos_publicados():
    try:
        with open(TITULOS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"titulos": []}

def guardar_titulo_publicado(titulo):
    data = cargar_titulos_publicados()
    if titulo not in data["titulos"]:
        data["titulos"].append(titulo)
        with open(TITULOS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

def titulo_ya_publicado(titulo):
    data = cargar_titulos_publicados()
    titulo_norm = titulo.lower().strip()
    for t in data["titulos"]:
        t_norm = t.lower().strip()
        if titulo_norm == t_norm:
            return True
        palabras1 = set(re.findall(r'\w+', titulo_norm))
        palabras2 = set(re.findall(r'\w+', t_norm))
        if len(palabras1) > 3 and len(palabras2) > 3:
            interseccion = palabras1.intersection(palabras2)
            similitud = len(interseccion) / min(len(palabras1), len(palabras2))
            if similitud > 0.7:
                return True
    return False

def obtener_publicaciones_hoy():
    estado = cargar_estado()
    pub = estado.get("publicaciones_hoy")
    if not pub:
        return 0
    hoy = datetime.now(pytz.timezone("America/Mexico_City")).strftime("%Y-%m-%d")
    if pub.get("fecha") == hoy:
        return pub.get("cantidad", 0)
    return 0

def incrementar_publicaciones_hoy():
    estado = cargar_estado()
    hoy = datetime.now(pytz.timezone("America/Mexico_City")).strftime("%Y-%m-%d")
    pub = estado.get("publicaciones_hoy")
    if pub and pub.get("fecha") == hoy:
        pub["cantidad"] = pub.get("cantidad", 0) + 1
    else:
        estado["publicaciones_hoy"] = {"fecha": hoy, "cantidad": 1}
    guardar_estado(estado)

def cargar_temas_publicados():
    try:
        with open(TEMAS_PUBLICADOS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("temas", [])
    except:
        return []

def guardar_tema_publicado(tema, tipo):
    temas = cargar_temas_publicados()
    tema_data = {
        "tema": tema,
        "tipo": tipo,
        "fecha": datetime.now(pytz.timezone("America/Mexico_City")).strftime("%Y-%m-%d")
    }
    temas.append(tema_data)
    if len(temas) > 200:
        temas = temas[-200:]
    with open(TEMAS_PUBLICADOS_FILE, "w", encoding="utf-8") as f:
        json.dump({"temas": temas}, f, indent=2, ensure_ascii=False)

def tema_ya_publicado(tema, dias=30):
    temas = cargar_temas_publicados()
    hoy = datetime.now(pytz.timezone("America/Mexico_City")).date()
    for t in temas:
        if t["tema"].lower() == tema.lower():
            fecha_tema = datetime.strptime(t["fecha"], "%Y-%m-%d").date()
            if (hoy - fecha_tema).days < dias:
                return True
    return False

# ================================================================
# TREND-JACKING
# ================================================================
def obtener_noticia_trending():
    try:
        url = "https://newsapi.org/v2/top-headlines"
        params = {
            "category": "business",
            "language": "es",
            "apiKey": NEWSAPI_KEY,
            "pageSize": 5,
            "country": "mx"
        }
        r = requests.get(url, params=params, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data.get("articles"):
                for article in data["articles"]:
                    title = article.get("title", "")
                    if any(word in title.lower() for word in ["bitcoin", "cripto", "oro", "etf", "inflación", "banco", "finanzas", "dólar", "peso"]):
                        return title
                return data["articles"][0].get("title", "")
        return None
    except Exception as e:
        print(f"⚠️ Error obteniendo noticia: {e}")
        return None

# ================================================================
# SANITIZAR TAGS PARA YOUTUBE
# ================================================================
def sanitizar_tags(tags_str, max_chars=500):
    if not tags_str:
        return []
    raw_tags = [t.strip() for t in tags_str.split(",") if t.strip()]
    cleaned = []
    for tag in raw_tags:
        clean = re.sub(r'[^a-zA-Z0-9áéíóúüñÁÉÍÓÚÜÑ\s\-]', '', tag)
        clean = clean.strip()
        if clean and len(clean) > 1:
            cleaned.append(clean)
    cleaned = list(dict.fromkeys(cleaned))
    current = ""
    for tag in cleaned:
        if current:
            test = current + "," + tag
        else:
            test = tag
        if len(test) <= max_chars:
            current = test
        else:
            break
    return current.split(",") if current else []

# ================================================================
# GENERAR FONDO SÓLIDO (fallback)
# ================================================================
def generar_fondo_solido(color=(20, 20, 50), ancho=1280, alto=720):
    img = Image.new('RGB', (ancho, alto), color)
    path = f"temp_fondo_{random.randint(1000,9999)}.jpg"
    img.save(path)
    return path

# ================================================================
# EXPANSIÓN Y TRUNCAMIENTO DE TEXTO
# ================================================================
def expandir_texto_corto(texto_corto, tema):
    palabras_cortas = len(re.findall(r'\w+', texto_corto))
    prompt = f"""El siguiente relato financiero es demasiado corto ({palabras_cortas} palabras). 
EXPÁNDELO a EXACTAMENTE 90-110 palabras añadiendo más contexto, detalles, ejemplos o consecuencias. 
Mantén el mismo tono y estructura (GANCHO, DATOS, EXPLICACION, SOLUCION, CIERRE).

TEMA: {tema}

TEXTO ORIGINAL:
{texto_corto}

Devuelve SOLO el texto expandido, con los mismos bloques [GANCHO], [DATOS], [EXPLICACION], [SOLUCION], [CIERRE].
"""
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 600,
    }
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=60)
        r.raise_for_status()
        expanded = r.json()["choices"][0]["message"]["content"].strip()
        palabras_exp = len(re.findall(r'\w+', expanded))
        print(f"✅ Texto expandido: {palabras_exp} palabras")
        if palabras_exp > 130:
            expanded = truncar_texto(expanded)
            palabras_exp = len(re.findall(r'\w+', expanded))
            print(f"✂️ Texto truncado a: {palabras_exp} palabras")
        return expanded
    except Exception as e:
        print(f"⚠️ Error en expansión: {e}")
        return texto_corto

def truncar_texto(texto):
    palabras = texto.split()
    if len(palabras) <= 110:
        return texto
    truncado = ' '.join(palabras[:110])
    if not truncado.endswith(('.', '!', '?')):
        truncado += '.'
    return truncado

# ================================================================
# EXTRAER BLOQUES (FALLBACK)
# ================================================================
def extraer_bloques(texto):
    patron = r'\[GANCHO\](.*?)(?=\[DATOS\]|$)|\[DATOS\](.*?)(?=\[EXPLICACION\]|$)|\[EXPLICACION\](.*?)(?=\[SOLUCION\]|$)|\[SOLUCION\](.*?)(?=\[CIERRE\]|$)|\[CIERRE\](.*?)$'
    matches = re.findall(patron, texto, re.DOTALL)
    bloques = []
    for grupo in matches:
        for parte in grupo:
            if parte and parte.strip():
                bloques.append(parte.strip())
    if len(bloques) == 5:
        return bloques
    oraciones = re.split(r'(?<=[.!?])\s+', texto)
    if len(oraciones) >= 5:
        chunk = len(oraciones) // 5
        bloques = []
        for i in range(5):
            start = i * chunk
            end = start + chunk if i < 4 else len(oraciones)
            bloques.append(' '.join(oraciones[start:end]))
        return bloques
    palabras = texto.split()
    if len(palabras) >= 5:
        chunk = len(palabras) // 5
        bloques = []
        for i in range(5):
            start = i * chunk
            end = start + chunk if i < 4 else len(palabras)
            bloques.append(' '.join(palabras[start:end]))
        return bloques
    return [texto]

# ================================================================
# GENERAR GUION (CON FALLBACK DE BLOQUES)
# ================================================================
def generar_guion_financiero(tipo):
    titulos_pub = cargar_titulos_publicados()["titulos"][-10:]
    titulos_referencia = "\n".join([f"- {t}" for t in titulos_pub]) if titulos_pub else "Ninguno aún."

    NICHOS_EDUCATIVOS = [
        "Inversiones en criptomonedas", "Estrategias para ahorrar e invertir",
        "Conceptos básicos del mercado financiero", "Cómo funciona la bolsa de valores",
        "Educación sobre seguros y protección financiera", "Análisis de activos: oro, acciones, bonos",
        "Finanzas personales y presupuestos", "Tecnología financiera (fintech)",
        "Planificación para el retiro", "Impuestos y declaraciones fiscales",
        "Qué es el trading y cómo empezar", "Forex: el mercado de divisas",
        "Cómo funcionan los ETFs", "Acciones vs. bonos: diferencias clave",
        "Qué es la diversificación de cartera", "Cómo leer un estado financiero",
        "Finanzas conductuales", "Qué es un fideicomiso",
        "Cómo funciona el crowdfunding", "Inversiones sostenibles y ESG",
        "Qué es el interés compuesto", "Cómo invertir en bienes raíces",
        "El papel de los bancos centrales", "Inflación y poder adquisitivo",
        "Qué son las criptomonedas estables", "Cómo funciona un exchange",
        "Qué es un swap en finanzas", "Cómo protegerte de la inflación",
        "Estrategias de inversión a largo plazo", "Análisis técnico vs. fundamental"
    ]
    
    NICHOS_ESTAFAS = [
        "Fraudes famosos en el mundo financiero", "Estafas con criptomonedas",
        "Crisis bancarias y sus lecciones", "Escándalos corporativos",
        "Estafas de inversión", "Casos de corrupción financiera",
        "Colapsos bursátiles", "Estafas piramidales",
        "Fraudes con seguros", "Manipulación del mercado",
        "Estafa de las opciones binarias", "Fraude de las criptomonedas falsas",
        "El colapso de los mercados emergentes", "Estafas de refinanciación",
        "Fraudes con préstamos", "Esquemas Ponzi en la historia",
        "Manipulación de la libra esterlina", "Estafas de las puntocom",
        "Fraude de las hipotecas subprime", "Caso de la estafa de la minera de Bitcoin",
        "El escándalo de las divisas", "Estafa de las acciones de centavo",
        "Fraude de los seguros de vida", "Estafa de los fondos de inversión",
        "Caso de la estafa de las criptomonedas en México",
        "Fraudes con tarjetas de crédito", "Estafas de los bienes raíces",
        "El caso de la estafa de la energética", "Fraudes con las remesas",
        "Estafas de las inversiones en arte"
    ]

    tema_elegido = None
    
    if tipo == "noticia":
        noticia_trending = obtener_noticia_trending()
        if noticia_trending and not tema_ya_publicado(noticia_trending, DIAS_SIN_REPETIR_TEMA):
            tema_elegido = noticia_trending[:100]
            print(f"📰 Noticia en tiempo real: {tema_elegido}")
        else:
            print("⚠️ Noticia ya usada o no disponible. Usando nicho educativo...")
            tipo = "educativo"
            temas_disponibles = [n for n in NICHOS_EDUCATIVOS if not tema_ya_publicado(n, DIAS_SIN_REPETIR_TEMA)]
            tema_elegido = random.choice(temas_disponibles) if temas_disponibles else random.choice(NICHOS_EDUCATIVOS)
    elif tipo == "educativo":
        temas_disponibles = [n for n in NICHOS_EDUCATIVOS if not tema_ya_publicado(n, DIAS_SIN_REPETIR_TEMA)]
        tema_elegido = random.choice(temas_disponibles) if temas_disponibles else random.choice(NICHOS_EDUCATIVOS)
    else:
        temas_disponibles = [n for n in NICHOS_ESTAFAS if not tema_ya_publicado(n, DIAS_SIN_REPETIR_TEMA)]
        tema_elegido = random.choice(temas_disponibles) if temas_disponibles else random.choice(NICHOS_ESTAFAS)

    print(f"📌 Tema seleccionado: {tema_elegido}")
    print(f"📌 Tipo: {tipo.upper()}")

    prompt = f"""
Eres un EXPERTO EN FINANZAS y CREADOR DE CONTENIDO VIRAL PARA YOUTUBE SHORTS.

📌 NICHO O TEMA BASE: "{tema_elegido}"
📌 TIPO DE CONTENIDO: {tipo.upper()}

🎯 REGLAS DE CONTENIDO VIRAL (MUY IMPORTANTE):
1. Escribe OBLIGATORIAMENTE entre 90 y 110 palabras.
2. Divide el texto en 5 BLOQUES OBLIGATORIOS. DEBES USAR EXACTAMENTE ESTAS ETIQUETAS:
   - [GANCHO] (3-5 palabras, impacto máximo)
   - [DATOS] (1-2 oraciones con el dato impactante)
   - [EXPLICACION] (2-3 oraciones desarrollando el tema)
   - [SOLUCION] (1-2 oraciones con la moraleja)
   - [CIERRE] (1 oración con pregunta o CTA)
3. Tono coloquial, directo.
4. Números escritos con LETRAS (no "400,500").

🎯 REGLAS SEO:
1. TÍTULO: 50-70 caracteres, con keyword al inicio.
2. PALABRAS CLAVE: 2-3 términos de alto volumen.
3. TAGS: 15-20 tags (sin fechas).
4. PALABRAS PORTADA: 2-3 palabras.

🎯 🖼️ DISEÑO DE LA MINIATURA (SHORT):
Crea un prompt en INGLÉS para que Agnes genere el FONDO de la miniatura. 
- Estilo: "crypto YouTube thumbnail", neón, high contrast, cinematic, hyperrealistic.
- PROHIBIDO: personas, rostros, caras, textos.
- Permitido: Bitcoin, oro, gráficos, fuego, hielo, tecnología.
- Tamaño: 1280x720 (horizontal).

🚫 TÍTULOS YA PUBLICADOS (NO REPETIR):
{titulos_referencia}

📤 RESPUESTA: Devuelve ESTRICTAMENTE este JSON:
{{
    "titulo": "Título SEO de 50-70 caracteres",
    "titulo_alternativo": "Segundo título para A/B testing",
    "anio_suceso": 2024,
    "palabras_clave": ["keyword1", "keyword2", "keyword3"],
    "gancho_descripcion": "Gancho para descripción (máx 90 chars)",
    "contexto_descripcion": "Contexto en una oración",
    "fuente_relato": "Fuente del relato",
    "texto_completo": "Texto con los 5 bloques (90-110 palabras)",
    "palabras_portada": "2-3 palabras para miniatura",
    "tags": "15-20 tags separados por coma",
    "prompt_miniatura": "Prompt en inglés para el fondo de la miniatura (SIN texto, SIN personas, 1280x720)"
}}
"""

    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.8,
        "max_tokens": 1200,
        "response_format": {"type": "json_object"}
    }

    for intento in range(6):
        try:
            print(f"🔄 Intento {intento+1}/6 generando guion viral...")
            r = requests.post(url, headers=headers, json=payload, timeout=90)
            r.raise_for_status()
            respuesta = r.json()["choices"][0]["message"]["content"].strip()
            
            respuesta = re.sub(r"```json\s*", "", respuesta)
            respuesta = re.sub(r"```\s*", "", respuesta)
            inicio = respuesta.find("{")
            fin = respuesta.rfind("}")
            if inicio != -1 and fin != -1:
                json_str = respuesta[inicio:fin+1]
                json_str = re.sub(r",\s*}", "}", json_str)
                json_str = re.sub(r",\s*\]", "]", json_str)
                data = json.loads(json_str, strict=False)
            else:
                raise ValueError("No se encontró JSON")

            texto = data.get("texto_completo", "")
            if not all(marker in texto for marker in ["[GANCHO]", "[DATOS]", "[EXPLICACION]", "[SOLUCION]", "[CIERRE]"]):
                print("   ⚠️ No se encontraron bloques. Extrayendo manualmente...")
                bloques = extraer_bloques(texto)
                if len(bloques) == 5:
                    texto_reconstruido = f"[GANCHO] {bloques[0]}\n[DATOS] {bloques[1]}\n[EXPLICACION] {bloques[2]}\n[SOLUCION] {bloques[3]}\n[CIERRE] {bloques[4]}"
                    data["texto_completo"] = texto_reconstruido
                    texto = texto_reconstruido
                    print("   ✅ Bloques reconstruidos manualmente.")
                else:
                    raise ValueError("No se pudieron extraer bloques")

            palabras = len(re.findall(r'\w+', texto))
            print(f"   📊 Palabras generadas: {palabras}")
            
            if palabras < 70:
                print(f"   ⚠️ Texto demasiado corto ({palabras} palabras). Expandiendo...")
                texto = expandir_texto_corto(texto, tema_elegido)
                data["texto_completo"] = texto
                palabras = len(re.findall(r'\w+', texto))
                print(f"   📊 Palabras después de expansión: {palabras}")
            elif palabras > 130:
                print(f"   ✂️ Texto demasiado largo ({palabras} palabras). Truncando...")
                texto = truncar_texto(texto)
                data["texto_completo"] = texto
                palabras = len(re.findall(r'\w+', texto))
                print(f"   📊 Palabras después de truncar: {palabras}")

            if palabras < 70 or palabras > 130:
                raise ValueError(f"Palabras fuera de rango: {palabras} (debe ser 70-120)")

            titulo = data.get("titulo", "").strip()
            titulo = re.sub(r'#\w+', '', titulo).strip()
            titulo = ' '.join(titulo.split())
            
            keywords = data.get("palabras_clave", [])
            if keywords and isinstance(keywords, list) and keywords:
                primera_kw = keywords[0].strip()
                if primera_kw and not titulo.lower().startswith(primera_kw.lower()):
                    titulo_sin_art = re.sub(r'^(El|La|Los|Las|Un|Una|Unos|Unas)\s+', '', titulo, flags=re.IGNORECASE)
                    if titulo_sin_art != titulo:
                        titulo = f"{primera_kw.capitalize()} {titulo_sin_art}"
                    else:
                        titulo = f"{primera_kw.capitalize()} {titulo}"
                if len(titulo) > 75:
                    titulo = titulo[:72] + "..."
            data["titulo"] = titulo

            if titulo_ya_publicado(titulo):
                raise ValueError("Título duplicado")

            hashtag_alto = random.choice(HASHTAGS_ALTO_VOLUMEN)
            hashtag_medio = random.choice(HASHTAGS_MEDIO_VOLUMEN)
            hashtag_bajo = random.choice(HASHTAGS_BAJO_VOLUMEN)
            data["hashtags_descripcion"] = f"#Shorts {hashtag_alto} {hashtag_medio} {hashtag_bajo}"

            tags_raw = data.get("tags", "")
            tags_list = sanitizar_tags(tags_raw)
            for kw in keywords:
                if kw.lower() not in [t.lower() for t in tags_list]:
                    tags_list.append(kw.lower())
            extras = ["finanzas", "inversiones", "economia", "bitcoin", "oro", "bancos", "seguros", "exchanges"]
            for extra in extras:
                if len(tags_list) < 20 and extra not in tags_list:
                    tags_list.append(extra)
            data["tags"] = ", ".join(tags_list[:20])

            if "prompt_miniatura" not in data or not data["prompt_miniatura"]:
                data["prompt_miniatura"] = f"cinematic wide shot of financial data and glowing charts, neon cyan and magenta lighting, high contrast, dark background, dramatic lighting, hyperrealistic, 8k, no people, no text, no watermark"

            print(f"   🏷️ Título: {data['titulo']} ({len(data['titulo'])} chars)")
            print(f"   🔑 Keywords: {keywords}")
            print(f"   📊 Palabras finales: {palabras}")
            return data, tema_elegido
            
        except Exception as e:
            print(f"❌ Intento {intento+1}/6 falló: {e}")
            if intento < 5:
                time.sleep(10)  # 🔥 10 SEGUNDOS ENTRE INTENTOS

    print("❌ TODOS LOS INTENTOS FALLARON.")
    sys.exit(1)

# ================================================================
# DIVIDIR EN SEGMENTOS
# ================================================================
def dividir_en_segmentos(texto, max_palabras_por_segmento=35):
    patron = r'\[GANCHO\](.*?)(?=\[DATOS\]|$)|\[DATOS\](.*?)(?=\[EXPLICACION\]|$)|\[EXPLICACION\](.*?)(?=\[SOLUCION\]|$)|\[SOLUCION\](.*?)(?=\[CIERRE\]|$)|\[CIERRE\](.*?)$'
    matches = re.findall(patron, texto, re.DOTALL)
    
    segmentos = []
    for grupo in matches:
        for parte in grupo:
            if parte and parte.strip():
                parte_limpia = parte.strip()
                palabras = parte_limpia.split()
                if len(palabras) > max_palabras_por_segmento:
                    for i in range(0, len(palabras), max_palabras_por_segmento):
                        sub_segmento = ' '.join(palabras[i:i+max_palabras_por_segmento])
                        segmentos.append(sub_segmento)
                else:
                    segmentos.append(parte_limpia)
    
    if not segmentos:
        oraciones = re.split(r'(?<=[.!?¿¡])\s+', texto)
        segmentos = [o.strip() for o in oraciones if o.strip()]
    
    if not segmentos:
        segmentos = [texto]
    
    if len(segmentos) > 5:
        while len(segmentos) > 5:
            segmentos[-2] = segmentos[-2] + " " + segmentos[-1]
            segmentos.pop()
    
    return segmentos

# ================================================================
# ASIGNAR ETAPAS VISUALES
# ================================================================
def asignar_etapas_visuales(segmentos):
    n = len(segmentos)
    etapas = []
    ubicaciones = []
    
    mapa_etapas = [
        "contexto_general",
        "analisis_datos",
        "evento_principal",
        "climax",
        "resolucion"
    ]
    mapa_ubicaciones = [
        "distrito financiero moderno, impacto visual",
        "sala de trading con gráficos y datos",
        "lugar del suceso financiero (banco, exchange)",
        "momento crítico de máxima tensión",
        "conclusión, ambiente calmado"
    ]
    
    for i in range(n):
        idx = min(i, len(mapa_etapas) - 1)
        etapas.append(mapa_etapas[idx])
        ubicaciones.append(mapa_ubicaciones[idx])
    
    return etapas, ubicaciones

# ================================================================
# GENERAR PROMPT DE IMAGEN
# ================================================================
def generar_prompt_imagen_segmento(segmento_texto, etapa, ubicacion_escena,
                                   segmento_anterior_texto=None,
                                   index_segmento=0, total_segmentos=1,
                                   tema=None, es_primer_frame=False):
    global COLOR_NEON_ACTUAL, PALETA_BASE_ACTUAL
    
    contexto_previo = ""
    if segmento_anterior_texto:
        contexto_previo = f"\nPREVIOUS SCENE: '{segmento_anterior_texto[:120]}'"

    if es_primer_frame and index_segmento == 0:
        estilo_base = f"NEON NOIR aesthetic, cyberpunk financial vibe, intense {COLOR_NEON_ACTUAL} glow on surfaces, high contrast, electric atmosphere, futuristic corporate look"
    elif etapa in ["climax"]:
        estilo_base = f"Hyperrealistic photography combined with intense {COLOR_NEON_ACTUAL} neon accents, dramatic lighting, high contrast, cinematic composition, financial crisis atmosphere"
    elif etapa in ["evento_principal", "analisis_datos"]:
        estilo_base = f"Realistic photograph with subtle {COLOR_NEON_ACTUAL} neon highlights, natural lighting mixed with artificial glow, professional corporate setting"
    elif etapa in ["contexto_general"]:
        estilo_base = "Authentic documentary-style photograph, natural lighting, real-world environment, no filters, no neon"
    else:
        estilo_base = "Realistic, natural photograph, natural lighting, authentic environment, calm atmosphere, no artificial effects"

    descripcion_estilo = f"{estilo_base}, vertical 9:16, {PALETA_BASE_ACTUAL}, sharp focus, hyperdetailed, 8k resolution, cinematic"

    tema_lower = tema.lower() if tema else ""
    if "bitcoin" in tema_lower or "cripto" in tema_lower:
        elementos_tema = "digital currency, blockchain data, crypto screens, modern fintech environment"
    elif "oro" in tema_lower:
        elementos_tema = "gold bars, precious metals, vault, luxury banking setting"
    elif "estafa" in tema_lower or "fraude" in tema_lower or "colapso" in tema_lower:
        elementos_tema = "dramatic financial collapse scene, crisis atmosphere, concerned professionals"
    else:
        elementos_tema = "modern financial setting, professional environment"

    prompt = f"""
You are a WORLD-CLASS CINEMATOGRAPHER specializing in FINANCIAL PHOTOGRAPHY.

STORY FRAGMENT:
\"\"\"
{segmento_texto}
\"\"\"
{contexto_previo}

CREATE A PREMIUM PHOTO PROMPT for a vertical (9:16) image.

SCENE DETAILS:
- STAGE: {etapa}
- LOCATION: {ubicacion_escena}
- VISUAL STYLE: {descripcion_estilo}
- SUBJECT: {elementos_tema}

COMPOSITION RULES:
1. SHOT TYPE: Wide or medium shot. ABSOLUTELY NO close-up of faces.
2. MAIN SUBJECT: The environment, objects, and setting.
3. If people appear: They occupy AT MOST 15% of the frame.
4. FOCUS: Sharp, hyperrealistic, premium quality.

Return ONLY the English prompt, no explanations.
"""

    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.6,
        "max_tokens": 350,
    }
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=60)
        r.raise_for_status()
        prompt_img = r.json()["choices"][0]["message"]["content"].strip()
        prompt_img += f", hyperrealistic, 8k resolution, sharp focus, professional corporate photography, vertical 9:16, wide establishing shot, environment as main subject, no close-up face, no text, no watermark"
        return prompt_img
    except Exception as e:
        print(f"⚠️ Error generando prompt: {e}")
        return f"Wide establishing shot of {ubicacion_escena}, vertical 9:16, financial environment, hyperrealistic, 8k quality, {PALETA_BASE_ACTUAL}"

# ================================================================
# GENERAR IMAGEN VERTICAL (CON PAUSA DE 10s)
# ================================================================
def generar_imagen_vertical(prompt, intentos=3):
    prompt = re.sub(r"\n+", " ", prompt).strip()
    prompt = re.sub(r'"', "'", prompt)
    prompt = prompt[:950]
    
    url = "https://apihub.agnes-ai.com/v1/images/generations"
    headers = {"Authorization": f"Bearer {AGNES_API_KEY}", "Content-Type": "application/json"}
    
    negative = (
        "multiple people, crowd, group, two people, three people, "
        "close-up face, portrait, headshot, face filling frame, "
        "gore, blood, violence, weapons, "
        "clones, duplicates, twins, doppelganger, "
        "deformed, bad anatomy, extra limbs, missing limbs, "
        "blurry, low quality, pixelated, "
        "text, watermark, logo, signature, "
        "cartoon, animated, painting, drawing, sketch, "
        "oversaturated, oversharpened, artificial, fake, "
        "abandoned, rusty, decayed, ruined (unless historical), "
        "monster, zombie, corpse, ghost, "
        "surreal, impossible, floating objects"
    )
    
    payload = {
        "model": "agnes-image-2.1-flash",
        "prompt": prompt,
        "negative_prompt": negative,
        "width": 1080,
        "height": 1920,
        "num_images": 1,
        "enhance_prompt": True
    }
    
    for intento in range(intentos):
        try:
            print(f"   🖼️ Generando imagen {intento+1}/{intentos}...")
            r = requests.post(url, headers=headers, json=payload, timeout=120)
            if r.status_code == 200:
                data = r.json()
                if data.get("data") and len(data["data"]) > 0:
                    return data["data"][0]["url"]
            else:
                print(f"   ⚠️ Error {r.status_code}: {r.text[:100]}")
        except Exception as e:
            print(f"   ⚠️ Error conexión: {e}")
        if intento < intentos - 1:
            time.sleep(10)  # 🔥 10 SEGUNDOS ENTRE INTENTOS
    return None

# ================================================================
# GENERAR IMAGEN HORIZONTAL PARA MINIATURA (CON PAUSA DE 10s)
# ================================================================
def generar_imagen_horizontal(prompt, intentos=3):
    prompt_completo = f"{prompt}, hyperrealistic, 8k, cinematic lighting, high contrast, sharp focus, no people, no text, no watermark"
    prompt_completo = prompt_completo[:950]
    
    url = "https://apihub.agnes-ai.com/v1/images/generations"
    headers = {"Authorization": f"Bearer {AGNES_API_KEY}", "Content-Type": "application/json"}
    negative = "multiple people, crowd, close-up face, portrait, headshot, gore, blood, clones, deformed, blurry, text, watermark, low quality"
    payload = {
        "model": "agnes-image-2.1-flash",
        "prompt": prompt_completo,
        "negative_prompt": negative,
        "width": 1280,
        "height": 720,
        "num_images": 1,
        "enhance_prompt": True
    }
    for intento in range(intentos):
        try:
            print(f"   🖼️ Generando fondo de miniatura {intento+1}/{intentos}...")
            r = requests.post(url, headers=headers, json=payload, timeout=120)
            if r.status_code == 200:
                data = r.json()
                if data.get("data") and len(data["data"]) > 0:
                    return data["data"][0]["url"]
            else:
                print(f"   ⚠️ Error {r.status_code}")
        except Exception as e:
            print(f"   ⚠️ Error conexión: {e}")
        if intento < intentos - 1:
            time.sleep(10)  # 🔥 10 SEGUNDOS ENTRE INTENTOS
    return None

# ================================================================
# GENERAR AUDIO (CON PAUSA DE 10s)
# ================================================================
def generar_audio(texto, index, intentos_por_voz=2):
    global CONFIG_VOZ_ACTUAL
    texto_limpio = re.sub(r'[^a-zA-ZáéíóúüñÁÉÍÓÚÜÑ0-9\s.,;:!?¿¡\'\"]', '', texto)
    texto_limpio = re.sub(r'\s+', ' ', texto_limpio).strip()
    if len(texto_limpio) < 20:
        texto_limpio = "Noticias financieras."
    filename = f"audio_short_{index}.mp3"
    voz = CONFIG_VOZ_ACTUAL["voz"]
    rate = CONFIG_VOZ_ACTUAL["velocidad"]
    pitch = CONFIG_VOZ_ACTUAL["tono"]
    for intento in range(intentos_por_voz):
        async def _gen():
            communicate = edge_tts.Communicate(texto_limpio, voz, rate=rate, pitch=pitch)
            await communicate.save(filename)
        try:
            asyncio.run(_gen())
            if os.path.exists(filename) and os.path.getsize(filename) > 0:
                return filename
        except Exception as e:
            print(f"   ❌ Falló voz {voz}: {e}")
        time.sleep(10)  # 🔥 10 SEGUNDOS ENTRE INTENTOS
        if os.path.exists(filename):
            try: os.remove(filename)
            except: pass
    return None

# ================================================================
# GENERAR RECURSOS POR SEGMENTO (CON PAUSA DE 10s)
# ================================================================
def generar_recursos_por_segmento(segmentos, etapas, ubicaciones, tema=None, intentos_imagen=3):
    recursos = []
    total = len(segmentos)
    last_successful_url = None

    for idx, seg in enumerate(segmentos):
        print(f"  🎬 Segmento {idx+1}/{total} ({len(seg.split())} palabras)")
        etapa = etapas[idx] if idx < len(etapas) else "contexto_general"
        ubic = ubicaciones[idx] if idx < len(ubicaciones) else "oficina financiera"
        seg_anterior = segmentos[idx-1] if idx > 0 else None
        es_primer_frame = (idx == 0)
        
        prompt_img = generar_prompt_imagen_segmento(
            seg, etapa, ubic, seg_anterior, idx, total, tema, es_primer_frame
        )
        print(f"    📝 Prompt: {prompt_img[:100]}...")
        
        img_url = None
        for intento in range(intentos_imagen):
            img_url = generar_imagen_vertical(prompt_img, intentos=1)
            if img_url:
                print(f"    ✅ Imagen generada (intento {intento+1})")
                last_successful_url = img_url
                break
            time.sleep(10)  # 🔥 10 SEGUNDOS ENTRE INTENTOS DE IMAGEN
        
        if not img_url:
            if last_successful_url:
                print(f"    🔄 Reutilizando imagen anterior")
                img_url = last_successful_url
            else:
                print(f"    ⚠️ No hay imagen previa. Reintentando...")
                time.sleep(10)
                img_url = generar_imagen_vertical(prompt_img, intentos=1)
                if img_url:
                    last_successful_url = img_url
                else:
                    print(f"    ❌ Falló definitivamente, usando fondo sólido")
                    img_path = generar_fondo_solido(color=(20, 20, 50), ancho=1080, alto=1920)
                    img_url = img_path
                    last_successful_url = img_url
        
        if not img_url:
            img_path = generar_fondo_solido(color=(20, 20, 50), ancho=1080, alto=1920)
            img_url = img_path
            last_successful_url = img_url
        
        audio_path = generar_audio(seg, idx)
        if not audio_path:
            print(f"    ❌ Falló audio en segmento {idx+1}. Abortando.")
            return None
        
        try:
            dur = AudioFileClip(audio_path).duration
        except:
            dur = 8.0
        
        recursos.append({
            "imagen_url": img_url,
            "audio_path": audio_path,
            "duracion": dur,
            "texto": seg
        })
        
        if idx < total - 1:
            print(f"   ⏳ Esperando 10 segundos...")
            time.sleep(10)  # 🔥 10 SEGUNDOS ENTRE SEGMENTOS
    
    return recursos

# ================================================================
# SUBTÍTULOS CON PIL (VERTICAL)
# ================================================================
def agregar_subtitulos_con_pil(imagen_path, texto, salida_path):
    try:
        img = Image.open(imagen_path)
        draw = ImageDraw.Draw(img)
        
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 50)
        except:
            try:
                font = ImageFont.truetype("arial.ttf", 50)
            except:
                font = ImageFont.load_default()
                print("   ⚠️ Usando fuente predeterminada")
        
        if not texto:
            return imagen_path
        
        palabras = texto.split()
        if len(palabras) > 14:
            texto_sub = ' '.join(palabras[:14])
        else:
            texto_sub = texto
        
        if len(texto_sub) > 50:
            mitad = len(texto_sub) // 2
            espacio = texto_sub.find(' ', mitad - 10)
            if espacio == -1:
                espacio = mitad
            linea1 = texto_sub[:espacio]
            linea2 = texto_sub[espacio+1:]
            lineas = [linea1, linea2]
        else:
            lineas = [texto_sub]
        
        y_base = 1700
        for i, linea in enumerate(lineas):
            bbox = draw.textbbox((0, 0), linea, font=font)
            ancho = bbox[2] - bbox[0]
            alto = bbox[3] - bbox[1]
            x = (1080 - ancho) // 2
            y = y_base + i * 60
            
            padding = 15
            bg_x = x - padding
            bg_y = y - padding
            bg_w = ancho + padding * 2
            bg_h = alto + padding * 2
            draw.rectangle([bg_x, bg_y, bg_x + bg_w, bg_y + bg_h], fill=(0, 0, 0, 160))
            
            draw.text((x+3, y+3), linea, fill='black', font=font)
            draw.text((x, y), linea, fill='white', font=font)
        
        img.save(salida_path)
        return salida_path
        
    except Exception as e:
        print(f"⚠️ Error en subtítulos: {e}")
        return imagen_path

# ================================================================
# MINIATURA PROFESIONAL PARA SHORTS (CON FALLBACK DE FONDO SÓLIDO)
# ================================================================
def crear_miniatura_profesional(prompt_miniatura, texto_portada, salida="miniatura_short.jpg"):
    try:
        print("🖼️ Generando fondo de miniatura...")
        fondo_url = generar_imagen_horizontal(prompt_miniatura, intentos=2)
        if not fondo_url:
            print("⚠️ No se pudo generar fondo, usando fondo sólido")
            fondo_path = generar_fondo_solido()
            fondo_url = fondo_path
        
        if fondo_url.startswith("http"):
            try:
                r = requests.get(fondo_url, timeout=30)
                r.raise_for_status()
                img_path = "temp_thumb_fondo_short.jpg"
                with open(img_path, "wb") as f:
                    f.write(r.content)
            except Exception as e:
                print(f"⚠️ Error descargando fondo: {e}. Usando fondo sólido.")
                img_path = generar_fondo_solido()
        else:
            img_path = fondo_url
        
        img = Image.open(img_path)
        img = ImageOps.fit(img, (1280, 720), Image.Resampling.LANCZOS)
        draw = ImageDraw.Draw(img)
        
        texto = texto_portada.upper().strip()
        lineas = texto.split()
        if len(lineas) > 3:
            texto = ' '.join(lineas[:3])
        else:
            texto = ' '.join(lineas)
        
        try:
            font = ImageFont.truetype("fonts/Anton.ttf", 100)
        except:
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/msttcorefonts/Impact.ttf", 100)
            except:
                try:
                    font = ImageFont.truetype("Impact.ttf", 100)
                except:
                    font = ImageFont.load_default()
        
        bbox = draw.textbbox((0, 0), texto, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        x = (1280 - text_w) // 2
        y = (720 - text_h) // 2 + 60
        
        for dx, dy in [(-4, -4), (-4, 4), (4, -4), (4, 4), (0, 6), (0, -6), (6, 0), (-6, 0)]:
            draw.text((x + dx, y + dy), texto, fill='black', font=font)
        for dx, dy in [(-2, -2), (-2, 2), (2, -2), (2, 2)]:
            draw.text((x + dx, y + dy), texto, fill='white', font=font)
        draw.text((x, y), texto, fill=(255, 255, 80), font=font)
        
        img.save(salida)
        print(f"✅ Miniatura profesional para Short creada: {salida}")
        return salida
    except Exception as e:
        print(f"⚠️ Error en miniatura profesional: {e}")
        return None

# ================================================================
# MONTAR VIDEO SHORTS (CON ORDEN CORREGIDO)
# ================================================================
def montar_video_shorts(recursos, fondo_path, salida="short_capital.mp4"):
    if not recursos:
        raise ValueError("No hay recursos")
    
    clips_video = []
    clips_audio = []
    
    for i, rec in enumerate(recursos):
        img_url = rec["imagen_url"]
        audio_path = rec["audio_path"]
        duracion = rec["duracion"]
        texto = rec.get("texto", "")
        
        try:
            if img_url.startswith("http"):
                try:
                    r = requests.get(img_url, timeout=30)
                    r.raise_for_status()
                    img_path = f"temp_short_{i}.jpg"
                    with open(img_path, "wb") as f:
                        f.write(r.content)
                except:
                    img_path = generar_fondo_solido(color=(20, 20, 50), ancho=1080, alto=1920)
            else:
                img_path = img_url
            
            img = Image.open(img_path)
            img = ImageOps.fit(img, (1080, 1920), Image.Resampling.LANCZOS)
            img.save(img_path)
            
            img_sub_path = f"temp_short_sub_{i}.jpg"
            img_path = agregar_subtitulos_con_pil(img_path, texto, img_sub_path)
            
            video_clip = (ImageClip(img_path)
                         .resize(lambda t: 1 + 0.02 * t)
                         .set_duration(duracion))
        except Exception as e:
            print(f"⚠️ Falló imagen {i}: {e}")
            img_path = generar_fondo_solido(color=(20, 20, 50), ancho=1080, alto=1920)
            video_clip = ImageClip(img_path, duration=duracion).resize(lambda t: 1 + 0.02 * t)
        
        clips_video.append(video_clip)
        
        try:
            audio = AudioFileClip(audio_path)
            clips_audio.append(audio)
        except:
            silencio = AudioClip(lambda t: 0, duration=duracion)
            clips_audio.append(silencio)
    
    PAUSA = 0.3
    audio_final_parts = []
    for i, aud in enumerate(clips_audio):
        audio_final_parts.append(aud)
        if i < len(clips_audio) - 1:
            audio_final_parts.append(AudioClip(lambda t: 0, duration=PAUSA))
    
    audio_narracion = concatenate_audioclips(audio_final_parts)
    duracion_total = audio_narracion.duration
    
    video = concatenate_videoclips(clips_video, method="compose")
    video = video.set_duration(duracion_total)
    
    if fondo_path and os.path.exists(fondo_path):
        try:
            fondo_clip = AudioFileClip(fondo_path)
            if fondo_clip.duration < duracion_total:
                veces = int(duracion_total / fondo_clip.duration) + 1
                fondo_clip = concatenate_audioclips([fondo_clip] * veces)
            fondo_clip = fondo_clip.subclip(0, duracion_total).volumex(0.06)
            audio_final = CompositeAudioClip([audio_narracion, fondo_clip])
        except:
            audio_final = audio_narracion
    else:
        audio_final = audio_narracion
    
    video = video.set_audio(audio_final)
    video.write_videofile(salida, fps=24, codec="libx264", audio_codec="aac", 
                          threads=4, preset="ultrafast")
    video.close()
    audio_final.close()
    
    for f in os.listdir("."):
        if f.startswith("temp_short_") and f.endswith(".jpg"):
            try: os.remove(f)
            except: pass
    
    return salida

# ================================================================
# SUBIR A YOUTUBE (CON CATEGORÍA 22: PERSONAS Y BLOGS)
# ================================================================
def subir_a_youtube(video_path, titulo, etiquetas_str, gancho, contexto, hashtags, fuente="", miniatura_path=None):
    try:
        creds = Credentials.from_authorized_user_info(YOUTUBE_USER_TOKEN)
        youtube = build("youtube", "v3", credentials=creds)
    except Exception as e:
        print(f"❌ Error autenticando: {e}")
        sys.exit(1)
    
    tags = sanitizar_tags(etiquetas_str)
    print(f"📝 Tags sanitizados: {len(tags)} tags")
    
    descripcion = f"""{gancho}

{contexto}

🔴 SUSCRÍBETE al canal: {CANAL_LINK}

📖 {fuente}

{hashtags}

⚠️ AVISO IMPORTANTE: Este contenido es solo para fines educativos no constituye asesoría financiera, legal o de inversión."""
    
    body = {
        "snippet": {
            "title": titulo[:100],
            "description": descripcion[:5000],
            "tags": tags[:30],
            "categoryId": "22",  # 🔥 CAMBIADO A "Personas y Blogs"
            "defaultLanguage": "es",
            "defaultAudioLanguage": "es",
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": True,
        },
    }
    
    media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = request.execute()
    video_id = response["id"]
    print(f"✅ Short subido: https://youtu.be/{video_id}")
    
    if miniatura_path and os.path.exists(miniatura_path):
        try:
            media_thumb = MediaFileUpload(miniatura_path, chunksize=-1, resumable=True)
            youtube.thumbnails().set(videoId=video_id, media_body=media_thumb).execute()
            print("✅ Miniatura profesional subida")
        except Exception as e:
            print(f"⚠️ Error subiendo miniatura: {e}")
    
    return video_id

# ================================================================
# LIMPIEZA
# ================================================================
def limpiar_archivos_temporales():
    import glob
    patrones = [
        "temp_*.jpg", "audio_short_*.mp3", "temp_thumb*.jpg",
        "miniatura_short.jpg", "short_capital.mp4", "placeholder*.jpg",
        "temp_fondo_*.jpg"
    ]
    for patron in patrones:
        for f in glob.glob(patron):
            try:
                os.remove(f)
                print(f"🧹 Eliminado: {f}")
            except:
                pass
    print("✅ Limpieza completada")

# ================================================================
# MAIN
# ================================================================
def main():
    print("="*60)
    print("🎬 Capital Digital - Bot de SHORTS (VERSIÓN DEFINITIVA)")
    print("   ✓ Música Corporate/Tech")
    print("   ✓ Ken Burns (Zoom)")
    print("   ✓ Transiciones Fade")
    print("   ✓ Miniatura profesional (fondo Agnes + texto PIL)")
    print("   ✓ Subtítulos 50px (orden corregido)")
    print("   ✓ Fallback de bloques en guion")
    print("   ✓ Tags sanitizados")
    print("   ✓ Pausas de 10 segundos entre generaciones")
    print("   ✓ Categoría: Personas y Blogs (22)")
    print("="*60)
    
    if not YOUTUBE_USER_TOKEN:
        print("❌ Falta YOUTUBE_USER_TOKEN_CAPITAL")
        sys.exit(1)
    
    publicadas = obtener_publicaciones_hoy()
    if publicadas >= META_DIARIA_SHORTS:
        print(f"✅ Ya se publicaron {META_DIARIA_SHORTS} shorts hoy. Saliendo.")
        sys.exit(0)
    
    if publicadas == 0:
        tipo = "noticia"
    elif publicadas == 1:
        tipo = "educativo"
    else:
        tipo = "estafa"
    
    print(f"📌 Tipo: {tipo.upper()} (Short #{publicadas+1} del día)")
    
    estado = cargar_estado()
    fondo_path = seleccionar_fondo_disponible(estado)
    
    guion, tema_elegido = generar_guion_financiero(tipo)
    texto = guion["texto_completo"]
    palabras_portada = guion.get("palabras_portada", "RÉCORD")
    prompt_miniatura = guion.get("prompt_miniatura", "")
    
    palabras_texto = len(re.findall(r'\w+', texto))
    print(f"📝 Texto: {palabras_texto} palabras")
    print(f"📌 Tema: {tema_elegido}")
    
    segmentos = dividir_en_segmentos(texto, max_palabras_por_segmento=35)
    etapas, ubicaciones = asignar_etapas_visuales(segmentos)
    print(f"🎬 {len(segmentos)} segmentos generados")
    
    recursos = generar_recursos_por_segmento(segmentos, etapas, ubicaciones, tema_elegido)
    if not recursos:
        print("❌ Error generando recursos.")
        sys.exit(1)
    
    video_path = montar_video_shorts(recursos, fondo_path, "short_capital.mp4")
    print(f"🎬 Video montado: {video_path}")
    
    miniatura_path = None
    if prompt_miniatura:
        print("🖼️ Generando miniatura profesional para Short...")
        miniatura_path = crear_miniatura_profesional(
            prompt_miniatura,
            palabras_portada,
            "miniatura_short.jpg"
        )
    
    video_id = subir_a_youtube(
        video_path=video_path,
        titulo=guion["titulo"],
        etiquetas_str=guion["tags"],
        gancho=guion["gancho_descripcion"],
        contexto=guion["contexto_descripcion"],
        hashtags=guion["hashtags_descripcion"],
        fuente=guion.get("fuente_relato", "Basado en análisis financiero"),
        miniatura_path=miniatura_path
    )
    
    guardar_titulo_publicado(guion["titulo"])
    guardar_tema_publicado(tema_elegido, tipo)
    incrementar_publicaciones_hoy()
    guardar_estado(estado)
    
    limpiar_archivos_temporales()
    
    print(f"✅ Short publicado exitosamente!")
    print(f"🔗 https://youtu.be/{video_id}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ Error fatal: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
