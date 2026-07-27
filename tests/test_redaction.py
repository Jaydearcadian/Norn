from app.redaction import redact


def test_redacts_credentials_and_bearer_tokens():
    value = {"authorization": "Bearer abc.def", "nested": {"password": "secret"}, "message": "Bearer abcdef"}
    result = redact(value)
    assert result["authorization"] == "[REDACTED]"
    assert result["nested"]["password"] == "[REDACTED]"
    assert "abcdef" not in result["message"]
