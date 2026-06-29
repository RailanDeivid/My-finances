# Registro de Usuários — Opções de Implementação

Duas abordagens para permitir que novas pessoas criem conta no app.
Ambas usam `django-allauth` para registro e login com Google.

---

## Opção A — Whitelist (lista de emails permitidos)

### Como funciona
Você cadastra os emails autorizados no admin do Django.
A pessoa acessa o site, clica em "Criar conta" ou "Entrar com Google",
e o sistema verifica se o email dela está na lista antes de permitir o registro.

### Fluxo do usuário
1. Você adiciona o email da pessoa no admin (`/painel-interno/`)
2. A pessoa acessa o site e escolhe como quer entrar (email+senha ou Google)
3. Sistema verifica o email → autorizado: cria a conta / bloqueado: mensagem de erro
4. Primeiro acesso feito — ela usa o app normalmente

### O que precisa ser feito
- Modelo `EmailPermitido` com campo `email` e `ativo`
- Sinal `pre_social_login` e `user_signed_up` do allauth para interceptar o registro
- Validação do email contra a tabela antes de criar a conta
- Mensagem de erro clara para emails não autorizados
- Registro no admin para você gerenciar a lista

### Vantagens
- Simples de manter
- Sem configuração de SMTP
- Você controla tudo pelo admin
- Menos código, menos pontos de falha

### Desvantagens
- Você precisa saber o email da pessoa com antecedência
- A pessoa precisa acessar o site por conta própria

### Pacotes necessários
```
django-allauth[socialaccount]
```

### Credenciais necessárias (Google Cloud Console)
```
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
```

---

## Opção B — Convite por token

### Como funciona
Você gera um link único com prazo de validade e envia para a pessoa
(por WhatsApp, email, etc.). Só quem tem o link consegue se registrar.

### Fluxo do usuário
1. Você clica em "Gerar convite" no admin, informa o email e o prazo
2. Sistema gera um link: `https://seuapp.com/registro/?token=abc123xyz`
3. Você envia o link para a pessoa (WhatsApp, email manual, etc.)
4. A pessoa clica, cai na tela de registro com email pré-preenchido
5. Ela define a senha (ou entra com Google) — conta criada
6. O link expira após o uso ou após o prazo definido

### O que precisa ser feito
- Modelo `Convite` com campos: `email`, `token` (UUID), `criado_em`, `expira_em`, `usado`
- View pública `/registro/?token=...` que valida o token antes de mostrar o formulário
- Geração do token no admin com prazo configurável
- Invalidação do token após uso
- Tratamento de token expirado ou já usado

### Vantagens
- A pessoa não precisa saber o endereço do site
- Link já vem com email pré-preenchido
- Controle de prazo de validade
- Histórico de quem foi convidado e quando

### Desvantagens
- Mais código para implementar
- Requer que você envie o link manualmente (WhatsApp, etc.)
- Mais partes que podem falhar (token expirado, link perdido)

### Pacotes necessários
```
django-allauth[socialaccount]
```

### Credenciais necessárias (Google Cloud Console)
```
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
```

---

## Comparativo

| Critério               | Whitelist (A)         | Convite por token (B)    |
|------------------------|-----------------------|--------------------------|
| Complexidade           | Baixa                 | Média                    |
| Configuração extra     | Nenhuma               | Nenhuma                  |
| A pessoa acha o site   | Por conta própria     | Pelo link enviado        |
| Controle de prazo      | Não                   | Sim                      |
| Histórico de convites  | Não                   | Sim                      |
| Tempo de implementação | ~2h                   | ~4h                      |
| Recomendado para       | Uso pessoal/familiar  | Grupos maiores ou SaaS   |

---

## Comum às duas opções

Independente da opção escolhida, a implementação inclui:

- `django-allauth` configurado com registro por email+senha e Google OAuth
- Tela de login atualizada com botão "Entrar com Google"
- Tela de registro com validação da opção escolhida (whitelist ou token)
- Após registro, usuário redirecionado para `/dashboard/`
- Dados do novo usuário isolados dos demais (`user=request.user` já garante isso)
- Credenciais do Google configuradas via `.env`

---

*Arquivo criado em 2026-06-29. Decidir entre Opção A e Opção B antes de implementar.*
