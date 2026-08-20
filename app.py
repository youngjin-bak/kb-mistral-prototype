import streamlit as st
import json
import os
import urllib.request

# ==========================================
# 1. Mock State & Authentication Setup
# ==========================================
def init_state():
    # Authentication & Session States added
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
    # Enforce Authentication Boundary
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
                If FAQ, extract 'branch' and 'attribute' (e.g., hours, phone, loan_officer).
                If TRANSFER, extract 'target_account' and 'amount'.
                Return ONLY valid JSON.
                Example: {"intent": "CARD_UNLOCK", "parameters": {}}
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
            result = json.loads(content)
            
            intent = result.get("intent", "UNKNOWN")
            parameters = result.get("parameters", {})
            return {"intent": intent, "parameters": parameters}
    except Exception:
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

    # 2. State Interception for Slot Filling (Missing Parameters)
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

    # 1. Evaluate Policy (Checks Auth implicitly)
    decision = evaluate_policy(intent)
    add_trace("⚖️ Policy Engine", f"Decision: {decision}")

    if decision == "AUTH_REQUIRED":
        st.session_state.awaiting_input_for = "auth"
        add_trace("🔐 Auth Engine", "Halted workflow. Requesting Identity Verification.")
        return "For your security, please verify your identity by entering your full name."

    # 2. Validate Required Parameters
    if intent == "TRANSFER":
        if not params.get("target_account"):
            st.session_state.awaiting_input_for = "target_account"
            add_trace("⚠️ Validation Engine", "Missing target_account. Prompting user.")
            return "Please enter the target account number."
        if not params.get("amount"):
            st.session_state.awaiting_input_for = "amount"
            add_trace("⚠️ Validation Engine", "Missing amount. Prompting user.")
            return "Please enter the amount you wish to transfer."

    # 3. Execute Validated Intent
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
        
        st.session_state.pending_action = {
            "intent": intent,
            "action": action_map.get(intent),
            "internal_id": "CARD001" if "CARD" in intent else params.get("target_account"),
            "display_target": "****1234" if "CARD" in intent else params.get("target_account"),
            "status": "PENDING",
            "human_summary": f"Customer requested a {intent} transaction.",
            "verification_rule": f"Identity verified: {st.session_state.authenticated}",
            "amount": params.get("amount", "N/A")
        }
        add_trace("⏳ Orchestrator", "Halted workflow for Human Approval")
        return "Final approval from an authorized agent is required. Please review the details."

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
        
        for msg in st.session_state.chat_history:
            st.chat_message(msg["role"]).write(msg["content"])

        user_input = st.chat_input("Enter request here...")
        if user_input:
            st.chat_message("user").write(user_input)
            st.session_state.chat_history.append({"role": "user", "content": user_input})
            
            response = handle_request(user_input)
            
            st.chat_message("assistant").write(response)
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
                
                btn_col1, btn_col2 = st.columns(2)
                if btn_col1.button("✅ Approve"):
                    add_trace("👤 Human Approval", "APPROVED")
                    execute_pending_action() 
                    st.session_state.pending_action["status"] = "EXECUTED"
                    st.session_state.active_intent = None
                    st.session_state.collected_params = {}
                    st.success("Transaction Complete.")
                    st.rerun()
                    
                if btn_col2.button("❌ Reject"):
                    st.session_state.pending_action = None
                    st.session_state.active_intent = None
                    st.session_state.collected_params = {}
                    st.error("Transaction cancelled.")
                    st.rerun()

if __name__ == "__main__":
    init_state()
    main()
