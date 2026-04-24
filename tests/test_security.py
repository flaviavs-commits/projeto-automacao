import unittest
from hashlib import sha1, sha256
from hmac import new as hmac_new

from app.core.security import verify_meta_signature


class SecurityTests(unittest.TestCase):
    def test_verify_meta_signature_valid_sha256(self) -> None:
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

    def test_verify_meta_signature_accepts_meta_escaped_unicode_payload(self) -> None:
        body = b'{"name":"Fl\xc3\xa1via"}'
        escaped_body = b'{"name":"Fl\\u00e1via"}'
        secret = "top-secret"
        digest = hmac_new(secret.encode("utf-8"), escaped_body, sha256).hexdigest()
        header = f"sha256={digest}"
        self.assertTrue(
            verify_meta_signature(
                body=body,
                signature_header=header,
                app_secret=secret,
            )
        )

    def test_verify_meta_signature_accepts_legacy_escaped_ascii_payload(self) -> None:
        body = b'{"message":"a/b<%@>"}'
        escaped_body = b'{"message":"a\\/b\\u003c\\u0025\\u0040\\u003e"}'
        secret = "top-secret"
        digest = hmac_new(secret.encode("utf-8"), escaped_body, sha256).hexdigest()
        header = f"sha256={digest}"
        self.assertTrue(
            verify_meta_signature(
                body=body,
                signature_header=header,
                app_secret=secret,
            )
        )

    def test_verify_meta_signature_accepts_sha1_header(self) -> None:
        body = b'{"hello":"world"}'
        secret = "top-secret"
        digest = hmac_new(secret.encode("utf-8"), body, sha1).hexdigest()
        header = f"sha1={digest}"
        self.assertTrue(
            verify_meta_signature(
                body=body,
                signature_header=header,
                app_secret=secret,
            )
        )

    def test_verify_meta_signature_accepts_quoted_digest(self) -> None:
        body = b'{"hello":"world"}'
        secret = "top-secret"
        digest = hmac_new(secret.encode("utf-8"), body, sha256).hexdigest()
        header = f'sha256="{digest}"'
        self.assertTrue(
            verify_meta_signature(
                body=body,
                signature_header=header,
                app_secret=secret,
            )
        )

    def test_verify_meta_signature_accepts_digest_with_suffix(self) -> None:
        body = b'{"hello":"world"}'
        secret = "top-secret"
        digest = hmac_new(secret.encode("utf-8"), body, sha256).hexdigest()
        header = f"sha256={digest},sha1=deadbeef"
        self.assertTrue(
            verify_meta_signature(
                body=body,
                signature_header=header,
                app_secret=secret,
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
