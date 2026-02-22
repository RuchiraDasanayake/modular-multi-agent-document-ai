"""
CSS Styles for Finance Q&A Bot with XAI
All styles are centralized here for easy maintenance.
"""

# Main CSS styles
MAIN_CSS = """
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
"""

# HITL Dashboard CSS styles
HITL_CSS = """
<style>
    /* HITL Page Styles - Classic */
    .hitl-header {
        background: #2c3e50;
        padding: 2rem;
        border-radius: 8px;
        margin-bottom: 2rem;
        text-align: center;
        border: 1px solid #34495e;
    }
    .hitl-header h1 {
        color: white;
        margin: 0;
        font-size: 2rem;
    }
    .hitl-header p {
        color: rgba(255,255,255,0.85);
        margin: 0.5rem 0 0 0;
    }
    
    .hitl-button-container {
        text-align: center;
        margin: 2rem 0;
        padding: 1.5rem;
        background: #2c3e50;
        border-radius: 8px;
        border: 1px solid #34495e;
    }
    .hitl-title {
        color: white;
        font-size: 1.2rem;
        margin-bottom: 0.5rem;
    }
    .hitl-subtitle {
        color: rgba(255,255,255,0.85);
        font-size: 0.9rem;
    }
    
    .workflow-bar {
        display: flex;
        justify-content: center;
        align-items: center;
        gap: 8px;
        margin: 1.5rem 0;
        flex-wrap: wrap;
    }
    .workflow-step {
        padding: 8px 16px;
        border-radius: 20px;
        font-size: 0.85rem;
        font-weight: 500;
    }
    .workflow-done {
        background: #27ae60;
        color: white;
    }
    .workflow-current {
        background: #3498db;
        color: white;
        font-weight: bold;
        box-shadow: 0 2px 8px rgba(52, 152, 219, 0.4);
    }
    .workflow-pending {
        background: #95a5a6;
        color: white;
    }
    .workflow-arrow {
        color: #bdc3c7;
        font-size: 1.2rem;
    }
    
    .context-card {
        background: #f8f9fa;
        border: 1px solid #e9ecef;
        border-radius: 12px;
        padding: 1.25rem;
        margin: 1rem 0;
    }
    .context-label {
        color: #6c757d;
        font-size: 0.85rem;
        font-weight: 600;
        margin-bottom: 0.5rem;
    }
    .context-content {
        color: #212529;
        font-size: 1rem;
        line-height: 1.6;
    }
    
    .feedback-section {
        background: white;
        border: 1px solid #e9ecef;
        border-radius: 12px;
        padding: 1.5rem;
        margin: 1.5rem 0;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05);
    }
    .feedback-section h3 {
        color: #2c3e50;
        margin-top: 0;
        padding-bottom: 0.75rem;
        border-bottom: 2px solid #e9ecef;
    }
    
    .rating-container {
        background: #f8f9fa;
        border-radius: 10px;
        padding: 1rem;
        margin: 0.5rem 0;
    }
    
    .submit-success {
        background: #27ae60;
        color: white;
        padding: 1.5rem;
        border-radius: 8px;
        text-align: center;
        margin: 1rem 0;
        border: 1px solid #229954;
    }
</style>
"""


def apply_styles():
    """Apply main CSS styles to the Streamlit app"""
    import streamlit as st
    st.markdown(MAIN_CSS, unsafe_allow_html=True)


def apply_hitl_styles():
    """Apply HITL dashboard CSS styles"""
    import streamlit as st
    st.markdown(HITL_CSS, unsafe_allow_html=True)
