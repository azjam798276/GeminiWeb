from geminiweb_provider.crypto import decrypt_bytes, encrypt_bytes


def test_encrypt_decrypt_roundtrip():
    key = "rYdGvZpTz4l7mOZ1m3cQ3EJ4xJ8k2bq7d2H1m1v7QkA="
    data = b"hello"
    token = encrypt_bytes(key, data)
    out = decrypt_bytes(key, token)
    assert out == data

