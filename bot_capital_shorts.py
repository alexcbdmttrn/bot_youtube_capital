import asyncio
from datetime import datetime
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
from PIL import Image, ImageOps
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
FACEBOOK_LINK = "https://www.facebook.com/tucapitaldigital"  # Cambia por tu página
CANAL_LINK = "https://www.youtube.com/@CapitalDigital"      # Cambia por tu canal
ESTADO_FILE = "estado_capital_shorts.json"
TITULOS_FILE = "titulos_capital_shorts_publicados.json"
META_DIARIA_SHORTS = 3
ACTIVAR_DISCLOSURE_IA = True  # 🔴 Activa el botón "Contenido generado con IA"

# ================================================================
# VOCES PREMIUM (edge-tts) - Voces naturales en español
# ================================================================
VOCES_DISPONIBLES = [
    {"voz": "es-MX-JorgeNeural", "velocidad": "+8%", "tono": "-1Hz", "nombre": "Jorge (MX)"},
    {"voz": "es-ES-AlvaroNeural", "velocidad": "+8%", "tono": "-2Hz", "nombre": "Álvaro (ES)"},
    {"voz": "es-MX-ManuelNeural", "velocidad": "+8%", "tono": "0Hz", "nombre": "Manuel (MX)"},
    {"voz": "es-CL-LorenzoNeural", "velocidad": "+8%", "tono": "-1Hz", "nombre": "Lorenzo (CL)"},
]
CONFIG_VOZ_ACTUAL = random.choice(VOCES_DISPONIBLES)

# ================================================================
# PALETAS DE COLOR PREMIUM (look cinematográfico)
# ================================================================
PALETAS_COLOR = [
    "Corporate blue and silver, LED trading screens, clean white light, modern office atmosphere",
    "Dark emerald green and gold, financial district at night, warm tungsten lighting, luxury banking decor",
    "Slate gray and cyan, modern trading floor, glass reflections, cool professional lighting",
    "Deep navy and amber, executive office, soft warm glow, mahogany and leather",
    "Muted teal and white, minimalist fintech office, natural daylight, clean aesthetic",
    "Crisp black and gold, Wall Street style, dramatic shadows, prestige atmosphere",
    "Cool steel blue and silver, high-tech trading environment, digital displays, futuristic vibe",
]
PALETA_COLOR_ACTUAL = random.choice(PALETAS_COLOR)

# ================================================================
# ESTILOS VISUALES PREMIUM (calidad cinematográfica)
# ================================================================
ESTILOS_VISUALES = [
    "Cinematic photograph, dramatic lighting, sharp focus, film still, 8k resolution, hyperrealistic",
    "Documentary style, natural lighting, authentic textures, professional corporate aesthetic",
    "High-end commercial photography, studio lighting, premium quality, clean composition",
    "Financial magazine photography style, editorial quality, sophisticated atmosphere",
    "Modern minimalist photography, clean lines, professional environment, natural tones",
]
ESTILO_VISUAL_ACTUAL = random.choice(ESTILOS_VISUALES)

# ================================================================
# MÚSICA DE FONDO (usa archivos .mp3 en la raíz del repositorio)
# ================================================================
FONDOS_DISPONIBLES = [
    "Ash and Marrow.mp3", "Black Maw.mp3", "Cold Hollow.mp3",
    "Hollow Marrow.mp3", "Sunken Dread.mp3", "Sunless Vault.mp3", "The Deep Rot.mp3"
]
# 🔴 Recomendación: Sube archivos de música libre de derechos financiera/urbana.
# Si no tienes, el bot funcionará igual sin música de fondo.

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
# 🎯 GENERAR GUION FINANCIERO CON SEO PREMIUM
# ================================================================
def generar_guion_financiero(tipo):
    """
    tipo: 'noticia', 'educativo', 'estafa'
    """
    titulos_pub = cargar_titulos_publicados()["titulos"][-10:]
    titulos_referencia = "\n".join([f"- {t}" for t in titulos_pub]) if titulos_pub else "Ninguno aún."

    # Base de datos de temas financieros actuales para variedad
    TEMAS_NOTICIAS = [
        "Bitcoin rompe nuevo máximo histórico", "Inflación en México y su impacto en ahorros",
        "Oro alcanza precio récord", "Bancos centrales compran oro", 
        "Nuevo exchange de criptomonedas", "Regulación de cripto en Latinoamérica",
        "ETF de Bitcoin aprobado", "Remesas con criptomonedas", "Banca digital en México",
        "Seguros de vida con cripto", "Inversiones sostenibles"
    ]
    
    TEMAS_EDUCATIVOS = [
        "¿Cómo funciona un exchange de criptomonedas?", "¿Qué es el oro como inversión?",
        "¿Cómo proteger tus ahorros de la inflación?", "¿Qué son los ETFs?",
        "¿Cómo funcionan los seguros de vida?", "¿Qué es un swap en finanzas?",
        "¿Cómo invertir en bienes raíces?", "¿Qué es la diversificación?",
        "¿Cómo funciona el mercado de acciones?", "¿Qué son las criptomonedas estables?"
    ]
    
    TEMAS_ESTAFAS = [
        "El colapso de FTX", "La estafa de OneCoin", "Mt. Gox y el robo de Bitcoin",
        "El fraude de Bernie Madoff", "La crisis de las hipotecas subprime 2008",
        "El escándalo de Enron", "La estafa de QuadrigaCX", "El caso de BitConnect"
    ]

    # Elegir un tema aleatorio del tipo correspondiente
    if tipo == "noticia":
        tema_elegido = random.choice(TEMAS_NOTICIAS)
    elif tipo == "educativo":
        tema_elegido = random.choice(TEMAS_EDUCATIVOS)
    else:  # estafa
        tema_elegido = random.choice(TEMAS_ESTAFAS)

    prompt = f"""Eres un EXPERTO EN FINANZAS, PERIODISTA ECONÓMICO y ESPECIALISTA EN SEO PARA YOUTUBE 2026.

📌 TEMA A TRATAR: "{tema_elegido}"
📌 TIPO DE CONTENIDO: {tipo.upper()}

🎯 REGLAS CRÍTICAS DE CONTENIDO:
1. El relato DEBE ser ENGAÑOSO y cautivador desde el primer segundo.
2. Usa un TONO COLOQUIAL y DIRECTO (como si estuvieras contando una historia a un amigo).
3. LONGITUD EXACTA: entre 150 y 170 palabras.
4. ESTRUCTURA: GANCHO (5-10 palabras) → CONTEXTO (20-30) → DESARROLLO (80-90) → CIERRE PODEROSO (30-40).
5. El cierre debe incluir una llamada a la acción sutil (ej. "¿Tú qué harías?", "Esto cambió todo", etc.)

🎯 REGLAS SEO PARA YOUTUBE SHORTS 2026:
1. TÍTULO: Fórmula [PALABRA CLAVE] + [VERBO DE IMPACTO] + [GANCHO EMOCIONAL]
   - Longitud: 55-70 caracteres
   - La PRIMERA PALABRA debe ser una de las palabras_clave
   - Ejemplos: "Bitcoin rompe récord y esto pasó", "Oro se dispara ¿qué hago?", "FTX colapsó y perdí todo"
   - PROHIBIDO: títulos genéricos como "El misterio de...", "La verdad sobre..."
   
2. PALABRAS CLAVE (2-3): Deben ser términos de búsqueda con alto volumen en finanzas.
   
3. TAGS (10-15): Combina:
   - Tags principales (ej. bitcoin, finanzas, inversiones)
   - Tags long-tail (ej. como invertir en oro, que es un exchange)
   - Tags de tendencia (ej. criptomonedas 2026, mercado financiero)
   - Tags geográficos (México, Latinoamérica)
   
4. DESCRIPCIÓN: 
   - Línea 1: Gancho de máximo 90 caracteres
   - Línea 2: Contexto en una oración
   - Línea 3: Fuente o base del relato
   - Línea 4: CTA al canal
   - Línea 5: Redes sociales
   - Línea 6: Hashtags (máx 5)

5. PALABRAS PORTADA: 2-3 palabras cortas e impactantes para la miniatura.
   Ejemplos: "RÉCORD", "¿QUÉ HAGO?", "COLAPSO", "GANAS", "PIERDE", "SUBE"

🎯 REGLAS DE ÉPOCA:
- Si el tema es histórico (estafa), usa el año exacto del suceso.
- Si es actual o educativo, usa el año actual.

🚫 TÍTULOS YA PUBLICADOS (NO REPETIR):
{titulos_referencia}

📤 RESPUESTA: Devuelve ESTRICTAMENTE este JSON:
{{
    "titulo": "Título SEO 55-70 caracteres con keyword al inicio",
    "titulo_alternativo": "Segundo título para A/B testing",
    "anio_suceso": 2024,
    "palabras_clave": ["keyword1", "keyword2", "keyword3"],
    "gancho_descripcion": "Gancho de 90 caracteres máximo",
    "contexto_descripcion": "Una oración de contexto",
    "fuente_relato": "Fuente del relato (ej. 'Basado en análisis de mercado')",
    "texto_completo": "Relato de 150-170 palabras en primera persona o tercera, tono coloquial",
    "palabras_portada": "2-3 palabras para miniatura",
    "tags": "10-15 tags separados por coma (máx 480 caracteres)",
    "tema_especifico": "{tema_elegido}"
}}
"""

    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 1200,
        "response_format": {"type": "json_object"}
    }

    for intento in range(6):
        try:
            print(f"🔄 Intento {intento+1}/6 generando guion {tipo}...")
            print(f"📌 Tema: {tema_elegido}")
            r = requests.post(url, headers=headers, json=payload, timeout=90)
            r.raise_for_status()
            respuesta = r.json()["choices"][0]["message"]["content"].strip()
            
            # Limpiar respuesta
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

            # Validar campos
            if "texto_completo" not in data or len(data["texto_completo"]) < 100:
                raise ValueError("Texto demasiado corto")
            
            data["texto_completo"] = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', data["texto_completo"])

            # Limpiar título
            titulo = data.get("titulo", "").strip()
            titulo = re.sub(r'#\w+', '', titulo).strip()
            titulo = ' '.join(titulo.split())
            
            # Forzar keyword al inicio del título
            keywords = data.get("palabras_clave", [])
            if keywords and isinstance(keywords, list) and keywords:
                primera_kw = keywords[0].strip()
                if primera_kw and not titulo.lower().startswith(primera_kw.lower()):
                    # Limpiar artículos iniciales
                    titulo_sin_art = re.sub(r'^(El|La|Los|Las|Un|Una|Unos|Unas)\s+', '', titulo, flags=re.IGNORECASE)
                    if titulo_sin_art != titulo:
                        titulo = f"{primera_kw.capitalize()} {titulo_sin_art}"
                    else:
                        titulo = f"{primera_kw.capitalize()} {titulo}"
                
                # Asegurar que no exceda 75 caracteres
                if len(titulo) > 75:
                    titulo = titulo[:72] + "..."
            
            data["titulo"] = titulo

            # Verificar duplicado
            if titulo_ya_publicado(titulo):
                print(f"   ⚠️ Título YA PUBLICADO. Regenerando...")
                raise ValueError("Título duplicado")

            # Actualizar época
            anio = data.get("anio_suceso")
            if anio:
                print(f"📅 Año del suceso: {anio}")

            # Generar hashtags dinámicos
            hashtags = ["#Shorts"]
            if keywords:
                for kw in keywords[:2]:
                    kw_clean = re.sub(r'[áéíóú]', lambda m: {'á':'a','é':'e','í':'i','ó':'o','ú':'u'}.get(m.group(), m.group()), kw)
                    kw_clean = re.sub(r'[^a-zA-Z0-9]', '', kw_clean)
                    if kw_clean and len(kw_clean) > 2:
                        hashtags.append(f"#{kw_clean.capitalize()}")
            hashtags.append(random.choice(["#Finanzas", "#Cripto", "#Inversiones", "#Economía", "#Oro", "#Bancos"]))
            data["hashtags_descripcion"] = " ".join(hashtags)

            # Limpiar tags y añadir keywords
            tags_raw = data.get("tags", "")
            tags_list = [t.strip() for t in tags_raw.split(",") if t.strip()][:15]
            for kw in keywords:
                if kw.lower() not in [t.lower() for t in tags_list]:
                    tags_list.append(kw.lower())
            
            # Añadir tags de respaldo
            extras = ["finanzas", "inversiones", "economia", "bitcoin", "oro", "bancos", "seguros", "exchanges"]
            i = 0
            while len(tags_list) < 10 and i < len(extras):
                if extras[i] not in tags_list:
                    tags_list.append(extras[i])
                i += 1
            data["tags"] = ", ".join(tags_list[:15])

            print(f"   🏷️ Título SEO: {data['titulo']} ({len(data['titulo'])} chars)")
            print(f"   🔑 Keywords: {keywords}")
            print(f"   📌 Tema: {data.get('tema_especifico', 'N/A')}")
            return data
            
        except Exception as e:
            print(f"❌ Intento {intento+1}/6 falló: {e}")
            if intento < 5:
                time.sleep(8 + intento * 3)

    print("❌ TODOS LOS INTENTOS FALLARON.")
    sys.exit(1)

# ================================================================
# 🖼️ GENERAR PROMPT DE IMAGEN PREMIUM PARA AGNES
# ================================================================
def generar_prompt_imagen_segmento(segmento_texto, etapa, ubicacion_escena, segmento_anterior_texto=None, index_segmento=0, total_segmentos=1, tema=None):
    contexto_previo = ""
    if segmento_anterior_texto:
        contexto_previo = f"\nPREVIOUS SCENE: '{segmento_anterior_texto[:120]}'"

    # Instrucciones de etapa con descripciones más ricas
    instrucciones_etapa = {
        "contexto_general": f"Wide establishing shot of a modern financial district or corporate environment, skyscrapers, glass buildings, professional atmosphere, {PALETA_COLOR_ACTUAL}, sharp focus, hyperrealistic, 8k quality",
        "analisis_datos": f"Close-up composition of financial data screens, trading charts, candlestick graphs, monitors with stock market data, modern office equipment, {PALETA_COLOR_ACTUAL}, cinematic lighting, ultra-detailed",
        "evento_principal": f"Medium shot of a business environment, meeting room or office, professionals in business attire, documents, computer screens, financial decision moment, {PALETA_COLOR_ACTUAL}, documentary style, natural expressions",
        "climax": f"Dramatic financial event scene, intense atmosphere, people reacting, market volatility, trading floor energy, {PALETA_COLOR_ACTUAL}, dramatic lighting, cinematic composition",
        "resolucion": f"Calm aftermath scene, professionals reflecting, relaxed office atmosphere, conclusion of financial event, {PALETA_COLOR_ACTUAL}, warm lighting, peaceful composition",
    }
    
    # Adaptar según el tema
    if tema and "oro" in tema.lower():
        instrucciones_etapa["evento_principal"] += ", gold bars, precious metals, vault, luxury banking"
    elif tema and "bitcoin" in tema.lower() or "cripto" in tema.lower():
        instrucciones_etapa["evento_principal"] += ", cryptocurrency coins, digital screens with blockchain data, modern fintech"
    elif tema and "estafa" in tema.lower() or "colapso" in tema.lower():
        instrucciones_etapa["climax"] += ", dramatic financial collapse, concerned faces, crisis atmosphere"

    instruccion = instrucciones_etapa.get(etapa, instrucciones_etapa["contexto_general"])

    # Ángulos de cámara variados
    angulos = [
        "eye level shot, natural perspective",
        "slightly high angle, comprehensive view",
        "slightly low angle, dramatic effect",
        "wide establishing shot, immersive environment",
        "medium shot, balanced composition"
    ]
    angulo = angulos[index_segmento % len(angulos)]

    prompt = f"""
You are a WORLD-CLASS CINEMATOGRAPHER specializing in FINANCIAL and CORPORATE photography for premium YouTube content.

STORY SEGMENT:
\"\"\"
{segmento_texto}
\"\"\"
{contexto_previo}

CREATE A PREMIUM PHOTO PROMPT for a vertical (9:16) image.

SCENE DETAILS:
- STAGE: {etapa}
- LOCATION: {ubicacion_escena}
- CAMERA ANGLE: {angulo}
- VISUAL STYLE: {ESTILO_VISUAL_ACTUAL}
- COLOR PALETTE: {PALETA_COLOR_ACTUAL}

COMPOSITION RULES (STRICT):
1. SHOT TYPE: Wide or medium shot. ABSOLUTELY NO close-up of faces.
2. MAIN SUBJECT: The environment, objects, and setting (buildings, computers, screens, documents, financial tools).
3. If people appear: They occupy AT MOST 15% of the frame, small and at distance.
4. If NO people are mentioned: Show ONLY the environment.
5. Style: Hyperrealistic, premium quality, sharp focus, natural lighting.
6. ERA: Modern, contemporary financial setting.
7. ATMOSPHERE: Professional, sophisticated, clean, high-end.

SPECIFIC SCENE DIRECTIVE: {instruccion}

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
        "max_tokens": 300,
    }
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=60)
        r.raise_for_status()
        prompt_img = r.json()["choices"][0]["message"]["content"].strip()
        # Añadir detalles de calidad premium
        prompt_img += f", hyperrealistic, 8k resolution, sharp focus, professional corporate photography, {ESTILO_VISUAL_ACTUAL}, vertical 9:16, wide establishing shot, environment as main subject, no close-up face, no text, no watermark"
        return prompt_img
    except Exception as e:
        print(f"⚠️ Error generando prompt de imagen: {e}")
        return f"Wide establishing shot of {ubicacion_escena}, vertical 9:16, financial environment, hyperrealistic, 8k quality, professional corporate photography, {PALETA_COLOR_ACTUAL}"

# ================================================================
# 🖼️ GENERAR IMAGEN CON AGNES (calidad premium)
# ================================================================
def generar_imagen_vertical(prompt, intentos=3):
    prompt = re.sub(r"\n+", " ", prompt).strip()
    prompt = re.sub(r'"', "'", prompt)
    prompt = prompt[:900]
    
    url = "https://apihub.agnes-ai.com/v1/images/generations"
    headers = {"Authorization": f"Bearer {AGNES_API_KEY}", "Content-Type": "application/json"}
    
    # Negative prompt más agresivo para evitar defectos
    negative = (
        "multiple people, crowd, group of people, two people, three people, "
        "close-up face, portrait, headshot, face filling frame, "
        "gore, blood, violence, weapons, "
        "clones, duplicates, twins, doppelganger, "
        "deformed, bad anatomy, extra limbs, missing limbs, "
        "blurry, low quality, pixelated, "
        "text, watermark, logo, signature, "
        "cartoon, animated, painting, drawing, sketch, "
        "oversaturated, oversharpened, artificial, fake, "
        "abandoned, rusty, decayed, ruined, "
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
            time.sleep(8 * (intento + 1))
    return None

# ================================================================
# 📝 GENERAR AUDIO CON EDGE-TTS (voz natural)
# ================================================================
def generar_audio(texto, index, intentos_por_voz=2):
    global CONFIG_VOZ_ACTUAL
    
    # Limpiar texto para TTS
    texto_limpio = re.sub(r'[^a-zA-ZáéíóúüñÁÉÍÓÚÜÑ0-9\s.,;:!?¿¡\'\"]', '', texto)
    texto_limpio = re.sub(r'\s+', ' ', texto_limpio).strip()
    
    if len(texto_limpio) < 30:
        texto_limpio = "Noticias financieras de hoy en Capital Digital."
    
    filename = f"audio_capital_{index}.mp3"
    
    # Probar voces en orden
    voces_a_probar = [CONFIG_VOZ_ACTUAL] + [v for v in VOCES_DISPONIBLES if v["voz"] != CONFIG_VOZ_ACTUAL["voz"]]
    
    for voz_config in voces_a_probar:
        voz = voz_config["voz"]
        rate = voz_config["velocidad"]
        pitch = voz_config["tono"]
        
        for intento in range(intentos_por_voz):
            async def _gen():
                communicate = edge_tts.Communicate(texto_limpio, voz, rate=rate, pitch=pitch)
                await communicate.save(filename)
            
            try:
                asyncio.run(_gen())
                if os.path.exists(filename) and os.path.getsize(filename) > 0:
                    if voz != CONFIG_VOZ_ACTUAL["voz"]:
                        print(f"🔄 Voz cambiada a {voz_config['nombre']}")
                        CONFIG_VOZ_ACTUAL = voz_config
                    return filename
            except Exception as e:
                print(f"   ❌ Falló {voz_config['nombre']}: {e}")
            time.sleep(3)
        
        if os.path.exists(filename):
            try: os.remove(filename)
            except: pass
    
    return None

# ================================================================
# 🎬 GENERAR RECURSOS POR SEGMENTO
# ================================================================
def generar_recursos_por_segmento(segmentos, etapas, ubicaciones, tema=None, intentos_imagen=3):
    recursos = []
    total = len(segmentos)
    
    for idx, seg in enumerate(segmentos):
        print(f"  🎬 Segmento {idx+1}/{total} ({len(seg.split())} palabras)")
        etapa = etapas[idx] if idx < len(etapas) else "contexto_general"
        ubic = ubicaciones[idx] if idx < len(ubicaciones) else "oficina financiera"
        seg_anterior = segmentos[idx-1] if idx > 0 else None
        
        # Generar prompt premium
        prompt_img = generar_prompt_imagen_segmento(
            seg, etapa, ubic, seg_anterior, 
            idx, total, tema
        )
        print(f"    📝 Prompt generado (primeros 100 chars): {prompt_img[:100]}...")
        
        # Generar imagen
        img_url = None
        for intento in range(intentos_imagen):
            img_url = generar_imagen_vertical(prompt_img, intentos=1)
            if img_url:
                print(f"    ✅ Imagen generada (intento {intento+1})")
                break
            time.sleep(6)
        
        if not img_url:
            print(f"    ⚠️ Imagen falló, usando placeholder")
            img_url = "https://via.placeholder.com/1080x1920/1a1a3a/4a8af4?text=Capital+Digital"
        
        # Generar audio
        audio_path = generar_audio(seg, idx)
        if not audio_path:
            print(f"    ❌ Falló audio en segmento {idx+1}. Abortando.")
            return None
        
        # Obtener duración
        try:
            dur = AudioFileClip(audio_path).duration
        except:
            dur = 8.0
        
        recursos.append({
            "imagen_url": img_url,
            "audio_path": audio_path,
            "duracion": dur
        })
        
        if idx < total - 1:
            time.sleep(12)  # Pausa entre imágenes para evitar rate limit
    
    return recursos

# ================================================================
# 🎬 MONTAR VIDEO SHORTS
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
        
        # Procesar imagen
        try:
            if img_url.startswith("http"):
                r = requests.get(img_url, timeout=30)
                r.raise_for_status()
                img_path = f"temp_cap_{i}.jpg"
                with open(img_path, "wb") as f:
                    f.write(r.content)
            else:
                img_path = img_url
            
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
        
        # Procesar audio
        try:
            audio = AudioFileClip(audio_path)
            clips_audio.append(audio)
        except:
            silencio = AudioClip(lambda t: 0, duration=duracion)
            clips_audio.append(silencio)
    
    # Concatenar audio con pausas
    PAUSA = 0.3
    audio_final_parts = []
    for i, aud in enumerate(clips_audio):
        audio_final_parts.append(aud)
        if i < len(clips_audio) - 1:
            sil = AudioClip(lambda t: 0, duration=PAUSA)
            audio_final_parts.append(sil)
    
    audio_narracion = concatenate_audioclips(audio_final_parts)
    duracion_total = audio_narracion.duration
    
    # Video
    video = concatenate_videoclips(clips_video, method="compose")
    video = video.set_duration(duracion_total)
    
    # Fondo musical
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
    
    # Limpiar archivos temporales de imagen
    for f in os.listdir("."):
        if f.startswith("temp_cap_") and f.endswith(".jpg"):
            try: os.remove(f)
            except: pass
        if f.startswith("placeholder_") and f.endswith(".jpg"):
            try: os.remove(f)
            except: pass
    
    return salida

# ================================================================
# 🚀 SUBIR A YOUTUBE CON DISCLOSURE IA
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
    
    # Construir descripción SEO
    descripcion = f"""{gancho}

{contexto}

🔴 SUSCRÍBETE al canal: {CANAL_LINK}

📖 {fuente}

📱 Síguenos en Facebook: {FACEBOOK_LINK}

{hashtags}"""

    if ACTIVAR_DISCLOSURE_IA:
        descripcion += "\n\n🤖 Este contenido ha sido generado con inteligencia artificial (relato e imágenes)."

    body = {
        "snippet": {
            "title": titulo[:100],
            "description": descripcion[:5000],
            "tags": etiquetas[:30],
            "categoryId": "24",
            "defaultLanguage": "es",
            "defaultAudioLanguage": "es",
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": True,  # 🔴 ACTIVA EL BOTÓN "CONTENIDO GENERADO CON IA"
        },
    }
    
    media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = request.execute()
    video_id = response["id"]
    print(f"✅ Short subido: https://youtu.be/{video_id}")
    return video_id

# ================================================================
# 🎯 MAIN
# ================================================================
def main():
    print("="*60)
    print("🎬 Capital Digital - Bot de SHORTS Premium")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🎤 Voz: {CONFIG_VOZ_ACTUAL['nombre']}")
    print("="*60)
    
    if not YOUTUBE_USER_TOKEN:
        print("❌ Falta YOUTUBE_USER_TOKEN_CAPITAL")
        sys.exit(1)
    
    # Verificar límite diario
    publicadas = obtener_publicaciones_hoy()
    if publicadas >= META_DIARIA_SHORTS:
        print(f"✅ Ya se publicaron {META_DIARIA_SHORTS} shorts hoy. Saliendo.")
        sys.exit(0)
    
    # Elegir tipo según la hora
    hora = datetime.now(pytz.timezone("America/Mexico_City")).hour
    if 7 <= hora < 11:
        tipo = "noticia"
    elif 11 <= hora < 16:
        tipo = "educativo"
    else:
        tipo = "estafa"
    
    print(f"📌 Tipo: {tipo.upper()}")
    print(f"🎨 Paleta de color: {PALETA_COLOR_ACTUAL[:50]}...")
    print(f"📷 Estilo visual: {ESTILO_VISUAL_ACTUAL[:50]}...")
    
    # Cargar estado y fondo musical
    estado = cargar_estado()
    fondo_path = seleccionar_fondo_disponible(estado)
    
    # Generar guion
    guion = generar_guion_financiero(tipo)
    texto = guion["texto_completo"]
    tema = guion.get("tema_especifico", "")
    print(f"📝 Texto: {len(texto.split())} palabras")
    print(f"📌 Tema: {tema}")
    
    # Dividir en segmentos
    segmentos = dividir_en_segmentos(texto, max_palabras_por_segmento=45)
    etapas, ubicaciones = asignar_etapas_visuales(segmentos)
    print(f"🎬 {len(segmentos)} segmentos generados")
    
    # Generar recursos
    recursos = generar_recursos_por_segmento(segmentos, etapas, ubicaciones, tema)
    if not recursos:
        print("❌ Error generando recursos.")
        sys.exit(1)
    
    # Montar video
    video_path = montar_video_shorts(recursos, fondo_path, "short_capital.mp4")
    print(f"🎬 Video generado: {video_path}")
    
    # Subir a YouTube
    video_id = subir_a_youtube(
        video_path=video_path,
        titulo=guion["titulo"],
        etiquetas=guion["tags"],
        gancho=guion["gancho_descripcion"],
        contexto=guion["contexto_descripcion"],
        hashtags=guion["hashtags_descripcion"],
        fuente=guion.get("fuente_relato", "Basado en análisis financiero")
    )
    
    # Guardar estado
    guardar_titulo_publicado(guion["titulo"])
    incrementar_publicaciones_hoy()
    guardar_estado(estado)
    
    print("✅ Short publicado exitosamente!")
    print(f"🔗 https://youtu.be/{video_id}")
    print("="*60)

# ================================================================
# FUNCIONES AUXILIARES
# ================================================================
def dividir_en_segmentos(texto, max_palabras_por_segmento=45):
    oraciones = re.split(r'(?<=[.!?¿¡])\s+', texto)
    oraciones = [o.strip() for o in oraciones if o.strip()]
    if not oraciones:
        return [texto]
    
    segmentos = []
    segmento_actual = []
    palabras_actuales = 0
    
    for oracion in oraciones:
        palabras_oracion = len(oracion.split())
        if palabras_actuales + palabras_oracion > max_palabras_por_segmento and segmento_actual:
            segmentos.append(" ".join(segmento_actual))
            segmento_actual = [oracion]
            palabras_actuales = palabras_oracion
        else:
            segmento_actual.append(oracion)
            palabras_actuales += palabras_oracion
    
    if segmento_actual:
        segmentos.append(" ".join(segmento_actual))
    
    return segmentos

def asignar_etapas_visuales(segmentos):
    n = len(segmentos)
    etapas = []
    ubicaciones = []
    
    for i in range(n):
        progreso = i / max(n-1, 1)
        
        if progreso < 0.2:
            etapa = "contexto_general"
            ubic = "distrito financiero moderno u oficina corporativa"
        elif progreso < 0.4:
            etapa = "analisis_datos"
            ubic = "sala de trading con pantallas y gráficos financieros"
        elif progreso < 0.65:
            etapa = "evento_principal"
            ubic = "lugar del suceso financiero (banco, exchange, junta ejecutiva)"
        elif progreso < 0.85:
            etapa = "climax"
            ubic = "momento crítico del evento financiero"
        else:
            etapa = "resolucion"
            ubic = "conclusión, regreso a la normalidad"
        
        etapas.append(etapa)
        ubicaciones.append(ubic)
    
    return etapas, ubicaciones

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ Error fatal: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
