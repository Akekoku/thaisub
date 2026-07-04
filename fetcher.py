import streamlit as st
from groq import Groq
import requests
import os
import time
import random

st.set_page_config(page_title="Mini B-Roll Fetcher", page_icon="🧲")
st.markdown("## 🧲 เครื่องมือดูดคลิป B-Roll จากเสียงพูด (Mini Fetcher)")

# ดึง API Key
if "GROQ_API_KEY" in st.secrets:
    api_key = st.secrets["GROQ_API_KEY"]
else:
    st.error("❌ ยังไม่ได้ตั้งค่า Groq API Key")
    st.stop()
pexels_key = st.secrets.get("PEXELS_API_KEY", "")

def get_single_action_keyword(client, text):
    try:
        prompt = f"""
        Read this Thai text: '{text}'
        Create a 2 to 4 word English search query for Pexels Stock Video that represents the main physical action or object.
        For example, if it's about an engineer creating a rice cooker, use "engineer working" or "cooking rice".
        Output ONLY the search query. No punctuation.
        """
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama3-8b-8192",
            temperature=0.2 
        )
        return chat_completion.choices[0].message.content.strip().replace('"', '')
    except Exception:
        return random.choice(["engineer working", "cooking rice", "vintage technology"])

def fetch_single_video(keyword, pexels_key, output_path):
    headers = {"Authorization": pexels_key}
    url = f"https://api.pexels.com/videos/search?query={keyword}&orientation=portrait&per_page=10"
    try:
        res = requests.get(url, headers=headers, timeout=10).json()
        if res.get("videos"):
            videos = res["videos"]
            random.shuffle(videos)
            for v in videos:
                for f in v.get("video_files", []):
                    if f.get("file_type") == "video/mp4" and f.get("width") and f.get("width") >= 720:
                        v_res = requests.get(f.get("link"), timeout=15)
                        with open(output_path, "wb") as f_out:
                            f_out.write(v_res.content)
                        return True
    except Exception:
        pass
    return False

uploaded_file = st.file_uploader("📂 อัปโหลดไฟล์เสียง 1 ฉาก (WAV / MP3)", type=["wav", "mp3"])

if uploaded_file and api_key and pexels_key:
    if st.button("🧲 ค้นหาและดูดคลิปวิดีโอ"):
        client = Groq(api_key=api_key)
        
        with st.spinner("กำลังฟังเสียง..."):
            with open("temp_audio.wav", "wb") as f:
                f.write(uploaded_file.getbuffer())
                
            with open("temp_audio.wav", "rb") as audio_file:
                transcription = client.audio.transcriptions.create(
                    model="whisper-large-v3", 
                    file=("temp_audio.wav", audio_file), 
                    response_format="text", 
                    language="th"
                )
            st.success(f"🗣️ ข้อความที่ได้ยิน: '{transcription.strip()}'")
            
        with st.spinner("กำลังวิเคราะห์คีย์เวิร์ด..."):
            keyword = get_single_action_keyword(client, transcription)
            st.info(f"🔍 AI สกัดคีย์เวิร์ดได้คำว่า: '{keyword}'")
            
        with st.spinner("กำลังดูดคลิปจาก Pexels..."):
            video_filename = "downloaded_broll.mp4"
            if os.path.exists(video_filename):
                os.remove(video_filename)
                
            success = fetch_single_video(keyword, pexels_key, video_filename)
            
            if success:
                st.video(video_filename)
                with open(video_filename, "rb") as v_file:
                    st.download_button(
                        label="📥 ดาวน์โหลดวิดีโอนี้ลงเครื่อง",
                        data=v_file,
                        file_name=f"Broll_{keyword.replace(' ', '_')}.mp4",
                        mime="video/mp4"
                    )
            else:
                st.error("❌ ค้นหาวิดีโอไม่พบ หรือระบบ Pexels มีปัญหา ลองใหม่อีกครั้งครับ")
