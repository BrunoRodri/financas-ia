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
│       ├── card_row.html
│       ├── goal_card.html
│       ├── recurring_row.html
│       ├── transaction_form.html
│       └── transaction_row.html
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
