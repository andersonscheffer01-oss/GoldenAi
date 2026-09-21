# License Audit — OpenClaw

---

## OpenClaw License

```
MIT License

Copyright (c) 2026 OpenClaw Foundation

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## Análise

| Item | Valor |
|------|-------|
| License | MIT |
| Copyright | OpenClaw Foundation, 2026 |
| Copyleft | NÃO (MIT é permissiva) |
| Commercial use | PERMITIDO |
| Modification | PERMITIDO |
| Distribution | PERMITIDO |
| Private use | PERMITIDO |
| Liability | ISENTO |
| Warranty | ISENTO |

---

## Implicações para Jarvis

### PODE (com atribuição):
- Ler código OpenClaw para referência
- Copiar conceitos e padrões
- Portar algoritmos pequenos
- Usar como inspiração arquitetural

### PODE (mesmo sem atribuição, mas recomendado):
- Adaptar padrões para Python/Jarvis
- Usar ideias de arquitetura
- Reproduzir contratos/ interfaces

### NÃO PRECISA:
- Copiar o LICENSE para Jarvis
- Distribuir código OpenClaw
- Citar OpenClaw em cada arquivo

### RECOMENDADO:
- Criar `THIRD_PARTY_NOTICES.md` no futuro
- Documentar referências em comments quando apropriado
- Manter `references/openclaw/` como referência isolada

---

## Commit Info

| Item | Valor |
|------|-------|
| SHA | `ecc4c992` (shallow clone, HEAD of main) |
| Date | 2026-09-17 (clone date) |
| Branch | main |
| Clone type | `--depth 1` |
| Path | `C:\GoldenAI\references\openclaw` |

---

## Risks

| Risco | Nível | Nota |
|-------|-------|------|
| License violation | BAIXO | MIT é permissivo; Jarvis é privado |
| Attribution missing | BAIXO | Recomendado mas não obrigatório para uso privado |
| Code contamination | MEDIUM | NÃO copiar código diretamente; portar conceitos |
| Dependency injection | NÃO | Jarvis NÃO depende de OpenClaw |
