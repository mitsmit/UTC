VALIDATOR_PROMPT = """You are a document classifier. Decide if the text below is a Terms and Conditions,
Privacy Policy, End User License Agreement, or similar legal agreement.

Respond with exactly one word: YES or NO.

Text (first 1000 chars):
{sample}
"""

CHUNK_ANALYSIS_PROMPT = """You are a legal plain-language expert. Analyze the following excerpt from a
Terms and Conditions document and extract clauses into four categories.

For each clause you find, output a JSON object with:
  - "category": one of "rights_given_up" | "obligations" | "benefits" | "unusual"
  - "summary": one plain-English sentence describing the clause
  - "risk": "red" (high impact on user) | "yellow" (moderate) | "green" (user-friendly)
  - "unusual": true if this clause is non-standard or surprising, false otherwise
  - "citation": the verbatim excerpt (max 200 chars) from the text that supports this clause

Guidelines:
- rights_given_up: things the user surrenders (data, rights to sue, IP, privacy)
- obligations: things the user MUST do or comply with
- benefits: things the user gets (service access, warranties, support)
- unusual: clauses that stand out as atypical, aggressive, or worth flagging separately
- Do NOT invent clauses. Only extract what is explicitly stated in the text.
- Omit trivial, boilerplate clauses (e.g. "this agreement is governed by law").
- Each clause must appear in exactly one category (no duplicates).
- If some clauses are too common but still worth noting, categorize them as "yellow" risk but not "unusual".
- Explain your reasoning for the risk level in the summary, but do not editorialize beyond that.

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
