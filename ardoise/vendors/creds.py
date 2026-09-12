"""Credential resolution: env → (later: 1Password / keychain).

Secrets stay in process memory. They are never written to the ledger,
queue, statements, or export.
"""

from __future__ import annotations

import os
from typing import Iterable

from ardoise.vendors.contract import (
    CredentialField,
    CredentialSpec,
    ResolvedField,
)

# Resolution order. `op` and `keychain` are reserved stubs.
CHAIN = ("env", "op", "keychain")


def _env_names(field: CredentialField) -> tuple[str, ...]:
    names = (field.env, *field.alt_envs)
    return tuple(name for name in names if name)


def _from_env(field: CredentialField) -> str | None:
    for name in _env_names(field):
        raw = os.environ.get(name)
        if raw and str(raw).strip():
            return str(raw).strip()
    return None


def _from_op(_field: CredentialField) -> str | None:
    # Optional later (1Password CLI). Do not shell out in Phase 2.
    return None


def _from_keychain(_field: CredentialField) -> str | None:
    # Optional later (OS keychain). Do not touch the keyring in Phase 2.
    return None


_SOURCES = {
    "env": _from_env,
    "op": _from_op,
    "keychain": _from_keychain,
}


def resolve_field(field: CredentialField) -> tuple[ResolvedField, str | None]:
    """Return public metadata plus the secret (secret is memory-only)."""
    for source in CHAIN:
        getter = _SOURCES[source]
        secret = getter(field)
        if secret:
            meta = ResolvedField(
                key=field.key,
                env=field.env,
                purpose=field.purpose,
                present=True,
                source=source,
                optional=field.optional,
            )
            return meta, secret
    meta = ResolvedField(
        key=field.key,
        env=field.env,
        purpose=field.purpose,
        present=False,
        source=None,
        optional=field.optional,
    )
    return meta, None


def resolve_status(spec: CredentialSpec) -> tuple[ResolvedField, ...]:
    return tuple(resolve_field(field)[0] for field in spec.fields)


def resolve(spec: CredentialSpec) -> dict[str, str]:
    """Map field.key → secret for fields that resolve. Do not persist."""
    found: dict[str, str] = {}
    for field in spec.fields:
        _meta, secret = resolve_field(field)
        if secret:
            found[field.key] = secret
    return found


def any_resolved(spec: CredentialSpec) -> bool:
    return any(item.present for item in resolve_status(spec))


def required_missing(spec: CredentialSpec) -> tuple[ResolvedField, ...]:
    return tuple(
        item
        for item in resolve_status(spec)
        if (not item.optional) and (not item.present)
    )


def iter_fields(spec: CredentialSpec) -> Iterable[CredentialField]:
    return spec.fields
