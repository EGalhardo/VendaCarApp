# -*- coding: utf-8 -*-
"""Auditoria R66 - performance + sincronizacao, do ponto de vista de quem vende.
Corre o app num browser real e mede: carga, navegacao, fluidez de escrita,
consistencia dos numeros entre ecras e persistencia depois de recarregar."""
import asyncio, json, time, statistics
from playwright.async_api import async_playwright

BASE = 'http://localhost:8000/index.html'
REL = []

def reg(nome, valor, alvo, ok=None, nota=''):
    REL.append({'nome': nome, 'valor': valor, 'alvo': alvo, 'ok': ok, 'nota': nota})

async def ms(pg, expr):
    return await pg.evaluate(expr)

async def main():
    async with async_playwright() as brw:
        b = await brw.chromium.launch()
        ctx = await b.new_context(viewport={'width': 1440, 'height': 900})
        pg = await ctx.new_page()
        erros, reqs, pesos = [], [], {}
        pg.on('pageerror', lambda e: erros.append('JS: ' + str(e)))
        pg.on('console', lambda m: erros.append('console: ' + m.text) if m.type == 'error' else None)
        pg.on('request', lambda r: reqs.append(r.url))
        pg.on('response', lambda r: pesos.__setitem__(r.url, r.headers.get('content-length') or '?'))

        # ---------------- 1. CARGA ----------------
        t0 = time.perf_counter()
        await pg.goto(BASE)
        await pg.wait_for_selector('#pg-modelos:not(.hidden)', timeout=8000)
        carga = (time.perf_counter() - t0) * 1000
        await pg.wait_for_timeout(400)

        nav = await pg.evaluate("""()=>{const n=performance.getEntriesByType('navigation')[0];
            const p=performance.getEntriesByType('paint');
            const fcp=(p.find(x=>x.name==='first-contentful-paint')||{}).startTime||0;
            return {domContentLoaded:Math.round(n.domContentLoadedEventEnd),
                    load:Math.round(n.loadEventEnd), fcp:Math.round(fcp),
                    transfer: n.transferSize, decoded: n.decodedBodySize};}""")
        externos = [u for u in reqs if not u.startswith('http://localhost:8000')]
        locais = [u for u in reqs if u.startswith('http://localhost:8000')]
        reg('Carga inicial (ate o ecra de Automoveis)', f'{carga:.0f} ms', '< 1500 ms', carga < 1500)
        reg('First Contentful Paint', f'{nav["fcp"]} ms', '< 800 ms', nav['fcp'] < 800)
        reg('DOMContentLoaded', f'{nav["domContentLoaded"]} ms', '< 1200 ms', nav['domContentLoaded'] < 1200)
        reg('Tamanho do ficheiro unico', f'{nav["decoded"]/1024:.0f} KB', 'sem limite', None,
          'html + css + js + imagens embutidas (base64)')
        reg('Pedidos de rede necessarios', f'{len(reqs)}', '1 (offline)', len(reqs) == 1,
          'zero CDNs, zero fontes externas')
        reg('Recursos externos', f'{len(externos)}', '0', len(externos) == 0, ', '.join(externos[:3]))

        # ---------------- 2. ARRANQUE / DADOS ----------------
        boot = await pg.evaluate("""()=>{const t=performance.now();
            return {carros:CARROS.length, orcs:ORCAMENTOS.length, clientes:new Set(ORCAMENTOS.map(o=>o.tel)).size,
                    versao:localStorage.getItem('modelo_versao_dados'), ms:Math.round(performance.now()-t)}}""")
        reg('Catalogo de demonstracao', f'{boot["carros"]} automoveis', '> 0', boot['carros'] > 0)
        reg('Orcamentos de demonstracao', f'{boot["orcs"]}', '> 0', boot['orcs'] > 0)
        reg('Versao dos dados gravada', boot['versao'], '= modelo atual', boot['versao'] is not None)

        # ---------------- 3. NAVEGACAO ----------------
        tempos = {}
        for pid in ['modelos', 'listaorc', 'vendas', 'clientes', 'perfil']:
            t = await pg.evaluate(f"""async()=>{{const a=performance.now();ir('{pid}');
                await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
                return performance.now()-a;}}""")
            tempos[pid] = round(t, 1)
        pior = max(tempos.values())
        reg('Navegacao entre as 5 secoes', f'max {pior:.0f} ms', '< 120 ms', pior < 120,
          json.dumps(tempos))

        # ---------------- 4. FLUXO DO VENDEDOR ----------------
        await pg.evaluate("ir('modelos')"); await pg.wait_for_timeout(200)
        await pg.evaluate("()=>{atual=CARROS.find(c=>c.id==='corolla');abrirDetalhe()}")
        await pg.wait_for_timeout(200)
        await pg.click('#btnCriarOrc'); await pg.wait_for_timeout(200)
        await pg.click('#btnSalvar'); await pg.wait_for_timeout(300)

        # fluidez: 40 teclas no desconto, mede o tempo de resposta do recalculo
        await pg.click('#oDesc')
        lat = []
        for ch in '1234567890' * 4:
            t = await pg.evaluate("()=>performance.now()")
            await pg.keyboard.type(ch)
            d = await pg.evaluate("()=>performance.now()") - t
            lat.append(d)
        lat_med = statistics.median(lat); lat_max = max(lat)
        reg('Recalculo por tecla no desconto',
          f'mediana {lat_med:.0f} ms / pior {lat_max:.0f} ms', 'pior < 50 ms', lat_max < 50,
          'cartao, resumo, IVA, parcelas e mensagem no mesmo instante')

        # ---------------- 5. SINCRONIZACAO ENTRE ECRAS ----------------
        await pg.fill('#oDesc',''); await pg.type('#oDesc','500000')
        await pg.wait_for_timeout(9000)          # deixa a contagem de 0 a 0 terminar
        sinc = await pg.evaluate("""()=>{const n=t=>Number(String(t).replace(/[^0-9.]/g,''));
            const preco=atual.preco, desc=500000, vista=preco-desc;
            const q={cartao:n(document.getElementById('oPreco').textContent),
                     painel:n(document.getElementById('oVistaCalc').textContent),
                     resumo:n(document.getElementById('oDescTxt').textContent),
                     maVista:n(document.getElementById('oVista').textContent),
                     descMini:n(document.getElementById('oDescMini').textContent)};
            return {preco, vista, q, esperado:{cartao:vista, painel:vista, resumo:desc,
                    maVista:vista, descMini:desc}};}""")
        difs = [k for k, v in sinc['esperado'].items() if abs(sinc['q'][k] - v) > 1]
        reg('Orcamento: 5 numeros coerentes com preco - desconto',
          'sim' if not difs else 'divergem: ' + ','.join(difs), 'todos iguais',
          not difs, json.dumps({k: round(v, 2) for k, v in sinc['q'].items()}))

        msg = await pg.evaluate("()=>mensagem()")
        import re
        val_msg = re.findall(r'valor de ([\d.,]+) Kz', msg)
        ok_msg = bool(val_msg) and abs(float(val_msg[0].replace(',', '')) - sinc['vista']) < 1
        reg('Mensagem de WhatsApp com o valor a vista negociado', val_msg[0] if val_msg else 'nao encontrado',
          f'{sinc["vista"]:,.0f}'.replace(',', ','), ok_msg)

        # enviar e ver o orcamento cair na lista de Orcamentos, Vendas e Clientes
        await pg.click('#btnEnviar'); await pg.wait_for_timeout(250)
        await pg.fill('#mNome','Cliente Auditoria'); await pg.fill('#mTel','923 000 111')
        await pg.click('#btnZap'); await pg.wait_for_timeout(700)
        novo = await pg.evaluate("""()=>{const o=[...ORCAMENTOS].reverse().find(x=>x.nome==='Cliente Auditoria')||{};
            return {nome:o.nome, tel:o.tel, preco:o.preco, desc:o.desc, vista:o.vista,
                    estado:o.estado, enviado:o.enviado, total:ORCAMENTOS.length};}""")
        reg('Orcamento guardado ao enviar', f'{novo.get("nome")} / desc {novo.get("desc")}', 'nome + desconto',
            novo.get('nome') == 'Cliente Auditoria' and novo.get('desc') == 500000, json.dumps(novo, default=str))
        await pg.evaluate("ir('listaorc')"); await pg.wait_for_timeout(400)
        na_lista = await pg.evaluate("()=>document.getElementById('tblOrc').innerText.includes('Cliente Auditoria')")
        linhas = await pg.evaluate("()=>document.querySelectorAll('#tblOrc tr.cli').length")
        reg('Aparece em Orcamentos', 'sim' if na_lista else 'nao', 'inclui o novo', na_lista, f'{linhas} linhas na tabela')
        await pg.evaluate("ir('vendas')"); await pg.wait_for_timeout(300)
        vendas_txt = await pg.inner_text('#vendasLista')
        reg('Aparece em Vendas (negocios em curso)', 'sim' if 'Cliente Auditoria' in vendas_txt else 'nao',
          'sim', 'Cliente Auditoria' in vendas_txt)
        await pg.evaluate("ir('clientes')"); await pg.wait_for_timeout(300)
        cli = await pg.evaluate("()=>document.querySelectorAll('#tblClientes tr.cli').length")
        tem_cli = await pg.evaluate("()=>document.getElementById('tblClientes').innerText.includes('Cliente Auditoria')")
        reg('Aparece em Clientes', 'sim' if tem_cli else 'nao', 'sim', tem_cli, f'{cli} clientes')

        # ---------------- 6. PERSISTENCIA ----------------
        antes = await pg.evaluate("()=>ORCAMENTOS.filter(o=>o.nome==='Cliente Auditoria').length")
        await pg.reload()
        await pg.wait_for_selector('#pg-modelos:not(.hidden)'); await pg.wait_for_timeout(700)
        depois = await pg.evaluate("""()=>{const o=ORCAMENTOS.find(x=>x.nome==='Cliente Auditoria');
            return {n:ORCAMENTOS.filter(x=>x.nome==='Cliente Auditoria').length,
                    desc:o?o.desc:null, tel:o?o.tel:null};}""")
        reg('Sobrevive a um recarregamento (sem duplicar)', f'{antes} -> {depois["n"]}',
          '1 e igual', antes == 1 and depois['n'] == 1, json.dumps(depois))
        reg('Desconto negociado mantido apos recarregar', depois['desc'], '500000', depois['desc'] == 500000)

        # ---------------- 7. EDITAR NO DETALHE DO ORCAMENTO ----------------
        await pg.evaluate("ir('listaorc')"); await pg.wait_for_timeout(300)
        oid = await pg.evaluate("()=>ORCAMENTOS.find(o=>o.nome==='Cliente Auditoria').id")
        await pg.evaluate(f"()=>abrirOrcDetalhe('{oid}')"); await pg.wait_for_timeout(400)
        await pg.fill('#odDescInp',''); await pg.type('#odDescInp','900000'); await pg.wait_for_timeout(9000)
        det = await pg.evaluate("""()=>{const o=ORCAMENTOS.find(x=>x.nome==='Cliente Auditoria');
            const n=t=>Number(String(t).replace(/[^0-9.]/g,''));
            return {gravado:o.desc, ecra:n(document.getElementById('odRVista').textContent),
                    esperado:o.preco-900000};}""")
        reg('Desconto alterado no detalhe recalcula e grava', f'desc {det["gravado"]}',
          '900000 e ecra coerente', det['gravado'] == 900000 and abs(det['ecra'] - det['esperado']) < 1,
          json.dumps(det))
        await pg.reload(); await pg.wait_for_selector('#pg-modelos:not(.hidden)'); await pg.wait_for_timeout(600)
        reg('...e continua la depois de recarregar',
          await pg.evaluate("()=>ORCAMENTOS.find(o=>o.nome==='Cliente Auditoria').desc"), '900000',
          await pg.evaluate("()=>ORCAMENTOS.find(o=>o.nome==='Cliente Auditoria').desc") == 900000)

        # ---------------- 8. REGISTAR AUTOMOVEL E USAR NO ORCAMENTO ----------------
        await pg.evaluate("ir('modelos')"); await pg.wait_for_timeout(200)
        await pg.locator('[data-criar]:visible').click(); await pg.wait_for_timeout(300)
        await pg.fill('#fMarca','Toyota'); await pg.fill('#fModelo','Hilux Aud')
        await pg.select_option('#fAno','2024'); await pg.select_option('#fTipo','Novo')
        await pg.fill('#fCor','Preto'); await pg.type('#fPreco','32000000')
        await pg.click('#btnGuardarModelo'); await pg.wait_for_timeout(600)
        novo_carro = await pg.evaluate("""()=>{const c=CARROS[CARROS.length-1];
            return {nome:c.nome, preco:c.preco, desc:c.desc};}""")
        reg('Registar automovel (sem campo de desconto)', json.dumps(novo_carro),
          'preco 32.000.000 e desc 0', novo_carro['preco'] == 32000000 and novo_carro['desc'] == 0)
        await pg.click('#btnCriarOrc'); await pg.wait_for_timeout(250)
        await pg.click('#btnSalvar'); await pg.wait_for_timeout(9000)
        reg('Automovel novo cria orcamento com o preco certo',
          await pg.evaluate("()=>document.getElementById('oVista').textContent"), '32,000,000 Kz',
          '32,000,000' in await pg.evaluate("()=>document.getElementById('oVista').textContent"))

        # ---------------- 9. ESTADOS DO NEGOCIO ----------------
        await pg.evaluate("ir('listaorc')"); await pg.wait_for_timeout(300)
        await pg.evaluate(f"()=>abrirOrcDetalhe('{oid}')"); await pg.wait_for_timeout(300)
        await pg.select_option('#odEstadoInp','Venda concluída'); await pg.wait_for_timeout(200)
        await pg.click('#odGuardar'); await pg.wait_for_timeout(400)
        await pg.evaluate("ir('vendas')"); await pg.wait_for_timeout(500)
        funil = await pg.evaluate("""()=>({vendas:document.getElementById('fnVendasPill').textContent,
            fechadas:ORCAMENTOS.filter(o=>o.estado==='Venda concluída').length,
            emCurso:ORCAMENTOS.filter(o=>['Pendente','Em negociação'].includes(o.estado)).length})""")
        reg('Marcar venda concluida atualiza o funil', json.dumps(funil, ensure_ascii=False),
          'pill = fechadas', funil['vendas'].startswith(str(funil['fechadas'])))

        # ---------------- 10. ELIMINAR ----------------
        await pg.evaluate("ir('listaorc')"); await pg.wait_for_timeout(300)
        n_antes = await pg.evaluate("()=>ORCAMENTOS.length")
        await pg.evaluate(f"()=>abrirOrcDetalhe('{oid}')"); await pg.wait_for_timeout(300)
        pg.on('dialog', lambda d: asyncio.ensure_future(d.accept()))
        await pg.click('#odApagar')
        await pg.wait_for_timeout(400)
        n_depois = await pg.evaluate("()=>ORCAMENTOS.length")
        await pg.reload(); await pg.wait_for_selector('#pg-modelos:not(.hidden)'); await pg.wait_for_timeout(500)
        n_final = await pg.evaluate("()=>ORCAMENTOS.length")
        reg('Eliminar orcamento (e nao voltar ao recarregar)', f'{n_antes} -> {n_depois} -> {n_final}',
          'desce e mantem-se', n_depois == n_antes - 1 and n_final == n_depois)

        # ---------------- 11. TEMA E MEMORIA ----------------
        await pg.evaluate("()=>document.getElementById('btnTema').click()"); await pg.wait_for_timeout(300)
        tema = await pg.evaluate("()=>document.documentElement.getAttribute('data-tema')")
        await pg.reload(); await pg.wait_for_selector('#pg-modelos:not(.hidden)'); await pg.wait_for_timeout(500)
        tema2 = await pg.evaluate("()=>document.documentElement.getAttribute('data-tema')")
        reg('Tema escolhido persiste', f'{tema} -> {tema2}', 'igual', tema == tema2)

        mem = await pg.evaluate("""()=>{const m=performance.memory;
            return m? {usado:Math.round(m.usedJSHeapSize/1048576), limite:Math.round(m.jsHeapSizeLimit/1048576)} : null;}""")
        if mem:
            reg('Memoria JS em uso', f'{mem["usado"]} MB', '< 80 MB', mem['usado'] < 80, f'limite {mem["limite"]} MB')

        # ---------------- 12. ECRAS LARGOS/ESTREITOS ----------------
        for w, h, nome in [(390, 844, 'telemovel'), (768, 1024, 'tablet'), (1440, 900, 'portatil')]:
            await pg.set_viewport_size({'width': w, 'height': h})
            await pg.wait_for_timeout(250)
            for pid in ['modelos', 'orcamento', 'vendas', 'clientes', 'perfil']:
                await pg.evaluate(f"ir('{pid}')"); await pg.wait_for_timeout(120)
            transbordo = await pg.evaluate("""()=>{const d=document.documentElement;
                return {x: d.scrollWidth > d.clientWidth + 2, sw:d.scrollWidth, cw:d.clientWidth};}""")
            reg(f'Sem conteudo a sair do ecra ({nome} {w}px)',
              'sim' if not transbordo['x'] else f'transborda {transbordo["sw"]}>{transbordo["cw"]}',
              'nenhum', not transbordo['x'])

        reg('Erros de JavaScript durante toda a sessao', len(erros), '0', not erros, '; '.join(erros[:3]))
        await b.close()

    # ---------------- RELATORIO ----------------
    print('\n' + '=' * 96)
    print(f'{"TESTE":56} {"RESULTADO":22} {"ALVO":18} OK')
    print('=' * 96)
    falhas = 0
    for r in REL:
        ok = '' if r['ok'] is None else ('OK' if r['ok'] else 'FALHA')
        if r['ok'] is False: falhas += 1
        print(f'{r["nome"][:56]:56} {str(r["valor"])[:22]:22} {str(r["alvo"])[:18]:18} {ok}')
        if r['nota']: print(f'    -> {r["nota"]}')
    print('=' * 96)
    print(f'{len(REL)} verificacoes · {len(REL)-falhas} conformes · {falhas} falhas')
    json.dump(REL, open('/home/user/qa/auditoria-r66.json', 'w'), ensure_ascii=False, indent=1)

asyncio.run(main())
