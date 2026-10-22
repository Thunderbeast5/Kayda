/**
 * Seed Cases — Starter Indian legal case scenarios for the Moot Court game.
 * Each case follows the Case model schema for Firestore.
 */

export const SEED_CASES = [
  {
    case_id: "case_001",
    title: "The Missing Contract",
    description:
      "A high-value commercial contract between two firms disappears from the registrar's office days before a court hearing. The plaintiff alleges the defendant orchestrated its removal to evade liability for a ₹2.5 crore defaulted payment. Key witnesses have conflicting accounts of who last accessed the document vault.",
    difficulty: "MEDIUM",
    category: "FRAUD",
    facts:
      "M/s Sunrise Exports Pvt. Ltd. entered into a supply contract dated 12.03.2023 with M/s Delta Traders for the supply of textile goods worth ₹2,50,00,000. The contract was duly registered at the Sub-Registrar's Office, Andheri. On 15.09.2023, when Sunrise Exports sought to enforce the contract in the Bombay High Court, the original registered copy was found missing from the registrar's vault. CCTV footage from 10.09.2023 shows an unidentified individual entering the registrar's office after hours. Delta Traders' managing director, Mr. Rakesh Mehra, was seen in the vicinity on the same date. Delta Traders denies all allegations and claims the contract was never validly executed.",
    evidence: [
      {
        id: "E1",
        type: "DOCUMENT",
        content: "Certified copy of the supply contract dated 12.03.2023 (Exhibit P-1)",
        description: "Photocopy of the original registered contract retained by the plaintiff",
      },
      {
        id: "E2",
        type: "FORENSIC",
        content: "CCTV footage from Sub-Registrar's Office dated 10.09.2023 showing unauthorized entry at 22:47 hrs (Exhibit P-5)",
        description: "Security camera recording from the night the document went missing",
      },
      {
        id: "E3",
        type: "STATEMENT",
        content: "Statement of Mr. Vijay Kulkarni, clerk at Sub-Registrar's Office, confirming the contract was present during his last audit on 08.09.2023 (Exhibit P-3)",
        description: "Witness testimony from the registrar's office staff",
      },
      {
        id: "E4",
        type: "DOCUMENT",
        content: "Bank statements showing ₹75,00,000 partial payment from Delta Traders to Sunrise Exports on 20.04.2023 (Exhibit P-4)",
        description: "Financial evidence corroborating the existence of the contract",
      },
    ],
    applicable_laws: [
      "Section 420 IPC — Cheating and dishonestly inducing delivery of property",
      "Section 468 IPC — Forgery for purpose of cheating",
      "Section 471 IPC — Using as genuine a forged document",
      "Section 201 IPC — Causing disappearance of evidence of offence",
      "Indian Evidence Act, Section 65 — Secondary evidence",
    ],
    participants: {
      appellant: "M/s Sunrise Exports Pvt. Ltd.",
      respondent: "M/s Delta Traders & Mr. Rakesh Mehra",
      judge: "Hon'ble Justice S. K. Nair",
    },
  },
  {
    case_id: "case_002",
    title: "State vs. Sharma — The Warehouse Robbery",
    description:
      "Armed robbery of a pharmaceutical warehouse resulting in theft of controlled substances worth ₹4.8 crore. The accused, a former warehouse supervisor, was identified by an eyewitness but claims he was coerced into confessing during custodial interrogation. Critical questions arise about the admissibility of the confession and the reliability of identification evidence.",
    difficulty: "HARD",
    category: "CRIMINAL",
    facts:
      "On the night of 28.07.2023, three masked individuals broke into the Medilife Pharma warehouse in Sector 18, Gurugram. The night watchman, Mr. Hari Prasad, was assaulted and tied up. Controlled substances including Schedule H drugs valued at ₹4,80,00,000 were stolen. CCTV systems had been disabled 30 minutes prior to the break-in. Mr. Arun Sharma, who had served as warehouse supervisor until his termination on 01.06.2023, was arrested on 05.08.2023 based on an eyewitness identification by Mr. Hari Prasad. During police custody, Sharma allegedly confessed and led police to a portion of the stolen goods recovered from a godown in Faridabad. Sharma's counsel claims the confession was coerced and the identification was tainted by a suggestive lineup procedure.",
    evidence: [
      {
        id: "E1",
        type: "TESTIMONY",
        content: "Eyewitness testimony of Mr. Hari Prasad (PW-1), night watchman, identifying the accused by his voice and a distinctive tattoo on his left forearm visible when a mask slipped during the assault",
        description: "Primary identification witness — knew the accused from his employment",
      },
      {
        id: "E2",
        type: "FORENSIC",
        content: "Forensic report confirming the CCTV system was disabled using the supervisor's master access code, last assigned to the accused (Exhibit P-8)",
        description: "Digital forensic evidence linking the accused to CCTV tampering",
      },
      {
        id: "E3",
        type: "DOCUMENT",
        content: "Panchnama and seizure memo of recovered drugs from Faridabad godown dated 07.08.2023 (Exhibit P-6)",
        description: "Recovery of stolen goods allegedly based on accused's disclosure",
      },
      {
        id: "E4",
        type: "STATEMENT",
        content: "Retracted confession of Mr. Arun Sharma recorded during police custody on 06.08.2023",
        description: "Confession later retracted by accused citing coercion",
      },
    ],
    applicable_laws: [
      "Section 392 IPC — Robbery",
      "Section 397 IPC — Robbery with attempt to cause death or grievous hurt",
      "Section 411 IPC — Dishonestly receiving stolen property",
      "Section 25 Indian Evidence Act — Confession to police officer inadmissible",
      "Section 27 Indian Evidence Act — Information leading to discovery",
      "NDPS Act, Section 22 — Contravention in relation to psychotropic substances",
      "Article 22(1) Constitution — Right to consult a legal practitioner",
    ],
    participants: {
      appellant: "State of Haryana",
      respondent: "Mr. Arun Sharma",
      judge: "Hon'ble Justice P. R. Deshpande",
    },
  },
  {
    case_id: "case_003",
    title: "Tenant Dispute — Kumar vs. Landlord Association",
    description:
      "A tenant of 15 years faces eviction from a rent-controlled premises after the landlord association claims the building needs demolition for structural safety. The tenant alleges the eviction is a pretext to redevelop the property for commercial gain. The case turns on the interpretation of 'bonafide need' and the tenant's right to alternative accommodation.",
    difficulty: "EASY",
    category: "PROPERTY",
    facts:
      "Mr. Dinesh Kumar has been a tenant at Flat No. 302, Shanti Apartments, Dadar, Mumbai, since 2009 under a registered lease agreement with a monthly rent of ₹8,500. The Shanti Apartments Landlord Association issued a notice on 01.02.2024 requiring all tenants to vacate within 6 months, citing a structural audit report declaring the building 'unsafe for habitation.' Mr. Kumar obtained an independent structural assessment from a RERA-certified engineer, which classified the building as 'repairable with moderate investment.' The landlord association has since obtained BMC permissions for demolition and reconstruction of a 12-storey commercial-residential complex. Mr. Kumar and 7 other tenants have refused to vacate, demanding alternate accommodation or compensation at current market rates (approximately ₹1.5 crore per flat).",
    evidence: [
      {
        id: "E1",
        type: "DOCUMENT",
        content: "Registered lease agreement dated 15.01.2009 between Mr. Kumar and the original landlord, Mr. S. R. Joshi (Exhibit P-1)",
        description: "Original tenancy document establishing long-term tenancy",
      },
      {
        id: "E2",
        type: "DOCUMENT",
        content: "Structural audit report by M/s SafeBuild Engineers commissioned by the landlord association, declaring building 'unsafe' (Exhibit D-1)",
        description: "Landlord's structural assessment supporting demolition",
      },
      {
        id: "E3",
        type: "DOCUMENT",
        content: "Independent structural assessment by Dr. A. K. Patel (RERA-certified), classifying building as 'repairable with moderate investment of ₹45 lakhs' (Exhibit P-2)",
        description: "Counter-report challenging the demolition necessity",
      },
      {
        id: "E4",
        type: "DOCUMENT",
        content: "BMC approved building plan for new 12-storey commercial-residential complex with estimated project value of ₹180 crore (Exhibit P-4)",
        description: "Evidence of commercial redevelopment intent",
      },
    ],
    applicable_laws: [
      "Maharashtra Rent Control Act, 1999 — Section 16 (Eviction on grounds of demolition)",
      "Maharashtra Rent Control Act, 1999 — Section 22 (Tenant's right to alternate accommodation)",
      "Transfer of Property Act, 1882 — Section 111 (Determination of lease)",
      "Article 21 Constitution — Right to shelter as part of right to life",
    ],
    participants: {
      appellant: "Mr. Dinesh Kumar & 7 Other Tenants",
      respondent: "Shanti Apartments Landlord Association",
      judge: "Hon'ble Justice M. L. Khanna",
    },
  },
  {
    case_id: "case_004",
    title: "Digital Privacy — Verma vs. Union of India",
    description:
      "A constitutional challenge against a government surveillance program that mass-collects citizens' digital communications metadata without judicial oversight. The petitioner, a journalist, argues this violates the fundamental right to privacy established in Puttaswamy. The government contends national security interests justify the program under reasonable restrictions.",
    difficulty: "HARD",
    category: "CONSTITUTIONAL",
    facts:
      "Ms. Priya Verma, an investigative journalist with The Independent Herald, filed a PIL in the Supreme Court after her sources within the intelligence community revealed the existence of 'Project Drishti' — a surveillance program operated by a central intelligence agency that collects metadata (call records, IP logs, location data, email headers) of all Indian mobile and internet users without individual warrants. The program has been operational since 2021 under an executive order. Ms. Verma's own communications were allegedly monitored after she published a series on defence procurement irregularities. The Union of India has neither confirmed nor denied the existence of Project Drishti but argues that any such program would be lawful under Section 69 of the IT Act and that disclosure of specific intelligence capabilities would endanger national security. Three former Supreme Court judges have submitted an amicus brief supporting the petitioner's right to privacy claims.",
    evidence: [
      {
        id: "E1",
        type: "DOCUMENT",
        content: "RTI response from Department of Telecommunications confirming 'data sharing agreements with intelligence agencies' without specifying scope (Exhibit P-1)",
        description: "Government acknowledgment of data-sharing with intelligence",
      },
      {
        id: "E2",
        type: "STATEMENT",
        content: "Affidavit of Mr. Anonymous Source (identity protected by court order) describing the technical architecture and scope of mass metadata collection (Exhibit P-3)",
        description: "Whistleblower testimony on surveillance program details",
      },
      {
        id: "E3",
        type: "DOCUMENT",
        content: "Amicus brief from three former Supreme Court judges citing K.S. Puttaswamy v. Union of India and international privacy jurisprudence (Exhibit P-5)",
        description: "Expert legal opinion supporting right to privacy",
      },
      {
        id: "E4",
        type: "DOCUMENT",
        content: "Government's sealed-cover affidavit claiming national security justification for surveillance capabilities (Exhibit R-1)",
        description: "Government's national security defense (partially sealed)",
      },
    ],
    applicable_laws: [
      "Article 21 Constitution — Right to Life and Personal Liberty (Right to Privacy)",
      "Article 19(1)(a) Constitution — Freedom of Speech and Expression",
      "Article 19(2) Constitution — Reasonable Restrictions on free speech",
      "Information Technology Act, 2000 — Section 69 (Power to intercept, monitor, decrypt)",
      "K.S. Puttaswamy v. Union of India (2017) — Right to Privacy as fundamental right",
      "Indian Telegraph Act, 1885 — Section 5(2) (Interception of messages)",
    ],
    participants: {
      appellant: "Ms. Priya Verma & The Independent Herald",
      respondent: "Union of India through Ministry of Home Affairs",
      judge: "Hon'ble Chief Justice & Constitution Bench",
    },
  },
];
