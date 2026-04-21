from __future__ import annotations

import argparse
import json
import os
import re
import unicodedata
from collections import Counter
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
class ThemeTopic:
    category: str
    theme: str


@dataclass(frozen=True)
class ThemeQuestion:
    question_id: str
    category: str
    theme: str
    variant: int
    text: str


def _normalize(value: str) -> str:
    lowered = str(value or "").lower()
    ascii_value = unicodedata.normalize("NFKD", lowered).encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_value.split())


def _build_topics() -> list[ThemeTopic]:
    return [
        ThemeTopic("Agendamento e disponibilidade", "Disponibilidade de datas"),
        ThemeTopic("Agendamento e disponibilidade", "Horários livres"),
        ThemeTopic("Agendamento e disponibilidade", "Reserva por hora ou diária"),
        ThemeTopic("Agendamento e disponibilidade", "Tempo mínimo de locação"),
        ThemeTopic("Agendamento e disponibilidade", "Antecedência para reservar"),
        ThemeTopic("Agendamento e disponibilidade", "Bloqueio de agenda"),
        ThemeTopic("Agendamento e disponibilidade", "Lista de espera"),
        ThemeTopic("Agendamento e disponibilidade", "Confirmação de booking"),
        ThemeTopic("Agendamento e disponibilidade", "Overbooking / encaixe"),
        ThemeTopic("Agendamento e disponibilidade", "Política de prioridade"),
        ThemeTopic("Preços e condições comerciais", "Valor por hora"),
        ThemeTopic("Preços e condições comerciais", "Valor por diária"),
        ThemeTopic("Preços e condições comerciais", "Pacotes de horas"),
        ThemeTopic("Preços e condições comerciais", "Descontos para recorrentes"),
        ThemeTopic("Preços e condições comerciais", "Parcerias com fotógrafos"),
        ThemeTopic("Preços e condições comerciais", "Condições para produtoras"),
        ThemeTopic("Preços e condições comerciais", "Tarifas para finais de semana"),
        ThemeTopic("Preços e condições comerciais", "Tarifas para feriados"),
        ThemeTopic("Preços e condições comerciais", "Taxas extras (hora extra, limpeza, etc.)"),
        ThemeTopic("Preços e condições comerciais", "Política de reajuste"),
        ThemeTopic("Pagamento", "Formas de pagamento (PIX, cartão, etc.)"),
        ThemeTopic("Pagamento", "Sinal para reserva"),
        ThemeTopic("Pagamento", "Pagamento antecipado"),
        ThemeTopic("Pagamento", "Prazo para pagamento"),
        ThemeTopic("Pagamento", "Faturamento para empresas"),
        ThemeTopic("Pagamento", "Nota fiscal"),
        ThemeTopic("Pagamento", "Parcelamento"),
        ThemeTopic("Pagamento", "Política de inadimplência"),
        ThemeTopic("Pagamento", "Caução / depósito de segurança"),
        ThemeTopic("Pagamento", "Reembolso"),
        ThemeTopic("Cancelamento e remarcação", "Política de cancelamento"),
        ThemeTopic("Cancelamento e remarcação", "Prazo para cancelamento sem multa"),
        ThemeTopic("Cancelamento e remarcação", "Multa por cancelamento"),
        ThemeTopic("Cancelamento e remarcação", "Remarcação de horário"),
        ThemeTopic("Cancelamento e remarcação", "No-show (não comparecimento)"),
        ThemeTopic("Cancelamento e remarcação", "Crédito para uso futuro"),
        ThemeTopic("Cancelamento e remarcação", "Transferência de reserva"),
        ThemeTopic("Cancelamento e remarcação", "Mudança de duração"),
        ThemeTopic("Cancelamento e remarcação", "Mudança de data"),
        ThemeTopic("Cancelamento e remarcação", "Regras para imprevistos"),
        ThemeTopic("Estrutura do estúdio", "Tamanho do estúdio"),
        ThemeTopic("Estrutura do estúdio", "Pé-direito"),
        ThemeTopic("Estrutura do estúdio", "Capacidade de pessoas"),
        ThemeTopic("Estrutura do estúdio", "Tipos de ambientes"),
        ThemeTopic("Estrutura do estúdio", "Luz natural vs artificial"),
        ThemeTopic("Estrutura do estúdio", "Isolamento acústico"),
        ThemeTopic("Estrutura do estúdio", "Ar-condicionado"),
        ThemeTopic("Estrutura do estúdio", "Energia elétrica disponível"),
        ThemeTopic("Estrutura do estúdio", "Estacionamento"),
        ThemeTopic("Estrutura do estúdio", "Acessibilidade"),
        ThemeTopic("Equipamentos incluídos", "Iluminação disponível"),
        ThemeTopic("Equipamentos incluídos", "Tipos de flashes"),
        ThemeTopic("Equipamentos incluídos", "Modificadores de luz"),
        ThemeTopic("Equipamentos incluídos", "Tripés e suportes"),
        ThemeTopic("Equipamentos incluídos", "Fundos fotográficos"),
        ThemeTopic("Equipamentos incluídos", "Troca de fundos"),
        ThemeTopic("Equipamentos incluídos", "Equipamentos inclusos no preço"),
        ThemeTopic("Equipamentos incluídos", "Equipamentos extras pagos"),
        ThemeTopic("Equipamentos incluídos", "Manutenção dos equipamentos"),
        ThemeTopic("Equipamentos incluídos", "Backup de equipamentos"),
        ThemeTopic("Equipamentos externos", "Pode levar equipamento próprio?"),
        ThemeTopic("Equipamentos externos", "Regras para uso de equipamentos externos"),
        ThemeTopic("Equipamentos externos", "Compatibilidade elétrica"),
        ThemeTopic("Equipamentos externos", "Segurança dos equipamentos"),
        ThemeTopic("Equipamentos externos", "Seguro de equipamentos"),
        ThemeTopic("Equipamentos externos", "Transporte de equipamentos"),
        ThemeTopic("Equipamentos externos", "Montagem e desmontagem"),
        ThemeTopic("Equipamentos externos", "Assistente técnico disponível"),
        ThemeTopic("Equipamentos externos", "Testes antes do ensaio"),
        ThemeTopic("Equipamentos externos", "Limitações técnicas do espaço"),
        ThemeTopic("Tipos de uso do estúdio", "Ensaios fotográficos"),
        ThemeTopic("Tipos de uso do estúdio", "Gravação de vídeo"),
        ThemeTopic("Tipos de uso do estúdio", "Produções publicitárias"),
        ThemeTopic("Tipos de uso do estúdio", "Lives / streaming"),
        ThemeTopic("Tipos de uso do estúdio", "Workshops"),
        ThemeTopic("Tipos de uso do estúdio", "Casting"),
        ThemeTopic("Tipos de uso do estúdio", "Ensaios editoriais"),
        ThemeTopic("Tipos de uso do estúdio", "Produções com equipe grande"),
        ThemeTopic("Tipos de uso do estúdio", "Conteúdo para redes sociais"),
        ThemeTopic("Tipos de uso do estúdio", "Projetos autorais"),
        ThemeTopic("Regras de uso", "Número máximo de pessoas"),
        ThemeTopic("Regras de uso", "Horário de entrada e saída"),
        ThemeTopic("Regras de uso", "Tolerância de atraso"),
        ThemeTopic("Regras de uso", "Uso de alimentos e bebidas"),
        ThemeTopic("Regras de uso", "Uso de fumaça / efeitos"),
        ThemeTopic("Regras de uso", "Uso de tinta, água ou sujeira"),
        ThemeTopic("Regras de uso", "Cuidados com o espaço"),
        ThemeTopic("Regras de uso", "Responsabilidade por danos"),
        ThemeTopic("Regras de uso", "Limpeza pós-uso"),
        ThemeTopic("Regras de uso", "Normas internas"),
        ThemeTopic("Logística operacional", "Tempo de montagem"),
        ThemeTopic("Logística operacional", "Tempo de desmontagem"),
        ThemeTopic("Logística operacional", "Acesso antecipado"),
        ThemeTopic("Logística operacional", "Extensão de horário (hora extra)"),
        ThemeTopic("Logística operacional", "Troca de cenário"),
        ThemeTopic("Logística operacional", "Apoio durante o uso"),
        ThemeTopic("Logística operacional", "Atendimento no local"),
        ThemeTopic("Logística operacional", "Check-in / check-out"),
        ThemeTopic("Logística operacional", "Fluxo de entrada de equipe"),
        ThemeTopic("Logística operacional", "Contato durante a locação"),
    ]


def _build_questions() -> list[ThemeQuestion]:
    questions: list[ThemeQuestion] = []
    for idx, item in enumerate(_build_topics(), start=1):
        templates = [
            f"Sobre {item.theme}, como funciona no estudio?",
            f"Quais sao as regras de {item.theme} para locacao?",
            f"Pode detalhar {item.theme} de forma objetiva?",
        ]
        for variant, text in enumerate(templates, start=1):
            questions.append(
                ThemeQuestion(
                    question_id=f"{idx:03d}-{variant}",
                    category=item.category,
                    theme=item.theme,
                    variant=variant,
                    text=text,
                )
            )
    if len(questions) != 300:
        raise RuntimeError(f"expected_300_questions got={len(questions)}")
    return questions


def _is_transient_unavailable(exc: Exception) -> bool:
    text = str(exc or "").lower()
    return "503" in text or "service unavailable" in text


def _classify_answer(question: ThemeQuestion, result: ReplyResult) -> tuple[str, list[str]]:
    reply_text = str(result.reply_text or "").strip()
    normalized_reply = _normalize(reply_text)
    normalized_theme = _normalize(question.theme)
    reasons: list[str] = []

    if not normalized_reply:
        return "erro_modelo", ["resposta_vazia"]

    uncertain_markers = {
        "nao tenho informacoes",
        "nao tenho acesso",
        "nao sei",
        "preciso encaminhar para a equipe",
        "consulte",
        "depende",
        "nao posso",
    }
    hallucination_markers = {
        "sao paulo",
        "apartamento",
        "hotel",
        "escola",
        "ensino",
        "chatbot",
        "inteligencia artificial",
        "assistente virtual",
    }

    if any(marker in normalized_reply for marker in hallucination_markers):
        reasons.append("sinal_hallucinacao_ou_fora_dominio")

    if "audio" in normalized_theme or "microfone" in normalized_theme or "lapela" in normalized_theme:
        has_positive_audio = "sim" in normalized_reply and ("microfone" in normalized_reply or "audio" in normalized_reply)
        if has_positive_audio and "nao" not in normalized_reply:
            reasons.append("audio_contraditorio")

    if "capacidade" in normalized_theme or "numero maximo de pessoas" in normalized_theme:
        match = re.search(r"ate\s+(\d{1,2})\s+pessoas", normalized_reply)
        if match:
            try:
                count = int(match.group(1))
                if count > 5:
                    reasons.append("capacidade_acima_do_limite")
            except ValueError:
                pass

    undefined_signal = False
    if any(marker in normalized_reply for marker in uncertain_markers):
        undefined_signal = True
    if len(normalized_reply) < 40:
        undefined_signal = True
    if "posso te ajudar" in normalized_reply and "fc vip" not in normalized_reply and len(normalized_reply) < 90:
        undefined_signal = True

    if reasons:
        return "erro_modelo", reasons
    if undefined_signal:
        return "sem_resposta_definida", ["resposta_generica_ou_sem_politica_clara"]
    return "ok", []


def _build_yellow_flags(results: list[dict[str, Any]]) -> list[str]:
    flags: list[str] = []
    model_counter = Counter(str((item.get("result") or {}).get("llm_model") or "") for item in results if item.get("status") == "ok")
    fallback_count = sum(1 for item in results if str((item.get("result") or {}).get("llm_model") or "").strip() == "qwen2.5:1.5b-instruct")
    close_phrase_count = sum(
        1
        for item in results
        if "por nada! sempre que precisar de ajuda" in _normalize(str((item.get("result") or {}).get("reply_text") or ""))
    )
    error_count = sum(1 for item in results if item.get("status") == "error")

    if fallback_count > 50:
        flags.append("Uso elevado do fallback 1.5b (potencial aumento de custo/latencia).")
    if close_phrase_count > 10:
        flags.append("Frase de encerramento apareceu muitas vezes fora de contexto; revisar gatilho de fechamento.")
    if error_count > 0:
        flags.append("Houve falhas transitórias HTTP durante a bateria online; monitorar estabilidade do serviço.")
    if model_counter.get("rule_human_handoff", 0) > 30:
        flags.append("Volume alto de handoff; validar se regras de risco estao excessivamente sensiveis.")
    return flags


def _write_reports(payload: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"theme_coverage_300_{stamp}.json"
    md_path = output_dir / f"theme_coverage_300_{stamp}.md"

    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines: list[str] = []
    summary = payload["summary"]
    lines.append("# Relatorio 300 Perguntas - Temas")
    lines.append("")
    lines.append(f"- total: {summary['total_questions']}")
    lines.append(f"- ok: {summary['ok']}")
    lines.append(f"- sem_resposta_definida: {summary['sem_resposta_definida']}")
    lines.append(f"- erro_modelo: {summary['erro_modelo']}")
    lines.append("")

    lines.append("## Temas com maior taxa de erros")
    lines.append("")
    for item in summary["top_error_themes"]:
        lines.append(
            f"- {item['theme']} ({item['category']}): {item['errors']}/{item['total']} "
            f"({item['error_rate_pct']:.2f}%)"
        )

    lines.append("")
    lines.append("## Perguntas sem resposta definida")
    lines.append("")
    for item in payload["results"]:
        if item.get("classification") != "sem_resposta_definida":
            continue
        lines.append(f"Tema: {item['theme']} | Pergunta: {item['question']}")
        lines.append(f"Resposta: {item.get('reply_text')}")
        lines.append("")

    lines.append("## Perguntas com erro do modelo")
    lines.append("")
    for item in payload["results"]:
        if item.get("classification") != "erro_modelo":
            continue
        lines.append(f"Tema: {item['theme']} | Pergunta: {item['question']}")
        lines.append(f"Motivos: {', '.join(item.get('reasons') or [])}")
        lines.append(f"Resposta: {item.get('reply_text')}")
        lines.append("")

    lines.append("## Yellow Flags")
    lines.append("")
    for flag in payload["summary"]["yellow_flags"]:
        lines.append(f"- {flag}")

    md_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return json_path, md_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bateria online com 300 perguntas (100 temas x 3 variacoes).")
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

    questions = _build_questions()
    detailed_results: list[dict[str, Any]] = []
    classification_counter = Counter()
    by_theme: dict[tuple[str, str], dict[str, Any]] = {}

    with httpx.Client(timeout=max(15.0, float(args.http_timeout)), trust_env=bool(args.trust_env)) as client:
        for idx, question in enumerate(questions, start=1):
            print(f"[{idx}/{len(questions)}] {question.question_id} | {question.category} | {question.theme}")
            try:
                result: ReplyResult | None = None
                for attempt in range(1, 4):
                    try:
                        result = send_message_and_wait_reply(
                            client=client,
                            base_url=args.base_url,
                            wa_id=args.wa_id,
                            profile_name=args.profile_name,
                            phone_number_id=str(args.phone_number_id or "").strip(),
                            app_secret=app_secret,
                            user_text=question.text,
                            timeout_seconds=int(args.reply_timeout),
                            poll_interval_seconds=float(args.poll_interval),
                        )
                        break
                    except Exception as exc:  # noqa: BLE001
                        if attempt < 3 and _is_transient_unavailable(exc):
                            continue
                        raise

                if result is None:
                    raise RuntimeError("reply_not_received_after_retries")

                classification, reasons = _classify_answer(question, result)
                classification_counter[classification] += 1
                row = {
                    "question_id": question.question_id,
                    "category": question.category,
                    "theme": question.theme,
                    "question": question.text,
                    "classification": classification,
                    "reasons": reasons,
                    "status": "ok",
                    "llm_model": result.llm_model,
                    "llm_status": result.llm_status,
                    "reply_text": result.reply_text,
                    "latency_seconds": result.request_latency_seconds,
                    "raw_result": asdict(result),
                }
            except Exception as exc:  # noqa: BLE001
                classification_counter["erro_modelo"] += 1
                row = {
                    "question_id": question.question_id,
                    "category": question.category,
                    "theme": question.theme,
                    "question": question.text,
                    "classification": "erro_modelo",
                    "reasons": [f"request_error:{type(exc).__name__}"],
                    "status": "error",
                    "llm_model": "",
                    "llm_status": "",
                    "reply_text": "",
                    "latency_seconds": 0.0,
                    "error": str(exc),
                    "raw_result": {},
                }

            detailed_results.append(row)
            theme_key = (row["category"], row["theme"])
            bucket = by_theme.setdefault(theme_key, {"total": 0, "errors": 0})
            bucket["total"] += 1
            if row["classification"] != "ok":
                bucket["errors"] += 1

    top_error_themes: list[dict[str, Any]] = []
    for (category, theme), stats in by_theme.items():
        total = int(stats["total"])
        errors = int(stats["errors"])
        top_error_themes.append(
            {
                "category": category,
                "theme": theme,
                "total": total,
                "errors": errors,
                "error_rate_pct": (errors / total * 100.0) if total else 0.0,
            }
        )
    top_error_themes.sort(key=lambda item: (item["error_rate_pct"], item["errors"]), reverse=True)

    summary = {
        "total_questions": len(detailed_results),
        "ok": classification_counter.get("ok", 0),
        "sem_resposta_definida": classification_counter.get("sem_resposta_definida", 0),
        "erro_modelo": classification_counter.get("erro_modelo", 0),
        "top_error_themes": top_error_themes[:20],
        "yellow_flags": _build_yellow_flags(detailed_results),
    }

    payload = {
        "run_at_utc": datetime.now(timezone.utc).isoformat(),
        "config": {
            "base_url": args.base_url,
            "reply_timeout": args.reply_timeout,
            "poll_interval": args.poll_interval,
            "total_questions": len(questions),
        },
        "summary": summary,
        "results": detailed_results,
    }

    json_path, md_path = _write_reports(payload, Path(args.output_dir))
    print("")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"json_report={json_path}")
    print(f"md_report={md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
