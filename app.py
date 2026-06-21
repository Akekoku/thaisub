import streamlit as st
from groq import Groq
import subprocess
import os
import json
from pythainlp.tokenize import word_tokenize
from PIL import ImageFont  # ไลบรารีสำหรับวัดขนาดพิกเซลของฟอนต์

# แผนผังจับคู่ชื่อฟอนต์หน้าเว็บ กับ ชื่อไฟล์จริงใน GitHub ของคุณ
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

def format_timestamp(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

# 🌟 ฟังก์ชันใหม่แกะกล่อง: คำนวณการตัดบรรทัดจากความกว้างพิกเซลจริง (เหมือน Word)
def split_text_by_pixel_width(text, font_file, font_size, max_width_pixels):
    try:
        # โหลดไฟล์ฟอนต์จริงมาจำลองการวัดขนาด
        font = ImageFont.truetype(font_file, font_size)
    except Exception:
        # ถ้าโหลดฟอนต์ไม่สำเร็จ ให้ใช้ระบบนับคำสำรองล่วงหน้าเพื่อไม่ให้แอปค้าง
        return text

    # หั่นข้อความภาษาไทยออกเป็นคำๆ ด้วย pythainlp ก่อนเพื่อป้องกันคำขาดครึ่ง
    words = word_tokenize(text, engine='newmm')
    
    lines = []
    current_line = ""
    
    for word in words:
        test_line = current_line + word
        # สั่งให้ฟอนต์ลองวัดขนาดความกว้าง (Width) ของบรรทัดทดสอบนี้
        bbox = font.getbbox(test_line)
        line_width = bbox[2] - bbox[0] if bbox else 0
        
        # ถ้าความกว้างเกินกรอบพิกเซลที่ตั้งไว้ ให้ปัดคำนี้ไปขึ้นบรรทัดใหม่
        if line_width > max_width_pixels and current_line:
            lines.append(current_line)
            current_line = word
        else:
            current_line = test_line
            
    if current_line:
        lines.append(current_line)
        
    return "\n".join(lines)

# 🌟 ฟังก์ชันพิเศษ: ใช้ ffprobe แอบส่องความกว้างพิกเซลจริงของตัววิดีโอที่อัปโหลดเข้ามา
def get_video_width(video_path):
    try:
        cmd = [
            'ffprobe', '-v', 'error', 
            '-select_streams', 'v:0', 
            '-show_entries', 'stream=width', 
            '-of', 'json'
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        return data['streams'][0]['width']
    except Exception:
        return 1080  # ถ้าตรวจไม่ได้ ให้ใช้ค่ามาตรฐานวิดีโอแนวตั้ง 1080px ค้ำไว้ก่อน

st.set_page_config(page_title="AI Subtitle Bounding Box Pro", page_icon="🎬")
st.title("🎬 ระบบฝังซับอัตโนมัติด้วยการวัดความกว้างพิกเซล")

if "GROQ_API_KEY" in st.secrets:
    api_key = st.secrets["GROQ_API_KEY"]
else:
    st.error("❌ ยังไม่ได้ตั้งค่าล็อก API Key ในระบบ Secrets")
    st.stop()

st.markdown("### 🛠️ ปรับแต่งสไตล์ซับไตเติล")
with st.expander("คลิกเพื่อเปิดเครื่องมือปรับแต่งตัวอักษรและการควบคุมกรอบ Safe Zone", expanded=True):
    
    font_choice = st.selectbox(
        "✒️ เลือกรูปแบบฟอนต์ที่คุณต้องการ:", 
        list(FONT_MAP.keys()),
        index=8 # ค่าเริ่มต้นที่ Mali ตามที่คุณชอบ
    )
    
    col1, col2 = st.columns(2)
    with col1:
        font_size_choice = st.slider("📏 ขนาดตัวอักษร (FontSize):", min_value=14, max_value=40, value=18)
        outline_choice = st.slider("🖍️ ความหนาของขอบ (Outline):", min_value=0, max_value=5, value=1)
        
    with col2:
        # 🌟 สไลเดอร์ใหม่! บังคับกรอบแสดงผลแทนการนับคำ (Safe Zone)
        max_width_pct = st.slider("🎯 ความกว้างกรอบข้อความ (% ของจอ):", min_value=50, max_value=95, value=80)
        margin_v_choice = st.slider("🔼 ระดับความสูงของซับจากขอบล่าง (MarginV):", min_value=20, max_value=200, value=50)

uploaded_file = st.file_uploader("📂 เลือกไฟล์วีดีโอ (MP4)", type=["mp4"])

if uploaded_file and api_key:
    if st.button("🚀 เริ่มกระบวนการสร้างซับและฝังวีดีโอ"):
        client = Groq(api_key=api_key)
        
        with st.spinner("กำลังอัปโหลดและเตรียมไฟล์..."):
            with open("input.mp4", "wb") as f:
                f.write(uploaded_file.getbuffer())
        
        # ค้นหาขนาดพิกเซลจริงของวิดีโอตัวนี้
        video_width = get_video_width("input.mp4")
        # คำนวณหากรอบพิกเซลสูงสุดที่จะยอมให้ตัวหนังสือวิ่งไปชน (เช่น 1080 x 80% = 864 พิกเซล)
        allowed_pixel_width = video_width * (max_width_pct / 100)
        
        st.info(f"📹 ตรวจพบวิดีโอกว้าง {video_width}px -> กางกรอบ Safe Zone ให้ข้อความกว้างไม่เกิน {int(allowed_pixel_width)}px")
        
        st.info("🎵 กำลังสกัดเฉพาะไฟล์เสียงเพื่อลดขนาดไฟล์ก่อนส่งให้ AI...")
        try:
            if os.path.exists("audio.mp3"):
                os.remove("audio.mp3")
            subprocess.run(['ffmpeg', '-y', '-i', 'input.mp4', '-vn', '-c:a', 'libmp3lame', '-b:a', '64k', 'audio.mp3'], check=True)
        except subprocess.CalledProcessError:
            st.error("เกิดข้อผิดพลาดในการสกัดไฟล์เสียง")
            st.stop()

        st.info("🎙️ ขั้นตอนที่ 1: กำลังส่งเสียงให้ AI ถอดเป็นซับภาษาไทย...")
        try:
            with open("audio.mp3", "rb") as audio_file:
                transcription = client.audio.transcriptions.create(
                    model="whisper-large-v3",
                    file=("audio.mp3", audio_file),
                    response_format="verbose_json", 
                    language="th"
                )
            
            srt_content = ""
            actual_font_file = FONT_MAP[font_choice] # ดึงชื่อไฟล์ .ttf ออกมาใช้งานจริง
            
            for i, segment in enumerate(transcription.segments, start=1):
                start_time = segment['start'] if isinstance(segment, dict) else getattr(segment, 'start')
                end_time = segment['end'] if isinstance(segment, dict) else getattr(segment, 'end')
                text = segment['text'] if isinstance(segment, dict) else getattr(segment, 'text')
                
                # ** ส่งเข้าไปหั่นประโยคด้วยระบบวัดพิกเซลจริงล่วงหน้าก่อนลงไฟล์ SRT **
                formatted_text = split_text_by_pixel_width(
                    text.strip(), 
                    font_file=actual_font_file, 
                    font_size=font_size_choice, 
                    max_width_pixels=allowed_pixel_width
                )
                srt_content += f"{i}\n{format_timestamp(start_time)} --> {format_timestamp(end_time)}\n{formatted_text}\n\n"
            
            with open("subs.srt", "w", encoding="utf-8") as f:
                f.write(srt_content)
            st.success("ถอดเสียงและสร้างไฟล์ SRT สำเร็จ!")
            
        except Exception as e:
            st.error(f"เกิดข้อผิดพลาดจาก Groq API: {e}")
            st.stop()

        st.info("⚙️ ขั้นตอนที่ 2: กำลังเรนเดอร์และฝังซับไตเติลลงในวีดีโอ...")
        try:
            if os.path.exists("output.mp4"):
                os.remove("output.mp4")
                
            cmd = [
                'ffmpeg', '-y',
                '-i', 'input.mp4',
                '-vf', f"subtitles=subs.srt:fontsdir=.:force_style='Fontname={font_choice},FontSize={font_size_choice},MarginV={margin_v_choice},Outline={outline_choice},Shadow=1,Alignment=2'",
                '-c:a', 'copy', 
                'output.mp4'
            ]
            
            subprocess.run(cmd, check=True)
            st.success("🎉 ฝังซับไตเติลลงวีดีโอเรียบร้อยแล้ว!")
            
            with open("output.mp4", "rb") as file:
                st.download_button(label="📥 ดาวน์โหลดวีดีโอพร้อมซับไตเติล", data=file, file_name="video_with_subtitles.mp4", mime="video/mp4")
                
        except subprocess.CalledProcessError:
            st.error("เกิดข้อผิดพลาดในการประมวลผลวีดีโอด้วย FFmpeg")
        finally:
            for temp_file in ["input.mp4", "audio.mp3", "subs.srt"]:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
