VALIDATOR_PROMPT = """You are a document classifier. Decide if the text below is a Terms and Conditions,
Privacy Policy, End User License Agreement, or similar legal agreement.

Respond with exactly one word: YES or NO.

Text (first 1000 chars):
{sample}
"""

CHUNK_ANALYSIS_PROMPT = """You are a legal plain-language expert. Analyze the following excerpt from a
Terms and Conditions document and extract clauses into four categories.

For each clause you find, output a JSON object with ALL of the following fields:

CLASSIFICATION FIELDS:
  - "category": one of "rights_given_up" | "obligations" | "benefits" | "unusual"
  - "summary": one plain-English sentence describing the clause
  - "risk": "red" (high impact on user) | "yellow" (moderate) | "green" (user-friendly)
  - "unusual": true if this clause is non-standard or surprising, false otherwise
  - "citation": the verbatim excerpt (max 200 chars) from the text that supports this clause
  - "data_topic": the single best-matching topic tag, or null if none apply.

      Data & privacy topics:
      "collection"    — what personal data is collected about the user
      "processing"    — how data is used or analysed internally
      "sharing"       — data shared with third parties or partners
      "retention"     — how long data is kept or when it is deleted
      "transfers"     — data moved across borders or jurisdictions
      "third_party"   — involvement of external companies or services

      Legal & commercial topics:
      "liability"     — limits on the company's liability or disclaimers of warranties
      "arbitration"   — mandatory arbitration, dispute resolution, class action waivers
      "security"      — data security obligations, breach notification, encryption
      "ai_training"   — use of user content or data to train AI or machine learning models
      "monetization"  — advertising, selling data, monetizing user behaviour or content
      "consent"       — opt-in / opt-out mechanisms, cookie consent, marketing permissions

ENTITY FIELDS (extract only what is explicitly stated — use empty list [] if nothing found):
  - "data_types": list of personal data types mentioned.
      Examples: "email address", "location data", "IP address", "browsing history",
                "biometric data", "payment information", "device identifiers", "photos"
  - "purposes": list of stated purposes for data use or the clause's intent.
      Examples: "targeted advertising", "analytics", "fraud prevention",
                "service improvement", "legal compliance", "AI model training"
  - "actors": list of parties involved (other than the user).
      Examples: "the company", "advertising partners", "data brokers",
                "analytics providers", "government agencies", "affiliated companies"
  - "legal_constructs": list of legal mechanisms or doctrines explicitly invoked.
      Examples: "limitation of liability", "indemnification", "force majeure",
                "warranty disclaimer", "class action waiver", "governing law"
  - "retention_duration": a single string describing how long data is kept, or null.
      Examples: "90 days", "2 years after account closure", "indefinitely", "as required by law"
  - "consent_mechanism": one of "opt-in" | "opt-out" | "implied" | "none" | null.
      "opt-in"  = user must actively agree before data is used
      "opt-out" = data used by default, user can withdraw
      "implied" = consent assumed from continued use of service
      "none"    = no consent mechanism mentioned
      null      = clause is not about consent
  - "monetization_signal": true if this clause involves the company profiting from
      user data or behaviour (ads, data sales, data brokering). false otherwise.

GUIDELINES:
- rights_given_up: things the user surrenders (data, rights to sue, IP, privacy)
- obligations: things the user MUST do or comply with
- benefits: things the user gets (service access, warranties, support)
- unusual: clauses that stand out as atypical, aggressive, or worth flagging separately
- Do NOT invent clauses or entities. Only extract what is explicitly stated in the text.
- Omit trivial, boilerplate clauses (e.g. "this agreement is governed by law").
- Each clause must appear in exactly one category (no duplicates).
- A clause may have a data_topic AND entity fields simultaneously.

Return a JSON object with a single key "clauses" whose value is an array of clause objects.
If no relevant clauses are found in this excerpt, return {{"clauses": []}}.

EXCERPT:
{chunk}
"""

TLDR_PROMPT = """You are a plain-language legal summarizer. Based on the key findings below from a
Terms and Conditions document, write a single TL;DR sentence (max 60 words) that tells the user
what they most need to know before agreeing.

Focus on: data sharing, auto-renewal, arbitration clauses, liability waivers, and any red-risk items.
Be direct and factual. Do not editorialize.

KEY FINDINGS:
{findings}

TL;DR:"""

OVERALL_RISK_PROMPT = """Given these clause risk levels from a Terms and Conditions analysis,
respond with the overall document risk as exactly one word: red, yellow, or green.

red   = multiple high-impact clauses (data selling, arbitration waiver, auto-renewal, broad IP grab)
yellow = some moderate clauses worth noting but not alarming
green  = mostly user-friendly, standard terms

Clause risks: {risk_summary}

Overall risk:"""
