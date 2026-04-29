from __future__ import annotations

import re
import unicodedata
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.contact_memory import ContactMemory


class ContactMemoryService:
    """Stores key customer memories while skipping ambiguous statements."""

    PILLAR_MEMORY_KEYS = {
        "nome_cliente",
        "telefone",
        "cliente_status",
        "tipo_projeto",
        "duracao_desejada_horas",
        "numero_pessoas",
        "intencao_principal",
        "interesse_servico",
        "preferencia_periodo",
        "preferencia_horario",
        "horario_perguntado",
        "duvida_valor",
        "duvida_disponibilidade",
        "localidade_cliente",
        "perfil_cliente",
        "interesse",
        "tipo_agendamento",
        "pacote_interesse",
        "interesse_membro",
        "estrutura_interesse",
        "human_reason",
        "origem",
    }

    _AMBIGUOUS_MARKERS = {
        "talvez",
        "nao sei",
        "ainda estou vendo",
        "ainda vou ver",
        "depois vejo",
        "vou pensar",
        "nao tenho certeza",
    }
    _OLD_CUSTOMER_MARKERS = {
        "sou cliente",
        "cliente antigo",
        "ja fui cliente",
        "ja conheco",
        "voltei",
        "retornando",
    }
    _NEW_CUSTOMER_MARKERS = {
        "cliente novo",
        "primeira vez",
        "nao conheco",
        "ainda nao conheco",
        "nunca fui",
    }
    _SCHEDULE_INTENT_MARKERS = {
        "agendar",
        "agendamento",
        "marcar",
        "reserva",
        "reservar",
        "disponibilidade",
        "horario",
        "vaga",
    }
    _DISCOVER_INTENT_MARKERS = {
        "conhecer",
        "como funciona",
        "estrutura",
        "endereco",
        "localizacao",
        "onde fica",
    }
    _HOURS_INFO_MARKERS = {
        "horario de funcionamento",
        "que horas abre",
        "que horas fecha",
        "funciona ate",
        "funciona de",
    }

    _SERVICE_MAP = {
        "ensaio": "ensaio_fotografico",
        "book": "book_fotografico",
        "casamento": "evento_casamento",
        "gestante": "ensaio_gestante",
        "familia": "ensaio_familia",
        "corporativo": "ensaio_corporativo",
        "retrato": "ensaio_retrato",
        "video": "video",
    }

    _DAY_MARKERS = {
        "segunda",
        "terca",
        "quarta",
        "quinta",
        "sexta",
        "sabado",
        "domingo",
        "manha",
        "tarde",
        "noite",
    }

    _TIME_RE = re.compile(r"\b([01]?\d|2[0-3])(?::|h)([0-5]\d)?\b")
    _PRICE_RE = re.compile(r"(r\$\s?\d+[\d\.,]*)", flags=re.IGNORECASE)
    _DURATION_RE = re.compile(r"\b([1-9])\s*(h|hora|horas)\b")
    _PEOPLE_RE = re.compile(r"\b(\d{1,2})\s*(pessoa|pessoas)\b")
    _NAME_RE = re.compile(
        r"\bmeu\s+nome\s*(?:e|\u00e9)\s+([A-Za-z\u00C0-\u00FF][A-Za-z\u00C0-\u00FF'\- ]{1,60})\b",
        flags=re.IGNORECASE,
    )
    _I_AM_RE = re.compile(
        r"\b(?:eu\s+sou|sou)\s+([A-Za-z\u00C0-\u00FF][A-Za-z\u00C0-\u00FF'\- ]{1,60})\b",
        flags=re.IGNORECASE,
    )
    _LOCATION_RE = re.compile(
        r"\b(?:moro em|sou de|vim de|resido em)\s+([A-Za-z\u00C0-\u00FF][A-Za-z\u00C0-\u00FF'\- ]{1,60})\b",
        flags=re.IGNORECASE,
    )
    _INSTAGRAM_RE = re.compile(r"@([A-Za-z0-9._]{2,30})", flags=re.IGNORECASE)
    _PROFILE_MARKERS = {
        "fotografo": "fotografo",
        "fotografa": "fotografo",
        "videomaker": "videomaker",
        "modelo": "modelo",
        "locacao": "locacao",
        "locar": "locacao",
    }

    def save_from_inbound_text(
        self,
        *,
        db: Session,
        contact_id: UUID,
        source_message_id: UUID,
        inbound_text: str,
        strict_temporary_mode: bool = False,
    ) -> dict:
        analyzed = self.analyze_text(inbound_text)
        candidates = analyzed["candidates"]
        if strict_temporary_mode:
            candidates = [
                candidate
                for candidate in candidates
                if candidate.get("memory_key") in self.PILLAR_MEMORY_KEYS
                and float(candidate.get("confidence") or 0.0) >= 0.85
            ]
        if not candidates:
            return {"status": analyzed["status"], "saved_keys": []}

        saved_keys: list[str] = []
        for candidate in candidates:
            memory_key = candidate["memory_key"]
            existing = (
                db.query(ContactMemory)
                .filter(
                    ContactMemory.contact_id == contact_id,
                    ContactMemory.memory_key == memory_key,
                )
                .first()
            )
            if existing is None:
                db.add(
                    ContactMemory(
                        contact_id=contact_id,
                        source_message_id=source_message_id,
                        memory_key=memory_key,
                        memory_value=candidate["memory_value"],
                        status="active",
                        importance=candidate["importance"],
                        confidence=candidate["confidence"],
                    )
                )
            else:
                existing.memory_value = candidate["memory_value"]
                existing.source_message_id = source_message_id
                existing.status = "active"
                existing.importance = max(existing.importance, candidate["importance"])
                existing.confidence = max(existing.confidence, candidate["confidence"])
            saved_keys.append(memory_key)

        return {"status": "saved", "saved_keys": saved_keys}

    def analyze_text(self, inbound_text: str) -> dict:
        cleaned = " ".join(str(inbound_text or "").split()).strip()
        if not cleaned:
            return {"status": "ignored_no_text", "candidates": []}

        normalized = self._normalize(cleaned)
        if self._is_ambiguous(normalized):
            return {"status": "ignored_ambiguous", "candidates": []}

        candidates = self._extract_candidates(cleaned, normalized)
        if not candidates:
            return {"status": "ignored_no_candidate", "candidates": []}

        return {"status": "candidate_found", "candidates": candidates}

    def _normalize(self, value: str) -> str:
        lowered = value.lower()
        ascii_value = unicodedata.normalize("NFKD", lowered).encode("ascii", "ignore").decode("ascii")
        return " ".join(ascii_value.split())

    def _is_ambiguous(self, normalized_text: str) -> bool:
        return any(marker in normalized_text for marker in self._AMBIGUOUS_MARKERS)

    def _extract_candidates(self, original_text: str, normalized_text: str) -> list[dict]:
        candidates: list[dict] = []

        name_candidate = self._extract_name(original_text, normalized_text)
        if name_candidate:
            candidates.append(name_candidate)

        instagram_candidate = self._extract_instagram_handle(original_text)
        if instagram_candidate:
            candidates.append(instagram_candidate)

        profile_candidate = self._extract_customer_profile(normalized_text)
        if profile_candidate:
            candidates.append(profile_candidate)

        location_candidate = self._extract_location(original_text)
        if location_candidate:
            candidates.append(location_candidate)

        if any(marker in normalized_text for marker in self._OLD_CUSTOMER_MARKERS):
            candidates.append(
                {
                    "memory_key": "cliente_status",
                    "memory_value": "antigo",
                    "importance": 5,
                    "confidence": 0.95,
                }
            )
            candidates.append(
                {
                    "memory_key": "ja_conhece_estudio",
                    "memory_value": "sim",
                    "importance": 5,
                    "confidence": 0.95,
                }
            )
        elif any(marker in normalized_text for marker in self._NEW_CUSTOMER_MARKERS):
            candidates.append(
                {
                    "memory_key": "cliente_status",
                    "memory_value": "novo",
                    "importance": 5,
                    "confidence": 0.95,
                }
            )
            candidates.append(
                {
                    "memory_key": "ja_conhece_estudio",
                    "memory_value": "nao",
                    "importance": 5,
                    "confidence": 0.95,
                }
            )

        if any(marker in normalized_text for marker in self._SCHEDULE_INTENT_MARKERS):
            candidates.append(
                {
                    "memory_key": "intencao_principal",
                    "memory_value": "agendar",
                    "importance": 4,
                    "confidence": 0.88,
                }
            )
        elif any(marker in normalized_text for marker in self._DISCOVER_INTENT_MARKERS):
            candidates.append(
                {
                    "memory_key": "intencao_principal",
                    "memory_value": "conhecer",
                    "importance": 4,
                    "confidence": 0.85,
                }
            )

        has_foto = "foto" in normalized_text or "fotografia" in normalized_text
        has_video = "video" in normalized_text or "filmagem" in normalized_text
        if has_foto and has_video:
            candidates.append(
                {
                    "memory_key": "tipo_projeto",
                    "memory_value": "foto_e_video",
                    "importance": 4,
                    "confidence": 0.9,
                }
            )
        elif has_foto:
            candidates.append(
                {
                    "memory_key": "tipo_projeto",
                    "memory_value": "foto",
                    "importance": 4,
                    "confidence": 0.9,
                }
            )
        elif has_video:
            candidates.append(
                {
                    "memory_key": "tipo_projeto",
                    "memory_value": "video",
                    "importance": 4,
                    "confidence": 0.9,
                }
            )

        for marker, canonical_service in self._SERVICE_MAP.items():
            if marker in normalized_text:
                candidates.append(
                    {
                        "memory_key": "interesse_servico",
                        "memory_value": canonical_service,
                        "importance": 5,
                        "confidence": 0.9,
                    }
                )
                break

        if any(marker in normalized_text for marker in {"valor", "preco", "orcamento", "quanto custa"}):
            candidates.append(
                {
                    "memory_key": "duvida_valor",
                    "memory_value": "true",
                    "importance": 3,
                    "confidence": 0.85,
                }
            )

        if any(marker in normalized_text for marker in {"horario", "disponibilidade", "vaga"}):
            candidates.append(
                {
                    "memory_key": "duvida_disponibilidade",
                    "memory_value": "true",
                    "importance": 3,
                    "confidence": 0.85,
                }
            )

        if any(marker in normalized_text for marker in self._HOURS_INFO_MARKERS):
            candidates.append(
                {
                    "memory_key": "perguntou_horario_funcionamento",
                    "memory_value": "true",
                    "importance": 3,
                    "confidence": 0.84,
                }
            )

        day_hits = [marker for marker in self._DAY_MARKERS if marker in normalized_text]
        if day_hits:
            candidates.append(
                {
                    "memory_key": "preferencia_periodo",
                    "memory_value": ", ".join(sorted(set(day_hits))),
                    "importance": 4,
                    "confidence": 0.8,
                }
            )

        time_hits = [match.group(0) for match in self._TIME_RE.finditer(normalized_text)]
        if time_hits:
            compact_time_hits = ", ".join(time_hits[:3])
            candidates.append(
                {
                    "memory_key": "preferencia_horario",
                    "memory_value": compact_time_hits,
                    "importance": 4,
                    "confidence": 0.9,
                }
            )
            candidates.append(
                {
                    "memory_key": "horario_perguntado",
                    "memory_value": compact_time_hits,
                    "importance": 5,
                    "confidence": 0.92,
                }
            )

        duration_hits = [match.group(1) for match in self._DURATION_RE.finditer(normalized_text)]
        if duration_hits:
            first_duration = duration_hits[0]
            candidates.append(
                {
                    "memory_key": "duracao_desejada_horas",
                    "memory_value": str(first_duration),
                    "importance": 4,
                    "confidence": 0.92,
                }
            )

        people_hits = [match.group(1) for match in self._PEOPLE_RE.finditer(normalized_text)]
        if people_hits:
            candidates.append(
                {
                    "memory_key": "numero_pessoas",
                    "memory_value": str(people_hits[0]),
                    "importance": 4,
                    "confidence": 0.92,
                }
            )

        price_hits = [match.group(1) for match in self._PRICE_RE.finditer(original_text)]
        if price_hits:
            candidates.append(
                {
                    "memory_key": "referencia_orcamento",
                    "memory_value": ", ".join(price_hits[:2]),
                    "importance": 4,
                    "confidence": 0.9,
                }
            )

        if "foto" in normalized_text and ("espaco" in normalized_text or "estudio" in normalized_text):
            candidates.append(
                {
                    "memory_key": "quer_fotos_espaco",
                    "memory_value": "true",
                    "importance": 3,
                    "confidence": 0.9,
                }
            )

        deduped: dict[str, dict] = {}
        for item in candidates:
            deduped[item["memory_key"]] = item
        return list(deduped.values())

    def _extract_name(self, original_text: str, normalized_text: str) -> dict | None:
        raw = ""
        match = self._NAME_RE.search(original_text or "")
        if match:
            raw = str(match.group(1) or "").strip()
        else:
            match = self._I_AM_RE.search(original_text or "")
            if match:
                raw = str(match.group(1) or "").strip()

        if not raw:
            return None

        cleaned = re.sub(r"[^A-Za-z\u00C0-\u00FF'\- ]+", " ", raw)
        cleaned = " ".join(cleaned.split()).strip()
        if not cleaned:
            return None

        parts = cleaned.split(" ")
        cleaned = " ".join(parts[:3]).strip()
        if not cleaned:
            return None

        normalized = self._normalize(cleaned)
        if normalized in {"cliente", "cliente antigo", "cliente novo"}:
            return None
        if any(marker in normalized_text for marker in {"sou cliente", "cliente antigo", "cliente novo"}):
            if normalized in {"cliente", "cliente antigo", "cliente novo"}:
                return None

        display = " ".join(word[:1].upper() + word[1:] for word in cleaned.split(" ") if word)
        if not display:
            return None

        return {
            "memory_key": "nome_cliente",
            "memory_value": display,
            "importance": 5,
            "confidence": 0.9,
        }

    def _extract_location(self, original_text: str) -> dict | None:
        match = self._LOCATION_RE.search(original_text or "")
        if not match:
            return None

        raw = str(match.group(1) or "").strip()
        cleaned = re.sub(r"[^A-Za-z\u00C0-\u00FF'\- ]+", " ", raw)
        cleaned = " ".join(cleaned.split()).strip()
        if not cleaned:
            return None

        stop_words = {"e", "que", "pra", "para", "com", "porque", "mas", "quero", "queria"}
        words = []
        for token in cleaned.split(" "):
            lowered = self._normalize(token)
            if words and lowered in stop_words:
                break
            words.append(token)

        cleaned = " ".join(words[:4]).strip()
        if not cleaned:
            return None

        normalized = self._normalize(cleaned)
        if normalized in {"aqui", "ai", "estudio"}:
            return None

        display = " ".join(word[:1].upper() + word[1:] for word in cleaned.split(" ") if word)
        if not display:
            return None

        return {
            "memory_key": "localidade_cliente",
            "memory_value": display,
            "importance": 3,
            "confidence": 0.82,
        }

    def _extract_instagram_handle(self, original_text: str) -> dict | None:
        match = self._INSTAGRAM_RE.search(original_text or "")
        if not match:
            return None
        raw = str(match.group(1) or "").strip(" .")
        if not raw:
            return None
        return {
            "memory_key": "instagram_cliente",
            "memory_value": f"@{raw.lower()}",
            "importance": 4,
            "confidence": 0.9,
        }

    def _extract_customer_profile(self, normalized_text: str) -> dict | None:
        for marker, profile in self._PROFILE_MARKERS.items():
            if marker in normalized_text:
                return {
                    "memory_key": "perfil_cliente",
                    "memory_value": profile,
                    "importance": 4,
                    "confidence": 0.86,
                }
        return None
