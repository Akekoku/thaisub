import streamlit as st
from groq import Groq
import subprocess
import os
import re
import shutil
import asyncio
import edge_tts
import requests
from pythainlp.tokenize import word_tokenize
from PIL import ImageFont

FONT_MAP = {
    "Kanit": "Kanit-Regular.ttf",
    "Kanit Medium": "Kanit-Medium.ttf",
    "Kanit Bold": "Kanit-Bold.ttf",
    "Noto Sans Thai": "NotoSansThai-Regular.ttf",
    "Noto Sans Thai Medium": "NotoSansThai-Medium.ttf",
    "Noto Sans Thai Bold": "NotoSansThai-Bold.ttf",
    "Sarabun": "Sarabun.ttf",
    "Chonburi": "Chonburi.ttf",
    "Mali": "Mali.ttf"
}

# =========================================================
# 🔒 ระบบดักรหัสผ่านความปลอดภัยสูง (Gatekeeper Authentication)
# =========================================================
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if not st.session_state["authenticated"]:
    st.set_page_config(page_title="🔒กรุณาล็อกอิน", page_icon="🔑")
    st.markdown("## 🔐 ระบบภายในส่วนตัว (Restricted Access)")
    st.write("แอปพลิเคชันนี้จำกัดสิทธิ์การเข้าถึงเฉพาะเจ้าของบัญชีเท่านั้น")
    
    user_password = st.text_input("🔑 กรุณากรอกรหัสผ่านเพื่อเข้าใช้งาน:", type="password")
    
    if st.button("🔓 เข้าสู่ระบบ (Login)"):
        correct_password = st.secrets.get("APP_PASSWORD", "12345")
        if user_password == correct_password:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("❌ รหัสผ่านไม่ถูกต้อง! กรุณาตรวจสอบใหม่อีกครั้ง")
    st.stop()
# =========================================================

def hex_to_ass_color(hex_str, alpha_hex="00"):
    hex_str = hex_str.lstrip('#')
    r = hex_str[0:2]
    g = hex_str[2:4]
    b = hex_str[4:6]
    return f"&H{alpha_hex}{b}{g}{r}"

def format_ass_timestamp(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centis = int(round((seconds - int(seconds)) * 100))
    if centis == 100:
        secs += 1
        centis = 0
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"

def split_text_by_pixel_width(text, font_file, pil_font_size, max_width_pixels):
    try:
        font = ImageFont.truetype(font_file, pil_font_size)
    except Exception:
        return text
    words = word_tokenize(text, engine='newmm')
    lines = []
    current_line = ""
    for word in words:
        test_line = current_line + word
        if hasattr(font, 'getlength'):
            line_width = font.getlength(test_line)
        else:
            bbox = font.getbbox(test_line)
            line_width = bbox[2] - bbox[0] if bbox else 0
            
        if line_width > max_width_pixels and current_line:
            lines.append(current_line)
            current_line = word
        else:
            current_line = test_line
    if current_line:
        lines.append(current_line)
    return "\n".join(lines)

def get_video_dimensions(video_path):
    try:
        cmd = [
            'ffprobe', '-v', 'error', 
            '-select_streams', 'v:0', 
            '-show_entries', 'stream=width,height', 
            '-of', 'csv=s=x:p=0',
            video_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        width_str, height_str = result.stdout.strip().split('x')
        return int(width_str), int(height_str)
    except Exception:
        return 720, 1280

# ฟังก์ชันค้นหาและดาวน์โหลดคลิปจาก Pexels API
def fetch_pexels_video(keyword, pexels_key, output_path):
    headers = {"Authorization": pexels_key}
    url = f"https://api.pexels.com/videos/search?query={keyword}&orientation=portrait&per_page=1"
    try:
        res = requests.get(url, headers=headers, timeout=10).json()
        if res.get("videos"):
            video_files = res["videos"][0].get("video_files", [])
            # เลือกไฟล์วิดีโอที่เป็น mp4 และคุณภาพใกล้เคียง HD
            download_url = None
            for f in video_files:
                if f.get("file_type") == "video/mp4":
                    download_url = f.get("link")
                    if f.get("width") and f.get("width") >= 720:
                        break
            if download_url:
                v_res = requests.get(download_url, timeout=15)
                with open(output_path, "wb") as f:
                    f.write(v_res.content)
                return True
    except Exception:
        pass
    return False

# ฟังก์ชันให้ AI ช่วยคิดคีย์เวิร์ดภาษาอังกฤษจากข้อความภาษาไทย
def get_english_keyword_from_ai(client, thai_text):
    try:
        prompt = f"Extract exactly ONE or TWO English keywords representing this Thai text for searching stock video. Respond with only the keywords, no explanation, no punctuation. Text: '{thai_text}'"
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama3-8b-8192",
            temperature=0.3
        )
        return chat_completion.choices[0].message.content.strip().replace('"', '')
    except Exception:
        return "nature"

st.set_page_config(page_title="AI Auto-Edit & Subtitle Pro", page_icon="🎬")
st.markdown("## 🎬 ระบบ AI ตัดต่ออัตโนมัติ & ฝังซับ (Pro)")

if "GROQ_API_KEY" in st.secrets:
    api_key = st.secrets["GROQ_API_KEY"]
else:
    st.error("❌ ยังไม่ได้ตั้งค่าล็อก Groq API Key ในระบบ Secrets")
    st.stop()

pexels_key = st.secrets.get("PEXELS_API_KEY", "")

st.markdown("### ✂️ ระบบ AI ตัดต่ออัตโนมัติ (Rough Cut)")
enable_dead_air = st.toggle("🔇 เปิดระบบตรวจจับและตัดช่วงเงียบ (Dead Air Removal)", value=False)
silence_thresh = "-35dB"
silence_duration = 0.5
if enable_dead_air:
    col_d1, col_d2 = st.columns(2)
    with col_d1:
        silence_thresh_val = st.slider("ระดับเสียงที่ถือว่าเงียบ (dB)", min_value=-50, max_value=-10, value=-35, step=5)
        silence_thresh = f"{silence_thresh_val}dB"
    with col_d2:
        silence_duration = st.slider("ระยะเวลาเงียบขั้นต่ำ (วินาที)", min_value=0.2, max_value=2.0, value=0.5, step=0.1)

enable_filler_removal = st.toggle("🧹 เปิดระบบล้างคำฟุ่มเฟือยในซับไตเติล (Auto-Clean Text)", value=True)
if enable_filler_removal:
    filler_words_input = st.text_input("📝 กำหนดคำขยะที่ต้องการให้ AI ลบออก (คั่นด้วยลูกน้ำ)", value="เอ่อ, อ่า, อืม, แบบว่า, คือแบบ")
    filler_words_list = [w.strip() for w in filler_words_input.split(',') if w.strip()]

st.markdown("### 🎭 โหมดช่องไร้ใบหน้า (Faceless Automation)")
enable_faceless = st.toggle("🎬 เปิดโหมดสร้างภาพวิดีโอพื้นหลังอัตโนมัติจากคีย์เวิร์ด (Faceless Mode)", value=False)
if enable_faceless and not pexels_key:
    st.warning("⚠️ น้าต้องไปเพิ่มรหัส PEXELS_API_KEY ในระบบ Secrets ก่อนนะครับ ถึงจะรันโหมดนี้ได้")

st.markdown("### 🌐 เลือกภาษาของซับไตเติล")
sub_language = st.radio(
    "ระบบ AI ต้องการให้ฝังซับไตเติลเป็นภาษาอะไร?",
    ["🇹🇭 ภาษาไทย (ถอดจากเสียงพูดต้นฉบับ)", "🇬🇧 ภาษาอังกฤษ (แปลอัตโนมัติจากเสียงพูด)"],
    horizontal=True
)

enable_dubbing = False
selected_voice = "en-US-JennyNeural"
if "ภาษาอังกฤษ" in sub_language:
    st.markdown("### 🎙️ ระบบพากย์เสียงอัตโนมัติ (Auto-Dubbing V.2 Pro)")
    enable_dubbing = st.toggle("🎧 เปิดใช้งานเสียงพากย์ AI ฝรั่ง (วางตำแหน่งตรงตามจังหวะพูดเป๊ะ)", value=False)
    if enable_dubbing:
        voice_labels = {
            "👩 เสียงผู้หญิง - ร่าเริง สดใส ตลาดคลิปสั้น (Jenny)": "en-US-JennyNeural",
            "👩 เสียงผู้หญิง - นุ่มนวล น่าเชื่อถือ (Aria)": "en-US-AriaNeural",
            "👨 เสียงผู้ชาย - อบอุ่น เป็นธรรมชาติ (Guy)": "en-US-GuyNeural",
            "👨 เสียงผู้ชาย - เข้ม ทรงพลัง ดุดัน (Brian)": "en-US-BrianNeural"
        }
        voice_choice = st.selectbox("👤 เลือกสไตล์และเพศของนักพากย์ AI:", list(voice_labels.keys()), index=0)
        selected_voice = voice_labels[voice_choice]

st.markdown("### 🛠️ ปรับแต่งสไตล์ซับไตเติล")
with st.expander("คลิกเพื่อเปิดเครื่องมือปรับแต่งตัวอักษร สี และเอฟเฟกต์", expanded=True):
    font_choice = st.selectbox("✒️ เลือกรูปแบบฟอนต์ที่คุณต้องการ:", list(FONT_MAP.keys()), index=8)
    c1, c2, c3 = st.columns(3)
    with c1: text_color = st.color_picker("🅰️ สีตัวอักษร", "#FFFFFF")
    with c2: outline_color = st.color_picker("🖍️ สีของขอบตัวอักษร", "#000000")
    with c3: bg_style = st.selectbox("🔲 สไตล์พื้นหลัง", ["ขอบปกติ (Outline)", "แถบกล่องดำรองหลัง (Box)"])

    anim_choice = st.selectbox("🎬 เลือกรูปแบบเอฟเฟกต์สำหรับตัวหนังสือ:", ["ไม่มีเอฟเฟกต์ (นิ่งๆ/ค่าเริ่มต้น)", "เด้งพอง (Pop-up Punch)", "ค่อยๆ ปรากฏ (Soft Fade-in)"], index=0)
    pop_scale, pop_duration, fade_duration = 130, 150, 200
    if anim_choice == "เด้งพอง (Pop-up Punch)":
        col_anim1, col_anim2 = st.columns(2)
        with col_anim1: pop_scale = st.slider("📈 ความขยายตอนเด้งออก (%)", min_value=110, max_value=180, value=130, step=5)
        with col_anim2: pop_duration = st.slider("⏱️ ความเร็วยุบตัว (มิลลิวินาที)", min_value=50, max_value=400, value=150, step=10)

    col1, col2 = st.columns(2)
    with col1:
        font_size_choice = st.slider("📏 ขนาดตัวอักษร (FontSize):", min_value=14, max_value=40, value=18)
        outline_thickness = st.slider("✏️ ความหนาขอบ:", min_value=0, max_value=5, value=1)
    with col2:
        max_width_pct = st.slider("🎯 ความกว้างกรอบข้อความ (% ของจอ):", min_value=50, max_value=150, value=100)
        margin_v_choice = st.slider("🔼 ระดับความสูงจากขอบล่าง:", min_value=20, max_value=200, value=50)

    force_max_2_lines = st.checkbox("🚫 บังคับซับไตเติลไม่ให้เกิน 2 บรรทัด (Smart Line Splitting)", value=True)

uploaded_file = st.file_uploader("📂 เลือกไฟล์วีดีโอหรือไฟล์เสียง (MP4 / MP3)", type=["mp4", "mp3"])

if uploaded_file and api_key:
    if st.button("🚀 เริ่มกระบวนการโรงงาน AI อัตโนมัติ"):
        client = Groq(api_key=api_key)
        
        with st.spinner("กำลังอัปโหลดและเตรียมไฟล์ต้นฉบับ..."):
            file_ext = uploaded_file.name.split('.')[-1].lower()
            with open(f"raw_upload.{file_ext}", "wb") as f:
                f.write(uploaded_file.getbuffer())
        
        # จัดการสกัดเสียงออกมาก่อนไม่ว่าอินพุตจะเป็นอะไร
        st.info("🎵 กำลังประมวลผลไฟล์เสียง...")
        if os.path.exists("audio.mp3"): os.remove("audio.mp3")
        if file_ext == "mp3":
            shutil.copy("raw_upload.mp3", "audio.mp3")
        else:
            subprocess.run(['ffmpeg', '-y', '-i', 'raw_upload.mp4', '-vn', '-c:a', 'libmp3lame', '-b:a', '64k', 'audio.mp3'], check=True)

        st.info(f"🎙️ กำลังให้ AI ถอดความและสกัดคีย์เวิร์ด...")
        try:
            with open("audio.mp3", "rb") as audio_file:
                # บังคับถอดเป็นไทยก่อนเสมอเพื่อเอาเนื้อความไปสกัดคีย์เวิร์ดภาพประกอบ
                response_th = client.audio.transcriptions.create(
                    model="whisper-large-v3", file=("audio.mp3", audio_file), response_format="verbose_json", language="th"
                )
                
                # ถ้าเลือกซับอังกฤษ ให้โหลดแบบแปลเพิ่ม
                if "ภาษาอังกฤษ" in sub_language:
                    audio_file.seek(0)
                    response_sub = client.audio.translations.create(
                        model="whisper-large-v3", file=("audio.mp3", audio_file), response_format="verbose_json"
                    )
                else:
                    response_sub = response_th

            video_width, video_height = (720, 1280) if enable_faceless else get_video_dimensions("raw_upload.mp4")
            allowed_pixel_width = video_width * (max_width_pct / 100)
            actual_pil_font_size = int((font_size_choice / 288) * video_height * 0.75)
            
            ass_font_size = int(font_size_choice * (video_height / 288.0))
            ass_outline = int(outline_thickness * (video_height / 288.0))
            ass_margin_v = int(margin_v_choice * (video_height / 288.0))
            
            ass_content = f"""[Script Info]\nScriptType: v4.00+\nPlayResX: {video_width}\nPlayResY: {video_height}\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Default,{font_choice},{ass_font_size},{hex_to_ass_color(text_color)},&H0000FFFF,{hex_to_ass_color(outline_color)},&H00000000,0,0,0,0,100,100,0,0,1,{ass_outline},0,2,10,10,{ass_margin_v},1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"""
            actual_font_file = FONT_MAP[font_choice]
            
            segments_data = []
            
            # วนลูปเพื่อจัดการข้อความ คีย์เวิร์ด และดาวน์โหลดคลิปพื้นหลัง
            for idx, (seg_th, seg_sub) in enumerate(zip(response_th.segments, response_sub.segments), start=1):
                start_time = seg_sub['start'] if isinstance(seg_sub, dict) else getattr(seg_sub, 'start')
                end_time = seg_sub['end'] if isinstance(seg_sub, dict) else getattr(seg_sub, 'end')
                text_sub = seg_sub['text'].strip() if isinstance(seg_sub, dict) else getattr(seg_sub, 'text').strip()
                text_th = seg_th['text'].strip() if isinstance(seg_th, dict) else getattr(seg_th, 'text').strip()
                
                if not text_sub: continue
                duration = end_time - start_time
                if duration <= 0: duration = 1.0

                # เคสเปิดโหมด Faceless: ให้ AI หาคีย์เวิร์ด และไปโหลดคลิปมา
                bg_clip_path = "none"
                if enable_faceless and pexels_key:
                    kw = get_english_keyword_from_ai(client, text_th)
                    st.caption(f"🎬 ประโยคที่ {idx}: คีย์เวิร์ดภาพคือ '{kw}' -> กำลังดึงคลิป...")
                    raw_clip = f"raw_clip_{idx}.mp4"
                    processed_clip = f"clip_{idx}.mp4"
                    
                    if fetch_pexels_video(kw, pexels_key, raw_clip):
                        # ใช้ FFmpeg ตัดความยาว และสเกลคลิปให้เป็นแนวตั้งมาตรฐาน 720x1280
                        scale_cmd = [
                            'ffmpeg', '-y', '-i', raw_clip, '-ss', '0', '-t', str(duration),
                            '-vf', f'scale={video_width}:{video_height}:force_original_aspect_ratio=increase,crop={video_width}:{video_height},fps=30',
                            '-c:v', 'libx264', '-an', processed_clip
                        ]
                        subprocess.run(scale_cmd, capture_output=True)
                        if os.path.exists(processed_clip):
                            bg_clip_path = processed_clip
                    if os.path.exists(raw_clip): os.remove(raw_clip)

                segments_data.append((idx, text_sub, start_time, end_time, bg_clip_path))

                # จัดการสับซับไตเติล
                formatted_text = split_text_by_pixel_width(text_sub, font_file=actual_font_file, pil_font_size=actual_pil_font_size, max_width_pixels=allowed_pixel_width)
                lines = formatted_text.split('\n')
                if force_max_2_lines and len(lines) > 2:
                    chunks = [ "\n".join(lines[j:j+2]) for j in range(0, len(lines), 2) ]
                    t_start = start_time
                    total_chars = max(1, sum(len(c.replace('\n','')) for c in chunks))
                    for chunk in chunks:
                        c_dur = (end_time - start_time) * (len(chunk.replace('\n','')) / total_chars)
                        t_end = t_start + c_dur
                        ass_content += f"Dialogue: 0,{format_ass_timestamp(t_start)},{format_ass_timestamp(t_end)},Default,,0,0,0,,{chunk.replace('\n', '\\N')}\n"
                        t_start = t_end
                else:
                    ass_content += f"Dialogue: 0,{format_ass_timestamp(start_time)},{format_ass_timestamp(end_time)},Default,,0,0,0,,{formatted_text.replace('\n', '\\N')}\n"
            
            with open("subs.ass", "w", encoding="utf-8") as f:
                f.write(ass_content)

            # พากย์เสียง AI แยกประโยค (ถ้าเปิดไว้)
            if enable_dubbing and "ภาษาอังกฤษ" in sub_language:
                st.info("🗣️ กำลังเจนเสียงพากย์ AI ฝรั่งแยกตามจังหวะเวลา...")
                async def gen_dubs(data, voice):
                    for idx, text, _, _, _ in data:
                        if os.path.exists(f"seg_{idx}.mp3"): os.remove(f"seg_{idx}.mp3")
                        await edge_tts.Communicate(text, voice).save(f"seg_{idx}.mp3")
                asyncio.run(gen_dubs(segments_data, selected_voice))

        except Exception as e:
            st.error(f"เกิดข้อผิดพลาดในการประมวลผลข้อความ: {e}")
            st.stop()

        st.info("⚙️ ขั้นตอนสุดท้าย: กำลังประกอบร่างมิกซ์เสียงและภาพด้วย FFmpeg...")
        try:
            if os.path.exists("output.mp4"): os.remove("output.mp4")
            
            # --- แผนผสมภาพพื้นหลัง (สเตปแกนกลางของ Faceless) ---
            bg_video_track = "raw_upload.mp4" if file_ext == "mp4" else None
            
            if enable_faceless and pexels_key:
                # ตรวจสอบและสร้างคลิปทดแทนกรณีโหลดบางช่องไม่สำเร็จ
                for idx, _, start, end, path in segments_data:
                    if path == "none" or not os.path.exists(path):
                        dur = end - start
                        subprocess.run([
                            'ffmpeg', '-y', '-f', 'lavfi', '-i', f'color=c=black:s={video_width}x{video_height}:d={dur}:r=30',
                            '-c:v', 'libx264', f'clip_{idx}.mp4'
                        ], capture_output=True)
                
                # เขียนไฟล์ลิสต์เพื่อสั่ง Concat รวมวิดีโอพื้นหลังทุกชิ้นเข้าด้วยกัน
                with open("concat_list.txt", "w") as f:
                    for idx, _, _, _, _ in segments_data:
                        f.write(f"file 'clip_{idx}.mp4'\n")
                
                subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', 'concat_list.txt', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', 'bg_combined.mp4'], check=True)
                bg_video_track = "bg_combined.mp4"

            # --- แผนผสมเสียง (Audio Mixing) ---
            cmd = ['ffmpeg', '-y']
            if bg_video_track: cmd.extend(['-i', bg_video_track])
            else:
                # กรณีอัปโหลดเป็น MP3 และไม่ได้เปิด Faceless จะสร้างจอดำนิ่งๆ รองรับซับ
                cmd.extend(['-f', 'lavfi', '-i', f'color=c=black:s=720x1280:d={segments_data[-1][3]}:r=30'])
            
            if enable_dubbing and "ภาษาอังกฤษ" in sub_language:
                for idx, _, _, _, _ in segments_data:
                    cmd.extend(['-i', f"seg_{idx}.mp3"])
                
                filter_str = ""
                for idx, _, start, _, _ in segments_data:
                    delay_ms = int(start * 1000)
                    filter_str += f"[{idx}:a]adelay={delay_ms}|{delay_ms}[a{idx}]; "
                
                mix_inputs = "".join(f"[a{idx}]" for idx, _, _, _, _ in segments_data)
                filter_str += f"{mix_inputs}amix=inputs={len(segments_data)}:normalize=0[outa]; "
                filter_str += f"[0:v]subtitles=subs.ass:fontsdir=.[outv]"
                
                cmd.extend([
                    '-filter_complex', filter_str, '-map', '[outv]', '-map', '[outa]',
                    '-c:v', 'libx264', '-crf', '17', '-preset', 'slow', '-c:a', 'aac', 'output.mp4'
                ])
            else:
                # เคสไม่พากย์เสียง เอาเสียงพูดเดิมมาใส่คู่กับวิดีโอใหม่/เก่า
                cmd.extend(['-i', 'audio.mp3', '-vf', 'subtitles=subs.ass:fontsdir=.', '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'libx264', '-crf', '17', '-c:a', 'aac', 'output.mp4'])

            subprocess.run(cmd, check=True)
            st.success("🎉 โรงงาน AI ประกอบคลิป Faceless อัตโนมัติเสร็จสมบูรณ์!")
            
            with open("output.mp4", "rb") as file:
                st.download_button(label="📥 ดาวน์โหลดวิดีโอ Faceless ของน้า", data=file, file_name="faceless_final.mp4", mime="video/mp4")
                
        except subprocess.CalledProcessError as e:
            st.error(f"เกิดข้อผิดพลาดในการประกอบวิดีโอ: {e}")
        finally:
            # ล้างไฟล์ขยะหลังรันเสร็จ
            for f in ["raw_upload.mp4", "raw_upload.mp3", "audio.mp3", "subs.ass", "concat_list.txt", "bg_combined.mp4"]:
                if os.path.exists(f): os.remove(f)
            if 'segments_data' in locals():
                for idx, _, _, _, _ in segments_data:
                    if os.path.exists(f"clip_{idx}.mp4"): os.remove(f"clip_{idx}.mp4")
                    if os.path.exists(f"seg_{idx}.mp3"): os.remove(f"seg_{idx}.mp3")
