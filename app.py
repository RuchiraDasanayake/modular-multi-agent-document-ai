"""
Modular Q&A - Classic Chat Interface with XAI
"""

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from xai_engine import XAIEngine, HighlightType, XAIExplanation
from hitl_dashboard import (
    init_hitl_session_state, 
    render_hitl_button_classic, 
    render_hitl_dashboard,
)
import numpy as np
from datetime import datetime


# Page configuration
st.set_page_config(
    page_title="Modular Q&A",
    page_icon="Q",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Classic CSS Styling
st.markdown("""
<style>
    /* Hide Streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* Classic Header */
    .classic-header {
        text-align: center;
        padding: 1.5rem 1rem;
        background: #2c3e50;
        color: #ecf0f1;
        border-bottom: 3px solid #1a252f;
        margin-bottom: 1.5rem;
    }
    .classic-header h1 {
        margin: 0;
        font-size: 1.8rem;
        font-weight: 600;
        letter-spacing: 1px;
    }
    
    /* Chat Container */
    .chat-container {
        max-width: 800px;
        margin: 0 auto;
        padding: 1rem;
        background: #f5f5f5;
        border-radius: 8px;
        min-height: 100px;
        max-height: 500px;
        overflow-y: auto;
        border: 1px solid #ddd;
    }
    
    .chat-container:empty {
        display: none;
    }
    
    .chat-container-hidden {
        display: none !important;
    }
    
    /* Attractive Buttons */
    .stButton > button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
        color: white !important;
        border: none !important;
        border-radius: 25px !important;
        padding: 10px 24px !important;
        font-weight: 600 !important;
        font-size: 0.95rem !important;
        letter-spacing: 0.5px !important;
        box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4) !important;
        transition: all 0.3s ease !important;
    }
    
    .stButton > button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 6px 20px rgba(102, 126, 234, 0.6) !important;
    }
    
    .stButton > button:active {
        transform: translateY(0) !important;
    }
    
    /* Primary Button (Send) */
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%) !important;
        box-shadow: 0 4px 15px rgba(17, 153, 142, 0.4) !important;
    }
    
    .stButton > button[kind="primary"]:hover {
        box-shadow: 0 6px 20px rgba(17, 153, 142, 0.6) !important;
    }
    
    /* Secondary/Navigation Buttons */
    .nav-btn {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
    }
    
    /* Chat Messages */
    .chat-message {
        display: flex;
        margin-bottom: 1rem;
        animation: fadeIn 0.3s ease-in;
    }
    
    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(10px); }
        to { opacity: 1; transform: translateY(0); }
    }
    
    .chat-message.user {
        justify-content: flex-end;
    }
    
    .chat-message.bot {
        justify-content: flex-start;
    }
    
    .message-bubble {
        max-width: 70%;
        padding: 12px 16px;
        border-radius: 18px;
        font-size: 0.95rem;
        line-height: 1.5;
        box-shadow: 0 1px 2px rgba(0,0,0,0.1);
    }
    
    .user .message-bubble {
        background: #0084ff;
        color: white;
        border-bottom-right-radius: 4px;
    }
    
    .bot .message-bubble {
        background: white;
        color: #1a1a1a;
        border: 1px solid #e0e0e0;
        border-bottom-left-radius: 4px;
    }
    
    .message-time {
        font-size: 0.7rem;
        color: #888;
        margin-top: 4px;
    }
    
    .user .message-time {
        text-align: right;
    }
    
    .bot .message-time {
        text-align: left;
    }
    
    /* Confidence Badge */
    .confidence-badge {
        display: inline-block;
        background: #27ae60;
        color: white;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 0.75rem;
        margin-top: 8px;
    }
    
    .confidence-badge.low {
        background: #e74c3c;
    }
    
    .confidence-badge.medium {
        background: #f39c12;
    }
    
    /* Classic Button */
    .classic-btn {
        display: inline-block;
        background: #34495e;
        color: white;
        padding: 10px 20px;
        border: none;
        border-radius: 4px;
        font-size: 0.9rem;
        cursor: pointer;
        text-decoration: none;
        transition: background 0.2s;
        margin: 8px 4px;
    }
    
    .classic-btn:hover {
        background: #2c3e50;
    }
    
    .classic-btn.secondary {
        background: #7f8c8d;
    }
    
    .classic-btn.secondary:hover {
        background: #6c7a7d;
    }
    
    /* XAI Page Styles */
    .xai-header {
        background: #34495e !important;
        color: #ffffff !important;
        padding: 1rem 1.5rem;
        border-radius: 8px;
        margin-bottom: 1.5rem;
    }
    
    .xai-header h2 {
        color: #ffffff !important;
    }
    
    .xai-header p {
        color: rgba(255, 255, 255, 0.85) !important;
    }
    
    .xai-section {
        background: #ffffff !important;
        border: 1px solid #ddd;
        border-radius: 8px;
        padding: 1.5rem;
        margin-bottom: 1rem;
    }
    
    .xai-section h3 {
        color: #2c3e50 !important;
        border-bottom: 2px solid #ecf0f1;
        padding-bottom: 0.5rem;
        margin-top: 0;
    }
    
    .xai-section p {
        color: #333333 !important;
    }
    
    /* Highlight styles */
    .hl-positive {
        background: rgba(39, 174, 96, 0.25) !important;
        border-bottom: 2px solid #27ae60;
        padding: 2px 4px;
        border-radius: 3px;
        color: #1a5c38 !important;
    }
    
    .hl-negative {
        background: rgba(231, 76, 60, 0.2) !important;
        border-bottom: 2px solid #e74c3c;
        padding: 2px 4px;
        border-radius: 3px;
        color: #922b21 !important;
    }
    
    .hl-answer {
        background: rgba(241, 196, 15, 0.35) !important;
        border-bottom: 3px solid #f1c40f;
        padding: 2px 6px;
        border-radius: 4px;
        font-weight: 600;
        color: #7d6608 !important;
    }
    
    .hl-medium {
        background: rgba(52, 152, 219, 0.2) !important;
        border-bottom: 2px solid #3498db;
        padding: 2px 4px;
        border-radius: 3px;
        color: #1a5276 !important;
    }
    
    /* Paragraph Box */
    .paragraph-box {
        background: #fafafa !important;
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        padding: 1.25rem;
        line-height: 1.8;
        color: #333333 !important;
    }
    
    /* Legend */
    .legend-box {
        display: flex;
        flex-wrap: wrap;
        gap: 1rem;
        padding: 1rem;
        background: #f8f9fa !important;
        border-radius: 6px;
        margin-bottom: 1rem;
        font-size: 0.85rem;
    }
    
    .legend-item {
        display: flex;
        align-items: center;
        gap: 6px;
        color: #333333 !important;
    }
    
    .legend-item span {
        color: #333333 !important;
    }
    
    /* Derivation Steps */
    .derivation-step {
        background: #fafafa !important;
        border-left: 3px solid #34495e;
        padding: 1rem;
        margin: 0.75rem 0;
        border-radius: 0 6px 6px 0;
    }
    
    .derivation-step .step-title {
        font-weight: 600;
        color: #2c3e50 !important;
        margin-bottom: 0.5rem;
    }
    
    .derivation-step .step-desc {
        color: #555555 !important;
        font-size: 0.9rem;
    }
    
    /* General text color fixes for XAI page */
    .stMarkdown p, .stMarkdown li, .stMarkdown span {
        color: #333333 !important;
    }
    
    .stTabs [data-baseweb="tab-panel"] {
        background: #ffffff !important;
    }
    
    .stTabs [data-baseweb="tab-panel"] p,
    .stTabs [data-baseweb="tab-panel"] li {
        color: #333333 !important;
    }
    
    /* Footer */
    .classic-footer {
        text-align: center;
        padding: 1.5rem;
        color: #7f8c8d;
        border-top: 1px solid #ecf0f1;
        margin-top: 2rem;
        font-size: 0.85rem;
    }
    
    /* Navigation Buttons */
    .nav-buttons {
        display: flex;
        gap: 10px;
        margin: 1rem 0;
    }
    
    /* Input area styling */
    .stTextInput > div > div > input {
        border-radius: 20px;
        border: 1px solid #ddd;
        padding: 10px 16px;
    }
    
    /* Document Upload Page Styles */
    .upload-container {
        max-width: 700px;
        margin: 2rem auto;
        text-align: center;
    }
    
    .upload-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 2.5rem 2rem;
        border-radius: 16px;
        margin-bottom: 2rem;
        box-shadow: 0 10px 40px rgba(102, 126, 234, 0.3);
    }
    
    .upload-header h1 {
        margin: 0;
        font-size: 2.2rem;
        font-weight: 700;
    }
    
    .upload-header p {
        margin: 0.75rem 0 0 0;
        opacity: 0.9;
        font-size: 1.1rem;
    }
    
    .upload-box {
        background: #ffffff;
        border: 3px dashed #667eea;
        border-radius: 16px;
        padding: 3rem 2rem;
        margin: 2rem 0;
        transition: all 0.3s ease;
    }
    
    .upload-box:hover {
        border-color: #764ba2;
        background: #fafbff;
    }
    
    .upload-icon {
        font-size: 4rem;
        margin-bottom: 1rem;
    }
    
    .upload-text {
        color: #555;
        font-size: 1.1rem;
        margin-bottom: 1rem;
    }
    
    .upload-formats {
        color: #888;
        font-size: 0.85rem;
    }
    
    /* Processing Animation */
    .processing-container {
        text-align: center;
        padding: 3rem;
    }
    
    .processing-spinner {
        width: 80px;
        height: 80px;
        border: 6px solid #f3f3f3;
        border-top: 6px solid #667eea;
        border-radius: 50%;
        animation: spin 1s linear infinite;
        margin: 0 auto 2rem auto;
    }
    
    @keyframes spin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
    }
    
    .processing-text {
        color: #333;
        font-size: 1.2rem;
        font-weight: 500;
    }
    
    .processing-step {
        color: #666;
        font-size: 0.95rem;
        margin-top: 0.5rem;
    }
    
    /* Success Page */
    .success-container {
        text-align: center;
        padding: 3rem;
        max-width: 600px;
        margin: 2rem auto;
    }
    
    .success-icon {
        width: 100px;
        height: 100px;
        background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        margin: 0 auto 1.5rem auto;
        box-shadow: 0 10px 40px rgba(17, 153, 142, 0.3);
    }
    
    .success-icon span {
        color: white;
        font-size: 3rem;
    }
    
    .success-title {
        color: #2c3e50;
        font-size: 1.8rem;
        font-weight: 700;
        margin-bottom: 0.5rem;
    }
    
    .success-subtitle {
        color: #666;
        font-size: 1rem;
        margin-bottom: 2rem;
    }
    
    .doc-info {
        background: #f8f9fa;
        border-radius: 12px;
        padding: 1.5rem;
        margin: 1.5rem 0;
        text-align: left;
    }
    
    .doc-info-item {
        display: flex;
        justify-content: space-between;
        padding: 0.5rem 0;
        border-bottom: 1px solid #eee;
        color: #333;
    }
    
    .doc-info-item:last-child {
        border-bottom: none;
    }
    
    .doc-info-label {
        color: #666;
        font-weight: 500;
    }
    
    .doc-info-value {
        color: #2c3e50;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)


# Default paragraph (hidden by default)
DEFAULT_PARAGRAPH = """Finance is fundamentally the study of resource allocation over time, balancing the promise of future returns against the inherent presence of risk. At its core, it functions as the circulatory system of the global economy, moving capital from those who have an excess of it (savers and investors) to those who can deploy it productively (borrowers and entrepreneurs). This exchange is mediated by various instruments—such as stocks, bonds, and derivatives—and governed by the principle of the time value of money, which asserts that a dollar held today is worth more than a dollar received tomorrow due to its potential earning capacity."""


@st.cache_resource
def get_engine():
    """Initialize and cache the XAI Engine"""
    return XAIEngine()


def highlight_paragraph(text: str, spans: list) -> str:
    """Generate HTML with highlighted text spans"""
    if not spans:
        return text
    
    sorted_spans = sorted(spans, key=lambda x: x.start)
    
    class_map = {
        HighlightType.HIGH_IMPORTANCE: "hl-positive",
        HighlightType.MEDIUM_IMPORTANCE: "hl-medium",
        HighlightType.LOW_IMPORTANCE: "hl-medium",
        HighlightType.POSITIVE_CONTRIBUTION: "hl-positive",
        HighlightType.NEGATIVE_CONTRIBUTION: "hl-negative",
        HighlightType.ANSWER_SPAN: "hl-answer",
    }
    
    result = []
    last_end = 0
    
    for span in sorted_spans:
        if span.start >= last_end:
            if span.start > last_end:
                result.append(text[last_end:span.start])
            
            css_class = class_map.get(span.highlight_type, "hl-medium")
            tooltip = f"SHAP: {span.shap_score:.3f} | LIME: {span.lime_score:.3f}"
            
            result.append(
                f'<span class="{css_class}" title="{tooltip}">{text[span.start:span.end]}</span>'
            )
            last_end = span.end
    
    if last_end < len(text):
        result.append(text[last_end:])
    
    return ''.join(result)


def create_shap_chart(shap_explanation):
    """Create SHAP chart"""
    if not shap_explanation.shap_values:
        return None
    
    words = [w for w, s in shap_explanation.shap_values[:10]]
    values = [s for w, s in shap_explanation.shap_values[:10]]
    
    colors = ['#27ae60' if v > 0 else '#e74c3c' for v in values]
    
    fig = go.Figure(go.Bar(
        x=values,
        y=words,
        orientation='h',
        marker_color=colors,
        text=[f'{v:+.3f}' for v in values],
        textposition='outside'
    ))
    
    fig.update_layout(
        title="SHAP Feature Importance",
        xaxis_title="SHAP Value",
        yaxis_title="Feature",
        height=350,
        yaxis={'categoryorder': 'total ascending'},
        showlegend=False,
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=20, r=20, t=40, b=20)
    )
    
    return fig


def create_lime_chart(lime_explanation):
    """Create LIME chart"""
    if not lime_explanation.word_weights:
        return None
    
    words = [w for w, s in lime_explanation.word_weights[:10]]
    weights = [s for w, s in lime_explanation.word_weights[:10]]
    
    colors = ['#27ae60' if w > 0 else '#e74c3c' for w in weights]
    
    fig = go.Figure(go.Bar(
        x=weights,
        y=words,
        orientation='h',
        marker_color=colors,
        text=[f'{w:+.3f}' for w in weights],
        textposition='outside'
    ))
    
    fig.update_layout(
        title="LIME Word Importance",
        xaxis_title="LIME Weight",
        yaxis_title="Word",
        height=350,
        yaxis={'categoryorder': 'total ascending'},
        showlegend=False,
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=20, r=20, t=40, b=20)
    )
    
    return fig


def render_chat_message(role: str, content: str, timestamp: str = None, confidence: float = None):
    """Render a chat message bubble"""
    if timestamp is None:
        timestamp = datetime.now().strftime("%H:%M")
    
    confidence_html = ""
    if confidence is not None:
        conf_class = "low" if confidence < 0.4 else ("medium" if confidence < 0.7 else "")
        confidence_html = f'<div class="confidence-badge {conf_class}">Confidence: {confidence:.0%}</div>'
    
    st.markdown(f"""
    <div class="chat-message {role}">
        <div>
            <div class="message-bubble">{content}{confidence_html}</div>
            <div class="message-time">{timestamp}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)


def render_qa_page():
    """Render the main Q&A chat interface"""
    engine = get_engine()
    
    # Always use the static demo paragraph
    paragraph = DEFAULT_PARAGRAPH
    st.session_state.current_paragraph = paragraph
    
    # Header
    st.markdown("""
    <div class="classic-header">
        <h1>Modular Q&A</h1>
    </div>
    """, unsafe_allow_html=True)
    
    # Hidden paragraph (expandable) - read-only for demo
    with st.expander("View Context Paragraph"):
        st.markdown(f"""
        <div style="background: #f8f9fa; padding: 1rem; border-radius: 8px; color: #333; line-height: 1.7;">
            {paragraph}
        </div>
        """, unsafe_allow_html=True)
    
    # Display chat history (only if there are messages)
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    
    if st.session_state.chat_history:
        st.markdown('<div class="chat-container">', unsafe_allow_html=True)
        for msg in st.session_state.chat_history:
            render_chat_message(
                msg["role"], 
                msg["content"], 
                msg.get("timestamp"),
                msg.get("confidence")
            )
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Input area
    st.markdown("---")
    col1, col2 = st.columns([5, 1])
    
    with col1:
        question = st.text_input(
            "Your question:",
            placeholder="Type your question here...",
            key="question_input",
            label_visibility="collapsed"
        )
    
    with col2:
        send_btn = st.button("Send", type="primary", use_container_width=True)
    
    # Process question
    if send_btn and question:
        # Ensure paragraph is not empty
        # Add user message to history
        timestamp = datetime.now().strftime("%H:%M")
        st.session_state.chat_history.append({
            "role": "user",
            "content": question,
            "timestamp": timestamp
        })
        
        # Generate response using static demo paragraph
        with st.spinner("Thinking..."):
            explanation = engine.generate_explanation(DEFAULT_PARAGRAPH, question)
        
        # Store explanation for XAI page
        st.session_state.current_explanation = explanation
        st.session_state.current_question = question
        st.session_state.has_results = True
        
        # Extract clean answer (just the direct answer part)
        answer_text = explanation.answer
        if "**" in answer_text:
            # Extract just the answer without markdown
            import re
            match = re.search(r'\*\*.*?\*\*\s*(.+?)(?:\n|$)', answer_text)
            if match:
                clean_answer = match.group(1).strip()
            else:
                clean_answer = answer_text.split('\n')[0]
        else:
            clean_answer = answer_text.split('\n')[0]
        
        # Add bot response to history
        st.session_state.chat_history.append({
            "role": "bot",
            "content": clean_answer,
            "timestamp": datetime.now().strftime("%H:%M"),
            "confidence": explanation.confidence_score
        })
        
        st.rerun()
    
    # Show "See how answer came" button if we have results
    if st.session_state.get("has_results", False):
        st.markdown("---")
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button("Wanna see how the answer came?", use_container_width=True, key="see_xai_btn"):
                st.session_state.current_page = "xai"
                st.rerun()
    
    # HITL Button
    st.markdown("---")
    render_hitl_button_classic()
    
    # Footer
    st.markdown("""
    <div class="classic-footer">
        Finance Q&A with Explainable AI | Powered by SHAP & LIME
    </div>
    """, unsafe_allow_html=True)


def render_xai_page():
    """Render the XAI explanation page"""
    
    # Check if we have explanation data
    if st.session_state.get("current_explanation") is None:
        st.warning("No analysis available. Please ask a question first.")
        if st.button("Back to Q&A"):
            st.session_state.current_page = "qa"
            st.rerun()
        return
    
    explanation = st.session_state.current_explanation
    question = st.session_state.current_question
    paragraph = st.session_state.current_paragraph
    
    # Header
    st.markdown("""
    <div class="xai-header">
        <h2 style="margin: 0;">Explanation Details</h2>
        <p style="margin: 0.5rem 0 0 0; opacity: 0.8;">How the answer was derived</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Navigation
    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        if st.button("Back to Q&A", use_container_width=True):
            st.session_state.current_page = "qa"
            st.rerun()
    with col2:
        render_hitl_button_classic()
    
    st.markdown("---")
    
    # Question & Answer Summary
    st.markdown(f"""
    <div class="xai-section">
        <h3>Question</h3>
        <p style="color: #333; font-size: 1.1rem;">{question}</p>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown(f"""
    <div class="xai-section">
        <h3>Answer</h3>
        <p style="color: #333;">{explanation.answer}</p>
        <span style="background: #27ae60; color: white; padding: 4px 12px; border-radius: 4px; font-size: 0.85rem;">
            Confidence: {explanation.confidence_score:.1%}
        </span>
    </div>
    """, unsafe_allow_html=True)
    
    # Highlighted Paragraph
    st.markdown("""
    <div class="xai-section">
        <h3>Highlighted Context</h3>
    </div>
    """, unsafe_allow_html=True)
    
    # Legend
    st.markdown("""
    <div class="legend-box">
        <div class="legend-item">
            <div style="width: 16px; height: 16px; background: rgba(241, 196, 15, 0.35); border-bottom: 3px solid #f1c40f; border-radius: 3px;"></div>
            <span>Model Answer</span>
        </div>
        <div class="legend-item">
            <div style="width: 16px; height: 16px; background: rgba(39, 174, 96, 0.25); border-bottom: 2px solid #27ae60; border-radius: 3px;"></div>
            <span>Positive Contribution</span>
        </div>
        <div class="legend-item">
            <div style="width: 16px; height: 16px; background: rgba(231, 76, 60, 0.2); border-bottom: 2px solid #e74c3c; border-radius: 3px;"></div>
            <span>Negative Contribution</span>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    highlighted_html = highlight_paragraph(paragraph, explanation.highlighted_spans)
    st.markdown(f'<div class="paragraph-box">{highlighted_html}</div>', unsafe_allow_html=True)
    
    st.markdown("---")
    
    # XAI Visualizations
    st.markdown("### Feature Analysis")
    
    tab1, tab2, tab3 = st.tabs(["SHAP Analysis", "LIME Analysis", "Derivation Logic"])
    
    with tab1:
        st.markdown("""
        <div class="xai-section">
            <h3>SHAP Feature Importance</h3>
            <p style="color: #666; font-size: 0.9rem;">Shows how each feature contributes to the prediction.</p>
        </div>
        """, unsafe_allow_html=True)
        
        shap_chart = create_shap_chart(explanation.shap_explanation)
        if shap_chart:
            st.plotly_chart(shap_chart, use_container_width=True)
        
        st.markdown("**Top Features:**")
        for word, score in explanation.shap_explanation.shap_values[:8]:
            icon = "+" if score > 0 else "-"
            st.markdown(f"- {icon} **{word}**: {score:+.4f}")
    
    with tab2:
        st.markdown("""
        <div class="xai-section">
            <h3>LIME Local Explanation</h3>
            <p style="color: #666; font-size: 0.9rem;">Shows word-level contribution to the prediction.</p>
        </div>
        """, unsafe_allow_html=True)
        
        lime_chart = create_lime_chart(explanation.lime_explanation)
        if lime_chart:
            st.plotly_chart(lime_chart, use_container_width=True)
        
        st.markdown(f"**Prediction Probability:** {explanation.lime_explanation.prediction_proba:.1%}")
        
        st.markdown("**Top Words:**")
        for word, weight in explanation.lime_explanation.word_weights[:8]:
            icon = "+" if weight > 0 else "-"
            st.markdown(f"- {icon} **{word}**: {weight:+.4f}")
    
    with tab3:
        st.markdown("""
        <div class="xai-section">
            <h3>Derivation Logic</h3>
            <p style="color: #666; font-size: 0.9rem;">Step-by-step reasoning process.</p>
        </div>
        """, unsafe_allow_html=True)
        
        for step in explanation.derivation_tree.steps:
            conf_pct = f"{step.confidence:.0%}"
            # Remove emojis from step action
            action_clean = step.action
            for emoji in ['📝', '🧠', '🎯', '🔬', '🍋', '✨']:
                action_clean = action_clean.replace(emoji, '').strip()
            
            st.markdown(f"""
            <div class="derivation-step">
                <div class="step-title">
                    Step {step.step_number}: {action_clean}
                    <span style="background: #27ae60; color: white; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; margin-left: 8px;">{conf_pct}</span>
                </div>
                <div class="step-desc">{step.description}</div>
                {f'<div style="margin-top: 8px; padding: 8px; background: #f5f5f5; border-radius: 4px; font-size: 0.85rem; color: #555;">{step.details}</div>' if step.details else ""}
            </div>
            """, unsafe_allow_html=True)
        
        st.markdown("---")
        st.markdown("**Evidence Sentences:**")
        for i, ev in enumerate(explanation.evidence_sentences, 1):
            st.markdown(f"""
            <div style="background: #fff9e6; border-left: 3px solid #f1c40f; padding: 10px; margin: 8px 0; color: #333;">
                <strong>Evidence {i}:</strong> {ev}
            </div>
            """, unsafe_allow_html=True)
    
    # Footer
    st.markdown("""
    <div class="classic-footer">
        Finance Q&A with Explainable AI | Powered by SHAP & LIME
    </div>
    """, unsafe_allow_html=True)


def render_upload_page():
    """Render the document upload page"""
    import time
    
    st.markdown("""
    <div class="upload-container">
        <div class="upload-header">
            <h1>Document Intelligence</h1>
            <p>Upload your documents to enable intelligent Q&A</p>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Upload section
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("""
        <div class="upload-box">
            <div class="upload-icon">📄</div>
            <div class="upload-text">Drag and drop your document here</div>
            <div class="upload-formats">Supported formats: PDF, TXT, DOCX</div>
        </div>
        """, unsafe_allow_html=True)
        
        uploaded_file = st.file_uploader(
            "Choose a file",
            type=["pdf", "txt", "docx"],
            label_visibility="collapsed"
        )
        
        st.markdown("<div style='text-align: center; margin: 1rem 0; color: #888;'>— or —</div>", unsafe_allow_html=True)
        
        # Text input option
        text_input = st.text_area(
            "Paste your text directly:",
            placeholder="Paste your document content here...",
            height=150
        )
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Process button
        process_btn = st.button("Process Document", type="primary", use_container_width=True)
        
        if process_btn:
            if uploaded_file or text_input:
                # Store the file info for display
                if uploaded_file:
                    st.session_state.uploaded_file_name = uploaded_file.name
                    st.session_state.uploaded_file_size = f"{uploaded_file.size / 1024:.1f} KB"
                else:
                    st.session_state.uploaded_file_name = "Pasted Text"
                    st.session_state.uploaded_file_size = f"{len(text_input)} characters"
                
                # Always use the static demo paragraph (ignore uploaded content)
                st.session_state.current_paragraph = DEFAULT_PARAGRAPH
                
                st.session_state.current_page = "processing"
                st.rerun()
            else:
                st.warning("Please upload a file or paste some text.")


def render_processing_page():
    """Render the fake processing animation page"""
    import time
    
    st.markdown("""
    <div class="processing-container">
        <div class="processing-spinner"></div>
        <div class="processing-text">Processing your document...</div>
        <div class="processing-step" id="current-step">Analyzing structure...</div>
    </div>
    """, unsafe_allow_html=True)
    
    # Simulate processing steps
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    steps = [
        ("Analyzing document structure...", 20),
        ("Extracting text content...", 40),
        ("Building knowledge index...", 60),
        ("Preparing Q&A engine...", 80),
        ("Finalizing...", 100)
    ]
    
    for step_text, progress in steps:
        status_text.markdown(f"<p style='text-align: center; color: #666;'>{step_text}</p>", unsafe_allow_html=True)
        progress_bar.progress(progress)
        time.sleep(0.6)
    
    # Move to success page
    st.session_state.current_page = "success"
    st.rerun()


def render_success_page():
    """Render the success page after document processing"""
    
    file_name = st.session_state.get("uploaded_file_name", "document.pdf")
    file_size = st.session_state.get("uploaded_file_size", "Unknown")
    
    st.markdown("""
    <div class="success-container">
        <div class="success-icon">
            <span>✓</span>
        </div>
        <div class="success-title">Document Processed Successfully!</div>
        <div class="success-subtitle">Your document is ready for intelligent Q&A</div>
    </div>
    """, unsafe_allow_html=True)
    
    # Document info
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown(f"""
        <div class="doc-info">
            <div class="doc-info-item">
                <span class="doc-info-label">Document</span>
                <span class="doc-info-value">{file_name}</span>
            </div>
            <div class="doc-info-item">
                <span class="doc-info-label">Size</span>
                <span class="doc-info-value">{file_size}</span>
            </div>
            <div class="doc-info-item">
                <span class="doc-info-label">Status</span>
                <span class="doc-info-value" style="color: #27ae60;">Ready</span>
            </div>
            <div class="doc-info-item">
                <span class="doc-info-label">Chunks Indexed</span>
                <span class="doc-info-value">12 sections</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Ask Q&A button
        if st.button("Ask Q&A", type="primary", use_container_width=True):
            st.session_state.current_page = "qa"
            st.session_state.document_loaded = True
            st.rerun()
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Upload another button
        if st.button("Upload Another Document", use_container_width=True):
            st.session_state.current_page = "upload"
            st.rerun()


def main():
    # Initialize session state
    init_hitl_session_state()
    
    if "current_page" not in st.session_state:
        st.session_state.current_page = "upload"  # Start with upload page
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    if "current_paragraph" not in st.session_state:
        st.session_state.current_paragraph = DEFAULT_PARAGRAPH
    if "document_loaded" not in st.session_state:
        st.session_state.document_loaded = False
    
    # Check if HITL dashboard is active
    if st.session_state.get("hitl_active", False):
        render_hitl_dashboard()
        return
    
    # Route to appropriate page
    current_page = st.session_state.get("current_page", "upload")
    
    if current_page == "upload":
        render_upload_page()
    elif current_page == "processing":
        render_processing_page()
    elif current_page == "success":
        render_success_page()
    elif current_page == "qa":
        render_qa_page()
    elif current_page == "xai":
        render_xai_page()
    else:
        render_upload_page()


if __name__ == "__main__":
    main()
