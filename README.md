# Painel Financeiro Multi-loja

Sistema web em Python para controlar:
- cadastro de lojas (escalável para quantas lojas precisar);
- despesas fixas mensais por loja;
- vendas diárias por loja;
- rateio automático das despesas fixas em dias úteis (segunda a sábado).

## Stack
- Flask
- Flask-SQLAlchemy
- PostgreSQL (Neon em produção)
- Vercel (deploy)

## Rodar localmente

1. Crie e ative um ambiente virtual:
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Instale as dependências:
```powershell
pip install -r requirements.txt
```

3. (Opcional) Configure `DATABASE_URL` para usar Postgres local/remoto.
Sem `DATABASE_URL`, o app usa SQLite local (`finance.db`).

4. Execute:
```powershell
python app.py
```

5. Abra no navegador:
`http://127.0.0.1:5000`

## Regras de cálculo implementadas

- O custo fixo mensal de cada loja é a soma das despesas fixas ativas no mês.
- O custo fixo diário é `total_fixos_mensal / quantidade_de_dias_uteis_no_mes`.
- Dias úteis considerados: segunda a sábado (domingo excluído).
- Resultado mensal da loja: `vendas_no_mes - fixos_no_mes`.
- Resultado diário: `venda_do_dia - rateio_fixo_do_dia`.

## Deploy em produção (Vercel + Neon)

### 1. Criar banco no Neon
1. No Neon, crie um projeto e um database Postgres.
2. Copie a connection string (algo como):
```text
postgresql://USER:PASSWORD@HOST/DBNAME?sslmode=require
```

### 2. Subir projeto no GitHub
1. Crie um repositório no GitHub.
2. Faça commit e push deste projeto.

### 3. Importar no Vercel
1. No Vercel, clique em **Add New > Project**.
2. Selecione o repositório.
3. Framework: pode deixar auto-detect.
4. Deploy.

### 4. Configurar variável de ambiente no Vercel
No projeto Vercel, vá em **Settings > Environment Variables** e adicione:
- `DATABASE_URL` = sua URL do Neon

Depois, faça **Redeploy**.

### 5. Estrutura de deploy já pronta neste projeto
- `api/index.py` (entrypoint serverless da Vercel)
- `vercel.json` (roteia todas as rotas para Flask)

## Observações importantes

- Em produção, use sempre Postgres (Neon). SQLite não é persistente em ambiente serverless.
- O app cria tabelas automaticamente na inicialização da função.
