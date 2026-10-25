"""Operator-selected browser approval rules. The model cannot grant approval."""

import hashlib
import json

from browser import DECLARATIONS, MUTATING_TOOLS


def action_digest(name, arguments):
    encoded = json.dumps({"name": name, "arguments": arguments}, sort_keys=True, ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_policy(policy):
    if not isinstance(policy, dict) or set(policy) != {"rules"} or not isinstance(policy["rules"], list) or not policy["rules"]:
        raise ValueError("Approval policy must be an object with a non-empty rules list")
    allowed = {item["name"]: item["parameters"]["properties"] for item in DECLARATIONS
               if item["name"] in MUTATING_TOOLS}
    for rule in policy["rules"]:
        if not isinstance(rule, dict) or set(rule) != {"tool", "match"}:
            raise ValueError("Each approval rule needs exactly tool and match")
        if not isinstance(rule["tool"], str) or rule["tool"] not in allowed or not isinstance(rule["match"], dict):
            raise ValueError("Approval rules support only declared browser mutation tools")
        properties = allowed[rule["tool"]]
        for key, value in rule["match"].items():
            if key == "reason" or key not in properties or not isinstance(value, str) or not value.strip():
                raise ValueError("Approval match fields must be non-empty strings from the tool's arguments, excluding reason")
    return policy


def matching_rule(policy, name, arguments):
    if policy is None:
        return None
    if name == "browser_fill":
        arguments = {"role": "textbox", **arguments}
    return next((rule for rule in policy["rules"] if rule["tool"] == name
                 and all(arguments.get(key) == value for key, value in rule["match"].items())), None)


def validate_decision(pending, decision):
    approval = pending.get("approval") if pending else None
    if not approval or approval["status"] != "pending":
        if decision:
            raise ValueError("No pending approval matches this decision")
        return
    if not decision or decision[0] not in {"approve", "reject"} or decision[1] != approval["id"]:
        raise ValueError(f"Use --approve {approval['id']} or --reject {approval['id']} for this exact pending action")
    if action_digest(pending["name"], pending["arguments"]) != approval["action_sha256"]:
        raise ValueError("Pending action no longer matches the requested approval")


def reject_pending(log, state, decision):
    """Cancel a detached approval without opening a browser or calling a model."""
    from state import save_json
    validate_decision(state.get("pending"), decision)
    if decision[0] != "reject":
        raise ValueError("Expected a rejection")
    pending = state["pending"]
    result = {"ok": False, "error": "User rejected this action; it was not executed",
              "approval_id": decision[1], "step": pending["step"]}
    log.record("resumed", previous_status=state["status"], decision=decision)
    log.record("approval_decision", step=pending["step"], approval_id=decision[1], decision="reject")
    log.record("tool_result", step=pending["step"], name=pending["name"], result=result)
    state["history"].append({"step": pending["step"], "name": pending["name"], "arguments": pending["arguments"], "result": result})
    state.update(status="cancelled", pending=None, error=None)
    outcome = {"status": "cancelled", "summary": "User rejected the pending action. It was not executed.",
               **{key: state[key] for key in ("requests", "tokens", "steps")}}
    save_json(log.directory / "checkpoint.json", state)
    log.record("state", status="cancelled", summary=outcome["summary"])
    log.result(outcome)
    return outcome
