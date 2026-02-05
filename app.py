import streamlit as st
import fitz
import re
import json
import hashlib
from datetime import datetime
from io import BytesIO
from docx import Document
import spacy
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import letter

pdfmetrics.registerFont(UnicodeCIDFont('HeiseiMin-W3'))
# ---------------- CONFIG ----------------
st.set_page_config(
    page_title="ContractAI – Legal Assistant",
    page_icon="⚖️",
    layout="wide"
)

@st.cache_resource
def load_nlp():
    return spacy.load("en_core_web_sm")

nlp = load_nlp()

# ---------------- UI ----------------
st.title("⚖️ ContractAI – GenAI Legal Assistant")
st.caption("Plain-English Contract Risk Analysis for Indian SMEs")

uploaded_file = st.sidebar.file_uploader(
    "📎 Upload Contract (PDF / DOCX / TXT)",
    type=["pdf", "docx", "txt"]
)

# ---------------- HINDI NORMALIZATION ----------------
def normalize_hindi(text):
    hindi_map = {
        "समझौता": "agreement",
        "कर्मचारी": "employee", 
        "नियोक्ता": "employer",
        "वेतन": "salary",
        "समाप्ति": "termination",
        "भुगतान": "payment",
        "कानून": "law",
        "न्यायालय": "court",
        "गोपनीय": "confidential",
        "क्षतिपूर्ति": "indemnity",
        "प्रतिस्पर्धा": "non compete",
    }
    for hi, en in hindi_map.items():
        text = text.replace(hi, en)
    return text

# ---------------- TEXT EXTRACTION ----------------
def extract_text(file_obj, name):
    if name.endswith(".pdf"):
        pdf = fitz.open(stream=file_obj)
        return " ".join(page.get_text() for page in pdf)
    elif name.endswith(".docx"):
        doc = Document(file_obj)
        return "\n".join(p.text for p in doc.paragraphs)
    return file_obj.getvalue().decode("utf-8")

# ---------------- UNIVERSAL PARTIES EXTRACTION ----------------
def extract_parties(text):
    parties = {}

    landlord = re.search(r"Landlord[:\s]+([A-Z][a-zA-Z\s&.,]+?)(?=\n|AND|$)", text, re.I)
    tenant = re.search(r"Tenant[:\s]+([A-Z][a-zA-Z\s&.,]+?)(?=\n|$)", text, re.I)
    
    if landlord:
        parties["Landlord"] = landlord.group(1).strip()
    if tenant:
        parties["Tenant"] = tenant.group(1).strip()
    
    # Fallback: BETWEEN pattern
    if not parties:
        between_match = re.search(r"BETWEEN\s+(.+?)(?:AND|\n{2,})", text, re.I | re.DOTALL)
        if between_match:
            party1 = between_match.group(1).strip()
            and_match = re.search(r"AND\s+(.+?)(?=\n{2,}|\()", text, re.I | re.DOTALL)
            if and_match:
                party2 = and_match.group(1).strip().split(':')[0].strip()
                parties["Party 1"] = party1
                parties["Party 2"] = party2
    
    return parties if parties else {"Party 1": "Detected", "Party 2": "Detected"}


# ---------------- UNIVERSAL AMOUNTS EXTRACTION ----------------
def extract_amounts(text):
    """Catches ALL Indian currency formats - CLEAN output only"""
    patterns = [
        r"(?:INR|₹|Rs\.?)\s*[\d,]+(?:\.\d+)?",  # INR 6,00,000, ₹50,000, Rs. 1,50,000
        r"\d{1,3}(?:,\d{3})+(?:\.\d+)?\s*(?:Lakhs?|Crores?)",  # 1,00,000 Lakhs
        r"(?:salary|rent|payment|amount|deposit)\s+of\s+(?:INR|₹|Rs\.?)?[\d,]+"
    ]
    
    all_amounts = []
    for pattern in patterns:
        all_amounts.extend(re.findall(pattern, text, re.I))
    clean_amounts = []
    for amt in all_amounts:
        amt = amt.strip()
        if len(amt) > 4 and re.search(r'[\d,]{3,}', amt):
            clean_amounts.append(amt)
    
    return list(set(clean_amounts))


# ---------------- UNIVERSAL JURISDICTION ----------------
def extract_jurisdiction(text):
    jurisdiction = {}
    
    # Governing Law
    law_patterns = [
        r"governed by the laws? of\s+([A-Za-z\s]+?)(?=\,|;|$)",
        r"laws? of\s+([A-Za-z\s]+?)(?=governing|$)"
    ]
    for pattern in law_patterns:
        match = re.search(pattern, text, re.I)
        if match:
            jurisdiction["Governing Law"] = match.group(1).strip()
            break
    
    # Jurisdiction
    court_patterns = [
        r"courts?\s+(?:at|in|of)\s+([A-Za-z\s]+?)(?:\s+shall|$)",
        r"exclusive jurisdiction.*?([A-Za-z\s]+)",
        r"([A-Za-z\s]+?)\s+courts?\s+(?:shall|have)"
    ]
    for pattern in court_patterns:
        match = re.search(pattern, text, re.I)
        if match:
            jurisdiction["Jurisdiction"] = match.group(1).strip()
            break
    
    return jurisdiction

# ---------------- CONTRACT TYPE ----------------
def classify_contract(text):
    t = text.lower()
    if any(word in t for word in ["employee", "salary", "employment"]):
        return "EMPLOYMENT"
    if any(word in t for word in ["lease", "rent", "tenant", "landlord"]):
        return "LEASE"
    if any(word in t for word in ["partner", "partnership"]):
        return "PARTNERSHIP"
    if any(word in t for word in ["service", "vendor"]):
        return "SERVICE"
    return "GENERAL"

# ---------------- CLAUSE EXTRACTION ----------------
def extract_clauses(text):
    clauses = re.split(r'\n\d+\.|Clause\s+\d+|Section\s+\d+', text)
    return [c.strip() for c in clauses if len(c.strip()) > 25]

# ---------------- RISK RULES ----------------
RISK_RULES = {
    "terminate immediate": ("HIGH", "Employer can terminate without notice"),
    "without notice": ("HIGH", "No notice or severance protection"),
    "non compete": ("HIGH", "Restricts future employment"),
    "two years": ("HIGH", "Excessive non-compete duration"),
    "perpetual": ("HIGH", "Unlimited lifelong obligation"),
    "confidentiality": ("MEDIUM", "Long-term confidentiality obligation"),
    "indemnity": ("HIGH", "Unlimited financial liability"),
    "arbitration": ("MEDIUM", "Dispute resolution outside courts")
}

# ---------------- CLAUSE ANALYSIS ----------------
def analyze_clause(clause):
    text = clause.lower()
    levels = []
    reasons = []
    
    for term, (level, reason) in RISK_RULES.items():
        if term in text:
            levels.append(level)
            reasons.append(reason)
    
    if "HIGH" in levels:
        risk = "HIGH"
    elif "MEDIUM" in levels:
        risk = "MEDIUM"
    else:
        risk = "LOW"
    
    explanation = (
        "This clause significantly disadvantages one party and may lead to legal/financial harm."
        if risk == "HIGH"
        else "This clause creates some imbalance or future uncertainty."
        if risk == "MEDIUM"
        else "This clause is generally standard and low risk."
    )
    
    suggestion = None
    if risk == "HIGH" and any(term in text for term in ["terminate", "termination"]):
        suggestion = "Add 30-day written notice or salary in lieu of notice."
    elif risk == "HIGH" and "non compete" in text:
        suggestion = "Limit to 6 months and specific competitors only."
    elif risk == "HIGH" and "perpetual" in text:
        suggestion = "Restrict to 2-3 years post-termination."

    
    return {
        "text": clause[:300],
        "risk": risk,
        "reasons": reasons,
        "explanation": explanation,
        "suggestion": suggestion
    }

# ---------------- CONTRACT RISK ----------------
def contract_risk(analysed):
    # If even ONE clause is HIGH → overall HIGH
    if any(c["risk"] == "HIGH" for c in analysed):
        return "HIGH"

    # If at least ONE clause is MEDIUM → overall MEDIUM
    if any(c["risk"] == "MEDIUM" for c in analysed):
        return "MEDIUM"

    return "LOW"

# ---------------- PDF REPORT ----------------
def generate_pdf(data):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)

    styles = getSampleStyleSheet()
    for style in styles.byName.values():
        style.fontName = 'HeiseiMin-W3'
    story = []
    
    story.append(Paragraph("ContractAI – Detailed Legal Analysis Report", styles["Title"]))
    story.append(Spacer(1, 12))
    
    story.append(Paragraph(f"<b>Contract Type:</b> {data['type']}", styles["Normal"]))
    story.append(Paragraph(f"<b>Overall Risk:</b> {data['risk']}", styles["Normal"]))
    story.append(Spacer(1, 12))
    
    story.append(Paragraph("<b>Identified Parties</b>", styles["Heading2"]))
    for role, name in data["parties"].items():
        story.append(Paragraph(f"{role}: {name}", styles["Normal"]))
    
    story.append(Spacer(1, 12))
    story.append(Paragraph("<b>Key Findings</b>", styles["Heading2"]))
    story.append(Paragraph(f"Amounts found: {', '.join(data.get('amounts', []))}", styles["Normal"]))
    story.append(Paragraph(f"Jurisdiction: {data.get('jurisdiction', 'Not specified')}", styles["Normal"]))
    
    story.append(Spacer(1, 12))
    story.append(Paragraph("<b>Clause Analysis</b>", styles["Heading2"]))
    for i, c in enumerate(data["clauses"], 1):
        story.append(Spacer(1, 8))
        story.append(Paragraph(f"<b>Clause {i} – Risk: {c['risk']}</b>", styles["Normal"]))
        story.append(Paragraph(c["text"], styles["Normal"]))
        story.append(Paragraph(f"Explanation: {c['explanation']}", styles["Normal"]))
        if c["suggestion"]:
            story.append(Paragraph(f"Suggested Change: {c['suggestion']}", styles["Normal"]))
    
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

# ---------------- MAIN EXECUTION ----------------
if uploaded_file is not None:
    with st.spinner("🔍 Analyzing contract..."):
        file_content = uploaded_file.read()
        text = extract_text(BytesIO(file_content), uploaded_file.name)
        
        # Hindi normalization
        if re.search(r'[\u0900-\u097F]', text):
            text = normalize_hindi(text)
        
        # Analysis
        parties = extract_parties(text)
        amounts = extract_amounts(text)
        jurisdiction = extract_jurisdiction(text)
        clauses = extract_clauses(text)
        analysed = [analyze_clause(c) for c in clauses[:10]]
        overall_risk = contract_risk(analysed)
        ctype = classify_contract(text)
    
    # Results Tabs
    tab1, tab2, tab3 = st.tabs(["📘 Summary", "⚠️ Clause Analysis", "📄 PDF Export"])
    
    with tab1:
        col1, col2 = st.columns(2)
        col1.metric("Contract Type", ctype)
        col2.metric("Overall Risk", overall_risk)
        
        st.subheader("👥 Parties")
        st.json(parties)
        
        st.subheader("💰 Amounts")
        clean_display = [a for a in amounts if len(a) > 4]
        st.success(f"Found {len(clean_display)} amounts: {', '.join(clean_display)}")

        
        st.subheader("⚖️ Jurisdiction")
        st.json(jurisdiction)
    
    with tab2:
        st.subheader("Detailed Clause Analysis")
        for i, c in enumerate(analysed, 1):
            with st.expander(f"Clause {i} | Risk: {c['risk']} ({len(c['reasons'])} issues)"):
                st.write(c["text"])
                st.info(c["explanation"])
                if c["reasons"]:
                    st.warning(f"Risk factors: {', '.join(c['reasons'])}")
                if c["suggestion"]:
                    st.success(f"💡 Fix: {c['suggestion']}")
    
    with tab3:
        pdf = generate_pdf({
            "type": ctype,
            "risk": overall_risk,
            "parties": parties,
            "amounts": amounts,
            "jurisdiction": str(jurisdiction),
            "clauses": analysed
        })
        st.download_button(
            "📥 Download Detailed PDF Report",
            pdf,
            "contract_analysis.pdf",
            "application/pdf"
        )
        
        st.info("✅ Professional PDF ready for lawyer consultation!")
    
    # Audit Log
    audit = {
        "hash": hashlib.sha256(text.encode()).hexdigest(),
        "time": datetime.now().isoformat(),
        "type": ctype,
        "risk": overall_risk,
        "parties": parties
    }
    with open("audit_log.json", "a") as f:
        f.write(json.dumps(audit) + "\n")

else:
    st.info("👆 Upload a contract in the sidebar to begin analysis!")
    st.balloons()

# Footer
st.markdown("---")
st.caption("GenAI Legal Assistant")
