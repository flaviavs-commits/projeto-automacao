import unittest
from hashlib import sha256
from hmac import new as hmac_new

from app.core.security import verify_meta_signature


class SecurityTests(unittest.TestCase):
    def test_verify_meta_signature_valid(self) -> None:
        body = b'{"hello":"world"}'
        secret = "top-secret"
        digest = hmac_new(secret.encode("utf-8"), body, sha256).hexdigest()
        header = f"sha256={digest}"
        self.assertTrue(
            verify_meta_signature(
                body=body,
                signature_header=header,
                app_secret=secret,
            )
        )

    def test_verify_meta_signature_invalid_digest(self) -> None:
        body = b'{"hello":"world"}'
        self.assertFalse(
            verify_meta_signature(
                body=body,
                signature_header="sha256=deadbeef",
                app_secret="top-secret",
            )
        )

    def test_verify_meta_signature_no_secret_is_permissive(self) -> None:
        self.assertTrue(
            verify_meta_signature(
                body=b"{}",
                signature_header=None,
                app_secret="",
            )
        )


if __name__ == "__main__":
    unittest.main()
