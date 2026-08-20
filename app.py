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
            
            # 1. 마크다운 백틱 및 공백 제거 (Sanitization)
            clean_content = content.replace("```json", "").replace("```", "").strip()
            
            # 2. JSON 파싱
            result = json.loads(clean_content)
            
            intent = result.get("intent", "UNKNOWN")
            parameters = result.get("parameters", {})
            
            VALID_INTENTS = ["FAQ", "BALANCE", "CARD_LOCK", "CARD_UNLOCK", "TRANSFER", "UNKNOWN"]
            if intent not in VALID_INTENTS:
                return {"intent": "UNKNOWN", "parameters": {}}
                
            return {"intent": intent, "parameters": parameters}
    except Exception as e:
        print(f"Mistral API Error: {e}")
        return {"intent": "UNKNOWN", "parameters": {}}

# ==========================================
# 5. Deterministic Orchestrator (State Machine)
# ==========================================
def handle_request(message):
    st.session_state.last_trace = [] 
    
    # 1. State Interception for Authentication
    if st.session_state.awaiting_input_for == "auth":
        if st.session_state.auth_target_name in message.lower():
            st.session_state.authenticated = True
            st.session_state.awaiting_input_for = None
            add_trace("🔐 Auth Engine", "Identity verified successfully.")
            return process_active_intent()
        else:
            add_trace("🔐 Auth Engine", f"Verification failed for input: {message}")
            return "Authentication failed. Please enter your registered full name to proceed."

    # 2. State Interception for Slot Filling (TRANSFER Sequence)
    if st.session_state.awaiting_input_for == "target_bank":
        st.session_state.collected_params["target_bank"] = message
        st.session_state.awaiting_input_for = None
        add_trace("📥 Slot Filling", f"Captured Target Bank: {message}")
        return process_active_intent()

    if st.session_state.awaiting_input_for == "target_account":
        st.session_state.collected_params["target_account"] = message
        st.session_state.awaiting_input_for = None
        add_trace("📥 Slot Filling", f"Captured Target Account: {message}")
        return process_active_intent()

    if st.session_state.awaiting_input_for == "amount":
        st.session_state.collected_params["amount"] = message
        st.session_state.awaiting_input_for = None
        add_trace("📥 Slot Filling", f"Captured Amount: {message}")
        return process_active_intent()

    # 3. New Request Classification
    nlu_result = classify_intent(message)
    intent = nlu_result["intent"]
    
    if intent != "UNKNOWN":
        st.session_state.active_intent = intent
        st.session_state.collected_params = nlu_result["parameters"]
        add_trace("🤖 Mistral NLU", f"Extracted Intent: {intent}")
    else:
        add_trace("🤖 Mistral NLU", "Failed to classify intent.")
        return "I couldn't understand your request. Please try again."

    return process_active_intent()

def process_active_intent():
    intent = st.session_state.active_intent
    params = st.session_state.collected_params

    decision = evaluate_policy(intent)
    add_trace("⚖️ Policy Engine", f"Decision: {decision}")

    if decision == "AUTH_REQUIRED":
        st.session_state.awaiting_input_for = "auth"
        add_trace("🔐 Auth Engine", "Halted workflow. Requesting Identity Verification.")
        return "For your security, please verify your identity by entering your full name."

        # 1. Null 값 및 형식 검증을 강화한 통합 함수
    def is_invalid_param(val, param_type="text"):
        if not val: return True
        val_str = str(val).strip().lower()
        if val_str in ["unknown", "n/a", "none", "null", ""]: return True
        
        # 2. 계좌번호 포맷 엄격 검증: 하이픈/공백 제외 오직 숫자로만 구성되어야 함
        if param_type == "account":
            clean_account = val_str.replace("-", "").replace(" ", "")
            if not clean_account.isdigit():
                return True
        return False

    # 3. 강화된 검증 로직 적용
    if intent == "TRANSFER":
        if is_invalid_param(params.get("target_bank"), "text"):
            st.session_state.awaiting_input_for = "target_bank"
            add_trace("⚠️ Validation", "Missing or invalid target_bank.")
            return "Please enter the name of the receiving bank."
            
        if is_invalid_param(params.get("target_account"), "account"):
            st.session_state.awaiting_input_for = "target_account"
            add_trace("⚠️ Validation", "Missing or invalid target_account.")
            return "Please enter a valid target account number (must contain numbers)."
            
        if is_invalid_param(params.get("amount"), "text"):
            st.session_state.awaiting_input_for = "amount"
            add_trace("⚠️ Validation", "Missing amount.")
            return "Please enter the amount you wish to transfer."

    # (이하 기존 분기 로직 동일)
    if decision == "NO_TRANSACTION":
        add_trace("🔄 Orchestrator", "Routed to Knowledge Tool")
        branch = params.get("branch", "")
        attribute = params.get("attribute", "")
        retrieved_info = retrieve_knowledge(branch, attribute)
        
        if retrieved_info:
            return f"The {attribute} for {branch} branch is: {retrieved_info}"
            
        st.session_state.pending_action = {
            "intent": "FAQ_MISSING_DATA",
            "branch": branch,
            "attribute": attribute,
            "status": "PENDING"
        }
        return "I don't have that specific information. Transferring to a human operator."
        
    elif decision == "READ_ONLY":
        balance = api_get_balance()
        add_trace("🔧 Banking Tool", "Executed api_get_balance()")
        return f"Your current balance is {balance:,} KRW."
        
    elif decision == "HUMAN_APPROVAL_REQUIRED":
        action_map = {
            "CARD_LOCK": "LOCK_CARD",
            "CARD_UNLOCK": "UNLOCK_CARD",
            "TRANSFER": "TRANSFER"
        }
        
        target_display = f"{params.get('target_bank')} {params.get('target_account')}" if intent == "TRANSFER" else "****1234"
        
        st.session_state.pending_action = {
            "intent": intent,
            "action": action_map.get(intent),
            "internal_id": "CARD001" if "CARD" in intent else params.get("target_account"),
            "display_target": target_display,
            "status": "PENDING",
            "human_summary": f"Customer requested a {intent} transaction.",
            "verification_rule": f"Identity verified: {st.session_state.authenticated}",
            "amount": params.get("amount", "N/A")
        }
        add_trace("⏳ Orchestrator", "Halted workflow for Human Approval")
        return "Final approval from an authorized agent is required. Please wait while an operator reviews your request."

def execute_pending_action():
    action = st.session_state.pending_action
    
    if action["action"] == "LOCK_CARD":
        if api_lock_card(action["internal_id"]):
            add_trace("⚙️ Banking API", "Executed api_lock_card()")
            return True
            
    elif action["action"] == "UNLOCK_CARD":
        if api_unlock_card(action["internal_id"]):
            add_trace("⚙️ Banking API", "Executed api_unlock_card()")
            return True
            
    elif action["action"] == "TRANSFER":
        add_trace("⚙️ Banking API", f"Executed api_transfer to {action['internal_id']}")
        return True
        
    return False

# ==========================================
# 6. Presentation Layer (Streamlit UI)
# ==========================================
def main():
    st.set_page_config(layout="wide")
    st.title("KB AI Assistant Prototype")
    
    col_chat, col_trace = st.columns([1, 1])

    with col_chat:
        st.subheader("Customer Chat")
        
        # UI Modification 1: Scrollable Chat Container (height fixed to 600px)
        chat_container = st.container(height=600)
        with chat_container:
            for msg in st.session_state.chat_history:
                st.chat_message(msg["role"]).write(msg["content"])

        user_input = st.chat_input("Enter request here...")
        if user_input:
            # Append user message
            st.session_state.chat_history.append({"role": "user", "content": user_input})
            
            # Since chat input doesn't rerun the whole script implicitly in the container block in the same way,
            # we run handle_request and append assistant response before the st.rerun()
            response = handle_request(user_input)
            st.session_state.chat_history.append({"role": "assistant", "content": response})
            st.rerun()

    with col_trace:
        st.subheader("System of Record")
        auth_indicator = "✅ VERIFIED" if st.session_state.authenticated else "❌ UNVERIFIED"
        
        col_sys1, col_sys2, col_sys3 = st.columns(3)
        col_sys1.write(f"**Auth:** {auth_indicator}")
        col_sys2.write(f"**Balance:** {st.session_state.balance:,} KRW")
        col_sys3.write(f"**Card:** {st.session_state.card_status}")
        st.divider()
        
        st.subheader("Execution Trace")
        if st.session_state.last_trace:
            for step in st.session_state.last_trace:
                st.info(f"**{step['component']}** ➔ {step['detail']}")

        if st.session_state.pending_action and st.session_state.pending_action["status"] == "PENDING":
            action = st.session_state.pending_action
            
            if action.get("intent") == "FAQ_MISSING_DATA":
                st.warning("⚠️ Operator Input Required")
                st.write(f"**Requested Branch:** {action.get('branch')}")
                st.write(f"**Requested Attribute:** {action.get('attribute')}")
                
                operator_response = st.text_input("Enter the answer to send:")
                if st.button("📤 Send to Customer"):
                    if operator_response:
                        add_trace("👤 Operator", "Provided manual response")
                        st.session_state.chat_history.append({"role": "assistant", "content": f"[Operator] {operator_response}"})
                        st.session_state.pending_action = None
                        st.rerun()
            else:
                st.warning("⚠️ Human Approval Required")
                st.markdown("#### 📋 Transaction Summary")
                st.write(f"**Summary:** {action.get('human_summary')}")
                st.write(f"**Security Check:** {action.get('verification_rule')}")
                st.write(f"**Target Identifier:** {action.get('display_target')}")
                if action.get("amount") != "N/A":
                    st.write(f"**Amount:** {action.get('amount')}")
                
                # UI Modification 3: Operator Note and Chat Feedback
                operator_note = st.text_input("Operator Note (Optional):", key="op_note_input")
                
                btn_col1, btn_col2 = st.columns(2)
                if btn_col1.button("✅ Approve"):
                    add_trace("👤 Human Approval", "APPROVED")
                    execute_pending_action() 
                    
                    sys_msg = "Transaction approved and executed by human operator."
                    if operator_note: sys_msg += f" Operator message: '{operator_note}'"
                    st.session_state.chat_history.append({"role": "assistant", "content": f"[System] {sys_msg}"})
                    
                    st.session_state.pending_action["status"] = "EXECUTED"
                    st.session_state.active_intent = None
                    st.session_state.collected_params = {}
                    st.rerun()
                    
                if btn_col2.button("❌ Reject"):
                    add_trace("👤 Human Approval", "REJECTED")
                    
                    sys_msg = "Transaction request denied by human operator."
                    if operator_note: sys_msg += f" Operator message: '{operator_note}'"
                    else: sys_msg += " Please verify your details to proceed."
                    st.session_state.chat_history.append({"role": "assistant", "content": f"[System] {sys_msg}"})
                    
                    st.session_state.pending_action = None
                    st.session_state.active_intent = None
                    st.session_state.collected_params = {}
                    st.rerun()

if __name__ == "__main__":
    init_state()
    main()
