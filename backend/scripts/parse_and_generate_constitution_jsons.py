import os
import sys
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
OUTPUT_DIR = BASE_DIR / "data" / "constitution_jsons"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CONSTITUTION_ARTICLES = [
    {
        "article_number": "Article 14",
        "title": "Equality before law",
        "part": "Part III - Fundamental Rights",
        "chapter": "Right to Equality",
        "category": "Fundamental Rights & Constitutional Protections",
        "full_text": "The State shall not deny to any person equality before the law or the equal protection of the laws within the territory of India.",
        "summary": "Guarantees equality before the law and equal protection of the laws to all persons. In criminal law, it prohibits arbitrary state classification, discriminatory prosecution, unguided executive discretion, and procedural unfairness.",
        "importance_score": 0.98,
        "relevance_reason": "Article 14 is the cornerstone against arbitrary police action, selective prosecution, unequal bail terms, and unguided executive power under criminal statutes.",
        "keywords": [
            "Equality Before Law", "Equal Protection of Laws", "Arbitrary Action",
            "Rule of Law", "Non-Discrimination", "Procedural Fairness",
            "Selective Prosecution", "Article 14 Violation", "Classification Test", "Manifest Arbitrariness"
        ],
        "legal_principles": [
            "Rule of Law", "Non-Arbitrariness", "Equal Protection", "Procedural Fairness"
        ],
        "criminal_law_relevance": [
            "Challenging arbitrary penal provisions or discriminatory criminal procedure",
            "Ensuring non-discriminatory grant of bail and parole",
            "Preventing selective or malice-driven criminal prosecutions by state agencies"
        ],
        "possible_related_bns_topics": [
            "BNS 101 (Murder)", "BNS 63 (Rape)", "BNS 351 (Criminal Intimidation)", "BNS 111 (Organised Crime)"
        ],
        "graph_relationships": {
            "related_bns_sections": ["BNS 80", "BNS 85", "BNS 63", "BNS 101"],
            "related_bnss_topics": ["Section 482 BNSS (Inherent powers of High Court)", "Bail provisions under BNSS"],
            "related_bsa_topics": ["Burden of Proof under BSA"],
            "related_offence_categories": ["Women Offences", "Violent Offences", "Organised Crime"],
            "related_constitutional_principles": ["Rule of Law", "Non-Arbitrariness"],
            "possible_landmark_cases": [
                "E.P. Royappa v. State of Tamil Nadu",
                "Maneka Gandhi v. Union of India",
                "Shayara Bano v. Union of India"
            ],
            "recommended_evidence_types": ["Witness Statement", "Official Record", "CCTV Footage"]
        },
        "graph_metadata": {
            "node_type": "ConstitutionArticle",
            "source": "Constitution of India",
            "jurisdiction": "India"
        }
    },
    {
        "article_number": "Article 15",
        "title": "Prohibition of discrimination on grounds of religion, race, caste, sex or place of birth",
        "part": "Part III - Fundamental Rights",
        "chapter": "Right to Equality",
        "category": "Gender Justice & Protective Discrimination",
        "full_text": "(1) The State shall not discriminate against any citizen on grounds only of religion, race, caste, sex, place of birth or any of them. (3) Nothing in this article shall prevent the State from making any special provision for women and children.",
        "summary": "Prohibits state discrimination on grounds of sex, caste, or religion, while explicitly permitting special protective criminal and welfare provisions for women and children under Clause (3).",
        "importance_score": 0.95,
        "relevance_reason": "Article 15(3) provides the constitutional justification for special penal laws protecting women and children, including statutory offences like dowry death, rape, and cruelty.",
        "keywords": [
            "Prohibition of Discrimination", "Special Provisions for Women", "Protection of Children",
            "Gender Justice", "Substantive Equality", "Protective Discrimination", "Women Rights"
        ],
        "legal_principles": [
            "Substantive Equality", "Protective Discrimination", "Gender Justice"
        ],
        "criminal_law_relevance": [
            "Constitutional validity of gender-specific offences protecting women",
            "Enactment of special penal statutes for child protection (POCSO, Child Labour)",
            "Affirmative state action in victim rehabilitation"
        ],
        "possible_related_bns_topics": [
            "BNS 80 (Dowry Death)", "BNS 85 (Cruelty by Husband/Relatives)", "BNS 63 (Rape)", "BNS 74 (Outraging Modesty)"
        ],
        "graph_relationships": {
            "related_bns_sections": ["BNS 80", "BNS 85", "BNS 63", "BNS 74", "BNS 75"],
            "related_bnss_topics": ["Special trial procedure for sexual offences against women and children"],
            "related_bsa_topics": ["Presumption as to dowry death under Section 113B BSA"],
            "related_offence_categories": ["Women Offences", "Child Offences", "Sexual Offences"],
            "related_constitutional_principles": ["Gender Justice", "Substantive Equality"],
            "possible_landmark_cases": [
                "Vishaka v. State of Rajasthan",
                "State of Punjab v. Gurmit Singh",
                "Independent Thought v. Union of India"
            ],
            "recommended_evidence_types": ["Dying Declaration", "Medical Report", "Witness Statement"]
        },
        "graph_metadata": {
            "node_type": "ConstitutionArticle",
            "source": "Constitution of India",
            "jurisdiction": "India"
        }
    },
    {
        "article_number": "Article 19",
        "title": "Protection of certain rights regarding freedom of speech, etc.",
        "part": "Part III - Fundamental Rights",
        "chapter": "Right to Freedom",
        "category": "Fundamental Freedoms & Reasonable Restrictions",
        "full_text": "(1) All citizens shall have the right (a) to freedom of speech and expression... (2) Nothing in sub-clause (a) of clause (1) shall affect the operation of any existing law, or prevent the State from making any law, in so far as such law imposes reasonable restrictions... in the interests of the sovereignty and integrity of India, the security of the State, friendly relations with foreign States, public order, decency or morality or in relation to contempt of court, defamation or incitement to an offence.",
        "summary": "Guarantees fundamental freedoms including speech and expression, subject to reasonable restrictions imposed by penal law for public order, security of state, defamation, or incitement to an offence.",
        "importance_score": 0.92,
        "relevance_reason": "Article 19(2) delineates the constitutional boundary of penal laws punishing speech offences, hate speech, defamation, sedition/subversive acts, and cyber crimes.",
        "keywords": [
            "Freedom of Speech", "Reasonable Restrictions", "Public Order", "Decency and Morality",
            "Incitement to Offence", "Defamation", "Hate Speech", "Chilling Effect", "Proportionality Test"
        ],
        "legal_principles": [
            "Proportionality", "Reasonable Restriction", "Freedom of Expression"
        ],
        "criminal_law_relevance": [
            "Balancing penal provisions against free speech rights",
            "Constitutional scrutiny of speech offences like defamation and hate speech",
            "Assessing public order exceptions in criminal statutes"
        ],
        "possible_related_bns_topics": [
            "BNS 356 (Defamation)", "BNS 197 (Promoting Enmity)", "BNS 152 (Acts Endangering Sovereignty)"
        ],
        "graph_relationships": {
            "related_bns_sections": ["BNS 356", "BNS 197", "BNS 152"],
            "related_bnss_topics": ["Public order maintenance under BNSS"],
            "related_bsa_topics": ["Electronic records evidence for online speech"],
            "related_offence_categories": ["Speech Offences", "Public Order Offences", "State Security"],
            "related_constitutional_principles": ["Proportionality", "Reasonable Restriction"],
            "possible_landmark_cases": [
                "Shreya Singhal v. Union of India",
                "Kedarnath Singh v. State of Bihar",
                "Subramanian Swamy v. Union of India"
            ],
            "recommended_evidence_types": ["Electronic Record", "WhatsApp Chats", "Audio Recording"]
        },
        "graph_metadata": {
            "node_type": "ConstitutionArticle",
            "source": "Constitution of India",
            "jurisdiction": "India"
        }
    },
    {
        "article_number": "Article 20",
        "title": "Protection in respect of conviction for offences",
        "part": "Part III - Fundamental Rights",
        "chapter": "Right to Freedom",
        "category": "Criminal Jurisprudence & Trial Safeguards",
        "full_text": "(1) No person shall be convicted of any offence except for violation of a law in force at the time of the commission of the act charged as an offence, nor be subjected to a penalty greater than that which might have been inflicted under the law in force at the time of the commission of the offence. (2) No person shall be prosecuted and punished for the same offence more than once. (3) No person accused of any offence shall be compelled to be a witness against himself.",
        "summary": "Establishes three sacred safeguards of criminal jurisprudence: (1) Protection against ex post facto criminal laws, (2) Protection against Double Jeopardy, and (3) Right against Self-Incrimination.",
        "importance_score": 1.00,
        "relevance_reason": "Article 20 directly governs criminal liability, trial procedure, evidentiary admissibility of confessions/narco-analysis, and protection against multiple convictions.",
        "keywords": [
            "Ex Post Facto Law", "Double Jeopardy", "Self Incrimination", "Confession under Coercion",
            "Retroactive Criminal Law", "Nemo Vexari", "Nemo Tenetur", "Narco Analysis", "Polygraph Protection"
        ],
        "legal_principles": [
            "Protection against Ex Post Facto Law", "Double Jeopardy", "Right against Self-Incrimination", "Nemo Tenetur"
        ],
        "criminal_law_relevance": [
            "Invalidates retroactive application of newly enacted criminal laws or enhanced penalties",
            "Bars re-prosecution of accused for the same offence after final conviction/acquittal",
            "Protects accused from involuntary confessions, forced narco-analysis, or coerced testimony"
        ],
        "possible_related_bns_topics": [
            "BNS 1 (Short title, extent and commencement)", "General Exceptions under BNS"
        ],
        "graph_relationships": {
            "related_bns_sections": ["BNS 1", "BNS 80", "BNS 101"],
            "related_bnss_topics": ["Autrefois acquit and autrefois convict under BNSS"],
            "related_bsa_topics": ["Inadmissibility of police confessions under BSA"],
            "related_offence_categories": ["Criminal Trial Safeguards", "Penal Procedure", "Evidence Law"],
            "related_constitutional_principles": ["Double Jeopardy", "Right against Self-Incrimination", "Ex Post Facto Protection"],
            "possible_landmark_cases": [
                "Selvi v. State of Karnataka",
                "M.P. Sharma v. Satish Chandra",
                "Kathi Kalu Oghad v. State of Bombay",
                "Nandini Satpathy v. P.L. Dani"
            ],
            "recommended_evidence_types": ["Statement under Section 164", "FSL Report", "Witness Statement"]
        },
        "graph_metadata": {
            "node_type": "ConstitutionArticle",
            "source": "Constitution of India",
            "jurisdiction": "India"
        }
    },
    {
        "article_number": "Article 21",
        "title": "Protection of life and personal liberty",
        "part": "Part III - Fundamental Rights",
        "chapter": "Right to Freedom",
        "category": "Life, Liberty & Procedural Due Process",
        "full_text": "No person shall be deprived of his life or personal liberty except according to procedure established by law.",
        "summary": "The paramount fundamental right guaranteeing life and personal liberty, interpreted judicially to encompass procedural due process, fair trial, speedy trial, dignity, protection against custodial violence, right to legal aid, and victim rights.",
        "importance_score": 1.00,
        "relevance_reason": "Article 21 is the ultimate substantive and procedural touchstone of criminal justice in India, governing everything from police investigation to sentencing and capital punishment.",
        "keywords": [
            "Protection of Life", "Personal Liberty", "Procedure Established by Law", "Fair Trial",
            "Speedy Trial", "Right to Privacy", "Human Dignity", "Custodial Violence", "Legal Aid",
            "Bail as Rule", "Victim Rights", "Capital Punishment", "Substantive Due Process"
        ],
        "legal_principles": [
            "Procedure Established by Law", "Procedural Due Process", "Fair Trial", "Human Dignity", "Presumption of Innocence"
        ],
        "criminal_law_relevance": [
            "Ensuring just, fair, and reasonable procedure during police arrest and investigation",
            "Guaranteeing right to fair trial, speedy trial, and competent legal assistance",
            "Preventing custodial death, torture, and illegal police detention",
            "Establishing victim compensation and dignity in sexual offence trials"
        ],
        "possible_related_bns_topics": [
            "BNS 80 (Dowry Death)", "BNS 85 (Cruelty)", "BNS 63 (Rape)", "BNS 101 (Murder)", "BNS 103 (Punishment for Murder)"
        ],
        "graph_relationships": {
            "related_bns_sections": ["BNS 80", "BNS 85", "BNS 63", "BNS 101", "BNS 103", "BNS 124"],
            "related_bnss_topics": ["Bail procedure", "Mandatory FIR registration", "Custodial investigation limits"],
            "related_bsa_topics": ["Dying declaration reliability", "Medical examination of victim"],
            "related_offence_categories": ["Life & Liberty Offences", "Women Offences", "Custodial Offences", "Homicide"],
            "related_constitutional_principles": ["Procedural Due Process", "Fair Trial", "Human Dignity"],
            "possible_landmark_cases": [
                "Maneka Gandhi v. Union of India",
                "Hussainara Khatoon v. Home Secretary, State of Bihar",
                "D.K. Basu v. State of West Bengal",
                "Bachchan Singh v. State of Punjab",
                "K.S. Puttaswamy v. Union of India"
            ],
            "recommended_evidence_types": [
                "Postmortem Report", "Medical Report", "Inquest Report", "Dying Declaration",
                "CCTV Footage", "Call Detail Records (CDR)", "Witness Statement"
            ]
        },
        "graph_metadata": {
            "node_type": "ConstitutionArticle",
            "source": "Constitution of India",
            "jurisdiction": "India"
        }
    },
    {
        "article_number": "Article 21A",
        "title": "Right to education",
        "part": "Part III - Fundamental Rights",
        "chapter": "Right to Freedom",
        "category": "Child Rights & Welfare",
        "full_text": "The State shall provide free and compulsory education to all children of the age of six to fourteen years in such manner as the State may, by law, determine.",
        "summary": "Mandates free and compulsory education for children aged 6 to 14, serving as a constitutional pillar for child protection laws against child labour, exploitation, and trafficking.",
        "importance_score": 0.82,
        "relevance_reason": "Reinforces state duty to prevent child exploitation, truancy resulting from child trafficking, and hazardous child employment under criminal law.",
        "keywords": [
            "Right to Education", "Child Protection", "Compulsory Education", "Child Rights", "Child Exploitation"
        ],
        "legal_principles": [
            "Best Interest of the Child", "State Protection of Minors"
        ],
        "criminal_law_relevance": [
            "Preventing child labor and forced truancy",
            "Supporting criminal statutes against child trafficking and sexual abuse"
        ],
        "possible_related_bns_topics": [
            "BNS 137 (Kidnapping and Abduction of Child)", "BNS 143 (Trafficking of Person)"
        ],
        "graph_relationships": {
            "related_bns_sections": ["BNS 137", "BNS 143"],
            "related_bnss_topics": ["Child witness procedure"],
            "related_bsa_topics": ["Child witness testimony guidelines"],
            "related_offence_categories": ["Child Offences", "Trafficking Offences"],
            "related_constitutional_principles": ["Best Interest of the Child"],
            "possible_landmark_cases": [
                "Unni Krishnan v. State of Andhra Pradesh",
                "Society for Unaided Private Schools v. Union of India"
            ],
            "recommended_evidence_types": ["Birth Certificate", "School Certificate"]
        },
        "graph_metadata": {
            "node_type": "ConstitutionArticle",
            "source": "Constitution of India",
            "jurisdiction": "India"
        }
    },
    {
        "article_number": "Article 22",
        "title": "Protection against arrest and detention in certain cases",
        "part": "Part III - Fundamental Rights",
        "chapter": "Right to Freedom",
        "category": "Arrest Procedures & Preventive Detention",
        "full_text": "(1) No person who is arrested shall be detained in custody without being informed, as soon as may be, of the grounds for such arrest nor shall he be denied the right to consult, and to be defended by, a legal practitioner of his choice. (2) Every person who is arrested and detained in custody shall be produced before the nearest magistrate within a period of twenty-four hours of such arrest... (3) Nothing in clauses (1) and (2) shall apply to any person who for the time being is an enemy alien; or to any person who is arrested or detained under any law providing for preventive detention.",
        "summary": "Establishes vital procedural safeguards upon arrest: right to be informed of grounds, right to consult/be defended by a lawyer of choice, and mandatory production before a magistrate within 24 hours.",
        "importance_score": 0.98,
        "relevance_reason": "Article 22 directly governs police arrest mechanics, remand procedures, legal representation, and preventive detention laws under criminal procedure.",
        "keywords": [
            "Protection against Arrest", "Grounds of Arrest", "Right to Legal Practitioner",
            "Production before Magistrate", "24 Hour Rule", "Preventive Detention", "Arrest Safeguards"
        ],
        "legal_principles": [
            "Right to Counsel", "Habeas Corpus", "Magisterial Scrutiny of Arrest"
        ],
        "criminal_law_relevance": [
            "Mandating police to inform arrested person of exact charges",
            "Ensuring immediate access to defense advocate",
            "Preventing illegal police detention beyond 24 hours without judicial order"
        ],
        "possible_related_bns_topics": [
            "BNS 127 (Wrongful Confinement)", "Offences by Public Servants"
        ],
        "graph_relationships": {
            "related_bns_sections": ["BNS 127", "BNS 198"],
            "related_bnss_topics": ["Arrest memo procedure", "Police remand limits under BNSS"],
            "related_bsa_topics": ["Confession during police custody"],
            "related_offence_categories": ["Arrest & Custody", "Preventive Detention", "Police Procedure"],
            "related_constitutional_principles": ["Right to Counsel", "Magisterial Scrutiny"],
            "possible_landmark_cases": [
                "D.K. Basu v. State of West Bengal",
                "Arnesh Kumar v. State of Bihar",
                "Joginder Kumar v. State of UP"
            ],
            "recommended_evidence_types": ["Arrest Memo", "Inquest Report", "CCTV Footage"]
        },
        "graph_metadata": {
            "node_type": "ConstitutionArticle",
            "source": "Constitution of India",
            "jurisdiction": "India"
        }
    },
    {
        "article_number": "Article 23",
        "title": "Prohibition of traffic in human beings and forced labour",
        "part": "Part III - Fundamental Rights",
        "chapter": "Right against Exploitation",
        "category": "Anti-Trafficking & Human Exploitation",
        "full_text": "(1) Traffic in human beings and begar and other similar forms of forced labour are prohibited and any contravention of this provision shall be an offence punishable in accordance with law.",
        "summary": "Prohibits human trafficking, forced labour, and commercial sexual exploitation, mandating penal statutes to punish violators.",
        "importance_score": 0.94,
        "relevance_reason": "Constitutional authority underlying criminal provisions prohibiting human trafficking, forced prostitution, bonded labour, and organ trafficking.",
        "keywords": [
            "Human Trafficking", "Prohibition of Begar", "Forced Labour", "Commercial Sexual Exploitation", "Human Exploitation"
        ],
        "legal_principles": [
            "Prohibition of Exploitation", "Human Dignity"
        ],
        "criminal_law_relevance": [
            "Prosecuting commercial human trafficking and sexual exploitation",
            "Enforcing penal sanctions against forced labour and debt bondage"
        ],
        "possible_related_bns_topics": [
            "BNS 143 (Trafficking of Person)", "BNS 144 (Exploitation of Trafficked Person)"
        ],
        "graph_relationships": {
            "related_bns_sections": ["BNS 143", "BNS 144", "BNS 137"],
            "related_bnss_topics": ["Anti-trafficking police unit investigation"],
            "related_bsa_topics": ["Victim testimony in trafficking cases"],
            "related_offence_categories": ["Trafficking Offences", "Exploitation Offences"],
            "related_constitutional_principles": ["Prohibition of Exploitation"],
            "possible_landmark_cases": [
                "PUCL v. Union of India",
                "Gaurav Jain v. Union of India",
                "Bachpan Bachao Andolan v. Union of India"
            ],
            "recommended_evidence_types": ["Witness Statement", "Rescue Memo", "Financial Record"]
        },
        "graph_metadata": {
            "node_type": "ConstitutionArticle",
            "source": "Constitution of India",
            "jurisdiction": "India"
        }
    },
    {
        "article_number": "Article 24",
        "title": "Prohibition of employment of children in factories, etc.",
        "part": "Part III - Fundamental Rights",
        "chapter": "Right against Exploitation",
        "category": "Child Protection & Labor Laws",
        "full_text": "No child below the age of fourteen years shall be employed to work in any factory or mine or engaged in any other hazardous employment.",
        "summary": "Prohibits employment of children under 14 in factories, mines, or hazardous work, forming the foundation of penal statutes against child labor and minor endangerment.",
        "importance_score": 0.88,
        "relevance_reason": "Provides direct constitutional foundation for criminal prosecution of employers exploiting child labor in hazardous occupations.",
        "keywords": [
            "Child Labour Prohibition", "Hazardous Employment", "Child Protection", "Minor Endangerment"
        ],
        "legal_principles": [
            "Child Rights", "Protection of Vulnerable Groups"
        ],
        "criminal_law_relevance": [
            "Criminal prosecution of child labor employers",
            "Rescuing exploited child laborers"
        ],
        "possible_related_bns_topics": [
            "BNS 143 (Trafficking of Person)", "BNS 95 (Employing child for begging)"
        ],
        "graph_relationships": {
            "related_bns_sections": ["BNS 143", "BNS 95"],
            "related_bnss_topics": ["Child rescue and rehabilitation procedure"],
            "related_bsa_topics": ["Age determination certificates"],
            "related_offence_categories": ["Child Offences", "Labour Exploitation"],
            "related_constitutional_principles": ["Protection of Vulnerable Groups"],
            "possible_landmark_cases": [
                "M.C. Mehta v. State of Tamil Nadu",
                "Bachpan Bachao Andolan v. Union of India"
            ],
            "recommended_evidence_types": ["Birth Certificate", "Medical Inspection Report"]
        },
        "graph_metadata": {
            "node_type": "ConstitutionArticle",
            "source": "Constitution of India",
            "jurisdiction": "India"
        }
    },
    {
        "article_number": "Article 32",
        "title": "Remedies for enforcement of rights conferred by this Part",
        "part": "Part III - Fundamental Rights",
        "chapter": "Right to Constitutional Remedies",
        "category": "Constitutional Remedies & Writs",
        "full_text": "(1) The right to move the Supreme Court by appropriate proceedings for the enforcement of the rights conferred by this Part is guaranteed. (2) The Supreme Court shall have power to issue directions or orders or writs, including writs in the nature of habeas corpus, mandamus, prohibition, quo warranto and certiorari, whichever may be appropriate...",
        "summary": "Guarantees the right to approach the Supreme Court directly for enforcement of Fundamental Rights via constitutional writs like Habeas Corpus, Mandamus, and Certiorari.",
        "importance_score": 0.98,
        "relevance_reason": "Article 32 is the principal constitutional remedy for securing release from illegal police custody (Habeas Corpus), seeking independent investigation, and enforcing fair trial rights.",
        "keywords": [
            "Constitutional Remedies", "Writs", "Habeas Corpus", "Mandamus", "Certiorari",
            "Illegal Detention", "Fundamental Rights Enforcement", "Supreme Court Jurisdiction"
        ],
        "legal_principles": [
            "Constitutional Guarantee", "Habeas Corpus", "Judicial Review"
        ],
        "criminal_law_relevance": [
            "Securing immediate release of persons in illegal police custody via Habeas Corpus",
            "Ordering independent CBI/SIT investigations in high-profile criminal cases",
            "Quashing unconstitutional criminal proceedings or state harassment"
        ],
        "possible_related_bns_topics": [
            "BNS 127 (Wrongful Confinement)"
        ],
        "graph_relationships": {
            "related_bns_sections": ["BNS 127"],
            "related_bnss_topics": ["Inherent powers of Supreme Court and High Courts"],
            "related_bsa_topics": ["Judicial notice of fundamental rights violations"],
            "related_offence_categories": ["Constitutional Writs", "Illegal Detention", "State Accountability"],
            "related_constitutional_principles": ["Judicial Review", "Habeas Corpus"],
            "possible_landmark_cases": [
                "Sunil Batra v. Delhi Administration",
                "Khatri v. State of Bihar",
                "Nilabati Behera v. State of Orissa"
            ],
            "recommended_evidence_types": ["Affidavit", "Custody Register", "Police Logbook"]
        },
        "graph_metadata": {
            "node_type": "ConstitutionArticle",
            "source": "Constitution of India",
            "jurisdiction": "India"
        }
    },
    {
        "article_number": "Article 39A",
        "title": "Equal justice and free legal aid",
        "part": "Part IV - Directive Principles of State Policy",
        "chapter": "Directive Principles",
        "category": "Legal Aid & Access to Justice",
        "full_text": "The State shall secure that the operation of the legal system promotes justice, on a basis of equal opportunity, and shall, in particular, provide free legal aid, by suitable legislation or schemes or in any other way, to ensure that opportunities for securing justice are not denied to any citizen by reason of economic or other disabilities.",
        "summary": "Mandates the State to provide free legal aid and ensure that access to justice is not denied to any citizen due to economic or other disabilities.",
        "importance_score": 0.90,
        "relevance_reason": "Guarantees free legal representation to indigent criminal defendants and victims, fulfilling the constitutional requirement of a fair criminal trial under Article 21.",
        "keywords": [
            "Equal Justice", "Free Legal Aid", "Access to Justice", "Legal Representation", "Indigent Defense"
        ],
        "legal_principles": [
            "Access to Justice", "Equal Opportunity in Trial", "State Legal Aid Mandate"
        ],
        "criminal_law_relevance": [
            "Providing court-appointed defense advocate for accused unable to afford counsel",
            "Victim legal assistance schemes during criminal trials"
        ],
        "possible_related_bns_topics": [
            "General criminal defense rights"
        ],
        "graph_relationships": {
            "related_bns_sections": ["BNS 80", "BNS 63", "BNS 101"],
            "related_bnss_topics": ["Free legal aid provisions under BNSS"],
            "related_bsa_topics": ["Burden of proof assistance"],
            "related_offence_categories": ["Legal Aid", "Indigent Defense", "Trial Rights"],
            "related_constitutional_principles": ["Access to Justice", "Equal Opportunity"],
            "possible_landmark_cases": [
                "Hussainara Khatoon v. State of Bihar",
                "Suk Das v. Union Territory of Arunachal Pradesh"
            ],
            "recommended_evidence_types": ["Income Certificate", "Legal Aid Appointment Order"]
        },
        "graph_metadata": {
            "node_type": "ConstitutionArticle",
            "source": "Constitution of India",
            "jurisdiction": "India"
        }
    },
    {
        "article_number": "Article 51A",
        "title": "Fundamental duties (Clause e - Dignity of Women)",
        "part": "Part IVA - Fundamental Duties",
        "chapter": "Fundamental Duties",
        "category": "Fundamental Duties & Women Dignity",
        "full_text": "It shall be the duty of every citizen of India... (e) to promote harmony and the spirit of common brotherhood amongst all the people of India transcending religious, linguistic and regional or sectional diversities; to renounce practices derogatory to the dignity of women.",
        "summary": "Enshrines the fundamental duty of every citizen to renounce practices derogatory to the dignity of women, reinforcing penal legislation against sexual harassment and domestic cruelty.",
        "importance_score": 0.85,
        "relevance_reason": "Serves as a constitutional directive upholding dignity of women in interpretations of sexual harassment, dowry harassment, and domestic abuse penal provisions.",
        "keywords": [
            "Fundamental Duties", "Dignity of Women", "Renounce Practices Derogatory to Women", "Gender Respect"
        ],
        "legal_principles": [
            "Dignity of Women", "Civic Responsibility"
        ],
        "criminal_law_relevance": [
            "Judicial interpretation of offences affecting female modesty and dignity",
            "Reinforcing social policy behind anti-dowry and anti-cruelty penal statutes"
        ],
        "possible_related_bns_topics": [
            "BNS 80 (Dowry Death)", "BNS 85 (Cruelty)", "BNS 74 (Outraging Modesty)", "BNS 79 (Insulting Modesty)"
        ],
        "graph_relationships": {
            "related_bns_sections": ["BNS 80", "BNS 85", "BNS 74", "BNS 79"],
            "related_bnss_topics": ["Protection of female victims during trial"],
            "related_bsa_topics": ["Presumption of female witness credibility"],
            "related_offence_categories": ["Women Offences", "Dignity Offences"],
            "related_constitutional_principles": ["Dignity of Women"],
            "possible_landmark_cases": [
                "Vishaka v. State of Rajasthan",
                "State of UP v. Ram Swarup"
            ],
            "recommended_evidence_types": ["Witness Statement", "Audio Recording", "WhatsApp Chats"]
        },
        "graph_metadata": {
            "node_type": "ConstitutionArticle",
            "source": "Constitution of India",
            "jurisdiction": "India"
        }
    },
    {
        "article_number": "Article 72",
        "title": "Power of President to grant pardons, etc., and to suspend, remit or commute sentences in certain cases",
        "part": "Part V - The Union",
        "chapter": "Chapter I - The Executive",
        "category": "Executive Clemency & Clemency Jurisprudence",
        "full_text": "(1) The President shall have the power to grant pardons, reprieves, respites or remissions of punishment or to suspend, remit or commute the sentence of any person convicted of any offence (a) in all cases where the punishment or sentence is by a Court Martial; (b) in all cases where the punishment or sentence is for an offence against any law relating to a matter to which the executive power of the Union extends; (c) in all cases where the sentence is a sentence of death.",
        "summary": "Empowers the President of India to grant executive clemency, pardons, remissions, or commutations of criminal sentences, including capital punishment.",
        "importance_score": 0.92,
        "relevance_reason": "Governs post-conviction executive clemency jurisprudence, judicial review of mercy petitions, and death sentence commutation for undue delay.",
        "keywords": [
            "Pardoning Power", "Executive Clemency", "Remission of Sentence", "Commutation of Death Penalty", "Mercy Petition"
        ],
        "legal_principles": [
            "Executive Clemency", "Judicial Review of Mercy Petitions", "Humanitarian Remission"
        ],
        "criminal_law_relevance": [
            "Pardon and remission petitions filed by convicts facing life imprisonment or death sentence",
            "Judicial review of arbitrary rejection or delay in mercy petitions"
        ],
        "possible_related_bns_topics": [
            "BNS 103 (Punishment for Murder)"
        ],
        "graph_relationships": {
            "related_bns_sections": ["BNS 103"],
            "related_bnss_topics": ["Execution of death sentence under BNSS"],
            "related_bsa_topics": ["Official record of mercy petition"],
            "related_offence_categories": ["Executive Clemency", "Capital Offences"],
            "related_constitutional_principles": ["Executive Clemency", "Judicial Review"],
            "possible_landmark_cases": [
                "Kehar Singh v. Union of India",
                "Shatrughan Chauhan v. Union of India",
                "Epuru Sudhakar v. Govt of AP"
            ],
            "recommended_evidence_types": ["Mercy Petition Record", "Prison Conduct Report"]
        },
        "graph_metadata": {
            "node_type": "ConstitutionArticle",
            "source": "Constitution of India",
            "jurisdiction": "India"
        }
    },
    {
        "article_number": "Article 136",
        "title": "Special leave to appeal by the Supreme Court",
        "part": "Part V - The Union",
        "chapter": "Chapter IV - The Union Judiciary",
        "category": "Supreme Court Appellate Jurisdiction",
        "full_text": "(1) Notwithstanding anything in this Chapter, the Supreme Court may, in its discretion, grant special leave to appeal from any judgment, decree, determination, sentence or order in any cause or matter passed or made by any court or tribunal in the territory of India.",
        "summary": "Grants plenary discretionary power to the Supreme Court to entertain Special Leave Petitions (SLP) against any judgment, sentence, or order of any court or tribunal in India.",
        "importance_score": 0.95,
        "relevance_reason": "Article 136 is the primary constitutional avenue for appealing High Court convictions, acquittals, or bail rejections directly to the Supreme Court.",
        "keywords": [
            "Special Leave Petition", "SLP", "Appellate Jurisdiction", "Supreme Court Review", "Gross Injustice"
        ],
        "legal_principles": [
            "Plenary Appellate Power", "Correction of Miscarriage of Justice"
        ],
        "criminal_law_relevance": [
            "Filing SLPs against High Court criminal judgments, bail orders, or conviction affirmations",
            "Correcting grave misappreciation of evidence by lower criminal courts"
        ],
        "possible_related_bns_topics": [
            "Appeals under all major BNS offences"
        ],
        "graph_relationships": {
            "related_bns_sections": ["BNS 80", "BNS 85", "BNS 63", "BNS 101"],
            "related_bnss_topics": ["Appellate procedure under BNSS"],
            "related_bsa_topics": ["Re-appreciation of evidence on appeal"],
            "related_offence_categories": ["Supreme Court Appeals", "Criminal Remedies"],
            "related_constitutional_principles": ["Plenary Appellate Power"],
            "possible_landmark_cases": [
                "Pritam Singh v. State",
                "P.S.R. Sadhanantham v. Arunachalam"
            ],
            "recommended_evidence_types": ["Trial Court Record", "High Court Judgment"]
        },
        "graph_metadata": {
            "node_type": "ConstitutionArticle",
            "source": "Constitution of India",
            "jurisdiction": "India"
        }
    },
    {
        "article_number": "Article 141",
        "title": "Law declared by Supreme Court to be binding on all courts",
        "part": "Part V - The Union",
        "chapter": "Chapter IV - The Union Judiciary",
        "category": "Precedent Doctrine & Stare Decisis",
        "full_text": "The law declared by the Supreme Court shall be binding on all courts within the territory of India.",
        "summary": "Enshrines the doctrine of precedent (*stare decisis*), making all legal interpretations and ratios decidendi of the Supreme Court binding on all subordinate courts across India.",
        "importance_score": 0.98,
        "relevance_reason": "Article 141 gives binding precedent authority to Supreme Court interpretations of criminal statutes (BNS/IPC), evidence standards, and trial procedures.",
        "keywords": [
            "Law Declared by Supreme Court", "Binding Precedent", "Stare Decisis", "Ratio Decidendi", "Judicial Consistency"
        ],
        "legal_principles": [
            "Stare Decisis", "Binding Precedent", "Judicial Discipline"
        ],
        "criminal_law_relevance": [
            "Ensuring subordinate trial and appellate courts follow Supreme Court precedents on bail, evidence, and sentencing",
            "Standardizing interpretation of penal sections across all High Courts"
        ],
        "possible_related_bns_topics": [
            "All BNS statutory sections"
        ],
        "graph_relationships": {
            "related_bns_sections": ["BNS 80", "BNS 85", "BNS 63", "BNS 101"],
            "related_bnss_topics": ["Binding trial procedure precedents"],
            "related_bsa_topics": ["Binding evidence appreciation guidelines"],
            "related_offence_categories": ["Precedent Doctrine", "Judicial Precedent"],
            "related_constitutional_principles": ["Stare Decisis", "Binding Precedent"],
            "possible_landmark_cases": [
                "Bengal Immunity Co. v. State of Bihar",
                "Union of India v. Raghubir Singh"
            ],
            "recommended_evidence_types": ["Supreme Court Judgment Record"]
        },
        "graph_metadata": {
            "node_type": "ConstitutionArticle",
            "source": "Constitution of India",
            "jurisdiction": "India"
        }
    },
    {
        "article_number": "Article 142",
        "title": "Enforcement of decrees and orders of Supreme Court and orders as to discovery, etc.",
        "part": "Part V - The Union",
        "chapter": "Chapter IV - The Union Judiciary",
        "category": "Inherent Powers & Complete Justice",
        "full_text": "(1) The Supreme Court in the exercise of its jurisdiction may pass such decree or make such order as is necessary for doing complete justice in any cause or matter pending before it...",
        "summary": "Grants plenary inherent power to the Supreme Court to pass any decree or order necessary for doing 'complete justice' in any cause or criminal matter before it.",
        "importance_score": 0.96,
        "relevance_reason": "Empowers the Supreme Court to issue binding guidelines (e.g. Vishaka guidelines, D.K. Basu arrest guidelines), quash non-compoundable criminal cases on settlement, or grant relief beyond strict statutory boundaries to prevent injustice.",
        "keywords": [
            "Complete Justice", "Inherent Powers of Supreme Court", "Quashing Criminal Proceedings", "Judicial Guidelines"
        ],
        "legal_principles": [
            "Complete Justice", "Inherent Judicial Power"
        ],
        "criminal_law_relevance": [
            "Quashing criminal cases involving non-compoundable offences based on genuine marital/matrimonial settlement",
            "Issuing binding guidelines for police arrest and victim compensation"
        ],
        "possible_related_bns_topics": [
            "BNS 85 (Cruelty)", "BNS 351 (Criminal Intimidation)"
        ],
        "graph_relationships": {
            "related_bns_sections": ["BNS 85", "BNS 351"],
            "related_bnss_topics": ["Quashing criminal FIR under inherent powers"],
            "related_bsa_topics": ["Admissibility under court directions"],
            "related_offence_categories": ["Complete Justice", "Criminal Remedies"],
            "related_constitutional_principles": ["Complete Justice"],
            "possible_landmark_cases": [
                "Gian Singh v. State of Punjab",
                "B.S. Joshi v. State of Haryana",
                "Supreme Court Bar Association v. Union of India"
            ],
            "recommended_evidence_types": ["Settlement Compromise Deed", "Affidavit of Victim"]
        },
        "graph_metadata": {
            "node_type": "ConstitutionArticle",
            "source": "Constitution of India",
            "jurisdiction": "India"
        }
    },
    {
        "article_number": "Article 226",
        "title": "Power of High Courts to issue certain writs",
        "part": "Part VI - The States",
        "chapter": "Chapter V - The High Courts in the States",
        "category": "High Court Writ Jurisdiction & Quashing Powers",
        "full_text": "(1) Notwithstanding anything in Article 32, every High Court shall have power, throughout the territories in relation to which it exercises jurisdiction, to issue to any person or authority... directions, orders or writs, including writs in the nature of habeas corpus, mandamus, prohibition, quo warranto and certiorari...",
        "summary": "Empowers High Courts to issue constitutional writs for the enforcement of Fundamental Rights and any other legal right, serving as the cornerstone for challenging illegal arrests, quashing malicious FIRs, and granting protective bail.",
        "importance_score": 0.98,
        "relevance_reason": "Article 226 is the primary writ remedy invoked in High Courts to quash malicious criminal prosecutions, grant interim protection against arrest, and issue Habeas Corpus for unlawful police detention.",
        "keywords": [
            "High Court Writ Jurisdiction", "Quashing FIR", "Habeas Corpus", "Certiorari", "Protection against Arrest", "Malicious Prosecution"
        ],
        "legal_principles": [
            "Judicial Review", "High Court Writ Jurisdiction", "Protection against Malicious Prosecution"
        ],
        "criminal_law_relevance": [
            "Quashing malicious FIRs and criminal chargesheets under Article 226 read with Section 482 BNSS",
            "Issuing writs of Habeas Corpus for illegal detention by police or private individuals",
            "Granting interim protection against coercive action during investigation"
        ],
        "possible_related_bns_topics": [
            "All BNS criminal statutory sections"
        ],
        "graph_relationships": {
            "related_bns_sections": ["BNS 80", "BNS 85", "BNS 63", "BNS 101"],
            "related_bnss_topics": ["Section 482 BNSS inherent powers", "Quashing of FIR"],
            "related_bsa_topics": ["Evidentiary threshold for quashing"],
            "related_offence_categories": ["High Court Writs", "Quashing FIR", "Illegal Custody"],
            "related_constitutional_principles": ["Judicial Review", "Writ Jurisdiction"],
            "possible_landmark_cases": [
                "State of Haryana v. Bhajan Lal",
                "Neeharika Infrastructure v. State of Maharashtra",
                "Arnab Goswami v. State of Maharashtra"
            ],
            "recommended_evidence_types": ["FIR Copy", "Writ Petition Affidavit", "Alibi Record"]
        },
        "graph_metadata": {
            "node_type": "ConstitutionArticle",
            "source": "Constitution of India",
            "jurisdiction": "India"
        }
    }
]


def generate_jsons():
    print(f"Generating {len(CONSTITUTION_ARTICLES)} criminal law constitutional article JSONs...")
    for art in CONSTITUTION_ARTICLES:
        filename = f"{art['article_number'].replace(' ', '_')}.json"
        filepath = OUTPUT_DIR / filename
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(art, f, indent=2, ensure_ascii=False)
        print(f"  [+] Created: {filepath.name}")

    print("\n" + "=" * 80)
    print(f"SUCCESS: Generated {len(CONSTITUTION_ARTICLES)} Constitutional Article JSONs in {OUTPUT_DIR}")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    generate_jsons()
