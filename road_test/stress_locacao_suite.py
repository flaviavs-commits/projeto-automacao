from __future__ import annotations

import argparse
import json
import os
import random
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


MANDATORY_CLOSE = "Por nada! Sempre que precisar de ajuda"


@dataclass
class StressCase:
    id: str
    category: str
    text: str
    expected: str


def _build_pool() -> list[StressCase]:
    greetings = [
        "oi",
        "boa tarde",
        "ola, tudo bem?",
        "bom dia, queria info do estudio",
        "vocês alugam estudio?",
    ]
    schedule = [
        "quero agendar sexta as 18h",
        "tem disponibilidade amanha 10h?",
        "consigo reservar hoje 20h?",
        "quero marcar 2h no sabado",
        "sou cliente antigo, quero reservar de novo",
        "preciso de vaga segunda 14h",
        "quero agendar para ensaio de produto",
        "tem horario livre de noite?",
        "da para marcar 1 hora ainda hoje?",
        "quero reservar para gravacao",
    ]
    prices = [
        "qual o valor de 1 hora?",
        "quanto fica 2 horas?",
        "quais os pacotes de horas?",
        "tem tabela de preco?",
        "valor para 3 horas?",
        "qual preco para membro?",
        "quanto custa locar o estudio?",
        "voces tem desconto progressivo?",
        "qual pacote compensa mais?",
        "me manda os valores",
    ]
    location = [
        "onde fica o estudio?",
        "qual o endereco?",
        "fica em qual bairro?",
        "como chego ai?",
        "o acesso e por escada?",
        "tem estacionamento?",
        "da para parar carro perto?",
        "o local e de facil acesso?",
        "tem elevador?",
        "fica na rua ou em shopping?",
    ]
    audio = [
        "tem microfone de lapela?",
        "voces alugam microfone?",
        "tem equipamento de audio?",
        "tem mesa de som ai?",
        "da pra gravar com lapela de voces?",
        "vocês oferecem audio?",
        "tem boom ou shotgun?",
        "tem interface de audio?",
        "fornecem microfones?",
        "audio esta incluso?",
    ]
    structure = [
        "qual estrutura de iluminacao voces tem?",
        "quais fundos fotograficos voces oferecem?",
        "o estudio tem softbox?",
        "tem ar condicionado?",
        "quais equipamentos estao inclusos?",
        "tem bastao de led?",
        "voces tem rebatedor?",
        "tem suporte para camera e celular?",
        "o estudio possui cenografia?",
        "o que vem incluso na locacao?",
    ]
    risk_people = [
        "vamos em 6 pessoas para gravar",
        "somos 7 na equipe, pode?",
        "vai 8 pessoas no total",
        "seremos 6 pessoas no ensaio",
        "equipe com 9 pessoas, tudo bem?",
        "dá para entrar 10 pessoas?",
        "vamos 6 pessoas e 1 pet",
        "a equipe sera grande, 12 pessoas",
        "somos 6, consegue liberar?",
        "vai todo mundo, umas 15 pessoas",
    ]
    risk_materials = [
        "queremos usar confete no ensaio",
        "pode usar fumaca?",
        "quero usar tinta no cenario",
        "vamos fazer smash the cake",
        "posso usar glitter?",
        "queria usar espuma na gravacao",
        "podemos levar areia colorida?",
        "da pra usar sangue falso?",
        "quero usar velas com faisca",
        "pode levar animal para foto?",
    ]
    paid_changes = [
        "preciso cancelar um horario que ja paguei",
        "quero reagendar meu horario pago",
        "ja paguei e quero trocar o horario",
        "paguei e preciso remarcar",
        "cancelamento de horario pago",
        "ja esta pago, posso mudar o dia?",
        "quero mudar horario que ja esta pago",
        "preciso reagendar reserva paga",
        "consigo trocar data apos pagamento?",
        "posso cancelar depois de pagar?",
    ]
    close = [
        "obrigado, vou fechar pelo site",
        "valeu, vou agendar no site",
        "muito obrigado pelas infos",
        "entendi, obrigado",
        "perfeito, obrigado",
    ]
    generic = [
        "nunca fui ai, como funciona?",
        "quero alugar para foto de produto",
        "preciso de estudio para video curto",
        "me explica rapidamente como alugar",
        "tem alguem la para ajudar com luz?",
        "se eu atrasar 20 minutos, perco tempo?",
        "qual a capacidade maxima do estudio?",
        "voces atendem de que horas a que horas?",
        "quero conhecer o espaco antes",
        "sou fotografo iniciante, voces ajudam?",
        "como funciona o pagamento?",
        "posso levar assistente tecnico?",
        "tem internet no local?",
        "da para gravar reels ai?",
        "consigo fazer ensaio corporativo?",
        "o estudio atende video entrevista?",
        "quero saber regras de atraso",
        "como faco para virar membro?",
        "voces ajudam com setup de luz?",
        "qual melhor pacote para ensaio rapido?",
    ]

    pool: list[StressCase] = []
    for idx, text in enumerate(greetings, 1):
        pool.append(StressCase(id=f"greet_{idx}", category="greeting", text=text, expected="generic_model"))
    for idx, text in enumerate(schedule, 1):
        pool.append(StressCase(id=f"schedule_{idx}", category="schedule", text=text, expected="rule_schedule"))
    for idx, text in enumerate(prices, 1):
        pool.append(StressCase(id=f"price_{idx}", category="prices", text=text, expected="generic_model"))
    for idx, text in enumerate(location, 1):
        pool.append(StressCase(id=f"loc_{idx}", category="location", text=text, expected="generic_model"))
    for idx, text in enumerate(audio, 1):
        pool.append(StressCase(id=f"audio_{idx}", category="audio", text=text, expected="generic_model"))
    for idx, text in enumerate(structure, 1):
        pool.append(StressCase(id=f"struct_{idx}", category="structure", text=text, expected="generic_model"))
    for idx, text in enumerate(risk_people, 1):
        pool.append(StressCase(id=f"risk_people_{idx}", category="risk_people", text=text, expected="rule_handoff"))
    for idx, text in enumerate(risk_materials, 1):
        pool.append(StressCase(id=f"risk_materials_{idx}", category="risk_materials", text=text, expected="rule_handoff"))
    for idx, text in enumerate(paid_changes, 1):
        pool.append(StressCase(id=f"paid_change_{idx}", category="paid_changes", text=text, expected="rule_handoff"))
    for idx, text in enumerate(close, 1):
        pool.append(StressCase(id=f"close_{idx}", category="close", text=text, expected="rule_close"))
    for idx, text in enumerate(generic, 1):
        pool.append(StressCase(id=f"generic_{idx}", category="generic", text=text, expected="generic_model"))
    return pool


def _select_cases(pool: list[StressCase], size: int, seed: int) -> list[StressCase]:
    if size >= len(pool):
        return list(pool)
    random.seed(seed)
    return random.sample(pool, k=size)


def _evaluate(case: StressCase, result: ReplyResult) -> tuple[bool, list[str]]:
    issues: list[str] = []
    model = str(result.llm_model or "")
    reply = str(result.reply_text or "").strip()
    lower_reply = reply.lower()

    if not reply:
        issues.append("empty_reply")

    if case.expected == "rule_schedule":
        if model != "rule_schedule_site_only":
            issues.append(f"expected_model=rule_schedule_site_only got={model}")
        if "agendamento pelo site:" not in lower_reply:
            issues.append("missing_schedule_cta")
        if "nao consigo confirmar horario manualmente" not in lower_reply:
            issues.append("missing_manual_schedule_guard")
    elif case.expected == "rule_handoff":
        if model != "rule_human_handoff":
            issues.append(f"expected_model=rule_human_handoff got={model}")
        if "encaminhar para a nossa equipe humana" not in lower_reply:
            issues.append("missing_handoff_text")
    elif case.expected == "rule_close":
        if model != "rule_close":
            issues.append(f"expected_model=rule_close got={model}")
        if MANDATORY_CLOSE.lower() not in lower_reply:
            issues.append("missing_mandatory_close_phrase")
    else:
        if model.startswith("rule_"):
            issues.append(f"unexpected_rule_model={model}")
        forbidden_markers = [
            "como sou uma inteligencia artificial",
            "nao tenho acesso a informacoes especificas",
            "nao posso ajudar com isso",
        ]
        for marker in forbidden_markers:
            if marker in lower_reply:
                issues.append(f"generic_ai_disclaimer:{marker}")
                break

        if case.category == "location":
            if "corifeu" not in lower_reply and "jardim amalia" not in lower_reply:
                issues.append("location_missing_official_reference")
        if case.category == "audio":
            if "audio" not in lower_reply and "microfone" not in lower_reply:
                issues.append("audio_answer_missing_topic")
            if "nao" not in lower_reply and "não" not in lower_reply:
                issues.append("audio_missing_negative_constraint")

    return len(issues) == 0, issues


def _write_reports(payload: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"stress_locacao_{stamp}.json"
    md_path = output_dir / f"stress_locacao_{stamp}.md"

    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines: list[str] = []
    summary = payload["summary"]
    lines.append("# Stress Test Locacao - Resumo")
    lines.append("")
    lines.append(f"- total_cases: {summary['total_cases']}")
    lines.append(f"- passed: {summary['passed']}")
    lines.append(f"- failed: {summary['failed']}")
    lines.append(f"- pass_rate: {summary['pass_rate_pct']:.2f}%")
    lines.append("")
    lines.append("## Por categoria")
    lines.append("")
    for item in summary["by_category"]:
        lines.append(
            f"- {item['category']}: {item['passed']}/{item['total']} "
            f"({item['pass_rate_pct']:.2f}%)"
        )
    lines.append("")
    lines.append("## Principais falhas")
    lines.append("")
    for issue, count in summary["top_issues"]:
        lines.append(f"- {issue}: {count}")

    md_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return json_path, md_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stress test de frases de locacao em producao.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--wa-id", default=DEFAULT_WA_ID)
    parser.add_argument("--profile-name", default=DEFAULT_PROFILE_NAME)
    parser.add_argument("--phone-number-id", default=DEFAULT_PHONE_NUMBER_ID)
    parser.add_argument(
        "--app-secret",
        default=(os.getenv("META_APP_SECRET", "").strip() or os.getenv("INSTAGRAM_APP_SECRET", "").strip()),
    )
    parser.add_argument("--size", type=int, default=100, help="Quantidade de casos a executar.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--reply-timeout", type=int, default=90)
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--http-timeout", type=float, default=45.0)
    parser.add_argument("--output-dir", default=".qa_tmp")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not str(args.app_secret or "").strip():
        print("Falha: informe --app-secret ou configure META_APP_SECRET.")
        return 2

    pool = _build_pool()
    selected = _select_cases(pool, max(1, int(args.size)), int(args.seed))

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
    failed_total = total - passed_total
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

    top_issues = sorted(issue_counter.items(), key=lambda item: item[1], reverse=True)[:12]

    payload = {
        "run_at_utc": datetime.now(timezone.utc).isoformat(),
        "config": {
            "base_url": args.base_url,
            "size": len(selected),
            "seed": args.seed,
            "reply_timeout": args.reply_timeout,
            "poll_interval": args.poll_interval,
        },
        "summary": {
            "total_cases": total,
            "passed": passed_total,
            "failed": failed_total,
            "pass_rate_pct": (passed_total / total * 100.0) if total else 0.0,
            "by_category": by_category_list,
            "top_issues": top_issues,
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
