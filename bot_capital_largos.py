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
# VOZ FIJA (Jorge) - +5% para largos
# ================================================================
VOZ_FIJA = {"voz": "es-MX-JorgeNeural", "velocidad": "+5%", "tono": "-1Hz", "nombre": "Jorge (MX)"}
CONFIG_VOZ_ACTUAL = VOZ_FIJA

# ================================================================
# PALETAS Y ESTILOS VISUALES (16:9)
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
    "hot pink neon reflection", "neon orange highlight"
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
# GENERAR GUION LARGO
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

    prompt = f"""
Eres un CREADOR DE CONTENIDO FINANCIERO EXPERTO para YouTube. Debes escribir un guion para un video de 7-8 minutos.
Tema: "{tema_elegido}"
Tipo: {tipo}

🎯 ESTRUCTURA ESTRICTA DEL GUION (usa timestamps):
[HOOK - 0:00] (5-10 palabras, impacto)
[INTRO - 0:15] (Presenta el tema y el beneficio)
[PROBLEMA - 1:00] (Expón el dolor/oportunidad con datos)
[DESARROLLO - 2:30] (Profundiza, da contexto, análisis)
[SOLUCION - 4:30] (Pasos prácticos, estrategias accionables)
[CIERRE - 6:00] (Resumen + CTA "Suscríbete, dale like")

🎯 REGLAS:
- Total: 1000-1200 palabras.
- Tono coloquial, directo, como si hablaras con un amigo.
- Incluye preguntas retóricas.
- NO uses fechas específicas (evita que se desactualice rápido).
- Al final del guion, asegúrate de que las secciones estén claras.

🎯 SEO:
- Título (60-70 chars): [Emoji] + [Keyword] + [Gancho]
- Descripción: Gancho, resumen, capítulos, CTA.
- Keywords: 5 keywords principales.
- Tags: 25-30 tags separados por coma.

🚫 TÍTULOS YA PUBLICADOS (NO REPETIR):
{titulos_referencia}

RESPONDE EN JSON:
{{
    "titulo": "Título",
    "titulo_alternativo": "Título alternativo",
    "palabras_clave": ["kw1", "kw2", "kw3", "kw4", "kw5"],
    "descripcion": "Descripción completa con capítulos",
    "tags": "tag1, tag2, tag3...",
    "hashtags": "#hashtag1 #hashtag2",
    "guion": "Texto completo con timestamps",
    "segmentos": [
        {{"texto": "Parte 1 (45-50 palabras)", "prompt_imagen": "Prompt en inglés para Agnes"}},
        ...
    ]
}}
"""
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 2500,
        "response_format": {"type": "json_object"}
    }
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
        print(f"❌ Error generando guion: {e}")
        sys.exit(1)

# ================================================================
# GENERAR IMAGEN HORIZONTAL (16:9)
# ================================================================
def generar_imagen_horizontal(prompt, intentos=3):
    prompt = re.sub(r"\n+", " ", prompt).strip()
    prompt = re.sub(r'"', "'", prompt)
    prompt = prompt[:950]
    
    url = "https://apihub.agnes-ai.com/v1/images/generations"
    headers = {"Authorization": f"Bearer {AGNES_API_KEY}", "Content-Type": "application/json"}
    negative = "multiple people, crowd, close-up face, portrait, headshot, gore, blood, clones, deformed, blurry, text, watermark"
    payload = {
        "model": "agnes-image-2.1-flash",
        "prompt": prompt,
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
# SUBTÍTULOS CON PIL (16:9)
# ================================================================
def agregar_subtitulos_con_pil_16_9(imagen_path, texto, salida_path):
    try:
        img = Image.open(imagen_path)
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 40)
        except:
            font = ImageFont.load_default()
        
        palabras = texto.split()
        if len(palabras) > 20:
            texto_sub = ' '.join(palabras[:20])
        else:
            texto_sub = texto
        
        bbox = draw.textbbox((0, 0), texto_sub, font=font)
        ancho = bbox[2] - bbox[0]
        x = (1280 - ancho) // 2
        y = 720 - 100
        
        draw.text((x+2, y+2), texto_sub, fill='black', font=font)
        draw.text((x, y), texto_sub, fill='white', font=font)
        
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
# MONTAR VIDEO
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
# SUBIR A YOUTUBE
# ================================================================
def subir_a_youtube(video_path, titulo, etiquetas, descripcion):
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
    return video_id

# ================================================================
# MAIN
# ================================================================
def main():
    print("="*60)
    print("🎬 Capital Digital - Bot de VIDEOS LARGOS (7+ min)")
    print("   ✓ Formato 16:9 Horizontal")
    print("   ✓ Guion de 1000-1200 palabras")
    print("   ✓ Voz Jorge +5%")
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
    
    video_id = subir_a_youtube(video_path, titulo, tags, descripcion)
    
    guardar_titulo_publicado(titulo)
    guardar_tema_publicado(tema, tipo)
    incrementar_publicaciones_hoy()
    guardar_estado(estado)
    
    print(f"✅ Publicado: https://youtu.be/{video_id}")

if __name__ == "__main__":
    main()
