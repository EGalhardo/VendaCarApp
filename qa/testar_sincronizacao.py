# -*- coding: utf-8 -*-
"""R67 - teste real de dois separadores abertos ao mesmo tempo."""
import asyncio, sys
from playwright.async_api import async_playwright

BASE = 'http://localhost:8000/index.html'
res = []

def ok(nome, cond, extra=''):
    res.append((nome, cond, str(extra)[:100]))
    print(('OK   ' if cond else 'FALHA') + ' ' + nome + (' | ' + str(extra)[:100] if extra else ''))

async def main():
    async with async_playwright() as brw:
        b = await brw.chromium.launch()
        ctx = await b.new_context(viewport={'width': 1440, 'height': 900})
        A = await ctx.new_page(); B = await ctx.new_page()
        erros = []
        for pg in (A, B):
            pg.on('pageerror', lambda e: erros.append(str(e)))
        await A.goto(BASE); await A.wait_for_selector('#pg-modelos:not(.hidden)')
        await A.evaluate("localStorage.clear()"); await A.reload()
        await A.wait_for_selector('#pg-modelos:not(.hidden)'); await A.wait_for_timeout(400)

        # B abre depois (mesmo contexto = mesmo localStorage)
        await B.goto(BASE); await B.wait_for_selector('#pg-modelos:not(.hidden)'); await B.wait_for_timeout(400)
        nA = await A.evaluate("()=>ORCAMENTOS.length"); nB = await B.evaluate("()=>ORCAMENTOS.length")
        ok('Os dois separadores arrancam com os mesmos dados', nA == nB, f'{nA} / {nB}')

        # 1) B cria um orcamento -> A tem de o ver sozinho
        await B.evaluate("""()=>{ORCAMENTOS.unshift({id:'sep1', nome:'Cliente Separador B', tel:'923777888',
            carro:CARROS[0].id, preco:9000000, entrada:900000, desc:0, data:Date.now(),
            estado:'Pendente', enviado:false, reenvios:0}); guardarOrc();}""")
        await A.wait_for_timeout(900)
        vA = await A.evaluate("()=>ORCAMENTOS.some(o=>o.id==='sep1')")
        ok('Separador A ve o orcamento criado em B (sem recarregar)', vA, '')
        contador = await A.evaluate("()=>document.querySelector('[data-cnt=\"orcs\"]').textContent")
        ok('Etiqueta "Orçamentos" do menu atualiza em A', contador == str(nA + 1), contador)

        # 2) A esta na lista: as linhas tem de aparecer sem tocar em nada
        await A.evaluate("ir('listaorc')"); await A.wait_for_timeout(600)
        linhas = await A.evaluate("()=>document.getElementById('tblOrc').innerText")
        ok('Tabela de Orçamentos de A mostra o registo de B', 'Cliente Separador B' in linhas, '')

        # 3) A muda um preco no catalogo -> B ve o novo valor no cartao
        await B.evaluate("ir('modelos')"); await B.wait_for_timeout(300)
        await A.evaluate("""()=>{const c=CARROS.find(x=>x.id==='corolla'); c.preco=12340000; guardar(); renderGrid();}""")
        await B.wait_for_timeout(900)
        precoB = await B.evaluate("()=>CARROS.find(c=>c.id==='corolla').preco")
        cartao = await B.evaluate("""()=>{const el=[...document.querySelectorAll('#grid .car')]
            .find(c=>c.innerText.includes('Corolla'));
            return el ? {valor:el.querySelector('.pr').dataset.valor, alvo:_alvo.get(el.querySelector('.pr'))} : null;}""")
        ok('Separador B recebe o preco novo do catalogo', precoB == 12340000, precoB)
        ok('...e o cartao de B passa a apontar para o valor novo',
           cartao and str(cartao['valor']) == '12340000' and str(cartao['alvo']) == '12340000', cartao)

        # 4) B esta a ver o detalhe desse carro: acompanha sem sair do ecra
        await B.evaluate("()=>{atual=CARROS.find(c=>c.id==='corolla');abrirDetalhe()}")
        await B.wait_for_timeout(300)
        await A.evaluate("""()=>{const c=CARROS.find(x=>x.id==='corolla'); c.preco=15000000; guardar(); renderGrid();}""")
        await B.wait_for_timeout(1200)
        det = await B.evaluate("()=>document.getElementById('dPreco').textContent")
        ok('Detalhe aberto em B atualiza o valor em direto', '15,000,000' in det, det)

        # 5) B esta a montar um orcamento: o desconto escrito por B nao pode ser perdido por A
        await B.click('#btnCriarOrc'); await B.wait_for_timeout(250)
        await B.click('#btnSalvar'); await B.wait_for_timeout(300)
        await B.evaluate("()=>{const i=document.getElementById('oDesc'); i.value='1,000,000 Kz'; calc();}")
        await B.wait_for_timeout(400)
        descontoB = await B.evaluate("()=>DESCONTO_ORC")
        await A.evaluate("()=>{CARROS[CARROS.length-1].cor='Verde'; guardar();}")   # A grava catalogo
        await B.wait_for_timeout(1000)
        descontoB2 = await B.evaluate("()=>document.getElementById('oDesc').value")
        ok('Escrita de A nao apaga o desconto em edicao em B', descontoB == 1000000 and '1,000,000' in descontoB2,
           f'{descontoB} / {descontoB2}')

        # 6) dados da loja: A muda o nome no Perfil -> B recebe na mensagem
        await A.evaluate("""()=>{LOJA.dados='Peugeot Stand'; LOJA.zap='951006421'; guardarLoja();}""")
        await B.wait_for_timeout(900)
        lojaB = await B.evaluate("()=>LOJA.dados + ' | ' + linhaLoja()")
        ok('Separador B recebe os dados da loja', 'Peugeot Stand' in lojaB, lojaB)

        # 7) tema
        await A.evaluate("()=>{localStorage.setItem('modelo_tema_v1','escuro'); iniciarTemaDoDisco();}")
        await B.wait_for_timeout(900)
        ok('Tema igual nos dois separadores', await B.evaluate("()=>document.documentElement.dataset.tema") == 'escuro', '')

        # 8) apagar em B -> desaparece em A
        await B.evaluate("()=>{ORCAMENTOS=ORCAMENTOS.filter(o=>o.id!=='sep1'); guardarOrc();}")
        await B.wait_for_timeout(800)
        ok('Orcamento apagado em B desaparece em A', not await A.evaluate("()=>ORCAMENTOS.some(o=>o.id==='sep1')"), '')

        # 9) nao deve haver sincronizacoes em falso (bate-bola entre separadores)
        await A.wait_for_timeout(1500)
        sA = await A.evaluate("()=>sincronizacoes"); sB = await B.evaluate("()=>sincronizacoes")
        await A.wait_for_timeout(5000)
        sA2 = await A.evaluate("()=>sincronizacoes"); sB2 = await B.evaluate("()=>sincronizacoes")
        ok('Sem sincronizacoes em ciclo (separadores em repouso)', sA == sA2 and sB == sB2,
           f'A {sA}->{sA2} | B {sB}->{sB2}')
        ok('Nenhum erro de JavaScript nos dois separadores', not erros, '; '.join(erros[:2]))

        # 10) desempenho da sincronizacao
        t = await A.evaluate("""async()=>{const a=performance.now(); adotarDadosDeOutroSeparador();
            await new Promise(r=>requestAnimationFrame(r)); return Math.round(performance.now()-a);}""")
        ok('Tempo de uma sincronizacao', t < 200, f'{t} ms')
        await b.close()

    falhas = sum(1 for _, c, _ in res if not c)
    print(f'\n{len(res)} verificacoes · {len(res)-falhas} conformes · {falhas} falhas')
    sys.exit(1 if falhas else 0)

asyncio.run(main())
