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
    """Deterministic transaction function altering state"""
    clean_amt = str(amount_str).replace(",", "").replace("krw", "").strip()
    try:
        transfer_amount = int(clean_amt)
        if st.session_state.balance >= transfer_amount:
            st.session_state.balance -= transfer_amount
            return True
        return False
    except ValueError:
        return False

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
        "loan_officer": "John Doe (john@kb.com)",
        "address": "123 Teheran-ro, Gangnam-gu, Seoul"
    },
    "Jongno": {
        "hours": "9 AM to 4 PM, Mon-Fri",
        "phone": "02-987-6543",
        "address": "45 Jong-ro, Jongno-gu, Seoul"
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
def _call_mistral_json(model, system_prompt, user_message, api_key):
    url = "https://api.mistral.ai/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ],
        "response_format": {"type": "json_object"}
    }
    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            content = res_data['choices'][0]['message']['content']
            backticks = "`" * 3
            clean_content = content.replace(backticks + "json", "").replace(backticks, "").strip()
            return json.loads(clean_content)
    except Exception as e:
        print(f"Mistral API Error ({model}): {e}")
        return {}

def _call_mistral_text(model, system_prompt, user_message, api_key):
    """Helper for generating plain natural language (non-JSON) conversational responses."""
    url = "https://api.mistral.ai/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]
    }
    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            return res_data['choices'][0]['message']['content'].strip()
    except Exception as e:
        return ""

def generate_fallback(user_message):
    """Generates an empathetic acknowledgment before handing off to a human."""
    api_key = os.environ.get("MISTRAL_API_KEY", "")
    if not api_key:
        return "I apologize, but I currently do not have the information or authority to support your inquiry. Let me connect the human agent to answer it."
    
    system_prompt = """
    You are a polite, welcoming customer service agent for KB Kookmin Bank.
    Acknowledge the user's inquiry empathetically in exactly ONE short sentence. 
    Do NOT provide any factual answers or promise solutions. Just acknowledge what they asked.
    Example: "I understand you are looking for information about our international wire transfer fees."
    """
    
    prefix = _call_mistral_text("mistral-small-latest", system_prompt, user_message, api_key)
    if not prefix:
        prefix = "I understand your request."
        
    return f"{prefix} However, I currently do not have the information or authority to support your inquiry - let me connect the human agent to answer it."

def classify_intent(user_message):
    api_key = os.environ.get("MISTRAL_API_KEY", "")
    if not api_key: return {"intent": "UNKNOWN", "parameters": {}}
        
    # STAGE 1: MACRO-ROUTING (Mistral Small)
    small_prompt = """
    Classify the request into exactly one category: FAQ, BALANCE, CARD_LOCK, CARD_UNLOCK, TRANSFER, UNKNOWN.
    You MUST return ONLY a valid JSON object with EXACTLY one key: "intent".
    Example: {"intent": "TRANSFER"}
    """
    
    stage_1_result = _call_mistral_json("mistral-small-latest", small_prompt, user_message, api_key)
    intent = stage_1_result.get("intent", "UNKNOWN")
    
    VALID_INTENTS = ["FAQ", "BALANCE", "CARD_LOCK", "CARD_UNLOCK", "TRANSFER", "UNKNOWN"]
    if intent not in VALID_INTENTS:
        intent = "UNKNOWN"

    add_trace("🤖 Macro-Routing (Mistral Small)", f"Classified intent as: {intent}")

    # STAGE 2: MICRO-ROUTING & EXTRACTION (Cascading based on complexity)
    parameters = {}
    if intent == "TRANSFER":
        # Complex task: Route to SMoE (Mixtral 8x22b)
        smoe_prompt = f"""
        The user wants to execute a {intent}. 
        Extract 'target_bank', 'target_account', and 'amount'. If missing, omit the key. Do not use placeholders.
        You MUST return ONLY a valid JSON object with the key: "parameters".
        Example: {{"parameters": {{"target_bank": "Hana", "amount": "50000"}}}}
        """
        stage_2_result = _call_mistral_json("open-mixtral-8x22b", smoe_prompt, user_message, api_key)
        parameters = stage_2_result.get("parameters", {})
        
        # Format for clean UI rendering
        formatted_params = json.dumps(parameters, ensure_ascii=False)
        add_trace("🧠 Micro-Routing (SMoE: Mixtral 8x22b)", f"High-precision slot extraction: {formatted_params}")
        
    elif intent == "FAQ":
        # Simple task: Keep on Mistral Small
        faq_prompt = f"""
        The user wants a {intent}. 
        Extract 'branch' and 'attribute' (e.g., 'hours', 'phone', 'address', 'loan_officer'). 
        You MUST return ONLY a valid JSON object with the key: "parameters".
        """
        stage_2_result = _call_mistral_json("mistral-small-latest", faq_prompt, user_message, api_key)
        parameters = stage_2_result.get("parameters", {})
        
        # Format for clean UI rendering
        formatted_params = json.dumps(parameters, ensure_ascii=False)
        add_trace("🤖 Extraction (Mistral Small)", f"Simple slot extraction: {formatted_params}")

    return {"intent": intent, "parameters": parameters}
    
# ==========================================
# 5. Deterministic Orchestrator (State Machine)
# ==========================================
def handle_request(message):
    st.session_state.last_trace = [] 
    
    # Check if we are waiting for user input to fill a specific slot (Auth or Missing Params)
    pending_slot = st.session_state.awaiting_input_for
    if pending_slot == "auth":
        if message.strip().lower() == st.session_state.auth_target_name.lower():
            st.session_state.authenticated = True
            st.session_state.awaiting_input_for = None
            add_trace("🔐 Auth Engine", "Identity verified successfully.")
            return process_active_intent(message)
        else:
            add_trace("🔐 Auth Engine", "Identity verification failed.")
            return "Name does not match our records. Please enter your full name to verify your identity."
            
    elif pending_slot:
        st.session_state.collected_params[pending_slot] = message
        st.session_state.awaiting_input_for = None
        add_trace("⚠️ Validation", f"User provided missing slot: {pending_slot}")
        return process_active_intent(message)

    # If no pending slot, classify the new intent
    nlu_result = classify_intent(message)
    intent = nlu_result["intent"]
    
    if intent != "UNKNOWN":
        st.session_state.active_intent = intent
        st.session_state.collected_params = nlu_result["parameters"]
    else:
        add_trace("🤖 Mistral NLU", "Intent UNKNOWN. Generating empathetic fallback.")
        st.session_state.pending_action = {
            "intent": "UNKNOWN_HANDOFF",
            "status": "PENDING"
        }
        return generate_fallback(message)

    return process_active_intent(message)

def process_active_intent(message=None):
    intent = st.session_state.active_intent
    params = st.session_state.collected_params

    decision = evaluate_policy(intent)
    add_trace("⚖️ Policy Engine", f"Decision: {decision}")

    if decision == "AUTH_REQUIRED":
        st.session_state.awaiting_input_for = "auth"
        add_trace("🔐 Auth Engine", "Halted workflow. Requesting Identity Verification.")
        return "For your security, please verify your identity by entering your full name."

    def is_invalid_param(val, param_type="text"):
        if not val: return True
        val_str = str(val).strip().lower()
        if val_str in ["unknown", "n/a", "none", "null", ""]: return True
        
        if param_type == "account":
            clean_account = val_str.replace("-", "").replace(" ", "")
            if not clean_account.isdigit(): return True
            
        if param_type == "amount":
            clean_amt = val_str.replace(",", "").replace("krw", "").strip()
            if not clean_amt.isdigit(): return True
            
        return False

    if intent == "TRANSFER":
        if is_invalid_param(params.get("target_bank"), "text"):
            st.session_state.awaiting_input_for = "target_bank"
            add_trace("⚠️ Validation", "Missing or invalid target_bank.")
            return "Please enter the name of the receiving bank."
            
        if is_invalid_param(params.get("target_account"), "account"):
            st.session_state.awaiting_input_for = "target_account"
            add_trace("⚠️ Validation", "Missing or invalid target_account.")
            return "Please enter a valid target account number (must contain numbers only)."
            
        if is_invalid_param(params.get("amount"), "amount"):
            st.session_state.awaiting_input_for = "amount"
            add_trace("⚠️ Validation", "Missing or invalid amount.")
            return "Please enter the amount you wish to transfer (numbers only)."

    if decision == "NO_TRANSACTION":
        add_trace("🔄 Orchestrator", "Routed to Knowledge Tool")
        branch = params.get("branch", "")
        attribute = params.get("attribute", "")
        retrieved_info = retrieve_knowledge(branch, attribute)
        
        if retrieved_info:
            return f"The {attribute} for the {branch} branch is: {retrieved_info}"
            
        st.session_state.pending_action = {
            "intent": "FAQ_MISSING_DATA",
            "branch": branch,
            "attribute": attribute,
            "status": "PENDING"
        }
        
        if message:
            add_trace("🤖 Mistral NLU", "Data missing. Generating empathetic fallback.")
            return generate_fallback(message)
            
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
            return True, "Card locked successfully."
            
    elif action["action"] == "UNLOCK_CARD":
        if api_unlock_card(action["internal_id"]):
            add_trace("⚙️ Banking API", "Executed api_unlock_card()")
            return True, "Card unlocked successfully."
            
    elif action["action"] == "TRANSFER":
        success = api_transfer(action["internal_id"], action["amount"])
        if success:
            add_trace("⚙️ Banking API", f"Executed api_transfer to {action['internal_id']}")
            return True, "Transfer executed successfully."
        else:
            add_trace("⚙️ Banking API", "Transfer failed: Insufficient balance.")
            return False, "Transfer failed due to insufficient balance."
            
    return False, "Unknown action."

# ==========================================
# 6. Presentation Layer (Streamlit UI & Theming)
# ==========================================
def inject_custom_css():
    st.markdown("""
    <style>
    .custom-header {
        display: flex;
        align-items: center;
        gap: 15px;
        padding-bottom: 20px;
        border-bottom: 2px solid #E5E5E5;
        margin-bottom: 20px;
    }
    .custom-header h1 {
        margin: 0;
        font-size: 24px;
        color: #171717;
        font-weight: 700;
    }
    .stButton>button {
        background-color: #F97316 !important;
        color: white !important;
        border: none !important;
        border-radius: 6px !important;
        font-weight: 600 !important;
    }
    .stButton>button:hover {
        background-color: #EA5A0C !important;
    }
    </style>
    """, unsafe_allow_html=True)

def main():
    st.set_page_config(layout="wide", page_title="KB x Mistral Prototype")
    inject_custom_css()
    
    st.markdown('''
    <div class="custom-header">
        <span style="color: #FFCC00; font-size: 28px; font-weight: 900; letter-spacing: -1px;">KB Kookmin Bank</span>
        <h1>AI Assistant Prototype <span style="color:#F97316; font-size:16px;">Powered by Mistral</span></h1>
    </div>
    ''', unsafe_allow_html=True)
    
    col_chat, col_trace = st.columns([1, 1])

    with col_chat:
        st.subheader("Customer Chat")
        
        chat_container = st.container(height=400)
        with chat_container:
            for msg in st.session_state.chat_history:
                # Assistant 메시지일 경우 제공된 Mistral 로고 적용
                avatar_img = "Mistral-Icon-Gradient-RGB.png" if msg["role"] == "assistant" else None
                st.chat_message(msg["role"], avatar=avatar_img).write(msg["content"])

        user_input = st.chat_input("Enter request here...")
        if user_input:
            st.session_state.chat_history.append({"role": "user", "content": user_input})
            response = handle_request(user_input)
            st.session_state.chat_history.append({"role": "assistant", "content": response})
            st.rerun()

    with col_trace:
        st.subheader("Status")
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
            
            if action.get("intent") in ["FAQ_MISSING_DATA", "UNKNOWN_HANDOFF"]:
                st.warning("⚠️ Operator Input Required")
                if action.get("intent") == "FAQ_MISSING_DATA":
                    st.write(f"**Requested Branch:** {action.get('branch')}")
                    st.write(f"**Requested Attribute:** {action.get('attribute')}")
                else:
                    st.write("**Reason:** Unrecognized Intent / Out of Scope")
                
                operator_response = st.text_input("Enter the answer to send:", key="op_fallback_input")
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
                
                operator_note = st.text_input("Operator Note (Optional):", key="op_note_input")
                
                btn_col1, btn_col2 = st.columns(2)
                if btn_col1.button("✅ Approve"):
                    add_trace("👤 Human Approval", "APPROVED")
                    success, msg = execute_pending_action() 
                    
                    sys_msg = f"Transaction approved. {msg}"
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
                    st.session_state.chat_history.append({"role": "assistant", "content": f"[System] {sys_msg}"})
                    
                    st.session_state.pending_action = None
                    st.session_state.active_intent = None
                    st.session_state.collected_params = {}
                    st.rerun()

if __name__ == "__main__":
    init_state()
    main()
