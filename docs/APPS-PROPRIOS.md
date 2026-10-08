# Transformar um app do Verto em produto próprio

> Guia para decidir se um app do Verto pode virar um app próprio, vendido, e como fazer
> isso. É uma **generalização** do plano do Social Preview
> ([`SOCIAL-APP-NOVO.md`](SOCIAL-APP-NOVO.md)), que é o caso de referência: cada app é
> um caso, e cada resposta pode mudar o plano. Nada aqui foi implementado.

**Como usar:** para cada app candidato, passe pela triagem (seção 2). Se passar, copie a
ficha (seção 8) para `docs/apps-proprios/<app>.md` e responda às perguntas das seções
3 a 6. As regras da seção 5 já vêm preenchidas com o padrão decidido para o Social
Preview: mantenha, mude ou marque "não se aplica".

---

## 1. Princípios herdados do Social Preview
Valem por padrão para todo app que virar produto. Cada um vira uma pergunta "vale aqui?"
na ficha.

1. **O backend é o mesmo** para a versão do Verto e o app próprio; o que muda é o front.
   Uma correção vale para os dois.
2. **A versão do Verto continua**, sem login, sem cobrança, nos padrões do Verto
   (`docs/REDESIGN.md`). Os dois só viram sistemas separados quando o app próprio for
   criado.
3. **App próprio leve e focado:** leva do Verto só o que aquele app usa.
4. **Sem os nomes Verto e LocalTools** em nada que o cliente veja; nome provisório = o
   nome atual do app.
5. **Identidade visual criada na hora**, pensando na melhor experiência, sem reaproveitar
   o visual da LocalTools.
6. **Custo mínimo** em todas as escolhas (servidor, e-mail, serviços).
7. **Quase autônomo:** cobrança, bloqueio, desbloqueio, e-mails e limpeza de dados
   acontecem sozinhos; o administrador só cuida das exceções.
8. **A camada comercial é uma só para todos os apps.** Login, 2FA, administrador,
   assinatura, nota fiscal, e-mails, limites e ciclo de vida da conta são construídos
   uma vez (com o Social Preview, o primeiro) e reaproveitados por cada app novo. Cada
   app só pluga o próprio núcleo e o próprio front.

---

## 2. Triagem: o app pode virar produto?
Responda antes de qualquer outra coisa. Um "não" ou "não sei" nos itens eliminatórios
(⛔) para o processo até resolver.

| # | Pergunta | Por que importa |
|---|---|---|
| ⛔ 1 | **O app depende de usar um serviço de terceiros de um jeito que os termos de uso dele proíbem?** (baixar vídeo de plataforma, raspar perfil, protocolo não oficial) | vender isso expõe o negócio a bloqueio, processo e banimento das contas dos clientes |
| ⛔ 2 | **As licenças de todas as dependências permitem vender** como serviço fechado ou como programa? | AGPL, GPL, licenças de modelos de IA "comunitárias" ou "não comerciais" podem exigir abrir o código, comprar licença ou trocar a peça |
| ⛔ 3 | **Usa API ou chave "de teste"** que não pode ir para produção? | o app para de funcionar ou viola os termos no dia em que tiver clientes |
| ⛔ 4 | **O uso esperado é legal e não é majoritariamente abuso?** (esteganografia, anti-forense, encurtador, censura) | uso duplo traz risco de imagem e de responsabilidade; pede regras de uso e moderação |
| 5 | **Alguém pagaria por isso sozinho**, ou só faz sentido num pacote com outros apps? | ferramentas pequenas e gratuitas em todo lugar vendem melhor em combo ou como freemium |
| 6 | **Quanto custa processar** para um cliente por mês (CPU, GPU, disco, banda)? | define se dá para ser assinatura fixa ou se precisa ser por uso (créditos) |
| 7 | **Precisa do computador do cliente?** (arquivos locais, sessão de app, pastas, tela) | decide se é web, desktop, extensão ou só navegador (seção 3.1) |
| 8 | **Quem já vende algo parecido, e por quanto?** | posiciona o preço e mostra o que o app precisa ter de melhor |
| 9 | **O README e as fichas dizem a verdade sobre o código?** | as descrições podem estar desatualizadas: o código é a fonte (seção 4) |

---

## 3. Perguntas por área

### 3.1 Formato de entrega
- **Web multiusuário** (padrão do Social Preview): servidor próprio, login, assinatura.
  Bom quando o processamento é no servidor e o cliente não precisa de nada instalado.
- **Só no navegador** (a página faz tudo; o servidor só entrega arquivos e a conta):
  custo de processamento perto de zero. Serve para apps que já rodam no navegador
  (Image Studio, Capture & OCR, Censor, Dev/Data…).
- **Desktop** (instalador → app): quando precisa de pastas, sessões ou arquivos do
  computador do cliente. A cobrança vira chave de licença validada online.
- **Extensão de navegador:** quando o app age em páginas que o cliente visita.
- **Pergunta-chave:** o processamento pesado roda **no servidor** (você paga) ou **na
  máquina do cliente** (ele paga, mas precisa de máquina boa)?

### 3.2 Produto e público
- Quem é o cliente (pessoa, criador de conteúdo, empresa, estudante)?
- Qual a tarefa principal, em uma frase, e o que o app faz melhor que os concorrentes?
- O que entra na primeira versão e o que fica para depois?
- Vende sozinho, em combo (por exemplo: Image Studio + Transparência + Efeitos +
  Compressor como "estúdio de imagem") ou como freemium (grátis com limite, pago sem
  limite)?
- Nome provisório e o que pesquisar antes do nome final (marca registrada, domínio).

### 3.3 Dados e privacidade
- Que dados do cliente o app recebe (arquivos, textos, tokens, áudio, rosto)? Algum é
  sensível pela LGPD (biometria, saúde)?
- Os arquivos precisam ficar guardados ou podem ser apagados logo depois do processamento?
- O app precisa de tokens ou senhas de outros serviços do cliente? Eles ficam
  criptografados, isolados por usuário e nunca voltam ao front.
- O que fica depois que a conta é apagada (só o aviso mínimo e o que a lei fiscal exige)?

### 3.4 Custos e limites
- Quais provedores todos os clientes dividem (servidor, GPU, Gmail, emissor de nota,
  provedor de pagamento, APIs pagas)? Qual a cota de cada um?
- Qual o custo por uso (por minuto de áudio, por imagem, por página, por modelo 3D)?
- Os limites do plano saem dessas cotas, com teto diário por pessoa, para ninguém
  esgotar sozinho o que é de todos.
- Assinatura fixa cobre o custo mesmo do cliente que mais usa? Se não: limites mais
  baixos, plano maior ou créditos por uso.

### 3.5 Operação
- Onde hospedar (VPS, nuvem, GPU sob demanda) pelo menor custo que aguente o pico?
- O processamento pesado precisa de fila? Quanto tempo o cliente aceita esperar?
- O que precisa ser atualizado com frequência (modelos, bibliotecas que quebram, APIs
  que mudam)? Quem é avisado quando quebra?
- Backup, monitoramento e o que acontece se o servidor cair no meio de um trabalho.
- Suporte: por onde o cliente fala (e-mail, formulário) e quanto tempo de resposta?

### 3.6 Legal e fiscal
- Termos de uso e política de privacidade (com a linha do tempo da conta escrita claramente).
- Regras de uso aceitável para apps de uso duplo, e como agir em denúncia.
- Direito de arrependimento de 7 dias (CDC, art. 49) e reembolso.
- Nota fiscal automática: o serviço se enquadra em qual código de serviço? O emissor
  escolhido para o Social Preview atende este app também?
- Marcas de terceiros que aparecem no app (logos de redes, formatos) podem ser usadas assim?

---

## 4. Onde olhar no Verto (inventário de cada app)

### 4.1 Onde cada app mora
A tabela "Os 34 apps" em [`REDESIGN.md`](REDESIGN.md) diz a rota, a pasta ou o trecho
de `app.py`, o ícone e o modo visual de cada app. Comece por ela.

### 4.2 Pontos de acoplamento a procurar
| O quê | Onde | Como achar |
|---|---|---|
| Rotas do app | `app.py` | `grep -n '@app.route("/<rota>' app.py` e seguir até a função, a constante `*_HTML` ou o `*_templates.py` |
| HTML do app | pasta do app (`<App>/*.html`) ou `templates/` ou constante em `app.py` | coluna "Fonte" da tabela do REDESIGN |
| Design system | `static/localtools/` (`base.css`, `app.css`, `modos/<modo>.css`, `fonts/`, `apps/<id>.webp`, `traco/`, `icons.svg`) | links `/static/localtools/` no HTML; classes `lt-*`, `modo-*`, `tema-*` |
| Marca | `lt-brand`, `lt-back`, "LOCALTOOLS", "Verto" | `grep -rni "verto\|localtools" <pasta> templates/<arquivo>` (inclui User-Agent e mensagens de erro) |
| Bibliotecas Python | imports da pasta do app e do trecho de `app.py` | `grep -rhoE "^\s*(import\|from) \w+" <pasta>`; comparar com `requirements.txt` |
| Bibliotecas JS e CDN | `<script src>` no HTML; `static/localtools/vendor/` | `grep -o 'src="[^"]*"' <html>`; tudo de CDN deve virar arquivo local no app próprio |
| Modelos de IA | `Efeitos/modelos/`, cache do Hugging Face, `Vetor3D/` | `grep -rn "onnx\|from_pretrained\|huggingface" <pasta>` e a licença de cada modelo |
| Binários externos | ffmpeg, LibreOffice, Node, cloudflared, Tesseract | `grep -rn "subprocess\|shutil.which" <pasta>` |
| Dados locais | `<App>/dados/` (gitignored) | `.gitignore` e `DADOS_DIR` no código |
| Instalação | `executaveis/INSTALAR.py`, `requirements.txt` | o que o instalador faz só por causa deste app |
| Dependência de outro app | imports entre pastas (por exemplo, Vetor3D usa o Conversor; Automações usa o modelo do Efeitos) | `grep -rn "from <OutroApp>\|<OutroApp>/" <pasta>` |

### 4.3 Confira o código, não a descrição
O README e as fichas às vezes descrevem uma versão antiga. Encontrados ao escrever este guia:
- **Censor:** o README fala em YOLOv8; o código usa TensorFlow.js (BlazeFace) e
  Tesseract.js no navegador (`templates/censor.html`).
- **Transcrever:** o README fala em Whisper; a rota `/transcribe` usa
  `speech_recognition` com `recognize_google`, o reconhecimento do Google pela chave
  embutida na biblioteca, que não serve para produto (triagem, item 3). O Subtitle
  Lab também importa `speech_recognition`.

---

## 5. Regras de negócio padrão
Preenchidas com o que foi decidido para o Social Preview. Na ficha de cada app, marque
**mantém**, **muda para…** ou **não se aplica**.

### 5.1 Contas e segurança
- Login por e-mail e senha (hash forte), limite de tentativas, sessão segura e CSRF.
- **2FA obrigatório para todos**, gratuito: app autenticador (TOTP) + 10 códigos de
  recuperação; sem SMS.
- Dois papéis: assinante e administrador; o primeiro administrador é criado por
  comando na instalação.
- Dados e segredos isolados por usuário; tokens de terceiros criptografados e nunca
  devolvidos ao front.

### 5.2 Administrador
- Vê as contas (situação, plano, uso, próxima cobrança, data prevista de exclusão).
- Cria contas por convite, bloqueia e desbloqueia com motivo, remove contas.
- Menus de preços e de limites, cobranças, fila de e-mails, painel do negócio e
  auditoria de tudo o que ele faz.
- Nunca vê senhas nem tokens, e não entra como o usuário.

### 5.3 Preço
- **Mensal e anual.** O administrador informa o valor base B; anual = **13 × B**;
  mensal = **anual ÷ 12 ÷ 0,9**, arredondado para cima → "você economiza 10% no plano
  anual" exato.
- Para o cliente aparece só "1 ano"; "13" e "13º" nunca aparecem.
- B, o multiplicador (13) e a economia (10%) são editáveis no menu do administrador.
- **Pergunta por app:** assinatura fixa cobre o custo? Se o custo varia muito por
  cliente (vídeo, IA, 3D), considerar créditos por uso, com o mesmo menu de preços.

### 5.4 Teste e ciclo de vida da conta
- **Teste grátis de 1 semana, só por convite** do administrador; cadastro pelo site paga
  na hora.
- **Não pagou:** 3 dias de carência → bloqueio → dados apagados 1 mês depois.
- **Cancelou:** usa até o fim do período pago → 1 mês para renovar, com e-mail no
  primeiro dia, no primeiro dia da última semana e no último dia → dados apagados.
- **Depois da exclusão:** aviso curto com o motivo por 6 meses (e-mail cifrado, datas e
  código do motivo), sem nenhum outro dado.
- Pagou dentro do prazo: volta na hora, com os dados.
- Bloqueado: entra, vê o histórico, baixa os próprios dados e paga; não processa nada.
- **Pergunta por app:** o que é "os dados" aqui (arquivos, projetos, links, tokens)? Há
  algo que o cliente perderia e não poderia baixar antes?

### 5.5 Cobrança, nota e e-mail
- Provedor de pagamento com recorrência, webhooks e Pix + cartão (escolher uma vez, para
  todos os apps).
- Nota fiscal automática a cada pagamento, cancelada no reembolso.
- E-mails por código próprio, pelo Gmail pessoal, com fila por prioridade (segurança >
  cobrança > avisos) dentro do limite diário.
- **Pergunta por app:** um Gmail para todos os apps ou um por app? O limite diário é
  da conta, então vários apps na mesma conta dividem o limite.

### 5.6 Limites
- Tirados das cotas dos provedores que todos dividem, com teto diário e mensal por pessoa.
- Painel de consumo para o administrador; mensagem clara quando o cliente chega no teto.
- **Pergunta por app:** qual é a unidade de uso (minutos, imagens, páginas, links,
  modelos) e quanto cada uma custa?

---

## 6. Mapa inicial dos apps do Verto
**Primeira leitura, para orientar a triagem; não substitui a ficha.** Licenças e termos
de uso precisam ser conferidos na hora (podem mudar). Legenda: 🟢 sem barreira
aparente · 🟡 resolver antes · 🔴 barreira séria.

| App | Entrega provável | O que pesa | Leitura |
|---|---|---|---|
| Social Preview | web multiusuário | caso de referência ([plano](SOCIAL-APP-NOVO.md)) | 🟢 |
| Verto (YouTube) | — | baixar vídeo do YouTube vai contra os termos dele; yt-dlp quebra com frequência | 🔴 |
| InstaSaver / VscoSaver | — | baixar e raspar Instagram/VSCO vai contra os termos das plataformas | 🔴 |
| WhatsSaver | — | protocolo não oficial do WhatsApp (ponte Node): risco de banir a conta do cliente e de violar os termos | 🔴 |
| Automações (Organizador) | desktop | mexe em pastas do computador; o valor depende do InstaSaver | 🟡 |
| Editor de Vídeo | web ou desktop | faster-whisper + ffmpeg + YuNet: custo alto de CPU por minuto; pede créditos por uso | 🟡 |
| PurpleFlix | a avaliar | depende de onde vem o conteúdo (direitos autorais) | 🟡 |
| Efeitos | web | rembg, OpenCV, YuNet: custo médio por foto/vídeo | 🟢 |
| Image Studio | só navegador | roda tudo na página: custo de servidor perto de zero | 🟢 |
| Transparência | web | rembg (remoção de fundo): mercado concorrido; conferir a licença do modelo | 🟢 |
| Matcha Effect | web com GPU | diffusers/torch (GPU cara); conferir a licença de cada modelo | 🟡 |
| Capture & OCR | só navegador ou extensão | Tesseract.js e gravação de tela no navegador | 🟢 |
| Transcrever / Subtitle Lab | web | hoje usam o reconhecimento do Google pela chave da biblioteca, que não serve para produto: trocar por Whisper (já usado no Editor de Vídeo) | 🟡 |
| Isolador de Voz | web com fila | Demucs, pesado em CPU/GPU: créditos por uso | 🟡 |
| Smart Studio | a avaliar | conferir dependências na pasta | 🟡 |
| PDFs / Office | web | PyMuPDF (`fitz`) é AGPL: serviço fechado precisa de licença comercial ou trocar a biblioteca; Office usa LibreOffice no servidor | 🟡 |
| Arquivos / Conversor | web | ffmpeg, PyMuPDF (AGPL), potrace (conferir licença), muitas rotas; mercado tipo Convertio | 🟡 |
| Compressor | web ou só navegador | ffmpeg/Pillow; ferramenta comum, melhor em combo | 🟢 |
| Ghost Tool | só navegador (melhor para privacidade) | remoção de metadados; vender como privacidade | 🟢 |
| Stealth | a avaliar | esteganografia/anti-forense: uso duplo, precisa de regras de uso | 🟡 |
| Censor | só navegador | TensorFlow.js + Tesseract.js na página | 🟢 |
| AI Guard & Diff | só navegador | detector heurístico: não pode prometer prova, só estimativa | 🟡 |
| Text Clean & Diff, Dev/Data, Clean Reader, QR Code, Tempo | só navegador | leves e com muitas versões gratuitas: melhor em combo ou freemium | 🟢 |
| Encurtador | web multiusuário | hoje usa a Cloudflare da conta do usuário; como serviço público, encurtador atrai phishing: precisa de denúncia, bloqueio de links e moderação | 🟡 |
| Vetor3D | web com GPU ou desktop | modelos 3D pesados (este PC trava com 7 GB); Hunyuan3D tem licença própria com restrições: conferir; TripoSR é a opção leve | 🟡 |
| Instruções | — | documentação do Verto, não é produto | — |

---

## 7. Ordem de trabalho
1. **Triagem** (seção 2). Algum ⛔ sem solução → o app fica só no Verto.
2. **Ficha** (seção 8) com o inventário da seção 4 feito no código.
3. **Decisões em aberto** no topo da ficha, como no Social Preview.
4. **Núcleo compartilhado:** separar o backend do app do resto do `app.py`, sem mudar
   o comportamento no Verto (a versão Verto testada antes e depois).
5. **Camada comercial comum** (seção 1, item 8): pluga login, 2FA, admin, assinatura,
   nota, e-mails, limites e ciclo de vida, sem reescrever nada.
6. **Front novo** com a identidade criada para o app.
7. **Instalação do servidor** (ou do instalador, se for desktop).
8. **Testes:** os critérios de pronto do Social Preview (isolamento entre usuários,
   ciclo da assinatura com relógio simulado, bloqueio aplicado no servidor, preço, sem
   "Verto"/"LocalTools"/"13º" para o cliente) + os específicos do app.
9. **Lançamento** e monitoramento do custo real, para ajustar B e os limites.

---

## 8. Ficha do app (copiar para `docs/apps-proprios/<app>.md`)

```markdown
# <App>: app próprio

## Decisões em aberto
| # | Decisão | O que já se sabe | Onde |
|---|---|---|---|
| 1 | Nome final | provisório: <nome atual> | — |
| 2 | Valor base B | depende do custo por uso | Preço |
| … | | | |

## Decisões já tomadas
1. …

## Triagem
| # | Pergunta | Resposta | Evidência (arquivo, licença, termo de uso) |
|---|---|---|---|
| ⛔1 | Termos de uso de terceiros | | |
| ⛔2 | Licenças das dependências | | |
| ⛔3 | API ou chave de teste | | |
| ⛔4 | Uso legal / abuso | | |
| 5 | Vende sozinho ou em combo | | |
| 6 | Custo por cliente por mês | | |
| 7 | Precisa do computador do cliente | | |
| 8 | Concorrentes e preços | | |
| 9 | Descrição bate com o código | | |

## O que o app faz hoje
(lista conferida no código, como a seção 1 do plano do Social Preview)

## Inventário
- Rotas: …
- HTML/JS/CSS: …
- Bibliotecas Python e JS (com licença): …
- Modelos de IA (com licença): …
- Binários externos: …
- Dados locais: …
- Dependência de outros apps: …
- Onde aparece "Verto"/"LocalTools": …

## Formato de entrega e arquitetura
(web multiusuário / só navegador / desktop / extensão, e por quê)

## Regras de negócio
| Regra padrão (seção 5) | Mantém / muda / não se aplica |
|---|---|
| 2FA obrigatório por TOTP | |
| Preço 13 × B, mensal ÷ 0,9 | |
| Teste de 1 semana por convite | |
| Carência 3 dias → bloqueio → apaga em 1 mês | |
| Cancelou: 1 mês para renovar, 3 e-mails | |
| Aviso com motivo por 6 meses | |
| Nota fiscal automática | |
| E-mail pelo Gmail pessoal | |
| Limites pelas cotas dos provedores | |

## Unidade de uso e limites
(unidade, custo por unidade, cotas dos provedores, teto diário e mensal)

## Front novo
(telas além das do app: as públicas, as do assinante e as do administrador)

## Critérios de pronto
- [ ] Critérios comuns (seção 7, passo 8)
- [ ] …
```
