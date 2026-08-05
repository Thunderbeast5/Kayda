# -*- coding: utf-8 -*-
"""
add_ipc_ingredients.py

Reads ipc_structured.json and pushes the legal "ingredients" (essential
elements) of ~100 major offence-defining IPC sections into Neo4j as:

    (:Section {id, section_number})-[:HAS_INGREDIENT {order}]->(:Ingredient {text, order})

USAGE
-----
    pip install neo4j
    export NEO4J_URI="bolt://localhost:7687"
    export NEO4J_USER="neo4j"
    export NEO4J_PASSWORD="your_password"

    python add_ipc_ingredients.py --json ipc_structured.json           # writes to DB
    python add_ipc_ingredients.py --json ipc_structured.json --dry-run # just prints a report

ASSUMPTIONS / THINGS TO CHECK BEFORE YOU RUN THIS
--------------------------------------------------
1. This assumes you already have (:Section {id: "IPC_302", ...}) nodes in
   your graph, using the same `id` values as in ipc_structured.json
   (e.g. "IPC_302" for Section 302). If your existing graph keys Section
   nodes differently (e.g. just `section_number`), change MATCH_PROPERTY
   below.
2. The ingredient lists are drawn from settled IPC jurisprudence (the
   kind of breakdown you'd find in a standard commentary like Ratanlal &
   Dhirajlal). They are a strong, structured starting point -- but legal
   "ingredients" extraction involves judgment and this has NOT been
   cross-checked against a current commentary section-by-section. Have
   someone with legal expertise review before relying on this in
   production, especially for sections touched by later amendment acts
   (e.g. the Criminal Law (Amendment) Acts of 2013/2018).
3. Only ~100 major substantive offence sections are covered here (scope
   you chose: offence-defining sections, not procedural/definitional
   ones). INGREDIENTS below is a plain dict, so extending coverage is
   just a matter of adding more entries in the same shape.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from backend/.env
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)
    print(f"Loaded environment from {env_path}")
else:
    print(f"Warning: .env not found at {env_path}")

# Property on your existing (:Section) node that matches ipc_structured.json's "id" field.
MATCH_PROPERTY = "id"


# ---------------------------------------------------------------------------
# 1. INGREDIENTS DATA — section_number -> {"offence": str, "ingredients": [str, ...]}
# ---------------------------------------------------------------------------
INGREDIENTS = {

    # ---- General principles frequently modelled as "ingredients" too ----
    "34": {
        "offence": "Acts done by several persons in furtherance of common intention",
        "ingredients": [
            "A criminal act is done by several persons",
            "The act is done in furtherance of the common intention of all",
            "Participation of each person in the criminal act (in some form)",
        ],
    },
    "120B": {
        "offence": "Criminal conspiracy — punishment",
        "ingredients": [
            "An agreement between two or more persons",
            "The agreement is to do, or cause to be done, an illegal act, or a legal act by illegal means",
            "(Mere agreement is sufficient; an overt act is not required except where the agreed offence is punishable with less than two years)",
        ],
    },
    "149": {
        "offence": "Every member of unlawful assembly guilty of offence committed in prosecution of common object",
        "ingredients": [
            "An offence is committed by any member of an unlawful assembly",
            "The offence is committed in prosecution of the common object of that assembly, OR",
            "The offence is such as the members knew was likely to be committed in prosecution of that object",
            "The accused was a member of the unlawful assembly at the time the offence was committed",
        ],
    },
    "107": {
        "offence": "Abetment of a thing",
        "ingredients": [
            "Instigating any person to do a thing, OR",
            "Engaging with one or more persons in a conspiracy for doing a thing, if an act or illegal omission takes place in pursuance of that conspiracy, OR",
            "Intentionally aiding, by act or illegal omission, the doing of a thing",
        ],
    },

    # ---- Offences against the State / public tranquility ----
    "121": {
        "offence": "Waging, or attempting to wage war, or abetting waging of war, against the Government of India",
        "ingredients": [
            "Waging war against the Government of India, OR",
            "Attempting to wage such war, OR",
            "Abetting the waging of such war",
        ],
    },
    "124A": {
        "offence": "Sedition",
        "ingredients": [
            "The accused, by words (spoken/written), signs, or visible representation, or otherwise",
            "Brings or attempts to bring into hatred or contempt, or excites or attempts to excite disaffection towards, the Government established by law in India",
        ],
    },
    "141": {
        "offence": "Unlawful assembly",
        "ingredients": [
            "An assembly of five or more persons",
            "The common object of the assembly is one of the objects listed in Section 141 (e.g. to overawe by criminal force, to commit an offence, to take possession of property by force, to compel a person to do what he is not legally bound to do, or to use criminal force against any person)",
        ],
    },
    "146": {
        "offence": "Rioting",
        "ingredients": [
            "There is an unlawful assembly (Section 141)",
            "Force or violence is used by that assembly or any member of it",
            "The force/violence is used in prosecution of the common object of the assembly",
        ],
    },
    "159": {
        "offence": "Affray",
        "ingredients": [
            "Two or more persons fight in a public place",
            "The fighting disturbs the public peace",
        ],
    },

    # ---- Offences relating to evidence / public justice ----
    "191": {
        "offence": "Giving false evidence",
        "ingredients": [
            "A person is legally bound by an oath, or by an express provision of law, to state the truth (or bound by law to make a declaration on a subject)",
            "That person makes a false statement, or a declaration, which is false and which he either knows or believes to be false, or does not believe to be true",
        ],
    },
    "193": {
        "offence": "Punishment for false evidence",
        "ingredients": [
            "The accused intentionally gives false evidence in a judicial proceeding, or fabricates false evidence for the purpose of being used in a judicial proceeding",
        ],
    },
    "201": {
        "offence": "Causing disappearance of evidence of offence, or giving false information to screen offender",
        "ingredients": [
            "An offence has been committed",
            "The accused knows or has reason to believe that the offence has been committed",
            "The accused causes the evidence of the offence to disappear, or gives false information relating to it",
            "The intent is to screen the offender from legal punishment",
        ],
    },

    # ---- Public health, safety, convenience, decency, morals ----
    "268": {
        "offence": "Public nuisance",
        "ingredients": [
            "An act or illegal omission causes common injury, danger, or annoyance to the public or to people in general who dwell or occupy property in the vicinity, or which must necessarily cause injury, obstruction, danger or annoyance to persons who may have occasion to use any public right",
        ],
    },
    "269": {
        "offence": "Negligent act likely to spread infection of disease dangerous to life",
        "ingredients": [
            "The accused acts unlawfully or negligently",
            "The act is likely to spread the infection of a disease dangerous to life",
            "The accused knows or has reason to believe the act is likely to have that effect",
        ],
    },
    "279": {
        "offence": "Rash driving or riving on a public way",
        "ingredients": [
            "Driving or riding any vehicle in a public way",
            "The manner of driving is rash or negligent",
            "It endangers human life, or is likely to cause hurt or injury to any other person",
        ],
    },
    "284": {
        "offence": "Negligent conduct with respect to poisonous substance",
        "ingredients": [
            "Doing any act with a poisonous substance",
            "So rashly or negligently as to endanger human life, or likely to cause hurt or injury to any person",
        ],
    },
    "295A": {
        "offence": "Deliberate and malicious acts intended to outrage religious feelings",
        "ingredients": [
            "An act, including insults or attempts to insult a religion or the religious beliefs of a class",
            "By words (spoken/written), signs, visible representations, or otherwise",
            "Done with the deliberate and malicious intention of outraging the religious feelings of that class",
        ],
    },

    # ---- Offences affecting life ----
    "299": {
        "offence": "Culpable homicide",
        "ingredients": [
            "The accused causes death of a person",
            "By an act done with the intention of causing death, OR",
            "With the intention of causing such bodily injury as is likely to cause death, OR",
            "With the knowledge that the act is likely to cause death",
        ],
    },
    "300": {
        "offence": "Murder",
        "ingredients": [
            "The act causing death is done with the intention of causing death, OR",
            "With the intention of causing such bodily injury as the offender knows to be likely to cause the death of the person injured, OR",
            "With the intention of causing bodily injury sufficient in the ordinary course of nature to cause death, OR",
            "With the knowledge that the act is so imminently dangerous that it must in all probability cause death, or such bodily injury as is likely to cause death, and is committed without any excuse for incurring the risk",
            "The case does not fall within any of the five stated Exceptions to Section 300 (e.g. grave and sudden provocation, private defence, sudden fight, consent, exceeding powers by a public servant)",
        ],
    },
    "302": {
        "offence": "Punishment for murder",
        "ingredients": [
            "The accused commits murder as defined in Section 300",
        ],
    },
    "304": {
        "offence": "Punishment for culpable homicide not amounting to murder",
        "ingredients": [
            "The accused commits culpable homicide (Section 299)",
            "The act does not amount to murder under Section 300 (i.e. falls within one of the Exceptions, or lacks the degree of intention/knowledge required for murder)",
        ],
    },
    "304A": {
        "offence": "Causing death by negligence",
        "ingredients": [
            "Death of a person is caused",
            "The death is caused by a rash or negligent act of the accused",
            "The act does not amount to culpable homicide",
        ],
    },
    "304B": {
        "offence": "Dowry death",
        "ingredients": [
            "Death of a woman is caused by burns, bodily injury, or otherwise than under normal circumstances",
            "The death occurs within seven years of her marriage",
            "It is shown that soon before her death she was subjected to cruelty or harassment by her husband or a relative of her husband",
            "Such cruelty or harassment was in connection with a demand for dowry",
        ],
    },
    "306": {
        "offence": "Abetment of suicide",
        "ingredients": [
            "A person commits suicide",
            "The accused abetted the commission of that suicide",
        ],
    },
    "307": {
        "offence": "Attempt to murder",
        "ingredients": [
            "An act is done by the accused with the intention or knowledge required for murder under Section 300",
            "The act is done under such circumstances that, had death been caused, the accused would be guilty of murder",
            "Death does not actually result",
        ],
    },
    "308": {
        "offence": "Attempt to commit culpable homicide",
        "ingredients": [
            "An act is done with the intention or knowledge required for culpable homicide (Section 299)",
            "Death does not result from the act",
        ],
    },

    # ---- Hurt ----
    "319": {
        "offence": "Hurt",
        "ingredients": [
            "Bodily pain, disease, or infirmity is caused to any person",
        ],
    },
    "320": {
        "offence": "Grievous hurt",
        "ingredients": [
            "The hurt caused falls within one of the specified categories (e.g. emasculation, permanent loss of sight/hearing, loss of a limb or joint, permanent disfiguration of the head/face, fracture or dislocation of a bone or tooth, or hurt endangering life or causing severe bodily pain / inability to follow ordinary pursuits for 20 days)",
        ],
    },
    "323": {
        "offence": "Punishment for voluntarily causing hurt",
        "ingredients": [
            "The accused voluntarily causes hurt to any person",
            "(i.e. intends, or knows himself likely, to cause hurt, and thereby causes hurt)",
        ],
    },
    "324": {
        "offence": "Voluntarily causing hurt by dangerous weapons or means",
        "ingredients": [
            "The accused voluntarily causes hurt",
            "By means of an instrument for shooting/stabbing/cutting, or any instrument used as a weapon of offence likely to cause death, or by fire/heated substance, poison, explosive substance, or any substance harmful to inhale/swallow/receive into the blood, or by any corrosive substance",
        ],
    },
    "325": {
        "offence": "Punishment for voluntarily causing grievous hurt",
        "ingredients": [
            "The accused voluntarily causes grievous hurt (as defined in Section 320)",
        ],
    },
    "326": {
        "offence": "Voluntarily causing grievous hurt by dangerous weapons or means",
        "ingredients": [
            "The accused voluntarily causes grievous hurt",
            "By means of an instrument for shooting/stabbing/cutting, or any instrument used as a weapon of offence likely to cause death, or by fire/heated substance, poison, explosive substance, or any substance harmful to inhale/swallow/receive into the blood, or by any corrosive substance",
        ],
    },

    # ---- Wrongful restraint / confinement ----
    "339": {
        "offence": "Wrongful restraint",
        "ingredients": [
            "The accused voluntarily obstructs a person",
            "So as to prevent that person from proceeding in a direction in which that person has a right to proceed",
        ],
    },
    "340": {
        "offence": "Wrongful confinement",
        "ingredients": [
            "The accused wrongfully restrains a person",
            "In such a manner as to prevent that person from proceeding beyond certain circumscribing limits",
        ],
    },

    # ---- Criminal force and assault ----
    "350": {
        "offence": "Criminal force",
        "ingredients": [
            "The accused intentionally uses force on a person, without that person's consent",
            "The force is used to commit an offence, or with intent (or knowledge that it is likely) to cause injury, fear, or annoyance to the person against whom it is used",
        ],
    },
    "351": {
        "offence": "Assault",
        "ingredients": [
            "The accused makes a gesture or preparation intending or knowing it likely to cause any person present to apprehend that criminal force is about to be used against them",
        ],
    },
    "354": {
        "offence": "Assault or criminal force to woman with intent to outrage her modesty",
        "ingredients": [
            "The accused assaults or uses criminal force on a woman",
            "With the intention of outraging her modesty, or knowing it to be likely that her modesty will be outraged",
        ],
    },
    "354A": {
        "offence": "Sexual harassment",
        "ingredients": [
            "Physical contact and advances involving unwelcome and explicit sexual overtures, OR",
            "A demand or request for sexual favours, OR",
            "Showing pornography against a woman's will, OR",
            "Making sexually coloured remarks",
        ],
    },
    "354C": {
        "offence": "Voyeurism",
        "ingredients": [
            "The accused watches or captures the image of a woman engaging in a private act",
            "In circumstances where she would usually have the expectation of not being observed either by the perpetrator or by any other person at the behest of the perpetrator, OR disseminates such image",
        ],
    },
    "354D": {
        "offence": "Stalking",
        "ingredients": [
            "The accused follows a woman and contacts, or attempts to contact, her to foster personal interaction repeatedly despite a clear indication of disinterest, OR",
            "Monitors her use of the internet, email, or other electronic communication",
        ],
    },

    # ---- Kidnapping, abduction, trafficking ----
    "359": {
        "offence": "Kidnapping (from India / from lawful guardianship)",
        "ingredients": [
            "Kidnapping from India, OR",
            "Kidnapping from lawful guardianship",
        ],
    },
    "361": {
        "offence": "Kidnapping from lawful guardianship",
        "ingredients": [
            "Taking or enticing a minor (under 16 if male, under 18 if female) or a person of unsound mind",
            "Out of the keeping of the lawful guardian",
            "Without the consent of that guardian",
        ],
    },
    "362": {
        "offence": "Abduction",
        "ingredients": [
            "By force compelling, or by deceitful means inducing, a person",
            "To go from any place",
        ],
    },
    "363": {
        "offence": "Punishment for kidnapping",
        "ingredients": [
            "The accused kidnaps a person from India or from lawful guardianship (Section 359–361)",
        ],
    },
    "366": {
        "offence": "Kidnapping, abducting, or inducing a woman to compel marriage etc.",
        "ingredients": [
            "Kidnapping or abducting a woman",
            "With intent that she may be compelled, or knowing it likely that she will be compelled, to marry any person against her will, OR",
            "With intent that she may be forced or seduced to illicit intercourse, or knowing it likely that she will be forced or seduced",
        ],
    },
    "370": {
        "offence": "Trafficking of person",
        "ingredients": [
            "Recruiting, transporting, harbouring, transferring, or receiving a person",
            "By means of threat, force, coercion, abduction, fraud, deception, abuse of power, or inducement",
            "For the purpose of exploitation (physical/sexual exploitation, slavery, servitude, or forced removal of organs)",
        ],
    },

    # ---- Sexual offences ----
    "375": {
        "offence": "Rape",
        "ingredients": [
            "A man performs any of the specified sexual acts (penetration as described in Section 375) with a woman",
            "The act is done under any of the described circumstances of lack of valid consent (against her will, without her consent, consent obtained by putting her in fear, consent given under a false belief of being lawfully married, consent given due to unsoundness of mind/intoxication, or with a woman under 18 years with or without consent, or where she is unable to communicate consent)",
        ],
    },
    "376": {
        "offence": "Punishment for rape",
        "ingredients": [
            "The accused commits rape as defined in Section 375",
        ],
    },
    "377": {
        "offence": "Unnatural offences",
        "ingredients": [
            "Voluntary carnal intercourse against the order of nature with any man, woman, or animal",
            "(As read down by the Supreme Court in Navtej Singh Johar (2018), this section no longer criminalises consensual acts between adults; it survives for non-consensual acts and acts involving minors or animals)",
        ],
    },

    # ---- Theft, extortion, robbery, dacoity ----
    "378": {
        "offence": "Theft",
        "ingredients": [
            "Moveable property is in the possession of a person",
            "The accused takes it out of that person's possession",
            "Without that person's consent",
            "The taking is dishonest, i.e. with the intention of causing wrongful gain or wrongful loss",
            "The property is moved in order to such taking",
        ],
    },
    "379": {
        "offence": "Punishment for theft",
        "ingredients": [
            "The accused commits theft as defined in Section 378",
        ],
    },
    "380": {
        "offence": "Theft in a dwelling house, or means of transport, or place of worship",
        "ingredients": [
            "Theft is committed (Section 378)",
            "In a building, tent, or vessel used as a human dwelling, or for custody of property",
        ],
    },
    "383": {
        "offence": "Extortion",
        "ingredients": [
            "The accused intentionally puts a person in fear of injury to that person or another",
            "By putting the person in such fear, dishonestly induces that person to deliver property, or any valuable security, or anything signed/sealed which may be converted into a valuable security",
        ],
    },
    "384": {
        "offence": "Punishment for extortion",
        "ingredients": [
            "The accused commits extortion as defined in Section 383",
        ],
    },
    "390": {
        "offence": "Robbery",
        "ingredients": [
            "Theft or extortion is committed",
            "In committing theft, the accused voluntarily causes or attempts to cause death, hurt, wrongful restraint, or fear of instant death/hurt/wrongful restraint, in order to commit the theft, retain the stolen property, or escape after the theft (theft-based robbery), OR",
            "In committing extortion, the offender is in the presence of the person put in fear and commits the extortion by causing that person to fear instant death, hurt, or wrongful restraint, and by so causing fear induces delivery of the property (extortion-based robbery)",
        ],
    },
    "392": {
        "offence": "Punishment for robbery",
        "ingredients": [
            "The accused commits robbery as defined in Section 390",
        ],
    },
    "395": {
        "offence": "Dacoity",
        "ingredients": [
            "Five or more persons conjointly commit or attempt to commit a robbery",
            "OR five or more persons are present and aid such commission/attempt",
        ],
    },
    "396": {
        "offence": "Dacoity with murder",
        "ingredients": [
            "Dacoity is committed by five or more persons conjointly (Section 395)",
            "One of those persons commits murder in the course of the dacoity",
        ],
    },
    "403": {
        "offence": "Dishonest misappropriation of property",
        "ingredients": [
            "The accused misappropriates or converts to his own use moveable property",
            "The misappropriation/conversion is done dishonestly",
        ],
    },
    "405": {
        "offence": "Criminal breach of trust",
        "ingredients": [
            "The accused is entrusted with property, or with dominion over property",
            "The accused dishonestly misappropriates, converts to his own use, or uses/disposes of that property in violation of any legal contract or direction of law prescribing how it is to be handled",
        ],
    },
    "406": {
        "offence": "Punishment for criminal breach of trust",
        "ingredients": [
            "The accused commits criminal breach of trust as defined in Section 405",
        ],
    },
    "409": {
        "offence": "Criminal breach of trust by public servant, banker, merchant, or agent",
        "ingredients": [
            "Criminal breach of trust is committed (Section 405)",
            "By the accused acting in the capacity of a public servant, or a banker/merchant/factor/broker/attorney/agent",
        ],
    },
    "410": {
        "offence": "Stolen property",
        "ingredients": [
            "Property, the possession of which has been transferred by theft, extortion, robbery, or criminal breach of trust, and property acquired by criminal misappropriation is 'stolen property'",
        ],
    },
    "411": {
        "offence": "Dishonestly receiving stolen property",
        "ingredients": [
            "The property in question is stolen property",
            "The accused dishonestly receives or retains it",
            "The accused knows, or has reason to believe, it to be stolen property",
        ],
    },
    "413": {
        "offence": "Habitually dealing in stolen property",
        "ingredients": [
            "The accused habitually receives or deals in property he knows or has reason to believe to be stolen property",
        ],
    },

    # ---- Cheating ----
    "415": {
        "offence": "Cheating",
        "ingredients": [
            "The accused deceives a person",
            "By such deception, fraudulently or dishonestly induces the person so deceived to deliver property, or consent to the retention of property by any person, or to do or omit to do something which he would not have done or omitted had he not been so deceived",
            "The act/omission causes or is likely to cause damage or harm to that person in body, mind, reputation, or property",
        ],
    },
    "417": {
        "offence": "Punishment for cheating",
        "ingredients": [
            "The accused commits cheating as defined in Section 415",
        ],
    },
    "418": {
        "offence": "Cheating with knowledge that wrongful loss may ensue to a person whose interest the offender was bound to protect",
        "ingredients": [
            "The accused cheats a person (Section 415)",
            "The accused was bound, by law or a legal contract, to protect the interests of the person cheated",
        ],
    },
    "420": {
        "offence": "Cheating and dishonestly inducing delivery of property",
        "ingredients": [
            "The accused cheats a person (Section 415)",
            "By such cheating, dishonestly induces delivery of any property to any person, or makes/alters/destroys the whole or a part of a valuable security, or anything signed/sealed capable of being converted into a valuable security",
        ],
    },

    # ---- Marriage offences ----
    "494": {
        "offence": "Marrying again during lifetime of husband or wife (bigamy)",
        "ingredients": [
            "The accused has a spouse living",
            "The accused marries again in a case in which such marriage is void by reason of it taking place during the life of such spouse",
        ],
    },
    "498A": {
        "offence": "Cruelty by husband or relatives of husband",
        "ingredients": [
            "The woman is subjected to cruelty",
            "By her husband, or a relative of her husband",
            "'Cruelty' means wilful conduct likely to drive the woman to suicide or cause grave injury/danger to life, limb, or health (mental or physical), OR harassment with a view to coercing her (or a person related to her) to meet an unlawful demand for property/valuable security, or on account of failure to meet such demand",
        ],
    },

    # ---- Defamation, criminal intimidation ----
    "499": {
        "offence": "Defamation",
        "ingredients": [
            "The accused makes or publishes an imputation concerning a person",
            "By words (spoken/written), signs, or visible representations",
            "The imputation is made with intent to harm, or with knowledge/reason to believe that it will harm, the reputation of the person",
            "The imputation does not fall within one of the Ten Exceptions to Section 499",
        ],
    },
    "500": {
        "offence": "Punishment for defamation",
        "ingredients": [
            "The accused commits defamation as defined in Section 499",
        ],
    },
    "503": {
        "offence": "Criminal intimidation",
        "ingredients": [
            "The accused threatens another person with injury to that person's person, reputation, or property (or to the person/reputation of someone in whom that person is interested)",
            "The threat is made with the intent to cause alarm to that person, or to cause that person to do any act, or to omit to do any act which he is legally entitled to do, as a means of avoiding the execution of the threat",
        ],
    },
    "506": {
        "offence": "Punishment for criminal intimidation",
        "ingredients": [
            "The accused commits criminal intimidation as defined in Section 503",
        ],
    },
    "509": {
        "offence": "Word, gesture, or act intended to insult the modesty of a woman",
        "ingredients": [
            "The accused utters a word, makes a sound or gesture, or exhibits an object",
            "Intending that the word/sound/gesture/object shall be seen or heard by a woman, or intrudes upon her privacy",
            "With the intention of insulting her modesty",
        ],
    },

    # ---- Mischief ----
    "425": {
        "offence": "Mischief",
        "ingredients": [
            "The accused causes destruction of property, or a change in property (or in its situation) that destroys or diminishes its value/utility, or affects it injuriously",
            "The act is done with intent to cause, or knowledge that it is likely to cause, wrongful loss or damage to the public or to any person",
        ],
    },
    "426": {
        "offence": "Punishment for mischief",
        "ingredients": [
            "The accused commits mischief as defined in Section 425",
        ],
    },
    "435": {
        "offence": "Mischief by fire or explosive substance with intent to cause damage",
        "ingredients": [
            "Mischief is committed by fire or an explosive substance",
            "With intent to cause, or knowledge it is likely to cause, damage of a specified value",
        ],
    },

    # ---- Criminal trespass and house-breaking ----
    "441": {
        "offence": "Criminal trespass",
        "ingredients": [
            "The accused enters into or upon property in the possession of another",
            "With intent to commit an offence, or to intimidate/insult/annoy the person in possession, OR",
            "Having lawfully entered, unlawfully remains there with such intent",
        ],
    },
    "442": {
        "offence": "House-trespass",
        "ingredients": [
            "Criminal trespass is committed (Section 441)",
            "By entering into or remaining in a building, tent, or vessel used as a human dwelling, or for custody of property",
        ],
    },
    "447": {
        "offence": "Punishment for criminal trespass",
        "ingredients": [
            "The accused commits criminal trespass as defined in Section 441",
        ],
    },
    "448": {
        "offence": "Punishment for house-trespass",
        "ingredients": [
            "The accused commits house-trespass as defined in Section 442",
        ],
    },
    "450": {
        "offence": "House-trespass to commit an offence punishable with imprisonment for life",
        "ingredients": [
            "House-trespass is committed (Section 442)",
            "The intent is to commit an offence punishable with imprisonment for life",
        ],
    },
    "457": {
        "offence": "Lurking house-trespass or house-breaking by night, to commit an offence punishable with imprisonment",
        "ingredients": [
            "Lurking house-trespass or house-breaking is committed, by night",
            "With intent to commit an offence punishable with imprisonment",
        ],
    },
    "458": {
        "offence": "Lurking house-trespass or house-breaking by night, after preparation for hurt/assault/wrongful restraint",
        "ingredients": [
            "Lurking house-trespass or house-breaking by night is committed",
            "The accused has made preparation for causing hurt, assault, or wrongful restraint to any person, or for putting any person in fear of it",
        ],
    },
    "459": {
        "offence": "Grievous hurt caused whilst committing lurking house-trespass or house-breaking",
        "ingredients": [
            "Lurking house-trespass or house-breaking is committed",
            "The accused causes grievous hurt to any person, or attempts to cause death or grievous hurt, while committing the trespass/house-breaking",
        ],
    },
    "460": {
        "offence": "All persons jointly concerned in lurking house-trespass or house-breaking by night punishable where death or grievous hurt caused by one",
        "ingredients": [
            "Lurking house-trespass or house-breaking by night is jointly committed by several persons",
            "Death or grievous hurt is caused to any person by any one of them in the commission of the offence",
        ],
    },

    # ---- Forgery ----
    "463": {
        "offence": "Forgery",
        "ingredients": [
            "The accused makes a false document or false electronic record, or part of it",
            "With intent to cause damage or injury to the public or any person, or to support any claim/title, or to cause any person to part with property, or to enter into an express/implied contract, or with intent to commit fraud (or that fraud may be committed)",
        ],
    },
    "464": {
        "offence": "Making a false document",
        "ingredients": [
            "The accused dishonestly or fraudulently makes, signs, seals, or executes a document/part of a document, or alters a document, or makes any mark denoting execution, without lawful authority and knowing it likely to be believed to have been made by another or at another time, OR",
            "Dishonestly or fraudulently causes a person to sign/seal/execute a document who does not know the contents or the effect of what he signs due to unsoundness of mind, intoxication, or deception",
        ],
    },
    "465": {
        "offence": "Punishment for forgery",
        "ingredients": [
            "The accused commits forgery as defined in Section 463",
        ],
    },
    "467": {
        "offence": "Forgery of a valuable security, will, or authority to make/transfer any valuable security",
        "ingredients": [
            "Forgery is committed (Section 463)",
            "The document forged is a valuable security, a will, or an authority to adopt a son, or an authority to make/transfer any valuable security or to receive its principal/interest/dividend",
        ],
    },
    "468": {
        "offence": "Forgery for the purpose of cheating",
        "ingredients": [
            "Forgery is committed (Section 463)",
            "With intent that the document/electronic record forged shall be used for the purpose of cheating",
        ],
    },
    "471": {
        "offence": "Using as genuine a forged document or electronic record",
        "ingredients": [
            "A document or electronic record is forged",
            "The accused fraudulently or dishonestly uses it as genuine",
            "Knowing or having reason to believe it to be forged",
        ],
    },

    # ---- Currency / property marks ----
    "489A": {
        "offence": "Counterfeiting currency notes or bank notes",
        "ingredients": [
            "The accused counterfeits, or knowingly performs any part of the process of counterfeiting, a currency note or bank note",
        ],
    },
    "489B": {
        "offence": "Using as genuine, forged or counterfeit currency notes or bank notes",
        "ingredients": [
            "A currency note or bank note is forged or counterfeit",
            "The accused sells, buys, receives, or uses it as genuine",
            "Knowing or having reason to believe it to be forged or counterfeit",
        ],
    },

    # ---- Attempt ----
    "511": {
        "offence": "Attempt to commit offences punishable with imprisonment for life or other imprisonment",
        "ingredients": [
            "The accused intends to commit an offence punishable with imprisonment for life or imprisonment",
            "The accused does an act towards the commission of that offence",
            "The offence is not actually committed",
        ],
    },
}


# ---------------------------------------------------------------------------
# 2. LOAD ipc_structured.json AND MATCH AGAINST INGREDIENTS
# ---------------------------------------------------------------------------
def load_sections(json_path):
    with open(json_path, encoding="utf-8-sig") as f:
        data = json.load(f)
    return {
        d["section_number"]: d
        for d in data
        if d.get("node_type") == "section" and d.get("section_number")
    }


def build_report(sections):
    matched, missing_in_json = [], []
    for sec_num in INGREDIENTS:
        if sec_num in sections:
            matched.append(sec_num)
        else:
            missing_in_json.append(sec_num)
    return matched, missing_in_json


# ---------------------------------------------------------------------------
# 3. NEO4J WRITE
# ---------------------------------------------------------------------------
CYPHER = f"""
MERGE (s:Section {{{MATCH_PROPERTY}: $section_id}})
ON CREATE SET s.section_number = $section_number
SET s.offence_name = $offence
WITH s
UNWIND $ingredients AS ing
MERGE (i:Ingredient {{section_id: $section_id, order: ing.order}})
SET i.text = ing.text
MERGE (s)-[r:HAS_INGREDIENT]->(i)
SET r.order = ing.order
"""


def push_to_neo4j(driver, sections, database=None):
    matched, missing = build_report(sections)
    with driver.session(database=database) as session:
        for sec_num in matched:
            node = sections[sec_num]
            info = INGREDIENTS[sec_num]
            ingredient_rows = [
                {"order": idx, "text": text}
                for idx, text in enumerate(info["ingredients"])
            ]
            session.run(
                CYPHER,
                section_id=node["id"],
                section_number=sec_num,
                offence=info["offence"],
                ingredients=ingredient_rows,
            )
            print(f"  [OK] Section {sec_num} ({info['offence']}) -> {len(ingredient_rows)} ingredients")
    return matched, missing


# ---------------------------------------------------------------------------
# 4. MAIN
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Push IPC section ingredients into Neo4j.")
    parser.add_argument("--json", default="ipc_structured.json", help="Path to ipc_structured.json")
    parser.add_argument("--dry-run", action="store_true", help="Only print the match report, don't write to Neo4j")
    parser.add_argument("--database", default=None, help="Neo4j database name (default: server default)")
    args = parser.parse_args()

    if not os.path.exists(args.json):
        print(f"ERROR: file not found: {args.json}", file=sys.stderr)
        sys.exit(1)

    sections = load_sections(args.json)
    print(f"Loaded {len(sections)} section nodes from {args.json}")
    print(f"Ingredients curated for {len(INGREDIENTS)} sections")

    matched, missing = build_report(sections)
    print(f"\nMatched against JSON: {len(matched)}")
    if missing:
        print(f"In INGREDIENTS but NOT found in JSON (check numbering): {missing}")

    if args.dry_run:
        print("\n--dry-run set: not connecting to Neo4j. Report only.")
        return

    from neo4j import GraphDatabase  # imported here so --dry-run works without the driver installed

    uri = os.environ.get("NEO4J_URI")
    user = os.environ.get("NEO4J_USER")
    password = os.environ.get("NEO4J_PASSWORD")
    if not all([uri, user, password]):
        print(
            "\nERROR: set NEO4J_URI, NEO4J_USER, and NEO4J_PASSWORD environment variables "
            "(or edit this script) before running without --dry-run.",
            file=sys.stderr,
        )
        sys.exit(1)

    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        driver.verify_connectivity()
        print(f"\nConnected to {uri}. Writing ingredients...\n")
        matched, missing = push_to_neo4j(driver, sections, database=args.database)
        print(f"\nDone. Wrote ingredients for {len(matched)} sections.")
        if missing:
            print(f"Skipped (no matching Section node in JSON): {missing}")
    finally:
        driver.close()


if __name__ == "__main__":
    main()