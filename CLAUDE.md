# CLAUDE.md — Finança

App pessoal de previsibilidade financeira focado em **projeção de fluxo de caixa futuro** (não histórico). O usuário lança receitas e despesas futuras e visualiza o saldo projetado dia a dia para os próximos 6 meses.

---

## Stack

- **Backend:** Python 3.12 + Django 5.2 LTS
- **Frontend:** Django Templates + Tailwind CSS (CDN) + HTMX
- **Banco:** SQLite em dev, PostgreSQL em prod (via `DATABASE_URL`)
- **Deploy:** Render — `build.sh` + `render.yaml`
- **Libs relevantes:** `python-decouple`, `dj-database-url`, `whitenoise`, `python-dateutil`

## Dev Setup

```bash
python manage.py migrate
python manage.py runserver
```

---

## Arquitetura

```
config/          # settings, urls raiz, wsgi/asgi
core/
  models.py      # todos os models
  views.py       # controllers HTTP + HTMX
  forms.py       # formulários com validações
  urls.py        # endpoints internos
  services/
    cash_flow.py # lógica de projeção (manter lógica de negócio aqui, não nas views)
  templatetags/
    currency_filters.py  # formatação BRL — usar sempre, nunca formatar moeda inline
templates/
  base.html      # Tailwind, HTMX, Chart.js, setupDatePickers() global
  partials/      # fragmentos HTML retornados exclusivamente para HTMX
static/css/
  custom.css     # glassmorphism, animações, dark layout
```

---

## Decisões arquiteturais fixas

- **Sem autenticação multi-usuário** — app pessoal, deploy independente.
- **`UserSettings` é Singleton** com `pk=1` — nunca criar mais de um registro.
- **WhiteNoise** serve os estáticos — sem Nginx/S3.

---

## Regras de negócio críticas

### Recorrências
- Regras `INSTALLMENT`: todas as parcelas são geradas e salvas **no momento da criação** da regra.
- Regras `MONTHLY`: transações são materializadas sob demanda (no acesso ao dashboard) para o horizonte de 6 meses. Transações já pagas ou editadas são preservadas.

### Metas (`Goal`)
- Aportes: transações `EXPENSE` cuja descrição começa com `"Aporte"` (case-insensitive) → somam a `current_amount`.
- Resgates: transações `INCOME` cuja descrição começa com `"Resgate"` (case-insensitive) → subtraem de `current_amount`.
- Despesas regulares vinculadas a uma meta (não Aportes) → `funded_by_goal=True` automaticamente ao salvar → somam a `spent_amount`.
- Transações com `funded_by_goal=True` são **excluídas do fluxo de caixa** e dos somatórios de despesas — não são despesas normais.
- A sincronização com a meta acontece nos métodos `save()` e `delete()` de `Transaction` — não duplicar essa lógica nas views.

### Cartão de crédito
- Fatura calculada por `get_bill_period`: período de `closing_day` do mês até o dia anterior ao `closing_day` do mês seguinte.

---

## Padrões HTMX

- Sempre retornar fragmentos HTML (`templates/partials/`) — nunca JSON.
- Usar `HX-Trigger: transactionUpdated` no header da response para notificar o dashboard e a lista de transações a se recarregarem.
- Modais são injetados em `#global-modal` e se fecham chamando `.remove()` no overlay interno.
- Qualquer input de data deve estar dentro de `.date-picker-wrap` para ser inicializado automaticamente pelo `setupDatePickers()`.

---

## CSS

- `.sidebar-link` / `.sidebar-link-active` → classes de navegação da sidebar.
- Empty states usam seletor CSS `:has()` — não adicionar JS imperativo para isso.
- Estilo premium definido em `custom.css` (glassmorphism, `backdrop-blur`, animações).

---

## Git

- **Nunca fazer commit ou push automaticamente.** Só executar `git commit` e `git push` quando o usuário pedir explicitamente.
