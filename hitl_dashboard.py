"""
Human-in-the-Loop (HITL) Dashboard Views
=========================================
Workflow: Retrieval → Q&A → XAI → Human Review (HITL) → Knowledge Update

This module contains only UI rendering functions.
Data models are in models.py, API client in services.py, CSS in styles.py.
"""

import streamlit as st
from datetime import datetime

from models import HITLFeedback, FeedbackType, FeedbackPriority
from services import MemoryEndpoint
from styles import apply_hitl_styles


def init_hitl_session_state():
    """Initialize HITL-related session state variables"""
    defaults = {
        "hitl_active": False,
        "current_explanation": None,
        "current_question": "",
        "current_paragraph": "",
        "feedback_history": [],
        "pending_feedback": [],
        "show_history": False,
        "has_results": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def render_hitl_button():
    """Render the HITL Dashboard entry button - original version"""
    st.markdown("""
    <div class="hitl-button-container">
        <div class="hitl-title">Human Review Available</div>
        <div class="hitl-subtitle">Review the XAI explanation and provide feedback to improve the system</div>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button("Enter HITL Dashboard", type="primary", use_container_width=True, key="enter_hitl_btn"):
            st.session_state.hitl_active = True
            st.rerun()


def render_hitl_button_classic():
    """Render a classic-styled HITL button"""
    if st.button("Human Review (HITL)", use_container_width=True, key="hitl_classic_btn"):
        st.session_state.hitl_active = True
        st.rerun()


def render_feedback_history(memory: MemoryEndpoint):
    """Render feedback history section"""
    st.markdown("## Feedback History")
    
    history = memory.get_feedback_history(limit=20)
    
    if not history:
        st.info("No feedback history yet.")
        return
    
    # Summary metrics
    total = len(history)
    correct = sum(1 for f in history if f.get("is_answer_correct", False))
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Feedback", total)
    with col2:
        st.metric("Correct Answers", correct)
    with col3:
        accuracy = (correct / total * 100) if total > 0 else 0
        st.metric("Accuracy Rate", f"{accuracy:.1f}%")
    
    # Feedback list
    for i, feedback in enumerate(reversed(history)):
        with st.expander(f"{feedback.get('feedback_id', f'Feedback {i+1}')} - {feedback.get('feedback_type', 'N/A')}"):
            st.markdown(f"**Question:** {feedback.get('question', 'N/A')}")
            st.markdown(f"**Original Answer:** {feedback.get('original_answer', 'N/A')}")
            if feedback.get('corrected_answer'):
                st.markdown(f"**Corrected Answer:** {feedback.get('corrected_answer')}")
            ratings = feedback.get('ratings', {})
            st.markdown(f"**Ratings:** Clarity: {ratings.get('explanation_quality', 'N/A')}/5 | Highlights: {ratings.get('highlight_accuracy', 'N/A')}/5 | Helpfulness: {ratings.get('xai_helpfulness', 'N/A')}/5")


def render_hitl_mini_status():
    """Render a mini status bar showing pending feedback count"""
    pending = len(st.session_state.get("pending_feedback", []))
    history = len(st.session_state.get("feedback_history", []))
    
    if pending > 0 or history > 0:
        st.markdown(f"""
        <div style="position: fixed; bottom: 20px; right: 20px; background: #34495e; 
                    color: white; padding: 10px 15px; border-radius: 25px; 
                    font-size: 0.85rem; box-shadow: 0 2px 10px rgba(0,0,0,0.2); z-index: 1000;">
            Feedback: {history} submitted | {pending} pending
        </div>
        """, unsafe_allow_html=True)


def render_hitl_dashboard():
    """Render the full HITL Dashboard as a dedicated page"""
    memory = MemoryEndpoint()
    
    # Apply HITL-specific styles
    apply_hitl_styles()
    
    # Header
    st.markdown("""
    <div class="hitl-header">
        <h1>Human-in-the-Loop Review</h1>
        <p>Provide feedback to improve the Q&A system</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Workflow Progress Bar
    st.markdown("""
    <div class="workflow-bar">
        <span class="workflow-step workflow-done">Retrieval</span>
        <span class="workflow-arrow">-</span>
        <span class="workflow-step workflow-done">Q&A</span>
        <span class="workflow-arrow">-</span>
        <span class="workflow-step workflow-done">XAI Analysis</span>
        <span class="workflow-arrow">-</span>
        <span class="workflow-step workflow-current">HITL Review</span>
        <span class="workflow-arrow">-</span>
        <span class="workflow-step workflow-pending">Knowledge Update</span>
    </div>
    """, unsafe_allow_html=True)
    
    # Back button and connection status
    col1, col2, col3 = st.columns([1, 2, 1])
    with col1:
        if st.button("Back to Q&A", key="back_to_qa", use_container_width=True):
            st.session_state.hitl_active = False
            st.rerun()
    with col3:
        if memory.check_connection():
            st.success("Connected")
        else:
            st.info("Offline Mode")
    
    st.markdown("---")
    
    # Check if we have data to review
    if st.session_state.current_explanation is None:
        st.warning("No Q&A result to review. Please go back and ask a question first.")
        return
    
    explanation = st.session_state.current_explanation
    question = st.session_state.current_question
    paragraph = st.session_state.current_paragraph
    
    # === CONTEXT SECTION ===
    st.markdown("## Review Context")
    
    # Question Card
    st.markdown(f"""
    <div class="context-card" style="border-left: 4px solid #3498db;">
        <div class="context-label">QUESTION</div>
        <div class="context-content" style="font-size: 1.15rem; font-weight: 500;">{question}</div>
    </div>
    """, unsafe_allow_html=True)
    
    # Answer Card
    st.markdown(f"""
    <div class="context-card" style="border-left: 4px solid #27ae60;">
        <div class="context-label">MODEL ANSWER</div>
        <div class="context-content">{explanation.answer}</div>
        <div style="margin-top: 0.75rem;">
            <span style="background: #27ae60; color: white; padding: 4px 12px; border-radius: 15px; font-size: 0.8rem;">
                Confidence: {explanation.confidence_score:.1%}
            </span>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Expandable Source Context
    with st.expander("View Source Paragraph"):
        st.markdown(f"""
        <div style="background: #f1f3f4; padding: 1rem; border-radius: 8px; color: #333; line-height: 1.8;">
            {paragraph}
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    # === FEEDBACK FORM ===
    st.markdown("## Your Feedback")
    
    # Section 1: Answer Correctness
    st.markdown("""
    <div class="feedback-section">
        <h3>1. Is the answer correct?</h3>
    </div>
    """, unsafe_allow_html=True)
    
    feedback_options = [
        ("Correct - The answer is accurate", FeedbackType.CORRECT),
        ("Incorrect - The answer is wrong", FeedbackType.INCORRECT),
        ("Partially Correct - Some parts are right", FeedbackType.PARTIALLY_CORRECT),
        ("Needs More Context - Answer is incomplete", FeedbackType.NEEDS_MORE_CONTEXT)
    ]
    
    selected_option = st.radio(
        "Select one:",
        options=feedback_options,
        format_func=lambda x: x[0],
        key="answer_feedback",
        label_visibility="collapsed"
    )
    selected_feedback_type = selected_option[1]
    
    # Corrected Answer (conditional)
    corrected_answer = None
    if selected_feedback_type in [FeedbackType.INCORRECT, FeedbackType.PARTIALLY_CORRECT]:
        st.markdown("**Please provide the correct answer:**")
        corrected_answer = st.text_area(
            "Correct Answer",
            placeholder="Enter the correct or improved answer here...",
            key="corrected_answer_input",
            label_visibility="collapsed",
            height=100
        )
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # Section 2: XAI Quality Ratings
    st.markdown("""
    <div class="feedback-section">
        <h3>2. Rate the XAI Explanation Quality</h3>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("**Explanation Clarity**")
        explanation_quality = st.slider(
            "How clear was the explanation?",
            min_value=1, max_value=5, value=3,
            key="rating_explanation",
            label_visibility="collapsed"
        )
        st.caption("1 = Confusing, 5 = Very Clear")
    
    with col2:
        st.markdown("**Highlight Accuracy**")
        highlight_accuracy = st.slider(
            "Were highlights relevant?",
            min_value=1, max_value=5, value=3,
            key="rating_highlights",
            label_visibility="collapsed"
        )
        st.caption("1 = Irrelevant, 5 = Spot On")
    
    with col3:
        st.markdown("**Overall Helpfulness**")
        xai_helpfulness = st.slider(
            "Did XAI help understanding?",
            min_value=1, max_value=5, value=3,
            key="rating_helpfulness",
            label_visibility="collapsed"
        )
        st.caption("1 = Not Helpful, 5 = Very Helpful")
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # Section 3: Additional Comments
    st.markdown("""
    <div class="feedback-section">
        <h3>3. Additional Comments (Optional)</h3>
    </div>
    """, unsafe_allow_html=True)
    
    additional_comments = st.text_area(
        "Share any additional thoughts or suggestions:",
        placeholder="E.g., 'The SHAP highlights were more useful than LIME for this question' or 'Missing information about...'",
        key="additional_comments_input",
        label_visibility="collapsed",
        height=100
    )
    
    # Knowledge Suggestion
    st.markdown("**Suggest Knowledge Update (Optional):**")
    knowledge_suggestion = st.text_area(
        "Knowledge Update",
        placeholder="If there's missing or incorrect information in the knowledge base, suggest updates here...",
        key="knowledge_suggestion_input",
        label_visibility="collapsed",
        height=80
    )
    
    st.markdown("---")
    
    # === SUBMIT SECTION ===
    col_submit1, col_submit2, col_submit3 = st.columns([1, 2, 1])
    
    with col_submit2:
        submit_clicked = st.button(
            "Submit Feedback",
            type="primary",
            use_container_width=True,
            key="submit_feedback_btn"
        )
    
    if submit_clicked:
        # Create feedback object
        feedback = HITLFeedback(
            feedback_id=f"fb_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            timestamp=datetime.now().isoformat(),
            question=question,
            original_answer=explanation.answer,
            feedback_type=selected_feedback_type,
            is_answer_correct=(selected_feedback_type == FeedbackType.CORRECT),
            corrected_answer=corrected_answer if corrected_answer else None,
            explanation_quality=explanation_quality,
            highlight_accuracy=highlight_accuracy,
            xai_helpfulness=xai_helpfulness,
            additional_context=additional_comments if additional_comments else None,
            knowledge_update=knowledge_suggestion if knowledge_suggestion else None,
            priority=FeedbackPriority.MEDIUM
        )
        
        # Submit to memory endpoint
        result = memory.submit_feedback(feedback)
        
        # Store in local history
        if "feedback_history" not in st.session_state:
            st.session_state.feedback_history = []
        st.session_state.feedback_history.append(feedback.to_dict())
        
        # Show success message
        st.markdown(f"""
        <div class="submit-success">
            <h2 style="margin: 0;">Feedback Submitted Successfully!</h2>
            <p style="margin: 0.5rem 0 0 0;">Feedback ID: {feedback.feedback_id}</p>
            <p style="margin: 0.25rem 0 0 0; opacity: 0.9;">Thank you for helping improve the system.</p>
        </div>
        """, unsafe_allow_html=True)
        
        # Show what was submitted
        with st.expander("View Submitted Feedback Details"):
            st.json(feedback.to_dict())
        
        # Option to go back or submit another
        st.markdown("<br>", unsafe_allow_html=True)
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("Back to Q&A", key="back_after_submit", use_container_width=True):
                st.session_state.hitl_active = False
                st.rerun()
        with col_b:
            if st.button("View Feedback History", key="view_history", use_container_width=True):
                st.session_state.show_history = True
                st.rerun()
    
    # Show history if requested
    if st.session_state.get("show_history", False):
        st.markdown("---")
        render_feedback_history(memory)
