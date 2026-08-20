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
    CompositeVideoClip,
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
ESTADO_FILE = "estado_capital_largos.json"
TITULOS_FILE = "titulos_capital_largos_publicados.json"
TEMAS_PUBLICADOS_FILE = "temas_largos_publicados.json"
META_DIARIA_LARGOS = 1
DIAS_SIN_REPETIR_TEMA = 45

# ================================================================
# VOZ FIJA (Jorge) - +10% para ritmo dinámico
# ================================================================
VOZ_FIJA = {"voz": "es-MX-JorgeNeural", "velocidad": "+10%", "tono": "-1Hz", "nombre": "Jorge (MX)"}
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

def tema_ya_publicado(tema, dias=45):
    temas = cargar_temas_publicados()
    hoy = datetime.now(pytz.timezone("America/Mexico_City")).date()
    for t in temas:
        if t["tema"].lower() == tema.lower():
            fecha_tema = datetime.strptime(t["fecha"], "%Y-%m-%d").date()
            if (hoy - fecha_tema).days < dias:
                return True
    return False

# ================================================================
# TREND-JACKING CON NOTICIAS DEL DÍA ACTUAL
# ================================================================
def obtener_tema_trending():
    try:
        url = "https://newsapi.org/v2/top-headlines"
        params = {
            "category": "business",
            "language": "es",
            "apiKey": NEWSAPI_KEY,
            "pageSize": 10,
            "country": "mx"
        }
        r = requests.get(url, params=params, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data.get("articles"):
                for article in data["articles"]:
                    title = article.get("title", "")
                    # Filtrar noticias con fechas pasadas
                    if not re.search(r'20[0-2][0-9]', title):
                        keywords = ["bitcoin", "cripto", "oro", "etf", "inflación", "banco", "finanzas", "dólar", "peso", "shiba", "dogecoin", "ethereum", "solana", "ftx", "binance", "exchange"]
                        if any(word in title.lower() for word in keywords):
                            return title[:100]
                # Si no encuentra con keywords, devuelve el primero sin fecha pasada
                for article in data["articles"]:
                    title = article.get("title", "")
                    if not re.search(r'20[0-2][0-9]', title):
                        return title[:100]
        return None
    except Exception as e:
        print(f"⚠️ Error obteniendo trending: {e}")
        return None

# ================================================================
# 🔥 GENERACIÓN DE IDEAS CON FECHA ACTUAL
# ================================================================
def generar_idea_video_largo(tipo, fecha_actual):
    prompt = f"""
Eres un ESTRATEGA DE CONTENIDO VIRAL para YouTube en el nicho de finanzas/cripto.

📅 FECHA ACTUAL: {fecha_actual}
⚠️ IMPORTANTE: NO uses fechas pasadas como 2020, 2021, 2022, 2023 o 2024.
   Usa la fecha actual ({fecha_actual}) o referencias como "hoy", "esta semana".

Tu tarea es generar 5 IDEAS DE VIDEO (para formato LARGO, 7-9 minutos) que sigan estos principios:
1. RESTRICCIÓN: El creador se impone una limitación (ej. "invertir solo $100").
2. DESAFÍO: Objetivo medible (ej. "llegar a $10,000 en 30 días").
3. TRANSFORMACIÓN: Antes y después (ej. "de deudas a inversor").

TIPO DE CONTENIDO: {tipo} (educativo, estafa, psicologia, analisis, noticia)

Para cada idea, escribe:
- Título (60-70 caracteres, con emoji y palabra clave, que genere CURIOSIDAD).
- Descripción de 1-2 líneas explicando la restricción/desafío.
- Nivel de curiosidad (1-10).

Luego ELIGE LA MEJOR IDEA (la que genera más curiosidad) y devuélvela.

RESPUESTA EN JSON:
{{
    "mejor_idea": {{
        "titulo": "Título final con curiosidad (sin fechas pasadas)",
        "descripcion": "Descripción de la idea",
        "restriccion": "Cuál es la restricción o desafío",
        "tipo": "{tipo}"
    }},
    "ideas_generadas": [
        {{"titulo": "...", "descripcion": "...", "curiosidad": 8}},
        ...
    ]
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
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=60)
        r.raise_for_status()
        data = r.json()
        content = data["choices"][0]["message"]["content"]
        inicio = content.find("{")
        fin = content.rfind("}")
        json_str = content[inicio:fin+1]
        return json.loads(json_str)
    except Exception as e:
        print(f"⚠️ Error generando ideas: {e}")
        return None

# ================================================================
# SANITIZAR TAGS PARA YOUTUBE
# ================================================================
def sanitizar_tags(tags_str, max_chars=500):
    if not tags_str:
        return []
    raw_tags = [t.strip() for t in tags_str.split(",") if t.strip()]
    cleaned_tags = []
    for tag in raw_tags:
        clean = re.sub(r'[^a-zA-Z0-9áéíóúüñÁÉÍÓÚÜÑ\s\-]', '', tag)
        clean = clean.strip()
        if clean and len(clean) > 1:
            cleaned_tags.append(clean)
    cleaned_tags = list(dict.fromkeys(cleaned_tags))
    current = ""
    for tag in cleaned_tags:
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
# EXPANSIÓN DE GUION LARGO
# ================================================================
def expandir_guion_largo(guion_corto, tema, restriccion, fecha_actual):
    prompt = f"""
Eres un GUIONISTA PROFESIONAL. El siguiente guion es demasiado corto. 
EXPÁNDELO a 1300-1500 palabras, manteniendo el arco de DESAFÍO → PROCESO → RESULTADO.
Añade:
- Más ejemplos concretos relacionados con la restricción.
- Datos y estadísticas relevantes (sin fechas pasadas).
- Analogías y comparaciones.
- Obstáculos y momentos de tensión.
- Conclusión y reflexión final.

📅 FECHA ACTUAL: {fecha_actual}
⚠️ NO uses fechas pasadas (2020, 2021, 2022, 2023, 2024).

TEMA: {tema}
RESTRICCIÓN/DESAFÍO: {restriccion}

GUION ACTUAL:
{guion_corto}

DEVUELVE SOLO EL TEXTO DEL GUION EXPANDIDO, con los mismos bloques [HOOK], [INTRO], [PROBLEMA], [DESARROLLO], [SOLUCION], [CIERRE].
"""
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.8,
        "max_tokens": 4000,
    }
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=120)
        r.raise_for_status()
        expanded = r.json()["choices"][0]["message"]["content"].strip()
        palabras = len(re.findall(r'\w+', expanded))
        if palabras > 1100:
            print(f"✅ Expansión exitosa: {palabras} palabras")
            return expanded
        else:
            print(f"⚠️ Expansión insuficiente ({palabras} palabras)")
            return None
    except Exception as e:
        print(f"❌ Error en expansión: {e}")
        return None

# ================================================================
# 🔥 GENERAR GUION LARGO CON FECHA ACTUAL
# ================================================================
def generar_guion_largo(tipo, fecha_actual, idea=None):
    titulos_pub = cargar_titulos_publicados()["titulos"][-10:]
    titulos_referencia = "\n".join([f"- {t}" for t in titulos_pub]) if titulos_pub else "Ninguno aún."

    TEMAS_EDUCATIVOS = [
        "Cómo Invertir en Criptomonedas con Seguridad (Guía Completa)",
        "Bitcoin y Oro: Refugios en Crisis Económica",
        "Análisis Técnico vs Fundamental: Cuál es mejor para ti",
        "Los 5 Niveles Financieros que te llevarán a la Riqueza",
        "Cómo Funciona el Interés Compuesto y por qué te empobrece no usarlo",
        "Estrategias de Diversificación de Portafolio",
        "Cómo Identificar una Criptomoneda con Potencial (Fundamentals)",
        "Finanzas Descentralizadas (DeFi): Oportunidades y Riesgos",
        "Cómo Leer un Gráfico de Trading (Guía para Principiantes)",
        "Inversión Pasiva vs Activa: Cuál te conviene más"
    ]
    TEMAS_ESTAFAS_CRISIS = [
        "El Colapso de FTX: Lecciones Aprendidas",
        "Cómo Detectar Estafas Piramidales en Cripto",
        "El Caso Enron: La Mayor Estafa Corporativa",
        "La Crisis de las Hipotecas Subprime y su Paralelismo con Cripto",
        "Mt. Gox: El Robo de Bitcoin que Cambió Todo",
        "Estafa de OneCoin: El Bitcoin Falso que Engañó al Mundo",
        "Manipulación del Mercado: Cómo los Grandes Mueven los Precios",
        "Alertas de Scams en Exchanges (Casos Reales)"
    ]
    TEMAS_PSICOLOGIA = [
        "FOMO y Pánico: Cómo Dominar tus Emociones en el Trading",
        "Los 4 Bugs Mentales que te Mantienen Pobre (y cómo arreglarlos)",
        "Disciplina vs Dinero: Los Hábitos de los Ricos",
        "Mentalidad de Riqueza: Cómo Atraer el Dinero",
        "Deja de ser Esclavo del Sueldo: 3 Pasos para la Libertad Financiera"
    ]
    TEMAS_ANALISIS = [
        "Análisis SHIBA INU: ¿Llegará a 1 Centavo?",
        "Bitcoin Análisis: ¿Preparado para el Siguiente ATH?",
        "Ethereum vs Solana: ¿Quién Ganará en el Futuro?",
        "Helium (HNT): Minería sin Tarjetas Gráficas, ¿Vale la Pena?",
        "Bittorrent (BTT): El Gigante Dormido del Almacenamiento",
        "Nuevas Altcoins con Potencial X10 (Análisis de Proyectos)"
    ]

    # Si no hay idea, generar una
    if not idea:
        print("💡 Generando idea con restricción/desafío...")
        idea_data = generar_idea_video_largo(tipo, fecha_actual)
        if idea_data and "mejor_idea" in idea_data:
            idea = idea_data["mejor_idea"]
            print(f"   ✅ Idea seleccionada: {idea['titulo']}")
            print(f"   🔥 Restricción: {idea['restriccion']}")
        else:
            print("⚠️ No se generó idea, usando tema de respaldo.")
            if tipo == "noticia":
                trending = obtener_tema_trending()
                if trending:
                    idea = {"titulo": trending, "restriccion": "Noticia del día"}
                else:
                    idea = {"titulo": random.choice(TEMAS_EDUCATIVOS), "restriccion": "Educación financiera"}
            elif tipo == "educativo":
                idea = {"titulo": random.choice(TEMAS_EDUCATIVOS), "restriccion": "Concepto financiero"}
            elif tipo == "estafa":
                idea = {"titulo": random.choice(TEMAS_ESTAFAS_CRISIS), "restriccion": "Caso real"}
            elif tipo == "psicologia":
                idea = {"titulo": random.choice(TEMAS_PSICOLOGIA), "restriccion": "Psicología financiera"}
            else:
                idea = {"titulo": random.choice(TEMAS_ANALISIS), "restriccion": "Análisis de mercado"}

    tema_elegido = idea["titulo"]
    restriccion = idea.get("restriccion", "Desafío financiero")

    prompt = f"""
Eres un GUIONISTA PROFESIONAL y EXPERTO EN FINANZAS. Debes escribir un guion DETALLADO para un video de YouTube de 7-9 minutos.

📌 IDEA DEL VIDEO: "{tema_elegido}"
📌 RESTRICCIÓN/DESAFÍO: "{restriccion}"
📌 TIPO: {tipo}
📅 FECHA ACTUAL: {fecha_actual}

⚠️ REGLA DE FECHAS (MUY IMPORTANTE):
   - NO uses fechas pasadas como 2020, 2021, 2022, 2023 o 2024.
   - Si necesitas mencionar un año, usa el año actual: {fecha_actual.split()[-1]}.
   - Para eventos recientes, di "hoy", "esta semana" o "en los últimos días".

🎯 REGLA DE ORO (CRÍTICA):
- El guion DEBE tener entre 1300 y 1500 palabras.
- Si el guion tiene menos de 1200 palabras, el video será demasiado corto.
- Cada bloque debe tener el largo indicado.

🎯 ESTRUCTURA OBLIGATORIA (basada en DESAFÍO → PROCESO → RESULTADO):
[HOOK - 0:00] Presenta el desafío de forma impactante (ej. "Voy a intentar X en 30 días").
[INTRO - 0:15] Explica por qué este desafío es interesante y qué se necesita. (150-200 palabras)
[PROBLEMA - 1:30] Muestra los obstáculos iniciales, dudas, miedos. (200-250 palabras)
[DESARROLLO - 3:00] El proceso paso a paso, con momentos de tensión y aprendizajes. (300-350 palabras)
[SOLUCION - 5:00] La estrategia usada para superar los obstáculos, el clímax. (250-300 palabras)
[CIERRE - 7:00] Resultado final (¿se logró o no?), reflexión y CTA. (200-250 palabras)

🎯 REGLA DE ORO PARA NÚMEROS:
- NUNCA uses números con comas: "400,500" o "50,100".
- SIEMPRE escribe los números con LETRAS: "cuatrocientos", "cincuenta".
- Para rangos, usa "entre X y Y".

🎯 INSTRUCCIONES ADICIONALES:
- Usa un tono coloquial, como si hablaras con un amigo.
- Incluye preguntas retóricas y analogías.
- NO uses fechas específicas pasadas.

🎯 IMÁGENES (prompts en inglés):
Cada bloque tendrá un prompt de imagen específico para Agnes.
- Estilo: cinematográfico, neón, 8k.
- PROHIBIDO: personas, rostros, caras en primer plano.
- Permitido: gráficos, monedas, datos, visualizaciones, mapas, tecnología.

🎯 🖼️ DISEÑO DE LA MINIATURA (IMPORTANTE):
Crea un prompt en INGLÉS para que Agnes genere el FONDO de la miniatura. El fondo debe reflejar el DESAFÍO.
- Estilo: "crypto YouTube thumbnail", neón, high contrast, cinematic, hyperrealistic.
- PROHIBIDO: personas, rostros, caras, textos.
- Permitido: una meta visual (ej. una moneda gigante, un gráfico ascendente, un camino con una X al final).
- Tamaño: 1280x720 (horizontal).

🚫 TÍTULOS YA PUBLICADOS (NO REPETIR):
{titulos_referencia}

📤 RESPUESTA EN JSON:
{{
    "titulo": "Título con emoji y curiosidad (60-70 chars, sin fechas pasadas)",
    "titulo_alternativo": "Título alternativo",
    "palabras_clave": ["kw1", "kw2", "kw3", "kw4", "kw5"],
    "descripcion": "Descripción completa con capítulos y hashtags, incluyendo el desafío",
    "tags": "25-30 tags separados por coma (SIN caracteres especiales, sin fechas)",
    "hashtags": "#hashtag1 #hashtag2",
    "guion": "Guion completo de 1300-1500 palabras con los 6 bloques marcados",
    "segmentos": [
        {{"bloque": "HOOK", "texto": "texto (~10 palabras)", "prompt_imagen": "prompt en inglés SIN PERSONAS"}},
        {{"bloque": "INTRO", "texto": "texto (~150-200 palabras)", "prompt_imagen": "prompt en inglés"}},
        {{"bloque": "PROBLEMA", "texto": "texto (~200-250 palabras)", "prompt_imagen": "prompt en inglés"}},
        {{"bloque": "DESARROLLO", "texto": "texto (~300-350 palabras)", "prompt_imagen": "prompt en inglés"}},
        {{"bloque": "SOLUCION", "texto": "texto (~250-300 palabras)", "prompt_imagen": "prompt en inglés"}},
        {{"bloque": "CIERRE", "texto": "texto (~200-250 palabras)", "prompt_imagen": "prompt en inglés"}}
    ],
    "palabras_portada": "2-3 palabras para el texto de la miniatura (ej. 'LO LOGRO', 'EL DESAFIO')",
    "prompt_miniatura": "Prompt en inglés para el fondo de la miniatura (SIN texto, SIN personas, 1280x720)"
}}
"""
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.8,
        "max_tokens": 4000,
        "response_format": {"type": "json_object"}
    }
    for intento in range(3):
        try:
            print(f"🔄 Generando guion (intento {intento+1}/3)...")
            r = requests.post(url, headers=headers, json=payload, timeout=150)
            r.raise_for_status()
            data = r.json()
            content = data["choices"][0]["message"]["content"]
            inicio = content.find("{")
            fin = content.rfind("}")
            json_str = content[inicio:fin+1]
            result = json.loads(json_str)
            
            guion_texto = result.get("guion", "")
            palabras = len(re.findall(r'\w+', guion_texto))
            print(f"📊 Palabras del guion: {palabras}")
            
            if palabras < 1100:
                print(f"⚠️ Guion corto ({palabras} palabras). Expandiendo...")
                guion_expandido = expandir_guion_largo(guion_texto, tema_elegido, restriccion, fecha_actual)
                if guion_expandido:
                    result["guion"] = guion_expandido
                    palabras = len(re.findall(r'\w+', guion_expandido))
                    print(f"📊 Guion expandido: {palabras} palabras")
                else:
                    print("❌ Falló la expansión, usando guion original")
            
            if palabras < 900:
                print(f"⚠️ Guion aún corto ({palabras} palabras). Reduciendo velocidad de voz a +5%.")
                global VOZ_FIJA
                VOZ_FIJA = {"voz": "es-MX-JorgeNeural", "velocidad": "+5%", "tono": "-1Hz", "nombre": "Jorge (MX)"}
                CONFIG_VOZ_ACTUAL = VOZ_FIJA
            
            if "prompt_miniatura" not in result:
                result["prompt_miniatura"] = f"cinematic wide shot of a glowing path leading to a golden Bitcoin, neon cyan and gold lighting, high contrast, dark background, hyperrealistic, 8k, no people, no text, no watermark"
            
            return result, tema_elegido, restriccion
        except Exception as e:
            print(f"❌ Intento {intento+1}/3 falló: {e}")
            time.sleep(10)
    print("❌ Error generando guion después de 3 intentos")
    sys.exit(1)

# ================================================================
# FILTRAR PROMPT DE MINIATURA (evitar rechazo de Agnes)
# ================================================================
def filtrar_prompt_miniatura(prompt):
    if not prompt:
        return prompt
    palabras_sensibles = {
        r'\bcrash\b': 'market drop', r'\bcollapse\b': 'decline',
        r'\bburning\b': 'glowing', r'\bfire\b': 'bright light',
        r'\bexplosion\b': 'burst', r'\bexplosive\b': 'intense',
        r'\bwreckage\b': 'ruins', r'\bdestroyed\b': 'damaged',
        r'\bwar\b': 'conflict', r'\bbattle\b': 'struggle',
        r'\bblood\b': 'red', r'\bscam\b': 'deception',
        r'\bfraud\b': 'fraudulent scheme', r'\bpanic\b': 'fear',
        r'\bdisaster\b': 'crisis', r'\bcatastrophe\b': 'tragedy',
        r'\bcrisis\b': 'challenge', r'\bdeath\b': 'end',
        r'\bkill\b': 'eliminate', r'\bgun\b': 'weapon',
        r'\bexplode\b': 'burst', r'\bflames\b': 'light',
    }
    prompt_filtrado = prompt
    for patron, reemplazo in palabras_sensibles.items():
        prompt_filtrado = re.sub(patron, reemplazo, prompt_filtrado, flags=re.IGNORECASE)
    if len(prompt_filtrado.split()) < 10:
        return "cinematic wide shot of glowing financial charts and golden coins, neon cyan and gold lighting, high contrast, dark background, hyperrealistic, 8k, no people, no text, no watermark"
    return prompt_filtrado

# ================================================================
# GENERAR IMAGEN HORIZONTAL (16:9) CON REINTENTOS
# ================================================================
def generar_imagen_horizontal(prompt, intentos=3):
    prompt = prompt[:950]
    prompt_completo = f"{prompt}, hyperrealistic, 8k, cinematic lighting, electric cyan neon, high contrast, sharp focus, wide shot, environment as main subject, no close-up face, no text, no watermark"
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
            print(f"   🖼️ Enviando prompt a Agnes (intento {intento+1}/{intentos})...")
            print(f"   📝 Prompt completo: {prompt_completo[:300]}...")
            r = requests.post(url, headers=headers, json=payload, timeout=120)
            if r.status_code == 200:
                data = r.json()
                if data.get("data") and len(data["data"]) > 0:
                    print(f"   ✅ Imagen generada exitosamente en intento {intento+1}.")
                    return data["data"][0]["url"]
            else:
                print(f"   ⚠️ Error {r.status_code} - {r.text[:400]}")
        except Exception as e:
            print(f"   ⚠️ Error conexión: {e}")
        if intento < intentos - 1:
            print("   ⏳ Esperando 10 segundos antes de reintentar...")
            time.sleep(10)
    return None

# ================================================================
# GENERAR FONDO SÓLIDO (fallback)
# ================================================================
def generar_fondo_solido(color=(20, 20, 50), ancho=1280, alto=720):
    img = Image.new('RGB', (ancho, alto), color)
    path = f"temp_fondo_{random.randint(1000,9999)}.jpg"
    img.save(path)
    return path

# ================================================================
# MINIATURA PROFESIONAL MEJORADA
# ================================================================
def crear_miniatura_profesional(prompt_miniatura, texto_portada, salida="miniatura_largo.jpg"):
    print("🖼️ Generando miniatura profesional...")
    prompt_filtrado = filtrar_prompt_miniatura(prompt_miniatura)
    print(f"   📝 Prompt original: {prompt_miniatura[:200]}...")
    print(f"   📝 Prompt filtrado: {prompt_filtrado[:200]}...")

    prompts_a_intentar = [
        prompt_filtrado,
        "cinematic wide shot of glowing financial charts and golden coins, neon cyan and gold lighting, high contrast, dark background, hyperrealistic, 8k, no people, no text, no watermark",
        "dramatic wide shot of stock market graphs and city skyline, blue and gold lighting, professional photography, sharp focus, no text, no watermark"
    ]

    fondo_url = None
    for intento, prompt in enumerate(prompts_a_intentar[:3], start=1):
        print(f"   🖼️ Intento {intento}/3 generando miniatura...")
        fondo_url = generar_imagen_horizontal(prompt, intentos=1)
        if fondo_url:
            break
        if intento < 3:
            print("   ⏳ Esperando 10 segundos...")
            time.sleep(10)

    if not fondo_url:
        print("⚠️ No se pudo generar fondo, usando placeholder")
        fondo_path = generar_fondo_solido()
        fondo_url = fondo_path

    try:
        if fondo_url.startswith("http"):
            try:
                r = requests.get(fondo_url, timeout=30)
                r.raise_for_status()
                img_path = "temp_thumb_fondo.jpg"
                with open(img_path, "wb") as f:
                    f.write(r.content)
            except Exception as e:
                print(f"⚠️ Error descargando fondo: {e}")
                fondo_path = generar_fondo_solido()
                img_path = fondo_path
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
        
        # Fuente grande para impacto
        try:
            font = ImageFont.truetype("fonts/Anton.ttf", 130)
        except:
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/msttcorefonts/Impact.ttf", 130)
            except:
                try:
                    font = ImageFont.truetype("Impact.ttf", 130)
                except:
                    font = ImageFont.load_default()
        
        bbox = draw.textbbox((0, 0), texto, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        x = (1280 - text_w) // 2
        y = (720 - text_h) // 2 + 60
        
        # Fondo neón detrás del texto
        padding = 40
        bg_x = x - padding
        bg_y = y - padding - 10
        bg_w = text_w + padding * 2
        bg_h = text_h + padding * 2 + 20
        overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        overlay_draw.rectangle([bg_x, bg_y, bg_x + bg_w, bg_y + bg_h], fill=(0, 0, 0, 200))
        overlay_draw.rectangle([bg_x-3, bg_y-3, bg_x+bg_w+3, bg_y+bg_h+3], outline=(0, 200, 255, 180), width=4)
        img = Image.alpha_composite(img.convert('RGBA'), overlay).convert('RGB')
        draw = ImageDraw.Draw(img)
        
        # Sombra gruesa
        for dx, dy in [(-5, -5), (-5, 5), (5, -5), (5, 5), (0, 8), (0, -8), (8, 0), (-8, 0)]:
            draw.text((x + dx, y + dy), texto, fill='black', font=font)
        # Borde blanco
        for dx, dy in [(-2, -2), (-2, 2), (2, -2), (2, 2)]:
            draw.text((x + dx, y + dy), texto, fill='white', font=font)
        # Texto principal en AMARILLO NEÓN
        draw.text((x, y), texto, fill=(255, 255, 80), font=font)
        
        img.save(salida)
        print(f"✅ Miniatura profesional creada: {salida}")
        return salida
    except Exception as e:
        print(f"⚠️ Error en miniatura profesional: {e}")
        return None

# ================================================================
# SUBTÍTULOS CON PIL (16:9) - TAMAÑO 28px
# ================================================================
def agregar_subtitulos_con_pil_16_9(imagen_path, texto, salida_path):
    try:
        img = Image.open(imagen_path)
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
        except:
            try:
                font = ImageFont.truetype("arial.ttf", 28)
            except:
                font = ImageFont.load_default()
        
        palabras = texto.split()
        if len(palabras) > 20:
            texto_sub = ' '.join(palabras[:20])
        else:
            texto_sub = texto
        
        if len(texto_sub) > 60:
            mitad = len(texto_sub) // 2
            espacio = texto_sub.find(' ', mitad - 10)
            if espacio == -1:
                espacio = mitad
            linea1 = texto_sub[:espacio]
            linea2 = texto_sub[espacio+1:]
            lineas = [linea1, linea2]
        else:
            lineas = [texto_sub]
        
        y_base = 720 - 80 - (len(lineas) - 1) * 35
        for i, linea in enumerate(lineas):
            bbox = draw.textbbox((0, 0), linea, font=font)
            ancho = bbox[2] - bbox[0]
            x = (1280 - ancho) // 2
            y = y_base + i * 35
            
            draw.text((x+2, y+2), linea, fill='black', font=font)
            draw.text((x, y), linea, fill='white', font=font)
        
        img.save(salida_path)
        return salida_path
    except Exception as e:
        print(f"⚠️ Error subtítulos: {e}")
        return imagen_path

# ================================================================
# GENERAR AUDIO
# ================================================================
def generar_audio(texto, index):
    global CONFIG_VOZ_ACTUAL
    texto_limpio = re.sub(r'[^a-zA-ZáéíóúüñÁÉÍÓÚÜÑ0-9\s.,;:!?¿¡\'\"]', '', texto)
    texto_limpio = re.sub(r'\s+', ' ', texto_limpio).strip()
    
    filename = f"audio_largo_{index}.mp3"
    voz = CONFIG_VOZ_ACTUAL["voz"]
    rate = CONFIG_VOZ_ACTUAL["velocidad"]
    pitch = CONFIG_VOZ_ACTUAL["tono"]
    
    async def _gen():
        communicate = edge_tts.Communicate(texto_limpio, voz, rate=rate, pitch=pitch)
        await communicate.save(filename)
    
    try:
        asyncio.run(_gen())
        return filename
    except Exception as e:
        print(f"❌ Error audio: {e}")
        return None

# ================================================================
# CAPÍTULOS VISUALES CON PIL (TAMAÑO 14px)
# ================================================================
def crear_capitulo_visual_pil(titulo_capitulo, timestamp, duracion=3, ancho=1280, alto=720):
    try:
        img = Image.new('RGBA', (ancho, alto), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        texto = f"{timestamp} - {titulo_capitulo.upper()}"
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14)
        except:
            try:
                font = ImageFont.truetype("arial.ttf", 14)
            except:
                font = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), texto, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        x = 20
        y = 15
        padding = 8
        bg_x = x - padding
        bg_y = y - padding
        bg_w = text_w + padding * 2
        bg_h = text_h + padding * 2
        overlay = Image.new('RGBA', (ancho, alto), (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        overlay_draw.rectangle([bg_x, bg_y, bg_x + bg_w, bg_y + bg_h], fill=(0, 0, 0, 160))
        overlay_draw.rectangle([bg_x, bg_y, bg_x + bg_w, bg_y + bg_h], outline=(0, 180, 255, 80), width=1)
        img = Image.alpha_composite(img, overlay)
        draw = ImageDraw.Draw(img)
        draw.text((x+1, y+1), texto, fill='black', font=font)
        draw.text((x, y), texto, fill='white', font=font)
        temp_path = f"temp_capitulo_{timestamp.replace(':', '')}.png"
        img.save(temp_path)
        clip = ImageClip(temp_path, duration=duracion, transparent=True)
        clip = clip.crossfadein(0.3).crossfadeout(0.3)
        return clip
    except Exception as e:
        print(f"⚠️ Error creando capítulo visual con PIL: {e}")
        return None

# ================================================================
# CTA FINAL "SUSCRÍBETE" CON PIL (TAMAÑO 40px)
# ================================================================
def crear_cta_final_pil(duracion=3, ancho=1280, alto=720):
    try:
        img = Image.new('RGB', (ancho, alto), (15, 15, 20))
        draw = ImageDraw.Draw(img)
        texto = "🔴 SUSCRÍBETE"
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 40)
        except:
            try:
                font = ImageFont.truetype("arial.ttf", 40)
            except:
                font = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), texto, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        x = (ancho - text_w) // 2
        y = (alto - text_h) // 2
        for dx, dy in [(-2, -2), (-2, 2), (2, -2), (2, 2)]:
            draw.text((x + dx, y + dy), texto, fill='black', font=font)
        draw.text((x, y), texto, fill=(255, 50, 50), font=font)
        temp_path = "temp_cta.png"
        img.save(temp_path)
        clip = ImageClip(temp_path, duration=duracion)
        clip = clip.crossfadein(0.5)
        return clip
    except Exception as e:
        print(f"⚠️ Error creando CTA con PIL: {e}")
        return None

# ================================================================
# MONTAR VIDEO (CON ORDEN CORREGIDO)
# ================================================================
def montar_video_largo(recursos, fondo_path, salida="largo_capital.mp4", capitulos=None):
    if not recursos:
        raise ValueError("No hay recursos")
    
    clips_video = []
    clips_audio = []
    
    for i, rec in enumerate(recursos):
        img_url = rec["imagen_url"]
        audio_path = rec["audio_path"]
        duracion = rec["duracion"]
        texto = rec.get("texto", "")
        bloque = rec.get("bloque", "")
        
        try:
            if img_url.startswith("http"):
                try:
                    r = requests.get(img_url, timeout=30)
                    r.raise_for_status()
                    img_path = f"temp_largo_{i}.jpg"
                    with open(img_path, "wb") as f:
                        f.write(r.content)
                except Exception as e:
                    print(f"⚠️ Falló descarga de imagen {i}: {e}")
                    img_path = generar_fondo_solido()
            else:
                img_path = img_url
            
            img = Image.open(img_path)
            img = ImageOps.fit(img, (1280, 720), Image.Resampling.LANCZOS)
            img.save(img_path)
            
            img_sub_path = f"temp_largo_sub_{i}.jpg"
            img_path = agregar_subtitulos_con_pil_16_9(img_path, texto, img_sub_path)
            
            video_clip = (ImageClip(img_path)
                         .resize(lambda t: 1 + 0.015 * t)
                         .set_duration(duracion))
        except Exception as e:
            print(f"⚠️ Falló imagen {i}: {e}")
            img_path = generar_fondo_solido()
            video_clip = ImageClip(img_path, duration=duracion).resize(lambda t: 1 + 0.015 * t)
        
        if capitulos and i < len(capitulos):
            cap_titulo = capitulos[i].get("bloque", "")
            cap_timestamp = f"{i:02d}:00" if i < 10 else f"{i}:00"
            cap_clip = crear_capitulo_visual_pil(cap_titulo, cap_timestamp, duracion=3)
            if cap_clip:
                video_clip = CompositeVideoClip([video_clip, cap_clip])
        
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
    
    cta_clip = crear_cta_final_pil(duracion=3)
    if cta_clip:
        video = concatenate_videoclips([video, cta_clip], method="compose")
        duracion_total += 3
    
    if fondo_path and os.path.exists(fondo_path):
        try:
            fondo_clip = AudioFileClip(fondo_path)
            if fondo_clip.duration < duracion_total:
                veces = int(duracion_total / fondo_clip.duration) + 1
                fondo_clip = concatenate_audioclips([fondo_clip] * veces)
            fondo_clip = fondo_clip.subclip(0, duracion_total).volumex(0.05)
            audio_final = CompositeAudioClip([audio_narracion, fondo_clip])
        except:
            audio_final = audio_narracion
    else:
        audio_final = audio_narracion
    
    video = video.set_audio(audio_final)
    video.write_videofile(salida, fps=24, codec="libx264", audio_codec="aac", threads=4, preset="ultrafast")
    return salida

# ================================================================
# SUBIR A YOUTUBE (CON CATEGORÍA 22: PERSONAS Y BLOGS)
# ================================================================
def subir_a_youtube(video_path, titulo, etiquetas_str, descripcion, miniatura_path=None):
    try:
        creds = Credentials.from_authorized_user_info(YOUTUBE_USER_TOKEN)
        youtube = build("youtube", "v3", credentials=creds)
    except Exception as e:
        print(f"❌ Error autenticando: {e}")
        sys.exit(1)
    
    tags = sanitizar_tags(etiquetas_str)
    print(f"📝 Tags sanitizados: {len(tags)} tags, {sum(len(t)+1 for t in tags)} caracteres aprox.")
    
    disclaimer = "\n\n⚠️ AVISO IMPORTANTE: Este contenido es solo para fines educativos no constituye asesoría financiera, legal o de inversión."
    descripcion_final = descripcion + disclaimer
    
    body = {
        "snippet": {
            "title": titulo[:100],
            "description": descripcion_final[:5000],
            "tags": tags[:30],
            "categoryId": "22",
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
    print(f"✅ Video largo subido: https://youtu.be/{video_id}")
    
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
        "temp_*.jpg", "temp_*.mp3", "audio_largo_*.mp3",
        "temp_thumb*.jpg", "miniatura_largo.jpg", "largo_capital.mp4",
        "placeholder*.jpg", "temp_*.png", "temp_capitulo_*.png",
        "temp_cta.png", "temp_fondo_*.jpg"
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
    print("🎬 Capital Digital - Bot de VIDEOS LARGOS (ESTRATEGIA YAYAS)")
    print("   ✓ Generación de ideas con restricción/desafío")
    print("   ✓ Estructura de desafío-proceso-resultado")
    print("   ✓ Títulos con curiosidad (sin fechas pasadas)")
    print("   ✓ Miniatura mejorada con texto neón")
    print("   ✓ Pausas de 10s entre generaciones")
    print("   ✓ Noticias del día actual (NewsAPI)")
    print("   ✓ Categoría: Personas y Blogs (22)")
    print("="*60)

    # 🔥 OBTENER FECHA ACTUAL
    tz_mexico = pytz.timezone("America/Mexico_City")
    fecha_actual = datetime.now(tz_mexico)
    fecha_formateada = fecha_actual.strftime("%d de %B de %Y")
    print(f"📅 Fecha actual: {fecha_formateada}")
    print("="*60)
    
    if not YOUTUBE_USER_TOKEN:
        print("❌ Falta YOUTUBE_USER_TOKEN_CAPITAL")
        sys.exit(1)
    
    publicadas = obtener_publicaciones_hoy()
    if publicadas >= META_DIARIA_LARGOS:
        print("✅ Ya se publicó el video largo hoy. Saliendo.")
        sys.exit(0)
    
    tipos = ["noticia", "educativo", "estafa", "psicologia", "analisis"]
    tipo = random.choice(tipos)
    print(f"📌 Tipo: {tipo.upper()}")
    
    estado = cargar_estado()
    fondo_path = seleccionar_fondo_disponible(estado)
    
    # 1. Generar idea con restricción/desafío
    print("💡 Generando idea de video...")
    idea_data = generar_idea_video_largo(tipo, fecha_formateada)
    if idea_data and "mejor_idea" in idea_data:
        idea = idea_data["mejor_idea"]
        print(f"   ✅ Idea seleccionada: {idea['titulo']}")
        print(f"   🔥 Restricción: {idea['restriccion']}")
    else:
        print("⚠️ No se generó idea, usando tema de respaldo.")
        idea = None
    
    # 2. Generar guion basado en la idea
    guion, tema, restriccion = generar_guion_largo(tipo, fecha_formateada, idea)
    titulo = guion["titulo"]
    descripcion = guion["descripcion"]
    tags_str = guion.get("tags", "")
    segmentos = guion["segmentos"]
    palabras_portada = guion.get("palabras_portada", "DESAFÍO")
    prompt_miniatura = guion.get("prompt_miniatura", "")
    
    capitulos = []
    for seg in segmentos:
        capitulos.append({"bloque": seg.get("bloque", "CAPÍTULO")})
    
    recursos = []
    for idx, seg in enumerate(segmentos):
        print(f"🎬 Segmento {idx+1}/{len(segmentos)} - {seg.get('bloque', '')}")
        prompt_img = seg["prompt_imagen"]
        img_url = generar_imagen_horizontal(prompt_img, intentos=3)
        if not img_url:
            img_path = generar_fondo_solido()
            img_url = img_path
            print(f"   🖼️ Usando fondo sólido para segmento {idx+1}")
        
        audio_path = generar_audio(seg["texto"], idx)
        if not audio_path:
            continue
        
        try:
            dur = AudioFileClip(audio_path).duration
        except:
            dur = 10.0
        
        recursos.append({
            "imagen_url": img_url,
            "audio_path": audio_path,
            "duracion": dur,
            "texto": seg["texto"],
            "bloque": seg.get("bloque", "")
        })
        time.sleep(15)
    
    if not recursos:
        print("❌ No se generaron recursos.")
        sys.exit(1)
    
    video_path = montar_video_largo(recursos, fondo_path, "largo_capital.mp4", capitulos)
    print(f"🎬 Video montado: {video_path}")
    
    miniatura_path = None
    if prompt_miniatura:
        print("🖼️ Generando miniatura profesional...")
        miniatura_path = crear_miniatura_profesional(
            prompt_miniatura,
            palabras_portada,
            "miniatura_largo.jpg"
        )
    
    video_id = subir_a_youtube(video_path, titulo, tags_str, descripcion, miniatura_path)
    
    guardar_titulo_publicado(titulo)
    guardar_tema_publicado(tema, tipo)
    incrementar_publicaciones_hoy()
    guardar_estado(estado)
    
    limpiar_archivos_temporales()
    
    print(f"✅ Publicado: https://youtu.be/{video_id}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ Error fatal: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
