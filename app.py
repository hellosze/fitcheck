import streamlit as st
import re
import requests
from bs4 import BeautifulSoup
from google import genai
from google.genai import types
from datetime import datetime
import streamlit.components.v1 as components

# ==============================================================================
# CONFIGURATION & CONSTANTS
# ==============================================================================
# Fetch secret from Streamlit Cloud Secrets or empty string if not set
SECRET_API_KEY = st.secrets.get("GEMINI_API_KEY", "")

URL_RESUME = "https://docs.google.com/document/d/1CR3_ALCHvWhfgCTQdbqqYUD-k32LJH6M-8MBY3479O0/edit?usp=sharing"

# Set page configuration
st.set_page_config(
    page_title="Resume & Cover Letter Generator",
    page_icon="📄",
    layout="wide"
)

# Sidebar for inputs and configurations
with st.sidebar:
    st.header("Configuration")
    
    # If secrets key exists, default to it; otherwise let user paste one dynamically
    api_key_input = st.text_input(
        "Gemini API Key", 
        value=SECRET_API_KEY, 
        type="password",
        help="Provide your Gemini API key from AI Studio."
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
    # Explicit validation check before initializing client
    if not api_key_input.strip():
        st.error("🔑 API Key Missing! Please add 'GEMINI_API_KEY' to Streamlit Secrets or enter your key in the sidebar.")
        st.stop()
        
    if not url_job_desc.strip():
        st.error("Please enter a valid Job Description URL.")
        st.stop()
