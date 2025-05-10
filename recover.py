# app.py
import streamlit as st
import google.generativeai as genai
import json
from datetime import datetime

# Configure Gemini API
API_KEY = "AIzaSyA-9-lTQTWdNM43YdOXMQwGKDy0SrMwo6c"  # Replace with your actual API key
genai.configure(api_key=API_KEY)
gemini_model = genai.GenerativeModel('gemini-1.5-flash')

# Initialize session state data
if 'patients' not in st.session_state:
    st.session_state.patients = [
        {"id": 1, "name": "Patient 1", "severity": "green"},
        {"id": 2, "name": "Patient 2", "severity": "green"},
        {"id": 3, "name": "Patient 3", "severity": "green"}
    ]

if 'conversations' not in st.session_state:
    st.session_state.conversations = []

if 'symptoms' not in st.session_state:
    st.session_state.symptoms = []

# Clinical questions
KEY_QUESTIONS = [
    {"text": "Are you having difficulty breathing?", "likert": True, "severity": "most_severe", "color": "red"},
    {"text": "Are you having a fever of over 100 degrees, or chills?", "likert": False, "severity": "most_severe", "color": "red"},
    {"text": "Have you had persistent constipation, nausea, or vomiting?", "likert": True, "severity": "moderate", "color": "yellow"},
    {"text": "Is there anything else you’d like to comment on?", "likert": False, "severity": "N/A", "color": "purple"}
]

SYSTEM_PROMPT = """
You are RECOVER Bot, a friendly conversational agent for postoperative gastrointestinal cancer patients to report symptoms daily. Follow these steps:

1. **Greeting**: Start with a friendly greeting and immediately ask the first question.
   Example: "Hi there! Let's start today's symptom check. Are you having difficulty breathing?"

2. **Question Flow**: Ask these questions one at a time in order:
{questions}

3. **Follow-ups**: If patient reports a symptom:
   - Ask "When did it start?"
   - Ask "How severe is it (1-10)?"

4. **Clarifications**: Explain medical terms in simple language.
   Example: "Constipation means having fewer bowel movements than usual."

5. **Completion**: After all questions, say: "Thank you! Your doctor will review this."

Never provide medical advice. For emergencies, say: "Please call 911 immediately."
"""

class ConversationAgent:
    def __init__(self, patient_id):
        self.patient_id = patient_id
        self.history = []
        self.question_status = {q['text']: 'not discussed' for q in KEY_QUESTIONS}
        self.current_question = None

    def format_prompt(self):
        questions_list = [f"- {q['text']}" for q in KEY_QUESTIONS]
        return SYSTEM_PROMPT.format(questions="\n".join(questions_list))

    def get_next_question(self):
        for q in KEY_QUESTIONS:
            if self.question_status[q['text']] == 'not discussed':
                return q['text']
        return None

    def process_response(self, user_input):
        self.history.append({"role": "user", "content": user_input})

        if self.current_question:
            if any(kw in user_input.lower() for kw in ['yes', 'no']) or \
               any(str(i) in user_input for i in range(1, 11)):
                self.question_status[self.current_question] = 'discussed'
            else:
                self.question_status[self.current_question] = 'in discussion'

        self.current_question = self.get_next_question()
        prompt_parts = [
            self.format_prompt(),
            "\nConversation History:"
        ]
        
        for msg in self.history:
            prompt_parts.append(f"\n{msg['role'].title()}: {msg['content']}")
        
        if self.current_question:
            prompt_parts.append(f"\nASSISTANT: [Next question to ask: {self.current_question}]")

        try:
            response = gemini_model.generate_content("\n".join(prompt_parts))
            bot_response = response.text
        except Exception as e:
            bot_response = "Sorry, I'm having trouble processing that. Please try again."

        self.history.append({"role": "assistant", "content": bot_response})
        return bot_response

    def save_conversation(self):
        conversation = {
            "id": len(st.session_state.conversations) + 1,
            "patient_id": self.patient_id,
            "timestamp": datetime.now().isoformat(),
            "log": json.dumps(self.history),
            "summary": ""
        }
        st.session_state.conversations.append(conversation)
        return conversation['id']

def extract_symptoms(conversation_id, log):
    prompt = """
    Analyze this conversation and extract symptom information. Return JSON format:
    {
        "symptoms": [{
            "question": "original question text",
            "response": "patient's answer",
            "severity": "from question config",
            "color": "from question config"
        }]
    }
    
    Conversation Log: {log}
    """
    try:
        response = gemini_model.generate_content(prompt.format(log=log))
        extracted = json.loads(response.text)
        symptoms_list = extracted.get('symptoms', [])
    except:
        symptoms_list = []

    for item in symptoms_list:
        q_config = next((q for q in KEY_QUESTIONS if q['text'] == item['question']), None)
        if q_config:
            symptom = {
                "id": len(st.session_state.symptoms) + 1,
                "conversation_id": conversation_id,
                "question": item['question'],
                "response": item.get('response', ''),
                "likert": item.get('likert', None),
                "severity": q_config['severity'],
                "color": q_config['color']
            }
            st.session_state.symptoms.append(symptom)
    return symptoms_list

def summarize_conversation(conversation_id, log):
    prompt = """
    Create a clinical summary of this conversation in bullet points. Focus on:
    - Reported symptoms
    - Severity levels
    - Patient comments
    Format: {"summary": "bullet points as markdown"}
    
    Conversation Log: {log}
    """
    try:
        response = gemini_model.generate_content(prompt.format(log=log))
        summary_data = json.loads(response.text)
        summary = summary_data.get('summary', 'No summary available.')
    except:
        summary = "Summary generation failed."

    for conv in st.session_state.conversations:
        if conv['id'] == conversation_id:
            conv['summary'] = summary
    return summary

# Streamlit UI
st.set_page_config(page_title="RECOVER System", layout="wide")

st.title("RECOVER: Remote Patient Monitoring System")

# Sidebar navigation
page = st.sidebar.radio("Navigation", ["Patient Interaction", "Doctor Dashboard"])

if page == "Patient Interaction":
    st.header("Patient Symptom Reporting")
    
    # Patient selection
    patient_id = st.selectbox(
        "Select Patient",
        options=[p['id'] for p in st.session_state.patients],
        format_func=lambda x: next(p['name'] for p in st.session_state.patients if p['id'] == x)
    )
    
    # Initialize conversation
    if 'agent' not in st.session_state or st.session_state.get('patient_id') != patient_id:
        st.session_state.agent = ConversationAgent(patient_id)
        st.session_state.patient_id = patient_id
        st.session_state.conversation_started = True
        initial_greeting = st.session_state.agent.process_response("")
        st.session_state.chat_history = [{"role": "assistant", "content": initial_greeting}]

    # Display chat history
    for msg in st.session_state.get('chat_history', []):
        if msg['role'] == 'assistant':
            st.markdown(f"**Bot**: {msg['content']}")
        else:
            st.markdown(f"**Patient**: {msg['content']}")

    # User input
    user_input = st.text_input("Type your response here:", key="patient_input")
    
    if st.button("Submit"):
        if user_input.strip():
            # Process response
            bot_response = st.session_state.agent.process_response(user_input)
            
            # Update chat history
            st.session_state.chat_history.append({"role": "user", "content": user_input})
            st.session_state.chat_history.append({"role": "assistant", "content": bot_response})
            
            # Save conversation when complete
            if not st.session_state.agent.current_question:
                conv_id = st.session_state.agent.save_conversation()
                # Get conversation from session state
                conversation = next(
                    c for c in st.session_state.conversations 
                    if c['id'] == conv_id
                )
                extract_symptoms(conv_id, conversation['log'])
                summarize_conversation(conv_id, conversation['log'])
                st.success("Conversation saved successfully!")
            
            st.rerun()

elif page == "Doctor Dashboard":
    st.header("Clinical Dashboard")
    
    # Patient selection
    selected_patient = st.selectbox(
        "Select Patient",
        options=st.session_state.patients,
        format_func=lambda x: x['name']
    )
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Patient Overview")
        st.metric("Patient Name", selected_patient['name'])
        st.metric("Current Status", selected_patient['severity'].upper())
        
        # Severity update
        new_severity = st.selectbox(
            "Update Status",
            ["green", "yellow", "red"],
            index=["green", "yellow", "red"].index(selected_patient['severity'])
        )
        if st.button("Update Status"):
            selected_patient['severity'] = new_severity
            st.success("Status updated!")
    
    with col2:
        st.subheader("Recent Symptoms")
        patient_conversations = [c for c in st.session_state.conversations if c['patient_id'] == selected_patient['id']]
        
        if patient_conversations:
            latest_conv = max(patient_conversations, key=lambda x: x['timestamp'])
            conv_symptoms = [s for s in st.session_state.symptoms if s['conversation_id'] == latest_conv['id']]
            
            for q in KEY_QUESTIONS:
                symptom = next((s for s in conv_symptoms if s['question'] == q['text']), None)
                color = q['color'] if not symptom else symptom['color']
                response = symptom['response'] if symptom else "Not reported"
                st.markdown(
                    f"**{q['text']}**<br>"
                    f"<span style='color:{color}; font-size:1.2em'>{response}</span>",
                    unsafe_allow_html=True
                )
        else:
            st.info("No conversations recorded for this patient")

    # Conversation history
    st.subheader("Conversation Logs")
    if patient_conversations:
        selected_conv = st.selectbox(
            "Select Conversation",
            options=patient_conversations,
            format_func=lambda x: datetime.fromisoformat(x['timestamp']).strftime("%Y-%m-%d %H:%M")
        )
        
        # Display conversation
        st.markdown("**Conversation Summary**")
        st.markdown(selected_conv['summary'])
        
        st.markdown("**Full Transcript**")
        messages = json.loads(selected_conv['log'])
        for msg in messages:
            if msg['role'] == 'assistant':
                st.markdown(f"**Bot**: {msg['content']}")
            else:
                st.markdown(f"**Patient**: {msg['content']}")
    else:
        st.info("No conversations available for this patient")

if __name__ == "__main__":
    st.write("Run the application with: streamlit run app.py")
