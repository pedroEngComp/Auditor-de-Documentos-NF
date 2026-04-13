import re
from typing import Optional


# Encodings a tentar, em ordem de prioridade
ENCODINGS = ["utf-8", "latin-1", "cp1252", "iso-8859-1"]

# Mapa de nomes de campo no arquivo → chave interna
FIELD_MAP = {
    "tipo_documento":    "tipo_documento",
    "numero_documento":  "numero_documento",
    "data_emissao":      "data_emissao",
    "fornecedor":        "fornecedor",
    "cnpj_fornecedor":   "cnpj_fornecedor",
    "descricao_servico": "descricao_servico",
    "valor_bruto":       "valor_bruto",
    "data_pagamento":    "data_pagamento",
    "data_emissao_nf":   "data_emissao_nf",
    "aprovado_por":      "aprovado_por",
    "banco_destino":     "banco_destino",
    "status":            "status",
    "hash_verificacao":  "hash_verificacao",
}


def parse_txt_file(filename: str, raw_bytes: bytes) -> dict:

    doc = {
        "filename": filename,
        "raw_text": None,
        "parse_status": None,
        "encoding_used": None,
        "parse_error": None,
    }

    # Inicializa todos os campos como None (nunca assume vazio = correto)
    for key in FIELD_MAP.values():
        doc[key] = None

    # ── Tentativa de decodificação ────────────────────────────────────────────
    text = None
    for enc in ENCODINGS:
        try:
            text = raw_bytes.decode(enc)
            doc["encoding_used"] = enc
            break
        except (UnicodeDecodeError, LookupError):
            continue

    if text is None:
        doc["parse_status"] = "encoding_error"
        doc["parse_error"] = "Não foi possível decodificar o arquivo com nenhum encoding conhecido"
        doc["raw_text"] = repr(raw_bytes[:200])  # salva amostra para diagnóstico
        return doc

    doc["raw_text"] = text

    # ── Parse linha a linha ───────────────────────────────────────────────────
    fields_found = 0
    for line in text.splitlines():
        line = line.strip()
        if ":" not in line:
            continue

        # Divide apenas no primeiro ":" para preservar valores como "Ag.1234 C/C"
        raw_key, _, raw_value = line.partition(":")
        key_normalized = raw_key.strip().lower()
        value = raw_value.strip()

        if key_normalized in FIELD_MAP and value:
            doc[FIELD_MAP[key_normalized]] = value
            fields_found += 1

    # ── Validação de completude ───────────────────────────────────────────────
    required_fields = ["numero_documento", "fornecedor", "cnpj_fornecedor",
                       "valor_bruto", "data_pagamento", "data_emissao_nf", "status"]

    missing = [f for f in required_fields if not doc.get(f)]

    if fields_found == 0:
        doc["parse_status"] = "empty_or_unrecognized"
        doc["parse_error"] = "Nenhum campo reconhecido no arquivo"
    elif missing:
        doc["parse_status"] = "partial"
        doc["parse_error"] = f"Campos ausentes: {', '.join(missing)}"
    else:
        doc["parse_status"] = "ok"

    # ── Normalização de valor monetário ──────────────────────────────────────
    if doc.get("valor_bruto"):
        doc["valor_bruto_num"] = parse_currency(doc["valor_bruto"])

    return doc


def parse_currency(value_str: str) -> Optional[float]:

    try:
        # Remove prefixo monetário e espaços
        cleaned = re.sub(r"[R$\s]", "", value_str)
        # Formato brasileiro: ponto como milhar, vírgula como decimal
        cleaned = cleaned.replace(".", "").replace(",", ".")
        return float(cleaned)
    except (ValueError, AttributeError):
        return None


def parse_date(date_str: Optional[str]):

    if not date_str:
        return None
    try:
        from datetime import datetime
        return datetime.strptime(date_str.strip(), "%d/%m/%Y").date()
    except ValueError:
        return None
