"""Task context selection. No reference is opened and no authority is inferred."""
from .records import now, stamp, time_value


def provisional(reason, max_age=86400, integrity="unknown", match="none"):
    return {"evaluated_at": stamp(now()), "match": match, "integrity": integrity,
            "recency": None, "acceptance": None, "disposition": "provisional",
            "task_key": None, "selected_record_id": None, "record": None,
            "continuation": None, "age_seconds": None, "max_age_seconds": max_age,
            "reference_check": "not_performed", "reasons": [reason]}


def pickup(rows, task=None, project=None, max_age=86400):
    candidates = [r for r in rows if (r["task_key"] == task if task is not None
                                     else r["project_key"] == project)]
    if not candidates:
        return "no_match", provisional("task_missing" if task is not None else "project_missing",
                                       max_age, "valid")
    if len(candidates) != 1:
        return "ambiguous", provisional("multiple_tasks", max_age, "valid", "ambiguous")
    row = candidates[0]
    evaluated = now()
    recency, acceptance, reasons, age = assess(row, max_age, evaluated)
    available = not any(reason != "evidence_missing" for reason in reasons)
    disposition = "context_available" if available else "inspect_only"
    return disposition, {
        "evaluated_at": stamp(evaluated), "match": "task" if task is not None else "project_unique",
        "integrity": "valid", "recency": recency, "acceptance": acceptance,
        "disposition": disposition, "task_key": row["task_key"],
        "selected_record_id": row["record_id"], "record": row,
        "continuation": {"recorded_baseline": row["acceptance_claims"][0]["baseline"],
                         "recorded_next_step": row["recorded_next_step"]} if available else None,
        "age_seconds": age,
        "max_age_seconds": max_age, "reference_check": "not_performed", "reasons": reasons,
    }


def assess(row, max_age=86400, evaluated=None):
    evaluated = evaluated or now()
    reasons = []
    if row["status"] in ("stale", "done"):
        reasons.append("status_" + row["status"])
    if time_value(row["created_at"]) > evaluated:
        reasons.append("record_time_future")
    age = ((evaluated - time_value(row["context_as_of"])).total_seconds()
           if row["context_as_of"] is not None else None)
    if age is None:
        recency = "unknown"
        reasons.append("context_time_unknown")
    elif age < 0:
        recency = "future"
        reasons.append("context_time_future")
    else:
        recency = "stale" if row["status"] == "stale" or age > max_age else "within_window"
        if age > max_age:
            reasons.append("context_too_old")
    claims = row["acceptance_claims"]
    complete = {tuple(c[k] for k in ("baseline", "reference", "accepted_at"))
                for c in claims if all(c[k] is not None for k in
                                       ("baseline", "reference", "accepted_at"))}
    if len(complete) > 1:
        acceptance = "conflicting"
    elif any(any(v is None for v in c.values()) for c in claims):
        acceptance = "incomplete"
    else:
        acceptance = "recorded" if claims else "missing"
    if acceptance != "recorded":
        reasons.append("acceptance_" + acceptance)
    if any(c["accepted_at"] is not None and time_value(c["accepted_at"]) > evaluated
           for c in claims):
        reasons.append("acceptance_time_future")
    evidence = row["evidence"]
    if not evidence:
        reasons.append("evidence_missing")
    if any(e["observed_at"] is None for e in evidence):
        reasons.append("evidence_time_unknown")
    if any(e["observed_at"] is not None and time_value(e["observed_at"]) > evaluated
           for e in evidence):
        reasons.append("evidence_time_future")
    return recency, acceptance, reasons, age
