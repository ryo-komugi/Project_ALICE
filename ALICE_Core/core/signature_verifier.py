# Backward compatibility shim for core.signature_verifier -> gateway.signature
from gateway.signature import SignatureVerifier

__all__ = ["SignatureVerifier"]
