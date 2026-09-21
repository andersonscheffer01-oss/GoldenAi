# Handoff - Golden Jarvis P1 Voice Performance

## Estado

P1 implementada no VoiceService único, sem iniciar P2 e sem alterar Brain, providers,
Computer Use, navegador, WhatsApp, imagem, vídeo ou trading. Orchestrator segue `shadow`.
Status final: PARTIAL somente porque falta aprovação de um comando humano no microfone real.

## Implementação

- `jarvis_core/voice.py`: Whisper `small/int8` em CPU, `beam=1`, `best_of=1`, idioma PT,
  prompt inicial curto, warmup assíncrono e modelo persistente.
- Gate adaptativo com calibração de ruído, pre-roll, início de fala real e silêncio final
  padrão de 550 ms; valores configuráveis por ambiente.
- Metadados do decoder viram confiança e classificação `VALID_COMMAND`, `LOW_CONFIDENCE`
  ou `IGNORED_NOISE`; alucinações conhecidas e repetição são rejeitadas.
- Comando de alto risco exige confiança mais estrita antes da execução.
- `jarvis_core/voice_service.py`: descarte de backlog antigo, IDs por fala, proteção contra
  autoescuta do TTS, invalidação de captura sobreposta e parada cooperativa.
- Telemetria: captura, início/fim de fala, silêncio, STT, normalização, primeiro áudio TTS,
  total do turno, modelo, compute, gate e rejeição.
- `jarvis_desktop/views/dev_view.py`: exposição compacta da telemetria real de voz.
- Áudio usado pelo STT é temporário e removido inclusive em falha. Benchmarks também não
  retêm gravações.

## Benchmark controlado

Mesmo corpus de 10 frases, SAPI do Windows, execução serial e sem CUDA:

| Modelo | P50 STT | P95 STT | Roteamento | CPU total | RSS delta |
|---|---:|---:|---:|---:|---:|
| base/int8, beam 5 | 656 ms | 1153 ms | 6/10 | 32,19 s | 132,7 MB |
| small/int8, beam 1 | 1760 ms | 2021 ms | 8/10 | 76,36 s | 299,8 MB |

Arquivos: `tests/benchmark_voice_p1_before.json` e `tests/benchmark_voice_p1_after.json`.
O `small` foi escolhido por qualidade. Apesar do STT mais lento, a janela de silêncio caiu
de 2,0 s para 0,55 s: fim da fala até transcrição estimado de ~2722 ms para ~2360 ms.

## Validação

- Suíte final: `154 passed, 72 subtests passed`; `py_compile` aprovado nos módulos P1.
- Casos P1 cobrem gate, ruído, alucinação, confiança, alto risco, warmup, backlog,
  `utterance_id`, autoescuta, fast paths sem LLM e rota conversacional.
- Teste acústico alto-falante para microfone rejeitou corretamente a alucinação de silêncio
  e não executou comando fantasma.
- Observação em silêncio: nenhum evento/comando criado.
- Comando humano solicitado não foi capturado; por isso não registrar PASS de microfone.

## Limitações

- Primeiro áudio TTS mede o instante de entrega ao player/SAPI, não o onset físico no alto-falante.
- Pipeline é serial; interrupção falada durante a própria resposta TTS não foi implementada.
- Aprovação humana do microfone permanece obrigatória para concluir P1 como PASS.

## Próximo

Executar uma única validação humana: iniciar voz e dizer `Jarvis, que horas são?`. Confirmar
transcrição, rota WINDOWS, resposta falada uma vez e ausência de autoescuta. Só depois marcar
P1 concluída. Não iniciar P2 sem autorização explícita.
