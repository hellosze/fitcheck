import re
import requests
from bs4 import BeautifulSoup
from google import genai
from google.genai import types
from datetime import datetime
import streamlit as st
import streamlit.components.v1 as components

# ==============================================================================
# CONFIGURATION & CONSTANTS
# ==============================================================================
# Retrieve API key securely from Streamlit secrets (or fallback to empty string)
API_KEY = st.secrets.get("GEMINI_API_KEY", "")

URL_RESUME = "https://docs.google.com/document/d/1CR3_ALCHvWhfgCTQdbqqYUD-k32LJH6M-8MBY3479O0/edit?usp=sharing"

# Set page configuration
st.set_page_config(
    page_title="Resume & Cover Letter Generator",
    page_icon="📄",
    layout="wide"
)

# ==============================================================================
# HELPER FUNCTIONS TO FETCH TEXT DATA
# ==============================================================================
@st.cache_data(show_spinner=False)
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

@st.cache_data(show_spinner=False)
def fetch_generic_url_text(url):
    """Scrapes raw text paragraphs from a standard website/job posting link."""
    try:
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(res.text, 'html.parser')
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()
        return "\n".join([p.get_text() for p in soup.find_all(['p', 'li', 'div']) if p.get_text().strip()])
    except Exception as e:
        return f"Could not automatically fetch text from URL due to: {str(e)}"

# Function to attempt optional WeasyPrint compilation
def try_compile_pdf(content_string, filename, is_html=True):
    try:
        from weasyprint import HTML
        if is_html:
            HTML(string=content_string).write_pdf(filename)
        else:
            HTML(string=f"<pre>{content_string}</pre>").write_pdf(filename)
        with open(filename, "rb") as f:
            return f.read(), None
    except Exception as e:
        return None, str(e)

# ==============================================================================
# STREAMLIT UI
# ==============================================================================
st.title("📄 AI Resume & Cover Letter Generator")
st.markdown("Automated single-page resume tailoring and cover letter generation powered by Gemini.")

# Sidebar for inputs and configurations
with st.sidebar:
    st.header("Configuration")
    
    # Use API key from secrets if present, or let user override/input manually
    api_key_input = st.text_input(
        "Gemini API Key", 
        value=API_KEY, 
        type="password",
        help="If configured in Streamlit Secrets, this will auto-fill hidden."
    )
    resume_url_input = st.text_input("Google Doc Resume URL", value=URL_RESUME)
    st.divider()
    st.info("Ensure the Google Doc is set to 'Anyone with the link can view'.")

# Main content form
with st.form("job_form"):
    st.subheader("Job Details")
    url_job_desc = st.text_input(
        "Job Description URL",
        placeholder="https://example.com/careers/job-posting-id",
        help="Enter the direct web address of the job posting."
    )
    submit_button = st.form_submit_button("Generate Application Documents", type="primary")

if submit_button:
    if not api_key_input.strip():
        st.error("Missing Gemini API Key. Please add it to your Streamlit secrets or enter it in the sidebar.")
        st.stop()

    if not url_job_desc.strip():
        st.error("Please enter a valid Job Description URL.")
        st.stop()

    try:
        # Step 1: Fetching Data
        with st.status("Fetching source data...", expanded=True) as status:
            st.write("📥 Fetching raw resume text from Google Docs...")
            raw_resume = fetch_google_doc_text(resume_url_input)
            
            st.write("📥 Fetching job description details from URL...")
            raw_jd = fetch_generic_url_text(url_job_desc)
            
            st.write("⚙️ Initializing Gemini Client...")
            client = genai.Client(api_key=api_key_input)
            
            # Step 2: Extract Job Title & Company
            st.write("🔍 Extracting Job Title and Company...")
            extraction_prompt = f"""
Analyze the following raw text scraped from a job description webpage.
Extract the official Job Title and the Company Name.
Return ONLY a short string in the format: "Job Title at Company Name" (e.g., "Senior Customer Success Manager at DISQO"). Do not add any extra text or pleasantries.

--- JOB DESCRIPTION TEXT ---
{raw_jd[:4000]}
"""
            extract_response = client.models.generate_content(
                model='gemini-3.1-flash-lite',
                contents=extraction_prompt,
                config=types.GenerateContentConfig(temperature=0.0)
            )
            job_title_company = extract_response.text.strip()
            st.write(f" Target Detected: **{job_title_company}**")

            # Step 3: Setup Prompts
            resume_system_instruction = f"""
You are an expert resume writer, technical recruiter, and executive layout designer.
Your task is to ingest a comprehensive, multi-page resume, match it against a target Job Description, and output a raw, standalone HTML page (with embedded print-CSS styling) that will generate a perfectly spaced, print-ready, single-page PDF resume.

Target Job Goal: {job_title_company}

### 1. Resume Structural Layout & Tiering Logic
* **Highly Concise Summary:** You are an expert career coach and professional resume writer. Your task is to write a highly tailored, punchy, and ultra-concise professional summary based on the candidate's profile and a target role..
* **No Standalone Skills Section:** To save critical vertical spacing, do not include a separate grid of keywords. Weave critical technical tools, languages, and methodologies directly into the experience bullets where we're applied.
* **Tier 1 Experience:** Prioritize the candidate's experience at Optimera, Penske Media Corp, and MPW Enterprises. Use 3-6 comprehensive bullet points per role, focusing heavily on metrics, cross-functional engineering leadership, scaling achievements, or customer success value.
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

            current_date_str = datetime.now().strftime("%B %d, %Y")
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

            # Step 4: AI Generation
            st.write("✨ Generating tailored single-page layout via Gemini...")
            resume_response = client.models.generate_content(
                model='gemini-3.1-flash-lite',
                contents=user_content,
                config=types.GenerateContentConfig(
                    system_instruction=resume_system_instruction,
                    temperature=0.2,
                )
            )

            st.write("✨ Generating perfectly aligned Cover Letter via Gemini...")
            cl_response = client.models.generate_content(
                model='gemini-3.1-flash-lite',
                contents=user_content,
                config=types.GenerateContentConfig(
                    system_instruction=cl_system_instruction,
                    temperature=0.3,
                )
            )

            status.update(label="Generation Complete!", state="complete", expanded=False)

        # Clean Outputs
        clean_html_content = resume_response.text.strip()
        if clean_html_content.startswith("```html"):
            clean_html_content = clean_html_content[7:]
        if clean_html_content.endswith("```"):
            clean_html_content = clean_html_content[:-3]
        clean_html_content = clean_html_content.strip()

        clean_cl_content = cl_response.text.strip()

        # Build Filenames
        sanitized_job_goal = re.sub(r'[\\/*?:"<>|]', "", job_title_company)
        pdf_filename = f"Sze Chan - {sanitized_job_goal}.pdf"
        cl_filename = f"Sze Chan - Cover Letter - {sanitized_job_goal}.txt"
        cl_pdf_filename = f"Sze Chan - Cover Letter - {sanitized_job_goal}.pdf"

        # Compilation Attempts
        resume_pdf_bytes, pdf_err1 = try_compile_pdf(clean_html_content, pdf_filename, is_html=True)
        cl_pdf_bytes, pdf_err2 = try_compile_pdf(clean_cl_content, cl_pdf_filename, is_html=False)

        # Display Downloads and Previews
        st.success(f"Generated Application Materials for **{job_title_company}**")

        tab1, tab2 = st.tabs(["📄 HTML Resume", "✉️ Cover Letter"])

        with tab1:
            col1, col2 = st.columns(2)
            with col1:
                st.download_button(
                    label="📥 Download HTML Resume",
                    data=clean_html_content,
                    file_name=f"Engineered_One_Page_Resume_{sanitized_job_goal}.html",
                    mime="text/html",
                    type="primary"
                )
            with col2:
                if resume_pdf_bytes:
                    st.download_button(
                        label="📥 Download Resume (PDF)",
                        data=resume_pdf_bytes,
                        file_name=pdf_filename,
                        mime="application/pdf"
                    )
                else:
                    st.warning("WeasyPrint isn't installed natively. Download HTML and use Chrome's 'Print to PDF' for perfect layout rendering.")

            st.divider()
            st.subheader("Interactive Preview")
            components.html(clean_html_content, height=800, scrolling=True)

        with tab2:
            col1, col2 = st.columns(2)
            with col1:
                st.download_button(
                    label="📥 Download Cover Letter (TXT)",
                    data=clean_cl_content,
                    file_name=cl_filename,
                    mime="text/plain",
                    type="primary"
                )
            with col2:
                if cl_pdf_bytes:
                    st.download_button(
                        label="📥 Download Cover Letter (PDF)",
                        data=cl_pdf_bytes,
                        file_name=cl_pdf_filename,
                        mime="application/pdf"
                    )

            st.divider()
            st.subheader("Cover Letter Text")
            st.text_area("Cover Letter Content", value=clean_cl_content, height=400)

    except Exception as e:
        st.error(f"An error occurred: {str(e)}")
