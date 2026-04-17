# Implementation Plan - OCR Hardening & Inline Athlete Creation

This plan addresses two high-priority roadmap items: stabilizing the OCR pipeline with a graceful fallback and implementing a frictionless workflow for creating missing athletes during match report review.

## User Review Required

> [!IMPORTANT]
> **Production Choice**: As requested, I will NOT use `threading.Thread` in this phase to avoid fragile async patterns. Actions are focused strictly on OCR reliability and athlete onboarding.
> **Athlete Creation**: New athletes will be created via a specialized method in `MatchReportAdmin` with a generated username (e.g., `ath_UUID`). I will assume a standard name splitting logic (the last word is the last name, others are the first name).

## Proposed Changes

---

### 1. OCR Service Stablization
#### [MODIFY] [ocr_service.py](file:///home/alberto/matches/services/ocr_service.py)
- **Safe Initialization**: `get_provider` will now check `settings.OPENAI_API_KEY`. If it's missing, empty, or fails initialization, it will log a warning and return `MockVisionProvider()`.
- **Exception Grabbing**: In `process_and_update`, I will catch specific provider exceptions and ensure the `MatchReport` status moves to `REJECTED` with a clear explanation in `validation_notes`. 500s will be avoided.

---

### 2. Inline Athlete Onboarding
#### [MODIFY] [admin.py](file:///home/alberto/matches/admin.py)
- **POST Action**: Add a handler for `_action == "create_athlete"` in the `review_view`.
- **Creation Logic**: Logic to generate a `User` + `AthleteProfile`, linking them to the team specified in the match context.
- **Immediate Feedback**: After creation, the `MatchReport.normalized_data` will be automatically updated with the new reconciliation mapping and the user redirected back to the review page with a success message.

#### [MODIFY] [review.html](file:///home/alberto/templates/admin/matches/matchreport/review.html)
- **UI Interaction**: Add an "Aggiungi" (Add) icon next to names in the reconciliation tables.
- **JS Hook**: Enhance script to trigger a hidden form submission with the player's name and team side.

---

## Verification Plan

### Automated Tests
- I will run a script to verify `get_provider` logic with different `settings.OPENAI_API_KEY` states.

### Manual Verification
1. **OCR Fallback**: Set `OCR_PROVIDER=gpt4o` but clear the key in `.env` (temporarily). Attempt OCR from admin. Verify it correctly logs and uses Mock without crashing.
2. **Inline Creation**:
   - Navigate to a report review.
   - For an unreconciled player "Mario Rossi", click the new "Add" button.
   - Verify the state reloads and "Mario Rossi" is now matched to a real ID.
   - Verify that "Mario Rossi" exists in `accounts.User` as an athlete.

## Risks
- **Duplicate Prevention**: Admin still needs to be careful not to create an athlete that already exists but was missed by fuzzy matching. I will add a warning in the UI if possible.
- **Name Complexity**: Complex names (e.g., "De Luca Mario") might split incorrectly into "De Luca" (first) and "Mario" (last) if using simple split. I'll default to the last word as the surname.

