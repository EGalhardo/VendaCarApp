# Prompt · Animar os ícones do app com o modelo de animação dos packs Lottie

> Copia tudo o que está dentro do bloco seguinte e cola-o como instrução para um agente
> (Arena, Claude, GPT, etc.). Foi escrito para reproduzir exatamente o trabalho feito nas
> rondas R59–R63 do projeto VendaCar.

---

## PROMPT

```text
CONTEXTO
Tens acesso a um app real, num único ficheiro `index.html` (~410 KB, HTML+CSS+JS inline,
sem dependências externas, funciona 100% offline). É um gerador de orçamentos de automóveis
em pt-PT, com sidebar no desktop e navbar em baixo no telemóvel. A navegação tem 5 itens:
Automóvel, Orçamentos, Vendas, Clientes e Perfil, cada um com um ícone SVG inline (18 px na
sidebar, 21 px na navbar) desenhado em estilo *outline* (traço 1,8 px, `fill:none`,
`stroke:currentColor`, `stroke-linecap:round`).

TAREFA
Quero que os 5 ícones ganhem vida. Usa como REFERÊNCIA DE MOVIMENTO os packs de animação
Lottie da IconScout (por exemplo
https://iconscout.com/lottie-animation-pack/essential-vol8-animation-pack_259043 e a família
"Unicons — Animated Icons", https://iconscout.com/unicons/animated-icons). Estuda O QUE se
move e COMO se move nesses packs — não copies os ficheiros.

RESTRIÇÕES INEGOCIÁVEIS
1. NÃO uses Lottie, `lottie-web`, GIF, vídeo nem canvas. Nada de ficheiros externos nem
   pedidos de rede: o app tem de continuar a funcionar offline e dentro de um único HTML.
2. A animação é feita só com CSS `@keyframes` aplicados ao SVG que já existe
   (`transform`, `stroke-dasharray`/`stroke-dashoffset`, `opacity`, `fill`).
3. Não mudes o desenho dos ícones, nem a estrutura da sidebar/navbar, nem nada fora dos
   ícones. Não inventes funcionalidades.
4. Tudo tem de continuar legível a 18 px. Movimentos abaixo de ~1 px ou de ~3 % de escala
   NÃO se veem e não contam como feitos.
5. A cor herda sempre de `currentColor` (tema claro e escuro sem duplicar regras).
6. Respeita `prefers-reduced-motion: reduce` (animação desligada).
7. O ficheiro tem de ficar ASCII-puro (usa `&#243;` e `\u00F3` para acentos). Nada de
   caracteres acima de 0x7F.

MÉTODO (segue esta ordem)
A. LÊ o pack Lottie e anota, por ícone, o *verbo* do movimento — não os desenhos.
   Exemplos observados nos packs: um item que cai dentro do cesto; um "+" que pulsa ao
   acrescentar; uma folha onde as linhas se escrevem de cima para baixo; um conjunto que
   balança ao "acenar"; um anel que sai de um avatar como um sinal.
B. TRADUZ cada verbo para uma primitiva CSS, com esta tabela mental:
      cai / sobe / desliza        -> transform: translateY() com opacity
      entra em cena               -> transform: scale() 0.5 -> 1.2 com opacity 0 -> 1
      escreve-se / traço cresce   -> stroke-dasharray = comprimento do traço,
                                     animar stroke-dashoffset até 0
      pulsa / respira             -> transform: scale() entre 0.86 e 1.22
      acena / balança             -> transform: rotate() entre -4.5deg e +2.4deg
      emite sinal                 -> transform: scale() até ~1.9 + opacity a desvanecer
      anda (carro)                -> translate() curto + estrada tracejada a passar
                                     (stroke-dashoffset linear)
C. A amplitude é escolhida para 18 px, não para 300 px: rotação 4–6 graus, escala ±20 %,
   translate 1–3 px, opacidade 0 → 0.6/1. Nada de exageros que pareçam um menu a piscar.
D. Aplica as animações SÓ ao item ativo (classe `.on` no botão de navegação), exceto
   pequenos estados "sempre vivos" que já existam. As cadências devem ser coordenadas
   (2,1 s a 2,8 s, `ease-in-out`/`ease-out`, `infinite`), sem itens fora de tempo.
E. Se precisares de grupos novos no SVG (ex.: envolver cabeça+ombros num `<g class="todo">`),
   acrescenta-os com `class` curtas e nomeadas pelo papel, nunca por cor.

ESPECIFICAÇÃO A ENTREGAR (ponto de partida, ajusta se medires melhor)
1. Automóvel — corpo do carro `translate` ±0,7 px e estrada tracejada a passar
   (`stroke-dashoffset` -8, 0,9 s linear).
2. Orçamentos — as 3 linhas do documento escrevem-se em sequência (atrasos 0 / 0,28 / 0,56 s),
   com `stroke-dasharray` igual ao comprimento de cada linha.
3. Vendas — o "+" do carrinho pulsa (escala 0,86 → 1,18) e um pequeno item cai dentro do
   cesto, que afunda 0,6 px ao receber o peso.
4. Clientes — o par inclina -4,2 graus, a cabeça da frente encolhe para 92 % e a segunda
   cabeça ENTRA em cena (escala 0,5 → 1,2, opacidade 0 → 1 → 0). Ciclo 2,1 s.
5. Perfil — o conjunto inclina -5,5 graus e a cabeça cresce até 122 %; um anel
   (`<circle class="halo">`) sai da cabeça e expande até 1,9× com opacidade 0 → 0,85 → 0.
   Ciclo 2,3 s.

ARMADILHAS JÁ CONHECIDAS (não as repitas)
- Um `<svg width="18" height="18">` CORTA tudo o que cresce para fora. Se a animação sair da
  caixa (o anel do Perfil), põe `overflow:visible` nesse SVG — e confirma que os cliques na
  navegação continuam a acertar no botão.
- A 18 px, movimentos de 0,3–0,6 px são invisíveis. Mede a amplitude, não a "achas".
- Animações sobrepostas no mesmo elemento (uma no `<svg>`, outra num filho) podem não correr
  como esperas: separa em grupos (`<g class="par">`, `<g class="todo">`).
- Se uma animação é retirada ao mudar de página, o elemento pode ficar "a meio do ciclo" num
  frame: acrescenta uma regra `:not(.on)` que fixe o estado final (`animation:none!important`).
- `getComputedStyle().transform` devolve `none` quando não há transformação: usa
  `new DOMMatrix(t)` com fallback, senão apanhas `NaN`.

VERIFICAÇÃO OBRIGATÓRIA (com Playwright, a conduzir o browser a sério)
1. Abre o app, limpa `localStorage` e recarrega.
2. Para cada ícone: confirma `getComputedStyle(el).animationName` e `animationDuration`.
3. MEDE a amplitude real, amostrando 20–40 vezes: escala (`Math.hypot(m.a, m.b)`),
   rotação (`m.b`), `opacity` e `strokeDashoffset`. Um movimento só conta se a amplitude
   for visível (escala ≥ 0,15; rotação ≥ 0,06 rad; opacidade ≥ 0,5 no pico; dashoffset ≥ 3).
4. Repete em 3 tamanhos (18, 21 e aumentado) e nos dois temas (claro e escuro).
5. Fotogramas: tira 4–6 screenshots seguidos do mesmo ícone e monta uma tira lado a lado.
   Se o movimento não se ler na tira, não está bom.
6. Clica nos 5 itens de navegação, em ordem cruzada, 10 vezes em desktop e 10 em telemóvel:
   a página ativa tem de ser sempre a certa.
7. Confirma 0 erros de consola e 0 `pageerror`.
8. Corre a suite de testes do projeto; se alguma asserção antiga media o movimento pelo nome
   da animação ou por `translateY`, reescreve-a para medir matrizes/escala/opacidade — nunca
   a apagues.

CRITÉRIOS DE ACEITAÇÃO
- Os 5 ícones animam quando ativos, com movimento visível a 18 px.
- Zero dependências novas, zero pedidos de rede, ficheiro ASCII-puro, tudo offline.
- Tema claro e escuro corretos sem regras duplicadas.
- `prefers-reduced-motion` desliga tudo.
- Suite verde, navegação intacta, nenhuma alteração fora dos ícones.
- Commit no fim, com o resto do ficheiro a copiar para as versões nomeadas do projeto.
```

---

## Como este prompt se liga ao que foi feito

| Passo do prompt | Onde apareceu no projeto |
|---|---|
| A. Ler o pack e extrair o *verbo* | Verifiquei o pack Essential Vol.8 (44 animações) e as Unicons animadas; concluí que serviam de **referência de movimento**, não de código. |
| B. Traduzir para primitivas CSS | `stroke-dashoffset` para o documento a escrever-se; `scale` + `opacity` para a 2.ª cabeça de Clientes e para o anel do Perfil. |
| C. Amplitude desenhada para 18 px | A 1.ª versão (0,3 px / escala 1,04) não se via — foi medida, reprovada e refeita (R63). |
| D. Só no item ativo + cadências coordenadas | Tudo dependente de `.nav.on[data-go="…"]`, ciclos de 2,1–2,8 s. |
| E. Grupos nomeados | `<g class="par">` (Clientes) e `<g class="todo">` (Perfil). |
| Armadilhas | `overflow:visible` no SVG do Perfil, regra `:not(.on)` para o 2.º boneco, `DOMMatrix` com fallback no `none`. |
| Verificação | 445 asserções na suite, tiras de fotogramas, 20 cliques de navegação, 2 temas, ASCII-puro. |

## O que este prompt deliberadamente NÃO deixa fazer

- Descarregar os Lottie e embuti-los em base64 (o ficheiro passaria de ~410 KB para ~700 KB
  e o ícone deixaria de ser legível a 18 px).
- Redesenhar os ícones.
- Pôr animações a correr em todos os itens ao mesmo tempo (o menu ficaria ruidoso).
- Aceitar "parece que mexe" como prova — só conta o que se mede.
