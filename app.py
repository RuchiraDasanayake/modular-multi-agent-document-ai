"""
Finance Q&A Bot with Explainable AI (XAI)
Main application entry point - handles session state and routing only.
"""

import streamlit as st

# Import styles
from styles import apply_styles

# Import views
from views import (
    render_upload_page,
    render_processing_page,
    render_success_page,
    render_qa_page,
    render_xai_page,
    DEFAULT_PARAGRAPH,
)

# Import HITL dashboard
from hitl_dashboard import init_hitl_session_state, render_hitl_dashboard


# Page configuration
st.set_page_config(
    page_title="Modular Q&A",
    page_icon="Q",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Apply CSS styles
apply_styles()


def init_session_state():
    """Initialize all session state variables"""
    init_hitl_session_state()
    
    if "current_page" not in st.session_state:
        st.session_state.current_page = "upload"
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    if "current_paragraph" not in st.session_state:
        st.session_state.current_paragraph = DEFAULT_PARAGRAPH
    if "document_loaded" not in st.session_state:
        st.session_state.document_loaded = False
    if "current_explanation" not in st.session_state:
        st.session_state.current_explanation = None
    if "current_question" not in st.session_state:
        st.session_state.current_question = None
    if "has_results" not in st.session_state:
        st.session_state.has_results = False


def route_to_page():
    """Route to the appropriate page based on current state"""
    
    # Check if HITL dashboard is active
    if st.session_state.get("hitl_active", False):
        render_hitl_dashboard()
        return
    
    # Route to appropriate page
    current_page = st.session_state.get("current_page", "upload")
    
    page_routes = {
        "upload": render_upload_page,
        "processing": render_processing_page,
        "success": render_success_page,
        "qa": render_qa_page,
        "xai": render_xai_page,
    }
    
    # Get the render function for current page, default to upload
    render_func = page_routes.get(current_page, render_upload_page)
    render_func()


def main():
    """Main application entry point"""
    init_session_state()
    route_to_page()


if __name__ == "__main__":
    main()
