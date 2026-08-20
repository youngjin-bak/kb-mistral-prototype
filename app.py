import streamlit as st
import json
import os
import urllib.request

# ==========================================
# 1. Mock State & Authentication Setup
# ==========================================
def init_state():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
        st.session_state.auth_target_name = "youngjin bak" 
        st.session_state.active_intent = None
        st.session_state.collected_params = {}
        st.session_state.awaiting_input_for = None
        
        st.session_state.balance = 1250000
        st.session_state.card_status = "ACTIVE"
        st.session_state.pending_action = None
        st.session_state.last_trace = []
        st.session_state.chat_history = []

def add_trace(component, detail):
    st.session_state.last_trace.append({"component": component, "detail": detail})

# ==========================================
# 2. Enterprise Layer (Mock System of Record)
# ==========================================
def api_get_balance():
    return st.session_state.balance

def api_lock_card(card_id):
    st.session_state.card_status = "LOCKED"
    return True

def api_unlock_card(card_id):
    st.session_state.card_status = "ACTIVE"
    return True

def api_transfer(account_id, amount_str):
    """상태(Balance)를 실제로 변경하는 결정론적 트랜잭션 함수"""
    clean_amt = str(amount_str).replace(",", "").replace("krw", "").strip()
    try:
        transfer_amount = int(clean_amt)
        if st.session_state.balance >= transfer_amount:
            st.session_state.balance -= transfer_amount
            return True
        return False # 잔액 부족
    except ValueError:
        return False # 숫자 변환 실패

# ==========================================
# 3. Governance Layer (Policy Engine & Knowledge Base)
# ==========================================
def evaluate_policy(intent):
    if not st.session_state.authenticated and intent != "FAQ":
        return "AUTH_REQUIRED"

    policies = {
        "FAQ": "NO_TRANSACTION",
        "BALANCE": "READ_ONLY",
        "CARD_LOCK": "HUMAN_APPROVAL_REQUIRED",
        "CARD_UNLOCK": "HUMAN_APPROVAL_REQUIRED",
        "TRANSFER": "HUMAN_APPROVAL_REQUIRED"
    }
    return policies.get(intent, "DENY")

MOCK_KNOWLEDGE_BASE = {
    "Gangnam": {
        "hours": "9 AM to 4 PM, Mon-Fri",
        "phone": "02-123-4567",
        "loan_officer": "John Doe (john@kb.com)"
    },
    "Jongno": {
        "hours": "9 AM to 4 PM, Mon-Fri",
        "phone": "02-987-6543"
    }
}

def retrieve_knowledge(branch, attribute):
    if not branch or not attribute: return None
    branch_data = MOCK_KNOWLEDGE_BASE.get(branch.capitalize())
    if not branch_data: return None
    return branch_data.get(attribute.lower())

# ==========================================
# 4. Probabilistic AI Layer (Mistral REST API)
# ==========================================
def classify_intent(user_message):
    api_key = os.environ.get("MISTRAL_API_KEY", "")
    if not api_key: return {"intent": "UNKNOWN", "parameters": {}}
        
    url = "https://api.mistral.ai/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    payload = {
        "model": "mistral-small-latest",
        "messages": [
            {
                "role": "system",
                "content": """
                Classify the request into one category: FAQ, BALANCE, CARD_LOCK, CARD_UNLOCK, TRANSFER, UNKNOWN.
                
                - For FAQ: Extract 'branch' and 'attribute'. The 'attribute' MUST be mapped to exactly one of: 'hours' (for open/close time), 'phone', or 'loan_officer'.
                - For TRANSFER: Extract 'target_bank', 'target_account', and 'amount'. If any of these are missing in the user's input, omit the key entirely. Do not use placeholders (e.g., 'unknown', 'N/A').
                
                You MUST return ONLY a valid JSON object with EXACTLY these two keys: "intent" and "parameters".
                Example: {"intent": "FAQ", "parameters": {"branch": "Gangnam", "attribute": "hours"}}
                """
            },
            {"role": "user", "content": user_message}
        ],
        "response_format": {"type": "json_object"}
    }
    
    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            content = res_data['choices'][0]['message']['content']
            
            clean_content = content.replace("```json", "").replace("
