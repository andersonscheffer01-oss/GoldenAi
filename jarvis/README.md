# Golden Jarvis

Golden Jarvis e a nova fundacao de assistente pessoal do ecossistema Golden AI.
Esta etapa cria apenas a base segura e independente do backend.

## Escopo implementado

As Etapas 1, 2, 3, 4, 5 e 6 estao implementadas. A Etapa 2 adiciona uma interface PWA
responsiva, login, chat visual inicial, dashboard financeiro vazio, configuracoes,
menu inferior para celular e upload autenticado de fotos e documentos.

O upload aceita JPG, JPEG, PNG, WEBP e PDF, com limite padrao de 10 MB.
O arquivo e validado por assinatura binaria, recebe nome interno aleatorio,
hash SHA-256 e fica fora da pasta publica do frontend. A exclusao remove o
arquivo fisico e preserva o registro no banco com status `excluido` para auditoria.

A Etapa 3 conecta o chat ao Ollama local usando, por padrao, `qwen2.5vl:7b`.
Conversas e mensagens sao persistidas no banco do Jarvis, com historico recente,
isolamento por usuario e tratamento seguro de indisponibilidade do Ollama.

A Etapa 4 permite analisar comprovantes enviados, extrair dados estruturados
com revisao humana e confirmar ou cancelar a analise. A confirmacao ainda nao
cria um gasto: essa criacao fica reservada para a Etapa 5.

A Etapa 5 adiciona lancamentos manuais e a conversao explicita de comprovantes
confirmados. Valores monetarios sao armazenados em centavos inteiros, sem float.
O dashboard consulta somente lancamentos ativos.

A Etapa 6 adiciona categorias hierarquicas, orcamentos, progresso de limites,
parcelamentos informativos, alertas internos, lembretes e a estrutura opcional
de inscricao para Web Push. O motor verifica orcamentos periodicamente e evita
duplicar o mesmo gatilho.

A Etapa 7 adiciona comandos financeiros controlados pelo chat. Consultas usam
dados do banco; criacoes, edicoes, exclusoes, parcelamentos, lembretes e baixa de
parcelas geram uma acao pendente com hash e validade de 15 minutos. A execucao
exige confirmacao explicita, inclusive por texto (`sim`/`confirmar` ou
`nao`/`cancelar`). O registro fechado de ferramentas impede que a IA execute
SQL, pagamentos, transferencias ou ordens de trading.

A Etapa 8 adiciona um agente seguro e separado para o computador Windows em
`C:\GoldenAI\jarvis\pc_agent`. Ele inicia conexoes para o backend, envia
heartbeat, informa CPU, memoria, disco, Ollama, Jarvis e MT5, e consome apenas
comandos confirmados pela API. Nao existe shell livre, PowerShell, CMD, captura
automatica de tela, exclusao de arquivos, pagamento, transferencia ou ordem de
trading.

## Diferenca entre Golden atual e Golden Jarvis

O Golden AI Studio atual continua em:

`C:\GoldenAI\studio\golden_ai_studio_web`

Ele contem Scanner, MT5, estrategias, backtests, graficos e radar de trading.

O Golden Jarvis fica separado em:

`C:\GoldenAI\jarvis`

Nesta etapa ele nao altera o Golden atual, nao consulta bancos, nao usa MT5 e nao
envia ordens de trading.

## Acessar a interface

Com o servidor iniciado, abra:

- Aplicacao PWA: `http://127.0.0.1:8780/app`
- Login: `http://127.0.0.1:8780/login`
- Documentacao da API: `http://127.0.0.1:8780/docs`

Depois do login, o menu inferior permite alternar entre Jarvis, Financas,
Alertas e Ajustes. O dashboard financeiro nesta etapa mostra apenas o estado
inicial, sem dados ficticios.

No chat, use `Nova` para criar uma conversa ou selecione uma conversa anterior
para reabrir seu historico. Enter envia e Shift + Enter cria uma nova linha.
Anexos continuam sendo recebidos e armazenados, mas nao sao analisados pelo
Ollama nesta etapa.

Para analisar um comprovante, abra Financas, envie uma imagem ou PDF e clique
em `Analisar comprovante`. Revise os campos no modal, corrija o que for preciso
e somente entao confirme. Valores ausentes, documento desconhecido e baixa
confianca exigem revisao manual. Cancelar nao cria nenhum lancamento.

Na area Financas, use `Novo gasto` ou `Nova receita` para cadastrar lancamentos.
Os filtros de periodo atualizam os totais, a lista e os graficos. Lancamentos
podem ser editados ou excluidos logicamente: saem dos totais, mas permanecem
no historico de auditoria.

Depois de confirmar uma analise, use a acao de criar lancamento financeiro.
O sistema bloqueia duplicidade da mesma analise e usa `Outros` quando nenhuma
categoria foi definida.

Na aba `Alertas`, crie lembretes, marque alertas como lidos e pause ou reative
alertas. Os alertas internos funcionam em HTTP local. Notificacoes push exigem
HTTPS e permissao dada pelo usuario; nenhum push e obrigatorio para usar o sistema.

No chat, `Quanto gastei hoje?` e `Qual foi minha maior despesa?` consultam o banco.
Para registrar, use por exemplo `Registre R$ 50 no mercado`; o Jarvis mostra uma
previa e aguarda `Confirmar` ou `Cancelar`. Sem valor, ele pede esclarecimento.
As acoes pendentes ficam em `GET /api/jarvis/acoes-pendentes`.

Orcamentos e parcelamentos sao cadastrados pelas rotas da API nesta etapa. As
parcelas sem vencimento conhecido ficam com status `sem_data` e nao sao tratadas
como vencidas. Nenhuma fatura bancaria e criada automaticamente.

## Ollama local

Verifique se o Ollama esta ativo e quais modelos existem:

```powershell
ollama list
Invoke-RestMethod http://127.0.0.1:11434/api/tags
```

Se necessario, inicie o servico com `ollama serve`. O backend usa
`JARVIS_OLLAMA_BASE_URL`, `JARVIS_OLLAMA_MODEL` e
`JARVIS_OLLAMA_TIMEOUT_SECONDS` somente no servidor. O frontend nunca recebe
o endereco interno do Ollama. Depois de alterar o `.env`, reinicie o Jarvis.

Para consultar o historico, use a lista de conversas na tela ou as rotas
autenticadas `GET /api/chat/conversas` e `GET /api/chat/conversas/{id}`.

## Rotas das Etapas 3 a 7

- `GET /`, `GET /app`, `GET /login`: paginas da PWA.
- `GET /manifest.json`, `GET /sw.js`: instalacao e cache basico da PWA.
- `POST /api/uploads`: recebe um arquivo autenticado.
- `GET /api/uploads`: lista somente os arquivos do usuario autenticado.
- `GET /api/uploads/{id}`: consulta um arquivo proprio.
- `DELETE /api/uploads/{id}`: exclui o arquivo fisico proprio e registra a exclusao.
- `POST /api/chat/conversas`: cria uma conversa autenticada.
- `GET /api/chat/conversas`: lista as conversas ativas do usuario.
- `GET /api/chat/conversas/{id}`: abre uma conversa propria com mensagens.
- `DELETE /api/chat/conversas/{id}`: desativa uma conversa propria.
- `POST /api/chat/mensagem`: envia mensagem ao Ollama e salva a resposta.
- `GET /api/uploads/{id}/content`: entrega o arquivo somente ao proprio usuario.
- `POST /api/comprovantes/{arquivo_id}/analisar`: processa uma imagem ou PDF.
- `GET /api/comprovantes/{arquivo_id}/analise`: consulta a ultima analise propria.
- `POST /api/analises/{analise_id}/confirmar`: salva edicoes e confirma a analise.
- `POST /api/analises/{analise_id}/cancelar`: cancela a analise.
- `POST /api/analises/{analise_id}/reanalisar`: tenta processar novamente, ate 3 vezes.
- `GET/POST /api/financas/categorias`: lista e cria categorias manuais.
- `GET/POST /api/financas/contas`: lista e cria contas manuais.
- `GET/POST /api/financas/cartoes`: lista e cria cartoes sem numero completo.
- `POST /api/financas/lancamentos`: cria gasto ou receita manual.
- `GET/PUT/DELETE /api/financas/lancamentos/{id}`: consulta, edita ou exclui logicamente.
- `POST /api/analises/{analise_id}/gerar-lancamento`: converte analise confirmada.
- `GET /api/financas/resumo`: retorna totais reais do periodo.
- `GET /api/financas/por-categoria`, `/por-dia`, `/por-forma-pagamento` e `/maiores-gastos`: relatorios basicos.
- `POST/GET/PUT/DELETE /api/financas/orcamentos`: gerencia orcamentos.
- `GET /api/financas/orcamentos/{id}/progresso`: acompanha uso e limite.
- `POST/GET/DELETE /api/financas/parcelamentos`: gerencia parcelamentos.
- `POST /api/financas/parcelamentos/{id}/parcelas`: adiciona parcela manual.
- `PUT /api/financas/parcelas/{id}`, `/marcar-paga` e `/cancelar`: atualiza parcelas.
- `POST/GET /api/alertas`: cria e lista alertas internos.
- `POST /api/alertas/{id}/pausar`, `/ativar`, `/marcar-lido`; `DELETE /api/alertas/{id}`.
- `POST/DELETE /api/notificacoes/subscribe`: registra ou cancela Web Push.
- `GET /api/notificacoes/preferencias`: preferencias de notificacao.
- `POST /api/financas/alertas/verificar`: executa verificacao manual do motor.
- `POST /api/jarvis/comando`: interpreta uma consulta ou prepara uma acao.
- `GET /api/jarvis/acoes-pendentes`: lista acoes aguardando confirmacao.
- `POST /api/jarvis/acoes/{id}/confirmar` e `/cancelar`: executa ou cancela.
- `POST /api/dispositivos/pareamento/criar`: cria codigo de pareamento de uso unico.
- `POST /api/dispositivos/pareamento/confirmar`: pareia o agente e retorna o token uma unica vez.
- `GET /api/dispositivos/pc`, `/pc/{id}`, `/pc/{id}/status`: lista e consulta PCs.
- `POST /api/dispositivos/pc/{id}/revogar`: revoga o token do computador.
- `POST /api/dispositivos/agente/heartbeat`: heartbeat autenticado do agente.
- `GET /api/pc/status`: ultimo estado conhecido do PC.
- `GET /api/pc/ferramentas`: comandos permitidos e bloqueados.
- `POST/GET /api/pc/comandos`: solicita/lista comandos do PC.
- `GET /api/pc/comandos/{id}`: consulta um comando.
- `POST /api/pc/comandos/{id}/confirmar` e `/cancelar`: confirma ou cancela comando.
- `GET /api/pc/agente/comandos/proximo`: agente busca proximo comando pendente.
- `POST /api/pc/agente/comandos/{id}/resultado`: agente devolve resultado.

Comandos suportados incluem resumo/gastos por periodo ou categoria, maior gasto,
orcamentos, parcelas e lembretes; criar orcamento, parcelamento ou lembrete;
marcar parcela paga; e editar ou excluir lancamento por ID. A data padrao de um
lembrete criado pelo chat e o dia seguinte, sempre apresentada antes da
confirmacao.

A tabela `arquivos` fica no banco do Jarvis e relaciona cada envio ao usuario.
O diretorio fisico usado e `C:\\GoldenAI\\jarvis\\uploads\\pending`.

## Agente seguro do PC

Instale as dependencias do agente:

```powershell
cd C:\GoldenAI\jarvis\pc_agent
pip install -r requirements.txt
```

No Jarvis, abra `Ajustes` e clique em `Criar pareamento`. Depois rode:

```powershell
cd C:\GoldenAI\jarvis\pc_agent
python agent.py --pair 123456
```

O token do dispositivo e salvo localmente em `C:\GoldenAI\jarvis\pc_agent\.env`
e nunca e enviado para o frontend. Para iniciar manualmente:

```powershell
C:\GoldenAI\jarvis\pc_agent\run_pc_agent.bat
```

Para iniciar automaticamente, use o Agendador de Tarefas do Windows apontando
para `run_pc_agent.bat`. Esta etapa nao instala servico Windows e nao exige
privilegio administrativo.

Configure programas permitidos em
`C:\GoldenAI\jarvis\pc_agent\allowed_programs.json`. O agente aceita somente a
chave cadastrada, por exemplo `golden_jarvis`, `metatrader` ou `navegador`. Se
o caminho estiver vazio ou inexistente, ele responde que o programa ainda nao
foi configurado.

Comandos permitidos:

- `verificar_status_pc`
- `verificar_ollama`
- `verificar_jarvis`
- `verificar_mt5`
- `abrir_aplicativo_autorizado`

Comandos bloqueados:

- shell livre, CMD, PowerShell, apagar/mover arquivos, instalar programas,
  alterar registro, reiniciar/desligar computador, pagamentos, transferencias e
  ordens de trading.

Abrir aplicativo exige confirmacao. Consultas de status podem ser executadas
diretamente. Para revogar um computador, use a tela `Ajustes` ou
`POST /api/dispositivos/pc/{id}/revogar`.

## Criar ambiente virtual

Abra o PowerShell:

```powershell
cd C:\GoldenAI\jarvis
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

## Instalar dependencias

```powershell
pip install -r requirements.txt
```

## Configurar ambiente

Crie um arquivo `.env` a partir do `.env.example`.

```powershell
Copy-Item .env.example .env
```

Depois altere `JARVIS_SECRET_KEY` para uma chave forte. Nao coloque tokens,
senhas bancarias ou chaves reais diretamente no codigo.

## Criar administrador

O sistema nao cria usuario padrao com senha fixa.

```powershell
cd C:\GoldenAI\jarvis\backend
python -m app.create_admin
```

O comando pede nome, email e senha.

## Iniciar servidor

Pelo atalho:

```powershell
C:\GoldenAI\jarvis\run_jarvis.bat
```

Ou manualmente:

```powershell
cd C:\GoldenAI\jarvis\backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8780
```

API:

`http://127.0.0.1:8780`

Swagger:

`http://127.0.0.1:8780/docs`

Health:

`http://127.0.0.1:8780/api/health`

## Acesso pelo iPhone na rede local

O atalho `run_jarvis.bat` inicia o servidor em `0.0.0.0:8780`, detecta o
IPv4 privado ativo e mostra os dois enderecos de acesso. Neste computador,
o endereco esperado e:

`http://192.168.1.100:8780/app`

O iPhone precisa estar conectado a mesma rede Wi-Fi do computador. Nao use
redirecionamento de portas no roteador e nao exponha a porta 8780 na internet.
O endereco pode mudar quando o roteador renovar o DHCP; execute novamente o
atalho para consultar o endereco atual.

Para iniciar manualmente com acesso pela rede local:

```powershell
cd C:\GoldenAI\jarvis\backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8780
```

Para conferir o IPv4 selecionado:

```powershell
powershell -ExecutionPolicy Bypass -File C:\GoldenAI\jarvis\scripts\detect_local_ipv4.ps1
```

### Firewall do Windows

O projeto nao altera o firewall automaticamente. A rede deve estar configurada
como `Privada`. Se o Windows ainda bloquear o iPhone, execute como administrador
somente depois de autorizar a abertura local:

```powershell
New-NetFirewallRule -DisplayName "Golden Jarvis 8780 Local Network" -Direction Inbound -Protocol TCP -LocalPort 8780 -Action Allow -Profile Private
```

Para remover essa permissao:

```powershell
Remove-NetFirewallRule -DisplayName "Golden Jarvis 8780 Local Network"
```

Se o computador estiver em uma rede marcada como `Publica`, nao crie uma regra
para o perfil Publico. Altere para `Privada` apenas quando for uma rede domestica
ou de confianca. VPNs, interfaces virtuais e redes de convidados podem impedir
que o iPhone alcance o computador.

## Banco de dados

Banco local de desenvolvimento:

`C:\GoldenAI\jarvis\data\jarvis_runtime.db`

O banco antigo do Golden AI Studio nao e usado:

`C:\GoldenAI\studio\golden_ai_studio_web\golden_runtime.db`

## Executar testes

```powershell
cd C:\GoldenAI\jarvis\backend
python -m pytest
```

Os testes usam banco SQLite temporario sempre que possivel.

## Backup

Para fazer backup do Jarvis:

```powershell
Compress-Archive -Path C:\GoldenAI\jarvis\* -DestinationPath C:\GoldenAI\backups\golden_jarvis_backup.zip -Force
```

## Seguranca desta etapa

- Senhas sao armazenadas com Argon2.
- Tokens usam JWT assinado.
- Sessoes podem ser revogadas no logout.
- Auditoria registra cadastro, login, falhas, logout e acesso negado.
- Configuracao usa variaveis de ambiente.
- Upload exige autenticacao, limite de tamanho, MIME real, extensao permitida,
  nome interno aleatorio e hash SHA-256.
- O service worker nao intercepta chamadas da API nem arquivos enviados.
- A integracao pessoal com Meu Pluggy e somente leitura; credenciais da aplicacao
  ficam exclusivamente no `.env` e chaves temporarias nao sao registradas em logs.
- Nenhum OCR ou processamento de comprovantes foi implementado.
- O chat com Ollama foi implementado nesta etapa; OCR, leitura de comprovantes,
  criacao de gastos, financas reais e memoria semantica ainda nao foram implementados.
- Analises usam `qwen2.5vl:7b`; imagens sao normalizadas em memoria e PDFs sao
  renderizados em no maximo 5 paginas. Nenhum base64 e salvo no banco.
- Cadastros manuais continuam disponiveis. Contas, cartoes, saldos, faturas e
  transacoes do Meu Pluggy aparecem em uma area separada.
- A importacao de transacoes exige selecao, categorias e confirmacao final. IDs
  externos impedem duplicidade mesmo quando a sincronizacao e repetida.
- Comandos financeiros exigem confirmacao e nao executam pagamentos, transferencias,
  SQL, comandos do sistema ou ordens de trading.
- Nenhum scraping bancario foi implementado.
- O agente do computador executa somente consultas e abertura de programas
  previamente autorizados, com confirmacao obrigatoria para abertura.
- Nenhuma ordem de trading e executada pelo Golden Jarvis nesta etapa.

## Open Finance pessoal - Meu Pluggy

Configure apenas no arquivo local `.env`:

```env
JARVIS_OPEN_FINANCE_PROVIDER=pluggy
PLUGGY_CLIENT_ID=
PLUGGY_CLIENT_SECRET=
```

Reinicie o Jarvis e abra **Open Finance** no menu. O backend troca as credenciais
por uma API key de curta duracao e envia ao Widget oficial somente um Connect Token
temporario. O fluxo usa `clientUserId`, evita conexoes duplicadas, guarda o `itemId`
e permite revogar a conexao. O Jarvis nao recebe nem armazena a senha bancaria.

Esta integracao nao contem endpoints de pagamento, Pix ou transferencia. A
cobertura de contas, cartoes, faturas e transacoes depende do conector disponibilizado
pelo Meu Pluggy para cada instituicao.

## Etapa 9 - VPS, HTTPS e acesso remoto

O pacote de implantacao esta em `deploy/`, com Docker Compose, Caddy, PostgreSQL,
diagnostico Linux/Windows, servico systemd alternativo, migracao validada e
backup/restauracao testavel.

Estado atual: os arquivos de producao foram preparados e testados localmente. A
publicacao real esta pendente porque IP, sistema operacional, credenciais e dominio
da VPS MustHost nao foram fornecidos. Consulte `deploy/README_DEPLOY.md` e
`deploy/deployment-checklist.md`.

Seguranca aplicada:

- apenas Caddy publica 80/443; backend, PostgreSQL e Ollama nao publicam portas;
- producao exige chave forte, URL publica HTTPS, origens HTTPS e hosts autorizados;
- login usa cookie HttpOnly/Secure em producao e a sessao expira no banco;
- uploads continuam privados e sao lidos apenas por rota autenticada do proprietario;
- Service Worker guarda somente uma lista fechada de arquivos estaticos;
- agente remoto recusa HTTP e usa a validacao TLS padrao do sistema;
- logs rotativos filtram mensagens com marcadores de segredo.

Ollama nao e exposto publicamente. Para uso remoto, instale-o na VPS/rede privada
ou implemente futuramente um relay autenticado; nao abra a porta 11434 na internet.
