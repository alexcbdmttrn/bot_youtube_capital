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
FACEBOOK_LINK = "https://www.facebook.com/tucapitaldigital"  # ⚠️ CAMBIA ESTO
CANAL_LINK = "https://www.youtube.com/@CapitalDigital"      # ⚠️ CAMBIA ESTO
ESTADO_FILE = "estado_capital_shorts.json"
TITULOS_FILE = "titulos_capital_shorts_publicados.json"
META_DIARIA_SHORTS = 3
ACTIVAR_DISCLOSURE_IA = True

# ================================================================
# VOCES PREMIUM
# ================================================================
VOCES_DISPONIBLES = [
    {"voz": "es-MX-JorgeNeural", "velocidad": "+8%", "tono": "-1Hz", "nombre": "Jorge (MX)"},
    {"voz": "es-ES-AlvaroNeural", "velocidad": "+8%", "tono": "-2Hz", "nombre": "Álvaro (ES)"},
    {"voz": "es-MX-ManuelNeural", "velocidad": "+8%", "tono": "0Hz", "nombre": "Manuel (MX)"},
    {"voz": "es-CL-LorenzoNeural", "velocidad": "+8%", "tono": "-1Hz", "nombre": "Lorenzo (CL)"},
]
CONFIG_VOZ_ACTUAL = random.choice(VOCES_DISPONIBLES)

# ================================================================
# PALETAS Y ESTILOS VISUALES (con acentos neón según etapa)
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

# Colores neón para acentos
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
# MÚSICA DE FONDO (opcional)
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
# 🎯 GENERAR GUION CON SEO PREMIUM (títulos de 50-70 caracteres)
# ================================================================
def generar_guion_financiero(tipo):
    titulos_pub = cargar_titulos_publicados()["titulos"][-10:]
    titulos_referencia = "\n".join([f"- {t}" for t in titulos_pub]) if titulos_pub else "Ninguno aún."

    # Temas ampliados
    TEMAS_NOTICIAS = [
        "Bitcoin rompe nuevo máximo histórico", "Inflación en México y su impacto en ahorros",
        "Oro alcanza precio récord", "Bancos centrales compran oro", 
        "Nuevo exchange de criptomonedas", "Regulación de cripto en Latinoamérica",
        "ETF de Bitcoin aprobado", "Remesas con criptomonedas", "Banca digital en México",
        "Seguros de vida con cripto", "Inversiones sostenibles", "Peso mexicano vs dólar",
        "Nuevo presidente de la CNBV", "Fintech en México 2026", "Cripto como reserva de valor"
    ]
    TEMAS_EDUCATIVOS = [
        "¿Cómo funciona un exchange de criptomonedas?", "¿Qué es el oro como inversión?",
        "¿Cómo proteger tus ahorros de la inflación?", "¿Qué son los ETFs?",
        "¿Cómo funcionan los seguros de vida?", "¿Qué es un swap en finanzas?",
        "¿Cómo invertir en bienes raíces?", "¿Qué es la diversificación?",
        "¿Cómo funciona el mercado de acciones?", "¿Qué son las criptomonedas estables?",
        "¿Qué es el interés compuesto?", "¿Cómo leer un estado financiero?",
        "¿Qué es un fideicomiso?", "¿Cómo funciona el crowdfunding?"
    ]
    TEMAS_ESTAFAS = [
        "El colapso de FTX", "La estafa de OneCoin", "Mt. Gox y el robo de Bitcoin",
        "El fraude de Bernie Madoff", "La crisis de las hipotecas subprime 2008",
        "El escándalo de Enron", "La estafa de QuadrigaCX", "El caso de BitConnect",
        "Fraude de Wirecard", "Estafa de PwC y Bank of Credit", "Caso de Olympus"
    ]

    if tipo == "noticia":
        tema_elegido = random.choice(TEMAS_NOTICIAS)
    elif tipo == "educativo":
        tema_elegido = random.choice(TEMAS_EDUCATIVOS)
    else:
        tema_elegido = random.choice(TEMAS_ESTAFAS)

    prompt = f"""Eres un EXPERTO EN FINANZAS, PERIODISTA ECONÓMICO y ESPECIALISTA EN SEO PARA YOUTUBE 2026.

📌 TEMA: "{tema_elegido}"
📌 TIPO: {tipo.upper()}

🎯 REGLAS DE CONTENIDO:
1. Relato ENGAÑOSO y cautivador desde el primer segundo.
2. Tono COLOQUIAL y DIRECTO.
3. LONGITUD: 150-170 palabras exactas.
4. ESTRUCTURA: GANCHO (5-10) → CONTEXTO (20-30) → DESARROLLO (80-90) → CIERRE PODEROSO (30-40).
5. Cierre con CTA sutil (ej. "¿Tú qué harías?", "Esto cambió todo").

🎯 REGLAS SEO PARA YOUTUBE SHORTS 2026 (CRÍTICO):
1. TÍTULO: 
   - Longitud OBLIGATORIA: entre 50 y 70 caracteres (¡NO MENOS DE 50!).
   - Fórmula: [PALABRA CLAVE] + [VERBO DE IMPACTO] + [GANCHO EMOCIONAL].
   - La PRIMERA PALABRA debe ser una de las palabras_clave.
   - Ejemplos válidos (50-70 chars):
     * "Enron: cómo el fraude más grande de Wall Street destruyó todo"
     * "Bitcoin en máximo histórico: ¿qué hacer con tus criptomonedas?"
     * "FTX colapsó y esto pasó con el dinero de los inversores"
   - PROHIBIDO: títulos genéricos o cortos.

2. PALABRAS CLAVE (2-3): Términos de alto volumen de búsqueda en finanzas/cripto.
   - Ejemplos: Bitcoin, Inflación, Oro, Inversión, Exchange, ETF, Bancos, Seguros, Finanzas personales.

3. TAGS (15-20): Combina:
   - Tags principales de alto volumen (ej. bitcoin, finanzas, inversiones, oro, criptomonedas)
   - Tags long-tail (ej. como invertir en oro, que es un exchange, mejores ETFs 2026)
   - Tags de tendencia (ej. mercado financiero 2026, cripto noticias)
   - Tags geográficos (México, Latinoamérica, Estados Unidos)
   - Tags específicos del tema (ej. Enron, FTX, Madoff)

4. DESCRIPCIÓN:
   - Línea 1: Gancho de 90 caracteres máximo.
   - Línea 2: Contexto en una oración.
   - Línea 3: Fuente del relato.
   - Línea 4: CTA al canal.
   - Línea 5: Redes sociales.
   - Línea 6: Hashtags (máx 5, con #Shorts incluido).

5. PALABRAS PORTADA: 2-3 palabras cortas e impactantes para miniatura (ej. "RÉCORD", "COLAPSO", "¿QUÉ HAGO?").

🚫 TÍTULOS YA PUBLICADOS (NO REPETIR):
{titulos_referencia}

📤 RESPUESTA: Devuelve ESTRICTAMENTE este JSON:
{{
    "titulo": "Título SEO de 50-70 caracteres con keyword al inicio",
    "titulo_alternativo": "Segundo título para A/B testing (también de 50-70 chars)",
    "anio_suceso": 2024,
    "palabras_clave": ["keyword1", "keyword2", "keyword3"],
    "gancho_descripcion": "Gancho de 90 caracteres máximo",
    "contexto_descripcion": "Una oración de contexto",
    "fuente_relato": "Fuente del relato (ej. 'Basado en análisis de mercado')",
    "texto_completo": "Relato de 150-170 palabras",
    "palabras_portada": "2-3 palabras para miniatura",
    "tags": "15-20 tags separados por coma (máx 480 caracteres)",
    "tema_especifico": "{tema_elegido}"
}}
"""

    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 1300,
        "response_format": {"type": "json_object"}
    }

    for intento in range(6):
        try:
            print(f"🔄 Intento {intento+1}/6 generando guion {tipo}...")
            print(f"📌 Tema: {tema_elegido}")
            r = requests.post(url, headers=headers, json=payload, timeout=90)
            r.raise_for_status()
            respuesta = r.json()["choices"][0]["message"]["content"].strip()
            
            # Limpiar JSON
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

            # Validar texto
            if "texto_completo" not in data or len(data["texto_completo"]) < 100:
                raise ValueError("Texto demasiado corto")
            data["texto_completo"] = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', data["texto_completo"])

            # 🔥 FORZAR TÍTULO DE AL MENOS 50 CARACTERES
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

            # 🔥 SI EL TÍTULO TIENE MENOS DE 50 CARACTERES, RELLENAR CON MÁS CONTEXTO
            if len(titulo) < 50:
                # Agregar más palabras al final para llegar a 50
                tema_palabras = tema_elegido.split()
                if len(tema_palabras) > 3:
                    extra = " " + " ".join(tema_palabras[-3:])
                else:
                    extra = " - Análisis financiero completo"
                titulo = (titulo + extra)[:70]  # Cortar en 70 si excede
                # Asegurar que termine bien
                if len(titulo) < 50:
                    titulo = titulo + " - Lo que debes saber"
                    titulo = titulo[:70]

            data["titulo"] = titulo

            if titulo_ya_publicado(titulo):
                print(f"   ⚠️ Título YA PUBLICADO. Regenerando...")
                raise ValueError("Título duplicado")

            # Generar hashtags
            hashtags = ["#Shorts"]
            if keywords:
                for kw in keywords[:2]:
                    kw_clean = re.sub(r'[áéíóú]', lambda m: {'á':'a','é':'e','í':'i','ó':'o','ú':'u'}.get(m.group(), m.group()), kw)
                    kw_clean = re.sub(r'[^a-zA-Z0-9]', '', kw_clean)
                    if kw_clean and len(kw_clean) > 2:
                        hashtags.append(f"#{kw_clean.capitalize()}")
            hashtags.append(random.choice(["#Finanzas", "#Cripto", "#Inversiones", "#Economía", "#Oro", "#Bancos", "#EducaciónFinanciera"]))
            data["hashtags_descripcion"] = " ".join(hashtags)

            # 🔥 MEJORAR TAGS: Asegurar variedad y alto volumen
            tags_raw = data.get("tags", "")
            tags_list = [t.strip() for t in tags_raw.split(",") if t.strip()]
            
            # Tags principales (siempre presentes)
            tags_principales = ["finanzas", "inversiones", "economia", "bitcoin", "oro", "bancos", "seguros", "exchanges", "criptomonedas", "mercado financiero", "educación financiera"]
            
            # Tags específicos por tema
            tema_lower = tema_elegido.lower()
            if "bitcoin" in tema_lower or "cripto" in tema_lower:
                tags_principales.extend(["bitcoin", "criptomonedas", "blockchain", "inversiones en cripto"])
            if "oro" in tema_lower:
                tags_principales.extend(["oro", "inversiones en oro", "metales preciosos", "reserva de valor"])
            if "estafa" in tema_lower or "fraude" in tema_lower or "colapso" in tema_lower:
                tags_principales.extend(["estafas financieras", "fraude", "crisis financiera", "historia de fraudes"])
            if "etf" in tema_lower:
                tags_principales.extend(["etf", "fondos cotizados", "inversiones pasivas"])
            if "seguro" in tema_lower:
                tags_principales.extend(["seguros", "protección financiera", "planeación financiera"])
            
            # Tags geográficos
            tags_geograficos = ["méxico", "latinoamérica", "estados unidos", "wall street", "economía global"]
            
            # Tags long-tail
            tags_longtail = [
                "como invertir", "que es un exchange", "mejores ETFs", "ahorros e inversiones",
                "finanzas personales", "educación financiera para principiantes", "mercados financieros",
                "análisis económico", "consejos financieros", "inversiones seguras", "dinero e inversión"
            ]
            
            # Mezclar y seleccionar 15-20 tags
            tags_final = set()
            # Añadir keywords principales
            for kw in keywords:
                if kw.lower() not in tags_final:
                    tags_final.add(kw.lower())
            # Añadir tags principales (hasta 8)
            for tag in tags_principales:
                if len(tags_final) < 8:
                    tags_final.add(tag)
            # Añadir tags geográficos (2-3)
            for tag in random.sample(tags_geograficos, min(3, len(tags_geograficos))):
                if len(tags_final) < 12:
                    tags_final.add(tag)
            # Añadir tags long-tail (hasta 15-18)
            for tag in random.sample(tags_longtail, min(6, len(tags_longtail))):
                if len(tags_final) < 18:
                    tags_final.add(tag)
            # Añadir tags del tema (si no están ya)
            for tag in tags_list:
                if len(tags_final) < 20 and tag.lower() not in tags_final and len(tag) > 2:
                    tags_final.add(tag.lower())
            
            data["tags"] = ", ".join(list(tags_final)[:20])
            
            print(f"   🏷️ Título: {data['titulo']} ({len(data['titulo'])} chars)")
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
# 🎨 GENERAR PROMPT DE IMAGEN CON ESTRATEGIA REAL + NEÓN
# ================================================================
def generar_prompt_imagen_segmento(segmento_texto, etapa, ubicacion_escena, 
                                   segmento_anterior_texto=None, 
                                   index_segmento=0, total_segmentos=1, 
                                   tema=None, es_primer_frame=False):
    """
    Estrategia visual de retención:
    - Frame 0 (primer segmento): NEÓN impactante (scroll-stopper)
    - Segmentos intermedios: REAL + acento neón (10-30%)
    - Último segmento: 100% REAL (cierre creíble)
    """
    contexto_previo = ""
    if segmento_anterior_texto:
        contexto_previo = f"\nPREVIOUS SCENE: '{segmento_anterior_texto[:120]}'"

    # Determinar el estilo de imagen según la etapa y posición
    if es_primer_frame and index_segmento == 0:
        # Primer frame: NEÓN impactante (scroll-stopper)
        estilo_base = f"NEON NOIR aesthetic, cyberpunk financial vibe, intense {COLOR_NEON_ACTUAL} glow on surfaces, high contrast, electric atmosphere, dramatic shadows, futuristic corporate look"
        porcentaje_real = 0
        porcentaje_neon = 100
    elif etapa in ["climax"]:
        # Clímax: Real + NEÓN fuerte (50/50)
        estilo_base = f"Hyperrealistic photography combined with intense {COLOR_NEON_ACTUAL} neon accents, dramatic lighting, high contrast, cinematic composition, financial crisis atmosphere"
        porcentaje_real = 50
        porcentaje_neon = 50
    elif etapa in ["evento_principal", "analisis_datos"]:
        # Evento principal: Real + acento neón (70/30)
        estilo_base = f"Realistic photograph with subtle {COLOR_NEON_ACTUAL} neon highlights, natural lighting mixed with artificial glow, professional corporate setting"
        porcentaje_real = 70
        porcentaje_neon = 30
    elif etapa in ["contexto_general"]:
        # Contexto: Real puro (100% real)
        estilo_base = f"Authentic documentary-style photograph, natural lighting, real-world environment, no filters, no neon"
        porcentaje_real = 100
        porcentaje_neon = 0
    else:  # resolución
        # Resolución: 100% REAL (cierre creíble)
        estilo_base = f"Realistic, natural photograph, natural lighting, authentic environment, calm atmosphere, no artificial effects"
        porcentaje_real = 100
        porcentaje_neon = 0

    # Construir prompt con nivel de detalle según el estilo
    if porcentaje_neon > 70:
        descripcion_estilo = f"{estilo_base}, vertical 9:16, {PALETA_BASE_ACTUAL} with {COLOR_NEON_ACTUAL} accents, sharp focus, hyperdetailed, 8k resolution, cinematic"
    elif porcentaje_neon > 20:
        descripcion_estilo = f"{estilo_base}, vertical 9:16, {PALETA_BASE_ACTUAL} with subtle neon touches, realistic textures, professional photography, 4k quality"
    else:
        descripcion_estilo = f"{estilo_base}, vertical 9:16, {PALETA_BASE_ACTUAL}, natural tones, documentary style, sharp focus, authentic"

    # Ajustar según el tema (agregar elementos específicos)
    tema_lower = tema.lower() if tema else ""
    if "bitcoin" in tema_lower or "cripto" in tema_lower:
        elementos_tema = "digital currency, blockchain data, crypto screens, modern fintech environment"
    elif "oro" in tema_lower:
        elementos_tema = "gold bars, precious metals, vault, luxury banking setting"
    elif "estafa" in tema_lower or "fraude" in tema_lower or "colapso" in tema_lower:
        elementos_tema = "dramatic financial collapse scene, crisis atmosphere, concerned professionals"
    else:
        elementos_tema = "modern financial setting, professional environment"

    # Construir prompt completo
    prompt = f"""
You are a WORLD-CLASS CINEMATOGRAPHER specializing in FINANCIAL PHOTOGRAPHY with a focus on RETENTION OPTIMIZATION.

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

COMPOSITION RULES (CRITICAL FOR RETENTION):
1. SHOT TYPE: Wide or medium shot. ABSOLUTELY NO close-up of faces.
2. MAIN SUBJECT: The environment, objects, and setting (buildings, computers, screens, documents, gold, etc.).
3. If people appear: They occupy AT MOST 15% of the frame, small and at distance.
4. FOCUS: Sharp, hyperrealistic, premium quality.
5. ATMOSPHERE: Professional, sophisticated, clean, high-end.
6. COLOR HARMONY: {PALETA_BASE_ACTUAL} with appropriate neon accents as indicated.

ABSOLUTE PROHIBITIONS:
- NO close-up faces, NO portraits, NO headshots
- NO gore, NO blood, NO violence
- NO clones, NO duplicates, NO twins
- NO text, NO watermarks, NO logos
- NO low quality, NO blurry images
- NO abandoned or ruined environments (unless specifically historical)

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
        # Añadir detalles de calidad premium
        prompt_img += f", hyperrealistic, 8k resolution, sharp focus, professional corporate photography, vertical 9:16, wide establishing shot, environment as main subject, no close-up face, no text, no watermark"
        return prompt_img
    except Exception as e:
        print(f"⚠️ Error generando prompt de imagen: {e}")
        # Fallback con estilo básico
        return f"Wide establishing shot of {ubicacion_escena}, vertical 9:16, financial environment, hyperrealistic, 8k quality, {PALETA_BASE_ACTUAL}"

# ================================================================
# 🖼️ GENERAR IMAGEN CON AGNES
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
            time.sleep(8 * (intento + 1))
    return None

# ================================================================
# 📝 GENERAR AUDIO
# ================================================================
def generar_audio(texto, index, intentos_por_voz=2):
    global CONFIG_VOZ_ACTUAL
    
    texto_limpio = re.sub(r'[^a-zA-ZáéíóúüñÁÉÍÓÚÜÑ0-9\s.,;:!?¿¡\'\"]', '', texto)
    texto_limpio = re.sub(r'\s+', ' ', texto_limpio).strip()
    
    if len(texto_limpio) < 30:
        texto_limpio = "Noticias financieras de hoy en Capital Digital."
    
    filename = f"audio_capital_{index}.mp3"
    
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
# 🎬 GENERAR RECURSOS POR SEGMENTO (con estrategia visual)
# ================================================================
def generar_recursos_por_segmento(segmentos, etapas, ubicaciones, tema=None, intentos_imagen=3):
    recursos = []
    total = len(segmentos)
    
    for idx, seg in enumerate(segmentos):
        print(f"  🎬 Segmento {idx+1}/{total} ({len(seg.split())} palabras)")
        etapa = etapas[idx] if idx < len(etapas) else "contexto_general"
        ubic = ubicaciones[idx] if idx < len(ubicaciones) else "oficina financiera"
        seg_anterior = segmentos[idx-1] if idx > 0 else None
        
        # Determinar si es el primer frame (scroll-stopper)
        es_primer_frame = (idx == 0)
        
        # Generar prompt con estrategia real+neón
        prompt_img = generar_prompt_imagen_segmento(
            seg, etapa, ubic, seg_anterior, 
            idx, total, tema, es_primer_frame
        )
        print(f"    📝 Prompt generado (primeros 120 chars): {prompt_img[:120]}...")
        
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
        
        try:
            dur = AudioFileClip(audio_path).duration
        except:
            dur = 8.0
        
        recursos.append({
            "imagen_url": img_url,
            "audio_path": audio_path,
            "duracion": dur,
            "etapa": etapa,
            "estilo": "real+neon" if "neon" in prompt_img.lower() else "real"
        })
        
        if idx < total - 1:
            time.sleep(12)
    
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
    
    # Limpiar temporales
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
            "containsSyntheticMedia": True,
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
    print("🎬 Capital Digital - Bot de SHORTS (Estrategia REAL+NEÓN)")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🎤 Voz: {CONFIG_VOZ_ACTUAL['nombre']}")
    print(f"🎨 Paleta: {PALETA_BASE_ACTUAL}")
    print(f"💡 Color neón: {COLOR_NEON_ACTUAL}")
    print("="*60)
    
    if not YOUTUBE_USER_TOKEN:
        print("❌ Falta YOUTUBE_USER_TOKEN_CAPITAL")
        sys.exit(1)
    
    publicadas = obtener_publicaciones_hoy()
    if publicadas >= META_DIARIA_SHORTS:
        print(f"✅ Ya se publicaron {META_DIARIA_SHORTS} shorts hoy. Saliendo.")
        sys.exit(0)
    
    hora = datetime.now(pytz.timezone("America/Mexico_City")).hour
    if 7 <= hora < 11:
        tipo = "noticia"
    elif 11 <= hora < 16:
        tipo = "educativo"
    else:
        tipo = "estafa"
    
    print(f"📌 Tipo: {tipo.upper()}")
    
    estado = cargar_estado()
    fondo_path = seleccionar_fondo_disponible(estado)
    
    guion = generar_guion_financiero(tipo)
    texto = guion["texto_completo"]
    tema = guion.get("tema_especifico", "")
    print(f"📝 Texto: {len(texto.split())} palabras")
    print(f"📌 Tema: {tema}")
    
    segmentos = dividir_en_segmentos(texto, max_palabras_por_segmento=45)
    etapas, ubicaciones = asignar_etapas_visuales(segmentos)
    print(f"🎬 {len(segmentos)} segmentos generados")
    
    recursos = generar_recursos_por_segmento(segmentos, etapas, ubicaciones, tema)
    if not recursos:
        print("❌ Error generando recursos.")
        sys.exit(1)
    
    video_path = montar_video_shorts(recursos, fondo_path, "short_capital.mp4")
    print(f"🎬 Video generado: {video_path}")
    
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
    incrementar_publicaciones_hoy()
    guardar_estado(estado)
    
    print("✅ Short publicado exitosamente!")
    print(f"🔗 https://youtu.be/{video_id}")
    print("="*60)

# ================================================================
# AUXILIARES
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
            ubic = "distrito financiero moderno, oficinas corporativas, entorno profesional"
        elif progreso < 0.4:
            etapa = "analisis_datos"
            ubic = "sala de trading con pantallas, gráficos financieros, computadoras"
        elif progreso < 0.65:
            etapa = "evento_principal"
            ubic = "lugar del suceso financiero (banco, exchange, junta ejecutiva)"
        elif progreso < 0.85:
            etapa = "climax"
            ubic = "momento crítico, tensión financiera máxima"
        else:
            etapa = "resolucion"
            ubic = "conclusión, regreso a la normalidad, ambiente calmado"
        
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
