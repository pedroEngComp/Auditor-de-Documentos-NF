# Auditor de Documentos NF — NLConsulting 2026

Aplicação web para auditoria automatizada de notas fiscais usando IA.

## Arquitetura

```
backend/   → Python + FastAPI (processa arquivos, chama Gemini API, detecta anomalias)
frontend/  → React + Vite (upload, tabela de resultados, exportação)
```

## Como rodar localmente

### Backend

```bash
cd backend
pip install -r requirements.txt

# Configure a chave da API (nunca coloque no código)
export GEMINI_API_KEY="sua-chave-aqui"

uvicorn main:app --reload --port 8000
```

API disponível em: http://localhost:8000
Documentação automática: http://localhost:8000/docs

### Frontend

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

Frontend disponível em: http://localhost:5173

## Endpoints

| Método | Rota | Descrição |
|--------|------|-----------|
| POST | `/process` | Upload de .zip ou .txt — retorna JSON com documentos e anomalias |
| POST | `/export/csv` | Exporta resultado como CSV (fonte do Power BI) |
| POST | `/export/excel` | Exporta resultado como Excel com duas abas |
| POST | `/export/audit-log` | Exporta log de auditoria rastreável |
| GET | `/health` | Status da API |

## Decisões técnicas

### Por que FastAPI?
- Suporte nativo a async/await — fundamental para processar 1.000 arquivos em paralelo sem travar
- Documentação automática via OpenAPI
- Validação de tipos embutida

### Por que processar em lotes com semáforo?
O dataset tem 1.000 arquivos. Chamadas sequenciais à Gemini API levariam ~30 min.
Com `asyncio.Semaphore(5)` processamos até 5 arquivos simultaneamente sem estourar o rate limit.

### Estratégia de extração em dois passos
1. **Parser local** tenta extrair campos linha a linha (rápido, sem custo de API)
2. **Gemini API** só é chamada para arquivos com encoding problemático ou campos ausentes

Isso reduz o consumo de tokens e o tempo total de processamento.

### Por que múltiplos encodings?
Arquivos reais de sistemas legados frequentemente usam `latin-1` ou `cp1252`.
O parser tenta `utf-8 → latin-1 → cp1252 → iso-8859-1` antes de escalar para a IA.

### Aprovadores conhecidos — threshold percentual
Ao invés de uma lista fixa de aprovadores, o sistema deriva quem é "conhecido" do próprio dataset.
Um aprovador é considerado legítimo se aparece em pelo menos 0.5% dos documentos.
Isso escala automaticamente para qualquer volume — funciona tanto com 1.000 quanto com 100.000 arquivos.

### Versão do prompt
Cada registro registra `prompt_version` para rastreabilidade — se o prompt mudar,
é possível saber qual versão gerou cada resultado.

### Anomalias detectadas
- **NF duplicada** — mesmo número de NF aparece mais de uma vez
- **CNPJ divergente** — CNPJ difere do padrão histórico do fornecedor
- **Fornecedor sem histórico** — fornecedor aparece em menos de 2 documentos
- **Data NF posterior ao pagamento** — pagamento antes da emissão da nota
- **Valor fora da faixa** — desvio z-score > 2.5σ em relação à média do fornecedor
- **Aprovador não reconhecido** — aparece em menos de 0.5% do dataset
- **STATUS inconsistente** — CANCELADO com data de pagamento preenchida
- **Arquivo não processável** — encoding inválido ou campos truncados

## Deploy

- **Backend**: Render.com — adicione `GEMINI_API_KEY` nas variáveis de ambiente
- **Frontend**: Vercel — aponta `VITE_API_URL` para a URL do backend no Render

## Segurança

- Chave de API exclusivamente via variável de ambiente no servidor
- Validação de tipo e tamanho de arquivo no upload
- Tratamento de exceções da API sem expor stack traces ao usuário
- CORS configurado (restrinja `allow_origins` em produção para a URL do seu frontend)