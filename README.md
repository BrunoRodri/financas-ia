# 📈 Finança — Previsibilidade Financeira

O **Finança** é um Web App pessoal de previsibilidade financeira focado em **fluxo de caixa futuro**, inspirado na filosofia do "App do Breno". Ao contrário dos gerenciadores financeiros tradicionais que olham para o passado, o Finança foi projetado para responder à pergunta mais importante: **"Como estará o meu saldo nos próximos meses?"**

Com uma interface moderna, dark-mode nativo, glassmorphism e atualizações sem recarga de página via HTMX, você pode simular receitas, despesas avulsas, assinaturas recorrentes e compras parceladas no cartão de crédito para visualizar seu caixa com precisão absoluta de até 6 meses à frente.

---

## 🚀 Principais Funcionalidades

- **🔮 Projeção de Saldo Futuro (Cash Flow):** Gráfico interativo de linha (Chart.js) e tabela de fluxo consolidado que projetam seu saldo dia a dia e mês a mês para os próximos 6 meses.
- **⚡ Lançamento Rápido (HTMX):** Form inline otimizado para adicionar receitas e despesas com o mínimo de cliques e atualização em tempo real sem dar refresh na página.
- **💳 Gestão de Cartões de Crédito:** Cadastre múltiplos cartões (ex: Nubank, MercadoPago) com controle de dia de fechamento, dia de vencimento e cores visuais customizadas para organizar suas compras.
- **🔄 Regras Recorrentes Híbridas:**
  - **Mensalidade / Assinaturas (`MONTHLY`):** Materialização automática on-demand para os próximos 6 meses (ex: mensalidade de streaming).
  - **Compras Parceladas (`INSTALLMENT`):** Geração imediata de todas as parcelas no banco de dados (ex: `1/12`, `2/12`), permitindo editar ou liquidar parcelas individuais no futuro.
- **🎯 Metas Financeiras (Goals):** Defina objetivos (ex: "Viagem pro Rio"), estipule metas de valor e prazos limites, acompanhando o progresso com barras dinâmicas coloridas.
- **🛡️ Saldo de Referência Integrado:** Ponto de partida flexível que aparece inserido em sua posição temporal exata na listagem de transações, servindo de base real para o cálculo de Saldo Líquido. Transações históricas anteriores a este saldo são atenuadas visualmente (`opacity-45`) e assinaladas como "Não computadas" com explicação em tooltip.
- **🎨 UI/UX Avançada e Controle Inteligente:**
  - **Filtros Avançados & Agrupamento:** Painel de filtros de transações dinâmico (ocultável) e listagem agrupada de forma elegante por mês cronológico.
  - **Datepicker Customizado:** Componente de calendário visual clicável integrado com digitação direta e máscara de formatação nacional (`DD/MM/YYYY`).
  - **Segurança de Deleção:** Modal dinâmico via HTMX ao excluir Regras Recorrentes, permitindo deletar apenas as parcelas futuras/não pagas e manter o histórico de pagamentos passados intacto.
  - **Desativação Dinâmica:** Ajuste instantâneo de campos de formulário de regras, bloqueando e limpando o campo de parcelas se a recorrência selecionada for mensal.

---

## 🛠️ Stack Tecnológico

- **Backend:** Python 3.12+ / Django 5.2 (LTS)
- **Frontend:** Django Templates + Tailwind CSS (Custom Theme) + HTMX (Fragments dinâmicos)
- **Visualização:** Chart.js (Gráficos interativos)
- **Banco de Dados:** SQLite (Desenvolvimento) / PostgreSQL (Produção no Render)
- **Static Files:** WhiteNoise (Serviço de estáticos com compressão manifest)
- **Deploy:** Configuração de deploy gratuito pronta com `build.sh` e `render.yaml`

---

## 📂 Estrutura do Projeto e Documentação

Para mais detalhes sobre as entranhas do app e regras de negócio específicas, consulte a nossa pasta `docs/`:
- 📕 [Contexto do Projeto e Filosofia (`docs/context.md`)](./docs/context.md) — Conceitos de design, decisões arquiteturais e regras de materialização.
- 📘 [Codemap do Projeto (`docs/codemap.md`)](./docs/codemap.md) — Árvore completa de arquivos, relacionamentos de models do banco e diagrama de fluxo do algoritmo de projeção.

---

## 💻 Como Rodar Localmente

### 1. Pré-requisitos
Certifique-se de ter o **Python 3.10+** e **Git** instalados na sua máquina.

### 2. Clonar e Configurar o Ambiente
```bash
# Clone o repositório
git clone git@github.com:BrunoRodri/financas-ia.git
cd financas-ia

# Crie e ative o ambiente virtual
python3 -m venv venv
source venv/bin/activate  # No Linux/Mac
# venv\Scripts\activate   # No Windows

# Instale as dependências
pip install -r requirements.txt
```

### 3. Configurar Variáveis de Ambiente
Crie um arquivo `.env` na raiz do projeto (use o `.env.example` como base):
```bash
cp .env.example .env
```

### 4. Executar Migrações e Iniciar o Servidor
```bash
# Aplique as migrações do banco de dados
python manage.py migrate

# (Opcional) Crie um usuário admin para gerenciar tags e dados brutos
python manage.py createsuperuser

# Inicie o servidor de desenvolvimento
python manage.py runserver
```
Acesse a aplicação em [http://127.0.0.1:8000/](http://127.0.0.1:8000/).

---

## ☁️ Deploy Gratuito no Render

O repositório já está 100% configurado para deploy automático usando a funcionalidade de **Render Blueprints**.

1. Crie uma conta gratuita em [Render.com](https://render.com/).
2. Conecte seu repositório do GitHub.
3. No painel do Render, vá em **New > Blueprints**.
4. Selecione o repositório `financas-ia`.
5. O Render lerá automaticamente o arquivo `render.yaml` e instanciará:
   - Um banco de dados **PostgreSQL** gerenciado (plano gratuito).
   - Um **Web Service** Python executando a compilação via `build.sh` (instalando pacotes, compilando estáticos e aplicando migrações) e servindo via **Gunicorn**.
6. Pronto! Sua aplicação estará online em poucos minutos.

---

## 🎨 Design System e Estilização

A aplicação utiliza uma paleta de cores escura personalizada com acentos vibrantes:
- **Fundo Escuro:** `#0a0e1a` e `#0f1629` (Sleek Dark Mode).
- **Glassmorphism:** Cartões translúcidos com bordas finas semi-transparentes (`border-white/5`) e desfoque de fundo (`backdrop-blur-xl`).
- **Verde Dinâmico (Entradas/Income):** `#22c55e` (Aumento de saldo).
- **Vermelho Dinâmico (Saídas/Expense):** `#ef4444` (Queda de saldo).
- **Micro-animações:** Efeitos suaves de hover em botões, transições de status HTMX e animações `@keyframes` personalizadas definidas em `static/css/custom.css`.
