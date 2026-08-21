import asyncio
from datetime import datetime
import json
import os
import random
import re
import sys
import time
import requests
import edge_tts
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont, ImageOps
from moviepy.editor import (
    AudioFileClip,
    CompositeAudioClip,
    ImageClip,
    concatenate_audioclips,
    concatenate_videoclips,
    AudioClip,
)
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

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
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY")

CANAL_LINK = "https://www.youtube.com/@CapitalMinds"
ESTADO_FILE = "estado_capital_shorts_en.json"
TITULOS_FILE = "titulos_capital_shorts_en_publicados.json"
TEMAS_PUBLICADOS_FILE = "temas_shorts_en_publicados.json"

# Archivos de estado del bot en español (para evitar duplicados entre bots)
ESTADO_FILE_ES = "estado_capital_shorts.json"
TITULOS_FILE_ES = "titulos_capital_shorts_publicados.json"
TEMAS_PUBLICADOS_FILE_ES = "temas_shorts_publicados.json"

META_DIARIA_SHORTS = 3
DIAS_SIN_REPETIR_TEMA = 30

# ================================================================
# VOZ EN INGLÉS (Jenny - US Female)
# ================================================================
VOZ_FIJA = {"voz": "en-US-JennyNeural", "velocidad": "+10%", "tono": "-1Hz"}
CONFIG_VOZ_ACTUAL = VOZ_FIJA

# ================================================================
# MÚSICA CORPORATE (opcional)
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
        print("ℹ️ No music found. Continuing without background music.")
        return None
    ultimo_fondo = estado.get("ultimo_fondo")
    if ultimo_fondo and ultimo_fondo in fondos_disponibles:
        fondos_disponibles.remove(ultimo_fondo)
    seleccionada = random.choice(fondos_disponibles) if fondos_disponibles else random.choice(FONDOS_DISPONIBLES)
    estado["ultimo_fondo"] = seleccionada
    print(f"🎵 Selected music: {os.path.basename(seleccionada)}")
    return seleccionada

# ================================================================
# FUNCIONES DE ESTADO (con soporte para revisar también los archivos en español)
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
    # Cargar títulos del bot en inglés
    try:
        with open(TITULOS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            titulos_en = data.get("titulos", [])
    except:
        titulos_en = []
    
    # Cargar títulos del bot en español (para evitar duplicados)
    try:
        with open(TITULOS_FILE_ES, "r", encoding="utf-8") as f:
            data = json.load(f)
            titulos_es = data.get("titulos", [])
    except:
        titulos_es = []
    
    # Combinar y eliminar duplicados
    todos = list(set(titulos_en + titulos_es))
    return {"titulos": todos}

def guardar_titulo_publicado(titulo):
    data = cargar_titulos_publicados()
    if titulo not in data["titulos"]:
        try:
            with open(TITULOS_FILE, "r", encoding="utf-8") as f:
                data_en = json.load(f)
        except:
            data_en = {"titulos": []}
        if titulo not in data_en["titulos"]:
            data_en["titulos"].append(titulo)
            with open(TITULOS_FILE, "w", encoding="utf-8") as f:
                json.dump(data_en, f, indent=2, ensure_ascii=False)

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
    hoy = datetime.now(ZoneInfo("America/Mexico_City")).strftime("%Y-%m-%d")
    if pub.get("fecha") == hoy:
        return pub.get("cantidad", 0)
    return 0

def incrementar_publicaciones_hoy():
    estado = cargar_estado()
    hoy = datetime.now(ZoneInfo("America/Mexico_City")).strftime("%Y-%m-%d")
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
            temas_en = data.get("temas", [])
    except:
        temas_en = []
    
    try:
        with open(TEMAS_PUBLICADOS_FILE_ES, "r", encoding="utf-8") as f:
            data = json.load(f)
            temas_es = data.get("temas", [])
    except:
        temas_es = []
    
    return temas_en + temas_es

def guardar_tema_publicado(tema, tipo):
    try:
        with open(TEMAS_PUBLICADOS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except:
        data = {"temas": []}
    tema_data = {
        "tema": tema,
        "tipo": tipo,
        "fecha": datetime.now(ZoneInfo("America/Mexico_City")).strftime("%Y-%m-%d")
    }
    data["temas"].append(tema_data)
    if len(data["temas"]) > 200:
        data["temas"] = data["temas"][-200:]
    with open(TEMAS_PUBLICADOS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def tema_ya_publicado(tema, dias=30):
    temas = cargar_temas_publicados()
    hoy = datetime.now(ZoneInfo("America/Mexico_City")).date()
    for t in temas:
        if t["tema"].lower() == tema.lower():
            fecha_tema = datetime.strptime(t["fecha"], "%Y-%m-%d").date()
            if (hoy - fecha_tema).days < dias:
                return True
    return False

# ================================================================
# TREND-JACKING CON NOTICIAS DEL DÍA (EN INGLÉS)
# ================================================================
def obtener_noticia_trending():
    if not NEWSAPI_KEY:
        return None
    try:
        url = "https://newsapi.org/v2/top-headlines"
        params = {
            "category": "business",
            "language": "en",
            "apiKey": NEWSAPI_KEY,
            "pageSize": 5,
            "country": "us"
        }
        r = requests.get(url, params=params, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data.get("articles"):
                for article in data["articles"]:
                    title = article.get("title", "")
                    keywords = ["bitcoin", "crypto", "gold", "etf", "inflation", "fed", "reserve", "stock", "market", "interest", "rates", "dollar", "economy"]
                    if any(word in title.lower() for word in keywords):
                        return title
                return data["articles"][0].get("title", "")
        return None
    except Exception as e:
        print(f"⚠️ Error getting news: {e}")
        return None

# ================================================================
# SANITIZAR TAGS MEJORADO (Robusto para YouTube)
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
def generar_fondo_solido(color=(20, 20, 50), ancho=1080, alto=1920):
    img = Image.new('RGB', (ancho, alto), color)
    path = f"temp_fondo_{random.randint(1000,9999)}.jpg"
    img.save(path)
    return path

# ================================================================
# GENERACIÓN DE IDEAS (EN INGLÉS)
# ================================================================
def generar_idea_video(tipo, fecha_actual):
    prompt = f"""
You are a VIRAL CONTENT STRATEGIST for YouTube Shorts in the finance/crypto niche.

📅 CURRENT DATE: {fecha_actual}
⚠️ IMPORTANT: DO NOT use past dates like 2020, 2021, 2022, 2023 or 2024.
   Use the current date ({fecha_actual}) or references like "today", "this week".

🎯 RESTRICTION: Vary the amount of money! DO NOT always use $100.
   Use different amounts like: $50, $200, $500, $1,000, $5,000, or even "only $10".
   Use different timeframes: 7 days, 14 days, 30 days, 60 days, 90 days, or "1 year".

🎯 CHALLENGE TYPES (choose a different one each time):
   1. "Grow a small amount into a large amount" (e.g., $50 → $5,000).
   2. "Follow a strategy blindly" (e.g., a trading bot, a guru's picks).
   3. "Avoid common mistakes" (e.g., "I made these 3 mistakes so you don't have to").
   4. "Test a controversial method" (e.g., "Is this crypto mining method a scam?").
   5. "Compare two strategies" (e.g., "Day trading vs. holding: which wins?").
   6. "Survival challenge" (e.g., "Can you survive 30 days without checking your portfolio?").
   7. "Reverse psychology" (e.g., "Do the opposite of what everyone is doing").
   8. "Extreme risk" (e.g., "I invested in the most volatile coin").
   9. "Educational breakdown" (e.g., "How does a crypto scam actually work?").
   10. "Personal story" (e.g., "How I lost $10,000 and what I learned").

🎯 PREVENT REPETITION:
   - DO NOT use "$100" if it was used recently.
   - DO NOT use "30 days" if it was used recently.
   - DO NOT use "turn $X into $Y" if it was used recently.

CONTENT TYPE: {tipo} (educational, scam, psychology, analysis, news)

Your task is to generate 5 VIDEO IDEAS (for SHORTS format, 30-60 seconds) that follow these principles:
1. RESTRICTION: The creator imposes a limitation (choose a different amount, different timeframe).
2. CHALLENGE: Measurable goal.
3. TRANSFORMATION: Before and after.

For each idea, write:
- Title (50-60 characters, with emoji, generating CURIOSITY).
- 1-2 line description explaining the restriction/challenge.
- Curiosity level (1-10).

Then CHOOSE THE BEST IDEA (the one with the most curiosity) and return it.

RESPONSE IN JSON:
{{
    "best_idea": {{
        "title": "Final title with curiosity (no past dates)",
        "description": "Idea description",
        "restriction": "What is the restriction or challenge",
        "type": "{tipo}"
    }},
    "ideas_generated": [
        {{"title": "...", "description": "...", "curiosity": 8}},
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
        "max_tokens": 1000,
        "response_format": {"type": "json_object"}
    }
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=90)
        r.raise_for_status()
        data = r.json()
        content = data["choices"][0]["message"]["content"]
        inicio = content.find("{")
        fin = content.rfind("}")
        json_str = content[inicio:fin+1]
        return json.loads(json_str)
    except Exception as e:
        print(f"⚠️ Error generating ideas: {e}")
        return None

# ================================================================
# EXPANSIÓN Y TRUNCAMIENTO DE TEXTO (en inglés)
# ================================================================
def expandir_texto_corto(texto_corto, tema):
    palabras_cortas = len(re.findall(r'\w+', texto_corto))
    prompt = f"""The following financial story is too short ({palabras_cortas} words).
EXPAND it to EXACTLY 90-110 words by adding more context, details, examples, or consequences.
Keep the same tone and structure (HOOK, DATA, EXPLANATION, SOLUTION, CLOSE).

TOPIC: {tema}

ORIGINAL TEXT:
{texto_corto}

Return ONLY the expanded text, with the same blocks [HOOK], [DATA], [EXPLANATION], [SOLUTION], [CLOSE].
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
        print(f"✅ Text expanded: {palabras_exp} words")
        if palabras_exp > 130:
            expanded = truncar_texto(expanded)
            palabras_exp = len(re.findall(r'\w+', expanded))
            print(f"✂️ Text truncated to: {palabras_exp} words")
        return expanded
    except Exception as e:
        print(f"⚠️ Error expanding: {e}")
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
    patron = r'\[HOOK\](.*?)(?=\[DATA\]|$)|\[DATA\](.*?)(?=\[EXPLANATION\]|$)|\[EXPLANATION\](.*?)(?=\[SOLUTION\]|$)|\[SOLUTION\](.*?)(?=\[CLOSE\]|$)|\[CLOSE\](.*?)$'
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
    return [texto]

# ================================================================
# GENERAR GUION SHORT (EN INGLÉS)
# ================================================================
def generar_guion_financiero(tipo, idea=None, fecha_actual=None):
    if not fecha_actual:
        fecha_actual = datetime.now(ZoneInfo("America/Mexico_City")).strftime("%B %d, %Y")

    titulos_pub = cargar_titulos_publicados()["titulos"][-10:]
    titulos_referencia = "\n".join([f"- {t}" for t in titulos_pub]) if titulos_pub else "None yet."

    EDUCATIONAL_TOPICS = [
        "How to Invest in Cryptocurrency Safely",
        "Bitcoin vs Gold: Which is a Better Safe Haven?",
        "Technical vs Fundamental Analysis",
        "The Power of Compound Interest",
        "Portfolio Diversification Strategies for 2026",
        "How to Identify a Cryptocurrency with Potential",
        "DeFi: Opportunities and Risks",
        "How to Read a Trading Chart",
        "Passive vs Active Investing",
        "The 5 Financial Levels to Wealth"
    ]
    SCAM_TOPICS = [
        "The Collapse of FTX: Lessons Learned",
        "How to Detect Pyramid Schemes in Crypto",
        "The Enron Case: The Biggest Corporate Fraud",
        "The Subprime Mortgage Crisis",
        "Mt. Gox: The Bitcoin Theft That Changed Everything",
        "The OneCoin Scam: The Fake Bitcoin",
        "Market Manipulation: How the Big Players Move Prices"
    ]

    if not idea:
        print("💡 Generating idea with restriction/challenge...")
        idea_data = generar_idea_video(tipo, fecha_actual)
        if idea_data and "best_idea" in idea_data:
            idea = idea_data["best_idea"]
            print(f"   ✅ Selected idea: {idea['title']}")
            print(f"   🔥 Restriction: {idea['restriction']}")
        else:
            print("⚠️ No idea generated, using fallback topic.")
            if tipo == "news":
                trending = obtener_noticia_trending()
                if trending:
                    idea = {"title": trending, "restriction": "Today's news"}
                else:
                    idea = {"title": random.choice(EDUCATIONAL_TOPICS), "restriction": "Financial education"}
            elif tipo == "educational":
                idea = {"title": random.choice(EDUCATIONAL_TOPICS), "restriction": "Financial concept"}
            elif tipo == "scam":
                idea = {"title": random.choice(SCAM_TOPICS), "restriction": "Real case"}
            else:
                idea = {"title": random.choice(EDUCATIONAL_TOPICS), "restriction": "Financial challenge"}

    tema_elegido = idea["title"]
    restriccion = idea.get("restriction", "Financial challenge")

    prompt = f"""
You are a FINANCE EXPERT and VIRAL CONTENT CREATOR for YouTube SHORTS.

📌 VIDEO IDEA: "{tema_elegido}"
📌 RESTRICTION/CHALLENGE: "{restriccion}"
📌 TYPE: {tipo.upper()}
📅 CURRENT DATE: {fecha_actual}

⚠️ DATE RULE (VERY IMPORTANT):
   - DO NOT use past dates like 2020, 2021, 2022, 2023 or 2024.
   - Use the current year: {fecha_actual.split()[-1]}.

🎯 CONTENT RULES:
1. Write EXACTLY between 90 and 110 words.
2. Structure: CHALLENGE → PROCESS → RESULT:
   - [HOOK] Present the challenge (e.g., "I'm going to try X with only $100").
   - [DATA] Show the starting point and the goal.
   - [EXPLANATION] Describe the process, obstacles, tension.
   - [SOLUTION] The strategy used to overcome.
   - [CLOSE] Final result + reflection + CTA.
3. Conversational, direct tone with rhetorical questions.
4. Numbers written with LETTERS (not "400,500").

🎯 SEO RULES:
1. TITLE: 50-60 characters, with emoji and keyword.
2. KEYWORDS: 2-3 high-volume terms.
3. TAGS: 15-20 tags (no dates).
4. COVER WORDS: 2-3 impactful words.

🎯 THUMBNAIL DESIGN:
Create a prompt in ENGLISH for Agnes to generate the BACKGROUND.
- Style: "crypto YouTube thumbnail", neon, high contrast, cinematic.
- PROHIBITED: people, faces, text.
- Allowed: Bitcoin, gold, graphs, fire, ice, data.
- Size: 1280x720 (horizontal).

🚫 TITLES ALREADY PUBLISHED (DO NOT REPEAT):
{titulos_referencia}

📤 RESPONSE: Return STRICTLY this JSON:
{{
    "title": "Title with curiosity (50-60 chars, no past dates)",
    "alternative_title": "Second title for A/B testing",
    "keywords": ["keyword1", "keyword2", "keyword3"],
    "hook_description": "Hook for description (max 90 chars)",
    "context_description": "Context in one sentence",
    "source_story": "Story source",
    "full_text": "Text with the 5 blocks (90-110 words)",
    "cover_words": "2-3 words for thumbnail",
    "tags": "15-20 tags separated by commas (no dates)",
    "thumbnail_prompt": "Prompt in English for the thumbnail background (NO text, NO people, 1280x720)"
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
            print(f"🔄 Attempt {intento+1}/6 generating viral script...")
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
                raise ValueError("No JSON found")

            texto = data.get("full_text", "")
            if not all(marker in texto for marker in ["[HOOK]", "[DATA]", "[EXPLANATION]", "[SOLUTION]", "[CLOSE]"]):
                print("   ⚠️ Blocks not found. Extracting manually...")
                bloques = extraer_bloques(texto)
                if len(bloques) == 5:
                    texto_reconstruido = f"[HOOK] {bloques[0]}\n[DATA] {bloques[1]}\n[EXPLANATION] {bloques[2]}\n[SOLUTION] {bloques[3]}\n[CLOSE] {bloques[4]}"
                    data["full_text"] = texto_reconstruido
                    texto = texto_reconstruido
                    print("   ✅ Blocks reconstructed manually.")
                else:
                    raise ValueError("Could not extract blocks")

            palabras = len(re.findall(r'\w+', texto))
            print(f"   📊 Words generated: {palabras}")
            
            if palabras < 70:
                print(f"   ⚠️ Text too short ({palabras} words). Expanding...")
                texto = expandir_texto_corto(texto, tema_elegido)
                data["full_text"] = texto
                palabras = len(re.findall(r'\w+', texto))
                print(f"   📊 Words after expansion: {palabras}")
            elif palabras > 130:
                print(f"   ✂️ Text too long ({palabras} words). Truncating...")
                texto = truncar_texto(texto)
                data["full_text"] = texto
                palabras = len(re.findall(r'\w+', texto))
                print(f"   📊 Words after truncation: {palabras}")

            if palabras < 70 or palabras > 130:
                raise ValueError(f"Words out of range: {palabras} (must be 70-120)")

            titulo = data.get("title", "").strip()
            titulo = re.sub(r'#\w+', '', titulo).strip()
            titulo = ' '.join(titulo.split())
            
            keywords = data.get("keywords", [])
            if keywords and isinstance(keywords, list) and keywords:
                primera_kw = keywords[0].strip()
                if primera_kw and not titulo.lower().startswith(primera_kw.lower()):
                    titulo_sin_art = re.sub(r'^(The|A|An)\s+', '', titulo, flags=re.IGNORECASE)
                    if titulo_sin_art != titulo:
                        titulo = f"{primera_kw.capitalize()} {titulo_sin_art}"
                    else:
                        titulo = f"{primera_kw.capitalize()} {titulo}"
                if len(titulo) > 75:
                    titulo = titulo[:72] + "..."
            data["title"] = titulo

            if titulo_ya_publicado(titulo):
                raise ValueError("Duplicate title")

            tags_raw = data.get("tags", "")
            tags_list = sanitizar_tags(tags_raw)
            for kw in keywords:
                if kw.lower() not in [t.lower() for t in tags_list]:
                    tags_list.append(kw.lower())
            extras = ["finance", "investing", "economy", "bitcoin", "gold", "banks", "trading"]
            for extra in extras:
                if len(tags_list) < 20 and extra not in tags_list:
                    tags_list.append(extra)
            data["tags"] = ", ".join(tags_list[:20])

            if "thumbnail_prompt" not in data or not data["thumbnail_prompt"]:
                data["thumbnail_prompt"] = "cinematic wide shot of glowing financial data and neon charts, high contrast, dark background, hyperrealistic, 8k, no people, no text, no watermark"

            print(f"   🏷️ Title: {data['title']} ({len(data['title'])} chars)")
            print(f"   🔑 Keywords: {keywords}")
            print(f"   📊 Final words: {palabras}")
            return data, tema_elegido, restriccion
            
        except Exception as e:
            print(f"❌ Attempt {intento+1}/6 failed: {e}")
            if intento < 5:
                time.sleep(10)

    print("❌ ALL ATTEMPTS FAILED.")
    sys.exit(1)

# ================================================================
# DIVIDIR EN SEGMENTOS
# ================================================================
def dividir_en_segmentos(texto, max_palabras_por_segmento=35):
    patron = r'\[HOOK\](.*?)(?=\[DATA\]|$)|\[DATA\](.*?)(?=\[EXPLANATION\]|$)|\[EXPLANATION\](.*?)(?=\[SOLUTION\]|$)|\[SOLUTION\](.*?)(?=\[CLOSE\]|$)|\[CLOSE\](.*?)$'
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
        oraciones = re.split(r'(?<=[.!?])\s+', texto)
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
        "context_challenge",
        "start_process",
        "obstacle",
        "climax",
        "result"
    ]
    mapa_ubicaciones = [
        "person preparing for the financial challenge",
        "first steps, initial graphs",
        "moment of doubt or difficulty",
        "turning point, maximum stress",
        "result, celebration or reflection"
    ]
    
    for i in range(n):
        idx = min(i, len(mapa_etapas) - 1)
        etapas.append(mapa_etapas[idx])
        ubicaciones.append(mapa_ubicaciones[idx])
    
    return etapas, ubicaciones

# ================================================================
# GENERAR PROMPT DE IMAGEN (ultraespecífico por bloque)
# ================================================================
def generar_prompt_imagen_segmento(segmento_texto, etapa, ubicacion_escena,
                                   segmento_anterior_texto=None,
                                   index_segmento=0, total_segmentos=1,
                                   tema=None, es_primer_frame=False):
    COLOR_NEON_ACTUAL = "electric cyan neon glow"
    PALETA_BASE_ACTUAL = "Corporate blue and silver, modern office"
    
    contexto_previo = ""
    if segmento_anterior_texto:
        contexto_previo = f"\nPREVIOUS SCENE: '{segmento_anterior_texto[:120]}'"

    prompts_etapa = {
        "context_challenge": f"NEON NOIR aesthetic, cyberpunk financial vibe, intense {COLOR_NEON_ACTUAL} glow on a Bitcoin coin or financial chart, person looking determined, high contrast, dramatic lighting, futuristic corporate look",
        "start_process": f"Hyperrealistic photograph of a trading screen with initial numbers, soft {COLOR_NEON_ACTUAL} neon accent, professional setting, natural lighting, clean composition",
        "obstacle": f"Dramatic wide shot of a person looking at red graphs, intense {COLOR_NEON_ACTUAL} neon glow, high contrast, cinematic tension, dark atmosphere",
        "climax": f"Extreme close-up of a glowing Bitcoin or gold bar, intense {COLOR_NEON_ACTUAL} neon lighting, high contrast, dramatic, hyperrealistic, 8k",
        "result": f"Wide shot of a person celebrating with green charts, warm {COLOR_NEON_ACTUAL} neon accents, optimistic atmosphere, professional photography, sharp focus"
    }
    estilo_base = prompts_etapa.get(etapa, prompts_etapa["context_challenge"])

    descripcion_estilo = f"{estilo_base}, vertical 9:16, {PALETA_BASE_ACTUAL}, sharp focus, hyperdetailed, 8k resolution, cinematic"

    tema_lower = tema.lower() if tema else ""
    if "bitcoin" in tema_lower or "crypto" in tema_lower:
        elementos_tema = "digital currency, blockchain data, crypto screens, modern fintech environment"
    elif "gold" in tema_lower:
        elementos_tema = "gold bars, precious metals, vault, luxury banking setting"
    elif "scam" in tema_lower or "fraud" in tema_lower:
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
1. SHOT TYPE: Wide or medium shot. ABSOLUTELY NO close-up of faces unless the story requires it (climax).
2. MAIN SUBJECT: The environment, objects, and setting.
3. If people appear: They occupy AT MOST 15% of the frame.
4. FOCUS: Sharp, hyperrealistic, premium quality.
5. Colors: Use neon accents ({COLOR_NEON_ACTUAL}) and high contrast.

Return ONLY the English prompt, no explanations.
"""
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.6,
        "max_tokens": 400,
    }
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=60)
        r.raise_for_status()
        prompt_img = r.json()["choices"][0]["message"]["content"].strip()
        prompt_img += f", hyperrealistic, 8k resolution, sharp focus, professional corporate photography, vertical 9:16, wide establishing shot, environment as main subject, no close-up face, no text, no watermark"
        return prompt_img
    except Exception as e:
        print(f"⚠️ Error generating prompt: {e}")
        return f"Wide establishing shot of {ubicacion_escena}, vertical 9:16, financial environment, hyperrealistic, 8k quality, {PALETA_BASE_ACTUAL}, {COLOR_NEON_ACTUAL} accent"

# ================================================================
# GENERAR IMAGEN VERTICAL (CON TIMEOUT 180s)
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
            print(f"   🖼️ Generating image {intento+1}/{intentos}...")
            # TIMEOUT AUMENTADO A 180 SEGUNDOS
            r = requests.post(url, headers=headers, json=payload, timeout=180)
            if r.status_code == 200:
                data = r.json()
                if data.get("data") and len(data["data"]) > 0:
                    return data["data"][0]["url"]
            else:
                print(f"   ⚠️ Error {r.status_code}: {r.text[:100]}")
        except Exception as e:
            print(f"   ⚠️ Connection error: {e}")
        if intento < intentos - 1:
            time.sleep(10)
    return None

# ================================================================
# GENERAR IMAGEN HORIZONTAL PARA MINIATURA (CON TIMEOUT 180s)
# ================================================================
def generar_imagen_horizontal(prompt, intentos=3):
    prompt_completo = f"{prompt}, hyperrealistic, 8k, cinematic lighting, high contrast, sharp focus, no people, no text, no watermark, electric cyan neon glow, dark background"
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
            print(f"   🖼️ Generating thumbnail background {intento+1}/{intentos}...")
            r = requests.post(url, headers=headers, json=payload, timeout=180)
            if r.status_code == 200:
                data = r.json()
                if data.get("data") and len(data["data"]) > 0:
                    return data["data"][0]["url"]
            else:
                print(f"   ⚠️ Error {r.status_code}")
        except Exception as e:
            print(f"   ⚠️ Connection error: {e}")
        if intento < intentos - 1:
            time.sleep(10)
    return None

# ================================================================
# GENERAR AUDIO (en inglés)
# ================================================================
def generar_audio(texto, index, intentos_por_voz=2):
    global CONFIG_VOZ_ACTUAL
    texto_limpio = re.sub(r'[^a-zA-ZáéíóúüñÁÉÍÓÚÜÑ0-9\s.,;:!?¿¡\'\"]', '', texto)
    texto_limpio = re.sub(r'\s+', ' ', texto_limpio).strip()
    if len(texto_limpio) < 20:
        texto_limpio = "Financial news."
    filename = f"audio_short_en_{index}.mp3"
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
            print(f"   ❌ Voice failed {voz}: {e}")
        time.sleep(10)
        if os.path.exists(filename):
            try: os.remove(filename)
            except: pass
    return None

# ================================================================
# GENERAR RECURSOS POR SEGMENTO (CON REUTILIZACIÓN DE IMÁGENES)
# ================================================================
def generar_recursos_por_segmento(segmentos, etapas, ubicaciones, tema=None, intentos_imagen=3):
    recursos = []
    total = len(segmentos)
    last_successful_url = None

    for idx, seg in enumerate(segmentos):
        print(f"  🎬 Segment {idx+1}/{total} ({len(seg.split())} words)")
        etapa = etapas[idx] if idx < len(etapas) else "context_challenge"
        ubic = ubicaciones[idx] if idx < len(ubicaciones) else "financial office"
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
                print(f"    ✅ Image generated (attempt {intento+1})")
                last_successful_url = img_url
                break
            time.sleep(10)
        
        # REUTILIZACIÓN DE IMAGEN ANTERIOR SI FALLA
        if not img_url:
            if last_successful_url:
                print(f"    🔄 Reusing previous image")
                img_url = last_successful_url
            else:
                print(f"    ⚠️ No previous image. Retrying...")
                time.sleep(10)
                img_url = generar_imagen_vertical(prompt_img, intentos=1)
                if img_url:
                    last_successful_url = img_url
                else:
                    print(f"    ❌ Failed definitively, using solid background")
                    img_path = generar_fondo_solido(color=(20, 20, 50), ancho=1080, alto=1920)
                    img_url = img_path
                    last_successful_url = img_url
        
        if not img_url:
            img_path = generar_fondo_solido(color=(20, 20, 50), ancho=1080, alto=1920)
            img_url = img_path
            last_successful_url = img_url
        
        audio_path = generar_audio(seg, idx)
        if not audio_path:
            print(f"    ❌ Audio failed for segment {idx+1}. Aborting.")
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
            print(f"   ⏳ Waiting 10 seconds...")
            time.sleep(10)
    
    return recursos

# ================================================================
# SUBTÍTULOS CON PIL (VERTICAL) - MEJORADOS
# ================================================================
def agregar_subtitulos_con_pil(imagen_path, texto, salida_path):
    try:
        img = Image.open(imagen_path)
        draw = ImageDraw.Draw(img)
        
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 55)
        except:
            try:
                font = ImageFont.truetype("arial.ttf", 55)
            except:
                font = ImageFont.load_default()
                print("   ⚠️ Using default font")
        
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
            draw.rectangle([bg_x, bg_y, bg_x + bg_w, bg_y + bg_h], fill=(0, 0, 0, 180))
            draw.rectangle([bg_x, bg_y, bg_x + bg_w, bg_y + bg_h], outline=(0, 200, 255, 80), width=2)
            
            draw.text((x+3, y+3), linea, fill='black', font=font)
            draw.text((x, y), linea, fill='white', font=font)
        
        img.save(salida_path)
        return salida_path
        
    except Exception as e:
        print(f"⚠️ Error in subtitles: {e}")
        return imagen_path

# ================================================================
# MINIATURA PROFESIONAL MEJORADA (sin rectángulo con borde)
# ================================================================
def crear_miniatura_profesional(prompt_miniatura, texto_portada, salida="miniatura_short_en.jpg"):
    try:
        print("🖼️ Generating thumbnail background...")
        fondo_url = generar_imagen_horizontal(prompt_miniatura, intentos=2)
        if not fondo_url:
            print("⚠️ Could not generate background, using solid background")
            fondo_path = generar_fondo_solido(color=(10, 10, 30), ancho=1280, alto=720)
            fondo_url = fondo_path
        
        if fondo_url.startswith("http"):
            try:
                r = requests.get(fondo_url, timeout=30)
                r.raise_for_status()
                img_path = "temp_thumb_fondo_short_en.jpg"
                with open(img_path, "wb") as f:
                    f.write(r.content)
            except Exception as e:
                print(f"⚠️ Error downloading background: {e}. Using solid background.")
                img_path = generar_fondo_solido(color=(10, 10, 30), ancho=1280, alto=720)
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
        y = (720 - text_h) // 2 + 40
        
        # Fondo oscuro detrás del texto (SIN BORDE)
        padding = 40
        bg_x = x - padding
        bg_y = y - padding - 10
        bg_w = text_w + padding * 2
        bg_h = text_h + padding * 2 + 20
        overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        overlay_draw.rectangle([bg_x, bg_y, bg_x + bg_w, bg_y + bg_h], fill=(0, 0, 0, 200))
        # ELIMINADO EL RECTÁNGULO CON BORDE
        img = Image.alpha_composite(img.convert('RGBA'), overlay).convert('RGB')
        draw = ImageDraw.Draw(img)
        
        for dx, dy in [(-5, -5), (-5, 5), (5, -5), (5, 5), (0, 8), (0, -8), (8, 0), (-8, 0)]:
            draw.text((x + dx, y + dy), texto, fill='black', font=font)
        for dx, dy in [(-2, -2), (-2, 2), (2, -2), (2, 2)]:
            draw.text((x + dx, y + dy), texto, fill='white', font=font)
        draw.text((x, y), texto, fill=(255, 255, 80), font=font)
        
        img.save(salida)
        print(f"✅ Professional thumbnail created: {salida}")
        return salida
    except Exception as e:
        print(f"⚠️ Error in professional thumbnail: {e}")
        return None

# ================================================================
# MONTAR VIDEO SHORTS
# ================================================================
def montar_video_shorts(recursos, fondo_path, salida="short_capital_en.mp4"):
    if not recursos:
        raise ValueError("No resources")
    
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
                    img_path = f"temp_short_en_{i}.jpg"
                    with open(img_path, "wb") as f:
                        f.write(r.content)
                except:
                    img_path = generar_fondo_solido(color=(20, 20, 50), ancho=1080, alto=1920)
            else:
                img_path = img_url
            
            img = Image.open(img_path)
            img = ImageOps.fit(img, (1080, 1920), Image.Resampling.LANCZOS)
            img.save(img_path)
            
            img_sub_path = f"temp_short_sub_en_{i}.jpg"
            img_path = agregar_subtitulos_con_pil(img_path, texto, img_sub_path)
            
            video_clip = (ImageClip(img_path)
                         .resize(lambda t: 1 + 0.02 * t)
                         .set_duration(duracion))
        except Exception as e:
            print(f"⚠️ Failed image {i}: {e}")
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
# SUBIR A YOUTUBE (CON CATEGORÍA 22 Y VALIDACIÓN DE TAGS)
# ================================================================
def subir_a_youtube(video_path, titulo, etiquetas_str, gancho, contexto, hashtags, fuente="", miniatura_path=None):
    try:
        creds = Credentials.from_authorized_user_info(YOUTUBE_USER_TOKEN)
        youtube = build("youtube", "v3", credentials=creds)
    except Exception as e:
        print(f"❌ Error authenticating: {e}")
        sys.exit(1)
    
    # Limpiar y validar tags
    tags = sanitizar_tags(etiquetas_str)
    if not tags:
        print("⚠️ No valid tags found. Using default tags.")
        tags = ["finance", "investing", "crypto", "trading", "shorts"]
    
    tags_str_final = ",".join(tags)
    if len(tags_str_final) > 500:
        tags = tags[:10]
        tags_str_final = ",".join(tags)
        if len(tags_str_final) > 500:
            tags = tags[:5]
            tags_str_final = ",".join(tags)
    
    print(f"📝 Final tags ({len(tags)}): {tags_str_final}")
    
    descripcion = f"""{gancho}

{contexto}

🔴 SUBSCRIBE to the channel: {CANAL_LINK}

📖 {fuente}

{hashtags}

⚠️ IMPORTANT NOTICE: This content is for educational purposes only and does not constitute financial, legal, or investment advice."""
    
    body = {
        "snippet": {
            "title": titulo[:100],
            "description": descripcion[:5000],
            "tags": tags[:30],
            "categoryId": "22",
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en",
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
    print(f"✅ Short uploaded: https://youtu.be/{video_id}")
    
    if miniatura_path and os.path.exists(miniatura_path):
        try:
            media_thumb = MediaFileUpload(miniatura_path, chunksize=-1, resumable=True)
            youtube.thumbnails().set(videoId=video_id, media_body=media_thumb).execute()
            print("✅ Professional thumbnail uploaded")
        except Exception as e:
            print(f"⚠️ Error uploading thumbnail: {e}")
    
    return video_id

# ================================================================
# LIMPIEZA
# ================================================================
def limpiar_archivos_temporales():
    import glob
    patrones = [
        "temp_*.jpg", "audio_short_en_*.mp3", "temp_thumb*.jpg",
        "miniatura_short_en.jpg", "short_capital_en.mp4", "placeholder*.jpg",
        "temp_fondo_*.jpg"
    ]
    for patron in patrones:
        for f in glob.glob(patron):
            try:
                os.remove(f)
                print(f"🧹 Removed: {f}")
            except:
                pass
    print("✅ Cleanup completed")

# ================================================================
# MAIN
# ================================================================
def main():
    print("="*60)
    print("🎬 Capital Minds - SHORTS BOT (ENGLISH VERSION)")
    print("   ✓ Idea generation with restriction/challenge")
    print("   ✓ Curiosity-driven titles (no past dates)")
    print("   ✓ Challenge → Process → Result structure")
    print("   ✓ Enhanced thumbnail with neon text")
    print("   ✓ 10s pauses between generations")
    print("   ✓ Today's news (NewsAPI)")
    print("   ✓ Category: People & Blogs (22)")
    print("   ✓ IMAGE REUSE: falls back to previous segment")
    print("   ✓ DUPLICATE CONTROL: checks Spanish bot's history too")
    print("   ✓ TAGS VALIDATION: ensures YouTube-compatible tags")
    print("="*60)

    tz_mexico = ZoneInfo("America/Mexico_City")
    fecha_actual = datetime.now(tz_mexico)
    fecha_formateada = fecha_actual.strftime("%B %d, %Y")
    print(f"📅 Current date: {fecha_formateada}")
    print("="*60)
    
    if not YOUTUBE_USER_TOKEN:
        print("❌ YOUTUBE_USER_TOKEN_CAPITAL missing")
        sys.exit(1)
    
    publicadas = obtener_publicaciones_hoy()
    if publicadas >= META_DIARIA_SHORTS:
        print(f"✅ Already published {META_DIARIA_SHORTS} shorts today. Exiting.")
        sys.exit(0)
    
    if publicadas == 0:
        tipo = "news"
    elif publicadas == 1:
        tipo = "educational"
    else:
        tipo = "scam"
    
    print(f"📌 Type: {tipo.upper()} (Short #{publicadas+1} of the day)")
    
    estado = cargar_estado()
    fondo_path = seleccionar_fondo_disponible(estado)
    
    print("💡 Generating video idea...")
    idea_data = generar_idea_video(tipo, fecha_formateada)
    if idea_data and "best_idea" in idea_data:
        idea = idea_data["best_idea"]
        print(f"   ✅ Selected idea: {idea['title']}")
        print(f"   🔥 Restriction: {idea['restriction']}")
    else:
        print("⚠️ No idea generated, using fallback topic.")
        idea = None
    
    guion, tema_elegido, restriccion = generar_guion_financiero(tipo, idea, fecha_formateada)
    texto = guion["full_text"]
    palabras_portada = guion.get("cover_words", "CHALLENGE")
    prompt_miniatura = guion.get("thumbnail_prompt", "")
    
    palabras_texto = len(re.findall(r'\w+', texto))
    print(f"📝 Text: {palabras_texto} words")
    print(f"📌 Topic: {tema_elegido}")
    print(f"🔒 Restriction: {restriccion}")
    
    segmentos = dividir_en_segmentos(texto, max_palabras_por_segmento=35)
    etapas, ubicaciones = asignar_etapas_visuales(segmentos)
    print(f"🎬 {len(segmentos)} segments generated")
    
    recursos = generar_recursos_por_segmento(segmentos, etapas, ubicaciones, tema_elegido)
    if not recursos:
        print("❌ Error generating resources.")
        sys.exit(1)
    
    video_path = montar_video_shorts(recursos, fondo_path, "short_capital_en.mp4")
    print(f"🎬 Video assembled: {video_path}")
    
    miniatura_path = None
    if prompt_miniatura:
        print("🖼️ Generating professional thumbnail...")
        miniatura_path = crear_miniatura_profesional(
            prompt_miniatura,
            palabras_portada,
            "miniatura_short_en.jpg"
        )
    
    video_id = subir_a_youtube(
        video_path=video_path,
        titulo=guion["title"],
        etiquetas_str=guion["tags"],
        gancho=guion["hook_description"],
        contexto=guion["context_description"],
        hashtags="#Shorts #Finance",
        fuente=guion.get("source_story", "Based on financial analysis"),
        miniatura_path=miniatura_path
    )
    
    guardar_titulo_publicado(guion["title"])
    guardar_tema_publicado(tema_elegido, tipo)
    incrementar_publicaciones_hoy()
    guardar_estado(estado)
    
    limpiar_archivos_temporales()
    
    print(f"✅ Short published successfully!")
    print(f"🔗 https://youtu.be/{video_id}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
