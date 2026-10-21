/**
 * Mock Evidence Data for the frontend-only Evidence Analyzer demo.
 * Contains sample FIR raw text and pre-computed structured facts.
 */

export const sampleCases = [
  {
    id: "fir_2024_005",
    filename: "FIR_2024_005_Theft_IPC379.pdf",
    label: "FIR No. 2024/005 — Theft (IPC 379)",
    description: "Complaint regarding theft of gold ornaments and cash from residential premises.",
    rawText: `FIRST INFORMATION REPORT
(Under Section 154 Cr.P.C.)

District: Pune City   P.S.: Shivajinagar   Year: 2024   FIR No.: 005   Date: 15/03/2024

1. Act(s) & Section(s): IPC Section 379, 454, 380

2. (a) Occurrence of offence:
   Day: Friday   Date from: 14/03/2024   Date to: 15/03/2024
   Time Period: Time from: 22:00 hrs   Time to: 06:30 hrs

   (b) Information received at P.S.:
   Date: 15/03/2024   Time: 08:15 hrs

   (c) General Diary Reference: Entry No. 47   Time: 08:15 hrs

3. Type of Information: Written

4. Place of Occurrence:
   (a) Direction and Distance from P.S.: 2.5 KM South-East
   (b) Address: Flat No. 302, Sunrise Apartments, Model Colony, Shivajinagar, Pune - 411016
   Beat No.: 07   Type: Residential Building

5. Complainant / Informant:
   (a) Name: Smt. Asha Rajendra Kulkarni
   (b) Father's / Husband's Name: Rajendra Vishwanath Kulkarni
   (c) Date / Year of Birth: 1975   Nationality: Indian
   (d) Passport No.: N/A
   (e) Occupation: Homemaker
   (f) Address: Flat No. 302, Sunrise Apartments, Model Colony, Shivajinagar, Pune - 411016

6. Details of Known / Suspected / Unknown Accused:
   Description: Unknown person(s)

7. Reasons for Delay in Reporting:
   The complainant discovered the theft only upon waking at 06:30 hrs on 15/03/2024.

8. Particulars of Properties Stolen / Involved:
   (i) Gold mangalsutra (approx. 25 grams, 22 carat) - Estimated value: Rs. 1,50,000
   (ii) Gold bangles, 2 nos. (approx. 40 grams total, 22 carat) - Estimated value: Rs. 2,40,000
   (iii) Gold earrings, 1 pair (approx. 8 grams, 22 carat) - Estimated value: Rs. 48,000
   (iv) Cash: Rs. 85,000 (kept in almirah drawer)
   (v) One Samsung Galaxy S23 mobile phone - Estimated value: Rs. 65,000
   Total Estimated Loss: Rs. 5,88,000 (Five Lakhs Eighty-Eight Thousand Only)

9. First Information Contents / Gist of FIR:

   I, Smt. Asha Rajendra Kulkarni, aged 49 years, resident of Flat No. 302, Sunrise
   Apartments, Model Colony, Shivajinagar, Pune, do hereby state the following:

   On 14/03/2024, my husband Shri Rajendra Kulkarni and I went to sleep at approximately
   22:00 hrs after locking the main door and all windows. Our two children were away at
   their respective hostels.

   When I woke up at approximately 06:30 hrs on 15/03/2024, I noticed that the bedroom
   window facing the rear balcony was open. The latch appeared to have been forced from
   outside. Upon checking the almirah in the bedroom, I found that the locker section was
   broken open.

   The following items were missing from the almirah:
   - My gold mangalsutra weighing approximately 25 grams
   - Two gold bangles weighing approximately 40 grams total
   - One pair of gold earrings weighing approximately 8 grams
   - Cash amount of Rs. 85,000/- which was kept in the drawer for household expenses

   Additionally, my Samsung Galaxy S23 mobile phone, which was kept on the bedside table
   for charging, was also missing.

   No other rooms in the flat appeared to have been disturbed. There were shoe marks
   visible near the rear balcony railing, suggesting that the unknown accused person(s)
   gained entry by climbing the drainpipe adjacent to the balcony.

   I suspect the theft occurred between 22:00 hrs on 14/03/2024 and 06:30 hrs on
   15/03/2024 while we were asleep.

   I request that an FIR be registered and the culprit(s) be apprehended at the earliest.

10. Action Taken:
    FIR registered u/s 379, 454, 380 IPC.
    Investigation taken up. Scene of crime visited. Forensic team summoned for
    fingerprint and shoe impression analysis.

    Sd/-
    PSI V.K. Patil
    Shivajinagar Police Station, Pune

Signature / Thumb Impression of the Complainant: Sd/- Asha Kulkarni
Date & Time of dispatch to the Court: 15/03/2024, 10:30 hrs`,

    facts: {
      who: {
        complainant: "Asha Rajendra Kulkarni",
        accused: ["Unknown person(s)"],
        victims: ["Asha Rajendra Kulkarni"]
      },
      incident: {
        summary: "Unknown person(s) entered Flat No. 302, Sunrise Apartments by forcing open the bedroom window latch from outside via the rear balcony drainpipe. Gold ornaments (mangalsutra, bangles, earrings), cash of Rs. 85,000, and a Samsung Galaxy S23 mobile phone were stolen from the almirah and bedside table while the complainant and her husband were asleep.",
        date: "14/03/2024 - 15/03/2024",
        time: "22:00 - 06:30",
        place: "Flat No. 302, Sunrise Apartments, Model Colony, Shivajinagar, Pune - 411016"
      },
      property: {
        cash: "Rs. 85,000",
        gold: "Gold mangalsutra (25g, 22ct) + 2 Gold bangles (40g total, 22ct) + Gold earrings pair (8g, 22ct)",
        documents: null,
        vehicles: [],
        other_property: [
          "Samsung Galaxy S23 mobile phone (estimated Rs. 65,000)"
        ],
        estimated_loss: "Rs. 5,88,000"
      },
      sections: ["IPC 379", "IPC 454", "IPC 380"]
    }
  },
  {
    id: "fir_2024_112",
    filename: "FIR_2024_112_CyberFraud_IT66C.pdf",
    label: "FIR No. 2024/112 — Cyber Fraud (IT Act 66C/66D)",
    description: "Online banking fraud via phishing — unauthorized transfer of funds.",
    rawText: `FIRST INFORMATION REPORT
(Under Section 154 Cr.P.C.)

District: Mumbai Suburban   P.S.: Andheri   Year: 2024   FIR No.: 112   Date: 22/06/2024

1. Act(s) & Section(s): IPC 420, IT Act Section 66C, 66D

2. (a) Occurrence of offence:
   Day: Saturday   Date from: 20/06/2024   Date to: 20/06/2024
   Time Period: Time from: 14:30 hrs   Time to: 14:45 hrs

   (b) Information received at P.S.:
   Date: 22/06/2024   Time: 11:00 hrs

3. Type of Information: Written

4. Place of Occurrence:
   (a) Address: Cyber Space (online transaction initiated from Flat 18-B,
       Sai Paradise, Lokhandwala Complex, Andheri West, Mumbai - 400053)

5. Complainant / Informant:
   (a) Name: Shri Arjun Vikram Deshmukh
   (b) Father's Name: Vikram Suresh Deshmukh
   (c) Date / Year of Birth: 1988   Nationality: Indian
   (d) Occupation: Software Engineer, TechNova Solutions Pvt. Ltd.
   (e) Address: Flat 18-B, Sai Paradise, Lokhandwala Complex, Andheri West,
       Mumbai - 400053

6. Details of Known / Suspected / Unknown Accused:
   Unknown person(s) operating from unknown location using
   Phone No.: +91-89XX-XXXX47 (suspected spoofed number)
   Email: support.refund@hdfc-alerts.co.in (fraudulent domain)

7. Particulars of Properties:
   (i) Rs. 2,47,500 transferred from HDFC Bank Savings Account
       No. XXXX-XXXX-6891 to unknown beneficiary account
   (ii) Rs. 1,12,000 transferred via UPI to unknown VPA
   Total Loss: Rs. 3,59,500

8. First Information Contents:

   I, Shri Arjun Vikram Deshmukh, age 36, do state as follows:

   On 20/06/2024 at approximately 14:30 hrs, I received a phone call from a person
   claiming to be a "Senior Fraud Prevention Officer" from HDFC Bank. The caller
   stated that my debit card had been compromised in a data breach and that I needed
   to verify my identity immediately to prevent unauthorized transactions.

   The caller provided my full name, last four digits of my card, and my registered
   email address - details which made me believe this was a genuine call.

   The caller directed me to install a "secure verification app" (which turned out
   to be a screen-sharing application). Once installed, the caller asked me to open
   my HDFC Bank mobile banking app and enter my credentials.

   Within minutes, I received two SMS alerts:
   - Rs. 2,47,500 debited via NEFT to an unknown account
   - Rs. 1,12,000 debited via UPI to an unknown VPA

   I immediately disconnected the call and contacted HDFC Bank's customer care.
   The bank confirmed the transactions were processed and advised me to file a
   police complaint. I also reported the incident to the National Cyber Crime
   Reporting Portal (cybercrime.gov.in), Complaint No.: NCRP/2024/MH/06-1847.

   Sd/- Arjun Deshmukh`,

    facts: {
      who: {
        complainant: "Arjun Vikram Deshmukh",
        accused: ["Unknown person(s) - Phone: +91-89XX-XXXX47, Email: support.refund@hdfc-alerts.co.in"],
        victims: ["Arjun Vikram Deshmukh"]
      },
      incident: {
        summary: "The complainant received a fraudulent phone call from a person impersonating an HDFC Bank Fraud Prevention Officer. The caller used personal details (name, card digits, email) to establish trust, then directed the victim to install a screen-sharing application and open mobile banking. Rs. 2,47,500 was transferred via NEFT and Rs. 1,12,000 via UPI to unknown beneficiary accounts, totaling Rs. 3,59,500 in losses.",
        date: "20/06/2024",
        time: "14:30 - 14:45",
        place: "Cyber Space - initiated from Flat 18-B, Sai Paradise, Lokhandwala Complex, Andheri West, Mumbai - 400053"
      },
      property: {
        cash: "Rs. 3,59,500 (total unauthorized transfers)",
        gold: null,
        documents: "NCRP Complaint No.: NCRP/2024/MH/06-1847",
        vehicles: [],
        other_property: [],
        estimated_loss: "Rs. 3,59,500"
      },
      sections: ["IPC 420", "IT Act 66C", "IT Act 66D"]
    }
  },
  {
    id: "fir_2024_078",
    filename: "FIR_2024_078_Assault_IPC323.pdf",
    label: "FIR No. 2024/078 — Assault & Criminal Intimidation",
    description: "Assault by known accused during property boundary dispute.",
    rawText: `FIRST INFORMATION REPORT
(Under Section 154 Cr.P.C.)

District: Nagpur Rural   P.S.: Hingna   Year: 2024   FIR No.: 078   Date: 05/05/2024

1. Act(s) & Section(s): IPC 323, 504, 506

2. (a) Occurrence of offence:
   Day: Sunday   Date: 05/05/2024
   Time: 09:30 hrs

   (b) Information received at P.S.:
   Date: 05/05/2024   Time: 11:00 hrs

3. Place of Occurrence:
   Agricultural land, Survey No. 47/2, Village Besa, Taluka Hingna,
   District Nagpur - adjacent to the boundary wall of the accused's land.

4. Complainant / Informant:
   (a) Name: Shri Ramesh Ganpat Wankhede
   (b) Age: 55 years   Occupation: Farmer
   (c) Address: House No. 89, Village Besa, Taluka Hingna, District Nagpur

5. Details of Accused:
   (a) Name: Shri Sunil Mahadeo Thakre, Age: 42 years
   (b) Address: House No. 112, Village Besa, Taluka Hingna, District Nagpur
   (c) Relation to Complainant: Neighbouring land-owner

6. First Information Contents:

   I, Shri Ramesh Ganpat Wankhede, age 55 years, farmer, resident of Village
   Besa, do hereby state:

   On 05/05/2024 at approximately 09:30 hrs, I was working on my agricultural
   land (Survey No. 47/2) near the boundary wall that separates my land from
   the land of the accused, Shri Sunil Mahadeo Thakre.

   The accused approached me and started abusing me in filthy language regarding
   the placement of the boundary wall. He alleged that I had encroached upon
   approximately 2 feet of his land, which is completely false as the boundary
   was demarcated by the Talathi office in 2019.

   When I tried to explain and show him the demarcation records, the accused
   became violent. He punched me on the left side of my face and kicked me
   in the abdomen, causing me to fall to the ground. He then picked up a
   wooden stick and struck me on my left arm.

   The accused then threatened me saying "Agar tu is zameen ko nahi chhodega
   to main tujhe aur tere poore khandaan ko dekh lunga" (Translation: "If you
   do not vacate this land, I will deal with you and your entire family.")

   Witnesses present:
   - Shri Prakash Narayan Gawai (neighbouring farmer)
   - Smt. Sunita Ramesh Wankhede (complainant's wife)

   I sustained injuries on my face (swelling on left cheek), abdomen (pain),
   and left arm (bruise). I was treated at Primary Health Centre, Hingna.
   Medical certificate obtained.

   Sd/- Ramesh Wankhede`,

    facts: {
      who: {
        complainant: "Ramesh Ganpat Wankhede",
        accused: ["Sunil Mahadeo Thakre"],
        victims: ["Ramesh Ganpat Wankhede"]
      },
      incident: {
        summary: "The accused Sunil Mahadeo Thakre assaulted the complainant Ramesh Ganpat Wankhede during a boundary dispute over agricultural land (Survey No. 47/2). The accused punched the complainant on the face, kicked him in the abdomen, and struck him with a wooden stick on the left arm. The accused also used abusive language and threatened the complainant and his family. The complainant sustained injuries to the face, abdomen, and left arm, and was treated at Primary Health Centre, Hingna.",
        date: "05/05/2024",
        time: "09:30",
        place: "Agricultural land, Survey No. 47/2, Village Besa, Taluka Hingna, District Nagpur"
      },
      property: {
        cash: null,
        gold: null,
        documents: "Medical certificate from PHC Hingna; Talathi demarcation records (2019)",
        vehicles: [],
        other_property: [],
        estimated_loss: null
      },
      sections: ["IPC 323", "IPC 504", "IPC 506"]
    }
  }
];
