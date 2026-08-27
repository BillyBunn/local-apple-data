from __future__ import annotations

import importlib.util
from pathlib import Path


_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "verify_runtime.py"
_SPEC = importlib.util.spec_from_file_location("verify_runtime_script", _SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
_mcp_mail_advanced_iso_contract = _MODULE._mcp_mail_advanced_iso_contract


def test_mcp_mail_advanced_iso_contract_requires_exact_synthetic_success() -> None:
    success = _mcp_mail_advanced_iso_contract(
        {
            "status": "ok",
            "source": "mail",
            "result_count": 1,
            "results": [{"handle": "mail:message:v2:synthetic"}],
            "query": {"after": 1782432000.0, "before": 1782863999.999},
            "warnings": [],
        }
    )
    unavailable = _mcp_mail_advanced_iso_contract(
        {
            "status": "degraded",
            "result_count": 0,
            "warnings": [{"code": "mail_store_unavailable"}],
        }
    )
    unrelated_error = _mcp_mail_advanced_iso_contract(
        {
            "status": "error",
            "result_count": 0,
            "warnings": [{"code": "invalid_date_bound"}],
        }
    )

    assert success["mcp_mail_advanced_iso_contract_valid"] is True
    assert success["mcp_mail_advanced_iso_after"] == 1782432000.0
    assert unavailable["mcp_mail_advanced_iso_contract_valid"] is False
    assert unavailable["mcp_mail_advanced_iso_warning"] == "mail_store_unavailable"
    assert unrelated_error["mcp_mail_advanced_iso_contract_valid"] is False
