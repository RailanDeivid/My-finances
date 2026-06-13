# Deploy na AWS — MyFinances

Stack: Django + PostgreSQL + Gunicorn + Nginx + Docker Compose  
Alvo: EC2 free tier (t2.micro ou t3.micro) + domínio próprio

---

## Pré-requisitos

- Conta AWS criada (free tier ativo)
- Domínio comprado (ex: Namecheap, Registro.br, Cloudflare)
- Chave SSH gerada localmente

---

## 1. Criar a instância EC2

1. Acesse o [Console AWS](https://console.aws.amazon.com) → **EC2 → Launch Instance**
2. Configurações:
   - **Nome:** myfinances
   - **AMI:** Ubuntu Server 24.04 LTS (free tier eligible)
   - **Instance type:** t2.micro ou t3.micro (free tier)
   - **Key pair:** crie ou selecione uma existente — salve o `.pem`
   - **Security group:** crie novo com as regras abaixo

### Regras do Security Group

| Tipo | Porta | Origem |
|------|-------|--------|
| SSH | 22 | Seu IP (My IP) |
| HTTP | 80 | 0.0.0.0/0 |
| HTTPS | 443 | 0.0.0.0/0 |

3. **Storage:** 20 GB gp3 (suficiente no free tier)
4. Clique em **Launch Instance**

---

## 2. Apontar o domínio para a instância

1. No painel EC2, copie o **IP público** da instância (ou aloque um Elastic IP para fixar o endereço)
2. No painel do seu registrador de domínio, crie dois registros DNS tipo **A**:

```
@    →  <IP público da instância>
www  →  <IP público da instância>
```

> A propagação pode levar até 24h, mas geralmente ocorre em 15-30 minutos.

---

## 3. Conectar na instância via SSH

```bash
chmod 400 ~/Downloads/sua-chave.pem
ssh -i ~/Downloads/sua-chave.pem ubuntu@<IP da instância>
```

---

## 4. Instalar Docker e Docker Compose

```bash
# Atualiza pacotes
sudo apt update && sudo apt upgrade -y

# Instala Docker
curl -fsSL https://get.docker.com | sudo sh

# Adiciona seu usuário ao grupo docker (evita usar sudo sempre)
sudo usermod -aG docker $USER
newgrp docker

# Verifica instalação
docker --version
docker compose version
```

---

## 5. Clonar o projeto

```bash
# Instala git
sudo apt install git -y

# Clona o repositório
git clone https://github.com/SEU_USUARIO/my-finances.git
cd my-finances
```

> Se o repositório for privado, configure uma chave SSH no GitHub primeiro:
> `ssh-keygen -t ed25519 -C "seu@email.com"` e adicione a chave pública em GitHub → Settings → SSH Keys.

---

## 6. Configurar variáveis de ambiente de produção

```bash
# Copia o exemplo
cp .env.example .env.prod

# Edita com suas variáveis reais
nano .env.prod
```

Preencha o `.env.prod` com:

```env
DEBUG=False
SECRET_KEY=GERE_COM_O_COMANDO_ABAIXO
ALLOWED_HOSTS=seudominio.com,www.seudominio.com

POSTGRES_DB=myfinancesDB
POSTGRES_USER=postgres_prod
POSTGRES_PASSWORD=UMA_SENHA_FORTE_AQUI
DB_HOST=db
DB_PORT=5432

DJANGO_SETTINGS_MODULE=config.settings.production
```

Para gerar o `SECRET_KEY`:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(50))"
```

---

## 7. Obter certificado SSL gratuito (Let's Encrypt)

```bash
sudo apt install certbot -y

# Gera o certificado (substitua pelo seu domínio)
sudo certbot certonly --standalone \
  -d seudominio.com \
  -d www.seudominio.com \
  --email seu@email.com \
  --agree-tos \
  --non-interactive
```

Os certificados ficam em `/etc/letsencrypt/live/seudominio.com/`.

Copie para a pasta esperada pelo Nginx do projeto:

```bash
mkdir -p nginx/ssl
sudo cp /etc/letsencrypt/live/seudominio.com/fullchain.pem nginx/ssl/
sudo cp /etc/letsencrypt/live/seudominio.com/privkey.pem nginx/ssl/
sudo chown $USER:$USER nginx/ssl/*.pem
```

Atualize `nginx/nginx.conf` com o `server_name` correto:

```nginx
server_name seudominio.com www.seudominio.com;
```

---

## 8. Subir a aplicação em produção

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

Isso vai:
1. Construir a imagem da aplicação
2. Subir o banco PostgreSQL
3. Rodar `migrate` e `collectstatic` automaticamente
4. Iniciar o Gunicorn
5. Iniciar o Nginx na frente

Verifique os logs:

```bash
docker compose -f docker-compose.prod.yml logs -f
```

---

## 9. Criar superusuário para o admin

```bash
docker compose -f docker-compose.prod.yml exec web python manage.py createsuperuser
```

Acesse o painel em `https://seudominio.com/admin`.

---

## 10. Renovação automática do certificado SSL

O certificado Let's Encrypt expira em 90 dias. Configure a renovação automática:

```bash
# Adiciona cron para renovar todo dia às 3h
(crontab -l 2>/dev/null; echo "0 3 * * * certbot renew --quiet && cp /etc/letsencrypt/live/seudominio.com/fullchain.pem /home/ubuntu/my-finances/nginx/ssl/fullchain.pem && cp /etc/letsencrypt/live/seudominio.com/privkey.pem /home/ubuntu/my-finances/nginx/ssl/privkey.pem && docker compose -f /home/ubuntu/my-finances/docker-compose.prod.yml restart nginx") | crontab -
```

---

## Atualizar a aplicação (após mudanças no código)

```bash
cd my-finances

# Puxa as mudanças
git pull

# Reconstrói e reinicia
docker compose -f docker-compose.prod.yml up -d --build
```

---

## Comandos úteis

```bash
# Ver status dos containers
docker compose -f docker-compose.prod.yml ps

# Ver logs em tempo real
docker compose -f docker-compose.prod.yml logs -f web

# Parar tudo
docker compose -f docker-compose.prod.yml down

# Acessar o shell do Django
docker compose -f docker-compose.prod.yml exec web python manage.py shell

# Backup do banco de dados
docker compose -f docker-compose.prod.yml exec db \
  pg_dump -U postgres_prod myfinancesDB > backup_$(date +%Y%m%d).sql
```

---

## Custos estimados (AWS free tier)

| Recurso | Free tier | Após 12 meses |
|---------|-----------|----------------|
| EC2 t2.micro | 750h/mês grátis por 12 meses | ~$8/mês |
| EBS 20GB | 30GB grátis por 12 meses | ~$1.60/mês |
| Transferência | 15GB/mês grátis | Mínimo |
| **Total estimado** | **$0** | **~$10/mês** |

> Certificado SSL via Let's Encrypt é sempre gratuito.
> Domínio: ~R$ 40-80/ano dependendo do registrador e extensão (.com, .com.br, etc).
