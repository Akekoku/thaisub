import streamlit as st
from groq import Groq
import subprocess
import os

# ฟังก์ชันใหม่! สำหรับแปลงเวลาเป็นรูปแบบของ SRT (ชั่วโมง:นาที:วินาที,มิลลิวินาที)
def format_timestamp(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

st.set_page_config(page_title="AI Subtitle Burner", page_icon="🎬")
st.title("🎬 ระบบอัปโหลดวีดีโอและฝังซับอัตโนมัติ (Groq API)")

api_key = st.text_input("🔑 ใส่ Groq API Key ของคุณ:", type="password")
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

        st.info("🎙️ ขั้นตอนที่ 1: กำลังส่งเสียงให้ AI ถอดเป็นซับภาษาไทย... (เร็วมาก!)")
        try:
            with open("audio.mp3", "rb") as audio_file:
                # แก้ไข: ขอข้อมูลเป็น verbose_json แทน srt
                transcription = client.audio.transcriptions.create(
                    model="whisper-large-v3",
                    file=("audio.mp3", audio_file),
                    response_format="verbose_json", 
                    language="th"
                )
            
            # แปลง JSON ที่ได้จาก Groq ให้กลายเป็นฟอร์แมต SRT
            srt_content = ""
            segments = transcription.segments
            
            for i, segment in enumerate(segments, start=1):
                # ดึงข้อมูลเวลาและข้อความ (รองรับทั้งแบบ Object และ Dictionary)
                start_time = segment.start if hasattr(segment, 'start') else segment['start']
                end_time = segment.end if hasattr(segment, 'end') else segment['end']
                text = segment.text if hasattr(segment, 'text') else segment['text']
                
                # แปลงเวลา
                start_str = format_timestamp(start_time)
                end_str = format_timestamp(end_time)
                
                # ประกอบร่างเป็นซับไตเติล 1 ก้อน
                srt_content += f"{i}\n{start_str} --> {end_str}\n{text.strip()}\n\n"
            
            # บันทึกเป็นไฟล์ .srt
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
                '-vf', 'subtitles=subs.srt',
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
