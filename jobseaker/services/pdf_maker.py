from __future__ import annotations

import os
from io import BytesIO
from typing import Any, Dict
from dataclasses import dataclass

from django.conf import settings
from django.core.files.base import ContentFile
from django.utils.html import escape
from openai import OpenAI
from xhtml2pdf import pisa

@dataclass
class ProfileStub:
    first_name: str
    last_name: str
    headline: str | None = None
    summary: str | None = None
    phone_number: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    user: Any | None = None

def create_resume_pdf_via_openai(resume_instance, model: str = "gpt-4o-mini") -> str:
    """Generate resume PDF using OpenAI → xhtml2pdf"""
    
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    profile = resume_instance.profile

    payload: Dict[str, Any] = {
        "name": f"{safe(profile.first_name)} {safe(profile.last_name)}",
        "headline": safe(getattr(profile, "headline", "")),
        "summary": safe(getattr(profile, "summary", "")),
        "contact": {
            "email": safe(getattr(getattr(profile, "user", None), "email", "")),
            "phone": safe(getattr(profile, "phone_number", "")),
            "location": ", ".join([p for p in [getattr(profile, "city", None), getattr(profile, "state", None), getattr(profile, "country", None)] if p]),
        },
        "experience": ensure_list(getattr(resume_instance, "work_experience_data", [])),
        "skills": ensure_list(getattr(resume_instance, "skills_data", [])),
        "education": ensure_list(getattr(resume_instance, "education_data", [])),
        "projects": ensure_list(getattr(resume_instance, "projects_data", [])),
        "certifications": ensure_list(getattr(resume_instance, "certifications_data", [])),
        "achievements": ensure_list(getattr(resume_instance, "achievements_data", [])),
        "languages": ensure_list(getattr(resume_instance, "languages_data", [])),
    }

    system = (
        "Output ONLY valid HTML with inline CSS. Use @page for PDF margins. "
        "No external fonts. System fonts only. Simple layout, 1-2 pages max."
    )

    user_prompt = f"""
Create modern resume HTML with inline CSS. Use @page {{ margin: 1in; }} for PDF.
Colors: #2C3E50, #3498DB, #BDC3C7. Simple layout, no complex CSS Grid.
Sections: Header, Summary, Experience, Skills, Education, Projects, Certifications, Achievements, Languages.
JSON DATA: {payload}
"""

    resp = client.chat.completions.create(
        model=model,
        temperature=0.2,
        max_tokens=2200,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_prompt},
        ],
    )

    html = resp.choices[0].message.content or ""

    # Generate PDF with xhtml2pdf
    pdf_buffer = BytesIO()
    pisa_status = pisa.CreatePDF(html, dest=pdf_buffer)
    
    if pisa_status.err:
        # Fallback to static HTML if OpenAI fails
        html = build_static_html(payload)
        pdf_buffer = BytesIO()
        pisa.CreatePDF(html, dest=pdf_buffer)

    pdf_bytes = pdf_buffer.getvalue()
    pdf_buffer.close()

    filename = f"{safe(profile.first_name)}_{safe(profile.last_name)}_resume.pdf".replace(" ", "_")
    resume_instance.resume_pdf.save(filename, ContentFile(pdf_bytes), save=False)

    return resume_instance.resume_pdf.url

def safe(v: Any) -> str:
    return "" if v is None else escape(str(v))

def ensure_list(v: Any) -> list:
    if v is None:
        return []
    if isinstance(v, list):
        return v
    try:
        import json
        return json.loads(v)
    except:
        return [v]

def build_static_html(payload: Dict[str, Any]) -> str:
    """Fallback static HTML"""
    name = payload.get("name", "")
    headline = payload.get("headline", "")
    contact = payload.get("contact", {})
    
    return f"""<!DOCTYPE html>
<html>
<head>
<style>
@page {{ margin: 1in; }}
body {{ font-family: Arial, sans-serif; line-height: 1.4; color: #2C3E50; }}
h1 {{ color: #2C3E50; margin: 0; }}
h2 {{ color: #3498DB; border-bottom: 2px solid #3498DB; padding-bottom: 4px; }}
.header {{ text-align: center; margin-bottom: 20px; }}
.section {{ margin-bottom: 15px; }}
</style>
</head>
<body>
<div class="header">
<h1>{name}</h1>
<p>{headline}</p>
<p>{contact.get('email','')} • {contact.get('phone','')} • {contact.get('location','')}</p>
</div>
<div class="section">
<h2>Summary</h2>
<p>{payload.get('summary','')}</p>
</div>
</body>
</html>"""
