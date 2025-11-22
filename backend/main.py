import subprocess, os, json, shutil, tempfile
from typing import Optional, List
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import requests

load_dotenv()
app = FastAPI()

# --- CONFIG ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OLLAMA_HOST = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434")
OLLAMA_API = f"{OLLAMA_HOST}/api/generate"
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral")

# Initialize OpenAI Client
try:
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
except ImportError:
    client = None

# Initialize yt-dlp
try:
    import yt_dlp
except ImportError:
    yt_dlp = None

# --- DATA MODELS (Optional, but good for documentation) ---
class QuizItem(BaseModel):
    question: str
    options: List[str]
    answer: str

class ProcessResponse(BaseModel):
    summary: str
    notes: str
    quiz: List[QuizItem]

# --- HELPERS ---

def download_media(url: str, out_dir: str) -> str:
    if not yt_dlp: raise RuntimeError("yt-dlp not installed")
    opts = {
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(out_dir, '%(id)s.%(ext)s'),
        'quiet': True,
        'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}],
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])
        for f in os.listdir(out_dir):
            if f.endswith('.mp3'): return os.path.join(out_dir, f)
    raise RuntimeError("Download failed")

def generate_content(transcript: str, mode: str):
    # We ask for a single JSON object containing all 3 parts
    system_prompt = """
    You are an expert AI tutor. Your task is to process a video transcript and output a single valid JSON object.
    
    The JSON object must strictly follow this schema:
    {
        "summary": "A concise executive summary (4-6 sentences).",
        "notes": "Detailed bullet points using markdown formatting (e.g., - Point\\n  - Sub-point). Includes definitions and examples.",
        "quiz": [
            {
                "question": "Question text?",
                "options": ["Option A", "Option B", "Option C", "Option D"],
                "answer": "Option A"
            },
            ... (3 questions total)
        ]
    }
    
    Ensure the 'answer' field in the quiz matches exactly one of the strings in 'options'.
    Do not include markdown code blocks (like ```json). Just return the raw JSON string.
    """
    
    # Truncate to avoid context limits
    user_prompt = f"TRANSCRIPT:\n{transcript[:14000]}" 

    try:
        if mode == "cloud" and client:
            # OpenAI JSON Mode
            completion = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"} # Forces valid JSON
            )
            raw_content = completion.choices[0].message.content
            return json.loads(raw_content)
        
        else: 
            # Ollama JSON Mode
            payload = {
                "model": OLLAMA_MODEL,
                "prompt": system_prompt + "\n\n" + user_prompt,
                "stream": False,
                "format": "json", # Forces valid JSON
                "options": {"temperature": 0.3, "num_ctx": 8192} 
            }
            res = requests.post(OLLAMA_API, json=payload, timeout=300)
            res.raise_for_status()
            return json.loads(res.json()["response"])

    except json.JSONDecodeError:
        # Fallback if AI fails to generate valid JSON
        return {
            "summary": "Error parsing AI response.", 
            "notes": "The AI generated an invalid format.", 
            "quiz": []
        }
    except Exception as e:
        return {
            "summary": f"System Error: {str(e)}", 
            "notes": "", 
            "quiz": []
        }

# --- ENDPOINTS ---

@app.post("/transcribe")
async def transcribe_endpoint(
    file: Optional[UploadFile] = File(None), 
    url: Optional[str] = Form(None),
    transcription_mode: str = Form("local")
):
    temp_dir = tempfile.mkdtemp()
    try:
        if url: path = download_media(url, temp_dir)
        elif file:
            path = os.path.join(temp_dir, file.filename)
            with open(path, "wb") as f: shutil.copyfileobj(file.file, f)
        else: raise HTTPException(400, "No input")

        # Transcription Logic
        if transcription_mode == "cloud" and client:
            with open(path, "rb") as f: 
                res = client.audio.transcriptions.create(model="whisper-1", file=f)
                text = res.text
        else:
            # Local Whisper
            subprocess.run(["whisper", path, "--model", "base", "--output_format", "txt", "--output_dir", temp_dir], check=True)
            for f in os.listdir(temp_dir):
                 if f.endswith(".txt"): 
                     with open(os.path.join(temp_dir, f), "r") as txt: text = txt.read()
                     break
            else: text = "Transcription failed or empty."

        return {"text": text}
    except Exception as e:
        print(e)
        raise HTTPException(500, str(e))
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

@app.post("/process_content")
async def process_content_endpoint(
    transcript: str = Form(...), 
    summarization_mode: str = Form(...)
):
    data = generate_content(transcript, summarization_mode)
    return data