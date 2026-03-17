# Painel Financeiro Multi-loja

Sistema web em Python para controlar:
- cadastro de lojas;
- despesas fixas mensais por loja;
- vendas diarias por loja;
- rateio automatico das despesas fixas em dias uteis (segunda a sabado).

## Stack
- Flask
- Flask-SQLAlchemy
- Flask-Migrate
- PostgreSQL (Neon em producao)
- Vercel (deploy)

## ORM e migrations

Neste projeto, o equivalente ao Prisma foi substituido por:
- `SQLAlchemy` para modelos, relacionamentos e queries
- `Flask-Migrate` para migrations versionadas

Essa e a stack correta para um backend Flask/Python.

## Rodar localmente

1. Crie e ative um ambiente virtual:
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Instale as dependencias:
```powershell
pip install -r requirements.txt
```

3. Configure o banco:
- sem `DATABASE_URL`, o app usa SQLite local
- com `DATABASE_URL`, o app usa PostgreSQL/Neon

Exemplo no PowerShell:
```powershell
$env:DATABASE_URL="postgresql://USER:PASSWORD@HOST/DBNAME?sslmode=require"
```

4. Inicialize migrations na primeira vez:
```powershell
flask --app app db init
flask --app app db migrate -m "initial schema"
flask --app app db upgrade
```

5. Rode o projeto:
```powershell
python app.py
```

6. Abra no navegador:
`http://127.0.0.1:5000`

## Fluxo de banco daqui para frente

Quando voce alterar os modelos em [app.py](c:\Users\Lucas\Desktop\MAKE10\app.py), rode:

```powershell
flask --app app db migrate -m "describe change"
flask --app app db upgrade
```

## Neon

Use a connection string do Neon em `DATABASE_URL`, por exemplo:

```text
postgresql://USER:PASSWORD@HOST/DBNAME?sslmode=require
```

## Deploy

O deploy em Vercel pode ser feito sem configuracao extra:
- a Vercel detecta o projeto Flask a partir de [app.py](c:\Users\Lucas\Desktop\MAKE10\app.py)
- use a raiz do repositorio como `Root Directory`

Em producao:
1. configure `DATABASE_URL` no Vercel
2. configure `SECRET_KEY` no Vercel
3. configure `ADMIN_PASSWORD` no Vercel
4. rode as migrations contra o banco Neon antes de usar o app

Se a Vercel reclamar de preset, selecione `Other` ou `Flask` e mantenha a raiz do projeto.

## Observacao importante

`db.create_all()` nao e mais a estrategia principal. Agora o schema deve ser controlado por migrations.
