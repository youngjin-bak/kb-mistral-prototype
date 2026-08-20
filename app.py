import streamlit as st
import json
import os
import urllib.request

# ==========================================
# 1. Mock State & Authentication Setup
# ==========================================
def init_state():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = True
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

# ==========================================
# 3. Governance Layer (Policy Engine & Knowledge Base)
# ==========================================
def evaluate_policy(intent):
    if not st.session_state.authenticated:
        return "DENY"

    policies = {
        "FAQ": "NO_TRANSACTION",
        "BALANCE": "READ_ONLY",
        "CARD_LOCK": "HUMAN_APPROVAL_REQUIRED",
        "TRANSFER": "HUMAN_APPROVAL_REQUIRED"
    }
    return policies.get(intent, "DENY")

# Nested Dictionary for multi-dimensional retrieval
MOCK_KNOWLEDGE_BASE = {
    "Gangnam": {
        "hours": "9 AM to 4 PM, Mon-Fri",
        "phone": "02-123-4567",
        "loan_officer": "John Doe (john@kb.com)"
    },
    "Jongno": {
        "hours": "9 AM to 4 PM, Mon-Fri",
        "phone": "02-987-6543"
        # loan_officer is intentionally missing for Operator Input test
    }
}

def retrieve_knowledge(branch, attribute):
    """Retrieves specific attributes. Returns None if data is missing."""
    if not branch or not attribute:
        return None
    
    # Simple capitalization normalization (e.g., 'gangnam' -> 'Gangnam')
    branch = branch.capitalize()
    
    branch_data = MOCK_KNOWLEDGE_BASE.get(branch)
    if not branch_data:
        return None
        
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
                Classify the request into one category: FAQ, BALANCE, CARD_LOCK, TRANSFER, UNKNOWN.
                If FAQ, extract 'branch' (e.g., Gangnam, Jongno) and 'attribute' (e.g., hours, phone, loan_officer).
                If TRANSFER, extract 'target_account' and 'amount'.
                Return ONLY valid JSON.
                Example: {"intent": "FAQ", "parameters": {"branch": "Gangnam", "attribute": "phone"}}
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
            
            VALID_INTENTS = ["FAQ", "BALANCE", "CARD_LOCK", "TRANSFER", "UNKNOWN"]
            if intent not in VALID_INTENTS:
                return {"intent": "UNKNOWN", "parameters": {}}
            return {"intent": intent, "parameters": parameters}
    except Exception as e:
        print(f"API Error: {e}")
        return {"intent": "UNKNOWN", "parameters": {}}

# ==========================================
# 5. Deterministic Orchestrator
# ==========================================
def handle_request(message):
    st.session_state.last_trace = [] 
    
    nlu_result = classify_intent(message)
    intent = nlu_result["intent"]
    parameters = nlu_result["parameters"]
    add_trace("🤖 Mistral NLU", f"Intent: {intent}, Params: {parameters}")

    decision = evaluate_policy(intent)
    add_trace("⚖️ Policy Engine", f"Decision: {decision}")

    if intent == "TRANSFER":
        if not parameters.get("target_account") or not parameters.get("amount"):
            add_trace("⚠️ Validation", "Missing parameters for TRANSFER")
            return "To proceed with the transfer, please provide both the target account number and the amount."

    if decision == "NO_TRANSACTION":
        add_trace("🔄 Orchestrator", "Routed to Knowledge Tool")
        
        branch = parameters.get("branch", "")
        attribute = parameters.get("attribute", "")
        retrieved_info = retrieve_knowledge(branch, attribute)
        
        if retrieved_info:
            add_trace("📚 Knowledge Tool", f"Found {attribute} for {branch}")
            return f"The {attribute} for {branch} branch is: {retrieved_info}"
        
        # Missing Data Logic -> Route to Human Operator
        st.session_state.pending_action = {
            "intent": "FAQ_MISSING_DATA",
            "branch": branch,
            "attribute": attribute,
            "status": "PENDING"
        }
        add_trace("⚠️ Orchestrator", f"Missing data for {branch} - {attribute}. Halted for Operator Input.")
        return "I don't have that specific information in my database. Transferring to a human operator to provide the correct answer."
        
    elif decision == "READ_ONLY":
        add_trace("🔄 Orchestrator", "Routed to Banking Tool (Read)")
        balance = api_get_balance()
        add_trace("🔧 Banking Tool", "Called api_get_balance()")
        return f"Your current balance is {balance:,} KRW."
        
    elif decision == "HUMAN_APPROVAL_REQUIRED":
        st.session_state.pending_action = {
            "intent": intent,
            "action": "LOCK_CARD" if intent == "CARD_LOCK" else "TRANSFER",
            "internal_id": "CARD001" if intent == "CARD_LOCK" else parameters.get("target_account"),
            "display_target": "****1234" if intent == "CARD_LOCK" else parameters.get("target_account"),
            "status": "PENDING",
            "human_summary": f"Customer requested a {intent} transaction.",
            "verification_rule": "Device ownership verified (Auth: True)",
            "amount": parameters.get("amount", "N/A")
        }
        add_trace("⏳ Orchestrator", "Halted workflow for Human Approval")
        return "Final approval from an authorized agent is required for security. Please review the details on the right."
        
    add_trace("🚫 Security", "Blocked by Default Deny")
    return "Request denied due to security policies."

def execute_pending_action():
    action = st.session_state.pending_action
    if action["action"] == "LOCK_CARD":
        result = api_lock_card(action["internal_id"])
        if result:
            add_trace("⚙️ Banking API", f"Executed api_lock_card() -> {st.session_state.card_status}")
            return True
    elif action["action"] == "TRANSFER":
        add_trace("⚙️ Banking API", f"Executed api_transfer({action['internal_id']}, {action['amount']})")
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
        st.caption("Try: 'Who is the loan officer at Jongno branch?' (Triggers Operator Input)")
        
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
        st.write(f"**Balance:** {st.session_state.balance:,} KRW | **Card Status:** {st.session_state.card_status}")
        st.divider()
        
        st.subheader("Execution Trace")
        if st.session_state.last_trace:
            for step in st.session_state.last_trace:
                st.info(f"**{step['component']}** ➔ {step['detail']}")

        if st.session_state.pending_action and st.session_state.pending_action["status"] == "PENDING":
            action = st.session_state.pending_action
            
            # 1. Operator Input UI (Missing Knowledge)
            if action.get("intent") == "FAQ_MISSING_DATA":
                st.warning("⚠️ Operator Input Required (Missing Knowledge)")
                st.write(f"**Requested Branch:** {action.get('branch')}")
                st.write(f"**Requested Attribute:** {action.get('attribute')}")
                
                operator_response = st.text_input("Enter the answer to send to the customer:")
                if st.button("📤 Send to Customer"):
                    if operator_response:
                        add_trace("👤 Operator", "Provided manual response")
                        st.session_state.chat_history.append({"role": "assistant", "content": f"[Operator] {operator_response}"})
                        st.session_state.pending_action = None
                        st.rerun()
            
            # 2. Human Approval UI (Transaction)
            else:
                st.warning("⚠️ Human Approval Required")
                st.markdown("#### 📋 Transaction Summary")
                st.write(f"**Summary:** {action.get('human_summary')}")
                st.write(f"**Security Check:** {action.get('verification_rule')}")
                st.write(f"**Target Identifier:** {action.get('display_target')}")
                if action.get("amount") != "N/A":
                    st.write(f"**Amount:** {action.get('amount')}")
                
                btn_col1, btn_col2 = st.columns(2)
                if btn_col1.button("✅ Approve Transaction"):
                    add_trace("👤 Human Approval", "APPROVED")
                    execute_pending_action() 
                    st.session_state.pending_action["status"] = "EXECUTED"
                    st.success("Transaction Complete.")
                    st.rerun()
                    
                if btn_col2.button("❌ Reject"):
                    st.session_state.pending_action = None
                    st.error("Transaction cancelled.")
                    st.rerun()

if __name__ == "__main__":
    init_state()
    main()
