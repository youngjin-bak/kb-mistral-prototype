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
# 3. Governance Layer (Policy Engine)
# ==========================================
def evaluate_policy(intent):
    if not st.session_state.authenticated:
        return "DENY"

    policies = {
        "FAQ": "NO_TRANSACTION",
        "BALANCE": "READ_ONLY",
        "CARD_LOCK": "HUMAN_APPROVAL_REQUIRED"
    }
    return policies.get(intent, "DENY")

MOCK_KB = {
    "FAQ": "KB branches are generally open from 9 AM to 4 PM, Monday to Friday."
}

# ==========================================
# 4. Probabilistic AI Layer (Mistral REST API Direct)
# ==========================================
def classify_intent(user_message):
    api_key = os.environ.get("MISTRAL_API_KEY", "")
    if not api_key:
        return "UNKNOWN"
        
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
                "content": "Classify the request into exactly one category: FAQ, BALANCE, CARD_LOCK, UNKNOWN. Return ONLY valid JSON format: {\"intent\": \"...\"}"
            },
            {
                "role": "user",
                "content": user_message
            }
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
            
            VALID_INTENTS = ["FAQ", "BALANCE", "CARD_LOCK", "UNKNOWN"]
            if intent not in VALID_INTENTS:
                return "UNKNOWN"
            return intent
    except Exception as e:
        print(f"API Error: {e}")
        return "UNKNOWN"

# ==========================================
# 5. Deterministic Orchestrator
# ==========================================
def handle_request(message):
    st.session_state.last_trace = [] 
    
    intent = classify_intent(message)
    add_trace("🤖 Mistral NLU", f"Intent: {intent}")

    decision = evaluate_policy(intent)
    add_trace("⚖️ Policy Engine", f"Decision: {decision}")

    if decision == "NO_TRANSACTION":
        add_trace("🔄 Orchestrator", "Routed to Knowledge Tool")
        return MOCK_KB["FAQ"]
        
    elif decision == "READ_ONLY":
        add_trace("🔄 Orchestrator", "Routed to Banking Tool (Read)")
        balance = api_get_balance()
        add_trace("🔧 Banking Tool", "Called api_get_balance()")
        return f"Your current balance is {balance:,} KRW."
        
    elif decision == "HUMAN_APPROVAL_REQUIRED":
        st.session_state.pending_action = {
            "intent": intent,
            "action": "LOCK_CARD",
            "internal_card_id": "CARD001",
            "display_card": "****1234",
            "status": "PENDING"
        }
        add_trace("⏳ Orchestrator", "Halted workflow for Human Approval")
        return "Please review and approve the transaction below."
        
    add_trace("🚫 Security", "Blocked by Default Deny")
    return "Request denied due to security policies."

def execute_pending_action():
    action = st.session_state.pending_action
    
    if action["action"] == "LOCK_CARD":
        result = api_lock_card(action["internal_card_id"])
        if result:
            add_trace("⚙️ Banking API", f"Executed api_lock_card() -> {st.session_state.card_status}")
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
        st.caption("Supported Demo Queries: 'Branch hours', 'Account balance', 'Lock my card'")
        
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
            st.warning("⚠️ Human Approval Required")
            action = st.session_state.pending_action
            st.write(f"- **Action:** {action['action']}")
            st.write(f"- **Target Card:** {action['display_card']}")
            
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
