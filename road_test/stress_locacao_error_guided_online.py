from __future__ import annotations

import argparse
import json
import os
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from chat_railway_prod import (
    DEFAULT_BASE_URL,
    DEFAULT_PHONE_NUMBER_ID,
    DEFAULT_PROFILE_NAME,
    DEFAULT_WA_ID,
    ReplyResult,
    send_message_and_wait_reply,
)


@dataclass(frozen=True)
class GuidedCase:
    id: str
    category: str
    text: str
    expected: str


def _normalize(value: str) -> str:
    lowered = str(value or "").lower()
    ascii_value = unicodedata.normalize("NFKD", lowered).encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_value.split())


def _variant_cases(
    *,
    prefix_seed: list[str],
    base_questions: list[str],
    category: str,
    expected: str,
    start_idx: int,
) -> list[GuidedCase]:
    cases: list[GuidedCase] = []
    idx = start_idx
    for question in base_questions:
        for prefix in prefix_seed:
            text = f"{prefix}{question}".strip()
            cases.append(
                GuidedCase(
                    id=f"{category}_{idx:03d}",
                    category=category,
                    text=text,
                    expected=expected,
                )
            )
            idx += 1
    return cases


def _build_pool() -> list[GuidedCase]:
    prefixes = [
        "",
        "boa tarde, ",
        "duvida rapida: ",
        "me ajuda por favor: ",
        "quero confirmar: ",
    ]

    location_questions = [
        "onde fica o estudio de voces?",
        "qual e o endereco completo?",
        "fica em volta redonda mesmo?",
        "tem estacionamento e acesso por escada?",
        "fica na rua ou em shopping?",
    ]
    audio_questions = [
        "voces oferecem microfone para gravacao?",
        "tem lapela incluida na locacao?",
        "audio esta incluso no pacote?",
        "tem mesa de som ou interface de audio?",
        "voces alugam equipamento de audio?",
    ]
    paid_change_questions = [
        "ja paguei a reserva e preciso trocar a data",
        "quero reagendar um horario que ja esta pago",
        "apos pagamento, consigo cancelar meu horario?",
    ]
    risk_questions = [
        "somos 7 pessoas para gravar um clipe",
        "queremos usar confete e glitter no ensaio",
        "vai 6 pessoas e um animal para foto",
    ]
    exploratory_questions = [
        "sou novo cliente, como funciona para reservar e pagar?",
        "nunca fui ai, pode me explicar como e a locacao?",
    ]
    explicit_schedule_questions = [
        "quero agendar para sexta as 18h, tem disponibilidade?",
        "consigo reservar amanha as 10h?",
    ]

    pool: list[GuidedCase] = []
    pool.extend(
        _variant_cases(
            prefix_seed=prefixes,
            base_questions=location_questions,
            category="location",
            expected="location_policy",
            start_idx=1,
        )
    )
    pool.extend(
        _variant_cases(
            prefix_seed=prefixes,
            base_questions=audio_questions,
            category="audio",
            expected="audio_policy",
            start_idx=1,
        )
    )
    pool.extend(
        _variant_cases(
            prefix_seed=prefixes,
            base_questions=paid_change_questions,
            category="paid_change",
            expected="handoff",
            start_idx=1,
        )
    )
    pool.extend(
        _variant_cases(
            prefix_seed=prefixes,
            base_questions=risk_questions,
            category="risk",
            expected="handoff",
            start_idx=1,
        )
    )
    pool.extend(
        _variant_cases(
            prefix_seed=prefixes,
            base_questions=exploratory_questions,
            category="exploratory",
            expected="not_schedule_rule",
            start_idx=1,
        )
    )
    pool.extend(
        _variant_cases(
            prefix_seed=prefixes,
            base_questions=explicit_schedule_questions,
            category="schedule",
            expected="schedule_rule",
            start_idx=1,
        )
    )

    if len(pool) != 100:
        raise RuntimeError(f"pool_size_mismatch expected=100 got={len(pool)}")
    return pool


def _evaluate(case: GuidedCase, result: ReplyResult) -> tuple[bool, list[str]]:
    issues: list[str] = []
    model = str(result.llm_model or "")
    reply = str(result.reply_text or "").strip()
    normalized_reply = _normalize(reply)

    if not reply:
        issues.append("empty_reply")
        return False, issues

    if case.expected == "location_policy":
        if "corifeu" not in normalized_reply:
            issues.append("location_missing_corifeu")
        if "jardim amalia" not in normalized_reply and "volta redonda" not in normalized_reply:
            issues.append("location_missing_city_context")
    elif case.expected == "audio_policy":
        if "audio" not in normalized_reply and "microfone" not in normalized_reply and "lapela" not in normalized_reply:
            issues.append("audio_missing_topic")
        if "nao" not in normalized_reply:
            issues.append("audio_missing_negative_constraint")
        if "estrutura fotografica" not in normalized_reply:
            issues.append("audio_missing_policy_context")
    elif case.expected == "handoff":
        if model != "rule_human_handoff":
            issues.append(f"expected_model=rule_human_handoff got={model}")
        if "equipe humana" not in normalized_reply:
            issues.append("handoff_missing_human_text")
    elif case.expected == "not_schedule_rule":
        if model == "rule_schedule_site_only":
            issues.append("unexpected_schedule_rule")
    elif case.expected == "schedule_rule":
        if model != "rule_schedule_site_only":
            issues.append(f"expected_model=rule_schedule_site_only got={model}")
        if "nao consigo confirmar horario manualmente" not in normalized_reply:
            issues.append("schedule_missing_manual_guard")
        if "fcvip.com.br" not in normalized_reply:
            issues.append("schedule_missing_link")
    else:
        issues.append(f"unknown_expected={case.expected}")

    return len(issues) == 0, issues


def _is_transient_unavailable(exc: Exception) -> bool:
    text = str(exc or "").lower()
    return "503" in text or "service unavailable" in text


def _write_reports(payload: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"stress_locacao_error_guided_100_{stamp}.json"
    md_path = output_dir / f"stress_locacao_error_guided_100_{stamp}.md"

    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines: list[str] = []
    lines.append("# Acertos")
    lines.append("")
    for item in payload["results"]:
        if not item.get("passed"):
            continue
        question = str(item["case"]["text"])
        answer = str(item.get("result", {}).get("reply_text") or "").strip()
        lines.append(f"Pergunta: {question}")
        lines.append(f"Resposta: {answer}")
        lines.append("")

    lines.append("# Erros")
    lines.append("")
    for item in payload["results"]:
        if item.get("passed"):
            continue
        question = str(item["case"]["text"])
        answer = str(item.get("result", {}).get("reply_text") or "").strip()
        lines.append(f"Pergunta: {question}")
        lines.append(f"Resposta: {answer}")
        lines.append("")

    md_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return json_path, md_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Bateria online de 100 testes guiada pelos erros mais frequentes do ultimo stress do LLM."
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--wa-id", default=DEFAULT_WA_ID)
    parser.add_argument("--profile-name", default=DEFAULT_PROFILE_NAME)
    parser.add_argument("--phone-number-id", default=DEFAULT_PHONE_NUMBER_ID)
    parser.add_argument(
        "--app-secret",
        default=(os.getenv("META_APP_SECRET", "").strip() or os.getenv("INSTAGRAM_APP_SECRET", "").strip()),
    )
    parser.add_argument("--reply-timeout", type=int, default=90)
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--http-timeout", type=float, default=45.0)
    parser.add_argument("--output-dir", default=".qa_tmp")
    parser.add_argument("--trust-env", action="store_true")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    app_secret = str(args.app_secret or "").strip()
    if not app_secret:
        print("Falha: informe --app-secret ou configure META_APP_SECRET.")
        return 2

    cases = _build_pool()
    evaluations: list[dict[str, Any]] = []
    issue_counter: dict[str, int] = {}
    by_category: dict[str, dict[str, int]] = {}

    with httpx.Client(timeout=max(15.0, float(args.http_timeout)), trust_env=bool(args.trust_env)) as client:
        for idx, case in enumerate(cases, 1):
            print(f"[{idx}/{len(cases)}] {case.id} | {case.category} | {case.text}")
            try:
                max_attempts = 3
                transient_errors: list[str] = []
                result: ReplyResult | None = None
                for attempt in range(1, max_attempts + 1):
                    try:
                        result = send_message_and_wait_reply(
                            client=client,
                            base_url=args.base_url,
                            wa_id=args.wa_id,
                            profile_name=args.profile_name,
                            phone_number_id=str(args.phone_number_id or "").strip(),
                            app_secret=app_secret,
                            user_text=case.text,
                            timeout_seconds=int(args.reply_timeout),
                            poll_interval_seconds=float(args.poll_interval),
                        )
                        break
                    except Exception as exc:  # noqa: BLE001
                        if attempt < max_attempts and _is_transient_unavailable(exc):
                            transient_errors.append(str(exc))
                            continue
                        raise

                if result is None:
                    raise RuntimeError("reply_not_received_after_retries")

                passed, issues = _evaluate(case, result)
                if transient_errors:
                    issues.append(f"transient_retry_count={len(transient_errors)}")
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
        "config": {
            "base_url": args.base_url,
            "reply_timeout": args.reply_timeout,
            "poll_interval": args.poll_interval,
            "total_cases": len(cases),
        },
        "summary": {
            "total_cases": total,
            "passed": passed_total,
            "failed": total - passed_total,
            "pass_rate_pct": (passed_total / total * 100.0) if total else 0.0,
            "by_category": by_category_list,
            "top_issues": sorted(issue_counter.items(), key=lambda item: item[1], reverse=True)[:20],
        },
        "results": evaluations,
    }

    json_path, md_path = _write_reports(payload, Path(args.output_dir))
    print("")
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    print(f"json_report={json_path}")
    print(f"md_report={md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
