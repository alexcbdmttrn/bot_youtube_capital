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
    CompositeVideoClip,
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
ESTADO_FILE = "estado_capital_largos_en.json"
TITULOS_FILE = "titulos_capital_largos_en_publicados.json"
TEMAS_PUBLICADOS_FILE = "temas_largos_en_publicados.json"
META_DIARIA_LARGOS = 1
DIAS_SIN_REPETIR_TEMA = 45

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
# FUNCIONES DE ESTADO (idénticas al original)
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
            return data.get("temas", [])
    except:
        return []

def guardar_tema_publicado(tema, tipo):
    temas = cargar_temas_publicados()
    tema_data = {
        "tema": tema,
        "tipo": tipo,
        "fecha": datetime.now(ZoneInfo("America/Mexico_City")).strftime("%Y-%m-%d")
    }
    temas.append(tema_data)
    if len(temas) > 200:
        temas = temas[-200:]
    with open(TEMAS_PUBLICADOS_FILE, "w", encoding="utf-8") as f:
        json.dump({"temas": temas}, f, indent=2, ensure_ascii=False)

def tema_ya_publicado(tema, dias=45):
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
def obtener_tema_trending():
    if not NEWSAPI_KEY:
        return None
    try:
        url = "https://newsapi.org/v2/top-headlines"
        params = {
            "category": "business",
            "language": "en",
            "apiKey": NEWSAPI_KEY,
            "pageSize": 10,
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
                        return title[:100]
                for article in data["articles"]:
                    title = article.get("title", "")
                    if not re.search(r'20[0-2][0-9]', title):
                        return title[:100]
        return None
    except Exception as e:
        print(f"⚠️ Error getting trending: {e}")
        return None

# ================================================================
# GENERACIÓN DE IDEAS (EN INGLÉS)
# ================================================================
def generar_idea_video_largo(tipo, fecha_actual):
    prompt = f"""
You are a VIRAL CONTENT STRATEGIST for YouTube in the finance/crypto niche.

📅 CURRENT DATE: {fecha_actual}
⚠️ IMPORTANT: DO NOT use past dates like 2020, 2021, 2022, 2023 or 2024.
   Use the current date ({fecha_actual}) or references like "today", "this week".

Your task is to generate 5 VIDEO IDEAS (for LONG format, 7-9 minutes) that follow these principles:
1. RESTRICTION: The creator imposes a limitation (e.g., "invest only $100").
2. CHALLENGE: Measurable goal (e.g., "reach $10,000 in 30 days").
3. TRANSFORMATION: Before and after (e.g., "from debt to investor").

CONTENT TYPE: {tipo} (educational, scam, psychology, analysis, news)

For each idea, write:
- Title (60-70 characters, with emoji and keyword, generating CURIOSITY).
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
        "max_tokens": 1200,
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
# SANITIZAR TAGS (en inglés)
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
# EXPANSIÓN DE GUION (EN INGLÉS)
# ================================================================
def expandir_guion_largo(guion_corto, tema, restriccion, fecha_actual):
    prompt = f"""
You are a PROFESSIONAL SCRIPTWRITER. The following script is too short.
EXPAND it to 1300-1500 words, maintaining the arc of CHALLENGE → PROCESS → RESULT.
Add:
- More concrete examples related to the restriction.
- Relevant data and statistics (no past dates).
- Analogies and comparisons.
- Obstacles and moments of tension.
- Conclusion and final reflection.

📅 CURRENT DATE: {fecha_actual}
⚠️ DO NOT use past dates (2020, 2021, 2022, 2023, 2024).

TOPIC: {tema}
RESTRICTION/CHALLENGE: {restriccion}

CURRENT SCRIPT:
{guion_corto}

RETURN ONLY THE EXPANDED SCRIPT TEXT, with the same blocks [HOOK], [INTRO], [PROBLEM], [DEVELOPMENT], [SOLUTION], [CLOSE].
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
            print(f"✅ Expansion successful: {palabras} words")
            return expanded
        else:
            print(f"⚠️ Expansion insufficient ({palabras} words)")
            return None
    except Exception as e:
        print(f"❌ Error in expansion: {e}")
        return None

# ================================================================
# GENERAR GUION LARGO (EN INGLÉS)
# ================================================================
def generar_guion_largo(tipo, fecha_actual, idea=None):
    titulos_pub = cargar_titulos_publicados()["titulos"][-10:]
    titulos_referencia = "\n".join([f"- {t}" for t in titulos_pub]) if titulos_pub else "None yet."

    TEMAS_EDUCATIVOS = [
        "How to Invest in Cryptocurrency Safely (Complete Guide)",
        "Bitcoin and Gold: Safe Havens in Economic Crisis",
        "Technical vs Fundamental Analysis: Which is Better for You",
        "The 5 Financial Levels That Will Lead You to Wealth",
        "How Compound Interest Works and Why Not Using It Makes You Poor",
        "Portfolio Diversification Strategies for 2026",
        "How to Identify a Cryptocurrency with Potential (Fundamentals)",
        "Decentralized Finance (DeFi): Opportunities and Risks",
        "How to Read a Trading Chart (Beginner's Guide)",
        "Passive vs Active Investing: Which One Suits You Best"
    ]
    TEMAS_ESTAFAS_CRISIS = [
        "The Collapse of FTX: Lessons Learned",
        "How to Detect Pyramid Schemes in Crypto",
        "The Enron Case: The Biggest Corporate Fraud",
        "The Subprime Mortgage Crisis and Its Parallel with Crypto",
        "Mt. Gox: The Bitcoin Theft That Changed Everything",
        "The OneCoin Scam: The Fake Bitcoin That Fooled the World",
        "Market Manipulation: How the Big Players Move Prices",
        "Scam Alerts on Exchanges (Real Cases)"
    ]
    TEMAS_PSICOLOGIA = [
        "FOMO and Panic: How to Master Your Emotions in Trading",
        "The 4 Mental Bugs That Keep You Poor (and How to Fix Them)",
        "Discipline vs Money: The Habits of the Rich",
        "Wealth Mindset: How to Attract Money",
        "Stop Being a Salary Slave: 3 Steps to Financial Freedom"
    ]
    TEMAS_ANALISIS = [
        "SHIBA INU Analysis: Will It Reach 1 Cent?",
        "Bitcoin Analysis: Ready for the Next ATH?",
        "Ethereum vs Solana: Who Will Win in the Future?",
        "Helium (HNT): Mining Without Graphics Cards, Is It Worth It?",
        "Bittorrent (BTT): The Sleeping Giant of Storage",
        "New Altcoins with X10 Potential (Project Analysis)"
    ]

    if not idea:
        print("💡 Generating idea with restriction/challenge...")
        idea_data = generar_idea_video_largo(tipo, fecha_actual)
        if idea_data and "best_idea" in idea_data:
            idea = idea_data["best_idea"]
            print(f"   ✅ Selected idea: {idea['title']}")
            print(f"   🔥 Restriction: {idea['restriction']}")
        else:
            print("⚠️ No idea generated, using fallback topic.")
            if tipo == "news":
                trending = obtener_tema_trending()
                if trending:
                    idea = {"title": trending, "restriction": "Today's news"}
                else:
                    idea = {"title": random.choice(TEMAS_EDUCATIVOS), "restriction": "Financial education"}
            elif tipo == "educational":
                idea = {"title": random.choice(TEMAS_EDUCATIVOS), "restriction": "Financial concept"}
            elif tipo == "scam":
                idea = {"title": random.choice(TEMAS_ESTAFAS_CRISIS), "restriction": "Real case"}
            elif tipo == "psychology":
                idea = {"title": random.choice(TEMAS_PSICOLOGIA), "restriction": "Financial psychology"}
            else:
                idea = {"title": random.choice(TEMAS_ANALISIS), "restriction": "Market analysis"}

    tema_elegido = idea["title"]
    restriccion = idea.get("restriction", "Financial challenge")

    prompt = f"""
You are a PROFESSIONAL SCRIPTWRITER and FINANCE EXPERT. Write a DETAILED script for a 7-9 minute YouTube video.

📌 VIDEO IDEA: "{tema_elegido}"
📌 RESTRICTION/CHALLENGE: "{restriccion}"
📌 TYPE: {tipo}
📅 CURRENT DATE: {fecha_actual}

⚠️ DATE RULE (VERY IMPORTANT):
   - DO NOT use past dates like 2020, 2021, 2022, 2023 or 2024.
   - If you need to mention a year, use the current year: {fecha_actual.split()[-1]}.
   - For recent events, say "today", "this week", or "in recent days".

🎯 GOLDEN RULE (CRITICAL):
- The script MUST be between 1300 and 1500 words.
- If the script has fewer than 1200 words, the video will be too short.
- Each block must have the indicated length.

🎯 MANDATORY STRUCTURE (based on CHALLENGE → PROCESS → RESULT):
[HOOK - 0:00] Present the challenge in an impactful way (e.g., "I'm going to try X in 30 days").
[INTRO - 0:15] Explain why this challenge is interesting and what is needed. (150-200 words)
[PROBLEM - 1:30] Show the initial obstacles, doubts, fears. (200-250 words)
[DEVELOPMENT - 3:00] The step-by-step process, with moments of tension and learning. (300-350 words)
[SOLUTION - 5:00] The strategy used to overcome obstacles, the climax. (250-300 words)
[CLOSE - 7:00] Final result (was it achieved or not?), reflection and CTA. (200-250 words)

🎯 GOLDEN RULE FOR NUMBERS:
- NEVER use numbers with commas: "400,500" or "50,100".
- ALWAYS write numbers with LETTERS: "four hundred", "fifty".
- For ranges, use "between X and Y".

🎯 ADDITIONAL INSTRUCTIONS:
- Use a conversational tone, like talking to a friend.
- Include rhetorical questions and analogies.
- DO NOT use specific past dates.

🎯 IMAGES (prompts in English):
Each block will have a specific image prompt for Agnes.
- Style: cinematic, neon, 8k.
- PROHIBITED: people, faces, close-up faces.
- Allowed: graphics, coins, data, visualizations, maps, technology.

🎯 THUMBNAIL DESIGN (IMPORTANT):
Create a prompt in ENGLISH for Agnes to generate the BACKGROUND of the thumbnail. The background should reflect the CHALLENGE.
- Style: "crypto YouTube thumbnail", neon, high contrast, cinematic, hyperrealistic.
- PROHIBITED: people, faces, text.
- Allowed: a visual goal (e.g., a giant coin, an upward graph, a path with an X at the end).
- Size: 1280x720 (horizontal).

🚫 TITLES ALREADY PUBLISHED (DO NOT REPEAT):
{titulos_referencia}

📤 RESPONSE IN JSON:
{{
    "title": "Title with emoji and curiosity (60-70 chars, no past dates)",
    "alternative_title": "Alternative title",
    "keywords": ["kw1", "kw2", "kw3", "kw4", "kw5"],
    "description": "Full description with chapters and hashtags, including the challenge",
    "tags": "25-30 tags separated by commas (NO special characters, no dates)",
    "hashtags": "#hashtag1 #hashtag2",
    "script": "Full script of 1300-1500 words with the 6 marked blocks",
    "segments": [
        {{"block": "HOOK", "text": "text (~10 words)", "image_prompt": "prompt in English WITHOUT PEOPLE"}},
        {{"block": "INTRO", "text": "text (~150-200 words)", "image_prompt": "prompt in English"}},
        {{"block": "PROBLEM", "text": "text (~200-250 words)", "image_prompt": "prompt in English"}},
        {{"block": "DEVELOPMENT", "text": "text (~300-350 words)", "image_prompt": "prompt in English"}},
        {{"block": "SOLUTION", "text": "text (~250-300 words)", "image_prompt": "prompt in English"}},
        {{"block": "CLOSE", "text": "text (~200-250 words)", "image_prompt": "prompt in English"}}
    ],
    "cover_words": "2-3 words for the thumbnail text (e.g., 'I MADE IT', 'THE CHALLENGE')",
    "thumbnail_prompt": "Prompt in English for the thumbnail background (NO text, NO people, 1280x720)"
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
            print(f"🔄 Generating script (attempt {intento+1}/3)...")
            r = requests.post(url, headers=headers, json=payload, timeout=150)
            r.raise_for_status()
            data = r.json()
            content = data["choices"][0]["message"]["content"]
            inicio = content.find("{")
            fin = content.rfind("}")
            json_str = content[inicio:fin+1]
            result = json.loads(json_str)
            
            guion_texto = result.get("script", "")
            palabras = len(re.findall(r'\w+', guion_texto))
            print(f"📊 Script words: {palabras}")
            
            if palabras < 1100:
                print(f"⚠️ Short script ({palabras} words). Expanding...")
                guion_expandido = expandir_guion_largo(guion_texto, tema_elegido, restriccion, fecha_actual)
                if guion_expandido:
                    result["script"] = guion_expandido
                    palabras = len(re.findall(r'\w+', guion_expandido))
                    print(f"📊 Expanded script: {palabras} words")
                else:
                    print("❌ Expansion failed, using original script")
            
            if palabras < 900:
                print(f"⚠️ Script still short ({palabras} words). Reducing voice speed to +5%.")
                global VOZ_FIJA
                VOZ_FIJA = {"voz": "en-US-JennyNeural", "velocidad": "+5%", "tono": "-1Hz"}
                CONFIG_VOZ_ACTUAL = VOZ_FIJA
            
            if "thumbnail_prompt" not in result:
                result["thumbnail_prompt"] = "cinematic wide shot of a glowing path leading to a golden Bitcoin, neon cyan and gold lighting, high contrast, dark background, hyperrealistic, 8k, no people, no text, no watermark"
            
            return result, tema_elegido, restriccion
        except Exception as e:
            print(f"❌ Attempt {intento+1}/3 failed: {e}")
            time.sleep(10)
    print("❌ Error generating script after 3 attempts")
    sys.exit(1)

# ================================================================
# FILTRAR PROMPT DE MINIATURA
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
# GENERAR IMAGEN HORIZONTAL
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
            print(f"   🖼️ Sending prompt to Agnes (attempt {intento+1}/{intentos})...")
            r = requests.post(url, headers=headers, json=payload, timeout=120)
            if r.status_code == 200:
                data = r.json()
                if data.get("data") and len(data["data"]) > 0:
                    print(f"   ✅ Image generated successfully on attempt {intento+1}.")
                    return data["data"][0]["url"]
            else:
                print(f"   ⚠️ Error {r.status_code} - {r.text[:400]}")
        except Exception as e:
            print(f"   ⚠️ Connection error: {e}")
        if intento < intentos - 1:
            print("   ⏳ Waiting 10 seconds before retrying...")
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
# MINIATURA PROFESIONAL MEJORADA (en inglés)
# ================================================================
def crear_miniatura_profesional(prompt_miniatura, texto_portada, salida="miniatura_largo_en.jpg"):
    print("🖼️ Generating professional thumbnail...")
    prompt_filtrado = filtrar_prompt_miniatura(prompt_miniatura)
    print(f"   📝 Original prompt: {prompt_miniatura[:200]}...")
    print(f"   📝 Filtered prompt: {prompt_filtrado[:200]}...")

    prompts_a_intentar = [
        prompt_filtrado,
        "cinematic wide shot of glowing financial charts and golden coins, neon cyan and gold lighting, high contrast, dark background, hyperrealistic, 8k, no people, no text, no watermark",
        "dramatic wide shot of stock market graphs and city skyline, blue and gold lighting, professional photography, sharp focus, no text, no watermark"
    ]

    fondo_url = None
    for intento, prompt in enumerate(prompts_a_intentar[:3], start=1):
        print(f"   🖼️ Attempt {intento}/3 generating thumbnail...")
        fondo_url = generar_imagen_horizontal(prompt, intentos=1)
        if fondo_url:
            break
        if intento < 3:
            print("   ⏳ Waiting 10 seconds...")
            time.sleep(10)

    if not fondo_url:
        print("⚠️ Could not generate background, using placeholder")
        fondo_path = generar_fondo_solido()
        fondo_url = fondo_path

    try:
        if fondo_url.startswith("http"):
            try:
                r = requests.get(fondo_url, timeout=30)
                r.raise_for_status()
                img_path = "temp_thumb_fondo_en.jpg"
                with open(img_path, "wb") as f:
                    f.write(r.content)
            except Exception as e:
                print(f"⚠️ Error downloading background: {e}")
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
# SUBTÍTULOS CON PIL (en inglés)
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
        print(f"⚠️ Error in subtitles: {e}")
        return imagen_path

# ================================================================
# GENERAR AUDIO (en inglés)
# ================================================================
def generar_audio(texto, index):
    global CONFIG_VOZ_ACTUAL
    texto_limpio = re.sub(r'[^a-zA-ZáéíóúüñÁÉÍÓÚÜÑ0-9\s.,;:!?¿¡\'\"]', '', texto)
    texto_limpio = re.sub(r'\s+', ' ', texto_limpio).strip()
    
    filename = f"audio_largo_en_{index}.mp3"
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
# CAPÍTULOS VISUALES CON PIL (en inglés)
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
        temp_path = f"temp_capitulo_en_{timestamp.replace(':', '')}.png"
        img.save(temp_path)
        clip = ImageClip(temp_path, duration=duracion, transparent=True)
        clip = clip.crossfadein(0.3).crossfadeout(0.3)
        return clip
    except Exception as e:
        print(f"⚠️ Error creating chapter visual with PIL: {e}")
        return None

# ================================================================
# CTA FINAL "SUBSCRIBE" (en inglés)
# ================================================================
def crear_cta_final_pil(duracion=3, ancho=1280, alto=720):
    try:
        img = Image.new('RGB', (ancho, alto), (15, 15, 20))
        draw = ImageDraw.Draw(img)
        texto = "🔴 SUBSCRIBE"
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
        temp_path = "temp_cta_en.png"
        img.save(temp_path)
        clip = ImageClip(temp_path, duration=duracion)
        clip = clip.crossfadein(0.5)
        return clip
    except Exception as e:
        print(f"⚠️ Error creating CTA with PIL: {e}")
        return None

# ================================================================
# MONTAR VIDEO
# ================================================================
def montar_video_largo(recursos, fondo_path, salida="largo_capital_en.mp4", capitulos=None):
    if not recursos:
        raise ValueError("No resources")
    
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
                    img_path = f"temp_largo_en_{i}.jpg"
                    with open(img_path, "wb") as f:
                        f.write(r.content)
                except Exception as e:
                    print(f"⚠️ Failed to download image {i}: {e}")
                    img_path = generar_fondo_solido()
            else:
                img_path = img_url
            
            img = Image.open(img_path)
            img = ImageOps.fit(img, (1280, 720), Image.Resampling.LANCZOS)
            img.save(img_path)
            
            img_sub_path = f"temp_largo_sub_en_{i}.jpg"
            img_path = agregar_subtitulos_con_pil_16_9(img_path, texto, img_sub_path)
            
            video_clip = (ImageClip(img_path)
                         .resize(lambda t: 1 + 0.015 * t)
                         .set_duration(duracion))
        except Exception as e:
            print(f"⚠️ Failed image {i}: {e}")
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
# SUBIR A YOUTUBE (CON CATEGORÍA 22: PEOPLE & BLOGS)
# ================================================================
def subir_a_youtube(video_path, titulo, etiquetas_str, descripcion, miniatura_path=None):
    try:
        creds = Credentials.from_authorized_user_info(YOUTUBE_USER_TOKEN)
        youtube = build("youtube", "v3", credentials=creds)
    except Exception as e:
        print(f"❌ Error authenticating: {e}")
        sys.exit(1)
    
    tags = sanitizar_tags(etiquetas_str)
    print(f"📝 Sanitized tags: {len(tags)} tags")
    
    disclaimer = "\n\n⚠️ IMPORTANT NOTICE: This content is for educational purposes only and does not constitute financial, legal, or investment advice."
    descripcion_final = descripcion + disclaimer
    
    body = {
        "snippet": {
            "title": titulo[:100],
            "description": descripcion_final[:5000],
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
    print(f"✅ Long video uploaded: https://youtu.be/{video_id}")
    
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
        "temp_*.jpg", "temp_*.mp3", "audio_largo_en_*.mp3",
        "temp_thumb*.jpg", "miniatura_largo_en.jpg", "largo_capital_en.mp4",
        "placeholder*.jpg", "temp_*.png", "temp_capitulo_en_*.png",
        "temp_cta_en.png", "temp_fondo_*.jpg"
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
    print("🎬 Capital Minds - LONG VIDEO BOT (ENGLISH VERSION)")
    print("   ✓ Idea generation with restriction/challenge")
    print("   ✓ Challenge → Process → Result structure")
    print("   ✓ Curiosity-driven titles (no past dates)")
    print("   ✓ Enhanced thumbnail with neon text")
    print("   ✓ 10s pauses between generations")
    print("   ✓ Today's news (NewsAPI)")
    print("   ✓ Category: People & Blogs (22)")
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
    if publicadas >= META_DIARIA_LARGOS:
        print("✅ Long video already published today. Exiting.")
        sys.exit(0)
    
    tipos = ["news", "educational", "scam", "psychology", "analysis"]
    tipo = random.choice(tipos)
    print(f"📌 Type: {tipo.upper()}")
    
    estado = cargar_estado()
    fondo_path = seleccionar_fondo_disponible(estado)
    
    print("💡 Generating video idea...")
    idea_data = generar_idea_video_largo(tipo, fecha_formateada)
    if idea_data and "best_idea" in idea_data:
        idea = idea_data["best_idea"]
        print(f"   ✅ Selected idea: {idea['title']}")
        print(f"   🔥 Restriction: {idea['restriction']}")
    else:
        print("⚠️ No idea generated, using fallback topic.")
        idea = None
    
    guion, tema, restriccion = generar_guion_largo(tipo, fecha_formateada, idea)
    titulo = guion["title"]
    descripcion = guion["description"]
    tags_str = guion.get("tags", "")
    segmentos = guion["segments"]
    palabras_portada = guion.get("cover_words", "CHALLENGE")
    prompt_miniatura = guion.get("thumbnail_prompt", "")
    
    capitulos = []
    for seg in segmentos:
        capitulos.append({"bloque": seg.get("block", "CHAPTER")})
    
    recursos = []
    for idx, seg in enumerate(segmentos):
        print(f"🎬 Segment {idx+1}/{len(segmentos)} - {seg.get('block', '')}")
        prompt_img = seg["image_prompt"]
        img_url = generar_imagen_horizontal(prompt_img, intentos=3)
        if not img_url:
            img_path = generar_fondo_solido()
            img_url = img_path
            print(f"   🖼️ Using solid background for segment {idx+1}")
        
        audio_path = generar_audio(seg["text"], idx)
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
            "texto": seg["text"],
            "bloque": seg.get("block", "")
        })
        time.sleep(15)
    
    if not recursos:
        print("❌ No resources generated.")
        sys.exit(1)
    
    video_path = montar_video_largo(recursos, fondo_path, "largo_capital_en.mp4", capitulos)
    print(f"🎬 Video assembled: {video_path}")
    
    miniatura_path = None
    if prompt_miniatura:
        print("🖼️ Generating professional thumbnail...")
        miniatura_path = crear_miniatura_profesional(
            prompt_miniatura,
            palabras_portada,
            "miniatura_largo_en.jpg"
        )
    
    video_id = subir_a_youtube(video_path, titulo, tags_str, descripcion, miniatura_path)
    
    guardar_titulo_publicado(titulo)
    guardar_tema_publicado(tema, tipo)
    incrementar_publicaciones_hoy()
    guardar_estado(estado)
    
    limpiar_archivos_temporales()
    
    print(f"✅ Published: https://youtu.be/{video_id}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
