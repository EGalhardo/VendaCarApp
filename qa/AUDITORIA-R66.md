# Auditoria R66 — Performance e sincronização (VendaCar)

Corrida em browser real (Chromium via Playwright) contra `index.html`, com os dados de demonstração
e depois com carga artificial. Data: 2026-11-05. Scripts: `qa/auditoria_r66.py` (31 verificações)
e `qa/auditoria_r66_stress.py` (15 sondagens). Resultados em `qa/auditoria-r66*.json`.

## Veredicto

| Área | Estado |
|---|---|
| Funcionalidade (fluxo completo de venda) | ✅ 31/31 |
| Sincronização entre ecrãs e persistência | ✅ |
| Rendimento em carga (300 carros / 500 orçamentos) | ✅ |
| Offline (ficheiro local, sem servidor) | ✅ |
| Erros de JavaScript | ✅ 0 em toda a sessão |
| Dois separadores abertos ao mesmo tempo | ⚠️ precisa de recarregar |

## Performance

| Medida | Resultado |
|---|---|
| Carga inicial até ao ecrã "Automóvel" | **88 ms** (alvo < 1500) |
| First Contentful Paint | **76 ms** |
| DOMContentLoaded | **49 ms** |
| Pedidos de rede | **1** (o próprio ficheiro) — 0 CDNs, 0 fontes externas |
| Tamanho | 404 KB (HTML + CSS + JS + fotos embutidas em base64) |
| Navegação entre as 5 secções | 20–32 ms |
| Recálculo por tecla no desconto | mediana **3 ms**, pior **6 ms** |
| Memória após 1000 mudanças de ecrã | 9,5 MB → 9,5 MB (**+0 MB**, sem fugas) |

Com carga artificial:

| Ecrã | Tempo de render |
|---|---|
| Orçamentos com 506 linhas | 184 ms |
| Vendas com 506 negócios | 196 ms |
| Automóveis com 304 carros | 90 ms |
| Clientes com 500+ registos | 59 ms |
| Pesquisa de clientes | 46 ms |
| Dados no dispositivo (localStorage) | 93 KB |

## Sincronização (o que foi confirmado com números)

- **Orçamento**: com preço 9.750.000 Kz e desconto 500.000 Kz, os cinco números do ecrã batem
  certo: cartão 9.250.000 · painel direito 9.250.000 · resumo "À Vista por" 9.250.000 ·
  "Desconto aplicado" 500.000 · linha "Desconto à vista" 500.000.
- **WhatsApp**: o texto gerado leva exatamente esse valor à vista (`… valor de 9,250,000 Kz`),
  com +244 e o nome do cliente.
- **Enviar → guardar**: o orçamento aparece logo em Orçamentos, em Vendas (negócios em curso)
  e em Clientes, com o desconto gravado.
- **Editar no detalhe**: mudar o desconto recalcula o "À vista por" e **grava sozinho**;
  depois de recarregar continua igual (sem duplicar registos).
- **Catálogo**: registar um automóvel novo (32.000.000 Kz, sem campo de desconto) cria orçamento
  com o valor certo; o catálogo continua com `desc: 0`.
- **Funil**: marcar um negócio como "Venda concluída" muda o contador de vendas e a lista de
  fechados no mesmo instante.
- **Eliminar**: apagar um orçamento remove-o da lista e não reaparece no recarregamento.
- **Tema**: a escolha claro/escuro persiste.
- **Matemática**: IVA 14% = 1.365.000 sobre 9.750.000 (à parte, somado no total com IVA);
  desconto maior que o preço dá 0 Kz (nunca negativo); entrada acima do preço dá saldo 0 Kz.

## Problemas encontrados

1. **Dois separadores (ou telemóvel + balcão) não se sincronizam sozinhos.** Cada separador
   guarda no `localStorage`, mas não escuta o evento `storage`; quem tem o app aberto noutro
   separador só vê as alterações depois de recarregar. Não há perda de dados — os dois escrevem
   no mesmo sítio e o último a gravar fica —, mas pode mostrar números desatualizados.
   → testado: 6 orçamentos no separador A, criado 1 no separador B, A continuou com 6 até recarregar.
2. **A contagem de 0 até ao valor demora 8 s** nos valores do Orçamento e do Funil (é a animação
   original do app). A resposta ao escrever é imediata, mas durante esses 8 s o número visível é
   um valor a meio do caminho — num balcão pode parecer "o app está lento". Já existe um modo
   rápido interno (`index.html#rapido` → valor final em ~300 ms), mas não está exposto na interface.
3. **CSV sem o desconto negociado** (corrigido nesta ronda): passou a ter as colunas
   "Desconto à vista" e "A vista".

## O que um vendedor nota, na prática

- Abrir o app e ter a lista de carros pronta em menos de 0,1 s, sem internet, é o cenário ideal
  para mostrar no balcão.
- Construir o orçamento com o cliente e mexer no desconto responde à letra (3 ms) —
  o preço a bold, o saldo a pagar, as prestações e a mensagem mudam juntos.
- O ponto mais frágil é o **envio**: depois de "Enviar por WhatsApp" o orçamento fica gravado,
  mas se o vendedor estiver a usar dois dispositivos (ou dois separadores) tem de recarregar
  para ver o que o colega criou.
