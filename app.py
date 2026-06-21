import streamlit as st
from groq import Groq
import subprocess
import os
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

st.set_page_config(page_title="AI Subtitle Kinetic Pro", page_icon="🎬")
st.markdown("### 🎬 ระบบฝังซับอัตโนมัติ (Kinetic Pro)")

if "GROQ_API_KEY" in st.secrets:
    api_key = st.secrets["GROQ_API_KEY"]
else:
    st.error("❌ ยังไม่ได้ตั้งค่าล็อก API Key ในระบบ Secrets")
    st.stop()

st.markdown("### 🌐 เลือกภาษาของซับไตเติล")
sub_language = st.radio(
    "ระบบ AI ต้องการให้ฝังซับไตเติลเป็นภาษาอะไร?",
    ["🇹🇭 ภาษาไทย (ถอดจากเสียงพูดต้นฉบับ)", "🇬🇧 ภาษาอังกฤษ (แปลอัตโนมัติจากเสียงพูด)"],
    horizontal=True
)

st.markdown("### 🛠️ ปรับแต่งสไตล์ซับไตเติล")
with st.expander("คลิกเพื่อเปิดเครื่องมือปรับแต่งตัวอักษร สี และเอฟเฟกต์ Kinetic", expanded=True):
    font_choice = st.selectbox("✒️ เลือกรูปแบบฟอนต์ที่คุณต้องการ:", list(FONT_MAP.keys()), index=8)
    
    st.markdown("#### 🎨 ปรับแต่งสีและสไตล์")
    c1, c2, c3 = st.columns(3)
    with c1:
        text_color = st.color_picker("🅰️ สีตัวอักษร", "#FFFFFF")
    with c2:
        outline_color = st.color_picker("🖍️ สีของขอบตัวอักษร", "#000000")
    with c3:
        bg_style = st.selectbox("🔲 สไตล์พื้นหลัง", ["ขอบปกติ (Outline)", "แถบกล่องดำรองหลัง (Box)"])

    st.markdown("#### 💥 เอฟเฟกต์การเคลื่อนไหว (Kinetic Animation)")
    # =========================================================
    # 🔒 จุดที่แก้ไข: เปลี่ยน value=True ให้เป็น value=False เพื่อปิดใช้งานเป็นค่าเริ่มต้น
    # =========================================================
    enable_pop = st.toggle("🔥 เปิดเอฟเฟกต์ตัวหนังสือเด้งพอง (Pop-up Punch)", value=False)
    if enable_pop:
        col_anim1, col_anim2 = st.columns(2)
        with col_anim1:
            pop_scale = st.slider("📈 ความขยายตอนเด้งออก (%)", min_value=110, max_value=180, value=130, step=5)
        with col_anim2:
            pop_duration = st.slider("⏱️ ความเร็วในการยุบตัวคืนรูป (มิลลิวินาที)", min_value=50, max_value=400, value=150, step=10)

    st.markdown("#### 📏 ปรับขนาดและตำแหน่ง")
    col1, col2 = st.columns(2)
    with col1:
        font_size_choice = st.slider("📏 ขนาดตัวอักษร (FontSize):", min_value=14, max_value=40, value=18)
        outline_thickness = st.slider("✏️ ความหนาของขอบ/แถบหลัง:", min_value=0, max_value=5, value=1)
    with col2:
        max_width_pct = st.slider("🎯 ความกว้างกรอบข้อความ (% ของจอ):", min_value=50, max_value=150, value=100)
        margin_v_choice = st.slider("🔼 ระดับความสูงของซับจากขอบล่าง (MarginV):", min_value=20, max_value=200, value=50)

uploaded_file = st.file_uploader("📂 เลือกไฟล์วีดีโอ (MP4)", type=["mp4"])

if uploaded_file and api_key:
    if st.button("🚀 เริ่มกระบวนการสร้างซับและฝังวีดีโอ"):
        client = Groq(api_key=api_key)
        
        with st.spinner("กำลังอัปโหลดและเตรียมไฟล์..."):
            with open("input.mp4", "wb") as f:
                f.write(uploaded_file.getbuffer())
        
        video_width, video_height = get_video_dimensions("input.mp4")
        allowed_pixel_width = video_width * (max_width_pct / 100)
        
        actual_pil_font_size = int((font_size_choice / 288) * video_height * 0.75)
        
        st.info(f"📹 วิดีโอขนาด {video_width}x{video_height}px | กางกรอบกว้าง {int(allowed_pixel_width)}px")
        
        st.info("🎵 กำลังสกัดเฉพาะไฟล์เสียงเพื่อลดขนาดไฟล์ก่อนส่งให้ AI...")
        try:
            if os.path.exists("audio.mp3"):
                os.remove("audio.mp3")
            subprocess.run(['ffmpeg', '-y', '-i', 'input.mp4', '-vn', '-c:a', 'libmp3lame', '-b:a', '64k', 'audio.mp3'], check=True)
        except subprocess.CalledProcessError:
            st.error("เกิดข้อผิดพลาดในการสกัดไฟล์เสียง")
            st.stop()

        st.info(f"🎙️ ขั้นตอนที่ 1: กำลังส่งเสียงให้ AI ประมวลผลเป็น {sub_language.split(' ')[1]}...")
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
            
            ass_content = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {video_width}
PlayResY: {video_height}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_choice},{ass_font_size},{primary_color_ass},&H0000FFFF,{outline_color_ass},{back_color_ass},0,0,0,0,100,100,0,0,{border_style},{ass_outline},0,2,10,10,{ass_margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
            actual_font_file = FONT_MAP[font_choice]
            
            for i, segment in enumerate(response.segments, start=1):
                start_time = segment['start'] if isinstance(segment, dict) else getattr(segment, 'start')
                end_time = segment['end'] if isinstance(segment, dict) else getattr(segment, 'end')
                text = segment['text'] if isinstance(segment, dict) else getattr(segment, 'text')
                
                formatted_text = split_text_by_pixel_width(
                    text.strip(), font_file=actual_font_file, pil_font_size=actual_pil_font_size, max_width_pixels=allowed_pixel_width
                )
                
                formatted_text_ass = formatted_text.replace("\n", "\\N")
                
                if enable_pop:
                    anim_tag = f"{{\\fscx{pop_scale}\\fscy{pop_scale}\\t(0,{pop_duration},\\fscx100\\fscy100)}}"
                    formatted_text_ass = f"{anim_tag}{formatted_text_ass}"
                
                start_str = format_ass_timestamp(start_time)
                end_str = format_ass_timestamp(end_time)
                
                ass_content += f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{formatted_text_ass}\n"
            
            with open("subs.ass", "w", encoding="utf-8") as f:
                f.write(ass_content)
            st.success("ประมวลผลเอฟเฟกต์เสียงและสร้างไฟล์ซับ Kinetic สำเร็จ!")
            
        except Exception as e:
            st.error(f"เกิดข้อผิดพลาดจาก Groq API: {e}")
            st.stop()

        st.info("⚙️ ขั้นตอนที่ 2: กำลังเรนเดอร์และฝังซับไตเติลเอฟเฟกต์ Kinetic ลงในวีดีโอ...")
        try:
            if os.path.exists("output.mp4"):
                os.remove("output.mp4")
                
            cmd = [
                'ffmpeg', '-y',
                '-i', 'input.mp4',
                '-vf', "subtitles=subs.ass:fontsdir=.",
                '-c:a', 'copy', 
                'output.mp4'
            ]
            
            subprocess.run(cmd, check=True)
            st.success("🎉 ฝังซับไตเติลระทึกใจสไตล์ภาพยนตร์เรียบร้อยแล้ว!")
            
            with open("output.mp4", "rb") as file:
                st.download_button(label="📥 ดาวน์โหลดวีดีโอพร้อมซับไตเติล", data=file, file_name="video_kinetic_subtitles.mp4", mime="video/mp4")
                
        except subprocess.CalledProcessError:
            st.error("เกิดข้อผิดพลาดในการประมวลผลวีดีโอด้วย FFmpeg")
        finally:
            for temp_file in ["input.mp4", "audio.mp3", "subs.ass"]:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
