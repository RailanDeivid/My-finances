# Deploy — Oracle Cloud Free Tier + Cloudflare Tunnel

Stack: Django + PostgreSQL + Redis + Nginx + Cloudflare Tunnel rodando em Docker.

---

## Pré-requisitos

- Conta no [Cloudflare](https://cloudflare.com) com o domínio `railandeivid.com.br` configurado
- Cartão de crédito para cadastro na Oracle (não cobra nada no plano gratuito)

---

## Parte 1 — Criar conta e VM na Oracle Cloud

### 1.1 Cadastro

1. Acesse [cloud.oracle.com](https://cloud.oracle.com) e clique em **"Start for free"**
2. Preencha nome, e-mail e país (**Brasil**)
3. Informe o cartão de crédito (só para verificação, não há cobrança)
4. Confirme o e-mail e conclua o cadastro

### 1.2 Criar a VM (instância Ampere ARM — Always Free)

1. No painel, vá em **"Compute" → "Instances" → "Create Instance"**
2. Configure:
   - **Name:** `my-finances`
   - **Image:** Ubuntu 22.04 (clique em "Change image" para selecionar)
   - **Shape:** clique em "Change shape" → selecione **"Ampere"** → `VM.Standard.A1.Flex`
     - OCPUs: `2`
     - RAM: `12 GB`
     *(o plano free permite até 4 OCPUs e 24 GB no total entre instâncias)*
   - **Networking:** deixe o padrão (cria VCN automaticamente)
   - **SSH keys:** clique em **"Generate a key pair for me"** e baixe as duas chaves (`.key` e `.key.pub`)
3. Clique em **"Create"** e aguarde a VM ficar com status **"Running"** (1–2 min)

### 1.3 Anotar o IP público

Na página da instância, copie o **"Public IP address"** — você vai precisar para conectar via SSH.

---

## Parte 2 — Liberar portas no firewall da Oracle

A Oracle bloqueia portas por padrão. Precisamos liberar a **22 (SSH)** — as demais não precisam abrir porque o Cloudflare Tunnel não exige porta aberta.

1. Na página da instância, clique na **subnet** em "Primary VNIC"
2. Clique na **Security List** padrão
3. Clique em **"Add Ingress Rules"** e adicione:
   - Source CIDR: `0.0.0.0/0`
   - IP Protocol: `TCP`
   - Destination Port: `22`
4. Salve

---

## Parte 3 — Configurar a VM via SSH

### 3.1 Conectar

```bash
# No terminal do seu Mac
chmod 400 /caminho/para/sua-chave.key
ssh -i /caminho/para/sua-chave.key ubuntu@SEU_IP_PUBLICO
```

### 3.2 Instalar Docker e Docker Compose

```bash
# Atualizar pacotes
sudo apt update && sudo apt upgrade -y

# Instalar Docker
curl -fsSL https://get.docker.com | sudo sh

# Adicionar seu usuário ao grupo docker (sem precisar de sudo)
sudo usermod -aG docker $USER
newgrp docker

# Verificar instalação
docker --version
docker compose version
```

### 3.3 Instalar Git

```bash
sudo apt install git -y
```

---

## Parte 4 — Clonar o projeto

```bash
# Na VM, clone o repositório
git clone https://github.com/SEU_USUARIO/My-finances.git
cd My-finances
```

---

## Parte 5 — Criar o Cloudflare Tunnel

### 5.1 Criar o túnel no painel Cloudflare

1. Acesse [one.dash.cloudflare.com](https://one.dash.cloudflare.com)
2. Vá em **"Networks" → "Tunnels" → "Create a tunnel"**
3. Escolha **"Cloudflared"** e clique em **Next**
4. Dê o nome `my-finances` e clique em **"Save tunnel"**
5. Escolha o ambiente **Docker** — copie o token que aparecer (começa com `eyJ...`)
6. Na seção **"Public Hostnames"**, clique em **"Add a public hostname"**:
   - Subdomain: `myfinances`
   - Domain: `railandeivid.com.br`
   - Type: `HTTP`
   - URL: `nginx:80`
7. Salve

### 5.2 Gerar uma SECRET_KEY segura para o Django

```bash
# Rode isso na VM para gerar uma chave
python3 -c "import secrets; print(secrets.token_urlsafe(50))"
```

Copie o resultado.

---

## Parte 6 — Criar o arquivo .env.prod

```bash
# Ainda na VM, dentro da pasta do projeto
nano .env.prod
```

Cole o conteúdo abaixo substituindo os valores:

```env
COMPOSE_PROJECT_NAME=my-finances

# Django
SECRET_KEY=COLE_A_CHAVE_GERADA_AQUI
DEBUG=False
ALLOWED_HOSTS=myfinances.railandeivid.com.br

# Banco de dados
POSTGRES_DB=myfinancesDB
POSTGRES_USER=postgres
POSTGRES_PASSWORD=CRIE_UMA_SENHA_FORTE_AQUI
DB_HOST=db
DB_PORT=5432

# Redis
REDIS_URL=redis://redis:6379/0

# OpenAI
OPENAI_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
OPENAI_TEMPERATURE=0.2

# Evolution API (WhatsApp)
EVOLUTION_API_URL=http://evolution-api:8080
EVOLUTION_INSTANCE_NAME=myfinances
EVOLUTION_API_KEY=CRIE_UMA_CHAVE_FORTE_AQUI

# Cloudflare Tunnel
TUNNEL_TOKEN=COLE_O_TOKEN_DO_CLOUDFLARE_AQUI
```

Salve com `Ctrl+O`, `Enter`, `Ctrl+X`.

---

## Parte 7 — Subir o projeto

```bash
# Dentro da pasta My-finances na VM
docker compose -f docker-compose.prod.yml up -d --build
```

Aguarde o build terminar (pode levar 3–5 min na primeira vez).

### Verificar se está tudo rodando

```bash
docker compose -f docker-compose.prod.yml ps
```

Todos os serviços devem estar com status **"running"**.

### Ver logs em tempo real

```bash
docker compose -f docker-compose.prod.yml logs -f
```

---

## Parte 8 — Testar

Acesse no navegador: **https://myfinances.railandeivid.com.br**

Se aparecer o app, está funcionando.

---

## Parte 9 — Fazer o app reiniciar automaticamente

Todos os serviços já têm `restart: always` no `docker-compose.prod.yml`, então reiniciam sozinhos se a VM reiniciar.

Para garantir que o Docker sobe com a VM:

```bash
sudo systemctl enable docker
```

---

## Comandos úteis no dia a dia

```bash
# Ver status dos containers
docker compose -f docker-compose.prod.yml ps

# Ver logs de um serviço específico
docker compose -f docker-compose.prod.yml logs -f web

# Reiniciar um serviço
docker compose -f docker-compose.prod.yml restart web

# Atualizar o projeto após um git pull
git pull
docker compose -f docker-compose.prod.yml up -d --build

# Acessar o shell do Django
docker compose -f docker-compose.prod.yml exec web python manage.py shell

# Criar superusuário admin
docker compose -f docker-compose.prod.yml exec web python manage.py createsuperuser

# Parar tudo
docker compose -f docker-compose.prod.yml down
```

---

## Solução de problemas

### Site não abre
```bash
# Ver se o túnel está conectado
docker compose -f docker-compose.prod.yml logs tunnel
```

### Erro 502 Bad Gateway
```bash
# Ver se o Django está rodando
docker compose -f docker-compose.prod.yml logs web
```

### Banco de dados não conecta
```bash
# Ver se o PostgreSQL está saudável
docker compose -f docker-compose.prod.yml ps db
```
