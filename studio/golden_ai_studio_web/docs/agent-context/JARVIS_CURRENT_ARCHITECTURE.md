# Arquitetura Atual do Jarvis

Fluxo de execução:

`entrada -> Memory Retrieval -> JarvisBrain -> ToolRegistry -> validação -> JarvisService -> SecurityManager -> handler -> AuditLog`

O `ToolRegistry` é a fonte única das 47 ferramentas. Ele gera automaticamente os schemas
das 46 ferramentas expostas ao Brain. `open_any_exe` permanece registrada para uso interno,
mas não é apresentada ao modelo.

O `JarvisService` centraliza normalização, validação, risco dinâmico, confirmação,
cancelamento, timeout e auditoria. Voice e Vision permanecem módulos separados.
O `GoldenMemoryManager` centraliza sessão, memória episódica/semântica, embeddings e retrieval.
