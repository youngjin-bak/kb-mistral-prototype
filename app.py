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
# [여기를 수정/보완하세요] 
# 새로운 지점 정보, 대출 금리 안내, 수수료 정책 등을 아래 딕셔너리에 추가합니다.
MOCK_KNOWLEDGE_BASE = {
    "Gangnam": "Gangnam branch opens 0900-1600 during the weekdays (address: 123 Teheran-ro, Gangnam-gu, Seoul).",
    "Jongro": "Jongro branch opens 0900-1630 during the weekdays (address: 45 Saejongdae-ro, Jongro-gu, Seoul).",
    "Fee": "Transaction fee for other banks is 500KRW - VIP customers are exempt from fees."
}

def retrieve_knowledge(user_message):
    """결정론적 키워드 매칭을 통한 RAG 검색 모의 함수"""
    for keyword, info in MOCK_KNOWLEDGE_BASE.items():
        if keyword in user_message:
            return info
    return "KB 국민은행 영업점은 일반적으로 평일 오전 9시부터 오후 4시까지 운영됩니다."

# ==========================================
# 4. Probabilistic AI Layer (Mistral NLU)
# ==========================================
def classify_intent(user_message):
    api_key = os.environ.get("MISTRAL_API_KEY", "")
    if not api_key: return "UNKNOWN"
        
    client = MistralClient(api_key=api_key)
    VALID_INTENTS = ["FAQ", "BALANCE", "CARD_LOCK", "TRANSFER", "UNKNOWN"]
    
    try:
        response = client.chat(
            model="mistral-small-latest",
            messages=[
                ChatMessage(
                    role="system",
                    # 추출할 파라미터의 스키마를 정의합니다.
                    content="""
                    Classify the request into one category: FAQ, BALANCE, CARD_LOCK, TRANSFER, UNKNOWN.
                    Extract relevant parameters if present.
                    Return ONLY JSON: {"intent": "...", "parameters": {"target_account": "...", "amount": "..."}}
                    """
                ),
                ChatMessage(role="user", content=user_message)
            ],
            response_format={"type": "json_object"}
        )
        result = json.loads(response.choices[0].message.content)
        intent = result.get("intent", "UNKNOWN")
        parameters = result.get("parameters", {})
        
        if intent not in VALID_INTENTS:
            return {"intent": "UNKNOWN", "parameters": {}}
        return {"intent": intent, "parameters": parameters}
    except Exception:
        return {"intent": "UNKNOWN", "parameters": {}}

# ==========================================
# 5. Deterministic Orchestrator 
# ==========================================
def handle_request(message):
    st.session_state.last_trace = [] 
    
    # 1. NLU 결과(딕셔너리) 수신
    nlu_result = classify_intent(message)
    intent = nlu_result["intent"]
    parameters = nlu_result["parameters"]
    add_trace("🤖 Mistral NLU", f"Intent: {intent}, Params: {parameters}")

    # (이전 evaluate_policy 호출 코드 유지) ...
    decision = evaluate_policy(intent) # (TRANSFER 정책도 evaluate_policy에 추가 필요)
    
    # 특정 의도에 대한 필수 파라미터 누락 검증(Validation)
    if intent == "TRANSFER":
        if not parameters.get("target_account") or not parameters.get("amount"):
            add_trace("⚠️ Validation", "Missing parameters for TRANSFER")
            return "Please input the receiving account number and amount."

    if decision == "NO_TRANSACTION":
        add_trace("🔄 Orchestrator", "Routed to Knowledge Tool")
        # 앞서 만든 검색 함수 적용
        return retrieve_knowledge(message)
        
        
    elif decision == "READ_ONLY":
        add_trace("🔄 Orchestrator", "Routed to Banking Tool (Read)")
        balance = api_get_balance()
        add_trace("🔧 Banking Tool", "Called api_get_balance()")
        return f"Your current balance is {balance:,} KRW."
        
  elif decision == "HUMAN_APPROVAL_REQUIRED":
        # Human Agent가 판단할 수 있도록 컨텍스트를 요약하여 주입합니다.
        st.session_state.pending_action = {
            "intent": intent,
            "action": "LOCK_CARD",
            "internal_card_id": "CARD001",
            "display_card": "****1234",
            "status": "PENDING",
            "human_summary": "Customer requested to lock their card.",
            "verification_rule": "Customer identity verified (Auth: True)"
        }
        add_trace("⏳ Orchestrator", "Halted workflow for Human Approval")
        return "Human approval required - please check below."
        
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
            
            # Human Agent에게 보여줄 데이터 렌더링 형태를 디자인합니다.
            st.markdown("#### 📋 Transaction Summary")
            st.write(f"**Summary:** {action.get('human_summary')}")
            st.write(f"**Verfication:** {action.get('verification_rule')}")
            st.write(f"**Target Card:** {action.get('display_card')}")
            
            
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
