import streamlit as st
from groq import Groq
import subprocess
import os
from pythainlp.tokenize import word_tokenize

# 1. ฟังก์ชันแปลงเวลาสำหรับไฟล์ SRT
def format_timestamp(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

# 2. ฟังก์ชันตัดคำภาษาไทยตามจำนวนคำที่เลือกจากเมนู
def split_thai_text_by_words(text, max_words=6):
    words = word_tokenize(text, engine='newmm')
    
    lines = []
    for i in range(0, len(words), max_words):
        line = "".join(words[i:i+max_words])
        lines.append(line)
    return "\n".join(lines)

st.set_page_config(page_title="AI Subtitle Burner Pro", page_icon="🎬")
st.title("🎬 ระบบอัปโหลดวีดีโอและฝังซับอัตโนมัติ (Groq API)")

# =========================================================
# 🔒 ส่วนที่อัปเดตใหม่: ดึง API Key จากระบบล็อกหลังบ้าน (Secrets)
# =========================================================
if "GROQ_API_KEY" in st.secrets:
    api_key = st.secrets["GROQ_API_KEY"]
else:
    st.error("❌ ยังไม่ได้ตั้งค่าล็อก API Key ในระบบ Secrets ของ Streamlit Cloud! (โปรดตั้งค่าตามขั้นตอน)")
    st.stop()

# ปรับแต่งสไตล์ซับไตเติล
st.markdown("### 🛠️ ปรับแต่งสไตล์ซับไตเติล")
with st.expander("คลิกเพื่อเปิดเครื่องมือปรับแต่งตัวอักษรและการตัดคำ", expanded=True):
    max_words_choice = st.selectbox("🔤 จำนวนคำสูงสุดต่อ 1 บรรทัด:", [5, 6, 7, 8], index=1)
    font_weight_choice = st.selectbox("✒️ เลือกความหนาของฟอนต์ (Kanit):", ["Regular", "Medium", "Bold"], index=1)
    font_size_choice = st.slider("📏 ขนาดตัวอักษร (FontSize):", min_value=14, max_value=40, value=22)
    margin_v_choice = st.slider("🔼 ระดับความสูงของซับจากขอบล่าง (MarginV):", min_value=20, max_value=200, value=60)

# ส่วนของการอัปโหลดไฟล์วีดีโอ
uploaded_file = st.file_uploader("📂 เลือกไฟล์วีดีโอ (MP4)", type=["mp4"])

if uploaded_file and api_key:
    if st.button("🚀 เริ่มกระบวนการสร้างซับและฝังวีดีโอ"):
        client = Groq(api_key=api_key)
        
        with st.spinner("กำลังอัปโหลดและเตรียมไฟล์..."):
            with open("input.mp4", "wb") as f:
                f.write(uploaded_file.getbuffer())
        
        st.info("🎵 กำลังสกัดเฉพาะไฟล์เสียงเพื่อลดขนาดไฟล์ก่อนส่งให้ AI...")
        try:
            if os.path.exists("audio.mp3"):
                os.remove("audio.mp3")
            
            subprocess.run([
                'ffmpeg', '-y', '-i', 'input.mp4', 
                '-vn', 
                '-c:a', 'libmp3lame', '-b:a', '64k', 
                'audio.mp3'
            ], check=True)
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
            segments = transcription.segments
            
            for i, segment in enumerate(segments, start=1):
                start_time = segment.start if hasattr(segment, 'start') else segment['start']
                end_time = segment.end if hasattr(segment, 'end') else segment['end']
                text = segment.text if hasattr(segment, 'text') else segment['text']
                
                start_str = format_timestamp(start_time)
                end_str = format_timestamp(end_time)
                
                formatted_text = split_thai_text_by_words(text.strip(), max_words=max_words_choice)
                
                srt_content += f"{i}\n{start_str} --> {end_str}\n{formatted_text}\n\n"
            
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
            
            font_name = "Kanit Medium"
            if font_weight_choice == "Regular":
                font_name = "Kanit"
            elif font_weight_choice == "Bold":
                font_name = "Kanit Bold"
                
            cmd = [
                'ffmpeg', '-y',
                '-i', 'input.mp4',
                '-vf', f"subtitles=subs.srt:fontsdir=.:force_style='Fontname={font_name},FontSize={font_size_choice},MarginV={margin_v_choice},Outline=2,Shadow=1,Alignment=2'",
                '-c:a', 'copy', 
                'output.mp4'
            ]
            
            subprocess.run(cmd, check=True)
            st.success("🎉 ฝังซับไตเติลลงวีดีโอเรียบร้อยแล้ว!")
            
            with open("output.mp4", "rb") as file:
                st.download_button(
                    label="📥 ดาวน์โหลดวีดีโอพร้อมซับไตเติล",
                    data=file,
                    file_name="video_with_subtitles.mp4",
                    mime="video/mp4"
                )
                
        except subprocess.CalledProcessError:
            st.error("เกิดข้อผิดพลาดในการประมวลผลวีดีโอด้วย FFmpeg")
        finally:
            for temp_file in ["input.mp4", "audio.mp3", "subs.srt"]:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                    
