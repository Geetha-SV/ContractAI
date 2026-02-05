# ContractAI
## Overview
ContractAI is a GenAI-powered legal assistant built to help Indian small and medium business owners understand complex contracts, identify legal risks, and receive actionable advice in simple business language.

The system analyzes contracts locally without using external legal databases, ensuring confidentiality and privacy.

## Problem Statement
SMEs often sign contracts without fully understanding hidden risks, unfavorable clauses, or long-term obligations. ContractAI bridges this gap by automatically analyzing contracts, explaining clauses clearly, and highlighting potential legal and financial risks.

## Key Features
- Contract type classification (Employment, Service, Lease, Partnership, Vendor)
- Clause-by-clause analysis with risk scoring (Low / Medium / High)
- Identification of unfavorable clauses:
  - Non-compete clauses
  - Indemnity clauses
  - Unilateral termination
  - Confidentiality obligations
- Plain-language explanations for non-legal users
- Suggested renegotiation improvements
- Overall contract risk score
- Multilingual support (English & Hindi)
- Professional PDF report generation
- Local audit trail for compliance and review

## Supported File Formats
- PDF (text-based)
- DOC / DOCX
- TXT

## Multilingual Support
- Supports both English and Hindi contracts
- Hindi text is internally normalized for analysis
- Output explanations are provided in simple business English
- Hindi content is fully supported in generated PDFs

## Technology Stack
- UI: Streamlit
- NLP: Python, spaCy, Regex-based extraction
- PDF Generation: ReportLab (Unicode support)
- Storage: Local JSON-based audit logs
- LLM: Conceptual use of GPT-4 / Claude for legal reasoning

## Project Structure
app.py # Main Streamlit application
requirements.txt # Python dependencies
README.md # Project documentation

## How to Run Locally
pip install -r req.txt
streamlit run app.py


## Screenshots
<img width="1353" height="619" alt="Image" src="https://github.com/user-attachments/assets/9d595dfc-06a7-4149-ae33-100b10f4e023" />

### Contract Upload & Summary
<img width="1352" height="638" alt="Image" src="https://github.com/user-attachments/assets/dab6bf3e-ab2c-452e-bbe9-84e4e97611dd" />
### Clause-by-Clause Risk Analysis
<img width="1355" height="630" alt="Image" src="https://github.com/user-attachments/assets/4b3d4046-25ca-4d53-9d7e-90f9cbc3ecc1" />

