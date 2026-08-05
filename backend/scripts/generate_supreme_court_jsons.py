import os
import sys
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
OUTPUT_DIR = BASE_DIR / "data" / "supreme_court_jsons"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SUPREME_COURT_CASES = [
    {
        "case_name": "Satbir Singh v. State of Haryana",
        "citation": "2021 SCC OnLine SC 404",
        "court": "Supreme Court of India",
        "year": 2021,
        "bench": "N.V. Ramana, Aniruddha Bose, Krishna Murari",
        "judgment_date": "2021-05-28",
        "summary": "Landmark ruling clarifying the interpretation of 'soon before her death' in dowry death cases and mandatory trial court guidelines under Section 304B IPC (now BNS 80).",
        "ratio_decidendi": "The phrase 'soon before' in dowry death provisions does not mean 'immediately before'. There must be a proximate and live link between the dowry demand/cruelty and the unnatural death.",
        "holding": "Upheld conviction for dowry death under Section 304B IPC; issued mandatory directions to trial courts for recording Section 313 statements cautiously in dowry death trials.",
        "keywords": ["dowry death", "soon before death", "cruelty", "proximity nexus", "presumption", "BNS 80", "BNS 85"],
        "interpreted_sections": [
            {"act": "BNS", "section": "80"},
            {"act": "BNS", "section": "85"},
            {"act": "IPC", "section": "304B"},
            {"act": "IPC", "section": "498A"}
        ],
        "constitutional_articles": ["Article 14", "Article 21", "Article 141"],
        "legal_principles": ["Presumption of Dowry Death", "Burden of Proof", "Proximity Nexus"],
        "related_evidence": ["Medical Report", "Postmortem Report", "Marriage Certificate", "Witness Statement", "WhatsApp Chats"]
    },
    {
        "case_name": "State of West Bengal v. Orilal Jaiswal",
        "citation": "(1994) 1 SCC 73",
        "court": "Supreme Court of India",
        "year": 1994,
        "bench": "G.N. Ray, S.C. Agrawal",
        "judgment_date": "1993-09-03",
        "summary": "Landmark precedent defining the standard of proof required to establish abetment of suicide and cruelty by husband and in-laws.",
        "ratio_decidendi": "Cruelty under matrimonial penal law requires persistent harassment or willful conduct of such a nature as is likely to drive a woman to commit suicide or cause grave injury to life, limb, or health.",
        "holding": "Reversed High Court acquittal, holding that continuous dowry harassment and torture directly instigated the victim's unnatural death within seven years of marriage.",
        "keywords": ["cruelty", "dowry harassment", "abetment of suicide", "willful conduct", "BNS 80", "BNS 85"],
        "interpreted_sections": [
            {"act": "BNS", "section": "80"},
            {"act": "BNS", "section": "85"},
            {"act": "IPC", "section": "304B"},
            {"act": "IPC", "section": "498A"}
        ],
        "constitutional_articles": ["Article 14", "Article 15", "Article 21", "Article 141"],
        "legal_principles": ["Standard of Proof in Cruelty", "Presumption of Dowry Death", "Mens Rea"],
        "related_evidence": ["Dying Declaration", "Witness Statement", "Inquest Report", "Postmortem Report"]
    },
    {
        "case_name": "State of Punjab v. Gurmit Singh",
        "citation": "(1996) 2 SCC 384",
        "court": "Supreme Court of India",
        "year": 1996,
        "bench": "A.S. Anand, K. Venkataswami",
        "judgment_date": "1996-01-17",
        "summary": "Landmark judgment establishing evidentiary guidelines for victim testimony in sexual assault trials.",
        "ratio_decidendi": "The sole testimony of a rape victim is reliable and does not require corroboration unless there are compelling reasons to doubt her credibility. Corroboration is not a legal mandate.",
        "holding": "Reversed acquittal of accused; laid down guidelines to conduct sexual offence trials in camera and protect victim dignity under Article 21.",
        "keywords": ["rape", "sole testimony of victim", "corroboration not essential", "in-camera trial", "female dignity", "BNS 63", "BNS 64"],
        "interpreted_sections": [
            {"act": "BNS", "section": "63"},
            {"act": "BNS", "section": "64"},
            {"act": "IPC", "section": "375"},
            {"act": "IPC", "section": "376"}
        ],
        "constitutional_articles": ["Article 15", "Article 21", "Article 51A", "Article 141"],
        "legal_principles": ["Sole Testimony of Victim", "Human Dignity", "Presumption of Innocence"],
        "related_evidence": ["Statement under Section 164", "Medical Report", "FSL Report", "DNA Report", "Witness Statement"]
    },
    {
        "case_name": "Independent Thought v. Union of India",
        "citation": "(2017) 10 SCC 800",
        "court": "Supreme Court of India",
        "year": 2017,
        "bench": "M.B. Lokur, Deepak Gupta",
        "judgment_date": "2017-10-11",
        "summary": "Landmark ruling striking down Exception 2 to Section 375 IPC, criminalizing sexual intercourse with a minor wife between 15 and 18 years of age.",
        "ratio_decidendi": "Bodily integrity, autonomy, and child rights under Articles 14, 15, and 21 paramountly protect minor girls from non-consensual sexual acts, regardless of marital status.",
        "holding": "Declared marital rape of minor wives aged 15-18 as an offence under sexual violence penal sections.",
        "keywords": ["marital rape of minor", "child rights", "bodily autonomy", "minor wife", "BNS 63", "BNS 64"],
        "interpreted_sections": [
            {"act": "BNS", "section": "63"},
            {"act": "BNS", "section": "64"},
            {"act": "IPC", "section": "375"}
        ],
        "constitutional_articles": ["Article 14", "Article 15", "Article 21", "Article 21A", "Article 141"],
        "legal_principles": ["Best Interest of the Child", "Bodily Autonomy", "Non-Arbitrariness"],
        "related_evidence": ["Birth Certificate", "Medical Report", "School Certificate", "Witness Statement"]
    },
    {
        "case_name": "Premiya @ Prem Prakash v. State of Rajasthan",
        "citation": "2023 SCC OnLine SC 1210",
        "court": "Supreme Court of India",
        "year": 2023,
        "bench": "B.R. Gavai, Prashant Kumar Mishra",
        "judgment_date": "2023-09-15",
        "summary": "Ruling on assault and criminal force with intent to outrage modesty of a woman under penal provisions.",
        "ratio_decidendi": "Essential ingredients for outraging modesty require that the victim must be a woman and the accused must have used criminal force intending or knowing it likely to outrage her modesty.",
        "holding": "Upheld conviction under modesty outraging provisions, emphasizing house trespass and criminal intimidation aggravating the assault.",
        "keywords": ["outraging modesty", "criminal force", "house trespass", "criminal intimidation", "BNS 355", "BNS 351", "BNS 74"],
        "interpreted_sections": [
            {"act": "BNS", "section": "355"},
            {"act": "BNS", "section": "351"},
            {"act": "BNS", "section": "74"},
            {"act": "IPC", "section": "354"},
            {"act": "IPC", "section": "506"}
        ],
        "constitutional_articles": ["Article 14", "Article 15", "Article 21", "Article 51A", "Article 141"],
        "legal_principles": ["Actus Reus", "Mens Rea", "Protection of Female Safety"],
        "related_evidence": ["CCTV Footage", "Statement under Section 164", "Witness Statement", "FSL Report"]
    },
    {
        "case_name": "Bachchan Singh v. State of Punjab",
        "citation": "(1980) 2 SCC 684",
        "court": "Supreme Court of India",
        "year": 1980,
        "bench": "Y.V. Chandrachud, R.S. Sarkaria, A.C. Gupta, N.L. Untwalia, P.N. Bhagwati",
        "judgment_date": "1980-05-09",
        "summary": "Constitutional Bench judgment laying down the 'rarest of rare cases' doctrine for capital punishment in murder trials.",
        "ratio_decidendi": "Death penalty for murder under penal provisions is constitutionally valid under Article 21 if restricted to the 'rarest of rare cases' where alternative option of life imprisonment is unquestionably foreclosed.",
        "holding": "Upheld constitutionality of capital punishment for murder under Section 302 IPC (now BNS 103), establishing balancing test between aggravating and mitigating circumstances.",
        "keywords": ["murder", "rarest of rare", "capital punishment", "death penalty", "mitigating circumstances", "BNS 101", "BNS 103"],
        "interpreted_sections": [
            {"act": "BNS", "section": "101"},
            {"act": "BNS", "section": "103"},
            {"act": "IPC", "section": "300"},
            {"act": "IPC", "section": "302"}
        ],
        "constitutional_articles": ["Article 14", "Article 19", "Article 21", "Article 72", "Article 141"],
        "legal_principles": ["Rarest of Rare Doctrine", "Proportionality in Sentencing", "Human Dignity"],
        "related_evidence": ["Postmortem Report", "FSL Report", "Weapon Recovery Memo", "DNA Report", "CCTV Footage"]
    },
    {
        "case_name": "Lalita Kumari v. Government of UP",
        "citation": "(2014) 2 SCC 1",
        "court": "Supreme Court of India",
        "year": 2014,
        "bench": "P. Sathasivam, B.S. Chauhan, Ranjan Gogoi, S.A. Bobde, M.Y. Eqbal",
        "judgment_date": "2013-11-12",
        "summary": "Landmark Constitution Bench ruling on mandatory registration of FIR upon receipt of cognizable offence information.",
        "ratio_decidendi": "Registration of FIR under Section 154 CrPC (now BNSS 173) is mandatory if the information discloses commission of a cognizable offence. Police have no discretion to conduct preliminary inquiry prior to FIR in clear cognizable offences.",
        "holding": "Mandated immediate FIR registration for cognizable offences including rape, dowry death, murder, and kidnapping.",
        "keywords": ["mandatory FIR", "cognizable offence", "police duty", "investigation procedure", "BNS 80", "BNS 63", "BNS 101"],
        "interpreted_sections": [
            {"act": "BNS", "section": "80"},
            {"act": "BNS", "section": "63"},
            {"act": "BNS", "section": "101"},
            {"act": "BNSS", "section": "173"}
        ],
        "constitutional_articles": ["Article 14", "Article 21", "Article 22", "Article 141"],
        "legal_principles": ["Mandatory Duty of State", "Rule of Law", "Access to Justice"],
        "related_evidence": ["FIR Copy", "Written Complaint", "Police Logbook", "Call Detail Records (CDR)"]
    },
    {
        "case_name": "Arnesh Kumar v. State of Bihar",
        "citation": "(2014) 8 SCC 273",
        "court": "Supreme Court of India",
        "year": 2014,
        "bench": "Chandramauli Kr. Prasad, Pinaki Chandra Ghose",
        "judgment_date": "2014-07-02",
        "summary": "Landmark precedent regulating arbitrary police arrests in matrimonial cruelty and offences punishable up to 7 years imprisonment.",
        "ratio_decidendi": "Arrest should not be automatic upon registration of FIR under Section 498A IPC (now BNS 85). Police must satisfy Section 41 CrPC (now BNSS 35) parameters before arresting.",
        "holding": "Laid down mandatory 9-point checklist for police officers and magistrates prior to authorizing detention in 7-year imprisonment offences.",
        "keywords": ["arrest safeguards", "matrimonial cruelty", "unnecessary arrest", "police remand", "BNS 85", "BNS 80"],
        "interpreted_sections": [
            {"act": "BNS", "section": "85"},
            {"act": "BNS", "section": "80"},
            {"act": "IPC", "section": "498A"}
        ],
        "constitutional_articles": ["Article 14", "Article 21", "Article 22", "Article 141"],
        "legal_principles": ["Protection against Arbitrary Arrest", "Magisterial Scrutiny", "Personal Liberty"],
        "related_evidence": ["Arrest Memo", "Notice under Section 35 BNSS", "Police Logbook"]
    }
]


def generate_supreme_court_jsons():
    print(f"Generating {len(SUPREME_COURT_CASES)} landmark Supreme Court case JSONs...")
    for cs in SUPREME_COURT_CASES:
        filename = f"{cs['case_name'].replace(' ', '_').replace('@', '').replace('.', '').replace('/', '_')}.json"
        filepath = OUTPUT_DIR / filename
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(cs, f, indent=2, ensure_ascii=False)
        print(f"  [+] Created: {filepath.name}")

    print("\n" + "=" * 80)
    print(f"SUCCESS: Generated {len(SUPREME_COURT_CASES)} Supreme Court Case JSONs in {OUTPUT_DIR}")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    generate_supreme_court_jsons()
