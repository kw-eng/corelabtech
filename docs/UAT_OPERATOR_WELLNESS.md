# CoreLabTech operator acceptance test

Version: 2026-07-26

Facility: `[name]`  
Location: `[location]`  
Operator: `[name and role]`  
Build/version: `[commit or image tag]`  
Test date: `[date]`

## Acceptance scenario

| # | Step | Expected result | Pass/Fail | Notes |
|---:|---|---|---|---|
| 1 | Log in as operator | Operator dashboard opens; admin-only actions are hidden | | |
| 2 | Select/create client | Correct client ID appears in the session | | |
| 3 | Select chamber | Facility chamber and maximum ATA are correct | | |
| 4 | Select 1.3 ATA protocol | Target displays as 1.30 ATA | | |
| 5 | Enter pressure in configured unit | Converted ATA and difference are correct | | |
| 6 | Repeat with 1.5 ATA protocol | Target displays as 1.50 ATA | | |
| 7 | Complete PRE questionnaire | Sleep, stress, training, fatigue and goal are saved | | |
| 8 | Upload approved FIT file | HR/HRV timeline is accepted and assigned to the client | | |
| 9 | Upload approved CSV file | SpO2/pulse timeline is accepted and assigned to the client | | |
| 10 | Synchronize files | Match rate, offsets and warnings are visible | | |
| 11 | Save DURING and POST | Chamber, protocol, pressure and check-out are retained | | |
| 12 | Confirm wellness acknowledgement | Versioned consent is saved | | |
| 13 | Run analysis | Wellness Response, Data Quality and Baseline Confidence are separate | | |
| 14 | Review trend | 1.3 ATA history excludes 1.5 ATA sessions and vice versa | | |
| 15 | Generate PDF | Client, chamber, protocol, ATA, PRE/DURING/POST and disclaimer appear | | |
| 16 | Export client | ZIP contains manifest, profile, sessions, signals, results and consents | | |
| 17 | Test operator permissions | Operator cannot delete a client or access admin-only functions | | |
| 18 | Test backup restore | Restore script reports users, sessions and migrations then cleans test DB | | |
| 19 | Test HTTPS | HTTP redirects; secure cookie and valid certificate are present | | |
| 20 | Review wellness wording | No diagnosis, treatment or medical-clearance claim appears | | |

## Acceptance criteria

All steps must pass. Any failed identity, permission, protocol separation,
pressure conversion, consent, export, restore or HTTPS step blocks production
acceptance.

## Sign-off

Operator signature/date: ______________________________

Facility owner signature/date: _________________________

CoreLabTech representative/date: _______________________
