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
    TextClip,
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
CANAL_LINK = "https://www.youtube.com/@CapitalDigitalInversiones"
ESTADO_FILE = "estado_capital_largos.json"
TITULOS_FILE = "titulos_capital_largos_publicados.json"
TEMAS_PUBLICADOS_FILE = "temas_largos_publicados.json"
META_DIARIA_LARGOS = 1
DIAS_SIN_REPETIR_TEMA = 45

# ================================================================
# VOZ FIJA (Jorge) - ¡VELOCIDAD +10% como en Shorts!
# ================================================================
VOZ_FIJA = {"voz": "es-MX-JorgeNeural", "velocidad": "+10%", "tono": "-1Hz", "nombre": "Jorge (MX)"}
CONFIG_VOZ_ACTUAL = VOZ_FIJA

# ================================================================
# PALETAS Y ESTILOS VISUALES (neón + alto contraste)
# ================================================================
PALETAS_BASE = [
    "Corporate blue and silver, modern office",
    "Dark emerald and gold, financial district",
    "Slate gray and cyan, trading floor",
    "Deep navy and amber, executive office",
    "Black and gold, Wall Street style",
]
PALETA_BASE_ACTUAL = random.choice(PALETAS_BASE)

COLORES_NEON = [
    "electric cyan neon glow", "neon magenta pulse", "vivid lime green neon",
    "hot pink neon reflection", "neon orange highlight", "electric purple neon aura"
]
COLOR_NEON_ACTUAL = random.choice(COLORES_NEON)

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
# GENERAR GUION LARGO (con instrucciones de SEO y diseño visual mejorado)
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
    tema_elegido = random.choice(temas_disponibles) if temas_disponibles else random.choice(temas_pool)
    print(f"📌 Tema seleccionado: {tema_elegido}")

    # 🔥 PROMPT MEJORADO CON INSTRUCCIONES PARA IMÁGENES NEÓN Y MINIATURA
    prompt = f"""
Eres un CREADOR DE CONTENIDO FINANCIERO EXPERTO para YouTube y un DIRECTOR DE CINE. Debes escribir un guion para un video de 7-8 minutos.
Tema: "{tema_elegido}"
Tipo: {tipo}

🎯 ESTRUCTURA ESTRICTA DEL GUION (usa timestamps):
[HOOK - 0:00] (5-10 palabras, impacto)
[INTRO - 0:15] (Presenta el tema y el beneficio)
[PROBLEMA - 1:00] (Expón el dolor/oportunidad con datos)
[DESARROLLO - 2:30] (Profundiza, da contexto, análisis)
[SOLUCION - 4:30] (Pasos prácticos, estrategias accionables)
[CIERRE - 6:00] (Resumen + CTA "Suscríbete, dale like")

🎯 REGLAS DE CONTENIDO:
- Total: 1000-1200 palabras.
- Tono coloquial, directo, con preguntas retóricas.
- NO uses fechas específicas (evita desactualización).

🎯 REGLAS DE SEO PARA MAXIMIZAR CTR:
- Título (60-70 chars): **DEBE incluir un EMOJI + PALABRA CLAVE + GANCHO**.
  Ej: "🔥 SHIBA INU: ¿Aún estás a tiempo de comprar?"
- Descripción: Gancho, resumen, capítulos, CTA, hashtags.
- Tags: 25-30 tags (alto volumen + nicho).
- Palabras clave: 5 keywords principales.

🎯 INSTRUCCIONES PARA LAS IMÁGENES (CADA SEGMENTO):
Para cada segmento, genera un prompt en INGLÉS para Agnes que incluya:
- Estilo: cinematográfico, hiperrealista, 8k.
- Colores: neón (cyan, magenta, naranja, verde lima) combinados con fondos oscuros o corporativos.
- Composición: gran angular o plano medio, NUNCA primer plano de rostros.
- Ambiente: oficinas modernas, pantallas de trading, gráficos financieros, edificios, personas en segundo plano (pequeñas).
- Acentos de luz: "electric neon glow", "dramatic lighting", "high contrast".
- Época: actual o ligeramente futurista (2026).
- Prohibido: texto, marcas de agua, gore, clones.

🎯 INSTRUCCIÓN PARA LA MINIATURA (se generará al final):
Crea una miniatura de alto CTR: texto grande, colores neón sobre fondo oscuro, imagen de impacto (ej. Bitcoin, gráfico, persona emocionada).

📤 RESPUESTA EN JSON:
{{
    "titulo": "Título con emoji y keyword",
    "titulo_alternativo": "Título alternativo",
    "palabras_clave": ["kw1", "kw2", "kw3", "kw4", "kw5"],
    "descripcion": "Descripción completa (incluye capítulos y hashtags)",
    "tags": "tag1, tag2, tag3...",
    "hashtags": "#hashtag1 #hashtag2",
    "guion": "Texto completo con timestamps",
    "segmentos": [
        {{"texto": "Parte 1 (45-50 palabras)", "prompt_imagen": "Prompt en inglés para Agnes"}},
        ...
    ],
    "palabras_portada": "2-3 palabras para la miniatura (ej. 'BITCOIN', 'SHIBA', 'ALERTA')"
}}
"""
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 2800,
        "response_format": {"type": "json_object"}
    }
    for intento in range(3):
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=120)
            r.raise_for_status()
            data = r.json()
            content = data["choices"][0]["message"]["content"]
            inicio = content.find("{")
            fin = content.rfind("}")
            json_str = content[inicio:fin+1]
            result = json.loads(json_str)
            return result, tema_elegido
        except Exception as e:
            print(f"❌ Intento {intento+1}/3 falló: {e}")
            time.sleep(10)
    print("❌ Error generando guion")
    sys.exit(1)

# ================================================================
# GENERAR IMAGEN HORIZONTAL (16:9) CON ESTILO NEÓN
# ================================================================
def generar_imagen_horizontal(prompt, intentos=3):
    # Añadir instrucciones de estilo al prompt
    prompt_completo = f"{prompt}, hyperrealistic, 8k, cinematic lighting, {COLOR_NEON_ACTUAL}, high contrast, sharp focus, wide shot, environment as main subject, no close-up face, no text, no watermark"
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
            print(f"   🖼️ Generando imagen horizontal {intento+1}/{intentos}...")
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
# GENERAR MINIATURA PERSONALIZADA (alto CTR)
# ================================================================
def crear_miniatura_personalizada(imagen_url, texto_portada, salida="miniatura_largo.jpg"):
    try:
        # Descargar imagen de referencia (puede ser una de las imágenes del video)
        if imagen_url.startswith("http"):
            r = requests.get(imagen_url, timeout=30)
            r.raise_for_status()
            img_path = "temp_thumb.jpg"
            with open(img_path, "wb") as f:
                f.write(r.content)
        else:
            img_path = imagen_url
        
        # Redimensionar a 1280x720 (16:9)
        img = Image.open(img_path)
        img = ImageOps.fit(img, (1280, 720), Image.Resampling.LANCZOS)
        draw = ImageDraw.Draw(img)
        
        # Cargar fuente grande
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 140)
        except:
            try:
                font = ImageFont.truetype("arial.ttf", 140)
            except:
                font = ImageFont.load_default()
        
        texto = texto_portada.upper().strip()
        # Limitar a 3 palabras
        palabras = texto.split()
        if len(palabras) > 3:
            texto = ' '.join(palabras[:3])
        
        # Calcular posición centrada (ligeramente abajo)
        bbox = draw.textbbox((0, 0), texto, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = (1280 - text_width) // 2
        y = 720 - text_height - 80
        
        # Sombra para legibilidad (negra, gruesa)
        sombra_offset = 6
        draw.text((x + sombra_offset, y + sombra_offset), texto, fill='black', font=font)
        # Texto principal en color neón o blanco
        draw.text((x, y), texto, fill='white', font=font)
        
        # Añadir un rectángulo semitransparente detrás del texto para mejor contraste
        # (opcional, pero ayuda)
        overlay = Image.new('RGBA', (text_width + 40, text_height + 40), (0, 0, 0, 128))
        overlay_draw = ImageDraw.Draw(overlay)
        overlay_draw.rectangle([(0, 0), (text_width + 40, text_height + 40)], fill=(0, 0, 0, 128))
        img.paste(overlay, (x - 20, y - 20), overlay)
        # Volver a dibujar el texto encima
        draw.text((x, y), texto, fill='white', font=font)
        
        img.save(salida)
        print(f"✅ Miniatura personalizada creada: {salida}")
        return salida
    except Exception as e:
        print(f"⚠️ Error creando miniatura: {e}")
        return None

# ================================================================
# SUBTÍTULOS CON PIL (16:9) - MEJORADOS
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
        
        # Limitar texto a 20 palabras
        palabras = texto.split()
        if len(palabras) > 20:
            texto_sub = ' '.join(palabras[:20])
        else:
            texto_sub = texto
        
        # Dividir en 2 líneas si es largo
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
        
        # Calcular posición (centrado abajo)
        y_base = 720 - 120 - (len(lineas) - 1) * 60
        for i, linea in enumerate(lineas):
            bbox = draw.textbbox((0, 0), linea, font=font)
            ancho = bbox[2] - bbox[0]
            x = (1280 - ancho) // 2
            y = y_base + i * 65
            
            # Fondo semitransparente para legibilidad (opcional)
            # En lugar de fondo, usamos sombra gruesa
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
# MONTAR VIDEO (incluye CTA visual final)
# ================================================================
def montar_video_largo(recursos, fondo_path, salida="largo_capital.mp4"):
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
            video_clip = ImageClip(img_path).set_duration(duracion)
        except Exception as e:
            print(f"⚠️ Falló imagen {i}: {e}")
            img_path = "placeholder.jpg"
            img = Image.new("RGB", (1280, 720), (20, 20, 50))
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
    PAUSA = 0.2
    audio_final_parts = []
    for i, aud in enumerate(clips_audio):
        audio_final_parts.append(aud)
        if i < len(clips_audio) - 1:
            audio_final_parts.append(AudioClip(lambda t: 0, duration=PAUSA))
    
    audio_narracion = concatenate_audioclips(audio_final_parts)
    duracion_total = audio_narracion.duration
    
    video = concatenate_videoclips(clips_video, method="compose")
    video = video.set_duration(duracion_total)
    
    # Agregar CTA visual final (SUSCRÍBETE)
    try:
        # Crear un clip de texto de 3 segundos al final
        cta_text = TextClip(
            "🔴 SUSCRÍBETE",
            fontsize=100,
            color='red',
            font='Arial-Bold',
            stroke_color='white',
            stroke_width=4,
            method='caption',
            size=(1280, None)
        ).set_position('center').set_duration(3)
        
        # Fondo oscuro para el CTA
        cta_fondo = ImageClip(np.zeros((720, 1280, 3), dtype=np.uint8) + 20, duration=3).set_fps(24)
        cta_fondo = cta_fondo.set_audio(AudioClip(lambda t: 0, duration=3))  # Silencio
        cta_final = CompositeVideoClip([cta_fondo, cta_text])
        
        # Añadir al final del video
        video = concatenate_videoclips([video, cta_final], method="compose")
        duracion_total += 3
    except Exception as e:
        print(f"⚠️ No se pudo agregar CTA visual: {e}")
    
    # Fondo musical
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
# SUBIR A YOUTUBE (CON MINIATURA PERSONALIZADA)
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
    print(f"✅ Video largo subido: https://youtu.be/{video_id}")
    
    # Subir miniatura personalizada
    if miniatura_path and os.path.exists(miniatura_path):
        try:
            media_thumb = MediaFileUpload(miniatura_path, chunksize=-1, resumable=True)
            youtube.thumbnails().set(videoId=video_id, media_body=media_thumb).execute()
            print("✅ Miniatura personalizada subida exitosamente")
        except Exception as e:
            print(f"⚠️ Error subiendo miniatura: {e}")
    
    return video_id

# ================================================================
# MAIN
# ================================================================
def main():
    print("="*60)
    print("🎬 Capital Digital - Bot de VIDEOS LARGOS (MEJORADO)")
    print("   ✓ Formato 16:9 Horizontal")
    print("   ✓ Velocidad voz +10% (como Shorts)")
    print("   ✓ Imágenes con neón y alto contraste")
    print("   ✓ Miniatura personalizada de alto CTR")
    print("   ✓ Subtítulos grandes y legibles")
    print("   ✓ CTA visual final")
    print("="*60)
    
    if not YOUTUBE_USER_TOKEN:
        print("❌ Falta YOUTUBE_USER_TOKEN_CAPITAL")
        sys.exit(1)
    
    publicadas = obtener_publicaciones_hoy()
    if publicadas >= META_DIARIA_LARGOS:
        print("✅ Ya se publicó el video largo hoy. Saliendo.")
        sys.exit(0)
    
    tipos = ["educativo", "estafa", "psicologia", "analisis"]
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
    
    recursos = []
    for idx, seg in enumerate(segmentos):
        print(f"🎬 Segmento {idx+1}/{len(segmentos)}")
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
            "texto": seg["texto"]
        })
        time.sleep(10)
    
    if not recursos:
        print("❌ No se generaron recursos.")
        sys.exit(1)
    
    video_path = montar_video_largo(recursos, fondo_path, "largo_capital.mp4")
    print(f"🎬 Video montado: {video_path}")
    
    # Crear miniatura personalizada usando la primera imagen del video
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
    
    print(f"✅ Publicado: https://youtu.be/{video_id}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ Error fatal: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
