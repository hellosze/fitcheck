import re
import requests
from datetime import datetime
from bs4 import BeautifulSoup
import streamlit as st
from google import genai
from google.genai import types

# Optional import for PDF rendering
try:
    from weasyprint import HTML
    WEASYPRINT_AVAILABLE = True
except ImportError:
    WEASYPRINT_AVAILABLE = False

# ==============================================================================
# PAGE CONFIGURATION & SECRETS CHECK
# ==============================================================================
st.set_page_config(
    page_title="AI Resume & Cover Letter Generator",
    page_icon="📄",
    layout="wide"
)

# Fetch API key securely from Streamlit secrets
if "GEMINI_API_KEY" not in st.secrets:
    st.error("⚠️ `GEMINI_API_KEY` not found in Streamlit Secrets! Please add it to `.streamlit/secrets.toml` or your app platform settings.")
    st.stop()

API_KEY = st.secrets["GEMINI_API_KEY"]

# Default static resume URL
DEFAULT_RESUME_URL = "https://docs.google.com/document/d/1CR3_ALCHvWhfgCTQdbqqYUD-k32LJH6M-8MBY3479O0/edit?usp=sharing"

# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================
def fetch_google_doc_text(url):
    """Converts a standard Google Doc view link into an export text stream and scrapes it."""
    doc_id_match = re.search(r"/d/([a-zA-Z0-9-_]+)", url)
    if not doc_id_match:
        raise ValueError("Invalid Google Doc URL structure.")
    export_url = f"https://docs.google.com/document/d/{doc_id_match.group(1)}/export?format=txt"
    response = requests.get(export_url)
    if response.status_code == 200:
        return response.text
    else:
        # Fallback to standard web scraping if export stream is blocked
        res = requests.get(url)
        soup = BeautifulSoup(res.text, 'html.parser')
        return soup.get_text(separator='\n')

def fetch_generic_url_text(url):
    """Scrapes raw text paragraphs from a standard website/job posting link."""
    try:
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(res.text, 'html.parser')
        for script in soup(["script", "style"]):
            script.decompose()
        return "\n".join([p.get_text() for p in soup.find_all(['p', 'li', 'div']) if p.get_text().strip()])
    except Exception as e:
        return f"Could not automatically fetch text from URL due to: {str(e)}"

# ==============================================================================
# STREAMLIT UI
# ==============================================================================
st.title("📄 AI Resume & Cover Letter Generator")
st.write("Tailor your resume and cover letter using Gemini 3.5 Flash Lite based on a target job description.")

col1, col2 = st.columns(2)

with col1:
    job_url = st.text_input(
        "Job Description URL",
        placeholder="https://freestar.com/careers/?gh_jid=8614935002"
    )

with col2:
    resume_url = st.text_input(
        "Google Doc Resume URL",
        value=DEFAULT_RESUME_URL
    )

if st.button("Generate Documents", type="primary"):
    if not job_url.strip():
        st.warning("Please enter a valid Job Description URL.")
        st.stop()

    with st.status("Processing application materials...", expanded=True) as status:
        try:
            # 1. Fetch Texts
            status.update(label="Fetching raw text from resume and job posting...")
            raw_resume = fetch_google_doc_text(resume_url)
            raw_jd = fetch_generic_url_text(job_url)

            # 2. Initialize Gemini Client
            status.update(label="Initializing Gemini Client...")
            client = genai.Client(api_key=API_KEY)

            # 3. Extract Job Title & Company
            status.update(label="Analyzing Job Description for Title & Company...")
            extraction_prompt = f"""
            Analyze the following raw text scraped from a job description webpage.
            Extract the official Job Title and the Company Name.
            Return ONLY a short string in the format: "Job Title at Company Name" (e.g., "Senior Customer Success Manager at DISQO"). Do not add any extra text or pleasantries.

            --- JOB DESCRIPTION TEXT ---
            {raw_jd[:4000]}
            """

            extract_response = client.models.generate_content(
                model='gemini-3.5-flash-lite',
                contents=extraction_prompt,
                config=types.GenerateContentConfig(temperature=0.0)
            )
            job_title_company = extract_response.text.strip()
            st.success(f"Detected Goal: **{job_title_company}**")

            # 4. Define Prompts
            resume_system_instruction = f"""
            You are an expert resume writer, technical recruiter, and executive layout designer.
            Your task is to ingest a comprehensive, multi-page resume, match it against a target Job Description, and output a raw, standalone HTML page (with embedded print-CSS styling) that will generate a perfectly spaced, print-ready, single-page PDF resume.

            Target Job Goal: {job_title_company}

            ### 1. Resume Structural Layout & Tiering Logic
            * **Highly Concise Summary:** You are an expert career coach and professional resume writer. Your task is to write a highly tailored, punchy, and ultra-concise professional summary based on the candidate's profile and a target role..
            * **No Standalone Skills Section:** To save critical vertical spacing, do not include a separate grid of keywords. Weave critical technical tools, languages, and methodologies directly into the experience bullets where we're applied.
            * **Tier 1 Experience:** Prioritize the candidate's experience at Optimera, Penske Media Corp, and MPW Enterprises. Use 3-5 comprehensive bullet points per role, focusing heavily on metrics, cross-functional engineering leadership, scaling achievements, or customer success value.
            * **Tier 2 Experience:** Shorten all other older positions (Undertone, Frankly Media, American Media Inc, XO Group) down to exactly 1 high-impact bullet point focusing strictly on a key achievement or architecture build.
            * Do include education NYU Polytechnic, 2007, Masters of Science, Computer Science
            * Do include education City College of New York, 2004, Bachelors of Science, Computer Science
            * Do not include tech used bullet point from Tier 2 experience
            * Do not include leverage tools bullet point from Penske Media

            ### 2. Strict PDF Blueprint Layout Constraints (HTML/CSS)
            You must output a single page style blueprint using the following inline CSS blocks:
            - `@page {{ size: letter; margin: 10mm 12mm 10mm 12mm; }}`
            - Set the base `body` font-size strictly to `8.5pt` with a crisp `line-height: 1.25` using common web-safe sans-serif fonts.
            - Use `display: block;` headers with `float: right;` spans to place company names/titles side-by-side with employment dates cleanly.
            - Tight list padding (`padding-left: 12px; margin: 2px 0 4px 0;`) and minimal item margins (`margin-bottom: 2px;`) to eliminate accidental white space overflows.

            ### 3. Output Format Requirement
            Your response must contain ONLY the valid, pure HTML text string. Do not wrap the code block in markdown code blocks like ```html ... ```. Start directly with <!DOCTYPE html> and end with </html>.
            """

            cl_system_instruction = f"""
            ### Cover Letter Strategy & Guardrails:

            You are an expert career coach and professional resume writer. Your task is to write a highly tailored, punchy, and ultra-concise cover letter based on the candidate's profile and a target role.

            Inputs for this Generation:
            - Candidate Name: Sze Chan
            - Candidate Contact: sze.m.chan@gmail.com | 646-269-7616
            - Target Company: {job_title_company}
            - Target Position: {job_title_company}

            Formatting & Constraints:
            1. Structure: Include a standard professional header using the provided candidate info, the current date, and the target company/position details.
            2. Length: Keep the actual body text extremely short—exactly TWO paragraphs total, spanning between 3 to 6 sentences combined.
            3. Tone: Professional, direct, and incredibly punchy. Avoid fluff.
            4. Strategy: Successfully bridge the candidate's advanced background in technical client success over to the target role by highlighting transferable core competencies: empathetic communication, multi-platform system navigation, and high-stakes issue resolution.
            5. Ending: Conclude the letter immediately following the second paragraph with the exact phrase: "Thank you for your time and consideration." followed by the sign-off.
            """

            user_content = f"""
            Please evaluate this target job and multi-page source resume data.

            ---
            ### TARGET JOB TITLE & COMPANY:
            {job_title_company}

            ---
            ### TARGET JOB DESCRIPTION:
            {raw_jd}

            ---
            ### SOURCE MULTI-PAGE RESUME:
            {raw_resume}
            """

            # 5. Generate Outputs
            status.update(label="Generating tailored single-page HTML resume...")
            resume_response = client.models.generate_content(
                model='gemini-3.5-flash-lite',
                contents=user_content,
                config=types.GenerateContentConfig(
                    system_instruction=resume_system_instruction,
                    temperature=0.2,
                )
            )

            status.update(label="Generating Cover Letter...")
            cl_response = client.models.generate_content(
                model='gemini-3.5-flash-lite',
                contents=user_content,
                config=types.GenerateContentConfig(
                    system_instruction=cl_system_instruction,
                    temperature=0.3,
                )
            )

            # Cleanup text
            clean_html = resume_response.text.strip()
            if clean_html.startswith("```html"):
                clean_html = clean_html[7:]
            if clean_html.endswith("```"):
                clean_html = clean_html[:-3]
            clean_html = clean_html.strip()

            clean_cl = cl_response.text.strip()

            status.update(label="Generation complete!", state="complete")

            # Store in session state for rendering outside the form submission
            st.session_state["resume_html"] = clean_html
            st.session_state["cover_letter"] = clean_cl
            st.session_state["job_target"] = job_title_company

        except Exception as e:
            status.update(label="An error occurred during generation.", state="error")
            st.error(f"Error: {str(e)}")

# ==============================================================================
# DISPLAY AND DOWNLOAD RESULTS
# ==============================================================================
if "resume_html" in st.session_state and "cover_letter" in st.session_state:
    st.divider()
    st.header(f"Results for {st.session_state['job_target']}")

    sanitized_goal = re.sub(r'[\\/*?:"<>|]', "", st.session_state["job_target"])
    tab1, tab2 = st.tabs(["📄 Resume", "✉️ Cover Letter"])

    with tab1:
        col_down1, col_down2 = st.columns(2)
        with col_down1:
            st.download_button(
                label="Download Resume (HTML)",
                data=st.session_state["resume_html"],
                file_name=f"Sze Chan - Resume - {sanitized_goal}.html",
                mime="text/html"
            )
        with col_down2:
            if WEASYPRINT_AVAILABLE:
                pdf_bytes = HTML(string=st.session_state["resume_html"]).write_pdf()
                st.download_button(
                    label="Download Resume (PDF)",
                    data=pdf_bytes,
                    file_name=f"Sze Chan - Resume - {sanitized_goal}.pdf",
                    mime="application/pdf"
                )
            else:
                st.info("💡 Install `weasyprint` locally/on host to enable direct PDF downloads.")

        st.components.v1.html(st.session_state["resume_html"], height=800, scrolling=True)

    with tab2:
        st.download_button(
            label="Download Cover Letter (TXT)",
            data=st.session_state["cover_letter"],
            file_name=f"Sze Chan - Cover Letter - {sanitized_goal}.txt",
            mime="text/plain"
        )
        st.text_area("Generated Cover Letter", value=st.session_state["cover_letter"], height=400)
