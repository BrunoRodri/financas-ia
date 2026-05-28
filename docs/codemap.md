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
│   │       ├── __init__.py
│   │       └── seed_db.py      # Comando de sementeira customizado (limpeza e mock dinâmico)
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
- `credit_card` (ForeignKey): Cartão de crédito associado à regra.
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

### 5. `Goal`
- `name` (CharField): Nome do objetivo.
- `target_amount` (Decimal): Meta total de capital.
- `current_amount` (Decimal): Capital atualmente acumulado.
- `deadline` (DateField): Prazo final limite.
- `color` (CharField): Cor personalizada.

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

### 3. Datepicker Premium e Desabilitação Condicional de Parcelas
* **Datepicker Completo:** O campo de data inicial das Regras Recorrentes e nos formulários do dashboard conta com um componente customizado que combina digitação livre direta, máscara automatizada brasileira (`DD/MM/YYYY`) e calendário clicável interativo com tratamento anti-clipping de CSS.
* **Desabilitação de Parcelas:** Ao selecionar a recorrência "Mensal" no cadastro de regras recorrentes, o campo "Parcelas" é automaticamente zerado, desativado e esmaecido via Javascript.

### 4. Modal de Confirmação para Exclusão de Regras
* **HTMX Dynamic Popups:** Ao clicar no botão de remoção de uma Regra Recorrente, o sistema consulta via HTMX o status da regra.
* **Preservação de Histórico:** Se houver transações já pagas pertencentes à regra, o modal (glassmorphism/blur) oferece ao usuário as opções de **"Excluir apenas as NÃO PAGAS"** (preservando o histórico e desvinculando os lançamentos quitados) ou **"Excluir TUDO"**.

