import streamlit as st
from groq import Groq
import subprocess
import os
import shutil
import asyncio
from pythainlp.tokenize import word_tokenize
from PIL import ImageFont
import requests
import random
import time
import re
import urllib.request
import tarfile

# =========================================================
# ⚙️ ส่วนตั้งค่าเริ่มต้น & ฟังก์ชันช่วยเหลือ (Helper Functions)
# =========================================================
FONT_MAP = {
    "Kanit": "Kanit-Regular.ttf", "Kanit Medium": "Kanit-Medium.ttf", "Kanit Bold": "Kanit-Bold.ttf",
    "Noto Sans Thai": "NotoSansThai-Regular.ttf", "Noto Sans Thai Medium": "NotoSansThai-Medium.ttf",
    "Noto Sans Thai Bold": "NotoSansThai-Bold.ttf", "Sarabun": "Sarabun.ttf", "Chonburi": "Chonburi.ttf", "Mali": "Mali.ttf"
}

def hex_to_ass_color(hex_str, alpha_hex="00"):
    hex_str = hex_str.lstrip('#')
    return f"&H{alpha_hex}{hex_str[4:6]}{hex_str[2:4]}{hex_str[0:2]}"

def format_ass_timestamp(seconds):
    hours, minutes, secs = int(seconds // 3600), int((seconds % 3600) // 60), int(seconds % 60)
    centis = int(round((seconds - int(seconds)) * 100))
    if centis == 100: secs += 1; centis = 0
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"

def split_text_by_pixel_width(text, font_file, pil_font_size, max_width_pixels):
    try: font = ImageFont.truetype(font_file, pil_font_size)
    except Exception: return text
    words = word_tokenize(text, engine='newmm')
    lines, current_line = [], ""
    for word in words:
        test_line = current_line + word
        line_width = font.getlength(test_line) if hasattr(font, 'getlength') else (font.getbbox(test_line)[2] - font.getbbox(test_line)[0] if font.getbbox(test_line) else 0)
        if line_width > max_width_pixels and current_line:
            lines.append(current_line); current_line = word
        else: current_line = test_line
    if current_line: lines.append(current_line)
    return "\n".join(lines)

def get_action_keyword_from_ai(client, thai_text):
    try:
        prompt = f"Read this Thai scene description: '{thai_text}'. Create a 2 to 4 word English search query for Pexels Stock Video (literal, simple action phrases). Output ONLY the search query."
        res = client.chat.completions.create(messages=[{"role": "user", "content": prompt}], model="llama3-8b-8192", temperature=0.2)
        time.sleep(2.5) 
        return res.choices[0].message.content.strip().replace('"', '')
    except Exception:
        time.sleep(2.5)
        return random.choice(["cinematic landscape", "people walking", "vintage object"])

def fetch_pexels_video(keyword, pexels_key, output_path):
    headers = {"Authorization": pexels_key}
    url = f"https://api.pexels.com/videos/search?query={keyword}&orientation=portrait&per_page=15"
    try:
        res = requests.get(url, headers=headers, timeout=10).json()
        if res.get("videos"):
            videos = res["videos"]; random.shuffle(videos)
            for v in videos:
                for f in v.get("video_files", []):
                    if f.get("file_type") == "video/mp4" and f.get("width") and f.get("width") >= 720:
                        v_res = requests.get(f.get("link"), timeout=15)
                        with open(output_path, "wb") as f_out: f_out.write(v_res.content)
                        return True
    except Exception: pass
    return False

# =========================================================
# 🔒 ระบบความปลอดภัย (Gatekeeper)
# =========================================================
st.set_page_config(page_title="AI Studio Pro", page_icon="🎬", layout="wide")
if "authenticated" not in st.session_state: st.session_state["authenticated"] = False
if not st.session_state["authenticated"]:
    st.markdown("## 🔐 ระบบภายในส่วนตัว (Restricted Access)")
    user_password = st.text_input("🔑 รหัสผ่าน:", type="password")
    if st.button("🔓 เข้าสู่ระบบ"):
        if user_password == st.secrets.get("APP_PASSWORD", "12345"):
            st.session_state["authenticated"] = True; st.rerun()
        else: st.error("❌ รหัสผ่านไม่ถูกต้อง!")
    st.stop()

if "GROQ_API_KEY" in st.secrets: api_key = st.secrets["GROQ_API_KEY"]
else: st.error("❌ ยังไม่ได้ตั้งค่า Groq API Key"); st.stop()
pexels_key = st.secrets.get("PEXELS_API_KEY", "")

# =========================================================
# 🎛️ เมนูสลับโหมดการทำงาน & ระบบอัปเกรดเอนจินสระ
# =========================================================
st.sidebar.markdown("## 🛠️ เลือกโหมดการทำงาน")
app_mode = st.sidebar.radio("สตูดิโอของคุณ:", [
    "🎭 โหมด 1: สร้างคลิปไร้หน้า (Faceless)", 
    "🎞️ โหมด 2: ต่อคลิปและฝังซับ (Join & Sub)"
])

# 🚀 โค้ดใหม่: ดึงเอนจินรุ่นที่มี HarfBuzz 100%
st.sidebar.markdown("---")
st.sidebar.markdown("### 🇹🇭 เครื่องมือแก้สระลอย (อัปเกรด)")
if os.path.exists("./ffmpeg") and os.path.exists("./ffprobe"):
    st.sidebar.success("✅ มีเอนจินติดตั้งอยู่แล้ว")
else:
    st.sidebar.warning("⚠️ ยังไม่มีเอนจิน โปรดติดตั้ง")

if st.sidebar.button("🔄 ติดตั้ง / อัปเกรดเอนจิน (ซ่อมสระลอย)"):
    with st.spinner("กำลังดาวน์โหลด FFmpeg รุ่น Full-Engine (ประมาณ 40MB)..."):
        try:
            # ลบตัวเก่าทิ้งก่อน (ถ้ามี)
            if os.path.exists("./ffmpeg"): os.remove("./ffmpeg")
            if os.path.exists("./ffprobe"): os.remove("./ffprobe")
            
            # โหลดเวอร์ชัน Full จาก yt-dlp builds ที่รองรับภาษาไทย
            url = "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz"
            urllib.request.urlretrieve(url, "ffmpeg.tar.xz")
            with tarfile.open("ffmpeg.tar.xz", "r:xz") as tar:
                tar.extractall()
            
            # เข้าไปหาไฟล์ในโฟลเดอร์ bin
            extracted = [f for f in os.listdir() if "ffmpeg-master" in f and os.path.isdir(f)][0]
            shutil.copy(os.path.join(extracted, "bin", "ffmpeg"), "./ffmpeg")
            shutil.copy(os.path.join(extracted, "bin", "ffprobe"), "./ffprobe")
            os.chmod("./ffmpeg", 0o755)
            os.chmod("./ffprobe", 0o755)
            
            os.remove("ffmpeg.tar.xz")
            shutil.rmtree(extracted)
            
            st.sidebar.success("✅ อัปเกรดเสร็จสมบูรณ์! สระไทยพร้อมใช้งาน")
            time.sleep(2)
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"❌ เกิดข้อผิดพลาด: {e}")

FFMPEG_CMD = "./ffmpeg" if os.path.exists("./ffmpeg") else "ffmpeg"
FFPROBE_CMD = "./ffprobe" if os.path.exists("./ffprobe") else "ffprobe"

def get_video_dimensions(video_path):
    try:
        cmd = [FFPROBE_CMD, '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height', '-of', 'csv=s=x:p=0', video_path]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        width_str, height_str = result.stdout.strip().split('x')
        return int(width_str), int(height_str)
    except Exception: return 720, 1280

client = Groq(api_key=api_key)

def render_subtitle_ui(key_prefix):
    st.markdown("### 🛠️ ปรับแต่งสไตล์ซับไตเติล")
    with st.expander("เปิดเครื่องมือปรับแต่ง (ฟอนต์, สี, เอฟเฟกต์, แก้คำผิด)", expanded=True):
        st.markdown("#### 📝 แก้ไขคำทับศัพท์ / เปลี่ยนคำผิด")
        replace_words_input = st.text_input("รูปแบบ (คำเดิม=คำใหม่) คั่นด้วยลูกน้ำ:", value="Save=เซฟ, OK=โอเค, AI=เอไอ, Content=คอนเทนต์", key=f"{key_prefix}_replace")
        st.markdown("---")
        font_choice = st.selectbox("✒️ ฟอนต์:", list(FONT_MAP.keys()), index=8, key=f"{key_prefix}_font")
        c1, c2, c3 = st.columns(3)
        with c1: text_color = st.color_picker("🅰️ สีตัวอักษร", "#FFFFFF", key=f"{key_prefix}_tc")
        with c2: outline_color = st.color_picker("🖍️ สีขอบ", "#000000", key=f"{key_prefix}_oc")
        with c3: bg_style = st.selectbox("🔲 พื้นหลัง", ["ขอบปกติ", "แถบกล่องดำรองหลัง"], key=f"{key_prefix}_bg")
        anim_choice = st.selectbox("🎬 เอฟเฟกต์:", ["ไม่มี", "เด้งพอง (Pop-up)", "ค่อยๆ ปรากฏ (Fade-in)"], index=1, key=f"{key_prefix}_anim")
        pop_scale, pop_duration, fade_duration = 130, 150, 200
        if anim_choice == "เด้งพอง (Pop-up)":
            ca1, ca2 = st.columns(2)
            with ca1: pop_scale = st.slider("ความขยายตอนเด้ง (%)", 110, 180, 130, 5, key=f"{key_prefix}_ps")
            with ca2: pop_duration = st.slider("ความเร็วยุบตัว (ms)", 50, 400, 150, 10, key=f"{key_prefix}_pd")
        elif anim_choice == "ค่อยๆ ปรากฏ (Fade-in)":
            fade_duration = st.slider("ความเร็ว Fade (ms)", 100, 1000, 200, 50, key=f"{key_prefix}_fd")
        cl1, cl2 = st.columns(2)
        with cl1:
            font_size_choice = st.slider("ขนาดตัวอักษร:", 14, 40, 18, key=f"{key_prefix}_fs")
            outline_thickness = st.slider("ความหนาขอบ:", 0, 5, 1, key=f"{key_prefix}_ot")
        with cl2:
            max_width_pct = st.slider("ความกว้างกรอบข้อความ (%):", 50, 150, 100, key=f"{key_prefix}_mw")
            margin_v_choice = st.slider("ความสูงจากขอบล่าง:", 20, 200, 50, key=f"{key_prefix}_mv")
        force_max_2_lines = st.checkbox("🚫 บังคับซับไม่เกิน 2 บรรทัด", value=True, key=f"{key_prefix}_f2l")
        
        replace_dict = {}
        if replace_words_input.strip():
            pairs = replace_words_input.split(',')
            for pair in pairs:
                if '=' in pair:
                    old_w, new_w = pair.split('=', 1)
                    replace_dict[old_w.strip()] = new_w.strip()
        
        return {
            "font": font_choice, "t_color": text_color, "o_color": outline_color, 
            "bg_style": bg_style, "anim": anim_choice, "pop_scale": pop_scale, 
            "pop_dur": pop_duration, "fade_dur": fade_duration, "size": font_size_choice, 
            "outline": outline_thickness, "max_w": max_width_pct, "margin_v": margin_v_choice,
            "force_2_lines": force_max_2_lines, "replacements": replace_dict
        }

# =========================================================
# 🎭 โหมด 1: สร้างคลิปไร้หน้า (Faceless / Storyboard)
# =========================================================
if app_mode == "🎭 โหมด 1: สร้างคลิปไร้หน้า (Faceless)":
    st.markdown("## 🎭 โหมดสร้างคลิปไร้หน้า (Storyboard Automation)")
    faceless_mode = st.radio("เลือกวิธีสร้างวิดีโอพื้นหลัง:", ["ไม่ใช้ (ใช้วิดีโอต้นฉบับ)", "🤖 Pexels AI (ดึงภาพอัตโนมัติ)", "📂 Custom B-Roll (อัปโหลดมาเรียงเอง)"], index=0)
    scene_target_duration, custom_videos = 8.0, []
    if faceless_mode != "ไม่ใช้ (ใช้วิดีโอต้นฉบับ)":
        scene_target_duration = st.slider("⏱️ ความยาวแต่ละฉาก (วินาที)", 4.0, 15.0, 8.0, 1.0)
        if faceless_mode == "📂 Custom B-Roll (อัปโหลดมาเรียงเอง)": custom_videos = st.file_uploader("📂 อัปโหลดคลิป B-Roll จาก Google Labs (MP4)", type=["mp4"], accept_multiple_files=True)
            
    sub_config = render_subtitle_ui("mode1")
    uploaded_file = st.file_uploader("📂 อัปโหลดไฟล์เสียงเล่าเรื่อง (MP3/WAV/MP4)", type=["mp4", "mp3", "wav"])

    if uploaded_file and st.button("🚀 เริ่มผลิตคลิปไร้หน้า"):
        with st.spinner("กำลังทำงาน..."):
            file_ext = uploaded_file.name.split('.')[-1].lower()
            with open(f"raw_upload.{file_ext}", "wb") as f: f.write(uploaded_file.getbuffer())
            
            custom_broll_paths = []
            if custom_videos:
                for i, vid in enumerate(custom_videos):
                    p = f"custom_broll_{i}.mp4"
                    with open(p, "wb") as f: f.write(vid.getbuffer())
                    custom_broll_paths.append(p)

            if file_ext == "mp3": shutil.copy("raw_upload.mp3", "audio.mp3")
            elif file_ext == "wav": subprocess.run([FFMPEG_CMD, '-y', '-i', 'raw_upload.wav', '-c:a', 'libmp3lame', 'audio.mp3'], check=True)
            else: subprocess.run([FFMPEG_CMD, '-y', '-i', 'raw_upload.mp4', '-vn', '-c:a', 'libmp3lame', 'audio.mp3'], check=True)

            with open("audio.mp3", "rb") as audio_file:
                res_th = client.audio.transcriptions.create(model="whisper-large-v3", file=("audio.mp3", audio_file), response_format="verbose_json", language="th")

            video_width, video_height = (720, 1280) if faceless_mode != "ไม่ใช้ (ใช้วิดีโอต้นฉบับ)" else get_video_dimensions("raw_upload.mp4")
            
            actual_font_file = FONT_MAP[sub_config["font"]]
            actual_pil_font_size = int((sub_config["size"] / 288) * video_height * 0.75)
            allowed_pixel_width = video_width * (sub_config["max_w"] / 100)
            ass_font_size = int(sub_config["size"] * (video_height / 288.0))
            ass_outline = int(sub_config["outline"] * (video_height / 288.0))
            ass_margin_v = int(sub_config["margin_v"] * (video_height / 288.0))
            border_style = 3 if sub_config["bg_style"] == "แถบกล่องดำรองหลัง" else 1

            effect_prefix = ""
            if sub_config["anim"] == "เด้งพอง (Pop-up)": effect_prefix = f"{{\\fscx{sub_config['pop_scale']}\\fscy{sub_config['pop_scale']}\\t(0,{sub_config['pop_dur']},\\fscx100\\fscy100)}}"
            elif sub_config["anim"] == "ค่อยๆ ปรากฏ (Fade-in)": effect_prefix = f"{{\\fad({sub_config['fade_dur']},0)}}"
            
            ass_content = f"""[Script Info]\nScriptType: v4.00+\nPlayResX: {video_width}\nPlayResY: {video_height}\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Default,{sub_config["font"]},{ass_font_size},{hex_to_ass_color(sub_config["t_color"])},&H0000FFFF,{hex_to_ass_color(sub_config["o_color"])},&H80000000,0,0,0,0,100,100,0,0,{border_style},{ass_outline},0,2,10,10,{ass_margin_v},1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"""
            
            segments_data_for_subs, scenes, current_scene, s_start, s_idx = [], [], "", 0.0, 1
            
            for seg in res_th.segments:
                s, e, t = (seg['start'], seg['end'], seg['text'].strip()) if isinstance(seg, dict) else (seg.start, seg.end, seg.text.strip())
                if not t: continue
                for old_w, new_w in sub_config["replacements"].items(): t = re.sub(re.escape(old_w), new_w, t, flags=re.IGNORECASE)
                
                segments_data_for_subs.append((t, s, e))
                if current_scene == "": s_start = s
                current_scene += t + " "
                if (e - s_start) >= scene_target_duration:
                    scenes.append({"idx": s_idx, "start": s_start, "end": e, "text": current_scene}); s_idx += 1; current_scene = ""
            if current_scene: scenes.append({"idx": s_idx, "start": s_start, "end": e, "text": current_scene})
            
            for text_sub, start_time, end_time in segments_data_for_subs:
                formatted_text = split_text_by_pixel_width(text_sub, font_file=actual_font_file, pil_font_size=actual_pil_font_size, max_width_pixels=allowed_pixel_width)
                lines = formatted_text.split('\n')
                if sub_config["force_2_lines"] and len(lines) > 2:
                    chunks = [ "\n".join(lines[j:j+2]) for j in range(0, len(lines), 2) ]
                    t_start = start_time
                    total_chars = max(1, sum(len(c.replace('\n','')) for c in chunks))
                    for chunk in chunks:
                        c_dur = (end_time - start_time) * (len(chunk.replace('\n','')) / total_chars)
                        t_end = t_start + c_dur
                        ass_content += f"Dialogue: 0,{format_ass_timestamp(t_start)},{format_ass_timestamp(t_end)},Default,,0,0,0,,{effect_prefix}{chunk.replace('\n', '\\N')}\n"
                        t_start = t_end
                else: ass_content += f"Dialogue: 0,{format_ass_timestamp(start_time)},{format_ass_timestamp(end_time)},Default,,0,0,0,,{effect_prefix}{formatted_text.replace('\n', '\\N')}\n"
            
            with open("subs.ass", "w", encoding="utf-8") as f: f.write(ass_content)

            if faceless_mode != "ไม่ใช้ (ใช้วิดีโอต้นฉบับ)":
                with open("concat.txt", "w") as f:
                    for i, sc in enumerate(scenes):
                        c_path = f"clip_{sc['idx']}.mp4"
                        sc_dur = sc['end'] - sc['start']
                        if faceless_mode == "🤖 Pexels AI (ดึงภาพอัตโนมัติ)":
                            kw = get_action_keyword_from_ai(client, sc["text"])
                            if fetch_pexels_video(kw, pexels_key, "temp.mp4"): subprocess.run([FFMPEG_CMD, '-y', '-i', 'temp.mp4', '-ss', '0', '-t', str(sc_dur), '-vf', f'scale={video_width}:{video_height}:force_original_aspect_ratio=increase,crop={video_width}:{video_height}', '-c:v', 'libx264', '-an', c_path])
                            else: subprocess.run([FFMPEG_CMD, '-y', '-f', 'lavfi', '-i', f'color=c=black:s={video_width}x{video_height}:d={sc_dur}', '-c:v', 'libx264', c_path])
                        else:
                            in_b = custom_broll_paths[i % len(custom_broll_paths)] if custom_broll_paths else None
                            if in_b: subprocess.run([FFMPEG_CMD, '-y', '-i', in_b, '-ss', '0', '-t', str(sc_dur), '-vf', f'scale={video_width}:{video_height}:force_original_aspect_ratio=increase,crop={video_width}:{video_height}', '-c:v', 'libx264', '-an', c_path])
                            else: subprocess.run([FFMPEG_CMD, '-y', '-f', 'lavfi', '-i', f'color=c=black:s={video_width}x{video_height}:d={sc_dur}', '-c:v', 'libx264', c_path])
                        f.write(f"file '{c_path}'\n")
                subprocess.run([FFMPEG_CMD, '-y', '-f', 'concat', '-safe', '0', '-i', 'concat.txt', '-c:v', 'libx264', 'bg.mp4'])
                subprocess.run([FFMPEG_CMD, '-y', '-i', 'bg.mp4', '-i', 'audio.mp3', '-vf', 'subtitles=subs.ass:fontsdir=.', '-c:v', 'libx264', '-c:a', 'aac', 'output.mp4'])
            else: subprocess.run([FFMPEG_CMD, '-y', '-i', 'raw_upload.mp4', '-vf', 'subtitles=subs.ass:fontsdir=.', '-c:v', 'libx264', '-c:a', 'aac', 'output.mp4'])

        st.success("🎉 คลิปเสร็จสมบูรณ์!")
        with open("output.mp4", "rb") as f: st.download_button("📥 ดาวน์โหลดวิดีโอ", f, "faceless.mp4", "video/mp4")

# =========================================================
# 🎞️ โหมด 2: ต่อคลิปและฝังซับ (Join Video & Sub)
# =========================================================
elif app_mode == "🎞️ โหมด 2: ต่อคลิปและฝังซับ (Join & Sub)":
    st.markdown("## 🎞️ โหมดต่อคลิปพร้อมเสียง & ฝังซับอัตโนมัติ")
    st.info("อัปโหลดคลิปวิดีโอ (MP4) หลายๆ คลิปที่มีเสียงพูดอยู่แล้ว ระบบจะนำมาเรียงต่อกันและเจาะเสียงไปทำซับไตเติลให้ตลอดทั้งคลิปครับ")
    
    sub_config = render_subtitle_ui("mode2")
    uploaded_videos = st.file_uploader("📂 อัปโหลดวิดีโอ (MP4)", type=["mp4"], accept_multiple_files=True)

    if uploaded_videos and st.button("🚀 รวมคลิปและสร้างซับไตเติล"):
        with st.spinner("กำลังต่อคลิปวิดีโอ..."):
            with open("concat_join.txt", "w", encoding="utf-8") as f:
                for i, vid in enumerate(uploaded_videos):
                    v_path = f"part_{i}.mp4"
                    with open(v_path, "wb") as f_vid: f_vid.write(vid.getbuffer())
                    f.write(f"file '{v_path}'\n")
            
            subprocess.run([FFMPEG_CMD, '-y', '-f', 'concat', '-safe', '0', '-i', 'concat_join.txt', '-c', 'copy', 'combined.mp4'], check=True)
            subprocess.run([FFMPEG_CMD, '-y', '-i', 'combined.mp4', '-vn', '-c:a', 'libmp3lame', 'audio_joined.mp3'], check=True)
            
        with st.spinner("กำลังฟังเสียงและสร้างซับไตเติล..."):
            with open("audio_joined.mp3", "rb") as audio_file:
                res_th = client.audio.transcriptions.create(model="whisper-large-v3", file=("audio_joined.mp3", audio_file), response_format="verbose_json", language="th")
            
            v_w, v_h = get_video_dimensions("combined.mp4")
            actual_font_file = FONT_MAP[sub_config["font"]]
            actual_pil_font_size = int((sub_config["size"] / 288) * v_h * 0.75)
            allowed_pixel_width = v_w * (sub_config["max_w"] / 100)
            ass_font_size = int(sub_config["size"] * (v_h / 288.0))
            ass_outline = int(sub_config["outline"] * (v_h / 288.0))
            ass_margin_v = int(sub_config["margin_v"] * (v_h / 288.0))
            border_style = 3 if sub_config["bg_style"] == "แถบกล่องดำรองหลัง" else 1

            effect_prefix = ""
            if sub_config["anim"] == "เด้งพอง (Pop-up)": effect_prefix = f"{{\\fscx{sub_config['pop_scale']}\\fscy{sub_config['pop_scale']}\\t(0,{sub_config['pop_dur']},\\fscx100\\fscy100)}}"
            elif sub_config["anim"] == "ค่อยๆ ปรากฏ (Fade-in)": effect_prefix = f"{{\\fad({sub_config['fade_dur']},0)}}"
            
            ass = f"""[Script Info]\nScriptType: v4.00+\nPlayResX: {v_w}\nPlayResY: {v_h}\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Default,{sub_config["font"]},{ass_font_size},{hex_to_ass_color(sub_config["t_color"])},&H0000FFFF,{hex_to_ass_color(sub_config["o_color"])},&H80000000,0,0,0,0,100,100,0,0,{border_style},{ass_outline},0,2,10,10,{ass_margin_v},1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"""
            
            for seg in res_th.segments:
                s, e, t = (seg['start'], seg['end'], seg['text'].strip()) if isinstance(seg, dict) else (seg.start, seg.end, seg.text.strip())
                if not t: continue
                for old_w, new_w in sub_config["replacements"].items(): t = re.sub(re.escape(old_w), new_w, t, flags=re.IGNORECASE)
                
                formatted_text = split_text_by_pixel_width(t, font_file=actual_font_file, pil_font_size=actual_pil_font_size, max_width_pixels=allowed_pixel_width)
                
                lines = formatted_text.split('\n')
                if sub_config["force_2_lines"] and len(lines) > 2:
                    chunks = [ "\n".join(lines[j:j+2]) for j in range(0, len(lines), 2) ]
                    t_start = s
                    total_chars = max(1, sum(len(c.replace('\n','')) for c in chunks))
                    for chunk in chunks:
                        c_dur = (e - s) * (len(chunk.replace('\n','')) / total_chars)
                        t_end = t_start + c_dur
                        ass += f"Dialogue: 0,{format_ass_timestamp(t_start)},{format_ass_timestamp(t_end)},Default,,0,0,0,,{effect_prefix}{chunk.replace('\n', '\\N')}\n"
                        t_start = t_end
                else: ass += f"Dialogue: 0,{format_ass_timestamp(s)},{format_ass_timestamp(e)},Default,,0,0,0,,{effect_prefix}{formatted_text.replace('\n', '\\N')}\n"
            
            with open("subs_joined.ass", "w", encoding="utf-8") as f: f.write(ass)
            subprocess.run([FFMPEG_CMD, '-y', '-i', 'combined.mp4', '-vf', 'subtitles=subs_joined.ass:fontsdir=.', '-c:v', 'libx264', '-c:a', 'aac', 'output_joined.mp4'])
            
        st.success("🎉 ประกอบคลิปและฝังซับไตเติลเสร็จสมบูรณ์!")
        with open("output_joined.mp4", "rb") as f: st.download_button("📥 ดาวน์โหลดวิดีโอ", f, "joined_video_with_subs.mp4", "video/mp4")
