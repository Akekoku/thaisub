import streamlit as st
from groq import Groq
import subprocess
import os
import shutil
import asyncio
import edge_tts
from pythainlp.tokenize import word_tokenize
from PIL import ImageFont
import requests
import random
import time

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

def get_video_dimensions(video_path):
    try:
        cmd = ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height', '-of', 'csv=s=x:p=0', video_path]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        width_str, height_str = result.stdout.strip().split('x')
        return int(width_str), int(height_str)
    except Exception: return 720, 1280

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
# 🎛️ เมนูสลับโหมดการทำงาน (Sidebar)
# =========================================================
st.sidebar.markdown("## 🛠️ เลือกโหมดการทำงาน")
app_mode = st.sidebar.radio("สตูดิโอของคุณ:", [
    "🎭 โหมด 1: สร้างคลิปไร้หน้า (Faceless)", 
    "🎞️ โหมด 2: ต่อคลิปและฝังซับ (Join & Sub)"
])

client = Groq(api_key=api_key)

# =========================================================
# 🎭 โหมด 1: สร้างคลิปไร้หน้า (Faceless / Storyboard)
# =========================================================
if app_mode == "🎭 โหมด 1: สร้างคลิปไร้หน้า (Faceless)":
    st.markdown("## 🎭 โหมดสร้างคลิปไร้หน้า (Storyboard Automation)")
    
    faceless_mode = st.radio("เลือกวิธีสร้างวิดีโอพื้นหลัง:", ["ไม่ใช้ (ใช้วิดีโอต้นฉบับ)", "🤖 Pexels AI (ดึงภาพอัตโนมัติ)", "📂 Custom B-Roll (อัปโหลดมาเรียงเอง)"], index=0)
    scene_target_duration, custom_videos = 8.0, []
    if faceless_mode != "ไม่ใช้ (ใช้วิดีโอต้นฉบับ)":
        scene_target_duration = st.slider("⏱️ ความยาวแต่ละฉาก (วินาที)", 4.0, 15.0, 8.0, 1.0)
        if faceless_mode == "📂 Custom B-Roll (อัปโหลดมาเรียงเอง)":
            custom_videos = st.file_uploader("📂 อัปโหลดคลิป B-Roll จาก Google Labs (MP4)", type=["mp4"], accept_multiple_files=True)
            
    st.markdown("### 🛠️ ปรับแต่งสไตล์ซับไตเติล")
    with st.expander("เปิดเครื่องมือปรับแต่ง", expanded=False):
        font_choice = st.selectbox("✒️ ฟอนต์:", list(FONT_MAP.keys()), index=8)
        font_size_choice = st.slider("ขนาดตัวอักษร:", 14, 40, 18)
        text_color = st.color_picker("🅰️ สีตัวอักษร", "#FFFFFF")
        outline_color = st.color_picker("🖍️ สีขอบ", "#000000")

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
            elif file_ext == "wav": subprocess.run(['ffmpeg', '-y', '-i', 'raw_upload.wav', '-c:a', 'libmp3lame', 'audio.mp3'], check=True)
            else: subprocess.run(['ffmpeg', '-y', '-i', 'raw_upload.mp4', '-vn', '-c:a', 'libmp3lame', 'audio.mp3'], check=True)

            with open("audio.mp3", "rb") as audio_file:
                res_th = client.audio.transcriptions.create(model="whisper-large-v3", file=("audio.mp3", audio_file), response_format="verbose_json", language="th")

            video_width, video_height = (720, 1280) if faceless_mode != "ไม่ใช้ (ใช้วิดีโอต้นฉบับ)" else get_video_dimensions("raw_upload.mp4")
            
            ass_content = f"[Script Info]\nScriptType: v4.00+\nPlayResX: {video_width}\nPlayResY: {video_height}\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BorderStyle, Outline, Alignment, MarginV\nStyle: Default,{font_choice},{int(font_size_choice * (video_height/288))},{hex_to_ass_color(text_color)},{hex_to_ass_color(outline_color)},1,2,2,50\n\n[Events]\nFormat: Layer, Start, End, Style, Text\n"
            
            segments, scenes, current_scene, s_start, s_idx = [], [], "", 0.0, 1
            for seg in res_th.segments:
                s, e, t = (seg['start'], seg['end'], seg['text'].strip()) if isinstance(seg, dict) else (seg.start, seg.end, seg.text.strip())
                if not t: continue
                segments.append((t, s, e))
                ass_content += f"Dialogue: 0,{format_ass_timestamp(s)},{format_ass_timestamp(e)},Default,{t}\n"
                
                if current_scene == "": s_start = s
                current_scene += t + " "
                if (e - s_start) >= scene_target_duration:
                    scenes.append({"idx": s_idx, "start": s_start, "end": e, "text": current_scene}); s_idx += 1; current_scene = ""
            if current_scene: scenes.append({"idx": s_idx, "start": s_start, "end": e, "text": current_scene})
            
            with open("subs.ass", "w", encoding="utf-8") as f: f.write(ass_content)

            # --- รวมวิดีโอ ---
            if faceless_mode != "ไม่ใช้ (ใช้วิดีโอต้นฉบับ)":
                with open("concat.txt", "w") as f:
                    for i, sc in enumerate(scenes):
                        c_path = f"clip_{sc['idx']}.mp4"
                        sc_dur = sc['end'] - sc['start']
                        if faceless_mode == "🤖 Pexels AI (ดึงภาพอัตโนมัติ)":
                            kw = get_action_keyword_from_ai(client, sc["text"])
                            if fetch_pexels_video(kw, pexels_key, "temp.mp4"):
                                subprocess.run(['ffmpeg', '-y', '-i', 'temp.mp4', '-ss', '0', '-t', str(sc_dur), '-vf', f'scale={video_width}:{video_height}:force_original_aspect_ratio=increase,crop={video_width}:{video_height}', '-c:v', 'libx264', '-an', c_path])
                            else: subprocess.run(['ffmpeg', '-y', '-f', 'lavfi', '-i', f'color=c=black:s={video_width}x{video_height}:d={sc_dur}', '-c:v', 'libx264', c_path])
                        else:
                            in_b = custom_broll_paths[i % len(custom_broll_paths)] if custom_broll_paths else None
                            if in_b: subprocess.run(['ffmpeg', '-y', '-i', in_b, '-ss', '0', '-t', str(sc_dur), '-vf', f'scale={video_width}:{video_height}:force_original_aspect_ratio=increase,crop={video_width}:{video_height}', '-c:v', 'libx264', '-an', c_path])
                            else: subprocess.run(['ffmpeg', '-y', '-f', 'lavfi', '-i', f'color=c=black:s={video_width}x{video_height}:d={sc_dur}', '-c:v', 'libx264', c_path])
                        f.write(f"file '{c_path}'\n")
                subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', 'concat.txt', '-c:v', 'libx264', 'bg.mp4'])
                subprocess.run(['ffmpeg', '-y', '-i', 'bg.mp4', '-i', 'audio.mp3', '-vf', 'subtitles=subs.ass:fontsdir=.', '-c:v', 'libx264', '-c:a', 'aac', 'output.mp4'])
            else:
                subprocess.run(['ffmpeg', '-y', '-i', 'raw_upload.mp4', '-vf', 'subtitles=subs.ass:fontsdir=.', '-c:v', 'libx264', '-c:a', 'aac', 'output.mp4'])

        st.success("🎉 คลิปไร้หน้าเสร็จสมบูรณ์!")
        with open("output.mp4", "rb") as f: st.download_button("📥 ดาวน์โหลดวิดีโอ", f, "faceless.mp4", "video/mp4")


# =========================================================
# 🎞️ โหมด 2: ต่อคลิปและฝังซับ (Join Video & Sub)
# =========================================================
elif app_mode == "🎞️ โหมด 2: ต่อคลิปและฝังซับ (Join & Sub)":
    st.markdown("## 🎞️ โหมดต่อคลิปพร้อมเสียง & ฝังซับอัตโนมัติ")
    st.info("อัปโหลดคลิปวิดีโอ (MP4) หลายๆ คลิปที่มีเสียงพูดอยู่แล้ว ระบบจะนำมาเรียงต่อกันและเจาะเสียงไปทำซับไตเติลให้ตลอดทั้งคลิปครับ")
    
    st.markdown("### 🛠️ ปรับแต่งสไตล์ซับไตเติล")
    with st.expander("เปิดเครื่องมือปรับแต่ง", expanded=False):
        font_choice = st.selectbox("✒️ ฟอนต์:", list(FONT_MAP.keys()), index=8)
        font_size_choice = st.slider("ขนาดตัวอักษร:", 14, 40, 18)
        text_color = st.color_picker("🅰️ สีตัวอักษร", "#FFFF00", key="j_color")
        outline_color = st.color_picker("🖍️ สีขอบ", "#000000", key="j_out")

    uploaded_videos = st.file_uploader("📂 อัปโหลดวิดีโอ (MP4)", type=["mp4"], accept_multiple_files=True)

    if uploaded_videos and st.button("🚀 รวมคลิปและสร้างซับไตเติล"):
        with st.spinner("กำลังต่อคลิปวิดีโอ..."):
            with open("concat_join.txt", "w", encoding="utf-8") as f:
                for i, vid in enumerate(uploaded_videos):
                    v_path = f"part_{i}.mp4"
                    with open(v_path, "wb") as f_vid: f_vid.write(vid.getbuffer())
                    f.write(f"file '{v_path}'\n")
            
            # ต่อคลิปและแยกเสียง
            subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', 'concat_join.txt', '-c', 'copy', 'combined.mp4'], check=True)
            subprocess.run(['ffmpeg', '-y', '-i', 'combined.mp4', '-vn', '-c:a', 'libmp3lame', 'audio_joined.mp3'], check=True)
            
        with st.spinner("กำลังฟังเสียงและสร้างซับไตเติล..."):
            with open("audio_joined.mp3", "rb") as audio_file:
                res_th = client.audio.transcriptions.create(model="whisper-large-v3", file=("audio_joined.mp3", audio_file), response_format="verbose_json", language="th")
            
            v_w, v_h = get_video_dimensions("combined.mp4")
            ass = f"[Script Info]\nScriptType: v4.00+\nPlayResX: {v_w}\nPlayResY: {v_h}\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BorderStyle, Outline, Alignment, MarginV\nStyle: Default,{font_choice},{int(font_size_choice * (v_h/288))},{hex_to_ass_color(text_color)},{hex_to_ass_color(outline_color)},1,2,2,50\n\n[Events]\nFormat: Layer, Start, End, Style, Text\n"
            
            for seg in res_th.segments:
                s, e, t = (seg['start'], seg['end'], seg['text'].strip()) if isinstance(seg, dict) else (seg.start, seg.end, seg.text.strip())
                if t: ass += f"Dialogue: 0,{format_ass_timestamp(s)},{format_ass_timestamp(e)},Default,{t}\n"
            
            with open("subs_joined.ass", "w", encoding="utf-8") as f: f.write(ass)
            
            subprocess.run(['ffmpeg', '-y', '-i', 'combined.mp4', '-vf', 'subtitles=subs_joined.ass:fontsdir=.', '-c:v', 'libx264', '-c:a', 'aac', 'output_joined.mp4'])
            
        st.success("🎉 ประกอบคลิปและฝังซับไตเติลเสร็จสมบูรณ์!")
        with open("output_joined.mp4", "rb") as f: st.download_button("📥 ดาวน์โหลดวิดีโอ", f, "joined_video_with_subs.mp4", "video/mp4")
