# Legal Acts Coverage

This document lists all legal acts currently supported in the system for women and children protection.

## Complete List of Supported Acts (15 Acts)

### Core Criminal Law
1. **Bharatiya Nyaya Sanhita (BNS), 2023**
   - Pattern: `BNS`, `Bharatiya Nyaya Sanhita`
   - Coverage: Main criminal offences (murder, rape, assault, kidnapping, trafficking)
   - Relevant for: Women ✅ | Children ✅

2. **Indian Penal Code (IPC), 1860**
   - Pattern: `IPC`, `Indian Penal Code`
   - Coverage: Legacy criminal code (being replaced by BNS)
   - Relevant for: Women ✅ | Children ✅

### Child Protection Acts
3. **Protection of Children from Sexual Offences (POCSO) Act, 2012**
   - Pattern: `POCSO`, `POCSO Act`
   - Coverage: Sexual offences against children
   - Relevant for: Children ✅

4. **Juvenile Justice (Care and Protection of Children) Act, 2015**
   - Pattern: `Juvenile Justice Act`, `JJ Act`
   - Coverage: Child protection, abandonment, adoption, cruelty
   - Relevant for: Children ✅

5. **Prohibition of Child Marriage Act, 2006**
   - Pattern: `Child Marriage Act`, `PCMA`
   - Coverage: Prevention of child marriage
   - Relevant for: Women ✅ | Children ✅

6. **Child and Adolescent Labour (Prohibition and Regulation) Act, 1986**
   - Pattern: `Child Labour Act`
   - Coverage: Prevention of child labour
   - Relevant for: Children ✅

### Women Protection Acts
7. **Protection of Women from Domestic Violence Act, 2005**
   - Pattern: `Domestic Violence Act`, `DV Act`
   - Coverage: Domestic violence protection
   - Relevant for: Women ✅ | Children (Partial)

8. **Dowry Prohibition Act, 1961**
   - Pattern: `Dowry Prohibition Act`, `Dowry Act`
   - Coverage: Dowry demand and harassment
   - Relevant for: Women ✅

9. **Sexual Harassment of Women at Workplace (Prevention, Prohibition and Redressal) Act, 2013**
   - Pattern: `Sexual Harassment at Workplace Act`, `POSH Act`
   - Coverage: Workplace sexual harassment
   - Relevant for: Women ✅

10. **Indecent Representation of Women (Prohibition) Act, 1986**
    - Pattern: `Indecent Representation of Women Act`
    - Coverage: Obscene representation of women
    - Relevant for: Women ✅

11. **Commission of Sati (Prevention) Act, 1987**
    - Pattern: `Sati Prevention Act`, `Sati Act`
    - Coverage: Sati-related offences
    - Relevant for: Women ✅

12. **Pre-Conception and Pre-Natal Diagnostic Techniques (Prohibition of Sex Selection) Act, 1994**
    - Pattern: `PC-PNDT Act`, `PCPNDT Act`
    - Coverage: Female foeticide, sex selection
    - Relevant for: Women ✅ | Children (Indirect)

### Human Trafficking & Exploitation
13. **Immoral Traffic (Prevention) Act, 1956**
    - Pattern: `Immoral Traffic Act`, `ITP Act`, `ITPA`
    - Coverage: Human trafficking for prostitution
    - Relevant for: Women ✅ | Children ✅

14. **Bonded Labour System (Abolition) Act, 1976**
    - Pattern: `Bonded Labour Act`
    - Coverage: Forced labour
    - Relevant for: Women ✅ | Children ✅

### Medical & Organ-Related
15. **Transplantation of Human Organs and Tissues Act, 1994**
    - Pattern: `Transplantation of Organs Act`, `THOA`
    - Coverage: Illegal organ removal/trafficking
    - Relevant for: Women ✅ | Children ✅

## Additional Supporting Acts

16. **Code of Criminal Procedure (CrPC), 1973**
    - Pattern: `CrPC`, `Cr.P.C.`
    - Coverage: Criminal procedure framework

17. **Bharatiya Nagarik Suraksha Sanhita (BNSS), 2023**
    - Pattern: `BNSS`, `Bharatiya Nagarik Suraksha Sanhita`
    - Coverage: New criminal procedure code

18. **Indian Evidence Act, 1872**
    - Pattern: `Indian Evidence Act`, `Evidence Act`
    - Coverage: Rules of evidence

19. **Information Technology Act, 2000**
    - Pattern: `IT Act`, `Information Technology Act`
    - Coverage: Cyber crimes, digital offences

## Implementation Status

✅ All 15 required acts for women and child protection are now included in:
- `backend/data_extraction/scriptsD/stage_3.py`
- `backend/data_extraction/scriptsD/stage_3_improved.py`

## Pattern Matching

Each act has multiple pattern variations to ensure maximum detection:
- Full formal names with years
- Common abbreviations
- Alternative names
- Short forms

The system uses case-insensitive regex matching to identify these acts in legal documents.
