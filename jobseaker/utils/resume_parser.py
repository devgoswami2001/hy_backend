import json
import re
import os
from datetime import datetime
from django.contrib.auth.models import User
from django.utils.dateparse import parse_date
from django.conf import settings
from openai import OpenAI

# Initialize OpenAI client
client = OpenAI(api_key=settings.OPENAI_API_KEY)

# Import Django models
from ..models import JobSeekerProfile, Resume


class ResumeParser:
    """Resume parsing utility for Django"""
    
    def __init__(self):
        self.client = client
    
    def read_resume(self, file_path):
        """Read resume text from pdf/docx/txt"""
        if file_path.endswith(".txt"):
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
        elif file_path.endswith(".pdf"):
            from PyPDF2 import PdfReader
            reader = PdfReader(file_path)
            return " ".join([page.extract_text() for page in reader.pages if page.extract_text()])
        elif file_path.endswith(".docx"):
            import docx
            doc = docx.Document(file_path)
            return " ".join([para.text for para in doc.paragraphs if para.text.strip()])
        else:
            raise ValueError("Unsupported file format. Use .txt, .pdf, or .docx")

    def ask_openai(self, resume_text, model="gpt-4o-mini"):
        """Ask OpenAI to parse resume into JSON"""
        response = self.client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a resume parser. Extract information and return ONLY valid JSON matching the specified schema. No markdown, no explanations, no additional text."},
                {"role": "user", "content": f"""
Parse this resume text and extract information into the following JSON structure:

{{
  "jobseeker_profile": {{
    "first_name": "",
    "last_name": "",
    "date_of_birth": "YYYY-MM-DD or null",
    "gender": "male|female|other|prefer_not_to_say or empty",
    "phone_number": "",
    "address_line_1": "",
    "city": "",
    "state": "",
    "country": "",
    "postal_code": "",
    "headline": "",
    "summary": "",
    "job_status": "actively_looking|open_to_opportunities|not_looking|employed",
    "preferred_job_types": [],
    "preferred_locations": [],
    "expected_salary": null,
    "willing_to_relocate": false,
    "linkedin_url": "",
    "portfolio_url": ""
  }},
  "resume": {{
    "title": "",
    "experience_level": "fresher|junior|mid_level|senior|lead|executive",
    "total_experience_years": 0,
    "total_experience_months": 0,
    "current_company": "",
    "current_designation": "",
    "current_salary": null,
    "notice_period": "immediate|15_days|1_month|2_months|3_months",
    "education_data": [],
    "work_experience_data": [],
    "skills_data": [],
    "certifications_data": [],
    "projects_data": [],
    "languages_data": [],
    "achievements_data": [],
    "keywords": []
  }}
}}

Instructions:
- Extract all available information from the resume
- Use null for missing numeric values, empty strings for missing text
- For dates, use "YYYY-MM" format or null if not available
- Skills should be categorized as technical, soft, or language skills
- Keywords should include relevant job-related terms from the resume
- Calculate total experience from work history if not explicitly mentioned
- Infer experience level based on total years of experience

Resume Text:
{resume_text}
"""}
            ],
            temperature=0,
            response_format={"type": "json_object"}
        )
        return response.choices[0].message.content

    def save_to_django_models(self, parsed_data, user):
        """Save parsed resume data to Django models"""
        profile_data = parsed_data.get('jobseeker_profile', {})
        resume_data = parsed_data.get('resume', {})
        
        # Create/Update JobSeekerProfile
        profile, created = JobSeekerProfile.objects.get_or_create(
            user=user,
            defaults={
                'first_name': profile_data.get('first_name', ''),
                'last_name': profile_data.get('last_name', ''),
                'date_of_birth': parse_date(profile_data.get('date_of_birth')) if profile_data.get('date_of_birth') else None,
                'gender': profile_data.get('gender', ''),
                'phone_number': profile_data.get('phone_number', ''),
                'address_line_1': profile_data.get('address_line_1', ''),
                'city': profile_data.get('city', ''),
                'state': profile_data.get('state', ''),
                'country': profile_data.get('country', ''),
                'postal_code': profile_data.get('postal_code', ''),
                'headline': profile_data.get('headline', ''),
                'summary': profile_data.get('summary', ''),
                'job_status': profile_data.get('job_status', 'actively_looking'),
                'preferred_job_types': profile_data.get('preferred_job_types', []),
                'preferred_locations': profile_data.get('preferred_locations', []),
                'expected_salary': profile_data.get('expected_salary'),
                'willing_to_relocate': profile_data.get('willing_to_relocate', False),
                'linkedin_url': profile_data.get('linkedin_url', ''),
                'portfolio_url': profile_data.get('portfolio_url', ''),
            }
        )
        
        # Create Resume
        resume = Resume.objects.create(
            profile=profile,
            title=resume_data.get('title', f"{profile.first_name} {profile.last_name} Resume"),
            is_default=True,
            experience_level=resume_data.get('experience_level', 'fresher'),
            total_experience_years=resume_data.get('total_experience_years', 0),
            total_experience_months=resume_data.get('total_experience_months', 0),
            current_company=resume_data.get('current_company', ''),
            current_designation=resume_data.get('current_designation', ''),
            current_salary=resume_data.get('current_salary'),
            notice_period=resume_data.get('notice_period', ''),
            education_data=resume_data.get('education_data', []),
            work_experience_data=resume_data.get('work_experience_data', []),
            skills_data=resume_data.get('skills_data', []),
            certifications_data=resume_data.get('certifications_data', []),
            projects_data=resume_data.get('projects_data', []),
            languages_data=resume_data.get('languages_data', []),
            achievements_data=resume_data.get('achievements_data', []),
            keywords=resume_data.get('keywords', [])
        )
        
        resume.calculate_completion()
        resume.save()
        
        return profile, resume

    def parse_resume_file(self, file_path, user):
        """Main method to parse resume and save to database"""
        resume_text = self.read_resume(file_path)
        
        # Parse with OpenAI
        try:
            output = self.ask_openai(resume_text, model="gpt-4o-mini")
            parsed_data = json.loads(output)
        except Exception as e:
            # Fallback to GPT-4
            output = self.ask_openai(resume_text, model="gpt-4o")
            parsed_data = json.loads(output)
        
        # Save to database
        profile, resume = self.save_to_django_models(parsed_data, user)
        
        return profile, resume, parsed_data
