"""Guardrails on the proposed action: replica bounds, remedies that cannot fix the observed failure, and ACCEPT."""

import pytest

from ai_sre.agents.graph import (
    MAX_ACTION_REPLICAS,
    classify_verifier_state,
    validate_recommended_action,
)

NAMESPACE = "online-boutique"


def _tool_calls(deployment="cartservice", event_message="Back-off restarting failed container", other_failure=None):
    calls = [
        {"tool": "list_deployments", "args": {"namespace": NAMESPACE},
         "result": [{"name": deployment, "desired_replicas": 1}, {"name": "frontend", "desired_replicas": 1}]},
        {"tool": "get_pod_events", "args": {"namespace": NAMESPACE, "pod_name": f"{deployment}-7d9f8-x2k"},
         "result": [{"reason": "Observed", "message": event_message}]},
    ]
    if other_failure:
        calls.append({"tool": "get_pod_events", "args": {"namespace": NAMESPACE, "pod_name": "frontend-5c6-abc"},
                      "result": [{"reason": "Failed", "message": other_failure}]})
    return calls


def _payload(action="restart_deployment", deployment="cartservice", replicas=None):
    return {"recommended_action": action, "action_namespace": NAMESPACE,
            "action_deployment_name": deployment, "action_replicas": replicas}


@pytest.mark.parametrize("replicas", [-1, MAX_ACTION_REPLICAS + 1, 1000, 10**6])
def test_replica_count_outside_the_allowed_range_is_cleared(replicas):
    validated, log = validate_recommended_action(_payload("scale_deployment", replicas=replicas), _tool_calls())

    assert validated["action_replicas"] is None
    assert any("outside" in entry for entry in log)


@pytest.mark.parametrize("replicas", [0, 1, 3, MAX_ACTION_REPLICAS])
def test_replica_count_inside_the_allowed_range_is_kept(replicas):
    validated, log = validate_recommended_action(_payload("scale_deployment", replicas=replicas), _tool_calls())

    assert validated["action_replicas"] == replicas
    assert log == []


@pytest.mark.parametrize("message", [
    "Failed to pull image registry.invalid/app:never: no such host",
    "ErrImagePull: manifest unknown",
    "CreateContainerConfigError: configmap app-config not found",
    "0/1 nodes are available: 1 Insufficient memory",
])
@pytest.mark.parametrize("action", ["restart_deployment", "scale_deployment"])
def test_action_is_dropped_when_it_cannot_fix_the_observed_failure(message, action):
    validated, log = validate_recommended_action(_payload(action, replicas=3), _tool_calls(event_message=message))

    assert validated["recommended_action"] == "none"
    assert validated["action_deployment_name"] is None
    assert any("cannot fix" in entry for entry in log)


def test_scale_is_dropped_for_a_crash_loop_but_restart_is_kept():
    crash = _tool_calls(event_message="CrashLoopBackOff: back-off restarting failed container")

    scaled, scale_log = validate_recommended_action(_payload("scale_deployment", replicas=3), crash)
    restarted, restart_log = validate_recommended_action(_payload("restart_deployment"), crash)

    assert scaled["recommended_action"] == "none" and scale_log
    assert restarted["recommended_action"] == "restart_deployment" and restart_log == []


def test_oomkilled_restart_is_kept():
    validated, log = validate_recommended_action(_payload("restart_deployment"), _tool_calls(event_message="OOMKilled exit code 137"))

    assert validated["recommended_action"] == "restart_deployment"
    assert log == []


def test_another_deployments_failure_does_not_block_the_action():
    calls = _tool_calls(other_failure="ImagePullBackOff: Failed to pull image")

    validated, log = validate_recommended_action(_payload("restart_deployment"), calls)

    assert validated["recommended_action"] == "restart_deployment"
    assert log == []


def _state(log, score=0.86):
    return {
        "tool_calls": _tool_calls(),
        "retrieved_chunks": [{"score": score, "chunk_id": "c", "source_file": "f.txt", "chunk_text": "t"}],
        "diagnosis_degraded": False,
        "log": log,
    }


def test_accept_requires_that_validation_did_not_intervene():
    clean = _state(["planner", "log_analysis", "fix_proposer"])
    intervened = _state(["planner", "log_analysis", "Validation: action was corrected", "fix_proposer"])

    assert classify_verifier_state(clean)[1] == "ACCEPT"
    assert classify_verifier_state(intervened)[1] == "REVIEW"


def test_a_weak_runbook_match_is_still_review_regardless_of_validation():
    assert classify_verifier_state(_state(["planner"], score=0.6))[1] == "REVIEW"
