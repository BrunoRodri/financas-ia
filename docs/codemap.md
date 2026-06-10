# Codemap — Finança

Este documento fornece um mapeamento estruturado do diretório, arquitetura do banco de dados (Models) e fluxos das principais views/services do projeto **Finança**.

---

## 📂 Árvore de Diretórios do Projeto

```
financa/
├── config/                     # Configurações globais do Django
│   ├── settings.py             # Configurações de segurança, DB dinâmico, WhiteNoise e Decouple
│   ├── urls.py                 # Roteamento raiz do projeto (inclui admin/ e core.urls)
│   ├── wsgi.py                 # Ponto de entrada para servidores WSGI (Gunicorn)
│   └── asgi.py                 # Ponto de entrada para servidores assíncronos ASGI
│
├── core/                       # App principal da aplicação
│   ├── admin.py                # Configurações do painel administrativo
│   ├── apps.py                 # Registro do app
│   ├── forms.py                # Formulários com validações complexas e DateInput formatados
│   ├── models.py               # Estrutura do banco de dados (Tag, CreditCard, RecurringRule, etc.)
│   ├── urls.py                 # Definição de endpoints internos da aplicação
│   ├── views.py                # Controladores que lidam com requisições HTTP e HTMX
│   │
│   ├── management/             # Comandos de gerenciamento customizados do Django
│   │   ├── __init__.py
│   │   └── commands/
│   │       └── __init__.py
│   │
│   ├── services/               # Camada de lógica de negócio isolada
│   │   ├── __init__.py
│   │   └── cash_flow.py        # Algoritmo de projeção e materialização de caixa
│   │
│   └── templatetags/           # Filtros personalizados para Django Templates
│       ├── __init__.py
│       └── currency_filters.py # Formatação de moeda BRL (R$ 1.234,56)
│
├── templates/                  # Camada de Apresentação (Interface)
│   ├── base.html               # Layout base com Tailwind, HTMX, Chart.js e Menu responsivo
│   ├── dashboard.html          # Página inicial unificada com gráficos e inserção rápida
│   │
│   ├── cards/
│   │   └── list.html           # Página de listagem e criação de cartões de crédito
│   ├── goals/
│   │   └── list.html           # Página de acompanhamento de metas financeiras
│   ├── recurring/
│   │   └── list.html           # Página de controle de regras de recorrência/parcelados
│   ├── transactions/
│   │   └── list.html           # Página de listagem geral de transações com filtros
│   ├── settings/
│   │   └── edit.html           # Página de ajuste do saldo e data de referência
│   │
│   └── partials/               # Fragmentos HTML retornados especificamente para HTMX
│       ├── balance_card.html
│       ├── card_edit_form.html # Formulário inline de edição de cartões de crédito
│       ├── card_row.html
│       ├── goal_card.html
│       ├── goal_card_adjust_form.html # Formulário inline de aporte e resgate de metas
│       ├── goal_delete_modal.html # Modal de confirmação para exclusão de metas
│       ├── recurring_delete_modal.html # Modal de confirmação para exclusão de regras recorrentes
│       ├── recurring_row.html
│       ├── tag_list.html       # Lista de tags na tela de configurações
│       ├── tag_row.html        # Linha para visualização/remoção de uma tag
│       ├── tag_section.html    # Bloco completo de gerenciamento de tags
│       ├── transaction_edit_form.html # Formulário inline de edição de transações
│       ├── transaction_form.html
│       ├── transaction_initial_balance_row.html # Linha especial cronológica para saldo de partida
│       ├── transaction_row.html
│       └── transactions_full_content.html # Container principal dinâmico de transações com filtros
│
├── static/                     # Arquivos estáticos
│   └── css/
│       └── custom.css          # Estilos personalizados (glassmorphism, animações e layout dark)
│
├── build.sh                    # Script de shell executado na compilação do Render
├── render.yaml                 # Blueprint declarativo para infraestrutura do Render (Web Service + DB)
├── requirements.txt            # Dependências em cache para ambiente produtivo
├── .env.example                # Template de configuração local de variáveis de ambiente
└── .gitignore                  # Arquivos e diretórios ignorados pelo Git
```

---

## 🗄️ Modelagem de Dados (`core/models.py`)

Abaixo estão descritos os atributos chaves dos modelos principais do projeto:

### 1. `Tag`
- `name` (CharField, unique=True): Nome identificador da tag.
- `color` (CharField): Código hexadecimal da cor para exibição na UI (Default: `#6366f1`).

### 2. `CreditCard`
- `name` (CharField): Nome identificador do cartão (Ex: Nubank).
- `last_digits` (CharField, max_length=4): Últimos 4 dígitos para identificação.
- `brand` (Choices): Bandeiras suportadas (Visa, Mastercard, Elo, Amex, Hipercard, Outra).
- `color` (CharField): Cor hexadecimal para estilizar o cartão na UI.
- `due_day` (Integer, 1-31): Dia de vencimento da fatura.
- `closing_day` (Integer, 1-31): Dia de fechamento da fatura.

### 3. `RecurringRule`
- `description` (CharField): Descrição da regra.
- `amount` (DecimalField): Valor base do lançamento.
- `type` (Choices): Entrada (`INCOME`) ou Saída (`EXPENSE`).
- `recurrence_type` (Choices): Mensal recorrente (`MONTHLY`) ou Parcelado (`INSTALLMENT`).
- `total_installments` (IntegerField): Quantidade total de parcelas (para compras parceladas).
- `start_date` (DateField): Data inicial do ciclo.
- `end_date` (DateField, auto-calculado): Fim da regra (calculado para parcelamentos).
- `is_active` (BooleanField): Ativa ou inativa a geração de novos lançamentos.
- `is_archived` (BooleanField): Indica se a regra foi arquivada (regras arquivadas são ocultadas por padrão na UI e não geram transações).
- `credit_card` (ForeignKey): Cartão de crédito associado à regra.
- `goal` (ForeignKey): Meta vinculada à regra (opcional).
- `tags` (ManyToManyField): Associação flexível de marcadores.

### 4. `Transaction`
- `description` (CharField): Descrição do lançamento específico.
- `amount` (Decimal): Valor.
- `due_date` (DateField): Data de vencimento/ocorrência.
- `type` (Choices): Entrada ou Saída.
- `status` (Choices): Pendente (`PENDING`) ou Pago (`PAID`).
- `recurring_rule` (ForeignKey): Regra geradora (nula para transações avulsas).
- `credit_card` (ForeignKey): Cartão vinculado.
- `installment_number` (IntegerField): Indicador ordinal da parcela (Ex: 3).
- `funded_by_goal` (BooleanField): Indica se a despesa foi financiada pelo saldo acumulado de uma meta (não afeta fluxo de caixa).

### 5. `Goal`
- `name` (CharField): Nome do objetivo.
- `target_amount` (Decimal): Meta total de capital.
- `current_amount` (Decimal): Capital atualmente acumulado.
- `spent_amount` (Decimal): Capital já utilizado/gasto da meta.
- `available_amount` (property): Capital disponível para uso (`current_amount - spent_amount`).
- `deadline` (DateField): Prazo final limite.
- `color` (CharField): Cor personalizada.
- `is_archived` (BooleanField): Indica se a meta foi arquivada/encerrada (metas arquivadas são ocultadas por padrão na UI e excluídas dos formulários de transação).

### 6. `UserSettings`
- `current_balance` (Decimal): Saldo unificado inicial.
- `balance_date` (DateField): Data de consolidação do saldo inicial.

---

## 🔄 Fluxo de Negócio do fluxo de caixa (`core/services/cash_flow.py`)

O coração analítico do sistema reside na função `project_cash_flow(months_ahead=6)`:

```
                  ┌───────────────────────────────┐
                  │   dashboard.html (Acesso)     │
                  └───────────────┬───────────────┘
                                  │
                                  ▼
             ┌─────────────────────────────────────────┐
             │ materialize_recurring_transactions()    │
             │ (Materializa regras MONTHLY no banco)   │
             └───────────────┬─────────────────────────┘
                                  │
                                  ▼
             ┌─────────────────────────────────────────┐
             │ Carrega UserSettings (Saldo Inicial     │
             │ e Data de Referência)                   │
             └───────────────┬─────────────────────────┘
                                  │
                                  ▼
             ┌─────────────────────────────────────────┐
             │ Filtra todas as Transactions no         │
             │ intervalo [Hoje -> Hoje + 6 meses]      │
             └───────────────┬─────────────────────────┘
                                  │
                                  ▼
             ┌─────────────────────────────────────────┐
             │ Itera dia a dia aplicando somas de      │
             │ Entrada/Saídas e acumulando o saldo      │
             └───────────────┬─────────────────────────┘
                                  │
                                  ▼
             ┌─────────────────────────────────────────┐
             │ Retorna dados estruturados para         │
             │ Chart.js (Grafico) e Tabelas na View   │
             └─────────────────────────────────────────┘
```

---

## 💎 Funcionalidades de UI/UX e Regras Especiais

Abaixo estão detalhados os recursos especiais de usabilidade, regras de fluxo e tratamento refinado de dados presentes na aplicação:

### 1. Saldo de Referência Cronológico e Histórico Atenuado
* **Posicionamento Estável:** O saldo de referência cadastrado nas configurações é dinamicamente inserido em sua posição temporal exata na tabela de transações.
* **Estilização Neutra:** O valor do Saldo de Referência é exibido em cor cinza neutra, sem o sinal de `+` ou `-`, para refletir que se trata de uma definição de valor físico.
* **Atenuação Histórica:** Transações ocorridas antes da data de referência do saldo de partida são marcadas como **"Não computadas"** (badge explicativa + tooltip descritivo) e exibidas com opacidade reduzida (`opacity-45`, com transição suave para `100%` ao passar o mouse).
* **Cálculos Corretos do Fluxo:** Os cards superiores da tela de transações calculam os somatórios considerando apenas as transações *posteriores* à data de referência. O card de **"Saldo Líquido"** soma o Saldo de Referência às receitas ativas e subtrai as despesas ativas.

### 2. Filtros Avançados Inteligentes na Listagem de Transações
* **Toggle Dinâmico:** Os filtros avançados (busca, tipo, status, cartão, tags e intervalo de datas) começam ocultados por padrão. Um botão dinâmico interativo permite alternar a visibilidade de forma fluida.
* **Agrupamento Cronológico:** A lista de transações agrupa os lançamentos visualmente por meses cronológicos (ex: "DEZEMBRO 2025") utilizando a tag `ifchanged` do Django Template.
* **Filtro de Ciclo de Fatura:** Implementada a opção de visualizar transações baseadas no ciclo de fechamento real do cartão de crédito (calculado pela função utilitária `get_bill_period`). Ao ativar o filtro "Ver Fatura", as transações do mês selecionado são filtradas com base no período que se inicia no dia de fechamento do cartão do respectivo mês até o dia anterior ao fechamento do mês subsequente (ex: de 14/06 a 13/07 para fechamento no dia 14), eliminando a confusão de visualização entre o mês de compra e o mês de pagamento da fatura.

### 3. Datepicker Premium Unificado e Desabilitação Condicional de Parcelas
* **Datepicker Global Unificado:** A lógica do calendário customizado foi generalizada e centralizada em uma única função JavaScript global `setupDatePickers()` no template base `base.html`.
* **Inicialização Automatizada (HTMX & DOM):** O script monitora o carregamento inicial da página (`DOMContentLoaded`) e settle do HTMX (`htmx:afterSettle`). Qualquer campo de data que esteja encapsulado no wrapper `.date-picker-wrap` é automaticamente inicializado e ganha digitação direta mascarada (`DD/MM/YYYY`) e calendário visual interativo sem código redundante.
* **Cobertura Completa:** Aplica-se a todos os inputs de data do sistema: Lançamento Rápido, Regras Recorrentes, Edição Inline de Transações, Criação de Metas Financeiras e Data de Referência do Saldo.
* **Desabilitação de Parcelas:** Ao selecionar a recorrência "Mensal" no cadastro de regras recorrentes, o campo "Parcelas" é automaticamente zerado, desativado e esmaecido via Javascript.

### 4. Modais de Confirmação para Exclusão (Regras e Transações)
* **HTMX Dynamic Popups:** Ao clicar no botão de remoção de uma Regra Recorrente ou de uma Transação avulsa, o sistema consulta via HTMX a rota de confirmação correspondente e exibe um modal glassmorphic (`backdrop-blur-sm` e sombreamentos premium) injetado dinamicamente em `#global-modal`.
* **Exclusão de Regras (Preservação de Histórico):** Se houver transações já pagas pertencentes à regra, o modal oferece as opções de **"Excluir apenas as NÃO PAGAS"** (preservando o histórico e desvinculando os lançamentos quitados) ou **"Excluir TUDO"**.
* **Exclusão de Transações (Alerta Inteligente de Metas):** Se a transação estiver vinculada a uma meta financeira, o modal informa dinamicamente o usuário de que a exclusão daquela transação reverterá automaticamente o valor correspondente do progresso acumulado da meta associada.
* **Resiliência, Foco e Fechamento Autocontido via Reset de Placeholder:** O container global de modais (`#global-modal`) é um placeholder `div` simples sem estilos na raiz do documento, garantindo que não interfira no fluxo ou nos cliques da página quando vazio. Quando um modal é carregado, o overlay interno é posicionado com `fixed inset-0 z-[105]` para capturar eventos e escurecer a tela. O fechamento é feito diretamente pelo modal no DOM removendo a div de overlay (`.remove()`), permitindo aberturas e fechamentos ilimitados e independentes.
* **Regra de swap obrigatória (`hx-swap="innerHTML"`):** Todos os botões que abrem modais (`transaction_row.html`, `recurring_row.html`, `goal_card.html`) devem declarar explicitamente `hx-swap="innerHTML"` no botão que aponta para `#global-modal`. Sem isso, o HTMX herda `hx-swap="outerHTML"` do container pai (`#transactions-page-container`) e substitui o elemento `#global-modal` inteiro pelo overlay, removendo-o do DOM ao fechar e quebrando todas as aberturas subsequentes.
* **Listener `htmx:afterRequest` com filtro de verbo:** O listener em `base.html` que limpa o `#global-modal` após uma exclusão verifica `config.verb === 'post'` antes de agir. Isso é necessário porque as rotas de confirmação (`/delete/confirm/`) são GETs e contêm `/delete/` na URL — sem o filtro de verbo, o modal seria limpo imediatamente após ser carregado.

### 5. Ocultação Dinâmica de Empty States (CSS :has)
* **CSS Declarativo Moderno:** Para evitar que mensagens como "Nenhuma meta criada" continuem visíveis ao criar elementos via HTMX (ou reapareçam incorretamente ao deletar), foi implementada uma regra CSS declarativa usando o seletor moderno `:has()`.
* **Sem Código Imperativo:** Quando o grid/lista de metas, cartões ou regras recorrentes passa a ter qualquer filho que não seja o próprio container de empty state (`:has(> :not(.empty-state))`), a mensagem de estado vazio é ocultada automaticamente com `display: none`. Se todos os itens forem deletados, ela é reexibida instantaneamente sem a necessidade de scripts JS ou swaps HTMX adicionais.

### 6. Sincronização Automática e Bidirecional de Metas e Transações
* **Relacionamento Direto (ForeignKey):** A model `Transaction` possui uma chave estrangeira opcional `goal` apontando para `Goal`. Transações geradas a partir do formulário de metas recebem essa referência automaticamente, e transações criadas manualmente podem ser vinculadas a metas através do campo "Meta Vinculada" no painel de lançamento rápido. Adicionalmente, regras recorrentes (`RecurringRule`) também podem ser vinculadas diretamente a uma meta, propagando essa referência automaticamente para todas as suas transações geradas (seja no momento da criação da regra ou durante a materialização mensal).
* **Mapeamento de Fluxos:** 
  - Aportes oficiais (tipo **EXPENSE** com descrição começando por "Aporte" case-insensitive) adicionam ao valor acumulado da meta (`current_amount`).
  - Resgates oficiais (tipo **INCOME** com descrição começando por "Resgate" case-insensitive) subtraem do valor acumulado da meta (`current_amount`).
  - Despesas regulares (tipo **EXPENSE**) vinculadas a uma meta que não sejam Aportes são **automaticamente** consideradas como financiadas pela meta (`funded_by_goal = True`) ao salvar no banco, sem a necessidade de flags ou checkboxes na UI. Elas somam ao valor utilizado da meta (`spent_amount`) em vez de diminuir o acumulado (`current_amount`).
  - Transações com `funded_by_goal=True` são automaticamente excluídas tanto da projeção de fluxo de caixa (dashboard) quanto dos somatórios de despesas e saldo líquido dos cards na página de transações para evitar dupla contabilidade.
  - Outros tipos de transação associados à meta não têm impacto de saldo.
* **Sincronização no Ciclo de Vida da Model (Save/Delete):**
  - **Criação/Edição:** Ao salvar uma transação vinculada a uma meta, o Django intercepta o salvamento (`save()`), detecta se houve alteração de valor, tipo, descrição, `funded_by_goal` ou mudança de meta. Ele reverte o impacto antigo na meta anterior e aplica o novo impacto na meta atual de forma atômica e resiliente.
  - **Exclusão:** Ao excluir uma transação vinculada, o método `delete()` é interceptado para desfazer automaticamente o impacto correspondente (revertendo o aporte, resgate ou gasto utilizado da meta).
* **Exibição Visual Premium:** Transações integradas a metas recebem uma badge na cor âmbar com o ícone de dinheiro `💰 Nome da Meta` na listagem de transações para demonstrar de forma clara que foram financiadas pela meta e não interferem no fluxo de caixa líquido.

### 7. Sistema de Arquivamento (Finalização) de Metas e Regras Recorrentes
* **Organização e Redução de Poluição:** Metas encerradas e regras recorrentes antigas podem ser arquivadas para liberar espaço visual na tela, sem a necessidade de excluí-las (o que destruiria o histórico de transações e tags).
* **Arquivamento Manual e Automático:**
  - **Metas e Regras Gerais:** Podem ser arquivadas ou restauradas manualmente através do ícone correspondente na interface.
  - **Regras Parceladas (`INSTALLMENT`):** São arquivadas de forma 100% automatizada pelo sistema assim que a última parcela expira (quando a data atual ultrapassa a data final da regra recorrente). Esse processo roda em background no carregamento das listagens.
* **Abas e Seletores Ultra-Rápidos:** A visualização utiliza abas nativas com filtragem CSS de alta performance (`:has()`). Ao invés de fazer requisições extras ao banco de dados para filtrar itens, o navegador oculta instantaneamente os itens arquivados ou ativos conforme a aba selecionada no container pai.
* **Contadores Dinâmicos:** Os cabeçalhos das abas exibem a quantidade exata de itens ativos e arquivados/encerrados, atualizados automaticamente em tempo real após a estabilização do HTMX (`htmx:afterSettle`) decorrente de qualquer ação (criação, remoção ou alteração de estado).
* **Prevenção de Cache no Navegador:** Foi adicionado um parâmetro de versão (`?v=2`) à importação do `custom.css` no template base, garantindo que o navegador não utilize versões em cache desatualizadas do CSS e aplique corretamente as regras de exibição e ocultação baseadas nas abas de ativos/arquivados.

### 8. Atualização Dinâmica do Dashboard e Listas (Sem Refresh)
* **Comunicação por Eventos (`HX-Trigger`):** A comunicação entre as ações de backend (criar, editar, excluir ou marcar como pago/pendente uma transação, além de depósitos/resgates em metas) e a interface é feita de forma assíncrona usando o cabeçalho HTTP `HX-Trigger: transactionUpdated`.
* **Recarregamento Reativo dos Contêineres:** O contêiner do Dashboard (`#dashboard-container`) e o da página de Transações (`#transactions-page-container`) escutam o evento `transactionUpdated from:body`. Ao recebê-lo, realizam uma requisição GET transparente e automática (`hx-get="{{ request.get_full_path }}"` com `hx-select`), recarregando todos os dados, tabelas e cards com as query parameters de filtros ativas preservadas.
* **Ciclo de Vida do Gráfico de Projeção:** O gráfico de projeção de saldo (`Chart.js`) e seus respectivos dados JSON estão contidos dentro do `#dashboard-container`. Ao recarregar o fragmento, os novos dados são injetados e a inicialização é re-executada. Para evitar o erro de canvas em uso (`Canvas is already in use`), a instância anterior (`window.cashFlowChartInstance`) é detectada e destruída com segurança (`.destroy()`) antes de instanciar o novo gráfico.

### 9. Arquitetura de Navegação: Sidebar Responsiva
* **Layout Unificado (Sidebar):** Substituiu o menu superior anterior por uma barra lateral esquerda fixa de 256px (`w-64`) em telas grandes. O conteúdo principal (`<main>`) é deslocado lateralmente com `md:pl-64` para manter o grid estrutural intocado.
* **Responsividade e Comportamento Mobile:**
  - Em telas menores (mobile/tablet < md), um cabeçalho fixo no topo (`header`) é exibido com o botão Hamburguer.
  - A Sidebar é ocultada (`-translate-x-full`) e, ao clicar no Hamburguer, desliza na tela a partir da esquerda (`translate-x-0`) como uma gaveta (drawer) sobreposta.
  - Um overlay de fundo escurecido e desfocado (`#sidebar-overlay` com `.bg-black/60` e `.backdrop-blur-sm`) cobre o resto da tela. Clicar no overlay ou no botão fechar (X) desliza a Sidebar de volta para fora da tela.
  - O script em `base.html` escuta o evento `htmx:afterSwap` para fechar automaticamente a Sidebar no mobile quando um link é clicado e a requisição HTMX é concluída.
* **Estilização Premium:** Os links utilizam a classe `.sidebar-link` com efeito hover translúcido suave, e o link correspondente à página ativa recebe `.sidebar-link-active` que destaca o item com cor roxo/indigo e uma borda vertical esquerda distintiva de 3px (`border-left`).

### 10. Edição Inline Avançada de Transações
* **Gerenciamento de Cartões e Tags na Alteração:** Ao clicar para editar uma transação, o formulário inline exibe opções completas de edição para Tipo de Pagamento (Dinheiro/Pix/Débito vs. Cartão de Crédito), seleção do Cartão de Crédito correspondente e checkboxes com preenchimento reativo para todas as Tags cadastradas no sistema.
* **Isolamento de Scripts de Comportamento:** Para viabilizar que múltiplos formulários de alteração inline de transações estejam abertos simultaneamente sem conflito no DOM, a lógica JavaScript dinâmica de ocultação de campos de cartão/pagamento é encapsulada para cada transação individual utilizando o ID de banco (`{{ txn.id }}`) nos seletores HTML.
