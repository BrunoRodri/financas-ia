# Contexto do Projeto — Finança

Este documento resume o contexto de negócio, as regras conceituais e as decisões de design arquitetural para o **Finança**, um Web App de previsibilidade financeira focado em fluxo de caixa futuro.

---

## 🎯 Objetivo de Negócio
Ao contrário da maioria dos aplicativos financeiros tradicionais que focam no histórico passado de gastos, o **Finança** foi concebido com uma filosofia prospectiva: **projetar o futuro**.

O foco é permitir que o usuário:
1. Lance receitas e despesas futuras.
2. Cadastre despesas recorrentes (mensalidades/assinaturas) e compras parceladas (cartão de crédito).
3. Visualize com precisão o saldo projetado dia a dia e mês a mês para os próximos 6 meses.
4. Planeje metas financeiras de médio/longo prazo acompanhando o percentual de acúmulo de capital.

---

## 🛠️ Stack Tecnológico

- **Backend:** Python 3.12 + Django 5.2 LTS.
- **Frontend:** Django Templates + Tailwind CSS (via CDN estruturado para alto desempenho) + HTMX (para carregamento assíncrono e lançamentos rápidos sem recarga de página).
- **Banco de Dados:** SQLite em ambiente de Desenvolvimento e PostgreSQL pronto para Produção.
- **Deploy:** Configurado para o Render (plano gratuito) com script automatizado `build.sh` e blueprint declarativo `render.yaml`.
- **Bibliotecas Importantes:**
  - `python-decouple`: Gerenciamento seguro de variáveis de ambiente.
  - `dj-database-url`: Troca dinâmica de conexão de banco de dados por URL.
  - `whitenoise`: Serviço de arquivos estáticos comprimidos para ambiente produtivo sem necessidade de Nginx/S3.
  - `python-dateutil`: Lógica robusta de cálculo de datas e recorrências complexas.

---

## ⚖️ Decisões Arquiteturais e Regras de Negócio

### 1. Ausência de Autenticação Multi-usuário
Por ser uma aplicação de uso estritamente pessoal e hospedada de forma independente, foi decidido **não incluir** autenticação multi-usuário (Login/Sign-up). Isso simplifica o schema do banco de dados e otimiza o fluxo de interação direta do proprietário.

### 2. Ponto de Partida (Saldo de Referência)
A projeção futura exige um ponto de partida real. Para isso, foi criado o model `UserSettings` no padrão Singleton (apenas um registro permitido no banco com `pk=1`).
- O usuário informa o saldo consolidado atual de suas contas bancárias físicas e a data de referência desse saldo.
- A partir dessa data, as transações futuras cadastradas são somadas/subtraídas cumulativamente para desenhar a linha do fluxo de caixa.

### 3. Abordagem Híbrida para Recorrências e Parcelas
Para garantir praticidade e flexibilidade, desenvolveu-se duas estratégias no model `RecurringRule`:
- **Parcelados (`INSTALLMENT`):** Todas as transações futuras (ex: 1/12 até 12/12) são geradas e salvas **imediatamente** no banco de dados quando a regra é criada. Isso permite que o usuário veja, edite ou exclua parcelas específicas no futuro individualmente.
- **Mensais (`MONTHLY`):** Transações recorrentes infinitas (ex: assinaturas como Netflix) são materializadas no banco sob demanda para o horizonte da projeção (próximos 6 meses) sempre que o dashboard é acessado. Transações já pagas ou editadas são mantidas intocadas.

### 4. Integração de Cartões de Crédito (`CreditCard`)
Foi criado um cadastro flexível de cartões onde o usuário define:
- Nome do cartão (Ex: Nubank, MercadoPago).
- Bandeira (Visa, Mastercard, Elo, etc.).
- Dia de fechamento da fatura e dia de vencimento.
- Cor de identificação para a interface.
As transações e as parcelas podem ser vinculadas a um cartão cadastrado para organizar e concentrar o fluxo de faturas.

### 5. Interatividade com HTMX
Todas as operações de atualização rápida (mudar status de transação para pago/pendente, deletar transações, adicionar novos cartões, adicionar metas ou lançamentos rápidos) são realizadas usando **HTMX**. O Django processa a requisição e retorna um fragmento HTML (partial template) específico que atualiza cirurgicamente a tela do usuário com micro-animações nativas descritas em `custom.css`.
