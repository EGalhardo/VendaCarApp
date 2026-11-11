# -*- coding: utf-8 -*-
"""R66 - sondagens de stress: muitas vendas, offline, dois separadores, matematica."""
import asyncio, json, time
from playwright.async_api import async_playwright
REL = []

def reg(nome, valor, alvo, ok, nota=''):
    REL.append((nome, valor, alvo, ok, nota))

async def main():
    async with async_playwright() as brw:
        b = await brw.chromium.launch()
        ctx = await b.new_context(viewport={'width': 1440, 'height': 900})
        pg = await ctx.new_page()
        erros = []
        pg.on('pageerror', lambda e: erros.append(str(e)))
        await pg.goto('http://localhost:8000/index.html')
        await pg.wait_for_selector('#pg-modelos:not(.hidden)')
        await pg.evaluate("localStorage.clear()")
        await pg.reload()
        await pg.wait_for_selector('#pg-modelos:not(.hidden)')
        await pg.wait_for_timeout(500)

        # ---- 1. matematica do orcamento ----
        await pg.evaluate("()=>{atual=CARROS.find(c=>c.id==='corolla');abrirDetalhe()}")
        await pg.wait_for_timeout(200)
        await pg.click('#btnCriarOrc'); await pg.wait_for_timeout(200)
        await pg.click('#btnSalvar'); await pg.wait_for_timeout(300)
        await pg.type('#oDesc','1234567'); await pg.wait_for_timeout(8600)
        mat = await pg.evaluate("""()=>{const n=t=>Number(String(t).replace(/[^0-9.]/g,''));
            const preco=atual.preco, desc=Math.min(1234567,preco);
            const iva=Math.round(n(document.getElementById('oIva').textContent)*100)/100;
            const tot=n(document.getElementById('oTotalIva').textContent);
            const saldo=n(document.getElementById('oSaldo').textContent);
            const p12=n(document.getElementById('o12').textContent), p24=n(document.getElementById('o24').textContent),
                  p36=n(document.getElementById('o36').textContent);
            return {preco, iva, tot, saldo, p12, p24, p36,
                    ivaEsperado:Math.round(preco*0.14*100)/100, totEsperado:Math.round(preco*1.14*100)/100,
                    p12Esperado:Math.round(saldo/12*100)/100, p36Esperado:Math.round(saldo/36*100)/100};}""")
        ok_iva = abs(mat['iva'] - mat['ivaEsperado']) < 1
        ok_tot = abs(mat['tot'] - mat['totEsperado']) < 1
        ok_par = abs(mat['p12']*12 - mat['saldo']) / mat['saldo'] < 0.02 and abs(mat['p36']*36 - mat['saldo']) / mat['saldo'] < 0.02
        reg('IVA 14% calculado a parte e somado ao total', f'{mat["iva"]:.0f} / {mat["tot"]:.0f}', 'preco*0.14 e preco*1.14',
            ok_iva and ok_tot, json.dumps({k: round(v) for k, v in mat.items()}))
        reg('Parcelas 12x/24x/36x somam o saldo a pagar', f'{mat["p12"]*12:.0f} vs {mat["saldo"]:.0f} (12x)', 'soma = saldo (±2%)',
            ok_par, '')

        # ---- 2. desconto maior que o preco ----
        await pg.fill('#oDesc',''); await pg.type('#oDesc','999999999'); await pg.wait_for_timeout(8600)
        lim = await pg.evaluate("""()=>({vista:document.getElementById('oVista').textContent,
            num:Number(String(document.getElementById('oVista').textContent).replace(/[^0-9.]/g,'')),
            descMini:document.getElementById('oDescMini').textContent})""")
        reg('Desconto maior que o preco nao gera valor negativo', lim['vista'], '>= 0 Kz',
            lim['num'] >= 0 and '-' not in lim['vista'], f'desconto aplicado: {lim["descMini"]}')

        # ---- 3. aviso de preco vazio / entrada > preco ----
        await pg.fill('#oEntrada',''); await pg.type('#oEntrada','99999999999'); await pg.wait_for_timeout(500)
        sld = await pg.evaluate("()=>document.getElementById('oSaldo').textContent")
        reg('Entrada acima do preco e limitada', sld, '0 Kz', '0 Kz' in sld)

        # ---- 4. link de WhatsApp ----
        await pg.evaluate("window.open=(u)=>{window.__u=u;};")
        await pg.click('#btnEnviar'); await pg.wait_for_timeout(250)
        await pg.fill('#mNome','Ana Silva'); await pg.fill('#mTel','923111222')
        await pg.click('#btnZap'); await pg.wait_for_timeout(500)
        u = await pg.evaluate("()=>window.__u || ''")
        import urllib.parse as up
        txt = up.unquote(u.split('text=')[1]) if 'text=' in u else ''
        reg('Link do WhatsApp com +244 e nome', u.split('?')[0], 'wa.me/244923111222',
            u.startswith('https://wa.me/244923111222?text=') and 'Ana Silva' in txt)
        reg('Mensagem: carro, IVA, total e a vista', 'ok' if ('Corolla' in txt and 'IVA' in txt and 'vista' in txt) else 'falta',
            'todos', 'Corolla' in txt and 'IVA' in txt and 'vista' in txt, txt.split('\n')[3][:60])

        # ---- 5. STRESS: 300 automoveis e 500 orcamentos ----
        await pg.evaluate("""()=>{
            for(let i=0;i<300;i++) CARROS.push({id:'x'+i, nome:'Carro Teste '+i, tipo:'Sedan', ano:2020,
                cat:'Usado', cor:'Preto', preco:5000000+i*1000, desc:0, img:CARROS[0].img, fotos:[CARROS[0].img], videos:[]});
            for(let i=0;i<500;i++) ORCAMENTOS.push({id:'y'+i, carro:CARROS[i%CARROS.length].id, carroNome:'Carro Teste '+i,
                nome:'Cliente '+i, tel:'92300000'+String(i).padStart(2,'0').slice(-2), data:'2026-0'+(1+i%9)+'-1'+(i%9),
                preco:5000000+i*1000, entrada:500000, desc:i%3===0?100000:0, estado:['Pendente','Em negociação','Venda concluída','Perdido'][i%4],
                enviado:i%2===0, reenvios:0});
            guardar();}""")
        t_render = await pg.evaluate("""async()=>{const a=performance.now();
            renderTabelaOrc();
            await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
            return performance.now()-a;}""")
        reg('Tabela de Orcamentos com 506 linhas', f'{t_render:.0f} ms', '< 400 ms', t_render < 400)
        t_cli = await pg.evaluate("""async()=>{const a=performance.now();renderClientes();
            await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));return performance.now()-a;}""")
        reg('Lista de Clientes com 500+ clientes', f'{t_cli:.0f} ms', '< 400 ms', t_cli < 400)
        t_grid = await pg.evaluate("""async()=>{const a=performance.now();renderGrid();
            await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));return performance.now()-a;}""")
        reg('Grelha de Automoveis com 304 carros', f'{t_grid:.0f} ms', '< 400 ms', t_grid < 400)
        t_ven = await pg.evaluate("""async()=>{const a=performance.now();renderVendas();
            await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));return performance.now()-a;}""")
        reg('Ecra de Vendas com 506 negocios', f'{t_ven:.0f} ms', '< 400 ms', t_ven < 400)
        t_filtro = await pg.evaluate("""async()=>{const i=document.getElementById('buscaCliente');
            const a=performance.now(); renderClientes('Cliente 4');
            await new Promise(r=>requestAnimationFrame(r)); const d=performance.now()-a;
            renderClientes(''); return d;}""")
        reg('Pesquisar clientes com 500+ registos', f'{t_filtro:.0f} ms', '< 200 ms', t_filtro < 200)
        bytes_ls = await pg.evaluate("""()=>{let t=0;for(let i=0;i<localStorage.length;i++){
            const k=localStorage.key(i); t+=k.length+(localStorage.getItem(k)||'').length;} return t;}""")
        await pg.wait_for_timeout(100)
        reg('Tamanho dos dados no dispositivo', f'{bytes_ls/1024:.0f} KB', '< 5 MB (limite do browser)', bytes_ls < 5 * 1024 * 1024)
        await pg.evaluate("localStorage.clear()")
        await pg.reload(); await pg.wait_for_selector('#pg-modelos:not(.hidden)')
        await pg.wait_for_timeout(400)

        # ---- 6. DOIS SEPARADORES (telemovel + balcao) ----
        pg2 = await ctx.new_page()
        await pg2.goto('http://localhost:8000/index.html')
        await pg2.wait_for_selector('#pg-modelos:not(.hidden)')
        await pg2.wait_for_timeout(400)
        n1 = await pg.evaluate("()=>ORCAMENTOS.length")
        await pg2.evaluate("""()=>{ORCAMENTOS.push({id:'sync1', carro:CARROS[0].id, carroNome:CARROS[0].nome,
            nome:'Cliente Outro Separador', tel:'923444555', data:'2026-11-05', preco:9000000,
            entrada:900000, desc:0, estado:'Pendente', enviado:false, reenvios:0}); guardarOrc();}""")
        await pg.wait_for_timeout(600)
        n1b = await pg.evaluate("()=>ORCAMENTOS.length")
        await pg2.close()
        reg('Dois separadores: o outro separador ve o orcamento novo', f'{n1} -> {n1b}', 'atualiza sozinho',
            n1b == n1 + 1, 'sem evento "storage": precisa de recarregar' if n1b == n1 else '')

        # ---- 7. OFFLINE (ficheiro local, sem servidor) ----
        pg3 = await ctx.new_page()
        await pg3.goto('file:///home/user/index.html')
        await pg3.wait_for_timeout(600)
        offline = await pg3.evaluate("""()=>({ecra:!document.getElementById('pg-modelos').classList.contains('hidden'),
            carros:CARROS.length, imagens:document.querySelectorAll('#grid img').length})""")
        await pg3.evaluate("()=>{atual=CARROS[0];abrirDetalhe()}"); await pg3.wait_for_timeout(300)
        off2 = await pg3.evaluate("()=>document.getElementById('dPreco').textContent")
        await pg3.close()
        reg('Funciona offline a partir do ficheiro (file://)', json.dumps(offline), 'abre e mostra dados',
            offline['ecra'] and offline['carros'] > 0 and offline['imagens'] > 0, f'detalhe: {off2}')

        reg('Erros de JavaScript nas sondagens', len(erros), '0', not erros, '; '.join(erros[:3]))
        await b.close()

    print('\n' + '=' * 96)
    falhas = 0
    for nome, valor, alvo, ok, nota in REL:
        if not ok: falhas += 1
        print(f'{nome[:54]:54} {str(valor)[:20]:20} {str(alvo)[:18]:18} {"OK" if ok else "FALHA"}')
        if nota: print(f'    -> {str(nota)[:120]}')
    print('=' * 96)
    print(f'{len(REL)} sondagens · {len(REL)-falhas} conformes · {falhas} falhas')
    json.dump([{'nome': n, 'valor': str(v), 'alvo': str(a), 'ok': o, 'nota': str(t)} for n, v, a, o, t in REL],
              open('/home/user/qa/auditoria-r66-stress.json', 'w'), ensure_ascii=False, indent=1)

asyncio.run(main())
