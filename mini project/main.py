# app/main.py
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, File, UploadFile, HTTPException
from pydantic import BaseModel

# transcription & LLM libraries
import whisper
import openai  # used for summary + quiz generation

# CONFIG - set env vars OPENAI_API_KEY before running
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
openai.api_key = OPENAI_API_KEY

# where to store uploads
BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Video → Notes → Quiz MVP")

# load whisper model once (choose "small" or "medium" for speed/quality)
WHISPER_MODEL = whisper.load_model("small")


class QuizItem(BaseModel):
    question: str
    options: list[str]
    answer_index: int
    explanation: Optional[str] = None


@app.post("/upload-video/")
async def upload_video(file: UploadFile = File(...)):
    # save incoming file
    filename = UPLOAD_DIR / file.filename
    with open(filename, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # extract audio (wav) via ffmpeg
    audio_path = UPLOAD_DIR / (file.filename + ".wav")
    ffmpeg_cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(filename),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        "-ac",
        "1",
        str(audio_path),
    ]
    try:
        subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"ffmpeg failed: {e.stderr.decode()}")

    # transcribe using whisper
    result = WHISPER_MODEL.transcribe(str(audio_path))
    transcript = result.get("text", "").strip()

    return {"filename": file.filename, "transcript": transcript}


@app.post("/generate-notes/")
async def generate_notes(transcript: str):
    """
    Use OpenAI (chat) to create concise notes and a summary.
    If OPENAI_API_KEY is not set, return simple heuristics.
    """
    if not transcript or len(transcript) < 5:
        raise HTTPException(status_code=400, detail="Transcript too short")

    if not OPENAI_API_KEY:
        # fallback simple split heuristics
        lines = [l.strip() for l in transcript.split(".") if l.strip()]
        summary = " ".join(lines[:3])
        notes = [l for l in lines[:10]]
        return {"summary": summary, "notes": notes}

    # prompt for summary + notes (structured JSON output)
    system = "You are an assistant that creates concise lecture notes and a 2-3 sentence summary."
    user = (
        "Transcript:\n"
        f"{transcript}\n\n"
        "Produce a JSON object with fields:\n"
        "summary: a 2-3 sentence concise summary\n"
        "notes: an array of bullet points (short sentences) covering main points in order\n"
        "key_terms: a short array of important terms (5-10)\n\n"
        "Return only valid JSON."
    )

    resp = openai.ChatCompletion.create(
        model="gpt-4o-mini",  # replace if not available; use "gpt-4" or "gpt-3.5-turbo" if needed
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=800,
        temperature=0.2,
    )

    content = resp["choices"][0]["message"]["content"]
    # simple attempt to parse JSON from model output
    import json
    try:
        data = json.loads(content)
    except Exception:
        # fallback: try to find a JSON object inside the content
        import re
        match = re.search(r"(\{.*\})", content, flags=re.DOTALL)
        if not match:
            raise HTTPException(status_code=500, detail="LLM did not return JSON")
        data = json.loads(match.group(1))

    return data


@app.post("/generate-quiz/")
async def generate_quiz(notes: list[str], num_questions: int = 5):
    """
    Create multiple-choice quiz items from notes.
    Returns list of QuizItem.
    """
    if not notes:
        raise HTTPException(status_code=400, detail="Notes required")

    # if no API key, simple heuristic quiz
    if not OPENAI_API_KEY:
        items = []
        for i, n in enumerate(notes[:num_questions]):
            items.append(
                {
                    "question": f"What is the main point of: '{n}'?",
                    "options": [n, "Not applicable", "Another point", "Irrelevant"],
                    "answer_index": 0,
                    "explanation": "Heuristic fallback answer",
                }
            )
        return {"quiz": items}

    # build prompt
    notes_text = "\n".join(f"- {n}" for n in notes)
    user_prompt = (
        f"Create {num_questions} multiple-choice questions from the following notes.\n\nNotes:\n{notes_text}\n\n"
        "Requirements:\n"
        "- Each question must have 4 options.\n"
        "- Provide 'answer_index' (0-based) and a short explanation for the correct answer.\n"
        "- Return pure JSON: {\"quiz\": [{question, options, answer_index, explanation}, ...]}"
    )

    resp = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": "You generate multiple-choice quizzes."}, {"role": "user", "content": user_prompt}],
        temperature=0.3,
        max_tokens=800,
    )
    content = resp["choices"][0]["message"]["content"]

    import json, re
    try:
        data = json.loads(content)
    except Exception:
        match = re.search(r"(\{.*\})", content, flags=re.DOTALL)
        if not match:
            raise HTTPException(status_code=500, detail="LLM did not return JSON")
        data = json.loads(match.group(1))

    return data


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
