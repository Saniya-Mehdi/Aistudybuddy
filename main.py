
from fastapi import FastAPI, Request, UploadFile, File, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import PyPDF2
from pdf2image import convert_from_bytes
import pytesseract
import io
import uuid
from fastapi.staticfiles import StaticFiles
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

# IMPORTANT: set correct tesseract path
pytesseract.pytesseract.tesseract_cmd = r"C:\Users\saniy\Downloads\tesseract.exe"


templates = Jinja2Templates(directory="templates")

progress_status = {}  # file_id -> status
CHUNK_SIZE = 500


# -------- DEMO AI HELPERS -------- #

def demo_summary(text: str) -> str:
    return (
        "This document explains the key concepts discussed in the uploaded PDF. "
        "It highlights important ideas, definitions, and examples that help "
        "students understand the topic more effectively."
    )


def demo_mcqs(text: str) -> str:
    return """1. What is the main purpose of this document?
A) Entertainment
B) Education ✅
C) Advertisement
D) Navigation

2. Which method is commonly used to improve understanding?
A) Memorization
B) Visualization
C) Explanation of concepts ✅
D) Guessing

3. What is the benefit of structured content?
A) Confusion
B) Faster learning ✅
C) Errors
D) Repetition

4. What type of audience is this document best suited for?
A) Researchers
B) Students ✅
C) Gamers
D) Artists

5. Why are examples useful?
A) They increase length
B) They clarify ideas ✅
C) They distract readers
D) They replace theory
"""


# -------- PDF PROCESSING -------- #

def process_pdf(file_bytes: bytes, file_id: str):
    try:
        reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
        text = ""
        total_pages = len(reader.pages)

        for i, page in enumerate(reader.pages, start=1):
            extracted = page.extract_text()
            if extracted:
                text += extracted
            progress_status[file_id] = f"Extracting text: {i}/{total_pages} pages"

        # OCR fallback
        if not text.strip():
            images = convert_from_bytes(file_bytes)
            for i, img in enumerate(images, start=1):
                text += pytesseract.image_to_string(img)
                progress_status[file_id] = f"OCR processing: {i}/{len(images)} images"

        progress_status[file_id] = "Generating summary..."
        summary = demo_summary(text)

        progress_status[file_id] = "Generating MCQs..."
        mcqs = demo_mcqs(text)

        progress_status[file_id] = "Completed"
        progress_status[f"{file_id}_summary"] = summary
        progress_status[f"{file_id}_mcqs"] = mcqs

    except Exception as e:
        progress_status[file_id] = f"Error: {e}"
        progress_status[f"{file_id}_summary"] = "Error occurred"
        progress_status[f"{file_id}_mcqs"] = ""


# -------- ROUTES -------- #

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
