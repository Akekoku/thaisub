import streamlit as st
from groq import Groq
import subprocess
import os
import re
import shutil
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

def cut_dead_air(input_file, output_file, silence_thresh="-35dB", silence_duration=0.5):
    st.info("🔍 ขั้นตอน AI ตัดต่อ: กำลังสแกนหาช่วงเวลา Dead Air ในวิดีโอ...")
    cmd_detect = [
        'ffmpeg', '-i', input_file,
        '-af', f'silencedetect=noise={silence_thresh}:d={silence_duration}',
        '-f', 'null', '-'
    ]
    result = subprocess.run(cmd_detect, stderr=subprocess.PIPE, text=True)
    starts = re.findall(r'silence_start: ([\d\.]+)', result.stderr)
    ends = re.findall(r'silence_end: ([\d\.]+)', result.stderr)

    if not starts:
        st.success("✅ ไม่พบช่วง Dead Air เลยครับ ส่งผ่านไฟล์ต้นฉบับไปทำซับไตเติลต่อได้เลย")
        shutil.copy(input_file, output_file)
        return

    duration_cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', input_file]
    duration_res = subprocess.run(duration_cmd, capture_output=True, text=True)
    total_duration = float(duration_res.stdout.strip())
    keep_segments = []
    current_time = 0.0

    for i in range(len(starts)):
        start = float(starts[i])
        end = float(ends[i]) if i < len(ends) else total_duration
        if start > current_time:
            pad_start = current_time
            pad_end = start + 0.1 if start + 0.1 < total_duration else start
            keep_segments.append((pad_start, pad_end))
        current_time = end - 0.1 if end - 0.1 > 0 else end

    if current_time < total_duration:
        keep_segments.append((current_time, total_duration))

    filter_str = ""
    concat_inputs = ""
    for i, (start, end) in enumerate(keep_segments):
        filter_str += f"[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS[v{i}]; "
        filter_str += f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS[a{i}]; "
        concat_inputs += f"[v{i}][a{i}]"

    filter_str += f"{concat_inputs}concat=n={len(keep_segments)}:v=1:a=1[outv][outa]"
    cmd_run = [
        'ffmpeg', '-y', '-i', input_file,
        '-filter_complex', filter_str,
        '-map', '[outv]', '-map', '[outa]',
        '-c:v', 'libx264', '-crf', '17', '-preset', 'fast',
        output_file
    ]
    subprocess.run(cmd_run, check=True)
    st.success("✨ ตัดช่วงเงียบสำเร็จ ได้ไฟล์วิดีโอ Rough Cut ที่กระชับแล้ว!")

st.set_page_config(page_title="AI Auto-Edit & Subtitle Pro", page_icon="🎬")
st.markdown("## 🎬 ระบบ AI ตัดต่ออัตโนมัติ & ฝังซับ (Pro)")

if "GROQ_API_KEY" in st.secrets:
    api_key = st.secrets["GROQ_API_KEY"]
else:
    st.error("❌ ยังไม่ได้ตั้งค่าล็อก API Key ในระบบ Secrets")
    st.stop()

st.markdown("### ✂️ ระบบ AI ตัดต่ออัตโนมัติ (Rough Cut)")
enable_dead_air = st.toggle("🔇 เปิดระบบตรวจจับและตัดช่วงเงียบ (Dead Air Removal)", value=False)
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

st.markdown("### 🌐 เลือกภาษาของซับไตเติล")
sub_language = st.radio(
    "ระบบ AI ต้องการให้ฝังซับไตเติลเป็นภาษาอะไร?",
    ["🇹🇭 ภาษาไทย (ถอดจากเสียงพูดต้นฉบับ)", "🇬🇧 ภาษาอังกฤษ (แปลอัตโนมัติจากเสียงพูด)"],
    horizontal=True
)

# =========================================================
# 🌟 เมนูใหม่: ระบบพากย์เสียงอินเตอร์ (Auto-Dubbing)
# =========================================================
enable_dubbing = False
if "ภาษาอังกฤษ" in sub_language:
    st.markdown("### 🎙️ ระบบพากย์เสียงอัตโนมัติ (Auto-Dubbing)")
    enable_dubbing = st.toggle("🎧 เปิดใช้งานเสียงพากย์ AI ฝรั่ง (แทนที่เสียงต้นฉบับ)", value=False)
    if enable_dubbing:
        st.caption("✨ ระบบจะนำข้อความที่แปลแล้ว ไปสร้างเสียงมนุษย์ AI และฝังลงในคลิปแทนเสียงเดิม")

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
    elif anim_choice == "ค่อยๆ ปรากฏ (Soft Fade-in)":
        fade_duration = st.slider("⏱️ ความเร็วเฟดอิน (มิลลิวินาที)", min_value=50, max_value=500, value=200, step=10)

    col1, col2 = st.columns(2)
    with col1:
        font_size_choice = st.slider("📏 ขนาดตัวอักษร (FontSize):", min_value=14, max_value=40, value=18)
        outline_thickness = st.slider("✏️ ความหนาขอบ:", min_value=0, max_value=5, value=1)
    with col2:
        max_width_pct = st.slider("🎯 ความกว้างกรอบข้อความ (% ของจอ):", min_value=50, max_value=150, value=100)
        margin_v_choice = st.slider("🔼 ระดับความสูงจากขอบล่าง:", min_value=20, max_value=200, value=50)

    force_max_2_lines = st.checkbox("🚫 บังคับซับไตเติลไม่ให้เกิน 2 บรรทัด (Smart Line Splitting)", value=True)

uploaded_file = st.file_uploader("📂 เลือกไฟล์วีดีโอ (MP4)", type=["mp4"])

if uploaded_file and api_key:
    if st.button("🚀 เริ่มกระบวนการ AI ตัดต่อและฝังซับ"):
        client = Groq(api_key=api_key)
        
        with st.spinner("กำลังอัปโหลดและเตรียมไฟล์ต้นฉบับ..."):
            with open("raw_upload.mp4", "wb") as f:
                f.write(uploaded_file.getbuffer())
        
        if enable_dead_air:
            cut_dead_air("raw_upload.mp4", "input.mp4", silence_thresh, silence_duration)
        else:
            shutil.copy("raw_upload.mp4", "input.mp4")
        
        video_width, video_height = get_video_dimensions("input.mp4")
        allowed_pixel_width = video_width * (max_width_pct / 100)
        actual_pil_font_size = int((font_size_choice / 288) * video_height * 0.75)
        
        st.info("🎵 กำลังสกัดไฟล์เสียงเพื่อส่งให้ AI...")
        try:
            if os.path.exists("audio.mp3"): os.remove("audio.mp3")
            subprocess.run(['ffmpeg', '-y', '-i', 'input.mp4', '-vn', '-c:a', 'libmp3lame', '-b:a', '64k', 'audio.mp3'], check=True)
        except subprocess.CalledProcessError:
            st.error("เกิดข้อผิดพลาดในการสกัดไฟล์เสียง")
            st.stop()

        st.info(f"🎙️ กำลังให้ AI ประมวลผลและทำความสะอาดซับไตเติล...")
        try:
            with open("audio.mp3", "rb") as audio_file:
                if "ภาษาไทย" in sub_language:
                    response = client.audio.transcriptions.create(
                        model="whisper-large-v3", file=("audio.mp3", audio_file), response_format="verbose_json", language="th"
                    )
                else:
                    response = client.audio.translations.create(
                        model="whisper-large-v3", file=("audio.mp3", audio_file), response_format="verbose_json"
                    )
            
            primary_color_ass = hex_to_ass_color(text_color)
            outline_color_ass = hex_to_ass_color(outline_color)
            border_style = "1" if bg_style == "ขอบปกติ (Outline)" else "3"
            back_color_ass = hex_to_ass_color("#000000", alpha_hex="40") if border_style == "3" else "&H00000000"
            scale_factor = video_height / 288.0
            ass_font_size = int(font_size_choice * scale_factor)
            ass_outline = int(outline_thickness * scale_factor)
            ass_margin_v = int(margin_v_choice * scale_factor)
            
            ass_content = f"""[Script Info]\nScriptType: v4.00+\nPlayResX: {video_width}\nPlayResY: {video_height}\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Default,{font_choice},{ass_font_size},{primary_color_ass},&H0000FFFF,{outline_color_ass},{back_color_ass},0,0,0,0,100,100,0,0,{border_style},{ass_outline},0,2,10,10,{ass_margin_v},1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"""
            actual_font_file = FONT_MAP[font_choice]
            
            full_translated_text = "" # ตัวแปรเก็บข้อความไว้ให้ AI พากย์

            for i, segment in enumerate(response.segments, start=1):
                start_time = segment['start'] if isinstance(segment, dict) else getattr(segment, 'start')
                end_time = segment['end'] if isinstance(segment, dict) else getattr(segment, 'end')
                text = segment['text'] if isinstance(segment, dict) else getattr(segment, 'text')
                
                clean_text = text.strip()
                if enable_filler_removal and "ภาษาไทย" in sub_language:
                    for filler in filler_words_list:
                        clean_text = re.sub(rf'\b{filler}\b', '', clean_text)
                        clean_text = clean_text.replace(filler, '')
                    clean_text = " ".join(clean_text.split())
                if not clean_text: continue
                
                # เก็บข้อความสำหรับพากย์
                full_translated_text += clean_text + " "

                formatted_text = split_text_by_pixel_width(clean_text, font_file=actual_font_file, pil_font_size=actual_pil_font_size, max_width_pixels=allowed_pixel_width)
                lines = formatted_text.split('\n')
                
                if force_max_2_lines and len(lines) > 2:
                    chunks = []
                    for j in range(0, len(lines), 2): chunks.append("\n".join(lines[j:j+2]))
                    total_chars = sum(len(c.replace('\n', '')) for c in chunks)
                    if total_chars == 0: total_chars = 1
                    current_start, total_duration = start_time, end_time - start_time
                    for chunk in chunks:
                        chunk_len = len(chunk.replace('\n', ''))
                        chunk_duration = total_duration * (chunk_len / total_chars)
                        current_end = current_start + chunk_duration
                        formatted_text_ass = chunk.replace("\n", "\\N")
                        anim_tag = ""
                        if anim_choice == "เด้งพอง (Pop-up Punch)": anim_tag = f"{{\\fscx{pop_scale}\\fscy{pop_scale}\\t(0,{pop_duration},\\fscx100\\fscy100)}}"
                        elif anim_choice == "ค่อยๆ ปรากฏ (Soft Fade-in)": anim_tag = f"{{\\fad({fade_duration},0)}}"
                        if anim_tag: formatted_text_ass = f"{anim_tag}{formatted_text_ass}"
                        ass_content += f"Dialogue: 0,{format_ass_timestamp(current_start)},{format_ass_timestamp(current_end)},Default,,0,0,0,,{formatted_text_ass}\n"
                        current_start = current_end
                else:
                    formatted_text_ass = formatted_text.replace("\n", "\\N")
                    anim_tag = ""
                    if anim_choice == "เด้งพอง (Pop-up Punch)": anim_tag = f"{{\\fscx{pop_scale}\\fscy{pop_scale}\\t(0,{pop_duration},\\fscx100\\fscy100)}}"
                    elif anim_choice == "ค่อยๆ ปรากฏ (Soft Fade-in)": anim_tag = f"{{\\fad({fade_duration},0)}}"
                    if anim_tag: formatted_text_ass = f"{anim_tag}{formatted_text_ass}"
                    ass_content += f"Dialogue: 0,{format_ass_timestamp(start_time)},{format_ass_timestamp(end_time)},Default,,0,0,0,,{formatted_text_ass}\n"
            
            with open("subs.ass", "w", encoding="utf-8") as f:
                f.write(ass_content)
            st.success("สร้างไฟล์ซับไตเติลสำเร็จ!")
            
            # =========================================================
            # 🌟 ถ้าเปิด Auto-Dubbing ให้รันคำสั่งสร้างไฟล์เสียง
            # =========================================================
            if enable_dubbing and "ภาษาอังกฤษ" in sub_language:
                st.info("🗣️ กำลังให้ AI (Edge TTS) สร้างเสียงพากย์ภาษาอังกฤษ...")
                if os.path.exists("dubbed_audio.mp3"):
                    os.remove("dubbed_audio.mp3")
                # ใช้เสียงผู้ชายสำเนียงอเมริกันมาตรฐาน (GuyNeural)
                subprocess.run(['edge-tts', '--voice', 'en-US-GuyNeural', '--text', full_translated_text, '--write-media', 'dubbed_audio.mp3'], check=True)
                st.success("สร้างเสียงพากย์สำเร็จ!")

        except Exception as e:
            st.error(f"เกิดข้อผิดพลาด: {e}")
            st.stop()

        st.info("⚙️ ขั้นตอนสุดท้าย: กำลังเรนเดอร์วิดีโอ Final...")
        try:
            if os.path.exists("output.mp4"): os.remove("output.mp4")
            
            # 🌟 เช็กว่าต้องใส่เสียงพากย์ใหม่ หรือใช้เสียงเดิม
            cmd = ['ffmpeg', '-y', '-i', 'input.mp4']
            
            if enable_dubbing and "ภาษาอังกฤษ" in sub_language and os.path.exists("dubbed_audio.mp3"):
                # ดึงวิดีโอจากไฟล์ที่ 1 และดึงเสียงจากไฟล์ที่ 2 (dubbed_audio)
                cmd.extend(['-i', 'dubbed_audio.mp3'])
                cmd.extend([
                    '-vf', "subtitles=subs.ass:fontsdir=.", 
                    '-c:v', 'libx264', '-crf', '17', '-preset', 'slow', 
                    '-c:a', 'aac', 
                    '-map', '0:v:0', '-map', '1:a:0', # 👈 สลับ Track เสียงตรงนี้
                    'output.mp4'
                ])
            else:
                # เคสปกติ ใช้เสียงต้นฉบับ
                cmd.extend([
                    '-vf', "subtitles=subs.ass:fontsdir=.", 
                    '-c:v', 'libx264', '-crf', '17', '-preset', 'slow', 
                    '-c:a', 'copy', 
                    'output.mp4'
                ])
            
            subprocess.run(cmd, check=True)
            st.success("🎉 อัตโนมัติเสร็จสมบูรณ์! ได้ไฟล์คลิปพร้อมลุยแล้วครับ")
            
            with open("output.mp4", "rb") as file:
                st.download_button(label="📥 ดาวน์โหลดวีดีโอ Final", data=file, file_name="video_final.mp4", mime="video/mp4")
                
        except subprocess.CalledProcessError:
            st.error("เกิดข้อผิดพลาดในการประมวลผลวีดีโอด้วย FFmpeg")
        finally:
            for temp_file in ["raw_upload.mp4", "input.mp4", "audio.mp3", "subs.ass", "dubbed_audio.mp3"]:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
