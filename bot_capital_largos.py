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
# VOZ FIJA (Jorge) - +10%
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
    
    if not fondos_disponibles:
        fondos_disponibles = [os.path.join(root, f) for f in FONDOS_DISPONIBLES if os.path.exists(os.path.join(root, f))]
    
    seleccionada = random.choice(fondos_disponibles)
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
# TREND-JACKING
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
                    keywords = ["bitcoin", "cripto", "oro", "etf", "inflación", "banco", "finanzas", "dólar", "peso", "shiba", "dogecoin", "ethereum", "solana", "ftx", "binance", "exchange"]
                    if any(word in title.lower() for word in keywords):
                        return title[:100]
                return data["articles"][0].get("title", "")[:100]
        return None
    except Exception as e:
        print(f"⚠️ Error obteniendo trending: {e}")
        return None

# ================================================================
# GENERAR GUION LARGO (FORZADO A 1000-1200 PALABRAS)
# ================================================================
def generar_guion_largo(tipo):
    titulos_pub = cargar_titulos_publicados()["titulos"][-10:]
    titulos_referencia = "\n".join([f"- {t}" for t in titulos_pub]) if titulos_pub else "Ninguno aún."

    TEMAS_EDUCATIVOS = [
        "Cómo Invertir en Criptomonedas con Seguridad (Guía Completa)",
        "Bitcoin y Oro: Refugios en Crisis Económica",
        "Análisis Técnico vs Fundamental: Cuál es mejor para ti",
        "Los 5 Niveles Financieros que te llevarán a la Riqueza",
        "Cómo Funciona el Interés Compuesto y por qué te empobrece no usarlo",
        "Estrategias de Diversificación de Portafolio para 2026",
        "Cómo Identificar una Criptomoneda con Potencial (Fundamentals)",
        "Finanzas Descentralizadas (DeFi): Oportunidades y Riesgos",
        "Cómo Leer un Gráfico de Trading (Guía para Principiantes)",
        "Inversión Pasiva vs Activa: Cuál te conviene más"
    ]
    TEMAS_ESTAFAS_CRISIS = [
        "El Colapso de FTX: Lecciones Aprendidas",
        "Cómo Detectar Estafas Piramidales en Cripto",
        "El Caso Enron: La Mayor Estafa Corporativa",
        "La Crisis de las Hipotecas Subprime 2008 y su Paralelismo con Cripto",
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
        "Ethereum vs Solana: ¿Quién Ganará en 2026?",
        "Helium (HNT): Minería sin Tarjetas Gráficas, ¿Vale la Pena?",
        "Bittorrent (BTT): El Gigante Dormido del Almacenamiento",
        "Nuevas Altcoins con Potencial X10 (Análisis de Proyectos)"
    ]

    temas_pool = []
    if tipo == "educativo": temas_pool = TEMAS_EDUCATIVOS
    elif tipo == "estafa": temas_pool = TEMAS_ESTAFAS_CRISIS
    elif tipo == "psicologia": temas_pool = TEMAS_PSICOLOGIA
    else: temas_pool = TEMAS_ANALISIS

    temas_disponibles = [t for t in temas_pool if not tema_ya_publicado(t, DIAS_SIN_REPETIR_TEMA)]

    tema_elegido = None
    if tipo == "noticia":
        trending = obtener_tema_trending()
        if trending and not tema_ya_publicado(trending, DIAS_SIN_REPETIR_TEMA):
            tema_elegido = trending
            print(f"📰 Tema trending de NewsAPI: {tema_elegido}")
        else:
            tema_elegido = random.choice(temas_disponibles) if temas_disponibles else random.choice(TEMAS_EDUCATIVOS)
            print(f"📌 Tema de respaldo: {tema_elegido}")
    else:
        tema_elegido = random.choice(temas_disponibles) if temas_disponibles else random.choice(temas_pool)
        print(f"📌 Tema seleccionado: {tema_elegido}")

    # 🔥 PROMPT FORZANDO 1000-1200 PALABRAS
    prompt = f"""
Eres un CREADOR DE CONTENIDO FINANCIERO EXPERTO para YouTube y un GUIONISTA PROFESIONAL.
Tema: "{tema_elegido}"
Tipo: {tipo}

🎯 REGLA DE ORO: El guion DEBE tener entre 1000 y 1200 palabras (aproximadamente 7-8 minutos de narración). Si escribes menos, el video será demasiado corto.

🎯 ESTRUCTURA ESTRICTA DEL GUION (6 bloques, cada bloque debe tener ~150-200 palabras):
[HOOK - 0:00] (GANCHO: 5-10 palabras, impacto máximo)
[INTRO - 0:15] (Presenta el tema, el beneficio y lo que aprenderán, ~150 palabras)
[PROBLEMA - 1:00] (Expón el dolor, la oportunidad o el miedo, con datos concretos, ~200 palabras)
[DESARROLLO - 2:30] (Profundiza en el tema, da contexto, análisis, ejemplos, ~250 palabras)
[SOLUCION - 4:30] (Pasos prácticos, estrategias accionables, herramientas, ~200 palabras)
[CIERRE - 6:00] (Resumen de lo aprendido + CTA "Suscríbete, dale like, comenta", ~150 palabras)

🎯 REGLAS DE CONTENIDO:
- Tono coloquial, directo, como si hablaras con un amigo en un café.
- Incluye preguntas retóricas para mantener la atención.
- NO uses fechas específicas (evita desactualización).
- Usa ejemplos concretos y analogías para explicar conceptos complejos.

🎯 REGLAS DE SEO:
- Título (60-70 chars): [EMOJI] + [KEYWORD PRINCIPAL] + [GANCHO]
- Descripción: gancho + resumen + capítulos con timestamps + CTA + hashtags.
- Tags: 25-30 tags (alto volumen + nicho).
- Palabras clave: 5 keywords principales.

🎯 INSTRUCCIONES DE IMÁGENES ULTRAPESPECÍFICAS POR BLOQUE:
Cada bloque tendrá su propio prompt de imagen en INGLÉS para Agnes. Estilo general: cinematográfico, hiperrealista, 8k, neón cyan/magenta, high contrast, sharp focus, wide shot, no close-up face, no text, no watermark.

- [HOOK]: Persona mirando a cámara, fondo desenfocado con luces neón, expresión de sorpresa/urgencia.
- [INTRO]: Oficina moderna, pantallas con gráficos financieros, ambiente profesional, luz natural.
- [PROBLEMA]: Gráficos rojos en pantallas, trader frustrado, ambiente oscuro, luces rojas/azules.
- [DESARROLLO]: Pantallas con datos, análisis técnico, gráficos de velas, oficina de trading.
- [SOLUCION]: Persona feliz con gráficos verdes, oro, Bitcoin, ambiente de éxito, luz cálida.
- [CIERRE]: Persona sonriente, fondo corporativo, escena de éxito.

📤 RESPUESTA EN JSON (¡OBLIGATORIO!):
{{
    "titulo": "Título con emoji y keyword (60-70 chars)",
    "titulo_alternativo": "Título alternativo",
    "palabras_clave": ["kw1", "kw2", "kw3", "kw4", "kw5"],
    "descripcion": "Descripción completa con capítulos y hashtags",
    "tags": "25-30 tags separados por coma",
    "hashtags": "#hashtag1 #hashtag2 #hashtag3",
    "guion": "Texto completo del guion (1000-1200 palabras) con los 6 bloques marcados",
    "segmentos": [
        {{"bloque": "HOOK", "texto": "texto del hook (~20 palabras)", "prompt_imagen": "prompt en inglés para Agnes"}},
        {{"bloque": "INTRO", "texto": "texto del intro (~150 palabras)", "prompt_imagen": "prompt en inglés"}},
        {{"bloque": "PROBLEMA", "texto": "texto del problema (~200 palabras)", "prompt_imagen": "prompt en inglés"}},
        {{"bloque": "DESARROLLO", "texto": "texto del desarrollo (~250 palabras)", "prompt_imagen": "prompt en inglés"}},
        {{"bloque": "SOLUCION", "texto": "texto de la solución (~200 palabras)", "prompt_imagen": "prompt en inglés"}},
        {{"bloque": "CIERRE", "texto": "texto del cierre (~150 palabras)", "prompt_imagen": "prompt en inglés"}}
    ],
    "palabras_portada": "2-3 palabras para miniatura (ej. 'BITCOIN', 'SHIBA', 'ALERTA')"
}}
"""
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 3500,  # Aumentado para permitir 1200 palabras
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
            
            # Verificar palabras del guion
            guion_texto = result.get("guion", "")
            palabras = len(re.findall(r'\w+', guion_texto))
            print(f"📊 Palabras del guion: {palabras}")
            if palabras < 800:
                print(f"⚠️ Guion corto ({palabras} palabras). Reintentando...")
                continue
            
            return result, tema_elegido
        except Exception as e:
            print(f"❌ Intento {intento+1}/3 falló: {e}")
            time.sleep(10)
    print("❌ Error generando guion")
    sys.exit(1)

# ================================================================
# GENERAR IMAGEN HORIZONTAL (16:9)
# ================================================================
def generar_imagen_horizontal(prompt, intentos=3):
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
            print(f"   🖼️ Generando imagen {intento+1}/{intentos}...")
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
            time.sleep(10 * (intento + 1))
    return None

# ================================================================
# MINIATURA MEJORADA
# ================================================================
def crear_miniatura_personalizada(imagen_url, texto_portada, salida="miniatura_largo.jpg"):
    try:
        if imagen_url.startswith("http"):
            r = requests.get(imagen_url, timeout=30)
            r.raise_for_status()
            img_path = "temp_thumb.jpg"
            with open(img_path, "wb") as f:
                f.write(r.content)
        else:
            img_path = imagen_url
        
        img = Image.open(img_path)
        img = ImageOps.fit(img, (1280, 720), Image.Resampling.LANCZOS)
        draw = ImageDraw.Draw(img)
        
        texto = texto_portada.upper().strip()
        palabras = texto.split()
        if len(palabras) > 3:
            texto = ' '.join(palabras[:3])
        
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 140)
        except:
            try:
                font = ImageFont.truetype("arial.ttf", 140)
            except:
                font = ImageFont.load_default()
        
        bbox = draw.textbbox((0, 0), texto, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = (1280 - text_width) // 2
        y = 720 - text_height - 80
        
        # Rectángulo neón
        rect_margin = 30
        rect_x = x - rect_margin
        rect_y = y - rect_margin - 20
        rect_w = text_width + rect_margin * 2
        rect_h = text_height + rect_margin * 2 + 40
        
        overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        
        for i in range(0, 6):
            alpha = 150 - i * 25
            if alpha > 0:
                overlay_draw.rectangle(
                    [rect_x - i, rect_y - i, rect_x + rect_w + i, rect_y + rect_h + i],
                    outline=(0, 200, 255, alpha),
                    width=3
                )
        
        overlay_draw.rectangle(
            [rect_x, rect_y, rect_x + rect_w, rect_y + rect_h],
            fill=(0, 0, 0, 180)
        )
        
        img = Image.alpha_composite(img.convert('RGBA'), overlay).convert('RGB')
        draw = ImageDraw.Draw(img)
        
        # Sombra
        for dx, dy in [(-4, -4), (-4, 4), (4, -4), (4, 4), (0, 6), (0, -6), (6, 0), (-6, 0)]:
            draw.text((x + dx, y + dy), texto, fill='black', font=font)
        
        draw.text((x, y), texto, fill=(255, 255, 80), font=font)
        
        img.save(salida)
        print(f"✅ Miniatura mejorada creada: {salida}")
        return salida
    except Exception as e:
        print(f"⚠️ Error creando miniatura: {e}")
        return None

# ================================================================
# SUBTÍTULOS CON PIL (16:9)
# ================================================================
def agregar_subtitulos_con_pil_16_9(imagen_path, texto, salida_path):
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
        
        y_base = 720 - 120 - (len(lineas) - 1) * 60
        for i, linea in enumerate(lineas):
            bbox = draw.textbbox((0, 0), linea, font=font)
            ancho = bbox[2] - bbox[0]
            x = (1280 - ancho) // 2
            y = y_base + i * 65
            
            draw.text((x+3, y+3), linea, fill='black', font=font)
            draw.text((x+1, y+1), linea, fill='black', font=font)
            draw.text((x, y), linea, fill='white', font=font)
        
        img.save(salida_path)
        return salida_path
    except Exception as e:
        print(f"⚠️ Error subtítulos: {e}")
        return imagen_path

# ================================================================
# GENERAR AUDIO (VOZ +10%)
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
# 🔥 CAPÍTULOS VISUALES CON PIL (SIN IMAGEMAGICK)
# ================================================================
def crear_capitulo_visual_pil(titulo_capitulo, timestamp, duracion=3, ancho=1280, alto=720):
    """
    Crea un clip de video con el título del capítulo usando PIL (sin ImageMagick).
    Retorna un clip de moviepy.
    """
    try:
        # Crear imagen con PIL
        img = Image.new('RGBA', (ancho, alto), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # Texto del capítulo
        texto = f"{timestamp} - {titulo_capitulo.upper()}"
        
        # Fuente más pequeña (28px)
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
        except:
            try:
                font = ImageFont.truetype("arial.ttf", 28)
            except:
                font = ImageFont.load_default()
        
        # Calcular tamaño del texto
        bbox = draw.textbbox((0, 0), texto, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        
        # Posición: esquina superior izquierda con margen
        x = 30
        y = 30
        
        # Fondo semitransparente detrás del texto
        padding = 15
        bg_x = x - padding
        bg_y = y - padding
        bg_w = text_w + padding * 2
        bg_h = text_h + padding * 2
        
        # Dibujar fondo oscuro semitransparente
        overlay = Image.new('RGBA', (ancho, alto), (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        overlay_draw.rectangle(
            [bg_x, bg_y, bg_x + bg_w, bg_y + bg_h],
            fill=(0, 0, 0, 180)
        )
        # Borde sutil
        overlay_draw.rectangle(
            [bg_x, bg_y, bg_x + bg_w, bg_y + bg_h],
            outline=(0, 180, 255, 100),
            width=2
        )
        img = Image.alpha_composite(img, overlay)
        draw = ImageDraw.Draw(img)
        
        # Dibujar texto (blanco con sombra)
        draw.text((x+1, y+1), texto, fill='black', font=font)
        draw.text((x, y), texto, fill='white', font=font)
        
        # Guardar imagen temporal
        temp_path = f"temp_capitulo_{timestamp.replace(':', '')}.png"
        img.save(temp_path)
        
        # Crear clip de moviepy
        clip = ImageClip(temp_path, duration=duracion, transparent=True)
        clip = clip.crossfadein(0.3).crossfadeout(0.3)
        
        return clip
    except Exception as e:
        print(f"⚠️ Error creando capítulo visual con PIL: {e}")
        return None

# ================================================================
# 🔥 CTA FINAL "SUSCRÍBETE" CON PIL (SIN IMAGEMAGICK)
# ================================================================
def crear_cta_final_pil(duracion=3, ancho=1280, alto=720):
    """
    Crea un clip final con texto "🔴 SUSCRÍBETE" usando PIL.
    """
    try:
        img = Image.new('RGB', (ancho, alto), (15, 15, 20))
        draw = ImageDraw.Draw(img)
        
        texto = "🔴 SUSCRÍBETE"
        
        # Fuente más pequeña (80px)
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 80)
        except:
            try:
                font = ImageFont.truetype("arial.ttf", 80)
            except:
                font = ImageFont.load_default()
        
        bbox = draw.textbbox((0, 0), texto, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        x = (ancho - text_w) // 2
        y = (alto - text_h) // 2
        
        # Sombra
        for dx, dy in [(-3, -3), (-3, 3), (3, -3), (3, 3)]:
            draw.text((x + dx, y + dy), texto, fill='black', font=font)
        
        # Texto rojo con borde blanco
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
# MONTAR VIDEO (con PIL para capítulos y CTA)
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
                r = requests.get(img_url, timeout=30)
                r.raise_for_status()
                img_path = f"temp_largo_{i}.jpg"
                with open(img_path, "wb") as f:
                    f.write(r.content)
            else:
                img_path = img_url
            
            img_sub_path = f"temp_largo_sub_{i}.jpg"
            img_path = agregar_subtitulos_con_pil_16_9(img_path, texto, img_sub_path)
            
            img = Image.open(img_path)
            img = ImageOps.fit(img, (1280, 720), Image.Resampling.LANCZOS)
            img.save(img_path)
            
            # Ken Burns (Zoom lento)
            video_clip = (ImageClip(img_path)
                         .resize(lambda t: 1 + 0.015 * t)
                         .set_duration(duracion))
        except Exception as e:
            print(f"⚠️ Falló imagen {i}: {e}")
            video_clip = ImageClip(np.zeros((720, 1280, 3), dtype=np.uint8) + 20, duration=duracion).set_fps(24)
        
        # 🔥 Capítulo visual (usando PIL)
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
    
    # Concatenar audio con pausas
    PAUSA = 0.3
    audio_final_parts = []
    for i, aud in enumerate(clips_audio):
        audio_final_parts.append(aud)
        if i < len(clips_audio) - 1:
            audio_final_parts.append(AudioClip(lambda t: 0, duration=PAUSA))
    
    audio_narracion = concatenate_audioclips(audio_final_parts)
    duracion_total = audio_narracion.duration
    
    # Concatenar videos con fade
    video = concatenate_videoclips(clips_video, method="compose")
    video = video.set_duration(duracion_total)
    
    # 🔥 CTA final "SUSCRÍBETE" con PIL
    cta_clip = crear_cta_final_pil(duracion=3)
    if cta_clip:
        video = concatenate_videoclips([video, cta_clip], method="compose")
        duracion_total += 3
    
    # Música de fondo
    if fondo_path and os.path.exists(fondo_path):
        try:
            fondo_clip = AudioFileClip(fondo_path)
            if fondo_clip.duration < duracion_total:
                veces = int(duracion_total / fondo_clip.duration) + 1
                fondo_clip = concatenate_audioclips([fondo_clip] * veces)
            fondo_clip = fondo_clip.subclip(0, duracion_total).volumex(0.05)
            audio_final = CompositeAudioClip([audio_narracion, fondo_clip])
            print("🎵 Música de fondo agregada")
        except Exception as e:
            print(f"⚠️ Error con música: {e}")
            audio_final = audio_narracion
    else:
        print("ℹ️ Sin música de fondo")
        audio_final = audio_narracion
    
    video = video.set_audio(audio_final)
    video.write_videofile(salida, fps=24, codec="libx264", audio_codec="aac", threads=4, preset="ultrafast")
    return salida

# ================================================================
# SUBIR A YOUTUBE (CON DISCLAIMER)
# ================================================================
def subir_a_youtube(video_path, titulo, etiquetas, descripcion, miniatura_path=None):
    try:
        creds = Credentials.from_authorized_user_info(YOUTUBE_USER_TOKEN)
        youtube = build("youtube", "v3", credentials=creds)
    except Exception as e:
        print(f"❌ Error autenticando: {e}")
        sys.exit(1)
    
    if isinstance(etiquetas, str):
        etiquetas = [t.strip() for t in etiquetas.split(",") if t.strip()]
    
    # 🔥 AÑADIR DISCLAIMER A LA DESCRIPCIÓN
    disclaimer = "\n\n⚠️ AVISO IMPORTANTE: Este contenido es solo para fines educativos no constituye asesoría financiera, legal o de inversión."
    descripcion_final = descripcion + disclaimer
    
    body = {
        "snippet": {
            "title": titulo[:100],
            "description": descripcion_final[:5000],
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
    print(f"✅ Video largo subido: https://youtu.be/{video_id}")
    
    if miniatura_path and os.path.exists(miniatura_path):
        try:
            media_thumb = MediaFileUpload(miniatura_path, chunksize=-1, resumable=True)
            youtube.thumbnails().set(videoId=video_id, media_body=media_thumb).execute()
            print("✅ Miniatura personalizada subida")
        except Exception as e:
            print(f"⚠️ Error subiendo miniatura: {e}")
    
    return video_id

# ================================================================
# LIMPIEZA DE ARCHIVOS TEMPORALES
# ================================================================
def limpiar_archivos_temporales():
    import glob
    patrones = [
        "temp_*.jpg", "temp_*.mp3", "audio_largo_*.mp3",
        "temp_thumb.jpg", "miniatura_largo.jpg", "largo_capital.mp4",
        "placeholder*.jpg", "temp_*.png"
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
    print("🎬 Capital Digital - Bot de VIDEOS LARGOS (CORREGIDO)")
    print("   ✓ Música: The Ascent, Binary Pulse, Peak Momentum, Forward Momentum")
    print("   ✓ Ken Burns (Zoom)")
    print("   ✓ Transiciones Fade")
    print("   ✓ Miniatura neón")
    print("   ✓ Capítulos visuales con PIL (sin ImageMagick)")
    print("   ✓ CTA con PIL (sin ImageMagick)")
    print("   ✓ Disclaimer en descripción")
    print("   ✓ Guion forzado a 1000-1200 palabras")
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
    
    guion, tema = generar_guion_largo(tipo)
    titulo = guion["titulo"]
    descripcion = guion["descripcion"]
    tags = guion["tags"]
    segmentos = guion["segmentos"]
    palabras_portada = guion.get("palabras_portada", "RÉCORD")
    
    capitulos = []
    for seg in segmentos:
        capitulos.append({"bloque": seg.get("bloque", "CAPÍTULO")})
    
    recursos = []
    for idx, seg in enumerate(segmentos):
        print(f"🎬 Segmento {idx+1}/{len(segmentos)} - {seg.get('bloque', '')}")
        prompt_img = seg["prompt_imagen"]
        img_url = generar_imagen_horizontal(prompt_img)
        if not img_url:
            img_url = "https://via.placeholder.com/1280x720/1a1a3a/4a8af4?text=Capital+Digital"
        
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
        time.sleep(10)
    
    if not recursos:
        print("❌ No se generaron recursos.")
        sys.exit(1)
    
    video_path = montar_video_largo(recursos, fondo_path, "largo_capital.mp4", capitulos)
    print(f"🎬 Video montado: {video_path}")
    
    miniatura_path = None
    if recursos and recursos[0].get("imagen_url"):
        miniatura_path = crear_miniatura_personalizada(
            recursos[0]["imagen_url"],
            palabras_portada,
            "miniatura_largo.jpg"
        )
    
    video_id = subir_a_youtube(video_path, titulo, tags, descripcion, miniatura_path)
    
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
