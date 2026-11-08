# Configuração local de chaves

O repositório não contém chaves de API. Cada pessoa deve configurar as suas
localmente, sem enviar os valores para o GitHub.

## Opção recomendada

1. Copie `config/api_keys.example.json` para `config/api_keys.json`.
2. Preencha somente os provedores que pretende usar.
3. Mantenha `config/api_keys.json` local; ele é ignorado pelo Git.

## Alternativa por ambiente

Copie `.env.example` para `.env.local` e exporte as variáveis antes de iniciar
o servidor. Variáveis de ambiente têm precedência sobre o arquivo JSON local.

O caminho da configuração é relativo à raiz do clone. Se o projeto estiver em
outro local, defina `GOLDENAI_ROOT` para essa raiz.

Não coloque valores reais neste documento, em issues, handoffs, testes ou
arquivos de configuração versionados. Se uma chave já tiver sido compartilhada
por engano, revogue-a no provedor e gere outra; apagar o arquivo depois não
revoga uma credencial que já foi exposta.

