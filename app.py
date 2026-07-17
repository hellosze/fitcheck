import os
import re
import io
import requests
import streamlit as st
from bs4 import BeautifulSoup
from google import genai
import markdown
from weasyprint import HTML

# --- PAGE SETUP ---
st.set_page_config(
    page_title="Resume Tailor & PDF Generator",
    page_icon="📄",
    layout="centered"
)

st.title("📄 AI Resume Tailor")
st.write(
    "Paste your Google Doc resume link, the job description URL, and your target title "
    "to automatically align your resume and download a print-ready PDF."
)

# --- SECURE API KEY INGESTION ---
# Try getting API Key from environment or Streamlit Secrets
api_key = os.environ.get("GEMINI_API_KEY") or st.secrets.get("GEMINI_API_KEY")

# Fallback: Let user input it in the sidebar if not set globally
if not api_key:
    api_key = st.sidebar.text_input("Enter Gemini API Key", type="password")
    if not api_key:
        st.info("💡 Please provide your Gemini API key in the sidebar to get started.")

# --- HELPER FUNCTIONS ---
def download_google_doc_as_text(doc_url):
    """
    Converts a standard Google Doc sharing link to an export link
    and downloads its contents as plain text.
    """
    match = re.search(r"/d/([a-zA-Z0-9-_]+)", doc_url)
    if not match:
        raise ValueError("Invalid Google Doc URL format. Make sure it contains the document ID.")

    doc_id = match.group(1)
    export_url = f"https://docs.google.com/document/d/{doc_id}/export?format=txt"

    response = requests.get(export_url)
    if response.status_code == 404:
        raise PermissionError("Could not access Google Doc. Please check that 'Anyone with the link can view' is enabled.")
    response.raise_for_status()
    return response.text

def scrape_job_description(job_url):
    """
    Fetches and extracts clean text from the target job posting URL.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    response = requests.get(job_url, headers=headers)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, 'html.parser')
    for element in soup(["script", "style", "nav", "footer", "header"]):
        element.decompose()

    return soup.get_text(separator="\n", strip=True)

def tailor_resume(client, resume_text, job_desc_text, job_title):
    """
    Sends the resume and job details to Gemini to format
    and tailor to 1 to 2 pages.
    """
    system_prompt = """
    You are an expert executive resume writer. Your task is to rewrite the provided resume to align tightly with the target job title and job description.

    CRITICAL CONSTRAINTS:
    1. **Page Length Limit**: The resume must be structured to fit dynamically between **1 to 2 pages** depending on depth. Focus on high-impact accomplishments, but do not overly crush the formatting to fit on one page if two pages allow for a cleaner display of your deep technical background.
    2. **Formatting**: Ensure every bullet point is formatted as multiple bullet points, where each bullet point is on its own new line.
       * Do NOT group multiple bullet points into single dense paragraphs.
       * Do NOT separate bullets with spaces or stars (*) on the same line.
       * Do NOT include CORE Compentencies.
       * Every bullet point MUST begin with a dash (-) or an asterisk (*) on a brand-new line.
       * Ensure there is a line break (new line) between each individual bullet point.
       * Do include education NYU Polytechnic, 2007, Masters of Science, Computer Science
       * Do include education City College of New York, 2004, Bachelors of Science, Computer Science
       * Do not include experience from XO Group
    3. **Conversational yet Professional Tone**: Avoid stiff corporate buzzwords or hyper-formal prose. Write like an authoritative, confident technical peer.
    4. **Accuracy**: Do not invent employment history, credentials, or metrics. Map existing experience to the keywords and requirements of the target role.
    5. **Output Format**: Return the tailored resume in clean, standard Markdown format. Do not write an intro, explanation, or 'Here is your resume' text. Start directly with the resume content.
    """

    user_prompt = f"""
    TARGET JOB TITLE: {job_title}

    JOB DESCRIPTION:
    {job_desc_text}

    ORIGINAL RESUME:
    {resume_text}
    """

    response = client.models.generate_content(
        model="gemini-3.1-flash-lite",
        contents=user_prompt,
        config={
            "system_instruction": system_prompt,
            "temperature": 0.3
        }
    )
    return response.text

def convert_markdown_to_pdf(md_text):
    """
    Converts Markdown text into a beautifully styled PDF and returns it as bytes.
    """
    # 1. Convert Markdown to HTML body
    html_content = markdown.markdown(md_text, extensions=['extra'])

    # 2. Wrap in a complete HTML document with stylesheet
    full_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            @page {{
                size: letter;
                margin: 20mm;
                background-color: #ffffff;
                @bottom-right {{
                    content: counter(page) " of " counter(pages);
                    font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
                    font-size: 8pt;
                    color: #A0AEC0;
                }}
            }}
            * {{
                box-sizing: border-box;
            }}
            body {{
                font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
                font-size: 10pt;
                line-height: 1.5;
                color: #2D3748;
                margin: 0;
                padding: 0;
            }}
            h1 {{
                font-size: 22pt;
                margin: 0 0 4px 0;
                color: #1A365D;
                text-align: center;
                text-transform: uppercase;
                letter-spacing: 1px;
            }}
            h2 {{
                font-size: 12pt;
                margin: 18pt 0 6pt 0;
                color: #2B6CB0;
                border-bottom: 1px solid #E2E8F0;
                padding-bottom: 3px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
                page-break-after: avoid;
            }}
            h3 {{
                font-size: 10.5pt;
                margin: 10pt 0 4pt 0;
                color: #2D3748;
                font-weight: bold;
                page-break-after: avoid;
            }}
            p {{
                margin: 0 0 6pt 0;
            }}
            .contact-info {{
                text-align: center;
                font-size: 9pt;
                color: #4A5568;
                margin-bottom: 15pt;
                page-break-inside: avoid;
            }}
            ul {{
                margin: 0 0 10pt 0;
                padding-left: 20px;
            }}
            li {{
                margin-bottom: 5pt;
                line-height: 1.45;
                page-break-inside: avoid;
            }}
            strong {{
                color: #1A202C;
            }}
        </style>
    </head>
    <body>
        {html_content}
    </body>
    </html>
    """

    # 3. Write HTML directly to PDF bytes using WeasyPrint
    pdf_buffer = io.BytesIO()
    HTML(string=full_html).write_pdf(pdf_buffer)
    pdf_buffer.seek(0)
    return pdf_buffer.getvalue()

# --- STREAMLIT UI INPUT FORM ---
with st.form("resume_tailor_form"):
    doc_url = st.text_input(
        "1. Google Doc URL",
        placeholder="https://docs.google.com/document/d/... (Make sure Link Sharing is set to 'Anyone with link')"
    )
    job_url = st.text_input(
        "2. Job Description URL",
        placeholder="https://company.careers/job-listing"
    )
    job_title = st.text_input(
        "3. Target Job Title / Company",
        placeholder="e.g., Lead Software Engineer"
    )
    
    submitted = st.form_submit_button("Generate Tailored Resume")

# --- APP LOGIC EXECUTION ---
if submitted:
    if not api_key:
        st.error("❌ Please provide a Gemini API Key to continue.")
    elif not doc_url or not job_url or not job_title:
        st.error("❌ Please fill out all three fields.")
    else:
        # Clear previous generation caches
        if "pdf_data" in st.session_state:
            del st.session_state["pdf_data"]
            del st.session_state["tailored_md"]

        try:
            # Initialize Gemini Client
            client = genai.Client(api_key=api_key)

            # Step 1: Ingest Google Doc & Scrape Job Description
            with st.spinner("Downloading your Google Doc Resume and scraping job posting..."):
                resume_content = download_google_doc_as_text(doc_url)
                job_content = scrape_job_description(job_url)

            # Step 2: Tailor with Gemini
            with st.spinner("Analyzing resume matching patterns and tailoring copy via Gemini..."):
                tailored_markdown = tailor_resume(client, resume_content, job_content, job_title)

            # Step 3: Render to beautiful PDF
            with st.spinner("Rendering layout into print-ready PDF..."):
                pdf_bytes = convert_markdown_to_pdf(tailored_markdown)

            # Save successfully generated items into the session state
            st.session_state["pdf_data"] = pdf_bytes
            st.session_state["tailored_md"] = tailored_markdown
            st.session_state["filename"] = f"tailored_resume_{job_title.lower().replace(' ', '_')}.pdf"

            st.success("🎉 Tailored resume generated successfully!")

        except Exception as e:
            st.error(f"An error occurred during processing: {e}")

# --- DOWNLOAD INTERACTION PANEL ---
# If the PDF data is ready in session memory, display options to download or review
if "pdf_data" in st.session_state:
    st.markdown("### Ready for Download")
    
    st.download_button(
        label="📥 Download Tailored Resume PDF",
        data=st.session_state["pdf_data"],
        file_name=st.session_state["filename"],
        mime="application/pdf",
        use_container_width=True
    )

    # Optional Preview Feature
    with st.expander("👀 Preview Tailored Markdown Draft"):
        st.markdown(st.session_state["tailored_md"])
