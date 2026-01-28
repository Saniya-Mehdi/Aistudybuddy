from fastapi import FastAPI, Request, UploadFile, File, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import PyPDF2
from pdf2image import convert_from_bytes
import pytesseract
import io
import uuid
import os
import platform
import requests

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

# Tesseract configuration
if platform.system() == "Windows":
    pytesseract.pytesseract.tesseract_cmd = r"C:\Users\saniy\Downloads\tesseract.exe"
# On Linux/Render, Tesseract will be installed via apt and no path needed

templates = Jinja2Templates(directory="templates")
progress_status = {}  # file_id -> status
CHUNK_SIZE = 500

# Get Gemini API key from environment variable
gemini_key = os.getenv("GEMINI_API_KEY")

# ---------------- AI FUNCTIONS ---------------- #

def generate_summary(text: str) -> str:
    prompt = f"Summarize this document for a student:\n\n{text}"
    try:
        headers = {"Authorization": f"Bearer {gemini_key}"}
        data = {
            "prompt": prompt,
            "max_tokens": 500
        }
        response = requests.post("https://api.gemini.ai/v1/completions", headers=headers, json=data)
        if response.status_code == 200:
            return response.json()["choices"][0]["text"]
        else:
            return f"Error generating summary: {response.text}"
    except Exception as e:
        return f"Error generating summary: {e}"

def generate_mcqs(text: str) -> str:
    prompt = f"Generate 5 multiple-choice questions with answers from this document:\n\n{text}"
    try:
        headers = {"Authorization": f"Bearer {gemini_key}"}
        data = {
            "prompt": prompt,
            "max_tokens": 500
        }
        response = requests.post("https://api.gemini.ai/v1/completions", headers=headers, json=data)
        if response.status_code == 200:
            return response.json()["choices"][0]["text"]
        else:
            return f"Error generating MCQs: {response.text}"
    except Exception as e:
        return f"Error generating MCQs: {e}"

# ---------------- PDF PROCESSING ---------------- #

def process_pdf(file_bytes: bytes, file_id: str):
    try:
        reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
        text = ""
        total_pages = len(reader.pages)

        # Extract text
        for i, page in enumerate(reader.pages, start=1):
            extracted = page.extract_text()
            if extracted:
                text += extracted
            progress_status[file_id] = f"Extracting text: {i}/{total_pages} pages"

        # OCR fallback if no text
        if not text.strip():
            images = convert_from_bytes(file_bytes)
            for i, img in enumerate(images, start=1):
                text += pytesseract.image_to_string(img)
                progress_status[file_id] = f"OCR processing: {i}/{len(images)} images"

        # AI summary
        progress_status[file_id] = "Generating summary..."
        summary = generate_summary(text)

        # AI MCQs
        progress_status[file_id] = "Generating MCQs..."
        mcqs = generate_mcqs(text)

        progress_status[file_id] = "Completed"
        progress_status[f"{file_id}_summary"] = summary
        progress_status[f"{file_id}_mcqs"] = mcqs

    except Exception as e:
        progress_status[file_id] = f"Error: {e}"
        progress_status[f"{file_id}_summary"] = "Error occurred"
        progress_status[f"{file_id}_mcqs"] = ""

# ---------------- ROUTES ---------------- #

@app.get("/", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
def login_user():
    return RedirectResponse("/dashboard", status_code=303)

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_page(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})

@app.post("/upload_pdf", response_class=HTMLResponse)
async def upload_pdf(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...)
):
    file_bytes = await file.read()
    file_id = str(uuid.uuid4())

    background_tasks.add_task(process_pdf, file_bytes, file_id)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "file_id": file_id,
            "filename": file.filename
        }
    )

@app.get("/progress/{file_id}")
def get_progress(file_id: str):
    return {
        "status": progress_status.get(file_id, "Not started"),
        "summary": progress_status.get(f"{file_id}_summary", ""),
        "mcqs": progress_status.get(f"{file_id}_mcqs", "")
    }
