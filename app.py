import streamlit as st
from groq import Groq
import subprocess
import os
import shutil
import asyncio
import edge_tts
from pythainlp.tokenize import word_tokenize
from PIL import ImageFont
import requests
import random
import time

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
# 🔒 ระบบดักรหัสผ่านความปลอดภัยสูง
# =========================================================
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if not st.session_state["authenticated"]:
    st.set_page_config(page_title="🔒กรุณาล็อกอิน", page_icon="🔑")
    st.markdown("## 🔐 ระบบภายในส่วนตัว (Restricted Access)")
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
    return f"&H{alpha_hex}{hex_str[4:6]}{hex_str[2:4]}{hex_str[0:2]}"

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
    try: font = ImageFont.truetype(font_file, pil_font_size)
    except Exception: return text
    words = word_tokenize(text, engine='newmm')
    lines, current_line = [], ""
    for word in words:
        test_line = current_line + word
        if hasattr(font, 'getlength'): line_width = font.getlength(test_line)
        else:
            bbox = font.getbbox(test_line)
            line_width = bbox[2] - bbox[0] if bbox else 0
        if line_width > max_width_pixels and current_line:
            lines.append(current_line)
            current_line = word
        else: current_line = test_line
    if current_line: lines.append(current_line)
    return "\n".join(lines)

def get_video_dimensions(video_path):
    try:
        cmd = ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height', '-of', 'csv=s=x:p=0', video_path]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        width_str, height_str = result.stdout.strip().split('x')
        return int(width_str), int(height_str)
    except Exception:
        return 720, 1280

# (ส่วน Pexels ยังคงไว้ เผื่ออยากใช้สลับกัน)
def get_action_keyword_from_ai(client, thai_text):
    try:
        prompt = f"""
        You are creating a storyboard. Read this Thai scene description: '{thai_text}'
        Step 1: Determine "Who is doing what" in this scene.
        Step 2: Create a 2 to 4 word English search query for Pexels Stock Video. 
        Pexels needs literal, simple action phrases.
        Output ONLY the search query.
        """
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama3-8b-8192",
            temperature=0.2 
        )
        time.sleep(2.5) 
        return chat_completion.choices[0].message.content.strip().replace('"', '')
    except Exception:
        time.sleep(2.5)
        return random.choice(["cinematic landscape", "people walking", "vintage object"])

def fetch_pexels_video(keyword, pexels_key, output_path):
    headers = {"Authorization": pexels_key}
    url = f"https://api.pexels.com/videos/search?query={keyword}&orientation=portrait&per_page=15"
    try:
        res = requests.get(url, headers=headers, timeout=10).json()
        if res.get("videos"):
            videos = res["videos"]
            random.shuffle(videos)
            download_url = None
            for v in videos:
                for f in v.get("video_files", []):
                    if f.get("file_type") == "video/mp4" and f.get("width") and f.get("width") >= 720:
                        download_url = f.get("link")
                        break
                if download_url: break
            if download_url:
                v_res = requests.get(download_url, timeout=15)
                with open(output_path, "wb") as f:
                    f.write(v_res.content)
                return True
    except Exception: pass
    return False

st.set_page_config(page_title="AI Auto-Edit & Subtitle Pro", page_icon="🎬")
st.markdown("## 🎬 ระบบ AI ตัดต่ออัตโนมัติ & ฝังซับ (Pro)")

if "GROQ_API_KEY" in st.secrets: api_key = st.secrets["GROQ_API_KEY"]
else: st.error("❌ ยังไม่ได้ตั้งค่าล็อก Groq API Key"); st.stop()
pexels_key = st.secrets.get("PEXELS_API_KEY", "")

st.markdown("### ✂️ ระบบ AI ตัดต่ออัตโนมัติ (Rough Cut)")
enable_dead_air = st.toggle("🔇 เปิดระบบตรวจจับและตัดช่วงเงียบ", value=False)
silence_thresh, silence_duration = "-35dB", 0.5
if enable_dead_air:
    c_d1, c_d2 = st.columns(2)
    with c_d1: silence_thresh = f"{st.slider('ระดับเสียงเงียบ', -50, -10, -35, 5)}dB"
    with c_d2: silence_duration = st.slider('ระยะเวลาเงียบขั้นต่ำ', 0.2, 2.0, 0.5, 0.1)

enable_filler_removal = st.toggle("🧹 เปิดระบบล้างคำฟุ่มเฟือย", value=True)
if enable_filler_removal:
    filler_words_input = st.text_input("📝 คำขยะที่ต้องการให้ลบ", value="เอ่อ, อ่า, อืม, แบบว่า, คือแบบ")
    filler_words_list = [w.strip() for w in filler_words_input.split(',') if w.strip()]

st.markdown("### 🎭 โหมดสร้างภาพประกอบ (Faceless Video)")
faceless_mode = st.radio("เลือกวิธีสร้างวิดีโอพื้นหลัง:", 
                         ["ไม่ใช้ (ใช้วิดีโอต้นฉบับ)", 
                          "🤖 Pexels AI (ดึงภาพอัตโนมัติจากเน็ต)", 
                          "📂 Custom B-Roll (อัปโหลดวิดีโอมาเรียงต่อเอง)"], index=0)

scene_target_duration = 8.0
custom_videos = []
if faceless_mode != "ไม่ใช้ (ใช้วิดีโอต้นฉบับ)":
    scene_target_duration = st.slider("⏱️ กำหนดความยาวของแต่ละฉาก (วินาที)", 4.0, 15.0, 8.0, 1.0)
    if faceless_mode == "📂 Custom B-Roll (อัปโหลดวิดีโอมาเรียงต่อเอง)":
        st.info("💡 น้าสามารถลากคลิปวิดีโอที่เจนจาก Google Labs หลายๆ คลิปมาใส่ตรงนี้ได้เลยครับ ระบบจะนำไปเรียงต่อกันตามลำดับและตัดให้พอดีกับเสียงพูดแต่ละฉาก")
        custom_videos = st.file_uploader("เลือกไฟล์วิดีโอประกอบ (อัปโหลดได้หลายไฟล์)", type=["mp4"], accept_multiple_files=True)

st.markdown("### 🌐 เลือกภาษาซับไตเติล & พากย์เสียง")
sub_language = st.radio("ภาษาซับไตเติล?", ["🇹🇭 ภาษาไทย", "🇬🇧 ภาษาอังกฤษ"], horizontal=True)
enable_dubbing = False
selected_voice = "en-US-JennyNeural"
if "ภาษาอังกฤษ" in sub_language:
    enable_dubbing = st.toggle("🎧 เปิดพากย์เสียง AI ฝรั่ง", value=False)
    if enable_dubbing:
        voice_labels = {"👩 หญิง - สดใส": "en-US-JennyNeural", "👩 หญิง - นุ่มนวล": "en-US-AriaNeural", "👨 ชาย - อบอุ่น": "en-US-GuyNeural"}
        selected_voice = voice_labels[st.selectbox("นักพากย์:", list(voice_labels.keys()), index=0)]

st.markdown("### 🛠️ ปรับแต่งสไตล์ซับไตเติล")
with st.expander("เปิดเครื่องมือปรับแต่งตัวอักษร", expanded=False):
    font_choice = st.selectbox("✒️ ฟอนต์:", list(FONT_MAP.keys()), index=8)
    c1, c2, c3 = st.columns(3)
    with c1: text_color = st.color_picker("🅰️ สีตัวอักษร", "#FFFFFF")
    with c2: outline_color = st.color_picker("🖍️ สีขอบ", "#000000")
    with c3: bg_style = st.selectbox("🔲 พื้นหลัง", ["ขอบปกติ", "แถบกล่องดำรองหลัง"])

    anim_choice = st.selectbox("🎬 เอฟเฟกต์:", ["ไม่มี", "เด้งพอง (Pop-up)", "ค่อยๆ ปรากฏ (Fade-in)"], index=0)
    pop_scale, pop_duration, fade_duration = 130, 150, 200
    if anim_choice == "เด้งพอง (Pop-up)":
        ca1, ca2 = st.columns(2)
        with ca1: pop_scale = st.slider("ความขยายตอนเด้ง (%)", 110, 180, 130, 5)
        with ca2: pop_duration = st.slider("ความเร็วยุบตัว", 50, 400, 150, 10)

    cl1, cl2 = st.columns(2)
    with cl1:
        font_size_choice = st.slider("ขนาดตัวอักษร:", 14, 40, 18)
        outline_thickness = st.slider("ความหนาขอบ:", 0, 5, 1)
    with cl2:
        max_width_pct = st.slider("ความกว้างกรอบข้อความ (%):", 50, 150, 100)
        margin_v_choice = st.slider("ความสูงจากขอบล่าง:", 20, 200, 50)
    force_max_2_lines = st.checkbox("🚫 บังคับซับไม่เกิน 2 บรรทัด", value=True)

uploaded_file = st.file_uploader("📂 1. อัปโหลดไฟล์เสียงพูดหลัก (MP3 / WAV / MP4)", type=["mp4", "mp3", "wav"])

if uploaded_file and api_key:
    if st.button("🚀 เริ่มกระบวนการผลิตคลิป"):
        client = Groq(api_key=api_key)
        
        with st.spinner("กำลังเตรียมไฟล์..."):
            file_ext = uploaded_file.name.split('.')[-1].lower()
            with open(f"raw_upload.{file_ext}", "wb") as f: f.write(uploaded_file.getbuffer())
        
        # --- เตรียมไฟล์ B-Roll ที่อัปโหลด ---
        custom_broll_paths = []
        if faceless_mode == "📂 Custom B-Roll (อัปโหลดวิดีโอมาเรียงต่อเอง)" and custom_videos:
            for i, vid in enumerate(custom_videos):
                vid_path = f"custom_broll_{i}.mp4"
                with open(vid_path, "wb") as f: f.write(vid.getbuffer())
                custom_broll_paths.append(vid_path)

        st.info("🎵 กำลังประมวลผลไฟล์เสียง...")
        if os.path.exists("audio.mp3"): os.remove("audio.mp3")
        if file_ext == "mp3": shutil.copy("raw_upload.mp3", "audio.mp3")
        elif file_ext == "wav": subprocess.run(['ffmpeg', '-y', '-i', 'raw_upload.wav', '-c:a', 'libmp3lame', '-b:a', '64k', 'audio.mp3'], check=True)
        else: subprocess.run(['ffmpeg', '-y', '-i', 'raw_upload.mp4', '-vn', '-c:a', 'libmp3lame', '-b:a', '64k', 'audio.mp3'], check=True)

        st.info(f"🎙️ กำลังให้ AI ถอดความและจัดสตอรี่บอร์ด...")
        try:
            with open("audio.mp3", "rb") as audio_file:
                response_th = client.audio.transcriptions.create(model="whisper-large-v3", file=("audio.mp3", audio_file), response_format="verbose_json", language="th")
                if "ภาษาอังกฤษ" in sub_language:
                    audio_file.seek(0)
                    response_sub = client.audio.translations.create(model="whisper-large-v3", file=("audio.mp3", audio_file), response_format="verbose_json")
                else: response_sub = response_th

            video_width, video_height = (720, 1280) if faceless_mode != "ไม่ใช้ (ใช้วิดีโอต้นฉบับ)" else get_video_dimensions("raw_upload.mp4")
            allowed_pixel_width = video_width * (max_width_pct / 100)
            actual_pil_font_size = int((font_size_choice / 288) * video_height * 0.75)
            ass_font_size = int(font_size_choice * (video_height / 288.0))
            ass_outline = int(outline_thickness * (video_height / 288.0))
            ass_margin_v = int(margin_v_choice * (video_height / 288.0))
            
            ass_content = f"""[Script Info]\nScriptType: v4.00+\nPlayResX: {video_width}\nPlayResY: {video_height}\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Default,{font_choice},{ass_font_size},{hex_to_ass_color(text_color)},&H0000FFFF,{hex_to_ass_color(outline_color)},&H00000000,0,0,0,0,100,100,0,0,1,{ass_outline},0,2,10,10,{ass_margin_v},1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"""
            actual_font_file = FONT_MAP[font_choice]
            
            segments_data_for_subs = []
            scenes_data = []
            current_scene_text, scene_start, scene_idx = "", 0.0, 1
            
            for idx, (seg_th, seg_sub) in enumerate(zip(response_th.segments, response_sub.segments), start=1):
                start_time = seg_sub['start'] if isinstance(seg_sub, dict) else getattr(seg_sub, 'start')
                end_time = seg_sub['end'] if isinstance(seg_sub, dict) else getattr(seg_sub, 'end')
                text_sub = seg_sub['text'].strip() if isinstance(seg_sub, dict) else getattr(seg_sub, 'text').strip()
                text_th = seg_th['text'].strip() if isinstance(seg_th, dict) else getattr(seg_th, 'text').strip()
                
                if not text_sub: continue
                segments_data_for_subs.append((idx, text_sub, start_time, end_time))
                
                if current_scene_text == "": scene_start = start_time
                current_scene_text += text_th + " "
                
                if (end_time - scene_start) >= scene_target_duration:
                    scenes_data.append({"idx": scene_idx, "start": scene_start, "end": end_time, "text": current_scene_text.strip()})
                    scene_idx += 1
                    current_scene_text = ""
                    
            if current_scene_text != "":
                scenes_data.append({"idx": scene_idx, "start": scene_start, "end": end_time, "text": current_scene_text.strip()})

            # 🎬 จัดการวิดีโอพื้นหลัง
            if faceless_mode == "🤖 Pexels AI (ดึงภาพอัตโนมัติจากเน็ต)":
                st.info(f"🎞️ ดึงวิดีโอจาก Pexels สำหรับ {len(scenes_data)} ฉาก...")
                for scene in scenes_data:
                    kw = get_action_keyword_from_ai(client, scene["text"])
                    raw_clip, processed_clip = f"raw_scene_{scene['idx']}.mp4", f"clip_{scene['idx']}.mp4"
                    scene["clip_path"] = "none"
                    if fetch_pexels_video(kw, pexels_key, raw_clip):
                        subprocess.run(['ffmpeg', '-y', '-i', raw_clip, '-ss', '0', '-t', str(scene['end']-scene['start']), '-vf', f'scale={video_width}:{video_height}:force_original_aspect_ratio=increase,crop={video_width}:{video_height},fps=30', '-c:v', 'libx264', '-an', processed_clip], capture_output=True)
                        if os.path.exists(processed_clip): scene["clip_path"] = processed_clip
                    if os.path.exists(raw_clip): os.remove(raw_clip)
                    if scene["clip_path"] == "none":
                        subprocess.run(['ffmpeg', '-y', '-f', 'lavfi', '-i', f'color=c=black:s={video_width}x{video_height}:d={scene["end"]-scene["start"]}:r=30', '-c:v', 'libx264', f"clip_{scene['idx']}.mp4"], capture_output=True)
                        scene["clip_path"] = f"clip_{scene['idx']}.mp4"

            elif faceless_mode == "📂 Custom B-Roll (อัปโหลดวิดีโอมาเรียงต่อเอง)":
                st.info(f"🎞️ กำลังตัดต่อวิดีโอที่คุณอัปโหลดให้เข้ากับความยาวของ {len(scenes_data)} ฉาก...")
                broll_index = 0
                for scene in scenes_data:
                    processed_clip = f"clip_{scene['idx']}.mp4"
                    scene_dur = scene['end'] - scene['start']
                    if broll_index < len(custom_broll_paths):
                        # ดึงคลิปที่ผู้ใช้อัปโหลดมาตัดให้พอดีกับเวลาของฉาก
                        input_broll = custom_broll_paths[broll_index]
                        subprocess.run(['ffmpeg', '-y', '-i', input_broll, '-ss', '0', '-t', str(scene_dur), '-vf', f'scale={video_width}:{video_height}:force_original_aspect_ratio=increase,crop={video_width}:{video_height},fps=30', '-c:v', 'libx264', '-an', processed_clip], capture_output=True)
                        scene["clip_path"] = processed_clip
                        broll_index += 1 # สลับไปใช้คลิปถัดไปในฉากต่อไป
                    else:
                        # ถ้าคลิปที่อัปโหลดมามีน้อยกว่าจำนวนฉาก ให้วนกลับไปใช้คลิปแรกใหม่ (Loop)
                        input_broll = custom_broll_paths[0] if custom_broll_paths else None
                        if input_broll:
                            subprocess.run(['ffmpeg', '-y', '-i', input_broll, '-ss', '0', '-t', str(scene_dur), '-vf', f'scale={video_width}:{video_height}:force_original_aspect_ratio=increase,crop={video_width}:{video_height},fps=30', '-c:v', 'libx264', '-an', processed_clip], capture_output=True)
                            scene["clip_path"] = processed_clip
                        else:
                            subprocess.run(['ffmpeg', '-y', '-f', 'lavfi', '-i', f'color=c=black:s={video_width}x{video_height}:d={scene_dur}:r=30', '-c:v', 'libx264', processed_clip], capture_output=True)
                            scene["clip_path"] = processed_clip

            # สร้างไฟล์ซับไตเติล
            for idx, text_sub, start_time, end_time in segments_data_for_subs:
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
            with open("subs.ass", "w", encoding="utf-8") as f: f.write(ass_content)

            # พากย์เสียง AI
            if enable_dubbing and "ภาษาอังกฤษ" in sub_language:
                st.info("🗣️ กำลังเจนเสียงพากย์ AI...")
                async def gen_dubs(data, voice):
                    for idx, text, _, _ in data:
                        if os.path.exists(f"seg_{idx}.mp3"): os.remove(f"seg_{idx}.mp3")
                        await edge_tts.Communicate(text, voice).save(f"seg_{idx}.mp3")
                asyncio.run(gen_dubs(segments_data_for_subs, selected_voice))

        except Exception as e: st.error(f"เกิดข้อผิดพลาด: {e}"); st.stop()

        st.info("⚙️ ขั้นตอนสุดท้าย: กำลังประกอบร่างคลิปด้วย FFmpeg...")
        try:
            if os.path.exists("output.mp4"): os.remove("output.mp4")
            bg_video_track = "raw_upload.mp4" if file_ext == "mp4" and faceless_mode == "ไม่ใช้ (ใช้วิดีโอต้นฉบับ)" else None
            
            if faceless_mode != "ไม่ใช้ (ใช้วิดีโอต้นฉบับ)":
                with open("concat_list.txt", "w") as f:
                    for scene in scenes_data: f.write(f"file '{scene['clip_path']}'\n")
                subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', 'concat_list.txt', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', 'bg_combined.mp4'], check=True)
                bg_video_track = "bg_combined.mp4"

            cmd = ['ffmpeg', '-y']
            if bg_video_track: cmd.extend(['-i', bg_video_track])
            else: cmd.extend(['-f', 'lavfi', '-i', f'color=c=black:s=720x1280:d={segments_data_for_subs[-1][3]}:r=30'])
            
            if enable_dubbing and "ภาษาอังกฤษ" in sub_language:
                for idx, _, _, _ in segments_data_for_subs: cmd.extend(['-i', f"seg_{idx}.mp3"])
                filter_str = ""
                for idx, _, start, _ in segments_data_for_subs: filter_str += f"[{idx}:a]adelay={int(start * 1000)}|{int(start * 1000)}[a{idx}]; "
                mix_inputs = "".join(f"[a{idx}]" for idx, _, _, _ in segments_data_for_subs)
                filter_str += f"{mix_inputs}amix=inputs={len(segments_data_for_subs)}:normalize=0[outa]; [0:v]subtitles=subs.ass:fontsdir=.[outv]"
                cmd.extend(['-filter_complex', filter_str, '-map', '[outv]', '-map', '[outa]', '-c:v', 'libx264', '-crf', '17', '-preset', 'slow', '-c:a', 'aac', 'output.mp4'])
            else:
                cmd.extend(['-i', 'audio.mp3', '-vf', 'subtitles=subs.ass:fontsdir=.', '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'libx264', '-crf', '17', '-c:a', 'aac', 'output.mp4'])

            subprocess.run(cmd, check=True)
            st.success("🎉 โรงงาน AI ประกอบคลิปสตอรี่บอร์ดเสร็จสมบูรณ์!")
            
            with open("output.mp4", "rb") as file:
                st.download_button(label="📥 ดาวน์โหลดวิดีโอสตอรี่บอร์ด", data=file, file_name="storyboard_final.mp4", mime="video/mp4")
                
        except subprocess.CalledProcessError as e: st.error(f"เกิดข้อผิดพลาดในการประกอบวิดีโอ: {e}")
        finally:
            for f in ["raw_upload.mp4", "raw_upload.mp3", "raw_upload.wav", "audio.mp3", "subs.ass", "concat_list.txt", "bg_combined.mp4"]:
                if os.path.exists(f): os.remove(f)
            if 'scenes_data' in locals():
                for scene in scenes_data:
                    if os.path.exists(f"clip_{scene['idx']}.mp4"): os.remove(f"clip_{scene['idx']}.mp4")
            if 'segments_data_for_subs' in locals():
                for idx, _, _, _ in segments_data_for_subs:
                    if os.path.exists(f"seg_{idx}.mp3"): os.remove(f"seg_{idx}.mp3")
            if 'custom_broll_paths' in locals():
                for path in custom_broll_paths:
                    if os.path.exists(path): os.remove(path)
