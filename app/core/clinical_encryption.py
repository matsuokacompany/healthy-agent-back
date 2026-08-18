import json
import os
from dataclasses import dataclass
from typing import Mapping, Protocol

import boto3
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


AES_256_KEY_BYTES = 32
AES_GCM_NONCE_BYTES = 12
ALGORITHM = "AES-256-GCM"
ENVELOPE_VERSION = 1


class ClinicalEncryptionError(RuntimeError):
    """A clinical value could not be encrypted or authenticated."""


class ClinicalEncryptionConfigurationError(ClinicalEncryptionError):
    """Clinical encryption is missing required or safe configuration."""


@dataclass(frozen=True)
class GeneratedDataKey:
    plaintext: bytes
    encrypted: bytes
    key_id: str


@dataclass(frozen=True)
class ClinicalCiphertext:
    ciphertext: bytes
    nonce: bytes
    encrypted_data_key: bytes
    key_id: str
    key_version: str
    algorithm: str = ALGORITHM
    envelope_version: int = ENVELOPE_VERSION


class DataKeyProvider(Protocol):
    def generate_data_key(self, encryption_context: Mapping[str, str]) -> GeneratedDataKey:
        ...

    def decrypt_data_key(
        self,
        encrypted_data_key: bytes,
        key_id: str,
        encryption_context: Mapping[str, str],
    ) -> bytes:
        ...


class AwsKmsDataKeyProvider:
    """Generate envelope-encryption data keys using an AWS KMS key."""

    def __init__(self, key_id: str, region_name: str, *, kms_client=None):
        if not key_id or not region_name:
            raise ClinicalEncryptionConfigurationError("AWS KMS key ID and region are required")
        self.key_id = key_id
        self.kms_client = kms_client or boto3.client("kms", region_name=region_name)

    def generate_data_key(self, encryption_context: Mapping[str, str]) -> GeneratedDataKey:
        try:
            response = self.kms_client.generate_data_key(
                KeyId=self.key_id,
                KeySpec="AES_256",
                EncryptionContext=dict(encryption_context),
            )
            plaintext = bytes(response["Plaintext"])
            encrypted = bytes(response["CiphertextBlob"])
            resolved_key_id = str(response["KeyId"])
        except Exception as exc:
            raise ClinicalEncryptionError("AWS KMS could not generate a clinical data key") from exc
        if len(plaintext) != AES_256_KEY_BYTES or not encrypted:
            raise ClinicalEncryptionError("AWS KMS returned an invalid clinical data key")
        return GeneratedDataKey(plaintext=plaintext, encrypted=encrypted, key_id=resolved_key_id)

    def decrypt_data_key(
        self,
        encrypted_data_key: bytes,
        key_id: str,
        encryption_context: Mapping[str, str],
    ) -> bytes:
        if not encrypted_data_key or not key_id:
            raise ClinicalEncryptionError("The clinical data key envelope is incomplete")
        try:
            response = self.kms_client.decrypt(
                CiphertextBlob=encrypted_data_key,
                KeyId=key_id,
                EncryptionContext=dict(encryption_context),
            )
            plaintext = bytes(response["Plaintext"])
        except Exception as exc:
            raise ClinicalEncryptionError("AWS KMS could not decrypt the clinical data key") from exc
        if len(plaintext) != AES_256_KEY_BYTES:
            raise ClinicalEncryptionError("AWS KMS returned an invalid clinical data key")
        return plaintext


class LocalDataKeyProvider:
    """In-memory provider for automated tests; forbidden in production."""

    _WRAP_AAD = b"healthy-agent:local-data-key:v1"

    def __init__(self, wrapping_key: bytes, *, environment: str = "test"):
        if environment.lower() == "production":
            raise ClinicalEncryptionConfigurationError("The local clinical key provider is forbidden in production")
        if len(wrapping_key) != AES_256_KEY_BYTES:
            raise ClinicalEncryptionConfigurationError("The local wrapping key must contain exactly 32 bytes")
        self.wrapping_key = wrapping_key

    def generate_data_key(self, encryption_context: Mapping[str, str]) -> GeneratedDataKey:
        plaintext = os.urandom(AES_256_KEY_BYTES)
        nonce = os.urandom(AES_GCM_NONCE_BYTES)
        wrapped = nonce + AESGCM(self.wrapping_key).encrypt(nonce, plaintext, self._WRAP_AAD)
        return GeneratedDataKey(plaintext=plaintext, encrypted=wrapped, key_id="local-test-v1")

    def decrypt_data_key(
        self,
        encrypted_data_key: bytes,
        key_id: str,
        encryption_context: Mapping[str, str],
    ) -> bytes:
        if key_id != "local-test-v1" or len(encrypted_data_key) <= AES_GCM_NONCE_BYTES:
            raise ClinicalEncryptionError("The local clinical data key envelope is invalid")
        nonce = encrypted_data_key[:AES_GCM_NONCE_BYTES]
        ciphertext = encrypted_data_key[AES_GCM_NONCE_BYTES:]
        try:
            return AESGCM(self.wrapping_key).decrypt(nonce, ciphertext, self._WRAP_AAD)
        except InvalidTag as exc:
            raise ClinicalEncryptionError("The local clinical data key could not be authenticated") from exc


class ClinicalEncryptionService:
    def __init__(self, data_key_provider: DataKeyProvider, *, active_key_version: str):
        if not active_key_version:
            raise ClinicalEncryptionConfigurationError("An active clinical key version is required")
        self.data_key_provider = data_key_provider
        self.active_key_version = active_key_version

    def encrypt(self, plaintext: str, *, context: Mapping[str, str]) -> ClinicalCiphertext:
        normalized_context = self._validated_context(context)
        data_key = self.data_key_provider.generate_data_key(normalized_context)
        nonce = os.urandom(AES_GCM_NONCE_BYTES)
        aad = self._aad(normalized_context, self.active_key_version)
        try:
            ciphertext = AESGCM(data_key.plaintext).encrypt(nonce, plaintext.encode("utf-8"), aad)
        except Exception as exc:
            raise ClinicalEncryptionError("The clinical value could not be encrypted") from exc
        return ClinicalCiphertext(
            ciphertext=ciphertext,
            nonce=nonce,
            encrypted_data_key=data_key.encrypted,
            key_id=data_key.key_id,
            key_version=self.active_key_version,
        )

    def decrypt(self, encrypted: ClinicalCiphertext, *, context: Mapping[str, str]) -> str:
        if encrypted.algorithm != ALGORITHM or encrypted.envelope_version != ENVELOPE_VERSION:
            raise ClinicalEncryptionError("The clinical encryption envelope version is unsupported")
        if len(encrypted.nonce) != AES_GCM_NONCE_BYTES:
            raise ClinicalEncryptionError("The clinical encryption nonce is invalid")
        normalized_context = self._validated_context(context)
        data_key = self.data_key_provider.decrypt_data_key(
            encrypted.encrypted_data_key,
            encrypted.key_id,
            normalized_context,
        )
        aad = self._aad(normalized_context, encrypted.key_version)
        try:
            plaintext = AESGCM(data_key).decrypt(encrypted.nonce, encrypted.ciphertext, aad)
            return plaintext.decode("utf-8")
        except (InvalidTag, UnicodeDecodeError) as exc:
            raise ClinicalEncryptionError("The clinical value could not be authenticated") from exc

    @staticmethod
    def _validated_context(context: Mapping[str, str]) -> dict[str, str]:
        required = {"table", "record_id", "patient_id", "field"}
        normalized = {str(key): str(value) for key, value in context.items()}
        if required - normalized.keys() or any(not normalized[key] for key in required):
            raise ClinicalEncryptionConfigurationError("The clinical encryption context is incomplete")
        return normalized

    @staticmethod
    def _aad(context: Mapping[str, str], key_version: str) -> bytes:
        payload = {
            "domain": "healthy-agent:clinical-data",
            "envelope_version": ENVELOPE_VERSION,
            "key_version": key_version,
            "context": dict(context),
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
