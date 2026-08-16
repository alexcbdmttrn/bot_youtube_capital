import asyncio
from datetime import datetime, timedelta
import json
import os
import random
import re
import sys
import time
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
ACTIVAR_DISCLOSURE_IA = True
DIAS_SIN_REPETIR_TEMA = 30

# ================================================================
# VOZ FIJA (Jorge) - VELOCIDAD +10% (NATURAL Y CORTA)
# ================================================================
VOZ_FIJA = {"voz": "es-MX-JorgeNeural", "velocidad": "+10%", "tono": "-1Hz", "nombre": "Jorge (MX)"}
CONFIG_VOZ_ACTUAL = VOZ_FIJA

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
# MÚSICA DE FONDO
# ================================================================
FONDOS_DISPONIBLES = [
    "Ash and Marrow.mp3", "Black Maw.mp3", "Cold Hollow.mp3",
    "Hollow Marrow.mp3", "Sunken Dread.mp3", "Sunless Vault.mp3", "The Deep Rot.mp3"
]

def seleccionar_fondo_disponible(estado):
    fondos = FONDOS_DISPONIBLES.copy()
    ultimo_fondo = estado.get("ultimo_fondo")
    if ultimo_fondo and ultimo_fondo in fondos:
        fondos.remove(ultimo_fondo)
    random.shuffle(fondos)
    for root, dirs, files in os.walk("."):
        if "/." in root or "\\." in root:
            continue
        for file in files:
            for fondo in fondos:
                if file.lower() == fondo.lower():
                    full_path = os.path.join(root, file)
                    estado["ultimo_fondo"] = fondo
                    return full_path
    return None

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

# ================================================================
# 📁 TEMAS PUBLICADOS (evitar repeticiones)
# ================================================================
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
    print(f"📁 Tema guardado: '{tema}' ({tipo})")

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
# 🔥 EXPANSIÓN Y TRUNCAMIENTO DE TEXTO (PARA 90-110 PALABRAS)
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
# 🔥 TREND-JACKING: OBTENER NOTICIA DE NEWSAPI
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
# 🎯 GENERAR GUION CON ESTRUCTURA VIRAL (90-110 PALABRAS)
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
        if temas_disponibles:
            tema_elegido = random.choice(temas_disponibles)
        else:
            tema_elegido = random.choice(NICHOS_EDUCATIVOS)
            print(f"⚠️ Todos los nichos educativos usados en los últimos {DIAS_SIN_REPETIR_TEMA} días. Forzando: {tema_elegido}")
    
    else:
        temas_disponibles = [n for n in NICHOS_ESTAFAS if not tema_ya_publicado(n, DIAS_SIN_REPETIR_TEMA)]
        if temas_disponibles:
            tema_elegido = random.choice(temas_disponibles)
        else:
            tema_elegido = random.choice(NICHOS_ESTAFAS)
            print(f"⚠️ Todos los nichos de estafa usados en los últimos {DIAS_SIN_REPETIR_TEMA} días. Forzando: {tema_elegido}")

    print(f"📌 Tema seleccionado: {tema_elegido}")
    print(f"📌 Tipo: {tipo.upper()}")

    prompt = f"""Eres un EXPERTO EN FINANZAS y CREADOR DE CONTENIDO VIRAL PARA YOUTUBE SHORTS.

📌 NICHO O TEMA BASE: "{tema_elegido}"
📌 TIPO DE CONTENIDO: {tipo.upper()}

🎯 INSTRUCCIONES:
Desarrolla un relato corto y viral sobre este nicho. Puedes elegir un enfoque específico dentro del nicho, como un caso real, una lección práctica, un dato impactante o una historia ejemplar.

🎯 REGLAS DE CONTENIDO VIRAL (PARA SHORTS DE 30-40 SEGUNDOS):
1. Escribe OBLIGATORIAMENTE entre 90 y 110 palabras.
2. Divide el texto en 5 BLOQUES OBLIGATORIOS:
   - [GANCHO] (3-4 palabras, impacto máximo)
   - [DATOS] (1-2 oraciones con el dato impactante)
   - [EXPLICACION] (2-3 oraciones desarrollando el tema)
   - [SOLUCION] (1-2 oraciones con la moraleja)
   - [CIERRE] (1 oración con pregunta o CTA)
3. Usa un tono coloquial, directo y cercano. Frases cortas y contundentes.

🎯 REGLAS SEO:
1. TÍTULO: 50-70 caracteres, con keyword al inicio.
2. PALABRAS CLAVE: 2-3 términos de alto volumen.
3. TAGS: 15-20 tags.
4. PALABRAS PORTADA: 2-3 palabras.

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
    "tags": "15-20 tags separados por coma"
}}
"""

    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 1000,
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
                raise ValueError("Faltan bloques obligatorios")

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
            tags_list = [t.strip() for t in tags_raw.split(",") if t.strip()]
            for kw in keywords:
                if kw.lower() not in [t.lower() for t in tags_list]:
                    tags_list.append(kw.lower())
            extras = ["finanzas", "inversiones", "economia", "bitcoin", "oro", "bancos", "seguros", "exchanges"]
            i = 0
            while len(tags_list) < 12 and i < len(extras):
                if extras[i] not in tags_list:
                    tags_list.append(extras[i])
                i += 1
            data["tags"] = ", ".join(tags_list[:20])

            print(f"   🏷️ Título: {data['titulo']} ({len(data['titulo'])} chars)")
            print(f"   🔑 Keywords: {keywords}")
            print(f"   📊 Palabras finales: {palabras}")
            print(f"   🏷️ Hashtags: {data['hashtags_descripcion']}")
            return data, tema_elegido
            
        except Exception as e:
            print(f"❌ Intento {intento+1}/6 falló: {e}")
            if intento < 5:
                time.sleep(10 + intento * 3)

    print("❌ TODOS LOS INTENTOS FALLARON.")
    sys.exit(1)

# ================================================================
# 📝 DIVIDIR EN 5 SEGMENTOS
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
# 🎭 ASIGNAR ETAPAS VISUALES
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
# 🎨 GENERAR PROMPT DE IMAGEN
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
3. If people appear: They occupy AT MOST 15% of the frame, small and at distance.
4. FOCUS: Sharp, hyperrealistic, premium quality.
5. ATMOSPHERE: Professional, sophisticated, clean, high-end.

ABSOLUTE PROHIBITIONS:
- NO close-up faces, NO portraits, NO headshots
- NO gore, NO blood, NO violence
- NO clones, NO duplicates, NO twins
- NO text, NO watermarks, NO logos
- NO low quality, NO blurry images

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
# 🖼️ GENERAR IMAGEN CON AGNES (CON REUTILIZACIÓN)
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
            time.sleep(10 * (intento + 1))
    return None

# ================================================================
# 📝 GENERAR AUDIO CON JORGE (+10%)
# ================================================================
def generar_audio(texto, index, intentos_por_voz=2):
    global CONFIG_VOZ_ACTUAL
    
    texto_limpio = re.sub(r'[^a-zA-ZáéíóúüñÁÉÍÓÚÜÑ0-9\s.,;:!?¿¡\'\"]', '', texto)
    texto_limpio = re.sub(r'\s+', ' ', texto_limpio).strip()
    
    if len(texto_limpio) < 20:
        texto_limpio = "Noticias financieras."
    
    filename = f"audio_capital_{index}.mp3"
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
        time.sleep(5)
        if os.path.exists(filename):
            try: os.remove(filename)
            except: pass
    
    return None

# ================================================================
# 🎬 GENERAR RECURSOS POR SEGMENTO (CON REUTILIZACIÓN)
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
            time.sleep(8)
        
        if not img_url:
            if last_successful_url:
                print(f"    🔄 Reutilizando imagen anterior")
                img_url = last_successful_url
            else:
                print(f"    ⚠️ No hay imagen previa. Reintentando...")
                time.sleep(15)
                img_url = generar_imagen_vertical(prompt_img, intentos=1)
                if img_url:
                    last_successful_url = img_url
                else:
                    print(f"    ❌ Falló definitivamente, usando placeholder")
                    img_url = "https://via.placeholder.com/1080x1920/1a1a3a/4a8af4?text=Capital+Digital"
                    last_successful_url = img_url
        
        if not img_url:
            img_url = "https://via.placeholder.com/1080x1920/1a1a3a/4a8af4?text=Capital+Digital"
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
            print(f"   ⏳ Esperando 15 segundos antes del siguiente segmento...")
            time.sleep(15)
    
    return recursos

# ================================================================
# 🎬 SUBTÍTULOS CON PIL (VERSIÓN ROBUSTA)
# ================================================================
def agregar_subtitulos_con_pil(imagen_path, texto, salida_path):
    try:
        img = Image.open(imagen_path)
        draw = ImageDraw.Draw(img)
        
        # Intentar cargar fuente
        font = None
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 50)
        except:
            try:
                font = ImageFont.truetype("arial.ttf", 50)
            except:
                font = ImageFont.load_default()
                print("   ⚠️ Usando fuente predeterminada para subtítulos")
        
        if not texto:
            return imagen_path
        
        # Limpiar y dividir texto
        palabras = texto.split()
        if len(palabras) > 14:
            texto_sub = ' '.join(palabras[:14])
        else:
            texto_sub = texto
        
        # Dividir en 2 líneas si es largo
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
            x = (1080 - ancho) // 2
            y = y_base + i * 55
            
            draw.text((x + 3, y + 3), linea, fill='black', font=font)
            draw.text((x, y), linea, fill='white', font=font)
        
        img.save(salida_path)
        return salida_path
        
    except Exception as e:
        print(f"⚠️ Error en subtítulos: {e}")
        return imagen_path

# ================================================================
# 🎬 MONTAR VIDEO
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
                r = requests.get(img_url, timeout=30)
                r.raise_for_status()
                img_path = f"temp_cap_{i}.jpg"
                with open(img_path, "wb") as f:
                    f.write(r.content)
            else:
                img_path = img_url
            
            img_sub_path = f"temp_cap_sub_{i}.jpg"
            img_path = agregar_subtitulos_con_pil(img_path, texto, img_sub_path)
            
            img = Image.open(img_path)
            img = ImageOps.fit(img, (1080, 1920), Image.Resampling.LANCZOS)
            img.save(img_path)
            video_clip = ImageClip(img_path).set_duration(duracion)
        except Exception as e:
            print(f"⚠️ Falló imagen {i}: {e}")
            img_path = f"placeholder_{i}.jpg"
            img = Image.new("RGB", (1080, 1920), (20, 20, 50))
            img.save(img_path)
            video_clip = ImageClip(img_path).set_duration(duracion)
        
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
            sil = AudioClip(lambda t: 0, duration=PAUSA)
            audio_final_parts.append(sil)
    
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
        if f.startswith("temp_cap_") and f.endswith(".jpg"):
            try: os.remove(f)
            except: pass
        if f.startswith("placeholder_") and f.endswith(".jpg"):
            try: os.remove(f)
            except: pass
    
    return salida

# ================================================================
# 🚀 SUBIR A YOUTUBE (SIN MINIATURA PERSONALIZADA)
# ================================================================
def subir_a_youtube(video_path, titulo, etiquetas, gancho, contexto, hashtags, fuente=""):
    try:
        creds = Credentials.from_authorized_user_info(YOUTUBE_USER_TOKEN)
        youtube = build("youtube", "v3", credentials=creds)
    except Exception as e:
        print(f"❌ Error autenticando: {e}")
        sys.exit(1)
    
    if isinstance(etiquetas, str):
        etiquetas = [t.strip() for t in etiquetas.split(",") if t.strip()]
    
    # Descripción con disclaimer corto
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
            "tags": etiquetas[:30],
            "categoryId": "27",
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
    
    print("🖼️ YouTube seleccionará automáticamente la miniatura del video.")
    
    return video_id

# ================================================================
# 🎯 MAIN
# ================================================================
def main():
    print("="*60)
    print("🎬 Capital Digital - Bot de SHORTS (Versión FINAL)")
    print("   ✓ Voz fija (Jorge) - velocidad +10%")
    print("   ✓ 90-110 palabras por video")
    print("   ✓ Sin miniatura personalizada")
    print("   ✓ Reutilización de imágenes")
    print("   ✓ 30+ temas por categoría")
    print("   ✓ Rotación forzada: Noticia → Educativo → Estafa")
    print("   ✓ Subtítulos con PIL (robusto)")
    print("   ✓ Pausas de 15s entre segmentos")
    print("="*60)
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🎤 Voz: {CONFIG_VOZ_ACTUAL['nombre']}")
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
    print(f"🎬 Video generado: {video_path}")
    
    print("🖼️ Usando miniatura automática de YouTube.")
    
    video_id = subir_a_youtube(
        video_path=video_path,
        titulo=guion["titulo"],
        etiquetas=guion["tags"],
        gancho=guion["gancho_descripcion"],
        contexto=guion["contexto_descripcion"],
        hashtags=guion["hashtags_descripcion"],
        fuente=guion.get("fuente_relato", "Basado en análisis financiero")
    )
    
    guardar_titulo_publicado(guion["titulo"])
    guardar_tema_publicado(tema_elegido, tipo)
    incrementar_publicaciones_hoy()
    guardar_estado(estado)
    
    print("✅ Short publicado exitosamente!")
    print(f"🔗 https://youtu.be/{video_id}")
    print("="*60)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ Error fatal: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
