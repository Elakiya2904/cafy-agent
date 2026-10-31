"""Independent verification of a submission attempt.

A clicked Submit button is never proof. Only a recognised confirmation message or
confirmation page counts; validation errors mean failure; anything else is
``confirmation_pending`` for the candidate to resolve.
"""
import re
from typing import Any, Dict, Optional

_SUCCESS = re.compile(
    r"(thank you for (?:applying|your application|submitting)|application (?:has been |was )?(?:successfully )?(?:submitted|received|sent)|"
    r"successfully (?:submitted|applied)|we(?:'ve| have) received your application|your application (?:is|has been) (?:complete|in)|"
    r"application complete)", re.I)
_SUCCESS_URL = re.compile(r"(confirmation|thank-?you|thanks|submitted|success|application-complete|applied)", re.I)
_ERROR_TEXT = re.compile(r"(something went wrong|failed to submit|error submitting|could not (?:submit|process)|unable to submit|try again later|submission failed)", re.I)
_REF = re.compile(r"(?:reference|confirmation|application|tracking)\s*(?:number|no\.?|id|code|#)\s*(?:is)?\s*[:#]?\s*([A-Za-z0-9][A-Za-z0-9-]{4,})", re.I)


def extract_reference(text: str) -> Optional[str]:
    m = _REF.search(text or "")
    return m.group(1) if m else None


def verify_submission(signals: Dict[str, Any]) -> Dict[str, Any]:
    """Return {result, reference, error, reason}; result ∈ submitted | submission_failed | confirmation_pending."""
    text = " ".join(str(signals.get(k) or "") for k in ("confirmation_text", "page_title"))
    url = str(signals.get("confirmation_url") or "")
    errors = [e for e in (signals.get("validation_errors") or []) if str(e).strip()]
    reference = signals.get("reference_id") or extract_reference(text)
    if errors:
        return {"result": "submission_failed", "reference": None, "error": "Validation errors: " + "; ".join(map(str, errors[:5])), "reason": "validation"}
    success = bool(_SUCCESS.search(text)) or bool(_SUCCESS_URL.search(url.split("?")[0]) and not signals.get("form_still_present"))
    if success and not signals.get("form_still_present"):
        return {"result": "submitted", "reference": reference, "error": None, "reason": "confirmation_detected"}
    if _ERROR_TEXT.search(text):
        return {"result": "submission_failed", "reference": None, "error": "The website reported an error while submitting.", "reason": "site_error"}
    if signals.get("network_error"):
        return {"result": "confirmation_pending", "reference": None, "error": "Network error after submitting; the application may or may not have gone through.", "reason": "network"}
    return {"result": "confirmation_pending", "reference": reference, "error": "No confirmation message or page was detected.", "reason": "no_confirmation"}
