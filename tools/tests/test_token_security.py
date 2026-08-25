import os
import stat

from text_to_google import save_credentials


class FakeCredentials:
    def to_json(self):
        return '{"token":"test-only-placeholder"}'


def test_save_credentials_restricts_token_to_owner(tmp_path):
    token = tmp_path / "token.json"
    save_credentials(FakeCredentials(), token)

    assert token.read_text() == '{"token":"test-only-placeholder"}'
    if os.name != "nt":
        assert stat.S_IMODE(token.stat().st_mode) == 0o600
