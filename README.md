# Assistente de Inteligência Curricular

Projeto pronto para criar um chatbot que responde com base no seu banco, usando RAG.

O Neoprofessor ESPEN usa uma base SQLite local gerada a partir de:

- `espens_clean.xlsx`
- `_2.1._MCN 2026 SPB-3_07.04.2026.docx`

## O que ele faz

- Conecta em um banco SQL via `DATABASE_URL`.
- Lê dados de uma tabela e colunas que voce definir.
- Cria um indice vetorial local (`data/vector_index.json`) com embeddings da OpenAI.
- Usa LangChain para estruturar prompts, respostas tipadas e embeddings da OpenAI.
- Mantém estado e memória rastreável por sessão de consultoria.
- Registra sessões, interações, avaliações e consumo de tokens em um banco analítico.
- Aplica portões de avanço e validações antes do planejamento.
- Recebe perguntas e responde com contexto recuperado das duas bases separadas.
- Frontend simples em HTML + CSS + JS para facilitar deploy.

## Requisitos

- Python 3.10+
- Chave da OpenAI
- Acesso ao seu banco

## Configuracao

1. Crie e ative o ambiente virtual.
2. Instale dependencias:

```bash
pip install -r requirements.txt
```

3. Copie o arquivo de ambiente:

```bash
copy .env.example .env
```

4. Gere/atualize o SQLite local a partir da planilha e do documento MCN:

```bash
python app/build_sqlite_from_csv.py
```

5. Edite o `.env` com sua chave OpenAI.

Exemplo para SQLite local (padrao deste projeto):

```env
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small

DATABASE_URL=sqlite:///./data/local.db
ANALYTICS_DATABASE_URL=postgresql://usuario:senha@host/neondb?sslmode=require
TARGET_TABLE=rag_docs
TARGET_ID_COLUMN=id
TARGET_TEXT_COLUMNS=titulo,cadastro,conteudo
MAX_ROWS=2000
TOP_K=6
```

Exemplo para Postgres:

```env
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small

DATABASE_URL=postgresql+psycopg://usuario:senha@localhost:5432/meubanco
TARGET_TABLE=clientes
TARGET_ID_COLUMN=id
TARGET_TEXT_COLUMNS=nome,descricao,observacao
MAX_ROWS=2000
TOP_K=6
```



## Executar

```bash
uvicorn app.main:app --reload
```

Abra no navegador:

`http://127.0.0.1:8000`

## Deploy com Docker

Build da imagem:

```bash
docker build -t projetoegc-rag .
```

Executar container:

```bash
docker run --rm -p 8000:8000 --env-file .env projetoegc-rag
```

Abrir no navegador:

`http://127.0.0.1:8000`

## Deploy na Vercel

Este projeto pode subir na Vercel usando Python Serverless Function.

1. Importe o repositorio na Vercel.
2. Em `Settings > Environment Variables`, configure:

```env
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
DATABASE_URL=sqlite:///./data/local.db
TARGET_TABLE=rag_docs
TARGET_ID_COLUMN=id
TARGET_TEXT_COLUMNS=titulo,cadastro,conteudo
MAX_ROWS=2000
TOP_K=6
```

3. Faça o deploy normalmente.

Observacao importante:
- Na Vercel, o indice vetorial e gravado em `/tmp/vector_index.json` em runtime.
- Esse arquivo e temporario (por instancia). Se a instancia reiniciar, o indice e recriado automaticamente na primeira pergunta.

## Fluxo de uso

1. Abra o chat no navegador.
2. Faça uma pergunta normalmente.
3. Na primeira pergunta, se ainda nao existir indice vetorial, o sistema indexa automaticamente o banco e responde.

## Endpoints

- `POST /api/index`: indexa os dados da tabela configurada.
- `POST /api/chat`: responde perguntas com base no contexto recuperado.
- `POST /api/feedback`: registra uma avaliação positiva ou negativa de uma resposta.

As tabelas `chat_sessions` e `chat_interactions` são criadas automaticamente no
banco definido por `ANALYTICS_DATABASE_URL`. Cada atualização da página inicia
uma nova sessão; as mensagens seguintes, sem atualizar a página, permanecem na
mesma sessão.

Observacao: o endpoint `POST /api/index` continua disponivel caso voce queira forcar reindexacao manual apos atualizar o banco.

## Observacoes

- Se seu banco for PostgreSQL, instale tambem o driver:

```bash
pip install psycopg[binary]
```

- O indice e local. Se mudar os dados do banco, reindexe.
