# -*- coding: utf-8 -*-
"""R70 - eliminar aplica-se a todos os dados dependentes (teste real no browser)."""
import asyncio, sys
from playwright.async_api import async_playwright

URL = 'http://localhost:8000/index.html#semcarregamento'
res = []

def ok(nome, cond, extra=''):
    res.append(cond)
    print(('OK   ' if cond else 'FALHA') + ' ' + nome + (' | ' + str(extra)[:110] if extra else ''))

async def novo(pg):
    # #hash nao recarrega: passa por about:blank para garantir um arranque limpo
    await pg.goto('about:blank')
    await pg.goto(URL)
    await pg.wait_for_selector('#pg-modelos:not(.hidden)')
    await pg.evaluate("localStorage.clear()")
    await pg.reload()
    await pg.wait_for_selector('#pg-modelos:not(.hidden)')
    await pg.wait_for_timeout(500)

async def main():
    async with async_playwright() as brw:
        b = await brw.chromium.launch()
        pg = await (await b.new_context(viewport={'width': 1440, 'height': 900})).new_page()
        erros = []
        pg.on('pageerror', lambda e: erros.append(str(e)))
        pg.on('dialog', lambda d: asyncio.ensure_future(d.accept()))

        # ---------------------------------------------------------- A) apagar AUTOMOVEL
        await novo(pg)
        antes = await pg.evaluate("""()=>({carros:CARROS.length, orcs:ORCAMENTOS.length,
            clientes:new Set(ORCAMENTOS.map(o=>o.tel)).size,
            doCorolla:ORCAMENTOS.filter(o=>o.carro==='corolla').length})""")
        # garantir que um cliente SO tem o carro a apagar (para ver o cliente sair)
        await pg.evaluate("""()=>{ORCAMENTOS.push({id:'soCorolla', nome:'Cliente Só Corolla', tel:'999111222',
            carro:'corolla', carroNome:'Toyota Corolla 2018', preco:9750000, entrada:1000000, desc:0,
            data:Date.now(), estado:'Pendente', enviado:false, reenvios:0}); guardarOrc();}""")
        await pg.evaluate("()=>{FILA_ENVIOS.push({id:'f1', nome:'X', tel:'999111222', texto:'t', orcId:'o1', data:Date.now()}); guardarFila();}")
        await pg.wait_for_timeout(300)
        await pg.evaluate("ir('modelos')"); await pg.wait_for_timeout(300)
        await pg.evaluate("()=>{abrirApagarModelo('corolla');}"); await pg.wait_for_timeout(300)
        await pg.click('#btnApagarModelo'); await pg.wait_for_timeout(700)
        dep = await pg.evaluate("""()=>({carros:CARROS.length, orcs:ORCAMENTOS.length,
            restamDoCorolla:ORCAMENTOS.filter(o=>o.carro==='corolla').length,
            clientes:new Set(ORCAMENTOS.map(o=>o.tel)).size,
            clienteSoCorolla:ORCAMENTOS.some(o=>o.tel==='999111222'),
            fila:FILA_ENVIOS.filter(f=>f.orcId==='o1').length,
            grelha:document.getElementById('grid').innerText.includes('Corolla')})""")
        ok('A · automóvel sai do catálogo', dep['carros'] == antes['carros'] - 1, f"{antes['carros']} -> {dep['carros']}")
        ok('A · orçamentos desse carro são apagados',
           dep['restamDoCorolla'] == 0 and dep['orcs'] == antes['orcs'] - antes['doCorolla'],
           f"orcs {antes['orcs']} - {antes['doCorolla']} do carro -> {dep['orcs']}")
        ok('A · o cliente que ficou sem orçamentos desaparece',
           not dep['clienteSoCorolla'] and dep['clientes'] < antes['clientes'] + 1, str(dep['clientes']))
        ok('A · fila de envios limpa', dep['fila'] == 0, dep['fila'])
        ok('A · a grelha já não mostra o carro', not dep['grelha'], '')
        await pg.evaluate("ir('listaorc')"); await pg.wait_for_timeout(400)
        txt = await pg.inner_text('#tblOrc')
        ok('A · Orçamentos já não lista esses orçamentos', 'Toyota Corolla 2018' not in txt, '')
        await pg.evaluate("ir('vendas')"); await pg.wait_for_timeout(400)
        ven = await pg.inner_text('#vendasLista')
        ok('A · Vendas já não mostra esses negócios', 'Toyota Corolla 2018' not in ven, '')
        await pg.evaluate("ir('clientes')"); await pg.wait_for_timeout(400)
        cli = await pg.inner_text('#tblClientes')
        ok('A · Clientes já não mostra o cliente apagado', 'Cliente Só Corolla' not in cli, '')

        # ---------------------------------------------------------- B) apagar ORCAMENTO (ultimo do cliente)
        await novo(pg)
        q0 = await pg.evaluate("()=>({orcs:ORCAMENTOS.length, cli:new Set(ORCAMENTOS.map(o=>o.tel)).size})")
        alvo = await pg.evaluate("""()=>{const c={}; ORCAMENTOS.forEach(o=>c[o.tel]=(c[o.tel]||0)+1);
            const tel=Object.keys(c).find(t=>c[t]===1); return {tel, id:ORCAMENTOS.find(o=>o.tel===tel).id};}""")
        await pg.evaluate("ir('listaorc')"); await pg.wait_for_timeout(300)
        await pg.evaluate(f"()=>abrirOrcDetalhe('{alvo['id']}')"); await pg.wait_for_timeout(400)
        await pg.click('#odApagar'); await pg.wait_for_timeout(700)
        q1 = await pg.evaluate("""()=>{const o=ORCAMENTOS.find(x=>x.tel===%s);
            return {orcs:ORCAMENTOS.length, existe:!!o,
                    cli:new Set(ORCAMENTOS.map(x=>x.tel)).size,
                    naLista:document.getElementById('tblOrc').innerText.includes('%s')};}""" % (repr(alvo['tel']), alvo['tel']))
        ok('B · orçamento apagado sai da lista', q1['orcs'] == q0['orcs'] - 1, f"{q0['orcs']} -> {q1['orcs']}")
        ok('B · o cliente sem orçamentos sai de Clientes', q1['cli'] == q0['cli'] - 1, f"{q0['cli']} -> {q1['cli']}")
        await pg.evaluate("ir('vendas')"); await pg.wait_for_timeout(400)
        ok('B · Vendas também perde o negócio',
           not await pg.evaluate(f"()=>document.getElementById('vendasLista').innerText.includes('{alvo['tel']}')"), '')

        # ---------------------------------------------------------- C) apagar CLIENTE (2 orcamentos)
        await novo(pg)
        multi = await pg.evaluate("""()=>{const c={}; ORCAMENTOS.forEach(o=>c[o.tel]=(c[o.tel]||0)+1);
            const tel=Object.keys(c).find(t=>c[t]>1); return {tel, nome:ORCAMENTOS.find(o=>o.tel===tel).nome, qtd:c[tel]};}""")
        await pg.evaluate("ir('clientes')"); await pg.wait_for_timeout(400)
        await pg.evaluate("(t)=>abrirCliente(ORCAMENTOS.find(o=>o.tel===t).nome, t, false)", multi['tel'])
        await pg.wait_for_timeout(400)
        await pg.click('#btnApagarCliente'); await pg.wait_for_timeout(800)
        c1 = await pg.evaluate("""(t)=>({restam:ORCAMENTOS.filter(o=>o.tel===t).length,
            cliente:new Set(ORCAMENTOS.map(o=>o.tel)).has(t),
            naLista:document.getElementById('tblClientes').innerText.includes('Maria'),
            ecra:paginaAtual()})""", multi['tel'])
        ok('C · cliente com 2 orçamentos: todos apagados', c1['restam'] == 0, str(multi))
        ok('C · desaparece de Clientes', not c1['cliente'] and not c1['naLista'], str(c1))
        ok('C · volta ao ecrã de Clientes', c1['ecra'] == 'clientes', c1['ecra'])

        # ---------------------------------------------------------- D) consistência global + persistência
        d0 = await pg.evaluate("""()=>{
            const orfs = ORCAMENTOS.filter(o=>o.carro && !CARROS.some(c=>c.id===o.carro)).length;
            const ids = new Set(CARROS.map(c=>c.id));
            const cliTel = new Set(ORCAMENTOS.map(o=>o.tel));
            const clientesVisiveis = [...document.querySelectorAll('#tblClientes tr.cli')].length;
            return {orfãos:orfs, orcs:ORCAMENTOS.length, carros:CARROS.length,
                    clientesVisiveis, cliTel:cliTel.size,
                    filaOrf: FILA_ENVIOS.filter(f=>f.orcId && !ORCAMENTOS.some(o=>o.id===f.orcId)).length};}""")
        ok('D · nenhum orçamento aponta para carro inexistente', d0['orfãos'] == 0, str(d0))
        ok('D · lista de Clientes = clientes com orçamentos',
           d0['clientesVisiveis'] == d0['cliTel'], f"{d0['clientesVisiveis']} vs {d0['cliTel']}")
        ok('D · nenhuma mensagem na fila para orçamento apagado', d0['filaOrf'] == 0, str(d0))

        await pg.reload(); await pg.wait_for_selector('#pg-modelos:not(.hidden)'); await pg.wait_for_timeout(600)
        d1 = await pg.evaluate("""()=>({orcs:ORCAMENTOS.length, carros:CARROS.length,
            clientes:new Set(ORCAMENTOS.map(o=>o.tel)).size})""")
        ok('D · depois de recarregar, os dados continuam coerentes',
           d1 == {'orcs': d0['orcs'], 'carros': d0['carros'], 'clientes': d0['cliTel']}, f'{d1} vs {d0}')

        # ---------------------------------------------------------- E) dois separadores
        ctxE = await b.new_context(viewport={'width': 1440, 'height': 900})
        pg2 = await ctxE.new_page()
        await pg2.goto(URL); await pg2.wait_for_selector('#pg-modelos:not(.hidden)')
        await pg2.evaluate("localStorage.clear()"); await pg2.reload()
        await pg2.wait_for_selector('#pg-modelos:not(.hidden)'); await pg2.wait_for_timeout(500)
        x = await ctxE.new_page()
        await x.goto(URL); await x.wait_for_selector('#pg-modelos:not(.hidden)'); await x.wait_for_timeout(400)
        nA = await x.evaluate("()=>ORCAMENTOS.length")
        await pg2.evaluate("()=>apagarOrcamento(ORCAMENTOS[0].id)")
        await x.wait_for_timeout(1200)
        nB = await x.evaluate("()=>ORCAMENTOS.length")
        ok('E · o outro separador vê o orçamento apagado', nB == nA - 1, f'{nA} -> {nB}')
        await x.close(); await pg2.close()

        ok('Sem erros de JavaScript', not erros, '; '.join(erros[:3]))
        await b.close()

    print(f"\n{len(res)} verificacoes · {sum(res)} conformes · {len(res)-sum(res)} falhas")
    sys.exit(1 if any(not r for r in res) else 0)

asyncio.run(main())
