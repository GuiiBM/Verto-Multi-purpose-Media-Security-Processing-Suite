# Social Preview: versão web por assinatura (planejada)

> Plano, não implementação. Nada aqui foi feito ainda: este documento registra o que o
> usuário decidiu (2026-10-08) para quando o app novo for criado.

## Decisões em aberto

Resumo para bater o olho; os detalhes estão nas seções indicadas.

| # | Decisão | O que já se sabe | Onde |
|---|---|---|---|
| 1 | **Nome final** | provisório: Social Preview | — |
| 2 | **Valor base B** | o usuário vai informar depois de calcular o custo da operação; a fórmula já está decidida (anual = 13 × B; mensal = anual ÷ 12 ÷ 0,9, para a economia ser 10% exata) e B, o 13 e os 10% são editáveis no menu do administrador | 3.4 |
| 3 | **Provedor de pagamento** | precisa ter cobrança recorrente, webhooks, ambiente de testes e aceitar Pix e cartão (boleto talvez); candidatos: Stripe, Mercado Pago, Asaas, Pagar.me, Efí; comparar taxas e Pix recorrente | 3.4 |
| 4 | **Como a nota fiscal é emitida** | tem que ser automática a cada pagamento; pelo próprio provedor de pagamento ou por um emissor de NFS-e com API; depende de como o negócio for registrado | 3.4 |
| 5 | **Números dos limites** | a regra está decidida (limites tirados das cotas dos provedores, com teto diário por pessoa); os números saem depois de escolher servidor, provedor de pagamento e emissor | 3.4 |
| 6 | **Hospedagem do servidor** e domínio | VPS ou nuvem, pelo menor custo que aguente o ffmpeg | 3.7 |
| 7 | **Como o backend é compartilhado** | pacote comum instalado nos dois, ou repositório comum com o Verto importando de lá | 3.1 |
| 8 | **Apps de desenvolvedor das redes** | hoje cada pessoa usa o próprio app e cola os próprios tokens; login de um clique para o público exigiria App Review da Meta, auditoria do TikTok, verificação do Google, acesso padrão do Pinterest e créditos da API da X | — |

## Decisões já tomadas

1. **Duas versões, o mesmo backend.** O pacote `SocialPreview/` continua sendo o
   backend das duas: uma correção numa regra de API vale para o Verto e para o app novo.
   O que muda de verdade é o **front**.
2. **A versão do Verto fica.** O Social Preview atual, em `/social`, continua no Verto,
   em uso e evoluindo, porque é extremamente útil. Os dois só passam a ser sistemas
   separados **no dia em que o app novo for criado**. Até lá, existe só a versão do
   Verto. Quando for mexer nela, seguir os padrões do Verto (`docs/REDESIGN.md`).
3. **O app novo é uma aplicação web multiusuário, vendida por assinatura.** Tem login
   simples e toda a parte de segurança. Várias pessoas usam o mesmo backend e **cada uma conecta as próprias
   contas com os próprios tokens**.
4. **Leve e focado.** O app novo importa do Verto **só o que o Social Preview usa**
   (seção 3.5), sem as dependências da suíte (yt-dlp, LibreOffice, Demucs, Whisper,
   modelos 3D, WhatsSaver…).
5. **Sem Verto nem LocalTools.** Nenhuma ocorrência desses nomes no app novo.
6. **Nome provisório:** "Social Preview". O nome final está em aberto.
7. **Identidade visual definida na hora da criação**, pensada para dar a melhor
   experiência possível. Não reaproveitar o visual da LocalTools (grafite + "modo feed").
8. **Conta de administrador.** O administrador vê as contas criadas, adiciona,
   bloqueia e remove contas (seção 3.3).
9. **Website com assinatura, quase autônomo.** Cobrança recorrente, bloqueio de quem não
   paga e desbloqueio de quem regulariza acontecem sozinhos, sem o administrador fazer
   nada no dia a dia (seção 3.4).
10. **Administração e assinatura são só do app web.** A versão do Verto continua sem
    login, sem administrador e sem cobrança.
11. **Teste grátis só por convite do administrador, de 1 semana.** Quem se cadastra
    pelo site paga na hora; o teste existe apenas nas contas que o administrador convida.
12. **Mensal e anual, com economia de exatamente 10% no anual.** O usuário informa um
    valor base B.
    - **Anual = 13 × B** (os 12 meses + um "13º" que garante a margem).
    - **Mensal = anual ÷ 12 ÷ 0,9**, arredondado para cima nos centavos. Assim 12
      mensalidades custam 10% a mais que o anual, e a mensagem "você economiza 10% no
      plano anual" é verdadeira (o arredondamento para cima garante pelo menos 10%).
    - Exemplo: B = R$ 10,00 → anual R$ 130,00; mensal R$ 12,04 (12 × R$ 12,04 = R$ 144,48,
      economia de 10,02%).
    - **Para o cliente aparece só "1 ano"**: o "13" e o "13º" nunca aparecem em
      textos, páginas, faturas ou e-mails (13º é coisa de funcionário). Eles existem só
      na conta interna e no menu do administrador.
    - **B, o multiplicador (13) e a economia (10%) são editáveis no menu do
      administrador.** O valor de B fica em aberto.
13. **Carência de 3 dias e dados apagados 1 mês depois.** Linha do tempo na seção 3.4.
    O exemplo do usuário: pagou em 3/jan → assinatura até 3/fev → carência até 6/fev
    (aí bloqueia) → dados apagados em 6/mar → aviso curto no sistema até 6/set (6 meses
    depois da exclusão), dizendo o que aconteceu e por quê.
14. **Nota fiscal automática** a cada pagamento confirmado, sem ação manual (como emitir
    fica em aberto).
15. **E-mails por código próprio, pelo Gmail pessoal**, para gastar o mínimo. Nada de
    serviço pago de e-mail.
16. **Custo mínimo** é critério de todas as escolhas da plataforma (servidor, e-mail,
    serviços externos).
17. **Limites dos planos tirados das cotas dos provedores.** Os limites de cada assinante
    saem da capacidade dos serviços que todos dividem (servidor, Gmail, emissor de nota,
    provedor de pagamento), com teto diário, para que uma pessoa não esgote em um dia o
    limite do provedor que é de todos.
18. **Cancelamento: 1 mês para renovar.** Quando a assinatura cancelada deixa de valer, a
    pessoa tem 1 mês para renovar. Recebe e-mail no primeiro dia, no primeiro dia da
    última semana e no último dia, avisando que no fim do prazo os dados serão apagados.
    O motivo fica registrado no sistema (aviso curto, como no caso de falta de pagamento).
19. **2FA obrigatório também para o assinante**, por um meio gratuito: app autenticador
    (TOTP) com códigos de recuperação, implementado por código próprio, sem SMS.

---

## 1. O que o app faz hoje

Este é o comportamento que o front novo precisa oferecer. A versão de referência é a do
Verto: `templates/social.html` + `static/localtools/social/estudio.js` e `estudio.css`.

### Compor o post
- Fotos e vídeos por botão, arrastar e soltar ou colar (Ctrl+V), até 35 mídias.
  Miniaturas reordenáveis por arrasto ou setas, e remoção.
- Texto do post com contagem de caracteres e hashtags; link (entra no texto só onde é
  clicável); título (YouTube, Pinterest, prévia de link); texto alternativo para leitor
  de tela.
- Texto próprio por rede, com volta ao texto geral.
- Escolha das redes (14 destinos) com indicação de conta conectada, sem conta ou modo
  assistido.
- Rascunho (texto, link, título, alt, redes escolhidas, preferências da música)
  lembrado no navegador.

### Redes e formatos
Catálogo único em `SocialPreview/redes.py`, servido por `/social/catalogo`:

| Rede | Formatos | Proporções e tamanhos |
|---|---|---|
| Instagram | Feed (carrossel até 10), Story, Reels | 4:5 1080×1350, 1:1, 1.91:1 1080×566; 9:16 1080×1920 |
| Facebook | Feed, Story, Reels | 4:5, 1:1, 1.91:1 1200×630, 16:9; 9:16 |
| Threads | Post (carrossel até 20) | 4:5, 1:1, 3:4 1080×1440, 16:9 1440×810 |
| X | Post (4 fotos ou 1 vídeo) | 16:9 1600×900, 1:1, 4:5 |
| LinkedIn | Post (até 20 fotos ou 1 vídeo) | 1.91:1 1200×627, 1:1, 4:5, 16:9 |
| Bluesky | Post (até 4 fotos, ≤ 1 MB cada) | 4:5, 1:1, 16:9, 3:4 |
| Mastodon | Post | 16:9, 1:1, 4:5 |
| Telegram | Canal (álbum até 10) | 4:5, 1:1, 16:9 |
| Discord | Canal (webhook) | 16:9, 1:1, 4:5 |
| Pinterest | Pin | 2:3 1000×1500, 1:1, 9:16 |
| YouTube | Shorts, Vídeo | 9:16; 16:9 1920×1080 |
| TikTok | Vídeo, Fotos (assistido) | 9:16 |
| Status do WhatsApp | Status (assistido) | 9:16 |
| Prévia de link | Open Graph (assistido) | 1.91:1 1200×630 |

Limites de cada rede conferidos nas documentações oficiais: caracteres (inclusive o
"peso" da X, os grafemas do Bluesky e os emojis do Threads), hashtags, menções,
quantidade de mídias, mistura de foto e vídeo, duração e tamanho de vídeo, e tamanho de
arquivo.

### Configuração automática (na primeira foto)
- Liga todas as redes (a não ser que a pessoa já tenha escolhido as dela).
- Escolhe sozinho o formato de cada rede pela mídia (vídeo sozinho → Reels, Shorts,
  TikTok Vídeo) e a proporção mais próxima da foto.
- Analisa a foto (`/social/foco`): rostos com o YuNet; sem rosto, a região com mais
  detalhe e cor; e a cor média.
- Enquadramento automático **por rede**:
  - corta em volta do rosto ou do assunto quando a proporção deixa (rosto a 38% do topo
    nos verticais);
  - quando cortar perderia demais ou deixaria o assunto de fora, põe a foto inteira e
    preenche o resto, centrada na área livre da interface.
- Cada cartão mostra "automático" e o motivo da escolha.

### Edição individual (só aquela rede)
- Arrastar a mídia no cartão, roda do mouse para zoom ou tamanho, dois cliques para
  voltar ao automático.
- Editor ampliado com três modos:
  - **Cortar:** escolhe a parte que aparece e o zoom.
  - **Encaixar:** a foto inteira, centralizada.
  - **Preenchimento automático:** posição e tamanho livres; o resto é preenchido.
- O resto do quadro pode ser desfoque, cor da foto, espelho, bordas esticadas, preto,
  branco ou uma cor escolhida.
- Atalhos de posição (topo, centro, base, esquerda, direita), zonas da interface, grade
  dos terços e escolha da foto do carrossel.
- "Automático", "Usar nas outras fotos" (mesma rede) e "Copiar para as outras redes".
- O enquadramento fica guardado por mídia e por `rede:formato:proporção`.

### Prévia fiel de cada app
- Telas simuladas de cada rede: Feed do Instagram com carrossel e a **grade do perfil
  em 3:4**; Story e Status com barras; Reels, Shorts e TikTok com ações e legenda; grades
  de várias fotos do X e do Facebook; álbum do Telegram; pin do Pinterest; player do
  YouTube; card de link.
- Corte do texto como em cada app ("mais", "Ver mais", "…mais") e zonas cobertas pela
  interface (liga e desliga).
- Avisos por rede: limite estourado, mídia que fica de fora e por quê, vídeo cortado
  pelo limite de duração, link não clicável no Instagram, título faltando, conta não
  conectada.
- O que a prévia mostra é **exatamente** o arquivo que sai. A mesma conta de
  recorte/preenchimento existe no front e no backend; a imagem exportada bate com o
  recorte do servidor (diferença média < 1/255).

### Fotos com música
- Música por arquivo ou por arrastar, com forma de onda para escolher o trecho.
- Ajustes: tempo de cada foto, transição (esmaecer, dissolver, deslizar, zoom, corte
  seco), zoom lento, volume e entrada e saída suaves.
- Prévia tocando a música e passando as fotos nos cartões.
- Cada rede que aceita vídeo recebe um vídeo no próprio formato, com o enquadramento
  daquela rede. O tempo é encolhido para caber no limite do formato. As outras redes
  recebem as fotos (o Feed do Instagram também: lá o vídeo com música vai em Reels).

### Publicar
- Revisão por rede: direto (conta conectada), corrigir antes (erro) ou assistido.
- Publicação em paralelo, com progresso por rede e link do post no fim.
- Modo assistido: baixar o arquivo pronto, copiar o texto ou as meta tags e abrir o
  site da rede (TikTok, Status, prévia de link e redes sem conta).
- Exportar tudo em `.zip`, com as mídias de cada rede, `textos.txt` e as meta tags.
- Histórico das publicações (`historico.json`; ainda sem tela).

### Contas
- 11 redes por API oficial, cada uma com passo a passo, link do painel e campos.
  YouTube por OAuth (PKCE).
- "Salvar e testar" mostra o perfil real (nome, @, foto), que vira o perfil das prévias.
  Também há "Testar de novo" e "Desconectar".
- Segredos nunca voltam para a página (só "salvo: sim/não").
- Renovação automática de token (Instagram, Threads), troca por token sem validade
  (Facebook) e escolha de Página e de pasta (Facebook, Pinterest).

### Backend (já pronto, compartilhado)
- `redes.py`: catálogo.
- `publicador.py`: contas, conectores e jobs de publicação. Também traz a assinatura
  OAuth 1.0a da X (conferida com o vetor oficial), o fallback para IPv4 quando o IPv6
  não tem rota e as mensagens de erro legíveis de cada API.
- `midia.py`: recorte e preenchimento no ffmpeg, vídeo com música, foco automático e
  ajuste de JPEG ao limite de cada rede.
- `hospedagem.py`: endereço público temporário para Instagram e Threads (túnel da
  Cloudflare que expõe só os arquivos do post, com o Litterbox de reserva).

---

## 2. Contrato entre o front e o backend

O front novo conversa com o backend pelas mesmas rotas (hoje em `app.py`). As respostas
são JSON `{"success": true, …}` ou `{"success": false, "error": "…"}`.

| Rota | Para quê |
|---|---|
| `GET /social/catalogo` | redes, formatos, tamanhos, limites e passos de conexão |
| `GET /social/contas` | contas conectadas (perfil e quais campos estão salvos, sem segredos) e configuração |
| `POST /social/contas/<rede>` · `DELETE` | salvar e testar credenciais · desconectar |
| `POST /social/contas/<rede>/testar` | testar de novo (renova o token se precisar) |
| `POST /social/config` | método de hospedagem temporária |
| `GET /social/oauth/<rede>/iniciar` · `/retorno` | login OAuth (YouTube) |
| `POST /social/midia` | subir vídeo original (devolve id e duração) |
| `POST /social/audio` | subir música |
| `POST /social/foco` | analisar foto (rostos, foco, cor) |
| `POST /social/render-video` | vídeo enquadrado para baixar |
| `POST /social/render-slideshow` | vídeo com música para baixar |
| `POST /social/publicar` · `GET /social/publicar/<job>` | publicar (plano + imagens recortadas) · acompanhar |
| `GET /social/historico` | publicações feitas |

Só no app web (a versão do Verto não tem): rotas de autenticação (entrar, sair,
cadastro, senha, 2FA), da assinatura do próprio usuário (plano, checkout, faturas,
cancelar), da administração (`/admin/...`, só para administrador) e o endpoint dos
webhooks do provedor de pagamento. As rotas `/social/*` acima passam a exigir sessão
e a conferir se a conta está ativa antes de publicar, renderizar ou subir mídia.

---

## 3. O app novo: aplicação web multiusuário

### 3.1 O que muda no backend compartilhado (quando o app novo for criado)
O backend hoje é de **um usuário só**: `dados/contas.json`, `dados/midias/` e
`historico.json` são globais. Para servir várias pessoas sem quebrar o Verto:
- **Tudo passa a ter dono.** Contas, mídias, músicas, jobs, histórico e configuração
  ficam por usuário, e toda rota confere se o recurso é de quem pede.
- **No Verto, um "usuário local" único**, sem login, para o Verto continuar igual.
  Sugestão: o backend recebe de quem chama (Verto ou app web) qual é o usuário e onde
  ficam os dados dele.
- **Hospedagem temporária:** o servidor web já é público, então o Instagram e o Threads
  podem buscar a mídia **no próprio app**, por URL assinada e com validade curta. O
  túnel e o Litterbox continuam só para o Verto, que roda no computador.
- **OAuth do YouTube:** no web, o endereço de retorno é o domínio do app (cada usuário
  cadastra esse endereço no próprio projeto Google, ou o app usa um cliente próprio).
- **Fila de processamento** com limites por usuário (ffmpeg pesa): vídeos, músicas e
  renderizações em fila, com tamanho máximo de upload e de duração.

### 3.2 Login e segurança
- **Mini login:** e-mail e senha. Quem se cadastra pelo site paga na hora (seção 3.4);
  contas com teste grátis só nascem por convite do administrador (seção 3.3). Sair de
  todos os dispositivos, trocar senha e recuperar acesso por e-mail.
- **Senhas** com hash forte (Argon2id ou bcrypt), nunca em texto. Bloqueio progressivo e
  limite de tentativas no login.
- **2FA obrigatório para todos** (assinante e administrador), por um meio **gratuito**:
  - **app autenticador (TOTP)**, como Google Authenticator, Microsoft Authenticator,
    Aegis ou 2FAS, todos gratuitos. O site gera o segredo e o QR code com código próprio
    (biblioteca livre, por exemplo `pyotp`), sem serviço pago;
  - **10 códigos de recuperação** de uso único, mostrados uma vez na ativação, guardados
    só como hash e regeráveis;
  - ativação obrigatória no primeiro acesso, antes de conectar qualquer rede;
  - sem SMS (tem custo por mensagem e é o meio mais fraco); e-mail não serve como
    segundo fator, só para recuperar a conta;
  - perdeu o celular e os códigos: o administrador redefine o 2FA depois de confirmar a
    identidade, e a ação fica na auditoria;
  - opcional no futuro: chave de acesso (passkey/WebAuthn), também gratuita.
- **Sessão** em cookie `HttpOnly`, `Secure` e `SameSite=Lax/Strict`, com expiração e
  renovação. Proteção CSRF em todo POST/DELETE.
- **Tokens das redes criptografados em repouso** (chave do servidor fora do banco, por
  variável de ambiente ou arquivo protegido), nunca devolvidos ao front e nunca
  registrados em log.
- **Isolamento:** um usuário nunca vê nem usa contas, mídias, jobs ou histórico de
  outro. IDs aleatórios e checagem de dono em todas as rotas.
- **Uploads:** tipo e tamanho validados, nomes gerados pelo servidor, arquivos fora da
  pasta pública e limpeza automática dos temporários.
- **HTTPS obrigatório**, com cabeçalhos de segurança: HSTS, CSP sem scripts de
  terceiros (JSZip e fontes servidos pelo próprio app), `X-Frame-Options`/
  `frame-ancestors` e `Referrer-Policy`.
- **Limite de requisições** por usuário e por IP (login, publicar, renderizar).
- **Privacidade (LGPD):** apagar a conta remove tokens, mídias e histórico; exportar os
  próprios dados; política de privacidade clara sobre o que fica no servidor.
- **Auditoria:** registro de login, conexão e desconexão de contas e publicações, sem
  segredos.
- **Backup** do banco (usuários e contas criptografadas) e plano de rotação da chave.
- **Dois papéis:** `usuário` (assinante) e `administrador`. O papel é conferido no
  servidor em toda rota de administração, nunca só escondendo botões no front.

### 3.3 Conta de administrador
O administrador cuida dos usuários do site; ele não publica pelos usuários.

**O que ele faz:**
- **Ver as contas criadas:** nome, e-mail, data de cadastro, último acesso, plano,
  situação da assinatura (teste por convite, ativa, em atraso, bloqueada, cancelada),
  mensal ou anual, próxima cobrança, data prevista de exclusão (se bloqueada), redes conectadas (só quais, nunca os tokens) e uso no período (posts,
  minutos de vídeo, espaço).
- **Buscar e filtrar** por situação, plano e data, e exportar a lista (CSV).
- **Adicionar conta (convite):** cria o usuário e manda o e-mail para ele definir a
  senha. É o **único caminho para o teste grátis**: o convite dá **1 semana de teste**
  (ou um plano de cortesia, sem cobrança, ou um desconto). Ao fim da semana, a pessoa
  assina ou a conta segue a linha do tempo da seção 3.4.
- **Bloquear e desbloquear à mão**, com motivo registrado. Serve para casos fora da
  cobrança: abuso, fraude ou pedido do próprio usuário.
- **Remover conta:** pede confirmação e cancela a assinatura no provedor de pagamento.
  Apaga os tokens, as mídias e o histórico (LGPD); o registro financeiro fica guardado
  pelo prazo legal.
- **Ver as cobranças** de cada usuário (pagas, pendentes, falhas, reembolsos) e
  reembolsar quando precisar.
- **Painel do negócio:** assinantes ativos, receita recorrente do mês, novos
  assinantes, cancelamentos, inadimplência e publicações por rede.
- **Menu de preços:** três campos editáveis, **valor base B**, **multiplicador do
  anual** (padrão 13) e **economia do anual** (padrão 10%). O menu mostra na hora a
  prévia do anual, do mensal, das 12 mensalidades e da economia real.
  Mudança de preço vale para as próximas cobranças, com aviso por e-mail aos assinantes
  antes de valer.
- **Menu de limites:** as cotas de cada provedor e o painel de consumo (seção 3.4,
  "Limites").

**Regras de segurança do administrador:**
- 2FA obrigatório (como todos), sessão mais curta e acesso só por HTTPS.
- Nunca vê os tokens das redes nem a senha de ninguém. Também não "entra como" o
  usuário: se precisar ajudar, vê os dados da conta e os erros de publicação.
- Toda ação dele (criar, bloquear, remover, reembolsar, mudar plano) fica na auditoria
  com quem, quando e o motivo.
- O primeiro administrador é criado na instalação do servidor, por comando no
  terminal, nunca por uma página aberta. Outros administradores só são criados por
  um administrador.

### 3.4 Assinatura, cobrança e bloqueio (o site quase autônomo)
O objetivo é que o site funcione e receba sozinho: a pessoa entra, assina, usa e paga.
Quem para de pagar é bloqueado e desbloqueado sem intervenção, e os dados de quem não
volta são apagados no prazo. Tudo com o menor custo possível.

#### Planos e preço
- **Mensal ou anual.** O usuário informa o valor base **B**, e o site calcula:

  | | Fórmula interna | Exemplo (B = R$ 10,00) |
  |---|---|---|
  | Anual | 13 × B, cobrado de uma vez | R$ 130,00 por ano |
  | Mensal | anual ÷ 12 ÷ (1 − 10%), arredondado **para cima** nos centavos | R$ 12,04 por mês |
  | 12 mensalidades | 12 × mensal | R$ 144,48 |
  | Economia do anual | 1 − anual ÷ (12 × mensal) | 10,02% (nunca menos de 10%) |

- **Por que dividir por 0,9 e não somar 10%:** a parcela do anual + 10% (R$ 11,92) daria
  economia de só 9,09%, porque os 10% seriam calculados sobre o anual e a economia é
  medida sobre o mensal. Dividindo por 0,9, 12 mensalidades × 0,9 = o anual, e os 10%
  são exatos. O arredondamento para cima nos centavos deixa a economia sempre ≥ 10% (com
  valores de B entre R$ 7,90 e R$ 49,90, ela fica entre 10,007% e 10,024%).
- **Texto para o cliente:** só "plano anual" ou "1 ano", "plano mensal" e **"você
  economiza 10% no plano anual"**. Os nomes "13 × B" e "13º" **nunca** aparecem para o
  cliente (página de preços, checkout, faturas, notas, e-mails); a página mostra só o
  preço por ano e, se quiser, o equivalente por mês (anual ÷ 12 = R$ 10,83/mês no
  exemplo).
- **Editável no menu do administrador:** o valor base B, o multiplicador do anual
  (padrão 13) e a economia do anual (padrão 10%). O menu mostra na hora a prévia do
  anual, do mensal, das 12 mensalidades e da economia real; nada fica fixo no código.
- **B fica em aberto** até calcular o custo da operação: servidor, processamento de vídeo
  (ffmpeg), armazenamento, banda, taxas do provedor de pagamento e emissão de nota.
- **Teste grátis de 1 semana, só por convite** do administrador (seção 3.3). O cadastro
  pelo site já vai direto para o pagamento.

#### Limites (tirados das cotas dos provedores)
Cada assinante usa os **próprios tokens** nas redes sociais, então as cotas das APIs das
redes (por exemplo, 100 posts por dia no Instagram) são dele e o app só respeita e mostra.
Os limites do plano protegem o que **todos dividem**, para que uma pessoa não esgote num
dia a cota que é de todos:

| Provedor compartilhado | Cota que importa | O que vira limite por assinante |
|---|---|---|
| Servidor (hospedagem) | CPU para o ffmpeg, disco, banda | minutos de vídeo gerado por dia e por mês, tamanho de upload, espaço guardado |
| Gmail pessoal | limite diário de envio da conta (conferir o valor atual) | e-mails por dia, com prioridade (segurança > cobrança > avisos) |
| Emissor de nota | cota e custo por nota | nota só em pagamento confirmado; nenhuma em teste nem em cortesia |
| Provedor de pagamento | limites de API e taxas | tentativas de checkout e troca de cartão por dia |

- **Teto diário e mensal por pessoa:** cada cota é dividida pelo número de assinantes
  ativos, com folga, e ninguém passa de uma fração fixa da cota diária, mesmo que sobre.
- O administrador informa no menu de limites a cota de cada provedor; o site calcula os
  tetos e mostra um painel de consumo (hoje, mês, quem está perto do teto).
- Chegou no teto: a ação é recusada com mensagem clara ("limite diário de vídeos
  atingido, volta amanhã às 00:00") e o que estiver na fila espera o dia seguinte.
- Os números ficam em aberto (item 6) até escolher servidor e provedores.

#### Fluxo do assinante
1. Página pública com o que o app faz, os planos e os preços.
2. Cadastro → escolha de mensal ou anual → pagamento no checkout do provedor. O site
   **não** guarda número de cartão; quem guarda é o provedor.
3. Pagamento confirmado (webhook) → conta "ativa" → **nota fiscal emitida
   automaticamente** e enviada por e-mail com o recibo.
4. Uso normal, dentro dos limites do plano.
5. Renovação automática no mesmo dia do mês (ou do ano) do primeiro pagamento.
6. Área "Minha assinatura": trocar entre mensal e anual, atualizar a forma de pagamento,
   ver faturas e notas, cancelar sozinho e **renovar** dentro do prazo de 1 mês depois
   do cancelamento.

#### Linha do tempo de quem não paga
Regra: **a assinatura vale até o mesmo dia do mês seguinte** (ou do ano seguinte, no
anual). Depois vêm **3 dias de carência**, o **bloqueio**, **1 mês** até apagar os
dados e **6 meses de aviso**.

Exemplo mensal (primeiro pagamento em 3 de janeiro, sem renovação):

| Data | O que acontece | Situação |
|---|---|---|
| 3/jan | pagamento confirmado, nota emitida | ativa |
| 31/jan | e-mail: a renovação é em 3/fev | ativa |
| 3/fev | fim do período pago; cobrança de renovação falha | em atraso (carência) |
| 3 a 6/fev | uso normal, com faixa de aviso no app e e-mails pedindo para regularizar | em atraso |
| 6/fev | fim da carência sem pagamento | **bloqueada** |
| 6/fev a 6/mar | entra, vê o histórico, baixa os próprios dados e pode pagar; não publica, não gera vídeo, não sobe mídia; e-mails avisando a data da exclusão no mesmo padrão do cancelamento (primeiro dia, primeiro dia da última semana e último dia) | bloqueada |
| 6/mar | **dados apagados**: tokens, mídias, histórico, perfil e acesso | apagada |
| 6/mar a 6/set | quem tentar entrar com aquele e-mail vê o aviso curto do que aconteceu | aviso |
| 6/set | o aviso é apagado também | — |

- No **anual** é igual, contando a partir da data anual: pagou em 3/jan/2027 → vale até
  3/jan/2028 → carência até 6/jan/2028 → apagado em 6/fev/2028 → aviso até 6/ago/2028.
- **Dia que não existe no mês:** vale o último dia do mês (pagou em 31/jan → vale até
  28/fev, ou 29 no ano bissexto). Os prazos seguintes contam a partir dessa data.
- **Pagou durante a carência ou o bloqueio:** volta a "ativa" na hora, com os dados
  intactos, e o novo período começa na data do pagamento.
- **Depois de apagada**, a pessoa pode criar uma conta nova e assinar de novo, mas os
  dados antigos não voltam.
- **Bloqueio manual** do administrador (abuso, fraude) não segue esse relógio: fica
  bloqueada até ele decidir.

#### Linha do tempo de quem cancela
Cancelar não apaga nada na hora. A pessoa usa até o fim do período já pago; aí começa o
**prazo de 1 mês para renovar**, sem carência (ela escolheu sair). Se o cancelamento vier
com reembolso (arrependimento de 7 dias), o prazo começa no dia do cancelamento.

Exemplo (primeiro pagamento em 3 de janeiro, cancelou em 20 de janeiro):

| Data | O que acontece | Situação |
|---|---|---|
| 20/jan | cancelou; e-mail confirmando e dizendo até quando usa e até quando pode renovar | ativa (cancelada) |
| 3/fev | fim do período pago; começa o prazo de 1 mês; **1º e-mail**: "seus dados serão apagados em 3/mar se não renovar" | cancelada (prazo para renovar) |
| 24/fev | primeiro dia da última semana; **2º e-mail** com o mesmo aviso | cancelada |
| 2/mar | último dia do prazo; **3º e-mail**: "amanhã os dados serão apagados" | cancelada |
| 3/mar | **dados apagados** | apagada |
| 3/mar a 3/set | quem tentar entrar com aquele e-mail vê o aviso curto, com o motivo `cancelada` | aviso |

- Durante o prazo, a conta fica como "bloqueada": entra, vê o histórico, baixa os
  próprios dados e **renova** com um clique. Renovou: volta a "ativa" com os dados
  intactos.
- O **motivo fica registrado** no aviso de 6 meses e na auditoria (sem dados pessoais
  além do e-mail cifrado).

#### O aviso que fica depois da exclusão
Um registro mínimo, de algumas dezenas de bytes por conta, guardado por 6 meses:
- **e-mail cifrado por HMAC** (com a chave do servidor), para reconhecer a pessoa no
  login sem guardar o e-mail em texto;
- datas do fim do período pago, do bloqueio e da exclusão;
- motivo em código curto (`sem_pagamento`, `cancelada`, `fim_do_teste`, `removida_admin`).

Mensagem mostrada no login, por exemplo: *"Esta conta foi bloqueada em 06/02 por falta de
pagamento e os dados foram apagados em 06/03, como avisado por e-mail. Você pode criar
uma conta nova."* Nada de mídias, tokens ou histórico. O registro financeiro e as notas
fiscais seguem guardados à parte, pelo prazo que a lei fiscal exige.

#### Nota fiscal automática
- Emitida sozinha a cada pagamento confirmado (webhook), com os dados que o assinante
  informou no cadastro (nome, CPF/CNPJ, e-mail) e enviada por e-mail.
- Reembolso → nota cancelada sozinha (quando o emissor permitir) e registrada na auditoria.
- Falha na emissão → nova tentativa automática e alerta para o administrador; o
  pagamento não é desfeito por isso.
- Como emitir (pelo próprio provedor de pagamento ou por um emissor com API) está nas
  decisões em aberto, item 4.

#### E-mails por código próprio (Gmail pessoal)
- Envio pelo próprio backend via SMTP de uma **conta Gmail pessoal** (`smtp.gmail.com`,
  porta 587 com STARTTLS), autenticada com **senha de app** (exige a verificação em duas
  etapas ligada na conta Google). A senha de app fica criptografada, junto das outras
  chaves do servidor. Custo zero.
- **Limite diário do Gmail pessoal:** conferir o valor atual na hora. Ele entra nos
  limites da plataforma (seção "Limites"). A fila de envio prioriza:
  1. segurança: recuperação de senha, convite, 2FA redefinido;
  2. cobrança: pagamento confirmado + nota, pagamento falhou, renovação chegando;
  3. avisos da linha do tempo: bloqueio, cancelamento, exclusão chegando.

  O que não couber no dia vai no dia seguinte, e o painel do administrador mostra
  quantos envios faltam.
- **Fila com novas tentativas** e registro do que foi mandado, sem conteúdo sensível.
- **Modelos de e-mail** simples (texto + HTML leve):
  - convite com 1 semana de teste, fim do teste chegando;
  - pagamento confirmado + nota, renovação chegando, pagamento falhou, conta em atraso;
  - conta bloqueada, cancelamento confirmado;
  - os três avisos de exclusão (primeiro dia, primeiro dia da última semana, último dia);
  - dados apagados, conta reativada ou renovada, mudança de preço, recuperação de senha.
- Links de senha e de convite com token de uso único e validade curta.
- O remetente é um endereço @gmail.com, que cai mais fácil em spam: textos curtos, sem
  muitos links, e o endereço de envio citado na página do site para o usuário adicionar
  aos contatos.

#### Regras que valem sempre
- **O bloqueio é aplicado no servidor**, em todas as rotas que publicam, renderizam ou
  sobem mídia, e nos jobs já agendados. Não depende do front.
- **Limites do plano** aplicados pelo backend: posts por mês, redes conectadas, minutos
  de vídeo com música, espaço e tamanho de upload.
- **Webhooks seguros:** confere a assinatura de cada aviso, ignora avisos repetidos
  (idempotência) e reconcilia uma vez por dia com o provedor, para o caso de algum aviso
  se perder.
- **Rotinas diárias automáticas:** fim de período, fim do teste de 1 semana, fim de
  carência, bloqueio, início e fim do prazo de quem cancelou, e-mails da linha do tempo,
  zerar os tetos diários de uso, exclusão de dados no prazo, expiração dos avisos de 6 meses,
  reconciliação com o provedor, reemissão de notas que falharam, limpeza de mídias
  temporárias e backup.
- **Consumidor e legal:** termos de uso e política de privacidade com essa linha do tempo
  escrita de forma clara, cancelamento simples e direito de arrependimento de 7 dias em
  compra online (Código de Defesa do Consumidor, art. 49), com reembolso pelo provedor.

### 3.5 O que importar do Verto (e o que deixar)
**Levar:**
- `SocialPreview/` inteiro: `redes.py`, `publicador.py`, `midia.py`, `hospedagem.py`.
- As rotas `/social/*` (hoje em `app.py`) e o auxiliar `_social`.
- `static/localtools/social/marcas.js` (marcas das redes: Simple Icons CC0 e Phosphor
  MIT, guardar as licenças).
- `Efeitos/modelos/face_detection_yunet_2023mar.onnx` + `LICENSE-yunet.txt` (foco
  automático).
- JSZip local (hoje vem do CDN).
- Os testes de ponta a ponta usados na validação: API falsa do Instagram que baixa a
  mídia pela internet, vetor oficial da assinatura da X e recorte da página comparado
  ao do servidor.

**Não levar:** tudo o que é da suíte (yt-dlp, LibreOffice, runtime JS do YouTube,
WhatsSaver, Demucs, Whisper, rembg, modelos do Vetor3D, Encurtador…), o design system
da LocalTools (`base.css`, `app.css`, `modos/feed.css`, ícones 3D, fonte Geist via
LocalTools, `lt-back`, marca LOCALTOOLS) e o instalador do Verto.

**Dependências do app novo:** Python, Flask (ou equivalente), requests, Pillow, numpy,
opencv-python-headless, ffmpeg/ffprobe e as bibliotecas de segurança (hash de senha,
criptografia, banco). Para as fotos com música e o recorte de vídeo, o servidor precisa
de ffmpeg.

**Trocar textos:** onde hoje está "o Verto…" (`redes.py`, `publicador.py`,
`hospedagem.py`, `estudio.js`) e o User-Agent `Verto-SocialPreview/1.0`. Com o
backend compartilhado, esses textos passam a usar o nome do app que estiver chamando.

### 3.6 Front novo
- Identidade visual criada na hora, com o objetivo da melhor experiência possível.
- Mesmas funções da seção 1, mais as telas que o web exige:
  - **públicas:** página inicial com planos e preços (mensal e anual), entrar, criar
    conta e pagar, aceitar convite, recuperar senha, termos e privacidade;
  - **do assinante:** ativação obrigatória do 2FA (QR code do app autenticador +
    códigos de recuperação), primeiro acesso guiado para conectar as contas, minha conta
    (senha, 2FA, sessões, apagar conta), minha assinatura (plano, pagamento, faturas,
    cancelar, renovar), uso do dia e do mês contra os tetos, aviso de conta em atraso ou bloqueada com a data da exclusão e o botão de
    pagar, uso do plano e histórico de publicações;
  - **no login:** o aviso curto para quem teve os dados apagados (seção 3.4);
  - **do administrador:** contas, detalhe da conta, convites (1 semana de teste),
    menu de preços (valor base B, multiplicador do anual e economia, com prévia), menu de limites
    (cotas dos provedores e consumo), cobranças, fila de e-mails, painel do negócio e
    auditoria.
- Funciona bem no celular (o usuário de redes sociais vive nele).

### 3.7 Do servidor ao app no ar
A "instalação" passa a ser a do servidor: um passo a passo único (script e/ou Docker)
que prepara Python, ffmpeg, banco, chave de criptografia, HTTPS (proxy reverso) e o
serviço que reinicia sozinho. Também é preciso um jeito de atualizar sem perder os dados.
A instalação também:
- cria o primeiro administrador (por comando);
- configura as chaves do provedor de pagamento e o endereço dos webhooks;
- configura o envio de e-mails (conta Gmail pessoal e senha de app);
- pede o valor base B, o multiplicador do anual (padrão 13), a economia do anual (padrão 10%) e as cotas dos provedores (dá para mudar depois no menu do administrador);
- configura a emissão automática de nota fiscal;
- agenda as rotinas automáticas (seção 3.4).

### 3.8 Critérios de pronto
- [ ] Nenhuma ocorrência de "Verto" ou "LocalTools" no app novo.
- [ ] Dois usuários de teste não conseguem ver nem usar nada um do outro (testar cada rota).
- [ ] Tokens criptografados no banco e ausentes de respostas e logs.
- [ ] Login com limite de tentativas, CSRF e cookies seguros conferidos.
- [ ] Publicação direta e assistida funcionando para um usuário real de ponta a ponta.
- [ ] Administrador: lista, cria, bloqueia, desbloqueia e remove contas; usuário comum recebe 403 em toda rota de administração.
- [ ] Ciclo da assinatura testado no ambiente de testes do provedor, sem ação manual: ativa → renovação falha → em atraso → bloqueada → paga → ativa; e convite com teste → fim do teste → assina.
- [ ] Linha do tempo conferida com relógio simulado: pagamento em 3/jan → em atraso 3/fev → bloqueada 6/fev → dados apagados 6/mar → aviso até 6/set; e os casos 31/jan e anual.
- [ ] Preço calculado certo: B = 10,00 → anual 130,00 e mensal 12,04 (economia 10,02%); com outros valores de B, a economia nunca fica abaixo de 10%; trocar B, o multiplicador ou a economia no menu do administrador muda tudo na hora.
- [ ] Nenhum texto voltado ao cliente (páginas, checkout, faturas, notas, e-mails) mostra "13" ou "13º": só "1 ano"/"anual" e "economize 10%".
- [ ] Cancelamento: prazo de 1 mês com os três e-mails (primeiro dia, primeiro dia da última semana, último dia), renovação dentro do prazo mantendo os dados, exclusão no fim e aviso com motivo `cancelada` por 6 meses.
- [ ] Convite com 1 semana de teste; no fim, assina ou segue a linha do tempo.
- [ ] 2FA obrigatório no primeiro acesso de qualquer conta, com app autenticador e códigos de recuperação; sem 2FA ativo, nada além da tela de ativação funciona.
- [ ] Tetos diários: um assinante sozinho não passa da sua fração das cotas (vídeo, e-mail, uploads), e o painel mostra o consumo.
- [ ] Nota fiscal emitida sozinha a cada pagamento no ambiente de testes do emissor, e cancelada no reembolso.
- [ ] E-mails da linha do tempo saindo pela conta Gmail pessoal, com fila, prioridade e novas tentativas dentro do limite diário.
- [ ] Depois da exclusão, o banco guarda só o aviso mínimo (sem e-mail em texto), e ele some após 6 meses.
- [ ] Conta bloqueada não publica nem renderiza, nem chamando a API direto.
- [ ] Webhook com assinatura inválida é recusado; o mesmo aviso repetido não cobra nem muda nada duas vezes.
- [ ] O Social Preview do Verto continua funcionando igual com o backend compartilhado, sem login nem cobrança.
