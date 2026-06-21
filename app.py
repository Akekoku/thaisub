import streamlit as st
from groq import Groq
import subprocess
import os

st.set_page_config(page_title="AI Subtitle Burner", page_icon="🎬")
st.title("🎬 ระบบอัปโหลดวีดีโอและฝังซับอัตโนมัติ (Groq API)")

# รับค่า API Key
api_key = st.text_input("🔑 ใส่ Groq API Key ของคุณ:", type="password")

# รับไฟล์วีดีโอ
uploaded_file = st.file_uploader("📂 เลือกไฟล์วีดีโอ (MP4 ขนาดไม่เกิน 25MB)", type=["mp4"])

if uploaded_file and api_key:
    if st.button("🚀 เริ่มกระบวนการสร้างซับและฝังวีดีโอ"):
        client = Groq(api_key=api_key)
        
        # 1. บันทึกไฟล์วีดีโอที่อัปโหลดลงเซิร์ฟเวอร์ชั่วคราว
        with st.spinner("กำลังอัปโหลดและเตรียมไฟล์..."):
            with open("input.mp4", "wb") as f:
                f.write(uploaded_file.getbuffer())
        
        # 2. ส่งไฟล์ไปให้ Groq (Whisper V3) ถอดเสียงเป็น SRT
        st.info("🎙️ ขั้นตอนที่ 1: กำลังส่งเสียงให้ AI ถอดเป็นซับภาษาไทย... (เร็วมาก!)")
        try:
            with open("input.mp4", "rb") as video_file:
                transcription = client.audio.transcriptions.create(
                    model="whisper-large-v3",
                    file=("input.mp4", video_file),
                    response_format="srt",
                    language="th"
                )
            
            # บันทึกไฟล์ซับไตเติล
            with open("subs.srt", "w", encoding="utf-8") as f:
                f.write(transcription)
            st.success("ถอดเสียงเป็นซับไตเติลสำเร็จ!")
            
        except Exception as e:
            st.error(f"เกิดข้อผิดพลาดจาก Groq API: {e}")
            st.stop()

        # 3. ใช้ FFmpeg ฝังซับลงในวีดีโอ (Hardsub)
        st.info("⚙️ ขั้นตอนที่ 2: กำลังเรนเดอร์และฝังซับไตเติลลงในวีดีโอ...")
        try:
            # ลบไฟล์ output เดิมถ้ามีค้างอยู่
            if os.path.exists("output.mp4"):
                os.remove("output.mp4")
                
            # สั่งคำสั่ง FFmpeg
            cmd = [
                'ffmpeg', '-y',
                '-i', 'input.mp4',
                '-vf', 'subtitles=subs.srt',
                '-c:a', 'copy', # ใช้เสียงเดิม ไม่ต้องแปลงใหม่
                'output.mp4'
            ]
            
            subprocess.run(cmd, check=True)
            st.success("🎉 ฝังซับไตเติลลงวีดีโอเรียบร้อยแล้ว!")
            
            # 4. แสดงปุ่มดาวน์โหลด
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
            # เคลียร์ไฟล์ชั่วคราวทิ้งเพื่อไม่ให้รกเซิร์ฟเวอร์
            for temp_file in ["input.mp4", "subs.srt"]:
                if os.path.exists(temp_file):
                    os.remove(temp_file)