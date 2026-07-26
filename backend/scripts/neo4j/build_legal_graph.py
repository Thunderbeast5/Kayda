"""
build_legal_graph.py  –  Complete Legal Knowledge Graph Builder
================================================================
Creates a full legal knowledge graph covering ALL 571 IPC sections
with every meaningful relationship:

  1. (BNSSection) -[:REPLACES]->      (IPCSection)  — from bns.csv
  2. (IPCSection) -[:REPLACED_BY]->   (BNSSection)  — reverse
  3. (IPCSection) -[:CO_CHARGED_WITH]->(IPCSection)  — both apply in same incident
  4. (IPCSection) -[:ESCALATES_TO]->  (IPCSection)  — combined crime = graver offence
  5. (IPCSection) -[:ABETS]->         (IPCSection)  — abetment/conspiracy links
  6. (IPCSection) -[:AGGRAVATED_BY]-> (IPCSection)  — aggravated form of base offence
  7. (IPCSection) -[:PROCEDURAL_FOR]->  (IPCSection) — attempt / preparation links

Usage:
    python scripts/build_legal_graph.py            # build (safe, no delete)
    python scripts/build_legal_graph.py --wipe     # wipe ALL nodes first, then build
"""

import csv, os, sys
from pathlib import Path
from dotenv import load_dotenv
from neo4j import GraphDatabase

# ── Config ────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
# .env lives at backend/.env (two levels up from scripts/neo4j/)
_env_candidates = [
    BASE_DIR.parent / ".env",          # scripts/.env  (legacy)
    BASE_DIR.parent.parent / ".env",   # backend/.env  (correct)
    Path(".env"),
]
ENV_PATH = next((p for p in _env_candidates if p.exists()), None)
DATA_DIR = BASE_DIR.parent.parent.parent / "data" / "update_combine_Dataset"
IPC_CSV  = DATA_DIR / "ipc.csv"
BNS_CSV  = DATA_DIR / "bns.csv"

load_dotenv(ENV_PATH) if ENV_PATH else load_dotenv()
NEO4J_URI      = os.getenv("NEO4J_URI")
NEO4J_USER     = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

if not all([NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD]):
    raise EnvironmentError("Missing NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD in backend/.env")

# ══════════════════════════════════════════════════════════════════════════════
# RELATIONSHIP MAP  — Format: (sec_A, sec_B, REL_TYPE, note)
#
# REL_TYPE options:
#   CO_CHARGED_WITH  → both apply independently in same incident (bidirectional)
#   ESCALATES_TO     → A+B together = graver offence C (directional)
#   ABETS            → A is abetment/conspiracy for B (directional)
#   AGGRAVATED_BY    → B is aggravated/enhanced form of A (directional)
#   PROCEDURAL_FOR   → A is attempt/preparation of B (directional)
# ══════════════════════════════════════════════════════════════════════════════

RELATIONSHIPS = [

    # ──────────────────────────────────────────────────────────────────────────
    # CHAPTER IV — ABETMENT (107–120B)
    # Every major offence can be abetted; abetment sections link to main offences
    # ──────────────────────────────────────────────────────────────────────────
    ("107",  "302",  "ABETS", "Abetment of murder"),
    ("107",  "376",  "ABETS", "Abetment of rape"),
    ("107",  "395",  "ABETS", "Abetment of dacoity"),
    ("107",  "392",  "ABETS", "Abetment of robbery"),
    ("107",  "363",  "ABETS", "Abetment of kidnapping"),
    ("107",  "420",  "ABETS", "Abetment of cheating"),
    ("107",  "379",  "ABETS", "Abetment of theft"),
    ("109",  "302",  "ABETS", "Punishment of abetment — murder"),
    ("109",  "376",  "ABETS", "Punishment of abetment — rape"),
    ("114",  "302",  "CO_CHARGED_WITH", "Abettor present when murder committed"),
    ("114",  "392",  "CO_CHARGED_WITH", "Abettor present when robbery committed"),
    ("115",  "302",  "ABETS", "Abetment of offence punishable with death — murder"),
    ("116",  "302",  "ABETS", "Abetment of imprisonment offence — murder"),
    ("120A", "302",  "ABETS", "Criminal conspiracy definition — murder"),
    ("120A", "376",  "ABETS", "Criminal conspiracy definition — rape"),
    ("120A", "395",  "ABETS", "Criminal conspiracy definition — dacoity"),
    ("120B", "302",  "CO_CHARGED_WITH", "Criminal conspiracy to commit murder"),
    ("120B", "376",  "CO_CHARGED_WITH", "Criminal conspiracy to commit rape"),
    ("120B", "395",  "CO_CHARGED_WITH", "Criminal conspiracy to commit dacoity"),
    ("120B", "392",  "CO_CHARGED_WITH", "Criminal conspiracy to commit robbery"),
    ("120B", "363",  "CO_CHARGED_WITH", "Criminal conspiracy to commit kidnapping"),
    ("120B", "364A", "CO_CHARGED_WITH", "Criminal conspiracy for ransom kidnapping"),
    ("120B", "420",  "CO_CHARGED_WITH", "Criminal conspiracy to cheat"),
    ("120B", "468",  "CO_CHARGED_WITH", "Criminal conspiracy — forgery for cheating"),
    ("120B", "489A", "CO_CHARGED_WITH", "Criminal conspiracy — counterfeiting currency"),

    # ──────────────────────────────────────────────────────────────────────────
    # CHAPTER VI — OFFENCES AGAINST THE STATE (121–130)
    # ──────────────────────────────────────────────────────────────────────────
    ("121",  "120B", "CO_CHARGED_WITH", "Waging war + criminal conspiracy"),
    ("121",  "122",  "CO_CHARGED_WITH", "Waging war + collecting arms"),
    ("121A", "121",  "ABETS", "Conspiracy to wage war"),
    ("122",  "121",  "CO_CHARGED_WITH", "Collecting arms with intent to wage war"),
    ("124A", "153A", "CO_CHARGED_WITH", "Sedition + promoting enmity between groups"),
    ("124A", "120B", "CO_CHARGED_WITH", "Sedition + criminal conspiracy"),

    # ──────────────────────────────────────────────────────────────────────────
    # CHAPTER VIII — PUBLIC TRANQUILLITY (141–160)
    # ──────────────────────────────────────────────────────────────────────────
    ("141",  "147",  "AGGRAVATED_BY", "Unlawful assembly aggravated to rioting"),
    ("146",  "147",  "AGGRAVATED_BY", "Rioting — punishment section"),
    ("146",  "148",  "AGGRAVATED_BY", "Rioting aggravated by deadly weapon"),
    ("147",  "302",  "CO_CHARGED_WITH", "Murder during rioting"),
    ("147",  "326",  "CO_CHARGED_WITH", "Grievous hurt during rioting"),
    ("147",  "392",  "CO_CHARGED_WITH", "Robbery during rioting"),
    ("148",  "302",  "CO_CHARGED_WITH", "Murder while rioting with deadly weapon"),
    ("148",  "326",  "CO_CHARGED_WITH", "Grievous hurt while rioting with deadly weapon"),
    ("149",  "302",  "CO_CHARGED_WITH", "Common object — murder in unlawful assembly"),
    ("149",  "392",  "CO_CHARGED_WITH", "Common object — robbery in unlawful assembly"),
    ("149",  "395",  "CO_CHARGED_WITH", "Common object — dacoity in unlawful assembly"),
    ("153A", "295",  "CO_CHARGED_WITH", "Promoting enmity + defiling place of worship"),
    ("153A", "505",  "CO_CHARGED_WITH", "Promoting enmity + statements causing public mischief"),

    # ──────────────────────────────────────────────────────────────────────────
    # CHAPTER IX — PUBLIC SERVANTS (161–171)
    # ──────────────────────────────────────────────────────────────────────────
    ("166",  "167",  "CO_CHARGED_WITH", "Public servant disobeying law + framing false document"),
    ("166A", "376",  "CO_CHARGED_WITH", "Public servant disobeying law in rape investigation"),
    ("166B", "302",  "CO_CHARGED_WITH", "Non-treatment of victim leading to death"),
    ("167",  "192",  "CO_CHARGED_WITH", "Framing incorrect document + fabricating false evidence"),
    ("167",  "420",  "CO_CHARGED_WITH", "Framing false document + cheating"),
    ("170",  "419",  "CO_CHARGED_WITH", "Personating public servant + cheating by personation"),
    ("170",  "468",  "CO_CHARGED_WITH", "Personating public servant + forgery"),

    # ──────────────────────────────────────────────────────────────────────────
    # CHAPTER XI — FALSE EVIDENCE & OFFENCES AGAINST PUBLIC JUSTICE (191–229A)
    # ──────────────────────────────────────────────────────────────────────────
    ("191",  "193",  "AGGRAVATED_BY", "False evidence — punishment"),
    ("192",  "193",  "AGGRAVATED_BY", "Fabricating false evidence — punishment"),
    ("193",  "194",  "AGGRAVATED_BY", "False evidence aggravated — intent to convict for capital offence"),
    ("194",  "302",  "CO_CHARGED_WITH", "False evidence to get someone hanged + murder intent"),
    ("195A", "191",  "CO_CHARGED_WITH", "Threatening to give false evidence"),
    ("201",  "302",  "CO_CHARGED_WITH", "Causing disappearance of murder evidence"),
    ("201",  "376",  "CO_CHARGED_WITH", "Causing disappearance of rape evidence"),
    ("201",  "392",  "CO_CHARGED_WITH", "Causing disappearance of robbery evidence"),
    ("202",  "302",  "CO_CHARGED_WITH", "Omitting to give information of murder"),
    ("211",  "302",  "CO_CHARGED_WITH", "False charge of murder with intent to injure"),
    ("212",  "302",  "CO_CHARGED_WITH", "Harbouring murderer"),
    ("212",  "395",  "CO_CHARGED_WITH", "Harbouring dacoit"),
    ("216",  "302",  "CO_CHARGED_WITH", "Harbouring escaped murderer"),
    ("216A", "395",  "CO_CHARGED_WITH", "Harbouring robbers or dacoits"),
    ("217",  "302",  "CO_CHARGED_WITH", "Public servant shielding murderer"),
    ("218",  "302",  "CO_CHARGED_WITH", "Public servant framing false record to save murderer"),

    # ──────────────────────────────────────────────────────────────────────────
    # CHAPTER XII — COINS & STAMPS (230–263A)
    # ──────────────────────────────────────────────────────────────────────────
    ("231",  "239",  "AGGRAVATED_BY", "Counterfeiting coin — possession of counterfeited coin"),
    ("232",  "240",  "AGGRAVATED_BY", "Counterfeiting Indian coin — possession"),
    ("255",  "258",  "AGGRAVATED_BY", "Counterfeiting government stamp — sale of counterfeit stamp"),
    ("255",  "259",  "AGGRAVATED_BY", "Counterfeiting government stamp — possession"),
    ("489A", "489B", "AGGRAVATED_BY", "Counterfeiting currency — using counterfeit currency"),
    ("489A", "489C", "AGGRAVATED_BY", "Counterfeiting currency — possession of counterfeit"),
    ("489A", "489D", "AGGRAVATED_BY", "Counterfeiting currency — making machinery for it"),
    ("489B", "420",  "CO_CHARGED_WITH", "Using counterfeit currency + cheating"),
    ("489C", "489B", "CO_CHARGED_WITH", "Possessing counterfeit currency + using it"),

    # ──────────────────────────────────────────────────────────────────────────
    # CHAPTER XIV — PUBLIC HEALTH & SAFETY (268–294A)
    # ──────────────────────────────────────────────────────────────────────────
    ("269",  "270",  "AGGRAVATED_BY", "Negligent spreading of disease — malignant form"),
    ("279",  "304A", "ESCALATES_TO",  "Rash driving on public way escalates to causing death by negligence"),
    ("279",  "337",  "CO_CHARGED_WITH", "Rash driving + hurt to person"),
    ("279",  "338",  "CO_CHARGED_WITH", "Rash driving + grievous hurt"),
    ("279",  "302",  "CO_CHARGED_WITH", "Rash driving resulting in death charged as murder"),
    ("280",  "304A", "ESCALATES_TO",  "Rash navigation of vessel + death by negligence"),
    ("285",  "436",  "CO_CHARGED_WITH", "Dangerous use of fire + mischief by fire"),
    ("285",  "302",  "CO_CHARGED_WITH", "Dangerous use of fire causing death"),
    ("286",  "302",  "CO_CHARGED_WITH", "Dangerous use of explosive substance causing death"),
    ("286",  "326",  "CO_CHARGED_WITH", "Dangerous use of explosive causing grievous hurt"),

    # ──────────────────────────────────────────────────────────────────────────
    # CHAPTER XV — RELIGION (295–298)
    # ──────────────────────────────────────────────────────────────────────────
    ("295",  "295A", "AGGRAVATED_BY", "Defiling place of worship — deliberate insult to religion"),
    ("295",  "153A", "CO_CHARGED_WITH", "Defiling place of worship + promoting enmity"),
    ("295A", "153A", "CO_CHARGED_WITH", "Insulting religion + promoting enmity between groups"),
    ("295A", "505",  "CO_CHARGED_WITH", "Insulting religion + statements causing public mischief"),
    ("296",  "147",  "CO_CHARGED_WITH", "Disturbing religious assembly + rioting"),

    # ──────────────────────────────────────────────────────────────────────────
    # CHAPTER XVI — OFFENCES AGAINST HUMAN BODY (299–377)
    # ──────────────────────────────────────────────────────────────────────────

    # Homicide family
    ("299",  "302",  "AGGRAVATED_BY", "Culpable homicide — aggravated to murder"),
    ("299",  "304",  "AGGRAVATED_BY", "Culpable homicide not amounting to murder"),
    ("300",  "302",  "AGGRAVATED_BY", "Murder — punishment section"),
    ("302",  "307",  "CO_CHARGED_WITH", "Murder + attempt to murder (multiple victims)"),
    ("302",  "326",  "CO_CHARGED_WITH", "Murder + grievous hurt by dangerous weapon"),
    ("302",  "34",   "CO_CHARGED_WITH", "Murder — common intention"),
    ("302",  "120B", "CO_CHARGED_WITH", "Murder — criminal conspiracy"),
    ("302",  "149",  "CO_CHARGED_WITH", "Murder — common object of unlawful assembly"),
    ("302",  "392",  "CO_CHARGED_WITH", "Murder during robbery"),
    ("302",  "376",  "CO_CHARGED_WITH", "Murder after rape"),
    ("302",  "363",  "CO_CHARGED_WITH", "Murder of kidnapped person"),
    ("302",  "364A", "CO_CHARGED_WITH", "Murder in ransom kidnapping"),
    ("302",  "454",  "CO_CHARGED_WITH", "Murder during house break-in"),
    ("302",  "435",  "CO_CHARGED_WITH", "Murder + mischief by fire"),
    ("302",  "436",  "CO_CHARGED_WITH", "Murder + arson"),
    ("302",  "511",  "CO_CHARGED_WITH", "Attempt to commit offence punishable with death"),
    ("303",  "302",  "AGGRAVATED_BY", "Enhanced murder punishment for life-convict"),
    ("304",  "302",  "AGGRAVATED_BY", "Culpable homicide not murder — lesser form of 302"),
    ("304A", "279",  "CO_CHARGED_WITH", "Causing death by negligence + rash driving"),
    ("304A", "304",  "AGGRAVATED_BY", "Rash/negligent act causing death — lesser than culpable homicide"),
    ("304B", "498A", "CO_CHARGED_WITH", "Dowry death + dowry harassment"),
    ("304B", "306",  "CO_CHARGED_WITH", "Dowry death + abetment of suicide"),
    ("304B", "302",  "CO_CHARGED_WITH", "Dowry death investigated as murder"),
    ("305",  "306",  "AGGRAVATED_BY", "Abetment of suicide — by child or insane person"),
    ("306",  "498A", "CO_CHARGED_WITH", "Abetment of suicide + dowry harassment"),
    ("306",  "304B", "CO_CHARGED_WITH", "Abetment of suicide + dowry death"),
    ("307",  "302",  "CO_CHARGED_WITH", "Attempt to murder + murder (different victims)"),
    ("307",  "326",  "CO_CHARGED_WITH", "Attempt to murder + grievous hurt"),
    ("307",  "34",   "CO_CHARGED_WITH", "Attempt to murder — common intention"),
    ("307",  "120B", "CO_CHARGED_WITH", "Attempt to murder — conspiracy"),
    ("307",  "392",  "CO_CHARGED_WITH", "Attempt to murder during robbery"),
    ("307",  "376",  "CO_CHARGED_WITH", "Attempt to murder during rape"),
    ("308",  "304",  "AGGRAVATED_BY", "Attempt to commit culpable homicide"),
    ("309",  "306",  "CO_CHARGED_WITH", "Attempt to suicide + abetment"),

    # Miscarriage / child-related
    ("312",  "313",  "AGGRAVATED_BY", "Causing miscarriage — without woman's consent"),
    ("313",  "314",  "AGGRAVATED_BY", "Miscarriage without consent — death caused"),
    ("315",  "302",  "CO_CHARGED_WITH", "Preventing child being born alive + murder intent"),
    ("316",  "302",  "CO_CHARGED_WITH", "Causing death of quick unborn child + murder"),
    ("317",  "302",  "CO_CHARGED_WITH", "Exposing child + death caused"),
    ("363A", "363",  "AGGRAVATED_BY", "Kidnapping for begging — aggravated kidnapping"),
    ("369",  "363",  "AGGRAVATED_BY", "Kidnapping child to take property — aggravated"),

    # Hurt family
    ("319",  "321",  "AGGRAVATED_BY", "Hurt — voluntarily caused"),
    ("320",  "322",  "AGGRAVATED_BY", "Grievous hurt — voluntarily caused"),
    ("321",  "323",  "AGGRAVATED_BY", "Voluntarily causing hurt — punishment"),
    ("322",  "325",  "AGGRAVATED_BY", "Voluntarily causing grievous hurt — punishment"),
    ("323",  "34",   "CO_CHARGED_WITH", "Simple hurt — common intention"),
    ("323",  "324",  "AGGRAVATED_BY", "Simple hurt aggravated by dangerous weapon"),
    ("324",  "326",  "AGGRAVATED_BY", "Hurt by dangerous weapon aggravated to grievous hurt"),
    ("325",  "34",   "CO_CHARGED_WITH", "Grievous hurt — common intention"),
    ("325",  "326",  "AGGRAVATED_BY", "Grievous hurt aggravated by dangerous weapon"),
    ("326",  "302",  "CO_CHARGED_WITH", "Grievous hurt by weapon + murder"),
    ("326",  "34",   "CO_CHARGED_WITH", "Grievous hurt — common intention"),
    ("326",  "307",  "CO_CHARGED_WITH", "Grievous hurt + attempt to murder"),
    ("326",  "392",  "CO_CHARGED_WITH", "Grievous hurt during robbery"),
    ("326A", "326",  "AGGRAVATED_BY", "Acid attack — aggravated grievous hurt"),
    ("326A", "302",  "CO_CHARGED_WITH", "Acid attack + murder"),
    ("326A", "307",  "CO_CHARGED_WITH", "Acid attack + attempt to murder"),
    ("326B", "326A", "AGGRAVATED_BY", "Attempting to throw acid — lesser form of 326A"),
    ("327",  "392",  "CO_CHARGED_WITH", "Hurt to extort property — robbery element"),
    ("328",  "302",  "CO_CHARGED_WITH", "Administering drug + murder"),
    ("328",  "376",  "CO_CHARGED_WITH", "Administering drug to commit rape"),
    ("328",  "392",  "CO_CHARGED_WITH", "Administering drug for robbery"),
    ("329",  "386",  "CO_CHARGED_WITH", "Grievous hurt to extort + extortion by threat of death"),
    ("330",  "302",  "CO_CHARGED_WITH", "Hurt to extort confession + custodial death"),
    ("331",  "302",  "CO_CHARGED_WITH", "Grievous hurt to extort confession + custodial death"),
    ("332",  "353",  "CO_CHARGED_WITH", "Hurt to deter public servant + assault on public servant"),
    ("333",  "353",  "CO_CHARGED_WITH", "Grievous hurt to deter public servant"),

    # Wrongful restraint / confinement
    ("339",  "340",  "AGGRAVATED_BY", "Wrongful restraint aggravated to wrongful confinement"),
    ("340",  "343",  "AGGRAVATED_BY", "Wrongful confinement for 3+ days — aggravated"),
    ("343",  "344",  "AGGRAVATED_BY", "Wrongful confinement for 10+ days — further aggravated"),
    ("342",  "363",  "CO_CHARGED_WITH", "Wrongful confinement + kidnapping"),
    ("342",  "376",  "CO_CHARGED_WITH", "Wrongful confinement to commit rape"),
    ("342",  "392",  "CO_CHARGED_WITH", "Wrongful confinement during robbery"),
    ("347",  "384",  "CO_CHARGED_WITH", "Wrongful confinement for extortion + extortion"),
    ("348",  "330",  "CO_CHARGED_WITH", "Wrongful confinement to extort confession + hurt"),

    # Assault / Criminal force
    ("350",  "351",  "AGGRAVATED_BY", "Criminal force — assault"),
    ("351",  "352",  "AGGRAVATED_BY", "Assault — punishment"),
    ("352",  "323",  "CO_CHARGED_WITH", "Assault + simple hurt"),
    ("353",  "332",  "CO_CHARGED_WITH", "Assault on public servant + hurt to deter"),
    ("354",  "376",  "AGGRAVATED_BY", "Assault on woman with intent to outrage modesty — escalates to rape"),
    ("354",  "354A", "AGGRAVATED_BY", "Assault on woman — aggravated to sexual harassment"),
    ("354A", "376",  "CO_CHARGED_WITH", "Sexual harassment co-charged with rape"),
    ("354B", "354",  "AGGRAVATED_BY", "Assault to disrobe — aggravated form of 354"),
    ("354B", "376",  "CO_CHARGED_WITH", "Assault to disrobe + rape"),
    ("354C", "376",  "CO_CHARGED_WITH", "Voyeurism co-charged with rape"),
    ("354D", "376",  "CO_CHARGED_WITH", "Stalking co-charged with rape"),
    ("354D", "302",  "CO_CHARGED_WITH", "Stalking leading to murder"),
    ("355",  "354",  "AGGRAVATED_BY", "Assault to dishonour — aggravated form of 354"),

    # Kidnapping / Abduction / Trafficking
    ("359",  "360",  "AGGRAVATED_BY", "Kidnapping — from India"),
    ("359",  "361",  "AGGRAVATED_BY", "Kidnapping — from lawful guardianship"),
    ("361",  "363",  "AGGRAVATED_BY", "Kidnapping from guardianship — punishment"),
    ("362",  "363",  "CO_CHARGED_WITH", "Abduction co-charged with kidnapping"),
    ("363",  "302",  "CO_CHARGED_WITH", "Kidnapping + murder of victim"),
    ("363",  "376",  "CO_CHARGED_WITH", "Kidnapping + rape"),
    ("363",  "384",  "CO_CHARGED_WITH", "Kidnapping + extortion"),
    ("363",  "34",   "CO_CHARGED_WITH", "Kidnapping — common intention"),
    ("363",  "120B", "CO_CHARGED_WITH", "Kidnapping — criminal conspiracy"),
    ("364",  "302",  "CO_CHARGED_WITH", "Kidnapping to murder + murder"),
    ("364",  "363",  "AGGRAVATED_BY", "Kidnapping to murder — aggravated kidnapping"),
    ("364A", "302",  "CO_CHARGED_WITH", "Ransom kidnapping + murder"),
    ("364A", "363",  "AGGRAVATED_BY", "Ransom kidnapping — most aggravated form"),
    ("364A", "120B", "CO_CHARGED_WITH", "Ransom kidnapping — conspiracy"),
    ("365",  "363",  "AGGRAVATED_BY", "Kidnapping to confine secretly — aggravated"),
    ("366",  "363",  "AGGRAVATED_BY", "Kidnapping woman to compel marriage — aggravated"),
    ("366",  "376",  "CO_CHARGED_WITH", "Kidnapping for marriage + rape"),
    ("366A", "366",  "AGGRAVATED_BY", "Procuration of minor girl — aggravated 366"),
    ("367",  "363",  "AGGRAVATED_BY", "Kidnapping to cause grievous hurt — aggravated"),
    ("368",  "363",  "CO_CHARGED_WITH", "Concealing kidnapped person + kidnapping"),
    ("370",  "363",  "AGGRAVATED_BY", "Trafficking of person — aggravated kidnapping"),
    ("370",  "376",  "CO_CHARGED_WITH", "Trafficking + rape"),
    ("370",  "302",  "CO_CHARGED_WITH", "Trafficking + murder"),
    ("370A", "370",  "AGGRAVATED_BY", "Exploitation of trafficked person"),
    ("371",  "370",  "AGGRAVATED_BY", "Habitual dealing in slaves"),
    ("372",  "370",  "CO_CHARGED_WITH", "Selling minor for prostitution + trafficking"),
    ("373",  "372",  "CO_CHARGED_WITH", "Buying minor for prostitution"),
    ("374",  "370",  "CO_CHARGED_WITH", "Unlawful compulsory labour + trafficking"),

    # Rape / Sexual offences
    ("375",  "376",  "AGGRAVATED_BY", "Rape definition — punishment section"),
    ("376",  "302",  "CO_CHARGED_WITH", "Rape + murder"),
    ("376",  "307",  "CO_CHARGED_WITH", "Rape + attempt to murder"),
    ("376",  "34",   "CO_CHARGED_WITH", "Rape — common intention (gang rape element)"),
    ("376",  "120B", "CO_CHARGED_WITH", "Rape — criminal conspiracy"),
    ("376",  "363",  "CO_CHARGED_WITH", "Rape + kidnapping"),
    ("376",  "354",  "CO_CHARGED_WITH", "Rape + assault on woman"),
    ("376",  "328",  "CO_CHARGED_WITH", "Rape after administering stupefying drug"),
    ("376A", "376",  "AGGRAVATED_BY", "Rape causing death or persistent vegetative state"),
    ("376A", "302",  "CO_CHARGED_WITH", "Rape causing death + murder charge"),
    ("376AB","376A", "AGGRAVATED_BY", "Rape of woman under 12 — most severe"),
    ("376B", "498A", "CO_CHARGED_WITH", "Marital rape + dowry harassment"),
    ("376D", "376",  "AGGRAVATED_BY", "Gang rape — aggravated form of rape"),
    ("376D", "34",   "CO_CHARGED_WITH", "Gang rape — common intention"),
    ("376D", "120B", "CO_CHARGED_WITH", "Gang rape — criminal conspiracy"),
    ("376DA","376D", "AGGRAVATED_BY", "Gang rape of girl under 16"),
    ("376DB","376DA","AGGRAVATED_BY", "Gang rape of girl under 12 — most severe"),
    ("376E", "376",  "AGGRAVATED_BY", "Repeat rape offenders — enhanced punishment"),
    ("377",  "376",  "CO_CHARGED_WITH", "Unnatural offences co-charged with rape"),
    ("377",  "302",  "CO_CHARGED_WITH", "Unnatural offences + murder"),

    # ──────────────────────────────────────────────────────────────────────────
    # CHAPTER XVII — OFFENCES AGAINST PROPERTY (378–462)
    # ──────────────────────────────────────────────────────────────────────────

    # Theft family
    ("378",  "379",  "AGGRAVATED_BY", "Theft definition — punishment section"),
    ("379",  "380",  "AGGRAVATED_BY", "Theft aggravated — in building/tent/vessel"),
    ("379",  "381",  "AGGRAVATED_BY", "Theft aggravated — by clerk/servant"),
    ("379",  "382",  "AGGRAVATED_BY", "Theft aggravated — after preparation for hurt"),
    ("379",  "392",  "ESCALATES_TO",  "Theft + force = Robbery (390/392)"),
    ("379",  "411",  "CO_CHARGED_WITH", "Theft + receiving stolen property"),
    ("380",  "454",  "CO_CHARGED_WITH", "Theft in building + lurking house trespass"),
    ("382",  "392",  "CO_CHARGED_WITH", "Theft after preparation for hurt + robbery"),

    # Extortion family
    ("383",  "384",  "AGGRAVATED_BY", "Extortion definition — punishment"),
    ("384",  "385",  "CO_CHARGED_WITH", "Extortion + putting in fear of injury"),
    ("384",  "386",  "AGGRAVATED_BY", "Extortion aggravated — fear of death/grievous hurt"),
    ("386",  "387",  "AGGRAVATED_BY", "Extortion by fear of death — attempt form"),
    ("388",  "384",  "CO_CHARGED_WITH", "Extortion by threat of accusation"),
    ("389",  "388",  "CO_CHARGED_WITH", "Putting in fear of accusation for extortion"),
    ("384",  "363",  "CO_CHARGED_WITH", "Extortion + kidnapping"),
    ("384",  "302",  "CO_CHARGED_WITH", "Extortion + murder of victim"),
    ("384",  "120B", "CO_CHARGED_WITH", "Extortion — criminal conspiracy"),

    # Robbery / Dacoity family
    ("390",  "392",  "AGGRAVATED_BY", "Robbery definition — punishment"),
    ("391",  "395",  "AGGRAVATED_BY", "Dacoity definition — punishment"),
    ("392",  "302",  "CO_CHARGED_WITH", "Robbery + murder"),
    ("392",  "307",  "CO_CHARGED_WITH", "Robbery + attempt to murder"),
    ("392",  "326",  "CO_CHARGED_WITH", "Robbery + grievous hurt by weapon"),
    ("392",  "34",   "CO_CHARGED_WITH", "Robbery — common intention"),
    ("392",  "120B", "CO_CHARGED_WITH", "Robbery — criminal conspiracy"),
    ("392",  "363",  "CO_CHARGED_WITH", "Robbery + kidnapping"),
    ("393",  "392",  "PROCEDURAL_FOR", "Attempt to commit robbery"),
    ("394",  "392",  "AGGRAVATED_BY", "Robbery causing hurt — aggravated"),
    ("394",  "302",  "CO_CHARGED_WITH", "Robbery causing hurt + murder"),
    ("395",  "302",  "CO_CHARGED_WITH", "Dacoity + murder of victim"),
    ("395",  "392",  "AGGRAVATED_BY", "Dacoity — aggravated form of robbery"),
    ("396",  "395",  "ESCALATES_TO",  "Dacoity with murder — most aggravated"),
    ("396",  "302",  "CO_CHARGED_WITH", "Dacoity with murder — IPC 302 also charged"),
    ("397",  "392",  "AGGRAVATED_BY", "Robbery with attempt to cause death"),
    ("397",  "395",  "AGGRAVATED_BY", "Dacoity with attempt to cause death"),
    ("398",  "392",  "CO_CHARGED_WITH", "Robbery when armed with deadly weapon"),
    ("399",  "395",  "PROCEDURAL_FOR", "Making preparation to commit dacoity"),
    ("400",  "395",  "CO_CHARGED_WITH", "Belonging to dacoity gang"),
    ("402",  "395",  "PROCEDURAL_FOR", "Assembly for purpose of dacoity"),

    # Misappropriation / Trust
    ("403",  "406",  "AGGRAVATED_BY", "Dishonest misappropriation — aggravated to breach of trust"),
    ("405",  "406",  "AGGRAVATED_BY", "Criminal breach of trust — punishment"),
    ("406",  "420",  "CO_CHARGED_WITH", "Breach of trust + cheating"),
    ("406",  "467",  "CO_CHARGED_WITH", "Breach of trust + forgery of valuable security"),
    ("407",  "406",  "AGGRAVATED_BY", "Breach of trust — by carrier/wharfinger"),
    ("408",  "406",  "AGGRAVATED_BY", "Breach of trust — by clerk/servant"),
    ("409",  "406",  "AGGRAVATED_BY", "Breach of trust — by public servant/banker"),
    ("409",  "420",  "CO_CHARGED_WITH", "Public servant breach of trust + cheating"),
    ("409",  "120B", "CO_CHARGED_WITH", "Public servant breach of trust — conspiracy"),

    # Stolen property
    ("410",  "411",  "AGGRAVATED_BY", "Stolen property definition — receiving stolen property"),
    ("411",  "379",  "CO_CHARGED_WITH", "Receiving stolen property + theft"),
    ("411",  "392",  "CO_CHARGED_WITH", "Receiving stolen property from robbery"),
    ("412",  "411",  "AGGRAVATED_BY", "Receiving property from dacoity — aggravated"),
    ("413",  "411",  "AGGRAVATED_BY", "Habitually dealing in stolen property"),
    ("414",  "411",  "CO_CHARGED_WITH", "Assisting in concealment of stolen property"),

    # Cheating family
    ("415",  "417",  "AGGRAVATED_BY", "Cheating definition — punishment"),
    ("416",  "419",  "AGGRAVATED_BY", "Cheating by personation — punishment"),
    ("417",  "420",  "AGGRAVATED_BY", "Cheating aggravated — inducing delivery of property"),
    ("418",  "420",  "AGGRAVATED_BY", "Cheating where interest bound to protect — aggravated"),
    ("420",  "468",  "CO_CHARGED_WITH", "Cheating + forgery for cheating"),
    ("420",  "471",  "CO_CHARGED_WITH", "Cheating + using forged documents"),
    ("420",  "406",  "CO_CHARGED_WITH", "Cheating + criminal breach of trust"),
    ("420",  "120B", "CO_CHARGED_WITH", "Cheating — criminal conspiracy"),
    ("420",  "419",  "CO_CHARGED_WITH", "Cheating + cheating by personation"),
    ("420",  "467",  "CO_CHARGED_WITH", "Cheating + forgery of valuable security"),
    ("420",  "489B", "CO_CHARGED_WITH", "Cheating using counterfeit currency"),

    # Mischief family
    ("425",  "426",  "AGGRAVATED_BY", "Mischief definition — punishment"),
    ("426",  "427",  "AGGRAVATED_BY", "Mischief causing Rs.50+ damage — aggravated"),
    ("427",  "435",  "AGGRAVATED_BY", "Mischief aggravated — by fire/explosive Rs.100+"),
    ("435",  "436",  "AGGRAVATED_BY", "Mischief by fire/explosive — total destruction"),
    ("435",  "302",  "CO_CHARGED_WITH", "Mischief by fire causing death"),
    ("436",  "302",  "CO_CHARGED_WITH", "Arson + murder"),
    ("436",  "120B", "CO_CHARGED_WITH", "Arson — criminal conspiracy"),
    ("440",  "435",  "CO_CHARGED_WITH", "Mischief after preparation for causing death + fire mischief"),

    # Trespass / House-breaking family
    ("441",  "447",  "AGGRAVATED_BY", "Criminal trespass — punishment"),
    ("442",  "448",  "AGGRAVATED_BY", "House-trespass — punishment"),
    ("443",  "453",  "AGGRAVATED_BY", "Lurking house-trespass — punishment"),
    ("444",  "456",  "AGGRAVATED_BY", "Lurking house-trespass by night — punishment"),
    ("445",  "453",  "AGGRAVATED_BY", "House-breaking — punishment"),
    ("446",  "456",  "AGGRAVATED_BY", "House-breaking by night — punishment"),
    ("449",  "302",  "CO_CHARGED_WITH", "House-trespass to commit murder"),
    ("449",  "376",  "CO_CHARGED_WITH", "House-trespass to commit rape"),
    ("450",  "376",  "CO_CHARGED_WITH", "House-trespass to commit rape (punishable life)"),
    ("451",  "379",  "CO_CHARGED_WITH", "House-trespass to commit theft"),
    ("451",  "392",  "CO_CHARGED_WITH", "House-trespass + robbery"),
    ("452",  "302",  "CO_CHARGED_WITH", "House-trespass after preparation for hurt + murder"),
    ("454",  "302",  "CO_CHARGED_WITH", "Lurking house-trespass + murder"),
    ("454",  "376",  "CO_CHARGED_WITH", "Lurking house-trespass + rape"),
    ("454",  "379",  "CO_CHARGED_WITH", "Lurking house-trespass + theft"),
    ("455",  "302",  "CO_CHARGED_WITH", "Lurking house-trespass after preparation + murder"),
    ("457",  "380",  "CO_CHARGED_WITH", "Lurking house-trespass by night + theft"),
    ("457",  "376",  "CO_CHARGED_WITH", "Lurking house-trespass by night + rape"),
    ("458",  "302",  "CO_CHARGED_WITH", "Lurking house-trespass by night + grievous hurt/murder"),
    ("459",  "326",  "CO_CHARGED_WITH", "Grievous hurt during lurking trespass"),
    ("460",  "302",  "CO_CHARGED_WITH", "Death during house-breaking by one of several persons"),
    ("460",  "395",  "CO_CHARGED_WITH", "House-breaking by gang + dacoity"),

    # ──────────────────────────────────────────────────────────────────────────
    # CHAPTER XVIII — DOCUMENTS & FORGERY (463–489E)
    # ──────────────────────────────────────────────────────────────────────────
    ("463",  "465",  "AGGRAVATED_BY", "Forgery definition — punishment"),
    ("464",  "465",  "AGGRAVATED_BY", "Making false document — punishment"),
    ("465",  "466",  "AGGRAVATED_BY", "Forgery aggravated — of court records"),
    ("466",  "467",  "AGGRAVATED_BY", "Forgery of court record aggravated — valuable security/will"),
    ("467",  "468",  "AGGRAVATED_BY", "Forgery of will aggravated — for cheating"),
    ("468",  "420",  "CO_CHARGED_WITH", "Forgery for cheating + cheating"),
    ("468",  "471",  "CO_CHARGED_WITH", "Forgery for cheating + using forged document"),
    ("469",  "499",  "CO_CHARGED_WITH", "Forgery to harm reputation + defamation"),
    ("471",  "420",  "CO_CHARGED_WITH", "Using forged document + cheating"),
    ("471",  "467",  "CO_CHARGED_WITH", "Using forged valuable security"),
    ("474",  "471",  "CO_CHARGED_WITH", "Possessing forged document + using it"),
    ("477A", "406",  "CO_CHARGED_WITH", "Falsification of accounts + breach of trust"),
    ("477A", "420",  "CO_CHARGED_WITH", "Falsification of accounts + cheating"),

    # ──────────────────────────────────────────────────────────────────────────
    # CHAPTER XX — MARRIAGE OFFENCES (493–498A)
    # ──────────────────────────────────────────────────────────────────────────
    ("493",  "376",  "CO_CHARGED_WITH", "Cohabitation by deceit + rape"),
    ("494",  "495",  "AGGRAVATED_BY", "Bigamy aggravated — concealing former marriage"),
    ("497",  "376",  "CO_CHARGED_WITH", "Adultery + rape (historical — now read with 376)"),
    ("498",  "376",  "CO_CHARGED_WITH", "Enticing married woman + rape"),
    ("498A", "304B", "CO_CHARGED_WITH", "Dowry cruelty + dowry death"),
    ("498A", "306",  "CO_CHARGED_WITH", "Dowry cruelty + abetment of suicide"),
    ("498A", "302",  "CO_CHARGED_WITH", "Dowry cruelty investigated as murder"),
    ("498A", "323",  "CO_CHARGED_WITH", "Dowry cruelty + simple hurt"),
    ("498A", "325",  "CO_CHARGED_WITH", "Dowry cruelty + grievous hurt"),
    ("498A", "376B", "CO_CHARGED_WITH", "Dowry cruelty + marital rape"),

    # ──────────────────────────────────────────────────────────────────────────
    # CHAPTER XXI — DEFAMATION (499–502)
    # ──────────────────────────────────────────────────────────────────────────
    ("499",  "500",  "AGGRAVATED_BY", "Defamation definition — punishment"),
    ("499",  "469",  "CO_CHARGED_WITH", "Defamation + forgery to harm reputation"),
    ("499",  "505",  "CO_CHARGED_WITH", "Defamation + statements causing public mischief"),
    ("500",  "501",  "AGGRAVATED_BY", "Defamation — printing form"),
    ("501",  "502",  "AGGRAVATED_BY", "Printing defamation — sale of printed defamatory material"),

    # ──────────────────────────────────────────────────────────────────────────
    # CHAPTER XXII — CRIMINAL INTIMIDATION (503–510)
    # ──────────────────────────────────────────────────────────────────────────
    ("503",  "506",  "AGGRAVATED_BY", "Criminal intimidation definition — punishment"),
    ("506",  "507",  "AGGRAVATED_BY", "Criminal intimidation aggravated — anonymous threat"),
    ("503",  "384",  "CO_CHARGED_WITH", "Criminal intimidation + extortion"),
    ("503",  "302",  "CO_CHARGED_WITH", "Criminal intimidation as prelude to murder"),
    ("503",  "376",  "CO_CHARGED_WITH", "Criminal intimidation to commit rape"),
    ("504",  "506",  "CO_CHARGED_WITH", "Intentional insult + criminal intimidation"),
    ("505",  "153A", "CO_CHARGED_WITH", "Statements causing public mischief + promoting enmity"),
    ("505",  "295A", "CO_CHARGED_WITH", "Statements causing mischief + insulting religion"),
    ("509",  "354",  "CO_CHARGED_WITH", "Insulting modesty of woman + assault"),
    ("509",  "376",  "CO_CHARGED_WITH", "Insulting modesty + rape"),

    # ──────────────────────────────────────────────────────────────────────────
    # CHAPTER XXIII — ATTEMPTS (511)
    # ──────────────────────────────────────────────────────────────────────────
    ("511",  "302",  "PROCEDURAL_FOR", "Attempt to commit murder (when 307 doesn't apply)"),
    ("511",  "395",  "PROCEDURAL_FOR", "Attempt to commit dacoity"),
    ("511",  "376",  "PROCEDURAL_FOR", "Attempt to commit rape (when 376 doesn't apply)"),
    ("511",  "467",  "PROCEDURAL_FOR", "Attempt to commit forgery of valuable security"),

    # ──────────────────────────────────────────────────────────────────────────
    # CROSS-CHAPTER — COMMON INTENT & GENERAL SECTIONS
    # 34 (common intention) and 149 (common object) link to ALL major offences
    # ──────────────────────────────────────────────────────────────────────────
    ("34",   "302",  "CO_CHARGED_WITH", "Common intention — murder"),
    ("34",   "307",  "CO_CHARGED_WITH", "Common intention — attempt to murder"),
    ("34",   "326",  "CO_CHARGED_WITH", "Common intention — grievous hurt by weapon"),
    ("34",   "392",  "CO_CHARGED_WITH", "Common intention — robbery"),
    ("34",   "395",  "CO_CHARGED_WITH", "Common intention — dacoity"),
    ("34",   "376",  "CO_CHARGED_WITH", "Common intention — rape (gang rape)"),
    ("34",   "363",  "CO_CHARGED_WITH", "Common intention — kidnapping"),
    ("34",   "420",  "CO_CHARGED_WITH", "Common intention — cheating"),
    ("34",   "436",  "CO_CHARGED_WITH", "Common intention — arson"),
    ("34",   "454",  "CO_CHARGED_WITH", "Common intention — lurking house trespass"),
    ("149",  "302",  "CO_CHARGED_WITH", "Common object — murder in unlawful assembly"),
    ("149",  "307",  "CO_CHARGED_WITH", "Common object — attempt to murder"),
    ("149",  "326",  "CO_CHARGED_WITH", "Common object — grievous hurt"),
    ("149",  "392",  "CO_CHARGED_WITH", "Common object — robbery"),
    ("149",  "395",  "CO_CHARGED_WITH", "Common object — dacoity"),
    ("149",  "436",  "CO_CHARGED_WITH", "Common object — arson"),
]

# ── CSV Readers ───────────────────────────────────────────────────────────────
def read_ipc(path: Path) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            sec = str(row.get("Section", "")).strip()
            if not sec:
                continue
            rows.append({
                "section":     sec,
                "title":       str(row.get("Offense", "")).strip(),
                "description": str(row.get("Description", "")).strip(),
                "punishment":  str(row.get("Punishment", "")).strip(),
                "chapter":     str(row.get("Chapter", "")).strip(),
                "category":    str(row.get("Category", "")).strip(),
                "keywords":    str(row.get("Keywords", "")).strip(),
                "cognizable":  str(row.get("Cognizable", "")).strip(),
                "bailable":    str(row.get("Bailable", "")).strip(),
                "court":       str(row.get("Court", "")).strip(),
            })
    return rows


def read_bns(path: Path) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            sec = str(row.get("Section", "")).strip()
            if not sec:
                continue
            ipc_refs_raw = str(row.get("IPC_Section_Reference", "")).strip()
            ipc_refs = []
            if ipc_refs_raw and ipc_refs_raw != "-":
                ipc_refs = [r.strip() for r in ipc_refs_raw.split(",") if r.strip()]
            rows.append({
                "section":     sec,
                "title":       str(row.get("Title", "")).strip(),
                "description": str(row.get("Description", "")).strip(),
                "punishment":  str(row.get("Punishment", "")).strip(),
                "chapter":     str(row.get("Chapter", "")).strip(),
                "category":    str(row.get("Category", "")).strip(),
                "keywords":    str(row.get("Keywords", "")).strip(),
                "status":      str(row.get("Status", "")).strip(),
                "ipc_refs":    ipc_refs,
            })
    return rows


# ── Neo4j Functions ───────────────────────────────────────────────────────────
def wipe_graph(session):
    print("  Wiping IPCSection and BNSSection nodes only (preserving old graph)...")
    session.run("MATCH (n:IPCSection) DETACH DELETE n")
    session.run("MATCH (n:BNSSection) DETACH DELETE n")
    print("  Done.")


def create_constraints(session):
    session.run("CREATE CONSTRAINT ipc_unique IF NOT EXISTS FOR (n:IPCSection) REQUIRE n.section IS UNIQUE")
    session.run("CREATE CONSTRAINT bns_unique IF NOT EXISTS FOR (n:BNSSection) REQUIRE n.section IS UNIQUE")
    print("  Constraints ready.")


def ingest_ipc_nodes(session, rows: list[dict]) -> int:
    # Batch all rows in a single UNWIND query — one network round-trip instead of N
    batch = [
        {
            "section":     r["section"],
            "title":       r["title"],
            "description": r["description"],
            "punishment":  r["punishment"],
            "chapter":     r["chapter"],
            "category":    r["category"],
            "keywords":    r["keywords"],
            "cognizable":  r["cognizable"],
            "bailable":    r["bailable"],
            "court":       r["court"],
        }
        for r in rows
    ]
    session.run("""
        UNWIND $batch AS r
        MERGE (n:IPCSection {section: r.section})
        SET n.title=r.title, n.description=r.description, n.punishment=r.punishment,
            n.chapter=r.chapter, n.category=r.category, n.keywords=r.keywords,
            n.cognizable=r.cognizable, n.bailable=r.bailable, n.court=r.court, n.act='IPC'
    """, batch=batch)
    return len(batch)


def ingest_bns_nodes(session, rows: list[dict]) -> int:
    # Batch all rows in a single UNWIND query — one network round-trip instead of N
    batch = [
        {
            "section":     r["section"],
            "title":       r["title"],
            "description": r["description"],
            "punishment":  r["punishment"],
            "chapter":     r["chapter"],
            "category":    r["category"],
            "keywords":    r["keywords"],
            "status":      r["status"],
        }
        for r in rows
    ]
    session.run("""
        UNWIND $batch AS r
        MERGE (n:BNSSection {section: r.section})
        SET n.title=r.title, n.description=r.description, n.punishment=r.punishment,
            n.chapter=r.chapter, n.category=r.category, n.keywords=r.keywords,
            n.status=r.status, n.act='BNS'
    """, batch=batch)
    return len(batch)


def ingest_bns_ipc_links(session, bns_rows: list[dict]) -> int:
    # Flatten BNS->IPC pairs and batch in one UNWIND query
    pairs = [
        {"bns_sec": r["section"], "ipc_sec": ipc_ref, "status": r["status"]}
        for r in bns_rows
        for ipc_ref in r["ipc_refs"]
    ]
    if not pairs:
        return 0
    session.run("""
        UNWIND $pairs AS p
        MATCH (b:BNSSection {section: p.bns_sec})
        MERGE (i:IPCSection {section: p.ipc_sec})
        MERGE (b)-[r1:REPLACES]->(i)    SET r1.status = p.status
        MERGE (i)-[r2:REPLACED_BY]->(b) SET r2.status = p.status
    """, pairs=pairs)
    return len(pairs)


def ingest_relationships(session, mapping: list[tuple]) -> dict:
    counts = {"CO_CHARGED_WITH": 0, "ESCALATES_TO": 0, "ABETS": 0,
              "AGGRAVATED_BY": 0, "PROCEDURAL_FOR": 0}
    # Group by relationship type and batch each group in one UNWIND query
    from collections import defaultdict
    by_type = defaultdict(list)
    for (sec_a, sec_b, rel_type, note) in mapping:
        by_type[rel_type].append({"sec_a": sec_a, "sec_b": sec_b, "note": note})

    for rel_type, pairs in by_type.items():
        if rel_type == "CO_CHARGED_WITH":
            session.run(f"""
                UNWIND $pairs AS p
                MERGE (a:IPCSection {{section: p.sec_a}})
                MERGE (b:IPCSection {{section: p.sec_b}})
                MERGE (a)-[r:CO_CHARGED_WITH]->(b) SET r.note=p.note
                MERGE (b)-[r2:CO_CHARGED_WITH]->(a) SET r2.note=p.note
            """, pairs=pairs)
        else:
            session.run(f"""
                UNWIND $pairs AS p
                MERGE (a:IPCSection {{section: p.sec_a}})
                MERGE (b:IPCSection {{section: p.sec_b}})
                MERGE (a)-[r:{rel_type}]->(b) SET r.note=p.note
            """, pairs=pairs)
        counts[rel_type] = len(pairs)
    return counts


def verify_graph(session):
    print("\n─── Graph Summary ────────────────────────────────────")
    queries = [
        ("IPCSection nodes",         "MATCH (n:IPCSection) RETURN count(n) AS c"),
        ("BNSSection nodes",         "MATCH (n:BNSSection) RETURN count(n) AS c"),
        ("REPLACES (BNS→IPC)",       "MATCH ()-[r:REPLACES]->() RETURN count(r) AS c"),
        ("REPLACED_BY (IPC→BNS)",    "MATCH ()-[r:REPLACED_BY]->() RETURN count(r) AS c"),
        ("CO_CHARGED_WITH",          "MATCH ()-[r:CO_CHARGED_WITH]->() RETURN count(r) AS c"),
        ("ESCALATES_TO",             "MATCH ()-[r:ESCALATES_TO]->() RETURN count(r) AS c"),
        ("ABETS",                    "MATCH ()-[r:ABETS]->() RETURN count(r) AS c"),
        ("AGGRAVATED_BY",            "MATCH ()-[r:AGGRAVATED_BY]->() RETURN count(r) AS c"),
        ("PROCEDURAL_FOR",           "MATCH ()-[r:PROCEDURAL_FOR]->() RETURN count(r) AS c"),
    ]
    total_rels = 0
    for label, q in queries:
        c = session.run(q).single()["c"]
        if "nodes" not in label:
            total_rels += c
        print(f"  {label:30s}: {c}")
    print(f"  {'TOTAL relationships':30s}: {total_rels}")
    print("──────────────────────────────────────────────────────\n")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    wipe = "--wipe" in sys.argv

    print("\n══════════════════════════════════════════════════════")
    print("  Legal Knowledge Graph Builder  (Complete Edition)")
    print("══════════════════════════════════════════════════════")
    print(f"  URI: {NEO4J_URI}\n")

    ipc_rows = read_ipc(IPC_CSV);  print(f"  IPC: {len(ipc_rows)} sections")
    bns_rows = read_bns(BNS_CSV);  print(f"  BNS: {len(bns_rows)} sections")
    print(f"  Relationships defined: {len(RELATIONSHIPS)}\n")

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    with driver.session() as session:
        if wipe:
            wipe_graph(session)

        print("Creating constraints...")
        create_constraints(session)

        print("Ingesting IPC nodes...")
        print(f"  {ingest_ipc_nodes(session, ipc_rows)} nodes merged")

        print("Ingesting BNS nodes...")
        print(f"  {ingest_bns_nodes(session, bns_rows)} nodes merged")

        print("Creating BNS↔IPC replacement links...")
        print(f"  {ingest_bns_ipc_links(session, bns_rows)} links created")

        print("Creating IPC relationship network...")
        counts = ingest_relationships(session, RELATIONSHIPS)
        for k, v in counts.items():
            print(f"  {k}: {v} entries processed")

        verify_graph(session)

    driver.close()
    print("Done. Graph is ready.\n")


if __name__ == "__main__":
    main()
