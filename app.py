import streamlit as st
from groq import Groq
import subprocess
import os

st.set_page_config(page_title="AI Subtitle Burner", page_icon="🎬")
st.title("🎬 ระบบอัปโหลดวีดีโอและฝังซับอัตโนมัติ (Groq API)")

# รับค่า API Key
api_key = st.text_input("🔑 ใส่ Groq API Key ของคุณ:", type="password")

# อัปโหลดไฟล์วีดีโอ (ตอนนี้รองรับไฟล์ใหญ่ขึ้นได้แล้ว เพราะเราจะดึงแค่เสียง)
uploaded_file = st.file_uploader("📂 เลือกไฟล์วีดีโอ (MP4)", type=["mp4"])

if uploaded_file and api_key:
    if st.button("🚀 เริ่มกระบวนการสร้างซับและฝังวีดีโอ"):
        client = Groq(api_key=api_key)
        
        # 1. บันทึกไฟล์วีดีโอที่อัปโหลดลงเซิร์ฟเวอร์ชั่วคราว
        with st.spinner("กำลังอัปโหลดและเตรียมไฟล์..."):
            with open("input.mp4", "wb") as f:
                f.write(uploaded_file.getbuffer())
        
        # 2. **ส่วนที่เพิ่มมาใหม่: สกัดเฉพาะไฟล์เสียงเพื่อลดขนาดไฟล์**
        st.info("🎵 กำลังสกัดเฉพาะไฟล์เสียงเพื่อลดขนาดไฟล์ก่อนส่งให้ AI...")
        try:
            if os.path.exists("audio.mp3"):
                os.remove("audio.mp3")
            
            # ใช้ FFmpeg ดึงแค่เสียงออกมาเป็น MP3 คุณภาพ 64k
            subprocess.run([
                'ffmpeg', '-y', '-i', 'input.mp4', 
                '-vn', # ไม่เอาภาพ (Video No)
                '-c:a', 'libmp3lame', '-b:a', '64k', 
                'audio.mp3'
            ], check=True)
        except subprocess.CalledProcessError:
            st.error("เกิดข้อผิดพลาดในการสกัดไฟล์เสียง")
            st.stop()

        # 3. ส่งไฟล์เสียง (MP3) ไปให้ Groq ถอดเสียงเป็น SRT
        st.info("🎙️ ขั้นตอนที่ 1: กำลังส่งเสียงให้ AI ถอดเป็นซับภาษาไทย... (เร็วมาก!)")
        try:
            with open("audio.mp3", "rb") as audio_file:
                transcription = client.audio.transcriptions.create(
                    model="whisper-large-v3",
                    file=("audio.mp3", audio_file),
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

        # 4. ใช้ FFmpeg ฝังซับลงในวีดีโอต้นฉบับ
        st.info("⚙️ ขั้นตอนที่ 2: กำลังเรนเดอร์และฝังซับไตเติลลงในวีดีโอ...")
        try:
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
            
            # 5. แสดงปุ่มดาวน์โหลด
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
            # เคลียร์ไฟล์ชั่วคราวทิ้งทั้งหมดรวมถึงไฟล์ audio.mp3
            for temp_file in ["input.mp4", "audio.mp3", "subs.srt"]:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
