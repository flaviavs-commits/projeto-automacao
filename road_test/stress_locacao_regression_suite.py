from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from chat_railway_prod import (
    DEFAULT_BASE_URL,
    DEFAULT_PHONE_NUMBER_ID,
    DEFAULT_PROFILE_NAME,
    DEFAULT_WA_ID,
    send_message_and_wait_reply,
)
from stress_locacao_suite import StressCase, _build_pool, _evaluate


def _default_previous_report(output_dir: Path) -> Path:
    candidates = sorted(output_dir.glob("stress_locacao_*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    if not candidates:
        raise FileNotFoundError("Nenhum relatorio stress_locacao_*.json encontrado em .qa_tmp")
    return candidates[0]


def _load_previous_report(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("Relatorio invalido: payload raiz nao e objeto JSON")
    if not isinstance(payload.get("results"), list):
        raise RuntimeError("Relatorio invalido: campo results ausente")
    return payload


def _case_from_payload(raw_case: dict[str, Any]) -> StressCase:
    return StressCase(
        id=str(raw_case.get("id") or "").strip(),
        category=str(raw_case.get("category") or "").strip(),
        text=str(raw_case.get("text") or "").strip(),
        expected=str(raw_case.get("expected") or "").strip(),
    )


def _build_new_cases() -> list[StressCase]:
    return [
        StressCase(
            id="new_paid_change_1",
            category="paid_changes",
            text="paguei a reserva e preciso alterar a data para semana que vem",
            expected="rule_handoff",
        ),
        StressCase(
            id="new_paid_change_2",
            category="paid_changes",
            text="quero trocar o horario de uma reserva ja paga",
            expected="rule_handoff",
        ),
        StressCase(
            id="new_risk_people_1",
            category="risk_people",
            text="somos 11 para gravar um clipe, pode liberar?",
            expected="rule_handoff",
        ),
        StressCase(
            id="new_risk_people_2",
            category="risk_people",
            text="grupo com 6 integrantes para ensaio",
            expected="rule_handoff",
        ),
        StressCase(
            id="new_location_1",
            category="location",
            text="qual o endereco completo de voces?",
            expected="generic_model",
        ),
        StressCase(
            id="new_location_2",
            category="location",
            text="fica em volta redonda mesmo? qual bairro?",
            expected="generic_model",
        ),
        StressCase(
            id="new_audio_1",
            category="audio",
            text="audio e microfone estao inclusos na locacao?",
            expected="generic_model",
        ),
        StressCase(
            id="new_audio_2",
            category="audio",
            text="posso usar lapela de voces no estudio?",
            expected="generic_model",
        ),
        StressCase(
            id="new_structure_1",
            category="structure",
            text="o estudio tem ar condicionado e quantos softboxes?",
            expected="generic_model",
        ),
        StressCase(
            id="new_generic_1",
            category="generic",
            text="sou novo cliente, como funciona para reservar e pagar?",
            expected="generic_model",
        ),
    ]


def _dedupe_cases(cases: list[StressCase]) -> list[StressCase]:
    seen: set[tuple[str, str]] = set()
    unique: list[StressCase] = []
    for case in cases:
        signature = (case.category, " ".join(case.text.lower().split()))
        if signature in seen:
            continue
        seen.add(signature)
        unique.append(case)
    return unique


def _select_regression_cases(previous_payload: dict[str, Any], base_pool: list[StressCase]) -> tuple[list[StressCase], dict[str, int]]:
    base_by_id = {case.id: case for case in base_pool}
    previous_results = previous_payload["results"]

    passed_by_category: dict[str, list[StressCase]] = {}
    failed_cases: list[StressCase] = []

    for result in previous_results:
        if not isinstance(result, dict):
            continue
        raw_case = result.get("case")
        if not isinstance(raw_case, dict):
            continue
        case = _case_from_payload(raw_case)
        if not case.id or not case.category or not case.text:
            continue
        case = base_by_id.get(case.id, case)

        passed = bool(result.get("passed"))
        if passed:
            passed_by_category.setdefault(case.category, []).append(case)
        else:
            failed_cases.append(case)

    selected_passed: list[StressCase] = []
    for category in sorted(passed_by_category.keys()):
        candidates = sorted(passed_by_category[category], key=lambda item: item.id)
        selected_passed.append(candidates[0])

    new_cases = _build_new_cases()
    selected = _dedupe_cases([*selected_passed, *failed_cases, *new_cases])
    info = {
        "passed_sampled": len(selected_passed),
        "failed_repeated": len(failed_cases),
        "new_cases": len(new_cases),
        "total_selected": len(selected),
    }
    return selected, info


def _write_reports(payload: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"stress_locacao_regression_{stamp}.json"
    md_path = output_dir / f"stress_locacao_regression_{stamp}.md"

    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = payload["summary"]
    lines = [
        "# Stress Test Locacao - Regressao",
        "",
        f"- previous_report: {payload['selection']['previous_report']}",
        f"- passed_sampled: {payload['selection']['passed_sampled']}",
        f"- failed_repeated: {payload['selection']['failed_repeated']}",
        f"- new_cases: {payload['selection']['new_cases']}",
        f"- total_cases: {summary['total_cases']}",
        f"- passed: {summary['passed']}",
        f"- failed: {summary['failed']}",
        f"- pass_rate: {summary['pass_rate_pct']:.2f}%",
        "",
        "## Por categoria",
        "",
    ]
    for item in summary["by_category"]:
        lines.append(f"- {item['category']}: {item['passed']}/{item['total']} ({item['pass_rate_pct']:.2f}%)")

    lines.extend(["", "## Principais falhas", ""])
    for issue, count in summary["top_issues"]:
        lines.append(f"- {issue}: {count}")

    md_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return json_path, md_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bateria de regressao baseada no ultimo stress test de locacao.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--wa-id", default=DEFAULT_WA_ID)
    parser.add_argument("--profile-name", default=DEFAULT_PROFILE_NAME)
    parser.add_argument("--phone-number-id", default=DEFAULT_PHONE_NUMBER_ID)
    parser.add_argument(
        "--app-secret",
        default=(os.getenv("META_APP_SECRET", "").strip() or os.getenv("INSTAGRAM_APP_SECRET", "").strip()),
    )
    parser.add_argument("--previous-report", default="", help="Caminho para relatorio stress_locacao_*.json base")
    parser.add_argument("--reply-timeout", type=int, default=90)
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--http-timeout", type=float, default=45.0)
    parser.add_argument("--output-dir", default=".qa_tmp")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    previous_report = Path(args.previous_report) if str(args.previous_report).strip() else _default_previous_report(output_dir)
    previous_payload = _load_previous_report(previous_report)

    pool = _build_pool()
    selected, selection_info = _select_regression_cases(previous_payload, pool)

    evaluations: list[dict[str, Any]] = []
    issue_counter: dict[str, int] = {}
    by_category: dict[str, dict[str, int]] = {}

    with httpx.Client(timeout=max(15.0, float(args.http_timeout)), trust_env=False) as client:
        for idx, case in enumerate(selected, 1):
            print(f"[{idx}/{len(selected)}] {case.id} | {case.category} | {case.text}")
            try:
                result = send_message_and_wait_reply(
                    client=client,
                    base_url=args.base_url,
                    wa_id=args.wa_id,
                    profile_name=args.profile_name,
                    phone_number_id=str(args.phone_number_id or "").strip(),
                    app_secret=str(args.app_secret or "").strip(),
                    user_text=case.text,
                    timeout_seconds=int(args.reply_timeout),
                    poll_interval_seconds=float(args.poll_interval),
                )
                passed, issues = _evaluate(case, result)
                result_payload = asdict(result)
                status = "ok"
                error = ""
            except Exception as exc:  # noqa: BLE001
                passed = False
                issues = [f"request_error:{type(exc).__name__}"]
                result_payload = {}
                status = "error"
                error = str(exc)

            for issue in issues:
                issue_counter[issue] = issue_counter.get(issue, 0) + 1

            bucket = by_category.setdefault(case.category, {"total": 0, "passed": 0})
            bucket["total"] += 1
            if passed:
                bucket["passed"] += 1

            evaluations.append(
                {
                    "case": asdict(case),
                    "status": status,
                    "error": error,
                    "passed": passed,
                    "issues": issues,
                    "result": result_payload,
                }
            )

    total = len(evaluations)
    passed_total = sum(1 for item in evaluations if item["passed"])
    by_category_list = []
    for category in sorted(by_category.keys()):
        total_cat = by_category[category]["total"]
        passed_cat = by_category[category]["passed"]
        by_category_list.append(
            {
                "category": category,
                "total": total_cat,
                "passed": passed_cat,
                "failed": total_cat - passed_cat,
                "pass_rate_pct": (passed_cat / total_cat * 100.0) if total_cat else 0.0,
            }
        )

    payload = {
        "run_at_utc": datetime.now(timezone.utc).isoformat(),
        "selection": {
            "previous_report": str(previous_report),
            **selection_info,
        },
        "config": {
            "base_url": args.base_url,
            "reply_timeout": args.reply_timeout,
            "poll_interval": args.poll_interval,
        },
        "summary": {
            "total_cases": total,
            "passed": passed_total,
            "failed": total - passed_total,
            "pass_rate_pct": (passed_total / total * 100.0) if total else 0.0,
            "by_category": by_category_list,
            "top_issues": sorted(issue_counter.items(), key=lambda item: item[1], reverse=True)[:15],
        },
        "results": evaluations,
    }

    json_path, md_path = _write_reports(payload, output_dir)
    print("")
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    print(f"json_report={json_path}")
    print(f"md_report={md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
