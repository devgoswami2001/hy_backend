import json
import time
import re
import logging
from typing import Dict, Any, Optional
from django.utils import timezone
from django.conf import settings
from django.core.exceptions import ValidationError
from employer.models import JobPost
from jobseaker.models import JobSeekerProfile, Resume, AIRemarks
from openai import OpenAI
from openai.types.chat import ChatCompletion


# Configure logging
logger = logging.getLogger(__name__)

# Initialize OpenAI client
client = OpenAI(api_key=settings.OPENAI_API_KEY)

# Constants
AI_MODEL_VERSION = "gpt-4o-mini"
DEFAULT_TEMPERATURE = 0.3
MAX_RETRIES = 3
TIMEOUT_SECONDS = 60

PROMPT_TEMPLATE = """
You are an expert recruitment assistant AI.

I will give you:
1. A Job Post (title, description, required skills, location, experience level, salary range).
2. A Candidate Profile (personal info, job preferences).
3. A Resume (skills, education, work experience, certifications, projects).

Your task:
- Compare candidate and job requirements comprehensively.
- Score skills, experience, education, and location compatibility (0-100).
- Provide overall fit score (0-100).
- Determine if candidate is a good fit (true/false).
- Recommend for interview or not.
- Highlight candidate strengths, weaknesses, missing skills, and matching skills.
- Suggest 3-5 tailored interview questions.
- Write a concise AI remark (2–3 sentences).

CRITICAL: Output ONLY valid JSON without any markdown formatting, code blocks, or additional text.

Required JSON schema:
{
  "fit_score": float (0-100),
  "fit_level": "excellent" | "good" | "moderate" | "poor",
  "is_fit": boolean,
  "skills_match_score": float (0-100),
  "experience_match_score": float (0-100),
  "education_match_score": float (0-100),
  "location_match_score": float (0-100),
  "remarks": string (2-3 sentences),
  "strengths": array of strings,
  "weaknesses": array of strings,
  "missing_skills": array of strings,
  "matching_skills": array of strings,
  "recommendations": array of strings,
  "interview_recommendation": boolean,
  "suggested_interview_questions": array of strings (3-5 items),
  "potential_concerns": array of strings,
  "salary_expectation_alignment": "aligned" | "too_high" | "too_low" | "unknown"
}
"""


class AIMatcherException(Exception):
    """Custom exception for AI Matcher errors."""
    pass


class JobAIAnalyzer:
    """
    Production-ready OpenAI-powered analysis of job vs candidate matching.
    
    Features:
    - Comprehensive error handling
    - Retry logic for transient failures
    - Robust JSON parsing with markdown cleanup
    - Detailed logging for debugging
    - Input validation
    - Performance monitoring
    """

    def __init__(self, job_post: JobPost, job_seeker: JobSeekerProfile, resume: Resume = None):
        self.job_post = job_post
        self.job_seeker = job_seeker
        self.resume = resume or self._get_default_resume()
        self._validate_inputs()

    def _get_default_resume(self) -> Optional[Resume]:
        """Get the default resume for the job seeker."""
        try:
            return self.job_seeker.resumes.filter(is_default=True).first()
        except Exception as e:
            logger.warning(f"Could not fetch default resume for job_seeker {self.job_seeker.id}: {e}")
            return None

    def _validate_inputs(self) -> None:
        """Validate required inputs before processing."""
        if not self.job_post:
            raise ValidationError("JobPost is required")
        if not self.job_seeker:
            raise ValidationError("JobSeekerProfile is required")
        if not self.job_post.title or not self.job_post.description:
            raise ValidationError("Job post must have title and description")

    def _prepare_job_data(self) -> Dict[str, Any]:
        """Prepare job post data for AI analysis."""
        return {
            "title": self.job_post.title or "",
            "description": self.job_post.description or "",
            "required_skills": self.job_post.required_skills or [],
            "location": self.job_post.location or "",
            "experience_level": self.job_post.experience_level or "",
            "salary_min": self.job_post.salary_min,
            "salary_max": self.job_post.salary_max,
            "job_type": getattr(self.job_post, 'job_type', ''),
            "company": getattr(self.job_post, 'company_name', ''),
        }

    def _prepare_profile_data(self) -> Dict[str, Any]:
        """Prepare job seeker profile data for AI analysis."""
        return {
            "name": self.job_seeker.full_name or "",
            "city": self.job_seeker.city or "",
            "preferred_roles": self.job_seeker.preferred_roles or [],
            "expected_salary": self.job_seeker.expected_salary,
            "experience_years": getattr(self.job_seeker, 'experience_years', 0),
            "availability": getattr(self.job_seeker, 'availability', ''),
        }

    def _prepare_resume_data(self) -> Dict[str, Any]:
        """Prepare resume data for AI analysis."""
        if not self.resume:
            return {
                "skills_data": [],
                "education_data": [],
                "work_experience_data": [],
                "certifications_data": [],
                "projects_data": [],
            }

        return {
            "skills_data": self.resume.skills_data or [],
            "education_data": self.resume.education_data or [],
            "work_experience_data": self.resume.work_experience_data or [],
            "certifications_data": self.resume.certifications_data or [],
            "projects_data": self.resume.projects_data or [],
        }

    def _clean_json_response(self, response: str) -> str:
        """
        Clean markdown formatting and extract JSON from OpenAI response.
        
        Handles various formats:
        - ``````
        - ``````
        - Raw JSON
        """
        if not response:
            raise AIMatcherException("Empty response from OpenAI")

        response = response.strip()

        # Try to find JSON content between code blocks
        json_match = re.search(r'``````', response, re.DOTALL)
        if json_match:
            return json_match.group(1).strip()

        
        response = re.sub(r'\s*```$', '', response, flags=re.MULTILINE)

        return response.strip()

    def _validate_ai_output(self, parsed_data: Dict[str, Any]) -> None:
        """Validate the structure and content of AI output."""
        required_fields = [
            'fit_score', 'fit_level', 'is_fit', 'skills_match_score',
            'experience_match_score', 'education_match_score', 'location_match_score',
            'remarks', 'strengths', 'weaknesses', 'missing_skills',
            'matching_skills', 'recommendations', 'interview_recommendation',
            'suggested_interview_questions', 'potential_concerns',
            'salary_expectation_alignment'
        ]

        for field in required_fields:
            if field not in parsed_data:
                raise AIMatcherException(f"Missing required field: {field}")

        # Validate score ranges
        score_fields = ['fit_score', 'skills_match_score', 'experience_match_score', 
                       'education_match_score', 'location_match_score']
        
        for field in score_fields:
            score = parsed_data.get(field)
            if not isinstance(score, (int, float)) or not (0 <= score <= 100):
                raise AIMatcherException(f"Invalid score for {field}: {score}")

        # Validate fit_level
        valid_fit_levels = ['excellent', 'good', 'moderate', 'poor']
        if parsed_data.get('fit_level') not in valid_fit_levels:
            raise AIMatcherException(f"Invalid fit_level: {parsed_data.get('fit_level')}")

        # Validate boolean fields
        boolean_fields = ['is_fit', 'interview_recommendation']
        for field in boolean_fields:
            if not isinstance(parsed_data.get(field), bool):
                raise AIMatcherException(f"Field {field} must be boolean")

    def _call_openai_api(self, input_text: str, retry_count: int = 0) -> str:
        """
        Call OpenAI API with retry logic for transient failures.
        """
        try:
            response: ChatCompletion = client.chat.completions.create(
                model=AI_MODEL_VERSION,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a professional recruitment AI assistant. Always return ONLY valid JSON without any markdown formatting, code blocks, or additional text."
                    },
                    {"role": "user", "content": input_text}
                ],
                temperature=DEFAULT_TEMPERATURE,
                timeout=TIMEOUT_SECONDS,
                max_tokens=2000,  # Reasonable limit for response size
            )

            raw_output = response.choices[0].message.content
            if not raw_output:
                raise AIMatcherException("Empty response from OpenAI API")

            return raw_output.strip()

        except Exception as e:
            logger.error(f"OpenAI API call failed (attempt {retry_count + 1}): {e}")
            
            if retry_count < MAX_RETRIES - 1:
                time.sleep(2 ** retry_count)  # Exponential backoff
                return self._call_openai_api(input_text, retry_count + 1)
            
            raise AIMatcherException(f"OpenAI API failed after {MAX_RETRIES} attempts: {e}")

    def _create_ai_remarks_object(self) -> AIRemarks:
        """Create and return initial AIRemarks object."""
        return AIRemarks(
            job_post=self.job_post,
            job_seeker=self.job_seeker,
            analysis_status=AIRemarks.AnalysisStatus.PENDING,
            ai_model_version=AI_MODEL_VERSION,
            created_at=timezone.now()
        )

    def _populate_ai_remarks(self, remarks: AIRemarks, parsed_data: Dict[str, Any], 
                           analysis_duration: float) -> None:
        """Populate AIRemarks object with parsed AI output."""
        remarks.is_fit = parsed_data.get("is_fit")
        remarks.fit_score = float(parsed_data.get("fit_score", 0))
        remarks.fit_level = parsed_data.get("fit_level", AIRemarks.FitLevel.UNKNOWN)
        remarks.skills_match_score = float(parsed_data.get("skills_match_score", 0))
        remarks.experience_match_score = float(parsed_data.get("experience_match_score", 0))
        remarks.education_match_score = float(parsed_data.get("education_match_score", 0))
        remarks.location_match_score = float(parsed_data.get("location_match_score", 0))
        remarks.remarks = parsed_data.get("remarks", "")
        remarks.strengths = parsed_data.get("strengths", [])
        remarks.weaknesses = parsed_data.get("weaknesses", [])
        remarks.missing_skills = parsed_data.get("missing_skills", [])
        remarks.matching_skills = parsed_data.get("matching_skills", [])
        remarks.recommendations = parsed_data.get("recommendations", [])
        remarks.interview_recommendation = parsed_data.get("interview_recommendation", False)
        remarks.suggested_interview_questions = parsed_data.get("suggested_interview_questions", [])
        remarks.potential_concerns = parsed_data.get("potential_concerns", [])
        remarks.salary_expectation_alignment = parsed_data.get("salary_expectation_alignment", "unknown")
        remarks.analysis_status = AIRemarks.AnalysisStatus.COMPLETED
        remarks.analyzed_at = timezone.now()
        remarks.confidence_score = 95  # Could be derived from OpenAI response if available
        remarks.analysis_duration_seconds = int(analysis_duration)

    def analyze(self) -> AIRemarks:
        """
        Perform comprehensive AI analysis of job-candidate matching.
        
        Returns:
            AIRemarks: Analysis results with scores, recommendations, and insights
            
        Raises:
            AIMatcherException: For analysis-specific errors
            ValidationError: For input validation errors
        """
        start_time = time.time()
        remarks = self._create_ai_remarks_object()

        try:
            logger.info(f"Starting AI analysis for job {self.job_post.id} and candidate {self.job_seeker.id}")

            # Prepare input data
            job_data = self._prepare_job_data()
            profile_data = self._prepare_profile_data()
            resume_data = self._prepare_resume_data()

            # Create input prompt
            input_text = PROMPT_TEMPLATE + f"""

Job Post Data:
{json.dumps(job_data, indent=2)}

Candidate Profile Data:
{json.dumps(profile_data, indent=2)}

Resume Data:
{json.dumps(resume_data, indent=2)}

Analyze this job-candidate match and return ONLY the JSON response as specified.
"""

            # Call OpenAI API
            raw_output = self._call_openai_api(input_text)
            logger.debug(f"Raw OpenAI response: {raw_output[:200]}...")

            # Clean and parse JSON response
            cleaned_output = self._clean_json_response(raw_output)
            
            try:
                parsed_data = json.loads(cleaned_output)
            except json.JSONDecodeError as e:
                logger.error(f"JSON parsing failed. Raw: {raw_output}")
                logger.error(f"Cleaned: {cleaned_output}")
                raise AIMatcherException(f"Invalid JSON from OpenAI: {e}")

            # Validate AI output structure
            self._validate_ai_output(parsed_data)

            # Calculate analysis duration
            analysis_duration = time.time() - start_time

            # Populate AIRemarks object
            self._populate_ai_remarks(remarks, parsed_data, analysis_duration)

            # Save to database
            remarks.save()

            logger.info(f"AI analysis completed successfully for job {self.job_post.id} "
                       f"and candidate {self.job_seeker.id}. Fit score: {remarks.fit_score}")

            return remarks

        except (AIMatcherException, ValidationError):
            # Re-raise known exceptions
            raise

        except Exception as e:
            # Handle unexpected errors
            error_msg = f"Unexpected error during AI analysis: {e}"
            logger.error(error_msg, exc_info=True)
            
            remarks.analysis_status = AIRemarks.AnalysisStatus.FAILED
            remarks.error_message = str(e)
            remarks.analysis_duration_seconds = int(time.time() - start_time)
            
            try:
                remarks.save()
            except Exception as save_error:
                logger.error(f"Failed to save error state to database: {save_error}")
            
            raise AIMatcherException(error_msg) from e


# Utility functions for batch processing
def analyze_multiple_candidates(job_post: JobPost, job_seekers: list[JobSeekerProfile]) -> list[AIRemarks]:
    """
    Analyze multiple candidates for a single job post.
    
    Args:
        job_post: The job post to match against
        job_seekers: List of job seeker profiles to analyze
        
    Returns:
        List of AIRemarks objects with analysis results
    """
    results = []
    
    for job_seeker in job_seekers:
        try:
            analyzer = JobAIAnalyzer(job_post, job_seeker)
            result = analyzer.analyze()
            results.append(result)
        except Exception as e:
            logger.error(f"Failed to analyze candidate {job_seeker.id}: {e}")
            # Continue with other candidates
            continue
    
    return results


def get_top_matches(job_post: JobPost, job_seekers: list[JobSeekerProfile], 
                   limit: int = 10) -> list[AIRemarks]:
    """
    Get top matching candidates for a job post, sorted by fit score.
    
    Args:
        job_post: The job post to match against
        job_seekers: List of job seeker profiles to analyze
        limit: Maximum number of top matches to return
        
    Returns:
        List of top AIRemarks objects sorted by fit score (descending)
    """
    results = analyze_multiple_candidates(job_post, job_seekers)
    
    # Filter successful analyses and sort by fit score
    successful_results = [r for r in results if r.analysis_status == AIRemarks.AnalysisStatus.COMPLETED]
    successful_results.sort(key=lambda x: x.fit_score, reverse=True)
    
    return successful_results[:limit]
