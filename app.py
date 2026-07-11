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
import json

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
    if os.path.exists(PROFILE_FILE):
        try:
            with open(PROFILE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: pass
    
    default_profiles = {
        "🎬 สไตล์ Tiktok (เด้งพอง ตัวเหลือง)": {
            "replace": "Save=เซฟ, OK=โอเค", "font": "Kanit Bold", "tc": "#FFFF00", "oc": "#000000",
            "bg": "ขอบปกติ", "anim": "เด้งพอง (Pop-up)", "ps": 130, "pd": 150, "fd": 200, 
            "fs": 22, "ot": 2, "mw": 90, "mv": 50, "ll": "🚫 บังคับ 1 บรรทัด", "ai_proof": True
        },
        "🎞️ สไตล์ Cinematic (เรียบหรู กล่องดำ)": {
            "replace": "Save=เซฟ", "font": "Sarabun", "tc": "#FFFFFF", "oc": "#000000",
            "bg": "แถบกล่องดำรองหลัง", "anim": "ค่อยๆ ปรากฏ (Fade-in)", "ps": 130, "pd": 150, "fd": 300, 
            "fs": 16, "ot": 0, "mw": 100, "mv": 30, "ll": "ไม่จำกัด (ตามความกว้าง)", "ai_proof": False
        },
        "🎀 สไตล์ Vlog (น่ารัก ฟอนต์ลายมือ)": {
            "replace": "Save=เซฟ", "font": "Mali", "tc": "#FF69B4", "oc": "#FFFFFF",
            "bg": "ขอบปกติ", "anim": "เด้งพอง (Pop-up)", "ps": 120, "pd": 200, "fd": 200, 
            "fs": 20, "ot": 2, "mw": 80, "mv": 40, "ll": "🚫 บังคับไม่เกิน 2 บรรทัด", "ai_proof": False
        }
    }
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
        res = client.chat.completions.create(messages=[{"role": "user", "content": prompt}], model="llama3-8b-8192", temperature=0.2)
        time.sleep(2.5) 
        return res.choices[0].message.content.strip().replace('"', '')
    except Exception:
        time.sleep(2.5)
        return random.choice(["cinematic landscape", "people walking", "vintage object"])

def fetch_pexels_video(keyword, pexels_key, output_path):
    headers = {"Authorization": pexels_key}
    url = f"[https://api.pexels.com/videos/search?query=](https://api.pexels.com/videos/search?query=){keyword}&orientation=portrait&per_page=15"
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

# 🌟 ฟังก์ชันอัปเกรด V.20: ทำความสะอาดข้อความขยะ + หน่วงเวลาป้องกันโดนบล็อค
def ai_proofread_segments(client, segments):
    chunk_size = 10
    success_all = True
    
    for i in range(0, len(segments), chunk_size):
        chunk = segments[i:i+chunk_size]
        
        # แปลงเป็น Array of Objects ที่มี id ชัดเจน
        data_to_fix = [{"id": str(idx), "text": seg["text"]} for idx, seg in enumerate(chunk)]
        
        prompt = f"""คุณคือผู้เชี่ยวชาญภาษาไทย หน้าที่คือแก้คำผิดจากการฟัง (เช่น รถ/ลด, หน้า/น่า) 
ห้ามเปลี่ยนความหมาย ห้ามรวมประโยค
คำสั่งบังคับ:
1. ตอบกลับเป็น JSON Object เท่านั้น
2. รูปแบบ JSON คือ {{"corrected": [{{"id": "0", "text": "ข้อความที่แก้แล้ว"}}, ...]}}
3. จำนวน object ต้องเท่ากับต้นฉบับเป๊ะ
        
ข้อความต้นฉบับ:
{json.dumps(data_to_fix, ensure_ascii=False)}"""
        
        try:
            res = client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama3-70b-8192", 
                temperature=0.0, 
                response_format={"type": "json_object"}
            )
            
            content = res.choices[0].message.content.strip()
            
            # ลอกคราบ markdown ขยะทิ้ง (ถ้ามี)
            if content.startswith("```json"): content = content[7:]
            if content.startswith("```"): content = content[3:]
            if content.endswith("
