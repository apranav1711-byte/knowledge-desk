"""Synthetic enterprise policy corpus + labelled question set (fully deterministic, seed-controlled).

Design goals
  * Many near-duplicate documents that differ only in an entity (department / region / grade / system), so retrieval must
    discriminate on the entity, not just the topic.
  * Documents spread over the five access levels used by Knowledge Desk.
  * Every question has a gold fact (topic, entity, value) so correctness is checked by string containment of the value.
  * Unanswerable questions ask for a (topic, entity) combination that does not exist in the corpus.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

DEPTS = ["Engineering", "Sales", "Finance", "Human Resources", "Marketing", "Operations", "Legal", "Procurement",
         "Customer Support", "Research", "Facilities", "Security"]
REGIONS = ["North", "South", "East", "West", "Central", "Overseas"]
GRADES = ["G3", "G4", "G5", "G6", "G7", "G8", "G9"]
SYSTEMS = ["email", "VPN", "the finance portal", "the HR portal", "the code repository", "the data warehouse"]
DEVICES = ["14-inch laptop", "dual monitors", "standing desk", "noise-cancelling headset", "ergonomic chair", "docking station"]
CODENAMES = ["Cedar", "Falcon", "Orchid", "Granite", "Meridian", "Willow", "Atlas", "Sparrow", "Juniper", "Harbor",
             "Summit", "Lotus", "Phoenix", "Aurora", "Beacon", "Cobalt"]
OFFICES = ["Bengaluru", "Mumbai", "Delhi", "Chennai", "Hyderabad", "Pune", "Kolkata", "Ahmedabad", "Jaipur", "Kochi", "Noida",
           "Gurugram", "Indore", "Nagpur", "Lucknow", "Chandigarh", "Coimbatore", "Mysuru", "Vizag", "Bhopal", "Surat", "Patna",
           "Goa", "Ranchi"]
DEPT_OFFICE = [f"{d} ({o})" for d in DEPTS for o in OFFICES[:8]]            # 96 entities, near-duplicates by design
GRADE_TRACK = [f"{g}-{t}" for g in GRADES for t in ("technical", "managerial", "support")]  # 21
SYSTEM_ENV = [f"{s} ({e})" for s in SYSTEMS for e in ("production", "staging", "contractor accounts")]  # 18
PROJECTS = [f"{c}-{n}" for c in CODENAMES for n in (1, 2, 3)]               # 48
FILLER = [
    "This policy was reviewed by the policy committee and takes effect on the first working day of the quarter.",
    "Questions about this policy should be sent to the relevant service desk through the employee portal.",
    "Exceptions must be requested in writing and approved before any commitment is made.",
    "Managers are responsible for communicating this policy to their teams.",
    "A printed copy of this document is not controlled; always refer to the latest online version.",
    "Records related to this policy are retained for seven years in line with the retention schedule.",
    "Employees should contact their line manager if anything in this document is unclear.",
    "This document supersedes all earlier guidance on the same subject.",
]

# topic -> (classification, sentence template, question template, entity pool, value generator, value formatter)
TOPICS = {
    "annual_leave":  ("General_Internal", "{e} employees receive {v} days of paid annual leave each calendar year.",
                      "How many days of annual leave do {e} employees get?", DEPT_OFFICE, lambda r: r.randint(18, 30), str),
    "hotel_limit":   ("General_Internal", "For {e} travel, the reimbursable hotel room limit is INR {v} per night excluding taxes.",
                      "What is the hotel room limit for {e} travel?", OFFICES, lambda r: r.randrange(5000, 14000, 250), lambda v: f"{v:,}"),
    "password_age":  ("General_Internal", "Passwords for {e} must be changed every {v} days.",
                      "How often must passwords for {e} be changed?", SYSTEM_ENV, lambda r: r.choice([30, 45, 60, 75, 90, 120]), str),
    "equipment":     ("General_Internal", "New {e} starters receive a {v} on their first day.",
                      "What equipment does a new {e} starter receive?", DEPT_OFFICE, lambda r: r.choice(DEVICES), str),
    "remote_days":   ("General_Internal", "{e} employees may work remotely {v} days per week with manager approval.",
                      "How many days per week can {e} employees work remotely?", DEPT_OFFICE, lambda r: r.randint(1, 4), str),
    "holiday_count": ("Public", "The {e} office observes {v} company holidays each year.",
                      "How many company holidays does the {e} office observe?", OFFICES, lambda r: r.randint(9, 16), str),
    "cafeteria":     ("Public", "The {e} cafeteria opens at {v} in the morning on working days.",
                      "At what time does the {e} cafeteria open?", OFFICES, lambda r: f"{r.randint(7, 9)}:{r.choice(['00', '15', '30', '45'])}", str),
    "purchase_limit": ("Management", "Managers in {e} may approve purchases up to INR {v} per transaction.",
                       "Up to what amount can managers in {e} approve purchases?", DEPT_OFFICE, lambda r: r.randrange(20000, 400000, 5000), lambda v: f"{v:,}"),
    "training_budget": ("Management", "The quarterly training budget for {e} is INR {v}.",
                        "What is the quarterly training budget for {e}?", DEPT_OFFICE, lambda r: r.randrange(100000, 900000, 10000), lambda v: f"{v:,}"),
    "sales_target":  ("Management", "The revenue target for the {e} office this quarter is INR {v} crore.",
                      "What is the quarterly revenue target for the {e} office?", OFFICES, lambda r: r.randint(8, 60), str),
    "bonus_pct":     ("HR_Confidential", "The target annual bonus for grade {e} is {v} percent of base salary.",
                      "What is the target annual bonus for grade {e}?", GRADE_TRACK, lambda r: r.randint(5, 25), str),
    "notice_period": ("HR_Confidential", "Employees in grade {e} serve a notice period of {v} days.",
                      "What notice period applies to employees in grade {e}?", GRADE_TRACK, lambda r: r.choice([30, 45, 60, 90]), str),
    "planned_hires": ("HR_Confidential", "The planned number of new hires for {e} next year is {v}.",
                      "How many new hires are planned for {e} next year?", DEPT_OFFICE, lambda r: r.randint(2, 60), str),
    "project_budget": ("Restricted", "Project {e} has a planned budget of INR {v} million.",
                       "What is the planned budget of Project {e}?", PROJECTS, lambda r: r.randint(20, 900), str),
    "launch_quarter": ("Restricted", "The target launch quarter for Project {e} is {v}.",
                       "In which quarter is Project {e} planned to launch?", PROJECTS, lambda r: r.choice(["Q1 2027", "Q2 2027", "Q3 2027", "Q4 2027", "Q1 2028"]), str),
}
# Synonym-phrased questions: same entity, but none of the topic words of the source sentence (lexical mismatch).
ALT_Q = {
    "annual_leave": "What is the vacation allowance for {e} staff?",
    "hotel_limit": "What is the maximum lodging cost per night for {e} trips?",
    "password_age": "What is the password rotation interval for {e}?",
    "equipment": "Which hardware is issued to new joiners in {e}?",
    "remote_days": "How often can {e} staff work from home each week?",
    "holiday_count": "How many public holidays are there at the {e} site?",
    "cafeteria": "When does the canteen at {e} open?",
    "purchase_limit": "What spending authority do {e} managers have per transaction?",
    "training_budget": "How much money is set aside for learning and development in {e} each quarter?",
    "sales_target": "What turnover goal applies to the {e} branch this quarter?",
    "bonus_pct": "What is the performance bonus percentage for grade {e}?",
    "notice_period": "How long is the resignation notice for grade {e}?",
    "planned_hires": "How many people will {e} recruit next year?",
    "project_budget": "How much funding is allocated to Project {e}?",
    "launch_quarter": "When is Project {e} due to go live?",
}
PARAPHRASE = [
    lambda q: q,
    lambda q: q.replace("How many", "What number of").replace("What is the", "Tell me the").replace("What", "Which"),
]


@dataclass
class Fact:
    topic: str
    entity: str
    value: str
    classification: str
    doc_id: int
    sentence: str


@dataclass
class Doc:
    id: int
    title: str
    classification: str
    topic: str
    text: str
    facts: list[Fact] = field(default_factory=list)


@dataclass
class Query:
    text: str
    kind: str  # 'answerable' | 'unanswerable'
    topic: str
    entity: str
    value: str | None
    classification: str | None
    doc_id: int | None
    variant: str = "orig"  # 'orig' | 'para' | 'syn'


def build(seed: int = 7, facts_per_doc: int = 4) -> tuple[list[Doc], list[Query]]:
    rng = random.Random(seed)
    docs: list[Doc] = []
    queries: list[Query] = []
    for topic, (cls, sent_t, q_t, pool, gen, fmt) in TOPICS.items():
        entities = pool[:]
        rng.shuffle(entities)
        keep = entities[: max(3, int(len(entities) * 0.75))]  # hold back ~25% of entities -> unanswerable questions
        held_back = [e for e in entities if e not in keep]
        for start in range(0, len(keep), facts_per_doc):
            chunk = keep[start:start + facts_per_doc]
            doc = Doc(len(docs), f"{topic.replace('_', ' ').title()} guidelines {len(docs) + 1}", cls, topic, "")
            lines = [f"# {doc.title}", "", f"Classification: {cls.replace('_', ' ')}.", "", "## Provisions", ""]
            for e in chunk:
                v = fmt(gen(rng))
                s = sent_t.format(e=e, v=v)
                doc.facts.append(Fact(topic, e, v, cls, doc.id, s))
                lines += [s, rng.choice(FILLER), ""]
            lines += ["## Administration", "", rng.choice(FILLER), rng.choice(FILLER)]
            doc.text = "\n".join(lines)
            docs.append(doc)
            for f in doc.facts:
                base = q_t.format(e=f.entity)
                for k, para in enumerate(PARAPHRASE):
                    queries.append(Query(para(base), "answerable", topic, f.entity, f.value, cls, doc.id, ("orig", "para")[k]))
                queries.append(Query(ALT_Q[topic].format(e=f.entity), "answerable", topic, f.entity, f.value, cls, doc.id, "syn"))
        for e in held_back:
            queries.append(Query(q_t.format(e=e), "unanswerable", topic, e, None, None, None))
            queries.append(Query(ALT_Q[topic].format(e=e), "unanswerable", topic, e, None, None, None, "syn"))
    return docs, queries


if __name__ == "__main__":
    d, q = build()
    from collections import Counter
    print(len(d), "documents;", sum(len(x.facts) for x in d), "facts;", len(q), "queries")
    print(Counter(x.classification for x in d)); print(Counter(x.kind for x in q))
    print(d[0].text[:500])
