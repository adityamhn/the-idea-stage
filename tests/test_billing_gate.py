"""The payments kill-switch. Offline — no Razorpay, no DB, no network.

`configured()` is the single gate every payment surface consults (the /billing/packs
`configured` flag the UI reads, the /billing/checkout 503, and the startup
webhook-secret enforcement). It must be False unless PAYMENTS_ENABLED is explicitly
on AND the Razorpay keys are present, so a fresh deploy never accepts payments before
approval.
"""

from __future__ import annotations

import pytest

from api import billing

_KEYS = {"RAZORPAY_KEY_ID": "rzp_test_x", "RAZORPAY_KEY_SECRET": "secret_x"}


def _set(monkeypatch, **env: str | None) -> None:
    for k, v in env.items():
        if v is None:
            monkeypatch.delenv(k, raising=False)
        else:
            monkeypatch.setenv(k, v)


def test_disabled_by_default_even_with_keys(monkeypatch):
    _set(monkeypatch, PAYMENTS_ENABLED=None, **_KEYS)
    assert billing.payments_enabled() is False
    assert billing.configured() is False


def test_enabled_with_flag_and_keys(monkeypatch):
    _set(monkeypatch, PAYMENTS_ENABLED="true", **_KEYS)
    assert billing.payments_enabled() is True
    assert billing.configured() is True


def test_flag_on_but_keys_missing_stays_off(monkeypatch):
    _set(monkeypatch, PAYMENTS_ENABLED="true", RAZORPAY_KEY_ID=None, RAZORPAY_KEY_SECRET=None)
    assert billing.payments_enabled() is True
    assert billing.configured() is False


@pytest.mark.parametrize("value", ["true", "TRUE", "True", " yes ", "1", "on", "On"])
def test_truthy_values_enable(monkeypatch, value):
    _set(monkeypatch, PAYMENTS_ENABLED=value)
    assert billing.payments_enabled() is True


@pytest.mark.parametrize("value", ["false", "0", "no", "off", "", "  "])
def test_falsy_values_keep_disabled(monkeypatch, value):
    _set(monkeypatch, PAYMENTS_ENABLED=value)
    assert billing.payments_enabled() is False
