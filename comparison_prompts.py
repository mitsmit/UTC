TOPIC_ALIGNMENT_PROMPT = """You are a legal analyst comparing Terms and Conditions from {n} companies.

You are given a structured list of clauses per company. Your task is to group them into
COMMON TOPICS and produce a unified comparison table.

For each topic:
- Pick a short topic name (e.g. "Data Sharing", "Arbitration", "Auto-Renewal", "IP Rights", "Account Deletion")
- For each company, state whether a relevant clause is present and summarize their stance in one sentence
- Set "risk" per company: "red" (bad for user), "yellow" (moderate), "green" (user-friendly)
- Set "winner" to true for the company with the most user-friendly stance on this topic
- If a company has no clause on a topic, set present=false and risk="green" (absence of a bad clause is good)

Only include topics that are meaningful for comparison — skip topics where all companies are identical.
Limit to the 8 most important topics.

COMPANY CLAUSES:
{company_clauses}

Return a JSON object with key "topics", each element:
{{
  "topic": "...",
  "stances": {{
    "<company_name>": {{
      "present": true/false,
      "risk": "red"|"yellow"|"green",
      "summary": "one sentence",
      "winner": true/false
    }}
  }}
}}
"""

SCORING_PROMPT = """You are scoring Terms and Conditions documents on user-friendliness (0 = worst, 100 = best).

For each company, consider:
- How many red-risk clauses they have (data selling, arbitration waivers, IP grabs) — penalise heavily
- How many yellow-risk clauses (auto-renewal, vague terms) — penalise moderately
- How many green / user-friendly clauses — reward
- Absence of aggressive clauses is a positive signal

Score each company and assign a label:
  0–30: "Aggressive"
  31–55: "Mixed"
  56–75: "Fair"
  76–100: "User-friendly"

COMPANY RISK SUMMARIES:
{risk_summaries}

Return a JSON object with key "scores", a list of:
{{
  "company": "<name>",
  "score": <integer 0-100>,
  "label": "Aggressive"|"Mixed"|"Fair"|"User-friendly"
}}
"""

COMPARISON_SUMMARY_PROMPT = """Write a plain-English comparison summary (3–5 sentences) for someone
deciding which company's Terms and Conditions are most acceptable.

Cover:
- Which company is most user-friendly and why
- The biggest differences between the companies
- Any clauses that all companies share (red flags affecting all options)
- A clear recommendation

COMPARISON DATA:
Winner: {winner}
Scores: {scores}
Key topics: {topics}

Summary:"""
