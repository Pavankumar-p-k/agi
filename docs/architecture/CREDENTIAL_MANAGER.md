Credential Manager (short design)

Goal
----
Provide a single, testable subsystem that reports credential availability and provides values to trusted runtime code only. Prevents runtime surprises (decrypt failures) and lets the planner know capability readiness before execution.

Minimal components
------------------
- CredentialManager (core.credentials.manager.CredentialManager)
  - get(key) -> Optional[str]
  - has(key) -> bool
  - register_provider(provider)
- Providers
  - EnvCredentialProvider (dev and simple deployments)
  - EncryptedCredentialProvider (production: decrypt from disk/vault)
  - OAuthCredentialProvider (fetch/refresh tokens)

Dev-mode behavior
-----------------
- server.dev_mode (JARVIS_DEV_MODE) bypasses decryption and prefers env vars.
- Useful for local development and CI; must be disabled in production.

Checklist to finish
-------------------
- Add EncryptedCredentialProvider that defers to core.secret_storage.decrypt and reports detailed states (DECRYPT_FAILED, EXPIRED)
- Replace direct secret lookups across code with CredentialManager.has/get
- Make Planner query capability readiness from CredentialManager before executing tool calls
- Add automated tests for credential states and dev-mode bypass

Security notes
--------------
- Never expose raw secrets to models. Only expose availability/metadata.
- Treat env and local plaintext as dev-only; use Vault/KMS in production.

