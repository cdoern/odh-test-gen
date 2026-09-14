# SCORER CALIBRATION: LOW QUALITY test (should score 2/10 - Rework)
#
# Issues demonstrated (compare with good-pytest-test.py for correct version):
# ❌ Coverage: 1/2 - Missing some expected results, has TODOs for specified requirements,
#                    and skips a precondition the active feature MUST provide (should fail)
# ❌ Assertions: 0/2 - Generic "false-green" assertions, no messages, no feature-specific signal
# ❌ Conventions: 1/2 - Uses invented marker not in repo's pytest.ini
# ❌ Test Data: 0/2 - Uses placeholder "test-model" instead of exact ID from TC
# ❌ Code Quality: 0/2 - Excessive TODOs for things specified in TC, fabricated helper,
#                        unbounded stream loop, shell-injection in helper
#
# Tiger Team has no pytest rules yet - this calibration is standalone.

import pytest


@pytest.mark.p0  # Bad - marker invented, not from repo conventions
def test_retrieve_tool_calling_metadata(api_client):
    """TC-E2E-001: Verify that the API returns complete tool-calling metadata."""
    # Arrange
    model_id = "test-model"  # Placeholder instead of exact ID from TC

    # Act
    response = get_model_metadata(api_client, model_id)  # Fabricated helper not in repo

    # Assert
    assert response is not None  # Generic assertion
    assert response.status_code == 200  # No message - "false green": passes for ANY working backend,
    #                                     never checks the feature-under-test is actually present

    # TODO: Check tool_calling_supported field  # TC specifies this - shouldn't be TODO
    # TODO: Verify required_cli_args  # TC specifies this - shouldn't be TODO
    # TODO: Check chat_template_path  # TC specifies this - shouldn't be TODO


def test_gemini_streaming_completion(api_client):
    """TC-E2E-002: Verify the remote::gemini provider streams chat completions."""
    # Arrange
    models = api_client.models.list()
    gemini = [m for m in models if "gemini" in m.id]
    if not gemini:
        # Bad - the active provider MUST register a model; its absence is a real defect.
        # This should be pytest.fail(...), not a silent skip that hides a broken activation gate.
        pytest.skip("no gemini model found")

    # Act
    stream = api_client.chat.completions.create(model=gemini[0].id, messages=[], stream=True)

    # Assert
    chunks = []
    for chunk in stream:  # Bad - unbounded loop; a non-terminating stream hangs the suite
        chunks.append(chunk)
    assert len(chunks) > 0  # Generic "false green" - any stream produces chunks


def get_model_metadata(client, model_id):
    """Fabricated helper function that doesn't exist in repository."""
    import subprocess

    # Bad - CWE-78 shell injection: model_id is interpolated straight into sh -c
    subprocess.run(f"echo probing {model_id}", shell=True, check=False)
    return client.get(f"/models/{model_id}")
