# -*- coding: utf-8 -*-
"""Bateria de testes ao app de orçamentos (desktop + mobile)."""
import asyncio, json, urllib.parse as up
from playwright.async_api import async_playwright

URL = "file:///home/user/index.html"
R = []          # resultados
def ok(nome, cond, detalhe=""):
    R.append((("PASS" if cond else "FALHA"), nome, detalhe))
    print(("✔" if cond else "✘"), nome, "—", detalhe)

async def novo(pg):
    await pg.goto(URL); await pg.wait_for_timeout(400)
    await pg.evaluate("localStorage.clear()"); await pg.reload(); await pg.wait_for_timeout(500)

async def ir_orcamento_de(pg, modelo="Toyota Corolla 2018"):
    """percorre o fluxo: modelos -> carro -> criar orçamento -> confirmar"""
    await pg.evaluate("ir('modelos')"); await pg.wait_for_timeout(200)
    await pg.evaluate("""(m)=>{
      const c = CARROS.find(x=>x.nome===m); atual=c; abrirDetalhe();
    }""", modelo)
    await pg.wait_for_timeout(300)
    await pg.click("#btnCriarOrc"); await pg.wait_for_timeout(300)
    await pg.click("#btnSalvar"); await pg.wait_for_timeout(350)

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()

        # ============ DESKTOP ============
        pg = await b.new_page(viewport={"width":1440,"height":900})
        errs=[]; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("console", lambda m: errs.append(m.text) if m.type=="error" else None)
        await novo(pg)

        # ---------- 1. ARITMÉTICA ----------
        await ir_orcamento_de(pg)
        casos = [
            ("Corolla 75.000 / entrada 25.000", 75000, 25000),
            ("Entrada sugerida 10%", 75000, 7500),
            ("Entrada = preço (100%)", 75000, 75000),
            ("Entrada 1 Kz", 75000, 1),
            ("Hilux 210.000 / 30.000", 210000, 30000),
            ("Tucson 95.000 / 95.000", 95000, 95000),
        ]
        for nome, preco, entrada in casos:
            # garantir que o carro em ecrã tem o preço do caso
            trocou = await pg.evaluate("""(pr)=>{
                if (atual.preco !== pr){
                  const c = CARROS.find(x=>x.preco===pr);
                  if (c){ atual=c; abrirDetalhe(); return true; }
                }
                return false;
            }""", preco)
            if trocou:
                await pg.wait_for_timeout(250)
                await pg.click("#btnCriarOrc"); await pg.wait_for_timeout(250)
                await pg.click("#btnSalvar"); await pg.wait_for_timeout(300)
            await pg.evaluate("(e)=>{const i=document.getElementById('oEntrada'); i.value=Number(e).toLocaleString('en-US')+' Kz'; calc();}", entrada)
            await pg.wait_for_timeout(120)
            dados = await pg.evaluate("""()=>{
              const g = id => document.getElementById(id).textContent;
              const n = t => Number(String(t).replace(/[^\\d.]/g,''));
              return {saldo:n(g('oSaldo')), d12:n(g('o12')), d24:n(g('o24')), d36:n(g('o36')), vista:n(g('oVista'))};
            }""")
            saldo = preco - entrada
            esperado = {
              'saldo': saldo,
              'd12': round(saldo/12,2), 'd24': round(saldo/24,2), 'd36': round(saldo/36,2)
            }
            bate = all(abs(dados[k]-v) <= 0.01 for k,v in esperado.items())
            ok(f"Aritmética · {nome}", bate,
               f"saldo {dados['saldo']:,} | 12x {dados['d12']:,} (esperado {esperado['d12']:,})")

        # ---------- 2. À VISTA = preço - desconto ----------
        await pg.evaluate("()=>{atual=CARROS.find(c=>c.id==='corolla'); abrirDetalhe();}"); await pg.wait_for_timeout(250)
        await pg.click("#btnCriarOrc"); await pg.wait_for_timeout(250)
        await pg.click("#btnSalvar"); await pg.wait_for_timeout(300)
        v = await pg.evaluate("()=>document.getElementById('oVista').textContent")
        ok("À vista com desconto (75.000 − 15.000)", "60,000" in v, v)

        # ---------- 3. ENTRADA ACIMA DO PREÇO ----------
        await pg.fill("#oEntrada","999999999"); await pg.wait_for_timeout(200)
        s = await pg.evaluate("()=>document.getElementById('oSaldo').textContent")
        ok("Entrada acima do preço é limitada", "0 Kz" in s, f"saldo = {s}")

        # ---------- 4. NEGATIVOS / 12x quando saldo é 0 ----------
        d = await pg.evaluate("()=>[document.getElementById('o12').textContent, document.getElementById('o24').textContent]")
        ok("Saldo 0 → parcelas 0 (sem erro)", d[0].startswith("0") and d[1].startswith("0"), str(d))

        # ---------- 5. PERSISTÊNCIA DO ORÇAMENTO ----------
        await pg.evaluate("()=>{document.getElementById('oEntrada').value='25,000 Kz'; calc();}")
        await pg.click("#btnEnviar"); await pg.wait_for_timeout(300)
        await pg.fill("#mNome","Cliente Teste"); await pg.fill("#mTel","923111999")
        await pg.evaluate("window.__u=null; window.open=(u)=>{window.__u=u;}")
        await pg.click("#btnZap"); await pg.wait_for_timeout(300)
        u = await pg.evaluate("window.__u")
        ok("WhatsApp abre com +244 e texto", u.startswith("https://wa.me/244923111999?text="), u.split('?')[0])
        txt = up.unquote(u.split('text=')[1])
        ok("Mensagem contém carro, entrada e parcelas",
           "Corolla" in txt and "25,000 Kz" in txt and "12x" in txt and "60,000" in txt,
           txt.split("\n")[3] + " …")

        # ---------- 6. CLIENTES / REENVIO ----------
        await pg.evaluate("ir('clientes')"); await pg.wait_for_timeout(300)
        n_cli = await pg.eval_on_selector_all("#tblClientes tr.cli","e=>e.length")
        ok("Cliente criado aparece na lista", n_cli >= 5, f"{n_cli} clientes (4 seed + 1 novo)")

        await pg.evaluate("""()=>{const t=[...document.querySelectorAll('#tblClientes tr.cli')]
           .find(r=>r.dataset.cliente==='Cliente Teste'); abrirCliente(t.dataset.cliente,t.dataset.tel);}""")
        await pg.wait_for_timeout(400)
        q = await pg.inner_text("#cQtd")
        ok("Detalhe mostra orçamentos do cliente", q.strip() in ("1","2"), f"{q} orçamentos")
        await pg.locator("[data-reenviar]").first.click(); await pg.wait_for_timeout(400)
        ok("Reenvio abre popup com dados do cliente",
           (await pg.input_value("#mNome"))=="Cliente Teste" and (await pg.input_value("#mTel"))=="923 111 999",
           "nome/telefone preenchidos")

        # ---------- 7. VALIDAÇÕES ----------
        await pg.keyboard.press("Escape"); await pg.wait_for_timeout(200)
        await pg.evaluate("ir('modelos')"); await pg.wait_for_timeout(200)
        await pg.locator("[data-criar]:visible").click(); await pg.wait_for_timeout(300)
        await pg.click("#btnGuardarModelo"); await pg.wait_for_timeout(250)
        ok("Novo modelo não grava sem dados",
           await pg.evaluate("()=>document.getElementById('mNovoModelo').classList.contains('open')"),
           "modal mantém-se aberto")

        # marca input: capitalização
        await pg.fill("#fMarca","  mitsubishi   motors "); await pg.fill("#fModelo","L200")
        await pg.select_option("#fAno","2022"); await pg.select_option("#fTipo","Novo")
        await pg.type("#fPreco","300000"); await pg.type("#fDesc","20000")
        await pg.click("#btnGuardarModelo"); await pg.wait_for_timeout(500)
        nome = await pg.inner_text("#dNome")
        ok("Marca normalizada/capitalizada", nome.startswith("Mitsubishi Motors L200"), nome)

        # ---------- 8. CASOS-LIMITE DE CATÁLOGO ----------
        # preço 0 → deve bloquear
        await pg.evaluate("ir('modelos')"); await pg.wait_for_timeout(200)
        await pg.locator("[data-criar]:visible").click(); await pg.wait_for_timeout(300)
        await pg.fill("#fMarca","Teste"); await pg.fill("#fModelo","Zero")
        await pg.select_option("#fAno","2020"); await pg.select_option("#fTipo","Usado")
        await pg.click("#btnGuardarModelo"); await pg.wait_for_timeout(300)
        ok("Bloqueia modelo com preço 0",
           await pg.evaluate("()=>document.getElementById('mNovoModelo').classList.contains('open')"), "")
        await pg.wait_for_timeout(1300)

        # desconto maior que o preço
        await pg.type("#fPreco","50000"); await pg.type("#fDesc","80000")
        await pg.click("#btnGuardarModelo"); await pg.wait_for_timeout(500)
        await pg.click("#btnCriarOrc"); await pg.wait_for_timeout(300)
        await pg.click("#btnSalvar"); await pg.wait_for_timeout(350)
        vista = await pg.inner_text("#oVista")
        ok("Desconto > preço não gera valor negativo", not "-" in vista, f"à vista = {vista}")

        # ---------- 9. UPLOAD ----------
        await pg.evaluate("ir('modelos')"); await pg.wait_for_timeout(200)
        await pg.locator("[data-criar]:visible").click(); await pg.wait_for_timeout(300)
        await pg.set_input_files("#fFotos",["/home/user/docs/foto1.jpg","/home/user/docs/foto2.jpg","/home/user/docs/foto3.jpg",
                                            "/home/user/docs/foto4.jpg","/home/user/docs/foto5.jpg","/home/user/docs/foto6.jpg",
                                            "/home/user/docs/foto7.jpg"])
        await pg.wait_for_timeout(900)
        n = await pg.eval_on_selector_all(".up","e=>e.length")
        ok("Limite de 6 imagens respeitado", n==6, f"{n} miniaturas (enviei 7)")

        # ---------- 10. RESPONSIVIDADE ----------
        larg = await pg.evaluate("()=>({side:getComputedStyle(document.querySelector('.side')).display, nav:getComputedStyle(document.querySelector('.navbar')).display})")
        ok("Desktop usa barra lateral", larg['side']=='flex' and larg['nav']=='none', str(larg))

        ok("Sem erros de consola (desktop)", len(errs)==0, str(errs[:2]))
        await pg.close()

        # ============ MOBILE ============
        m = await b.new_page(viewport={"width":390,"height":844}, is_mobile=True, has_touch=True)
        me=[]; m.on("pageerror", lambda e: me.append(str(e)))
        await novo(m)
        lay = await m.evaluate("()=>({side:getComputedStyle(document.querySelector('.side')).display, nav:getComputedStyle(document.querySelector('.navbar')).display})")
        ok("Mobile usa navbar", lay['side']=='none' and lay['nav']=='flex', str(lay))
        # overflow horizontal?
        ow = await m.evaluate("()=>document.documentElement.scrollWidth - document.documentElement.clientWidth")
        ok("Sem scroll horizontal em mobile (390px)", ow<=0, f"overflow = {ow}px")
        # tabela Orçamentos não deve rebentar
        await m.evaluate("ir('listaorc')"); await m.wait_for_timeout(300)
        ow2 = await m.evaluate("()=>document.documentElement.scrollWidth - document.documentElement.clientWidth")
        ok("Orçamentos sem overflow em mobile", ow2<=0, f"overflow = {ow2}px")
        ok("Sem erros de consola (mobile)", len(me)==0, str(me[:2]))
        await m.close()

        # ============ TABLET ============
        t = await b.new_page(viewport={"width":820,"height":1180})
        await novo(t)
        ow3 = await t.evaluate("()=>document.documentElement.scrollWidth - document.documentElement.clientWidth")
        ok("Tablet 820px sem overflow", ow3<=0, f"overflow = {ow3}px")
        await t.close()

        # ============ MODO OFFLINE + BOTÕES DO POPUP (mobile) ============
        ctxo = await b.new_context(viewport={"width":1440,"height":860})
        o = await ctxo.new_page()
        oe=[]; o.on("pageerror", lambda e: oe.append(str(e)))
        await novo(o)
        ok("Arranque online", (await o.inner_text("#netTxt")).strip()=="Online", "")
        await ctxo.set_offline(True); await o.wait_for_timeout(500)
        ok("Offline detetado pela app", (await o.inner_text("#netTxt")).strip().startswith("Offline"),
           await o.inner_text("#netTxt"))
        await o.click("[data-car='corolla']"); await o.wait_for_timeout(600)
        await o.click("#btnCriarOrc"); await o.wait_for_timeout(500)
        await o.click("#btnSalvar"); await o.wait_for_timeout(700)
        await o.click("#btnEnviar"); await o.wait_for_timeout(600)
        await o.fill("#mNome","Cliente Offline"); await o.fill("#mTel","923555444")
        await o.click("#btnZap"); await o.wait_for_timeout(800)
        ok("Orçamento criado offline entra na fila",
           await o.evaluate("()=>FILA_ENVIOS.length")==1, str(await o.evaluate("()=>FILA_ENVIOS.length")))
        ok("Estado do orçamento passa a Pendente",
           await o.evaluate("()=>ORCAMENTOS.find(o=>o.tel==='923555444')?.estado")=="Pendente", "")
        ok("Fila persistida no dispositivo",
           await o.evaluate("()=>JSON.parse(localStorage.getItem('modelo_fila_envios_v1')).length")==1, "")
        await o.reload(); await o.wait_for_timeout(800)
        ok("App recarrega offline com dados",
           await o.evaluate("()=>CARROS.length>=4 && document.querySelectorAll('.car').length>=4"), "")
        ok("Fila mantém-se após recarregar",
           await o.evaluate("()=>JSON.parse(localStorage.getItem('modelo_fila_envios_v1')).length")==1, "")
        await ctxo.set_offline(False); await o.wait_for_timeout(900)
        ok("Ao voltar a rede pede para enviar a fila",
           await o.evaluate("()=>document.getElementById('mFila')?.classList.contains('open')")==True, "")
        await o.click("#mFila [data-fila='nao']"); await o.wait_for_timeout(400)
        ok("'Agora não' preserva a fila", await o.evaluate("()=>FILA_ENVIOS.length")==1, "")
        ok("Sem erros no modo offline", len(oe)==0, str(oe[:2]))
        await ctxo.close()

        # ============ APPBAR MOBILE ÚNICA ============
        ab = await b.new_page(viewport={"width":390,"height":844}, is_mobile=True, has_touch=True)
        ae=[]; ab.on("pageerror", lambda e: ae.append(str(e)))
        await novo(ab)
        g = await ab.evaluate("""()=>{
          const q=s=>document.querySelector(s).getBoundingClientRect();
          const brand=q('.brand'), pill=q('#netPill'), sino=q('.bar .ic-btn'), cont=q('.content');
          return {appbar:Math.round(brand.height), topoConteudo:Math.round(cont.top),
                  barraExtra:Math.round(q('.bar').top),
                  pillDentro: pill.top>=brand.top && pill.bottom<=brand.bottom,
                  sinoDentro: sino.top>=brand.top && sino.bottom<=brand.bottom};
        }""")
        ok("Mobile · appbar única (sem barra extra)", g["appbar"]==58 and g["topoConteudo"]==58 and g["barraExtra"]==0, str(g))
        ok("Mobile · 'Online' na appbar", g["pillDentro"], str(g))
        ok("Mobile · ícone de notificações na appbar", g["sinoDentro"], str(g))
        await ab.evaluate("()=>{atual=CARROS[0]; abrirDetalhe();}"); await ab.wait_for_timeout(500)
        d = await ab.evaluate("""()=>{
          const back=document.getElementById('btnBack'), mark=document.querySelector('.brand .mark');
          const rb=back.getBoundingClientRect(), rm=mark.getBoundingClientRect();
          return {voltar:getComputedStyle(back).visibility==='visible',
                  logoEscondido:getComputedStyle(mark).display==='none',
                  sobreposto: rm.width>0 && rb.right>rm.left};
        }""")
        ok("Mobile · voltar não tapa o logótipo", d["voltar"] and not d["sobreposto"], str(d))
        ok("Mobile · sem erros na appbar única", len(ae)==0, str(ae[:2]))
        await ab.close()

        # ============ CLIENTE · BOTÃO "ENVIAR NOVAMENTE" (mobile) ============
        cb = await b.new_page(viewport={"width":390,"height":844}, is_mobile=True, has_touch=True)
        ce=[]; cb.on("pageerror", lambda e: ce.append(str(e)))
        await novo(cb)
        await cb.evaluate("()=>abrirCliente('Maria Costa','921445010')"); await cb.wait_for_timeout(600)
        hb = await cb.evaluate("""()=>{
          const bs=[...document.querySelectorAll('#cOrcs .orc-card .orc-actions .btn')];
          const env=bs.filter(x=>x.textContent.includes('Enviar novamente'));
          return {n:env.length, alturas:env.map(b=>Math.round(b.getBoundingClientRect().height)),
                  larguras:env.map(b=>Math.round(b.getBoundingClientRect().width)),
                  fs: env.length?getComputedStyle(env[0]).fontSize:null};
        }""")
        ok("Mobile · botão 'Enviar novamente' com altura de toque",
           hb["n"]>0 and all(46<=x<=56 for x in hb["alturas"]), str(hb))
        ok("Mobile · botão ocupa a largura do cartão",
           len(set(hb["larguras"]))==1 and hb["larguras"][0]>=280, str(hb["larguras"]))
        await cb.click("#cOrcs .orc-card .orc-actions .btn"); await cb.wait_for_timeout(500)
        ok("Mobile · botão continua a abrir o popup de envio",
           await cb.evaluate("()=>document.getElementById('mEnviar').classList.contains('open')"), "")
        ok("Mobile · sem erros no detalhe do cliente", len(ce)==0, str(ce[:2]))
        await cb.close()

        mb = await b.new_page(viewport={"width":390,"height":760}, is_mobile=True, has_touch=True)
        await novo(mb)
        await mb.click("[data-criar]:visible"); await mb.wait_for_timeout(700)
        g = await mb.evaluate("""()=>{
          const f=document.querySelector('#mNovoModelo .foot');
          const b1=f.querySelector('.btn:not(.ghost)').getBoundingClientRect();
          const b2=f.querySelector('.btn.ghost').getBoundingClientRect();
          return {h1:Math.round(b1.height),h2:Math.round(b2.height),
                  w1:Math.round(b1.width),w2:Math.round(b2.width),
                  ordem: b1.bottom<=b2.top, fim:Math.round(f.getBoundingClientRect().bottom)<=innerHeight};
        }""")
        ok("Mobile · botões com altura harmoniosa", 44<=g["h1"]<=52 and 44<=g["h2"]<=52, str(g))
        ok("Mobile · botões com a mesma largura", abs(g["w1"]-g["w2"])<=1, str(g))
        ok("Mobile · Guardar acima de Cancelar", g["ordem"], "")
        ok("Mobile · rodapé dentro do ecrã", g["fim"], "")
        await mb.screenshot(path="/home/user/qa/mobile_popup.png")
        await mb.close()

        # ============ ORÇAMENTO: DETALHE E EDIÇÃO ============
        d = await b.new_page(viewport={"width":1440,"height":900})
        de=[]; d.on("pageerror", lambda e: de.append(str(e)))
        await novo(d)
        await d.evaluate("ir('listaorc')"); await d.wait_for_timeout(300)
        await d.click("#tblOrc tr:nth-child(2)"); await d.wait_for_timeout(500)
        ok("Clicar no orçamento abre a página de detalhe",
           await d.evaluate("()=>!document.getElementById('pg-orcdetalhe').classList.contains('hidden')"), "")
        ok("Abre o orçamento correto", await d.input_value("#odNomeInp")=="Ana Silva", await d.input_value("#odNomeInp"))
        ok("Campos vêm preenchidos com os valores guardados",
           (await d.input_value("#odPrecoInp"))=="100,000 Kz" and (await d.input_value("#odEntradaInp"))=="20,000 Kz", "")
        await d.fill("#odEntradaInp",""); await d.type("#odEntradaInp","40000"); await d.wait_for_timeout(300)
        ok("Resumo recalcula ao editar a entrada",
           (await d.inner_text("#odRSaldo"))=="60,000 Kz" and (await d.inner_text("#odR12"))=="5,000 Kz",
           await d.inner_text("#odRSaldo"))
        await d.fill("#odNomeInp","Ana Silva Editada")
        await d.click("#odGuardar"); await d.wait_for_timeout(500)
        ok("Guardar alterações persiste",
           await d.evaluate("()=>ORCAMENTOS.find(o=>o.id===orcAberto).nome")=="Ana Silva Editada"
           and await d.evaluate("()=>JSON.parse(localStorage.getItem('modelo_orcamentos_v1')).some(o=>o.nome==='Ana Silva Editada')"), "")
        await d.evaluate("ir('listaorc')"); await d.wait_for_timeout(300)
        ok("Lista de orçamentos mostra o valor editado", "Ana Silva Editada" in await d.inner_text("#tblOrc"), "")
        await d.evaluate("ir('clientes')"); await d.wait_for_timeout(300)
        ok("Clientes refletem a edição", "Ana Silva Editada" in await d.inner_text("#tblClientes"), "")
        await d.evaluate("abrirOrcDetalhe('o3')"); await d.wait_for_timeout(300)
        await d.fill("#odNomeInp",""); await d.click("#odGuardar"); await d.wait_for_timeout(300)
        ok("Bloqueia guardar sem nome", await d.evaluate("()=>ORCAMENTOS.find(o=>o.id==='o3').nome")=="João Mendes", "")
        await d.fill("#odNomeInp","João M."); await d.fill("#odTelInp","123")
        await d.click("#odGuardar"); await d.wait_for_timeout(300)
        ok("Bloqueia telefone incompleto", await d.evaluate("()=>ORCAMENTOS.find(o=>o.id==='o3').tel")=="934120556", "")
        await d.fill("#odTelInp","934120556"); await d.fill("#odPrecoInp","50000")
        await d.fill("#odEntradaInp","90000"); await d.wait_for_timeout(250)
        await d.click("#odGuardar"); await d.wait_for_timeout(400)
        ok("Entrada maior que o preço é limitada",
           await d.evaluate("()=>ORCAMENTOS.find(o=>o.id==='o3').entrada")==50000, "")
        await d.click("#odReenviar"); await d.wait_for_timeout(600)
        ok("Botão reenviar abre o popup com os dados",
           await d.evaluate("()=>document.getElementById('mEnviar').classList.contains('open')")
           and await d.input_value("#mNome")=="João M.", "")
        await d.click("[data-close='mEnviar']"); await d.wait_for_timeout(300)
        await d.evaluate("ir('listaorc')"); await d.wait_for_timeout(300)
        antes = await d.evaluate("()=>ORCAMENTOS.length")
        await d.evaluate("abrirOrcDetalhe('o5')"); await d.wait_for_timeout(300)
        d.once("dialog", lambda dl: asyncio.ensure_future(dl.accept()))
        await d.click("#odApagar"); await d.wait_for_timeout(600)
        ok("Apagar remove o orçamento", await d.evaluate("()=>ORCAMENTOS.length")==antes-1, "")
        ok("Sem erros de consola na página de orçamento", len(de)==0, str(de[:2]))
        await d.close()

        dmod = await b.new_page(viewport={"width":390,"height":800}, is_mobile=True, has_touch=True)
        await novo(dmod)
        await dmod.evaluate("ir('listaorc')"); await dmod.wait_for_timeout(300)
        await dmod.click("#tblOrc tr:first-child"); await dmod.wait_for_timeout(600)
        ow4 = await dmod.evaluate("()=>document.documentElement.scrollWidth - document.documentElement.clientWidth")
        ok("Mobile · orçamento abre sem overflow", ow4<=0, f"overflow = {ow4}px")
        ok("Mobile · edição utilizável",
           await dmod.locator("#odGuardar").is_visible() and await dmod.locator("#odNomeInp").is_visible(), "")
        await dmod.close()

        await b.close()

    print("\n" + "="*70)
    falhas = [r for r in R if r[0]=="FALHA"]
    print(f"TOTAL: {len(R)} testes · {len(R)-len(falhas)} passaram · {len(falhas)} falharam")
    for f in falhas: print("  ✘", f[1], "—", f[2])
    json.dump([{"r":a,"n":b,"d":c} for a,b,c in R], open('/home/user/qa/resultados.json','w'), ensure_ascii=False, indent=1)

asyncio.run(main())
