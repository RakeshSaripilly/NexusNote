import fitz
import pytesseract
from PIL import Image
import io
import uuid
import re

def chunk_text(text,chunk_size=3,overlap=1):
    clean_text=re.sub(r'\s+', ' ', text).strip()
    if not clean_text:
        return []
    sentences=[s.strip() for s in re.split(r'(?<=[.!?]) +', clean_text) if len(s.strip())>5]

    if len(sentences) <= chunk_size:
        return ["".join(sentences)]

    chunks=[]
    while i<len(sentences):
        chunk=sentences[i:i+chunk_size]
        chunks.append(" ".join(chunk))
        i+=chunk_size-overlap
    return chunks
def parse_pdf(file_bytes,filename):
    doc=fitz.open(stream=file_bytes,filetype="pdf")
    results=[]

    for page_idx in range(len(doc)):
        page = doc[page_idx]
        text=page.get_text("text").strip()
        chunks=chunk_text(text)
        for chunk in chunks:
            results.append({
                "chunk_id":str(uuid.uuid4()),
                "text":chunk,
                "filename":filename,
                "page_number":page_idx+1,
                "location_tag":f"Page {page_idx+1}"
            })
    return results

def parse_txt(file_bytes,filename):
    text=file_bytes.decode("utf-8",errors="ignore").strip()
    chunks=chunk_text(text)
    return[{
                "chunk_id":str(uuid.uuid4()),
                "text":chunk,
                "filename":filename,
                "location_tag":"Document Note",
    }for chunk in chunks]

def parse_image(file_bytes,filename):
    image=Image.open(io.BytesIO(file_bytes))
    text=pytesseract.image_to_string(image).strip()
    chunks=chunk_text(text)
    return [{
        "chunk_id":str(uuid.uuid4()),
        "text":chunk,
        "filename":filename,
        "location_tag":"Image OCR"
    } for chunk in chunks]