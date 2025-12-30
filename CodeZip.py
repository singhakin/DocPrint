import zipfile
import io

# --- 1. Dockerfile: Gotenberg with Custom Fonts ---
dockerfile_content = """FROM gotenberg/gotenberg:8

USER root

# 1. Install Metric-Compatible Fonts
# liberation -> Arial/Times/Courier replacement
# crosextra-carlito -> Calibri replacement
# crosextra-caladea -> Cambria replacement
RUN apt-get update && apt-get install -y --no-install-recommends \\
    fonts-liberation \\
    fonts-crosextra-carlito \\
    fonts-crosextra-caladea \\
    fontconfig \\
    ttf-mscorefonts-installer && \\
    apt-get clean && rm -rf /var/lib/apt/lists/*

# 2. Apply Custom Font Mapping Rules
COPY local.conf /etc/fonts/local.conf
RUN fc-cache -f -v

USER gotenberg"""

# --- 2. docker-compose.yml ---
docker_compose_content = """services:
  # The Conversion Engine
  gotenberg:
    build: .
    restart: always
    ports:
      - "3000:3000"

  # Your Logic / API Layer
  print_api:
    image: python:3.11-slim
    volumes:
      - .:/app
    working_dir: /app
    command: sh -c "pip install -r requirements.txt && uvicorn main:app --host 0.0.0.0 --port 8000"
    ports:
      - "8000:8000"
    depends_on:
      - gotenberg
    environment:
      - GOTENBERG_URL=http://gotenberg:3000/forms/libreoffice/convert
      - EXTERNAL_AV_URL=http://av-team-service/scan
      - DB_CONNECTION_STRING=sqlite:///./analytics.db

  # Optional: Simple DB for local testing
  # In prod, replace connection string with your actual Postgres/MySQL URI"""

# --- 3. local.conf: The Font Mapping Brain ---
local_conf_content = """<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig>
  <match target="pattern">
    <test name="family"><string>Calibri</string></test>
    <edit name="family" mode="assign" binding="same"><string>Carlito</string></edit>
  </match>
  <match target="pattern">
    <test name="family"><string>Cambria</string></test>
    <edit name="family" mode="assign" binding="same"><string>Caladea</string></edit>
  </match>
  <match target="pattern">
    <test name="family"><string>Arial</string></test>
    <edit name="family" mode="assign" binding="same"><string>Liberation Sans</string></edit>
  </match>
  <match target="pattern">
    <test name="family"><string>Times New Roman</string></test>
    <edit name="family" mode="assign" binding="same"><string>Liberation Serif</string></edit>
  </match>
</fontconfig>"""

# --- 4. main.py: The Orchestrator ---
main_py_content = """import os
import io
import zipfile
import httpx
import fitz  # PyMuPDF
import xml.etree.ElementTree as ET
from datetime import datetime
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import logging

# --- Configuration ---
app = FastAPI(title="Print Service Orchestrator")
GOTENBERG_URL = os.getenv("GOTENBERG_URL", "http://localhost:3000/forms/libreoffice/convert")
# Replace with the actual URL provided by your AV team
EXTERNAL_AV_URL = os.getenv("EXTERNAL_AV_URL", "https://av-service.internal/v1/scan") 

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Helper: External AV Check ---
async def verify_clean_status(file_content: bytes, filename: str):
    # This simulates the call to your other team's service.
    # Adjust payload/headers to match their API contract.
    try:
        # Example: MOCKING a clean response for now. 
        # Uncomment below to make real call:
        '''
        async with httpx.AsyncClient() as client:
            files = {'file': (filename, file_content)}
            resp = await client.post(EXTERNAL_AV_URL, files=files, timeout=10.0)
            if resp.status_code != 200 or resp.json().get('status') != 'clean':
                 return False
            return True
        '''
        return True # Mock pass
    except Exception as e:
        logger.error(f"AV Service Unreachable: {e}")
        # Fail Secure: If AV is down, do not process
        raise HTTPException(status_code=503, detail="Security Service Unavailable")

# --- Helper: Font Analytics ---
def analyze_fidelity(source_bytes: bytes, filename: str, pdf_bytes: bytes):
    requested_fonts = []
    
    # 1. Extract requested fonts (only works for .docx)
    if filename.endswith(".docx"):
        try:
            with zipfile.ZipFile(io.BytesIO(source_bytes)) as z:
                with z.open('word/fontTable.xml') as f:
                    tree = ET.fromstring(f.read())
                    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
                    requested_fonts = [el.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}name') 
                                       for el in tree.findall('.//w:font', ns)]
        except Exception:
            pass # Not critical if parsing fails

    # 2. Extract actual fonts from PDF
    actual_fonts = set()
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for page in doc:
            for f in page.get_fonts():
                # Format: (xref, ext, type, basefont, name, encoding...)
                # Clean 'ABCDEF+Carlito' -> 'Carlito'
                font_name = f[3].split('+')[-1]
                actual_fonts.add(font_name)
    except Exception:
        pass

    # 3. Determine Fidelity
    # Simple logic: If Carlito is used, it was likely a substitute for Calibri
    was_substituted = any(f in ["Carlito", "Caladea", "LiberationSans"] for f in actual_fonts)
    
    return {
        "requested": list(set(requested_fonts)),
        "actual": list(actual_fonts),
        "substitution_occurred": was_substituted
    }

# --- Main Endpoint ---
@app.post("/process-document")
async def process_document(file: UploadFile = File(...)):
    filename = file.filename
    content = await file.read()

    # STEP 1: Security Gate (External AV)
    is_clean = await verify_clean_status(content, filename)
    if not is_clean:
        raise HTTPException(status_code=400, detail="Security Alert: Malware Detected")

    # STEP 2: Conversion (Gotenberg)
    async with httpx.AsyncClient() as client:
        files = {'files': (filename, content)}
        # We use LibreOffice for all office/rtf/txt formats
        try:
            resp = await client.post(GOTENBERG_URL, files=files, timeout=60.0)
        except httpx.ReadTimeout:
             raise HTTPException(status_code=504, detail="Conversion Timed Out")

    if resp.status_code != 200:
        logger.error(f"Gotenberg Error: {resp.text}")
        raise HTTPException(status_code=500, detail="Conversion Engine Failed")

    pdf_content = resp.content

    # STEP 3: Analytics (Fire and Forget or Log)
    analytics = analyze_fidelity(content, filename, pdf_content)
    logger.info(f"JOB_AUDIT: {analytics}")
    
    # In production, INSERT 'analytics' into your DB here

    # STEP 4: Return PDF
    return StreamingResponse(
        io.BytesIO(pdf_content), 
        media_type="application/pdf",
        headers={"X-Fidelity-Status": "Substituted" if analytics['substitution_occurred'] else "Exact"}
    )
"""

# --- 5. requirements.txt ---
requirements_content = """fastapi
uvicorn
python-multipart
httpx
pymupdf
"""

# --- Zip Generation ---
files_map = {
    "Dockerfile": dockerfile_content,
    "docker-compose.yml": docker_compose_content,
    "main.py": main_py_content,
    "local.conf": local_conf_content,
    "requirements.txt": requirements_content
}

zip_filename = "print_service_v2_final.zip"
with zipfile.ZipFile(zip_filename, 'w') as z:
    for fname, fcontent in files_map.items():
        z.writestr(fname, fcontent)

print(f"Successfully generated {zip_filename}. Unzip and run 'docker-compose up --build'")
