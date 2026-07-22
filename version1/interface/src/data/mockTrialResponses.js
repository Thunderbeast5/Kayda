/**
 * Mock Trial Responses for the frontend-only courtroom demo.
 * Used as a fallback when the Python backend (server.py) is not running.
 */

const prosecutorResponses = [
  {
    text: "Your Honor, the prosecution submits that the evidence on record clearly establishes a prima facie case against the accused. The testimony of PW-1, corroborated by the forensic report marked as Exhibit P-7, demonstrates beyond reasonable doubt that the accused was present at the scene during the material time. We urge the court to consider the chain of circumstantial evidence in its totality.",
    citations: ["State v. Ramakrishnan (2019) SC", "IPC Section 379"]
  },
  {
    text: "Objection, Your Honor. The learned defense counsel is attempting to introduce character evidence that is neither relevant nor admissible under Section 53 of the Indian Evidence Act. The accused's reputation in the community has no bearing on the specific allegations of criminal breach of trust detailed in the charge sheet.",
    citations: ["Indian Evidence Act, Section 53", "Bhagwan Singh v. State (2001)"]
  },
  {
    text: "Your Honor, with the Court's permission, the prosecution wishes to draw attention to the contradictions in the statement of DW-2. During cross-examination, the defense witness stated that the accused was at the temple between 9 PM and 11 PM. However, the CCTV footage from the adjacent grocery store — admitted as Exhibit P-12 — clearly shows the accused's vehicle parked near the complainant's residence at 10:17 PM.",
    citations: ["Exhibit P-12 (CCTV Footage)", "CrPC Section 161"]
  },
  {
    text: "The prosecution rests its case on the strength of the documentary evidence, oral testimony of five prosecution witnesses, and the expert opinion of the forensic examiner. We submit that the cumulative weight of this evidence satisfies the burden of proof required under criminal law, and the accused must be held liable for the offences charged.",
    citations: ["Sharad Birdhichand v. State of Maharashtra (1984) SC"]
  }
];

const defenseResponses = [
  {
    text: "Your Honor, the defense respectfully submits that the prosecution has failed to establish the essential ingredient of mens rea. The accused's actions, as described by PW-1, are equally consistent with an innocent explanation. The principle laid down in Woolmington v. DPP is clear — the burden of proof rests squarely on the prosecution, and any reasonable doubt must benefit the accused.",
    citations: ["Woolmington v. DPP (1935)", "IPC Section 378 - Definition of Theft"]
  },
  {
    text: "Objection, Your Honor. The prosecution is relying on a confession allegedly made to a police officer, which is inadmissible under Section 25 of the Indian Evidence Act. Furthermore, the alleged confession was obtained during custodial interrogation without the presence of a lawyer, in violation of Article 22(1) of the Constitution.",
    citations: ["Indian Evidence Act, Section 25", "Article 22(1), Constitution of India"]
  },
  {
    text: "Your Honor, the defense produces DW-3, Shri Prakash Narayan Gawai, who will testify that the accused was present at the village community hall from 8:30 PM to midnight on the date of the alleged incident. This alibi, supported by the register maintained by the hall committee — marked as Exhibit D-4 — creates a reasonable doubt regarding the prosecution's timeline of events.",
    citations: ["Exhibit D-4 (Community Hall Register)", "Kali Ram v. State of Himachal Pradesh (1973) SC"]
  },
  {
    text: "Your Honor, the defense submits that the investigation in this case was conducted in a perfunctory manner. The IO failed to collect fingerprint evidence from the point of entry, did not record the statements of two material witnesses identified in the FIR, and the seizure memo was prepared without independent witnesses as required under Section 100 CrPC. These lapses fatally undermine the prosecution's case.",
    citations: ["CrPC Section 100", "Tomaso Bruno v. State of UP (2015) SC"]
  }
];

const judgeResponses = [
  {
    text: "The objection raised by the defense counsel is sustained. The prosecution shall refrain from referencing the prior conviction of the accused as it falls outside the scope of the present proceedings and is inadmissible under the established principles of evidence law. The jury, if present, is directed to disregard the last remark.",
    citations: []
  },
  {
    text: "This Court notes the submissions of both parties. Given the complexity of the forensic evidence presented, I am inclined to adjourn the matter to allow both sides to file written arguments on the admissibility of Exhibit P-12. The next hearing is fixed for the 15th of the coming month. Both counsels are directed to serve copies of their written submissions at least 48 hours before the next date.",
    citations: []
  },
  {
    text: "After careful consideration of the oral arguments presented by both the prosecution and the defense, and having examined the documentary evidence on record, this Court is of the prima facie view that a case for further inquiry exists. The charges under Sections 379 and 454 IPC are hereby framed against the accused. The accused is asked — do you plead guilty or claim trial?",
    citations: ["CrPC Section 228"]
  }
];

/**
 * Returns a mock response based on simple keyword matching.
 * Falls back to a random response if no keywords match.
 */
export function getMockResponse(userInput, userRole) {
  const input = userInput.toLowerCase();

  // Determine which agent should respond (opposite of user's role)
  let respondingAgent, responses, displayName;

  if (userRole === "defense") {
    respondingAgent = "prosecutor";
    responses = prosecutorResponses;
    displayName = "Public Prosecutor";
  } else if (userRole === "prosecutor") {
    respondingAgent = "defense";
    responses = defenseResponses;
    displayName = "Defense Counsel";
  } else {
    // Judge role — alternate between prosecutor and defense
    const coin = Math.random() > 0.5;
    respondingAgent = coin ? "prosecutor" : "defense";
    responses = coin ? prosecutorResponses : defenseResponses;
    displayName = coin ? "Public Prosecutor" : "Defense Counsel";
  }

  // Simple keyword-based selection
  let selectedResponse;
  if (input.includes("objection") || input.includes("inadmissible")) {
    selectedResponse = responses[1]; // objection-related
  } else if (input.includes("evidence") || input.includes("exhibit") || input.includes("forensic")) {
    selectedResponse = responses[2]; // evidence-related
  } else if (input.includes("witness") || input.includes("testimony")) {
    selectedResponse = responses[0]; // testimony-related
  } else {
    // Random selection
    selectedResponse = responses[Math.floor(Math.random() * responses.length)];
  }

  // Optionally add a judge follow-up
  const includeJudge = Math.random() > 0.5 && userRole !== "judge";

  const result = {
    success: true,
    agent: respondingAgent === "prosecutor" ? "Prosecutor" : "Accused",
    response: selectedResponse.text,
    citations: selectedResponse.citations
  };

  return result;
}
