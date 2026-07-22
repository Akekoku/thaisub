import streamlit as st
from groq import Groq
import subprocess
import os
import shutil
import asyncio
from pythainlp.tokenize import word_tokenize
from pythainlp.util import normalize as normalize_thai
from PIL import ImageFont
import requests
import random
import time
import re
import json
import difflib
import pandas as pd

# =========================================================
# ⚙️ ส่วนตั้งค่าเริ่มต้น & ฟังก์ชันช่วยเหลือ
# =========================================================
FONT_MAP = {
    "Kanit": "Kanit-Regular.ttf", "Kanit Medium": "Kanit-Medium.ttf", "Kanit Bold": "Kanit-Bold.ttf",
    "Noto Sans Thai": "NotoSansThai-Regular.ttf", "Noto Sans Thai Medium": "NotoSansThai-Medium.ttf",
    "Noto Sans Thai Bold": "NotoSansThai-Bold.ttf", "Sarabun": "Sarabun.ttf", "Chonburi": "Chonburi.ttf", "Mali": "Mali.ttf"
}

PROFILE_FILE = "subtitle_profiles.json"

def load_profiles():
    default_profiles = {
        "🎬 สไตล์ Tiktok (เด้งพอง ตัวเหลือง)": {
            "replace": "แบตเตอรี่กับรถ=แบตเตอรี่ลด, Save=เซฟ, OK=โอเค", "font": "Kanit Bold", "tc": "#FFFF00", "oc": "#000000",
            "bg": "ขอบปกติ", "anim": "เด้งพอง (Pop-up)", "ps": 130, "pd": 150, "fd": 200, 
            "fs": 22, "ot": 2, "mw": 90, "mv": 50, "ll": "🚫 บังคับ 1 บรรทัด", "ai_proof": True, "auto_cut": "ปิด (เก็บช่วงเงียบไว้ปกติ)"
        },
        "🎞️ สไตล์ Cinematic (เรียบหรู กล่องดำ)": {
            "replace": "Save=เซฟ", "font": "Sarabun", "tc": "#FFFFFF", "oc": "#000000",
            "bg": "แถบกล่องดำรองหลัง", "anim": "ค่อยๆ ปรากฏ (Fade-in)", "ps": 130, "pd": 150, "fd": 300, 
            "fs": 16, "ot": 0, "mw": 100, "mv": 30, "ll": "ไม่จำกัด (ตามความกว้าง)", "ai_proof": True, "auto_cut": "ปิด (เก็บช่วงเงียบไว้ปกติ)"
        }
    }
    if os.path.exists(PROFILE_FILE):
        try:
            with open(PROFILE_FILE, "r", encoding="utf-8") as f:
                loaded_profs = json.load(f)
                for k, v in default_profiles.items(): loaded_profs[k] = v
                return loaded_profs
        except: pass
    save_profiles(default_profiles)
    return default_profiles

def save_profiles(profs):
    with open(PROFILE_FILE, "w", encoding="utf-8") as f:
        json.dump(profs, f, ensure_ascii=False, indent=4)

def hex_to_ass_color(hex_str, alpha_hex="00"):
    hex_str = hex_str.lstrip('#')
    return f"&H{alpha_hex}{hex_str[4:6]}{hex_str[2:4]}{hex_str[0:2]}"

def format_ass_timestamp(seconds):
    hours, minutes, secs = int(seconds // 3600), int((seconds % 3600) // 60), int(seconds % 60)
    centis = int(round((seconds - int(seconds)) * 100))
    if centis == 100: secs += 1; centis = 0
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"

# 🌟 V.53/54: The Ultimate PUA Engine (สุดยอดอัลกอริทึมแก้สระลอย)
def fix_thai_floating_vowels(text):
    if not text: return text
    
    # 1. แยกสระอำ เป็น นิคหิต + สระอา เพื่อหลบวรรณยุกต์
    text = text.replace("ำ", "ํา")
    
    # 2. จัดระเบียบการพิมพ์ (พยัญชนะ -> สระ -> วรรณยุกต์)
    text = normalize_thai(text)
    
    # 3. กำหนดกลุ่มตัวอักษรเพื่อเตรียม Shift ตำแหน่ง
    left_cons = ['ป', 'ฝ', 'ฟ', 'ฬ', 'พ'] 
    down_cons = ['ฎ', 'ฏ', 'ฐ']
    upper_vowels = ['\u0e31', '\u0e34', '\u0e35', '\u0e36', '\u0e37', '\u0e4d']
    tone_marks = ['\u0e48', '\u0e49', '\u0e4a', '\u0e4b', '\u0e4c']
    lower_vowels = ['\u0e38', '\u0e39']
    
    # 4. แปลงร่างเป็นรหัส PUA (Private Use Area) ที่มีในฟอนต์ Kanit/Sarabun
    tone_up = {'\u0e48': '\uf70a', '\u0e49': '\uf70b', '\u0e4a': '\uf70c', '\u0e4b': '\uf70d', '\u0e4c': '\uf70e'}
    tone_left = {'\u0e48': '\uf705', '\u0e49': '\uf706', '\u0e4a': '\uf707', '\u0e4b': '\uf708', '\u0e4c': '\uf709'}
    vowel_left = {'\u0e31': '\uf710', '\u0e34': '\uf701', '\u0e35': '\uf702', '\u0e36': '\uf703', '\u0e37': '\uf704', '\u0e4d': '\uf711'}
    vowel_down = {'\u0e38': '\uf718', '\u0e39': '\uf719'}
    
    res = ""
    for i, char in enumerate(text):
        prev_char = res[-1] if len(res) > 0 else ""
        
        if char in lower_vowels and prev_char in down_cons:
            res += vowel_down.get(char, char) # หลบลงล่าง
        elif char in upper_vowels and prev_char in left_cons:
            res += vowel_left.get(char, char) # หลบซ้าย
        elif char in tone_marks:
            if prev_char in upper_vowels or prev_char in vowel_left.values():
                res += tone_up.get(char, char) # วรรณยุกต์ชูคอขึ้นบน
            elif prev_char in left_cons:
                res += tone_left.get(char, char) # วรรณยุกต์หลบซ้าย
            else:
                res += char
        else:
            res += char
            
    return res

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
        prompt = f"Read this Thai scene description: '{thai_text}'. Create a 2 to 4 word English search query for Pexels Stock Video. Output ONLY the search query."
        res = client.chat.completions.create(messages=[{"role": "user", "content": prompt}], model="llama-3.1-8b-instant", temperature=0.2)
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

def clean_whisper_segments(segments):
    cleaned = []
    for seg in segments:
        text = seg['text'].strip()
        if not text or text in ["ซับไทยโดย GDH", "แปลซับโดย", "ดนตรี", "เสียงดนตรี"]: continue
        if not cleaned:
            cleaned.append(seg); continue
        last_seg = cleaned[-1]
        last_text = last_seg['text'].strip()
        if text == last_text and (seg['start'] - last_seg['end'] < 1.0):
            last_seg['end'] = max(last_seg['end'], seg['end']); continue
        if seg['start'] < last_seg['end']: 
            orig_dur = max(0.5, seg['end'] - seg['start'])
            seg['start'] = last_seg['end'] + 0.01 
            seg['end'] = seg['start'] + orig_dur
        cleaned.append(seg)
    return cleaned

def ai_proofread_segments(client, segments, user_replacements=""):
    chunk_size = 10
    success_all = True
    for i in range(0, len(segments), chunk_size):
        chunk = segments[i:i+chunk_size]
        # 🌟 แก้ไขบั๊ก SyntaxError ตรงนี้ครับ
        data_to_fix = [{"id": str(idx), "text": seg["text"]} for idx, seg in enumerate(chunk)]
        
        prompt = f"""คุณคือ AI ผู้ช่วยตรวจสอบซับไตเติล
หน้าที่ของคุณ: ตรวจสอบและแก้ไขเฉพาะ "คำสะกดผิดไวยากรณ์" เท่านั้น
กฎเหล็กขั้นเด็ดขาด: ห้ามเปลี่ยนความหมาย ห้ามลบคำ ตอบกลับเป็น JSON: {{"corrected": [{{"id": "0", "text": "ข้อความ"}}]}}
คำใบ้เพิ่มเติม (ทับศัพท์): {user_replacements}\n
ข้อความต้นฉบับ:
{json.dumps(data_to_fix, ensure_ascii=False)}"""
        for attempt in range(3):
            try:
                res = client.chat.completions.create(messages=[{"role": "user", "content": prompt}], model="llama-3.1-8b-instant", temperature=0.0, response_format={"type": "json_object"})
                content = res.choices[0].message.content.strip()
                if "{" in content and "}" in content: content = content[content.find("{"):content.rfind("}")+1]
                data = json.loads(content)
                corrected_list = data.get("corrected", [])
                if len(corrected_list) == len(data_to_fix):
                    for item in corrected_list: segments[i + int(item["id"])]["text"] = str(item["text"])
                    break 
            except Exception: time.sleep(3)
    return segments

def handle_load_profile(key_prefix, profiles, defaults):
    selected = st.session_state.get(f"{key_prefix}_sel_prof")
    if selected and selected != "-- เลือกโปรไฟล์ --":
        for k, v in profiles[selected].items():
            if k in defaults: st.session_state[f"{key_prefix}_{k}"] = v

# =========================================================
# 🔒 ระบบความปลอดภัย (Gatekeeper) & CSS
# =========================================================
st.set_page_config(page_title="AI Studio Pro", page_icon="🎬", layout="wide", initial_sidebar_state="expanded")

# แทรก CSS เพื่อแก้อาการสระทับกันในตาราง Data Editor ตอนดูผ่านมือถือ
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Sarabun:wght@400;700&display=swap');
    div[data-testid="stDataEditor"] { line-height: 1.8 !important; font-family: 'Sarabun', sans-serif; }
    </style>
""", unsafe_allow_html=True)

if "authenticated" not in st.session_state: st.session_state["authenticated"] = False
if not st.session_state["authenticated"]:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<h2 style='text-align: center;'>🔐 ระบบภายในส่วนตัว</h2>", unsafe_allow_html=True)
        user_password = st.text_input("🔑 รหัสผ่าน:", type="password")
        if st.button("🔓 เข้าสู่ระบบ", use_container_width=True):
            if user_password == st.secrets.get("APP_PASSWORD", "12345"): st.session_state["authenticated"] = True; st.rerun()
            else: st.error("❌ รหัสผ่านไม่ถูกต้อง!")
    st.stop()

if "GROQ_API_KEY" in st.secrets: api_key = st.secrets["GROQ_API_KEY"]
else: st.error("❌ ยังไม่ได้ตั้งค่า Groq API Key"); st.stop()
pexels_key = st.secrets.get("PEXELS_API_KEY", "")
client = Groq(api_key=api_key)

# =========================================================
# 🎛️ เมนูสลับโหมดการทำงาน (Sidebar)
# =========================================================
st.sidebar.title("🎬 AI Studio Pro")
st.sidebar.markdown("---")
app_mode = st.sidebar.radio("📌 เลือกโหมดการทำงาน:", ["🎭 โหมด 1: สร้างคลิปไร้หน้า (Faceless)", "🎞️ โหมด 2: ต่อคลิปและฝังซับ (Join & Sub)"])

st.sidebar.markdown("---")
st.sidebar.markdown("**TH เอนจินแก้สระลอย (PUA System)**")
st.sidebar.success("✅ ระบบฝัง PUA Engine ไว้ในโค้ดแล้ว (รองรับฟอนต์ Kanit/Sarabun 100% ไม่ต้องดาวน์โหลดเอนจินเพิ่ม)")
st.sidebar.markdown("---")

FFMPEG_CMD = "./ffmpeg" if os.path.exists("./ffmpeg") else "ffmpeg"
FFPROBE_CMD = "./ffprobe" if os.path.exists("./ffprobe") else "ffprobe"

def get_video_dimensions(video_path):
    try:
        cmd = [FFPROBE_CMD, '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height', '-of', 'csv=s=x:p=0', video_path]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return map(int, result.stdout.strip().split('x'))
    except Exception: return 720, 1280

def get_video_duration(video_path):
    try:
        cmd = [FFPROBE_CMD, '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', video_path]
        return float(subprocess.run(cmd, capture_output=True, text=True, check=True).stdout.strip())
    except Exception: return 0.0

def render_subtitle_ui(key_prefix):
    defaults = {
        "replace": "แบตเตอรี่กับรถ=แบตเตอรี่ลด, Save=เซฟ, OK=โอเค", "font": "Kanit Bold", "tc": "#FFFF00", "oc": "#000000", "bg": "ขอบปกติ",
        "anim": "เด้งพอง (Pop-up)", "ps": 130, "pd": 150, "fd": 200, 
        "fs": 18, "ot": 1, "mw": 100, "mv": 50, "ll": "🚫 บังคับไม่เกิน 2 บรรทัด", "ai_proof": True, "auto_cut": "ปิด (เก็บช่วงเงียบไว้ปกติ)"
    }
    profiles = load_profiles()
    for p_name, p_data in profiles.items():
        if "ll" not in p_data and "f2l" in p_data: p_data["ll"] = "🚫 บังคับไม่เกิน 2 บรรทัด" if p_data["f2l"] else "ไม่จำกัด (ตามความกว้าง)"
        if "ai_proof" not in p_data: p_data["ai_proof"] = True 
        if "auto_cut" not in p_data: p_data["auto_cut"] = "ปิด (เก็บช่วงเงียบไว้ปกติ)"
    for k, v in defaults.items():
        if f"{key_prefix}_{k}" not in st.session_state: st.session_state[f"{key_prefix}_{k}"] = v

    with st.expander("⚙️ แผงควบคุมและตั้งค่าสตูดิโอ (คลิกเพื่อเปิด/ปิด)", expanded=False):
        tab_design, tab_ai, tab_profile = st.tabs(["🎨 ดีไซน์ซับไตเติล", "🤖 AI & การตัดต่อ", "💾 จัดการโปรไฟล์"])
        with tab_design:
            col_font, col_tc, col_oc, col_bg = st.columns(4)
            with col_font: font_choice = st.selectbox("✒️ ฟอนต์", list(FONT_MAP.keys()), key=f"{key_prefix}_font")
            with col_tc: text_color = st.color_picker("🅰️ สีตัวอักษร", key=f"{key_prefix}_tc")
            with col_oc: outline_color = st.color_picker("🖍️ สีขอบ", key=f"{key_prefix}_oc")
            with col_bg: bg_style = st.selectbox("🔲 พื้นหลัง", ["ขอบปกติ", "แถบกล่องดำรองหลัง"], key=f"{key_prefix}_bg")
            st.markdown("---")
            col_anim, col_anim_opt1, col_anim_opt2 = st.columns(3)
            with col_anim: anim_choice = st.selectbox("🎬 เอฟเฟกต์แอนิเมชัน", ["ไม่มี", "เด้งพอง (Pop-up)", "ค่อยๆ ปรากฏ (Fade-in)"], key=f"{key_prefix}_anim")
            if anim_choice == "เด้งพอง (Pop-up)":
                with col_anim_opt1: pop_scale = st.slider("ความขยายตอนเด้ง (%)", 110, 180, key=f"{key_prefix}_ps")
                with col_anim_opt2: pop_duration = st.slider("ความเร็วยุบตัว (ms)", 50, 400, key=f"{key_prefix}_pd")
                fade_duration = st.session_state[f"{key_prefix}_fd"]
            elif anim_choice == "ค่อยๆ ปรากฏ (Fade-in)":
                with col_anim_opt1: fade_duration = st.slider("ความเร็ว Fade (ms)", 100, 1000, key=f"{key_prefix}_fd")
                pop_scale = st.session_state[f"{key_prefix}_ps"]
                pop_duration = st.session_state[f"{key_prefix}_pd"]
            else:
                pop_scale, pop_duration, fade_duration = st.session_state[f"{key_prefix}_ps"], st.session_state[f"{key_prefix}_pd"], st.session_state[f"{key_prefix}_fd"]
            st.markdown("---")
            col_size1, col_size2 = st.columns(2)
            with col_size1:
                font_size_choice = st.slider("ขนาดตัวอักษร", 14, 40, key=f"{key_prefix}_fs")
                outline_thickness = st.slider("ความหนาขอบ", 0, 5, key=f"{key_prefix}_ot")
            with col_size2:
                max_width_pct = st.slider("ความกว้างกรอบข้อความ (%)", 50, 150, key=f"{key_prefix}_mw")
                margin_v_choice = st.slider("ความสูงจากขอบล่าง", 20, 200, key=f"{key_prefix}_mv")
            line_limit_choice = st.radio("การจัดบรรทัด", ["ไม่จำกัด (ตามความกว้าง)", "🚫 บังคับไม่เกิน 2 บรรทัด", "🚫 บังคับ 1 บรรทัด"], horizontal=True, key=f"{key_prefix}_ll")
        with tab_ai:
            auto_cut_choice = st.radio("จัดการช่วงเงียบ (Dead Air):", ["ปิด (เก็บช่วงเงียบไว้ปกติ)", "เปิด (ตัดช่วงเงียบอัตโนมัติ)"], horizontal=True, key=f"{key_prefix}_ac")
            st.markdown("---")
            ai_proof_choice = st.checkbox("เปิดใช้งาน AI พิสูจน์อักษร", key=f"{key_prefix}_ai_proof")
            replace_words_input = st.text_area("📝 แก้ไขคำทับศัพท์ (คำเดิม=คำใหม่ คั่นด้วยลูกน้ำ)", key=f"{key_prefix}_replace", height=68)
        with tab_profile:
            prof_names = ["-- เลือกโปรไฟล์ --"] + list(profiles.keys())
            col_sel, col_load_btn = st.columns([3, 1])
            with col_sel: st.selectbox("เลือกโปรไฟล์ที่บันทึกไว้:", prof_names, key=f"{key_prefix}_sel_prof", label_visibility="collapsed")
            with col_load_btn: st.button("📥 โหลด", key=f"{key_prefix}_load_btn", on_click=handle_load_profile, args=(key_prefix, profiles, defaults), use_container_width=True)
            col_name, col_save_btn, col_del_btn = st.columns([2, 1, 1])
            with col_name: new_prof_name = st.text_input("ชื่อโปรไฟล์:", placeholder="ตั้งชื่อ...", key=f"{key_prefix}_new_prof", label_visibility="collapsed")
            with col_save_btn:
                if st.button("💾 บันทึก", key=f"{key_prefix}_save_btn", use_container_width=True):
                    if new_prof_name:
                        profiles[new_prof_name] = {k: st.session_state[f"{key_prefix}_{k}"] for k in defaults.keys()}
                        save_profiles(profiles); st.success(f"บันทึก '{new_prof_name}' แล้ว!"); time.sleep(1); st.rerun()
            with col_del_btn:
                if st.button("🗑️ ลบ", key=f"{key_prefix}_del_btn", use_container_width=True):
                    selected_for_del = st.session_state.get(f"{key_prefix}_sel_prof")
                    if selected_for_del != "-- เลือกโปรไฟล์ --" and selected_for_del in profiles:
                        del profiles[selected_for_del]; save_profiles(profiles); st.success("ลบทิ้งแล้ว!"); time.sleep(1); st.rerun()

        replace_dict = {}
        if replace_words_input.strip():
            for pair in replace_words_input.split(','):
                if '=' in pair: old_w, new_w = pair.split('=', 1); replace_dict[old_w.strip()] = new_w.strip()
        
        return {
            "font": font_choice, "t_color": text_color, "o_color": outline_color, "bg_style": bg_style, "anim": anim_choice, 
            "pop_scale": pop_scale, "pop_dur": pop_duration, "fade_dur": fade_duration, "size": font_size_choice, 
            "outline": outline_thickness, "max_w": max_width_pct, "margin_v": margin_v_choice,
            "line_limit": line_limit_choice, "replacements": replace_dict, "ai_proof": ai_proof_choice,
            "raw_replace_input": replace_words_input, "auto_cut": auto_cut_choice
        }

# =========================================================
# 🎭 โหมด 1: สร้างคลิปไร้หน้า (Faceless / Storyboard)
# =========================================================
if "m1_segments" not in st.session_state: st.session_state.m1_segments = None
if "m1_video_path" not in st.session_state: st.session_state.m1_video_path = None

if app_mode == "🎭 โหมด 1: สร้างคลิปไร้หน้า (Faceless)":
    st.markdown("## 🎭 สตูดิโอสร้างคลิปไร้หน้า (Faceless)")
    st.markdown("---")
    
    st.markdown("### 1️⃣ อัปโหลดและตั้งค่าฉาก")
    uploaded_file = st.file_uploader("📂 อัปโหลดไฟล์เสียง (MP3/WAV/MP4)", type=["mp4", "mp3", "wav"])
    faceless_mode = st.radio("พื้นหลังวิดีโอ:", ["ไม่ใช้ (ใช้วิดีโอต้นฉบับ)", "🤖 Pexels AI (ดึงภาพอัตโนมัติ)", "📂 Custom B-Roll (อัปโหลดมาเรียงเอง)"], horizontal=True)
    scene_target_duration, custom_videos = 8.0, []
    if faceless_mode != "ไม่ใช้ (ใช้วิดีโอต้นฉบับ)":
        scene_target_duration = st.slider("⏱️ ความยาวแต่ละฉาก (วินาที)", 4.0, 15.0, 8.0, 1.0)
        if faceless_mode == "📂 Custom B-Roll (อัปโหลดมาเรียงเอง)": 
            custom_videos = st.file_uploader("📂 อัปโหลดคลิป B-Roll (MP4)", type=["mp4"], accept_multiple_files=True)
            
    if uploaded_file and st.button("🎧 ขั้นตอนที่ 1: ถอดเสียงและเตรียมสคริปต์", use_container_width=True, type="secondary"):
        with st.spinner("กำลังถอดเสียงและวิเคราะห์ข้อความ..."):
            file_ext = uploaded_file.name.split('.')[-1].lower()
            raw_path = f"raw_upload.{file_ext}"
            with open(raw_path, "wb") as f: f.write(uploaded_file.getbuffer())
            st.session_state.m1_video_path = raw_path

            if file_ext == "mp3": shutil.copy(raw_path, "audio.mp3")
            elif file_ext == "wav": subprocess.run([FFMPEG_CMD, '-y', '-i', raw_path, '-c:a', 'libmp3lame', 'audio.mp3'], check=True)
            else: subprocess.run([FFMPEG_CMD, '-y', '-i', raw_path, '-vn', '-c:a', 'libmp3lame', 'audio.mp3'], check=True)

            with open("audio.mp3", "rb") as audio_file:
                res_th = client.audio.transcriptions.create(model="whisper-large-v3", file=("audio.mp3", audio_file), response_format="verbose_json", language="th", temperature=0.0)
            
            raw_segments = [{"start": seg['start'] if isinstance(seg, dict) else seg.start, "end": seg['end'] if isinstance(seg, dict) else seg.end, "text": seg['text'].strip() if isinstance(seg, dict) else seg.text.strip()} for seg in res_th.segments if (seg['text'].strip() if isinstance(seg, dict) else seg.text.strip())]
            raw_segments = clean_whisper_segments(raw_segments)
            
            is_proof = st.session_state.get("mode1_ai_proof", True)
            user_rep = st.session_state.get("mode1_replace", "")
            if is_proof:
                with st.spinner("🧠 กำลังให้ AI ตรวจทานคำผิด..."):
                    raw_segments = ai_proofread_segments(client, raw_segments, user_rep)
            
            st.session_state.m1_segments = raw_segments
            st.success("✅ เตรียมสคริปต์เสร็จแล้ว! เชิญตรวจสอบด้านล่าง")

    if st.session_state.m1_segments:
        st.markdown("---")
        st.markdown("### 2️⃣ ตรวจสอบและแก้ไขซับไตเติล (Interactive Editor)")
        
        with st.form("m1_editor_form"):
            edited_segments = st.data_editor(
                st.session_state.m1_segments,
                column_config={
                    "start": st.column_config.NumberColumn("เวลาเริ่ม (วิ)", format="%.2f"),
                    "end": st.column_config.NumberColumn("เวลาจบ (วิ)", format="%.2f"),
                    "text": "ข้อความซับไตเติล"
                },
                num_rows="dynamic", use_container_width=True, key="m1_editor"
            )
            submit_edits_m1 = st.form_submit_button("💾 ยืนยันการแก้ไขซับไตเติล (Save Edits)")
            if submit_edits_m1:
                st.session_state.m1_segments = edited_segments
                st.success("✅ บันทึกข้อความล่าสุดแล้ว!")

        st.markdown("### 3️⃣ ปรับแต่งดีไซน์ซับไตเติล")
        sub_config = render_subtitle_ui("mode1")

        st.markdown("### 4️⃣ เรนเดอร์และพรีวิวงาน")
        if st.button("🎬 ขั้นตอนที่ 2: สร้างพรีวิววิดีโอ", use_container_width=True, type="primary"):
            with st.spinner("กำลังประกอบร่างวิดีโอ..."):
                video_to_process = st.session_state.m1_video_path
                segments_to_process = st.session_state.m1_segments
                orig_dur_process = get_video_duration(video_to_process)
                
                if faceless_mode == "ไม่ใช้ (ใช้วิดีโอต้นฉบับ)" and sub_config["auto_cut"] == "เปิด (ตัดช่วงเงียบอัตโนมัติ)":
                    merged_times = []
                    for seg in segments_to_process:
                        s_cut, e_cut = max(0.0, seg['start'] - 0.15), min(orig_dur_process, seg['end'] + 0.15) if orig_dur_process > 0 else seg['end'] + 0.15
                        if not merged_times: merged_times.append({'start': s_cut, 'end': e_cut, 'segments': [seg]})
                        else:
                            if s_cut <= merged_times[-1]['end']: 
                                merged_times[-1]['end'] = max(merged_times[-1]['end'], e_cut)
                                merged_times[-1]['segments'].append(seg)
                            else: merged_times.append({'start': s_cut, 'end': e_cut, 'segments': [seg]})
                    if merged_times and orig_dur_process > 0 and orig_dur_process - merged_times[-1]['end'] <= 4.0: merged_times[-1]['end'] = orig_dur_process
                    if merged_times:
                        filter_complex, concat_inputs = "", ""
                        for i, b in enumerate(merged_times):
                            filter_complex += f"[0:v]trim=start={b['start']}:end={b['end']},setpts=PTS-STARTPTS[v{i}];[0:a]atrim=start={b['start']}:end={b['end']},asetpts=PTS-STARTPTS[a{i}];"
                            concat_inputs += f"[v{i}][a{i}]"
                        filter_complex += f"{concat_inputs}concat=n={len(merged_times)}:v=1:a=1[outv][outa]"
                        subprocess.run([FFMPEG_CMD, '-y', '-i', video_to_process, '-filter_complex', filter_complex, '-map', '[outv]', '-map', '[outa]', '-c:v', 'libx264', '-crf', '18', '-preset', 'fast', '-c:a', 'aac', '-b:a', '256k', 'jumpcut.mp4'], check=True)
                        video_to_process = "jumpcut.mp4"
                        segments_to_process, current_new_time = [], 0.0
                        for block in merged_times:
                            for seg in block['segments']: segments_to_process.append({'start': current_new_time + max(0.0, seg['start'] - block['start']), 'end': current_new_time + min(block['end'] - block['start'], seg['end'] - block['start']), 'text': seg['text']})
                            current_new_time += block['end'] - block['start']

                video_width, video_height = (720, 1280) if faceless_mode != "ไม่ใช้ (ใช้วิดีโอต้นฉบับ)" else get_video_dimensions(video_to_process)
                actual_font_file = FONT_MAP[sub_config["font"]]
                actual_pil_font_size, allowed_pixel_width = int((sub_config["size"] / 288) * video_height * 0.75), video_width * (sub_config["max_w"] / 100)
                ass_font_size, ass_outline, ass_margin_v = int(sub_config["size"] * (video_height / 288.0)), int(sub_config["outline"] * (video_height / 288.0)), int(sub_config["margin_v"] * (video_height / 288.0))
                
                effect_prefix = ""
                if sub_config["anim"] == "เด้งพอง (Pop-up)": effect_prefix = f"{{\\fscx{sub_config['pop_scale']}\\fscy{sub_config['pop_scale']}\\t(0,{sub_config['pop_dur']},\\fscx100\\fscy100)}}"
                elif sub_config["anim"] == "ค่อยๆ ปรากฏ (Fade-in)": effect_prefix = f"{{\\fad({sub_config['fade_dur']},0)}}"
                
                ass_content = f"""[Script Info]\nScriptType: v4.00+\nPlayResX: {video_width}\nPlayResY: {video_height}\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Default,{sub_config["font"]},{ass_font_size},{hex_to_ass_color(sub_config["t_color"])},&H0000FFFF,{hex_to_ass_color(sub_config["o_color"])},&H80000000,0,0,0,0,100,100,0,0,{3 if sub_config["bg_style"] == "แถบกล่องดำรองหลัง" else 1},{ass_outline},0,2,10,10,{ass_margin_v},1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"""
                
                segments_data_for_subs, scenes, current_scene, s_start, s_idx = [], [], "", 0.0, 1
                for seg in segments_to_process:
                    s, e, t = seg['start'], seg['end'], seg['text']
                    
                    # 🌟 1. แทนที่คำทับศัพท์ก่อนจัดระเบียบสระ
                    for old_w, new_w in sub_config["replacements"].items(): t = re.sub(re.escape(old_w), new_w, t, flags=re.IGNORECASE)
                    
                    # 🌟 2. เรียกใช้งาน PUA Engine จัดระเบียบสระให้ชูคอ/หลบซ้าย
                    t = fix_thai_floating_vowels(t)
                        
                    segments_data_for_subs.append((t, s, e))
                    if current_scene == "": s_start = s
                    current_scene += t + " "
                    if (e - s_start) >= scene_target_duration: scenes.append({"idx": s_idx, "start": s_start, "end": e, "text": current_scene}); s_idx += 1; current_scene = ""
                if current_scene: scenes.append({"idx": s_idx, "start": s_start, "end": segments_to_process[-1]['end'], "text": current_scene})
                
                chunk_size = 2 if "2 บรรทัด" in sub_config["line_limit"] else (1 if "1 บรรทัด" in sub_config["line_limit"] else 0)
                
                for text_sub, start_time, end_time in segments_data_for_subs:
                    formatted_text = split_text_by_pixel_width(text_sub, actual_font_file, actual_pil_font_size, allowed_pixel_width)
                    lines = formatted_text.split('\n')
                    if chunk_size > 0 and len(lines) > chunk_size:
                        chunks = [ "\n".join(lines[j:j+chunk_size]) for j in range(0, len(lines), chunk_size) ]
                        t_start, total_chars = start_time, max(1, sum(len(c.replace('\n','')) for c in chunks))
                        for chunk in chunks:
                            t_end = t_start + ((end_time - start_time) * (len(chunk.replace('\n','')) / total_chars))
                            ass_content += f"Dialogue: 0,{format_ass_timestamp(t_start)},{format_ass_timestamp(t_end)},Default,,0,0,0,,{effect_prefix}{chunk.replace('\n', '\\N')}\n"
                            t_start = t_end
                    else: 
                        ass_content += f"Dialogue: 0,{format_ass_timestamp(start_time)},{format_ass_timestamp(end_time)},Default,,0,0,0,,{effect_prefix}{'\\N'.join(lines)}\n"
            
                with open("subs.ass", "w", encoding="utf-8") as f: f.write(ass_content)

                if faceless_mode != "ไม่ใช้ (ใช้วิดีโอต้นฉบับ)":
                    with open("concat.txt", "w") as f:
                        for i, sc in enumerate(scenes):
                            c_path, sc_dur = f"clip_{sc['idx']}.mp4", sc['end'] - sc['start']
                            if faceless_mode == "🤖 Pexels AI (ดึงภาพอัตโนมัติ)":
                                if fetch_pexels_video(get_action_keyword_from_ai(client, sc["text"]), pexels_key, "temp.mp4"): subprocess.run([FFMPEG_CMD, '-y', '-i', 'temp.mp4', '-ss', '0', '-t', str(sc_dur), '-vf', f'scale={video_width}:{video_height}:force_original_aspect_ratio=increase,crop={video_width}:{video_height}', '-c:v', 'libx264', '-crf', '18', '-preset', 'fast', '-an', c_path])
                                else: subprocess.run([FFMPEG_CMD, '-y', '-f', 'lavfi', '-i', f'color=c=black:s={video_width}x{video_height}:d={sc_dur}', '-c:v', 'libx264', '-crf', '18', '-preset', 'fast', c_path])
                            else:
                                subprocess.run([FFMPEG_CMD, '-y', '-i', f"custom_broll_{i % len(custom_videos)}.mp4", '-ss', '0', '-t', str(sc_dur), '-vf', f'scale={video_width}:{video_height}:force_original_aspect_ratio=increase,crop={video_width}:{video_height}', '-c:v', 'libx264', '-crf', '18', '-preset', 'fast', '-an', c_path])
                            f.write(f"file '{c_path}'\n")
                    subprocess.run([FFMPEG_CMD, '-y', '-f', 'concat', '-safe', '0', '-i', 'concat.txt', '-c:v', 'libx264', '-crf', '18', '-preset', 'fast', 'bg.mp4'])
                    subprocess.run([FFMPEG_CMD, '-y', '-i', 'bg.mp4', '-i', 'audio.mp3', '-vf', 'subtitles=subs.ass:fontsdir=.', '-c:v', 'libx264', '-crf', '18', '-preset', 'fast', '-c:a', 'aac', '-b:a', '256k', 'output.mp4'])
                else: 
                    subprocess.run([FFMPEG_CMD, '-y', '-i', video_to_process, '-vf', 'subtitles=subs.ass:fontsdir=.', '-c:v', 'libx264', '-crf', '18', '-preset', 'fast', '-c:a', 'aac', '-b:a', '256k', 'output.mp4'])

            st.success("🎉 เรนเดอร์เสร็จสมบูรณ์!")
            st.markdown("### 🖥️ พรีวิวผลลัพธ์")
            col_vid1, col_vid2, col_vid3 = st.columns([1, 1, 1])
            with col_vid2:
                st.video("output.mp4")
                with open("output.mp4", "rb") as f: 
                    st.download_button("📥 ดาวน์โหลดวิดีโอ", f, "faceless_output.mp4", "video/mp4", type="primary", use_container_width=True)

# =========================================================
# 🎞️ โหมด 2: ต่อคลิปและฝังซับ (Join Video & Sub)
# =========================================================
if "m2_segments" not in st.session_state: st.session_state.m2_segments = None

elif app_mode == "🎞️ โหมด 2: ต่อคลิปและฝังซับ (Join & Sub)":
    st.markdown("## 🎞️ สตูดิโอต่อคลิปพร้อมเสียง & ฝังซับ")
    st.markdown("---")
    
    st.markdown("### 1️⃣ อัปโหลดไฟล์วิดีโอ")
    uploaded_videos = st.file_uploader("📂 อัปโหลดวิดีโอที่ต้องการนำมาต่อกัน (MP4)", type=["mp4"], accept_multiple_files=True)
    
    if uploaded_videos and st.button("🎧 ขั้นตอนที่ 1: รวมคลิปและถอดเสียง", use_container_width=True, type="secondary"):
        with st.spinner("กำลังต่อคลิปวิดีโอและถอดเสียง..."):
            with open("concat_join.txt", "w", encoding="utf-8") as f:
                for i, vid in enumerate(uploaded_videos):
                    v_path = f"part_{i}.mp4"
                    with open(v_path, "wb") as f_vid: f_vid.write(vid.getbuffer())
                    f.write(f"file '{v_path}'\n")
            
            subprocess.run([FFMPEG_CMD, '-y', '-f', 'concat', '-safe', '0', '-i', 'concat_join.txt', '-c', 'copy', 'combined.mp4'], check=True)
            subprocess.run([FFMPEG_CMD, '-y', '-i', 'combined.mp4', '-vn', '-c:a', 'libmp3lame', 'audio_joined.mp3'], check=True)
            
            with open("audio_joined.mp3", "rb") as audio_file:
                res_th = client.audio.transcriptions.create(model="whisper-large-v3", file=("audio_joined.mp3", audio_file), response_format="verbose_json", language="th", temperature=0.0)
            
            raw_segments = [{"start": seg['start'] if isinstance(seg, dict) else seg.start, "end": seg['end'] if isinstance(seg, dict) else seg.end, "text": seg['text'].strip() if isinstance(seg, dict) else seg.text.strip()} for seg in res_th.segments if (seg['text'].strip() if isinstance(seg, dict) else seg.text.strip())]
            raw_segments = clean_whisper_segments(raw_segments)

            is_proof = st.session_state.get("mode2_ai_proof", True)
            user_rep = st.session_state.get("mode2_replace", "")
            if is_proof:
                with st.spinner("🧠 กำลังให้ AI ตรวจทานคำผิด..."):
                    raw_segments = ai_proofread_segments(client, raw_segments, user_rep)

            st.session_state.m2_segments = raw_segments
            st.success("✅ ถอดเสียงเสร็จแล้ว! ตรวจสอบด้านล่างได้เลย")

    if st.session_state.m2_segments:
        st.markdown("---")
        st.markdown("### 2️⃣ ตรวจสอบและแก้ไขซับไตเติล (Interactive Editor)")
        
        with st.form("m2_editor_form"):
            edited_segments = st.data_editor(
                st.session_state.m2_segments,
                column_config={
                    "start": st.column_config.NumberColumn("เวลาเริ่ม (วิ)", format="%.2f"),
                    "end": st.column_config.NumberColumn("เวลาจบ (วิ)", format="%.2f"),
                    "text": "ข้อความซับไตเติล"
                },
                num_rows="dynamic", use_container_width=True, key="m2_editor"
            )
            submit_edits_m2 = st.form_submit_button("💾 ยืนยันการแก้ไขซับไตเติล (Save Edits)")
            if submit_edits_m2:
                st.session_state.m2_segments = edited_segments
                st.success("✅ บันทึกข้อความล่าสุดแล้ว!")

        st.markdown("### 3️⃣ ปรับแต่งดีไซน์ซับไตเติล")
        sub_config = render_subtitle_ui("mode2")

        st.markdown("### 4️⃣ เรนเดอร์และพรีวิวงาน")
        if st.button("🎬 ขั้นตอนที่ 2: สร้างพรีวิววิดีโอ", use_container_width=True, type="primary"):
            with st.spinner("กำลังฝังซับไตเติล..."):
                video_to_process = "combined.mp4"
                segments_to_process = st.session_state.m2_segments
                orig_dur_process = get_video_duration(video_to_process)
                
                if sub_config["auto_cut"] == "เปิด (ตัดช่วงเงียบอัตโนมัติ)":
                    merged_times = []
                    for seg in segments_to_process:
                        s_cut, e_cut = max(0.0, seg['start'] - 0.15), min(orig_dur_process, seg['end'] + 0.15) if orig_dur_process > 0 else seg['end'] + 0.15
                        if not merged_times: merged_times.append({'start': s_cut, 'end': e_cut, 'segments': [seg]})
                        else:
                            if s_cut <= merged_times[-1]['end']: 
                                merged_times[-1]['end'] = max(merged_times[-1]['end'], e_cut)
                                merged_times[-1]['segments'].append(seg)
                            else: merged_times.append({'start': s_cut, 'end': e_cut, 'segments': [seg]})
                    if merged_times and orig_dur_process > 0 and orig_dur_process - merged_times[-1]['end'] <= 4.0: merged_times[-1]['end'] = orig_dur_process
                    if merged_times:
                        filter_complex, concat_inputs = "", ""
                        for i, b in enumerate(merged_times):
                            filter_complex += f"[0:v]trim=start={b['start']}:end={b['end']},setpts=PTS-STARTPTS[v{i}];[0:a]atrim=start={b['start']}:end={b['end']},asetpts=PTS-STARTPTS[a{i}];"
                            concat_inputs += f"[v{i}][a{i}]"
                        filter_complex += f"{concat_inputs}concat=n={len(merged_times)}:v=1:a=1[outv][outa]"
                        subprocess.run([FFMPEG_CMD, '-y', '-i', video_to_process, '-filter_complex', filter_complex, '-map', '[outv]', '-map', '[outa]', '-c:v', 'libx264', '-crf', '18', '-preset', 'fast', '-c:a', 'aac', '-b:a', '256k', 'jumpcut.mp4'], check=True)
                        video_to_process = "jumpcut.mp4"
                        segments_to_process, current_new_time = [], 0.0
                        for block in merged_times:
                            for seg in block['segments']: segments_to_process.append({'start': current_new_time + max(0.0, seg['start'] - block['start']), 'end': current_new_time + min(block['end'] - block['start'], seg['end'] - block['start']), 'text': seg['text']})
                            current_new_time += block['end'] - block['start']

                v_w, v_h = get_video_dimensions(video_to_process)
                actual_font_file = FONT_MAP[sub_config["font"]]
                actual_pil_font_size, allowed_pixel_width = int((sub_config["size"] / 288) * v_h * 0.75), v_w * (sub_config["max_w"] / 100)
                ass_font_size, ass_outline, ass_margin_v = int(sub_config["size"] * (v_h / 288.0)), int(sub_config["outline"] * (v_h / 288.0)), int(sub_config["margin_v"] * (v_h / 288.0))
                
                effect_prefix = ""
                if sub_config["anim"] == "เด้งพอง (Pop-up)": effect_prefix = f"{{\\fscx{sub_config['pop_scale']}\\fscy{sub_config['pop_scale']}\\t(0,{sub_config['pop_dur']}\\fscx100\\fscy100)}}"
                elif sub_config["anim"] == "ค่อยๆ ปรากฏ (Fade-in)": effect_prefix = f"{{\\fad({sub_config['fade_dur']},0)}}"
                
                ass = f"""[Script Info]\nScriptType: v4.00+\nPlayResX: {v_w}\nPlayResY: {v_h}\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Default,{sub_config["font"]},{ass_font_size},{hex_to_ass_color(sub_config["t_color"])},&H0000FFFF,{hex_to_ass_color(sub_config["o_color"])},&H80000000,0,0,0,0,100,100,0,0,{3 if sub_config["bg_style"] == "แถบกล่องดำรองหลัง" else 1},{ass_outline},0,2,10,10,{ass_margin_v},1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"""
                
                chunk_size = 2 if "2 บรรทัด" in sub_config["line_limit"] else (1 if "1 บรรทัด" in sub_config["line_limit"] else 0)
                for seg in segments_to_process:
                    t = seg['text']
                    
                    # 🌟 1. แทนที่คำทับศัพท์
                    for old_w, new_w in sub_config["replacements"].items(): t = re.sub(re.escape(old_w), new_w, t, flags=re.IGNORECASE)
                    
                    # 🌟 2. เรียกใช้งาน PUA Engine 
                    t = fix_thai_floating_vowels(t)
                    
                    formatted_text = split_text_by_pixel_width(t, actual_font_file, actual_pil_font_size, allowed_pixel_width)
                    lines = formatted_text.split('\n')
                    if chunk_size > 0 and len(lines) > chunk_size:
                        chunks = [ "\n".join(lines[j:j+chunk_size]) for j in range(0, len(lines), chunk_size) ]
                        t_start, total_chars = seg['start'], max(1, sum(len(c.replace('\n','')) for c in chunks))
                        for chunk in chunks:
                            t_end = t_start + ((seg['end'] - seg['start']) * (len(chunk.replace('\n','')) / total_chars))
                            ass += f"Dialogue: 0,{format_ass_timestamp(t_start)},{format_ass_timestamp(t_end)},Default,,0,0,0,,{effect_prefix}{chunk.replace('\n', '\\N')}\n"
                            t_start = t_end
                    else: 
                        ass += f"Dialogue: 0,{format_ass_timestamp(seg['start'])},{format_ass_timestamp(seg['end'])},Default,,0,0,0,,{effect_prefix}{'\\N'.join(lines)}\n"
                
                with open("subs_joined.ass", "w", encoding="utf-8") as f: f.write(ass)
                subprocess.run([FFMPEG_CMD, '-y', '-i', video_to_process, '-vf', 'subtitles=subs_joined.ass:fontsdir=.', '-c:v', 'libx264', '-crf', '18', '-preset', 'fast', '-c:a', 'aac', '-b:a', '256k', 'output_joined.mp4'])
                
            st.success("🎉 เรนเดอร์เสร็จสมบูรณ์!")
            st.markdown("### 🖥️ พรีวิวผลลัพธ์")
            col_vid1, col_vid2, col_vid3 = st.columns([1, 1, 1])
            with col_vid2:
                st.video("output_joined.mp4")
                with open("output_joined.mp4", "rb") as f: 
                    st.download_button("📥 ดาวน์โหลดวิดีโอ", f, "joined_video_with_subs.mp4", "video/mp4", type="primary", use_container_width=True)
