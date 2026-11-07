# -*- coding: utf-8 -*-
"""Bateria de testes ao app de orçamentos (desktop + mobile)."""
import asyncio, json, urllib.parse as up
from playwright.async_api import async_playwright

URL = "file:///home/user/index.html#rapido"   # sem contagem: testes deterministas
URL_ANIM = "file:///home/user/index.html"      # com contagem de 6 s
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
            ("Corolla 9,75M / entrada 2M", 9750000, 2000000),
            ("Entrada sugerida 10%", 9750000, 975000),
            ("Entrada = preço (100%)", 9750000, 9750000),
            ("Entrada 1 Kz", 9750000, 1),
            ("Hilux 28,5M / 6M", 28500000, 6000000),
            ("Tucson 12,9M / 12,9M", 12900000, 12900000),
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
        ok("À vista com desconto (9.750.000 − 450.000)", "9,300,000" in v, v)

        # ---------- 3. ENTRADA ACIMA DO PREÇO ----------
        await pg.fill("#oEntrada","99999999999"); await pg.wait_for_timeout(200)
        s = await pg.evaluate("()=>document.getElementById('oSaldo').textContent")
        ok("Entrada acima do preço é limitada", "0 Kz" in s, f"saldo = {s}")

        # ---------- 4. NEGATIVOS / 12x quando saldo é 0 ----------
        d = await pg.evaluate("()=>[document.getElementById('o12').textContent, document.getElementById('o24').textContent]")
        ok("Saldo 0 → parcelas 0 (sem erro)", d[0].startswith("0") and d[1].startswith("0"), str(d))

        # ---------- 5. PERSISTÊNCIA DO ORÇAMENTO ----------
        await pg.evaluate("()=>{document.getElementById('oEntrada').value='2,000,000 Kz'; calc();}")
        await pg.click("#btnEnviar"); await pg.wait_for_timeout(300)
        await pg.fill("#mNome","Cliente Teste"); await pg.fill("#mTel","923111999")
        await pg.evaluate("window.__u=null; window.open=(u)=>{window.__u=u;}")
        await pg.click("#btnZap"); await pg.wait_for_timeout(300)
        u = await pg.evaluate("window.__u")
        ok("WhatsApp abre com +244 e texto", u.startswith("https://wa.me/244923111999?text="), u.split('?')[0])
        txt = up.unquote(u.split('text=')[1])
        ok("Mensagem contém carro, entrada e parcelas",
           "Corolla" in txt and "2,000,000 Kz" in txt and "12x" in txt and "9,300,000" in txt,
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

        # ============ R31 · LOGÓTIPO COMPLETO + PALETA DA IMAGEM ============
        lg2 = await b.new_page(viewport={"width":1440,"height":900})
        lge=[]; lg2.on("pageerror", lambda e: lge.append(str(e)))
        await novo(lg2)
        LOGO = await lg2.evaluate("""()=>{
          const img=document.querySelector('.brand .logo');
          const r=img.getBoundingClientRect();
          // os 3 ticks ocupam o último terço direito da imagem
          return {ratio:+(r.width/r.height).toFixed(3), natRatio:+(img.naturalWidth/img.naturalHeight).toFixed(3),
                  completa: (img.naturalWidth/img.naturalHeight)>2.9,
                  altura:Math.round(r.height), etiqueta:img.alt};
        }""")
        ok("R31 · logótipo mostra todos os elementos (carro + nome + 3 ticks)",
           LOGO["completa"] and abs(LOGO["ratio"]-LOGO["natRatio"])<0.05, str(LOGO))
        ok("R31 · logótipo completo não é esticado", LOGO["altura"]==38, str(LOGO))
        await lg2.click("#btnTema"); await lg2.wait_for_timeout(500)
        PAL = await lg2.evaluate("""()=>{
          const cs=s=>getComputedStyle(document.querySelector(s));
          const rgb=c=>c.match(/[0-9]+/g).map(Number);
          const azul=c=>{const [r,g,b]=rgb(c); return b>r+15 && b>25 && r<60;};
          const alvos={'.brand':cs('.brand').backgroundColor,'.bar':cs('.bar').backgroundColor,
                       '.side':cs('.side').backgroundColor,'.content':cs('.content').backgroundColor,
                       '.car':cs('.car').backgroundColor,'.tbl-wrap':cs('.tbl-wrap').backgroundColor};
          const tudoAzul=Object.values(alvos).every(azul);
          // todas as superfícies idênticas à referência (4,13,31)
          const iguais=Object.values(alvos).every(c=>rgb(c).join()==='4,13,31');
          // bordas azuis visíveis nos painéis
          const b1=cs('.content').borderTopColor, b2=cs('.car').borderTopColor, b3=cs('.side').borderRightColor;
          return {alvos, tudoAzul, iguais, bordas:[b1,b2,b3],
                  bordasAzuis:[b1,b2,b3].every(c=>{const [r,g,b]=rgb(c); return b>r+15;}),
                  logoClaro:getComputedStyle(document.querySelector('.brand .logo-escuro')).display};
        }""")
        ok("R31 · modo escuro · fundo azul-marinho em todos os painéis", PAL["tudoAzul"], str(PAL["alvos"]))
        ok("R31 · modo escuro · mesmo tom da referência (#040d1f)", PAL["iguais"], str(PAL["alvos"]))
        ok("R31 · modo escuro · bordas azuis visíveis", PAL["bordasAzuis"], str(PAL["bordas"]))
        ok("R31 · modo escuro · logótipo troca para a variante clara", PAL["logoClaro"]=="block", str(PAL["logoClaro"]))
        LOGOD = await lg2.evaluate("""()=>{
          const img=document.querySelector('.brand .logo-escuro');
          const r=img.getBoundingClientRect();
          return {visivel:r.width>0, ratio:+(r.width/r.height).toFixed(2), nat:img.naturalWidth>0};
        }""")
        ok("R31 · variante escura mantém os 3 ticks e a proporção",
           LOGOD["visivel"] and LOGOD["nat"] and LOGOD["ratio"]>2.9, str(LOGOD))
        ok("R31 · logótipo/paleta sem erros de consola", len(lge)==0, str(lge[:2]))
        await lg2.close()

        # ============ R30 · BOTÃO "CRIAR" SÓ COM "+" ============
        cr = await b.new_page(viewport={"width":1440,"height":900})
        cre=[]; cr.on("pageerror", lambda e: cre.append(str(e)))
        await novo(cr)
        C = await cr.evaluate("""()=>{
          const btns=[...document.querySelectorAll('[data-criar]')];
          const vis=btns.filter(x=>x.offsetParent!==null);
          const b=vis[0], r=b.getBoundingClientRect(), svg=b.querySelector('svg');
          const chips=document.querySelector('#filtros').getBoundingClientRect();
          return {n:vis.length, texto:b.textContent.trim(), temSvg:!!svg,
                  altura:Math.round(r.height), largura:Math.round(r.width),
                  etiqueta:b.getAttribute('aria-label')||'',
                  direita:Math.round(r.right), contentDireita:Math.round(document.querySelector('.content').getBoundingClientRect().right)};
        }""")
        ok("R30 · botão Criar mostra apenas o símbolo +", C["texto"]=="" and C["temSvg"], str(C))
        ok("R30 · botão + quadrado (40×40) na linha dos filtros", C["altura"]==40 and C["largura"]==40, str(C))
        ok("R30 · botão + tem etiqueta acessível", "Criar" in C["etiqueta"], C["etiqueta"])
        ok("R30 · botão + alinhado ao canto direito", C["contentDireita"]-C["direita"]<=32, str(C))
        await cr.locator("[data-criar]:visible").click(); await cr.wait_for_timeout(600)
        abriu = await cr.evaluate("()=>document.querySelector('#mNovoModelo').classList.contains('open')")
        ok("R30 · botão + abre o popup Novo Modelo", abriu, str(abriu))
        ok("R30 · criação sem erros de consola", len(cre)==0, str(cre[:2]))
        await cr.close()

        cm = await b.new_page(viewport={"width":390,"height":844}, is_mobile=True, has_touch=True)
        cme=[]; cm.on("pageerror", lambda e: cme.append(str(e)))
        await novo(cm)
        MC = await cm.evaluate("""()=>{
          const b=[...document.querySelectorAll('[data-criar]')].filter(x=>x.offsetParent!==null)[0];
          const r=b.getBoundingClientRect();
          return {texto:b.textContent.trim(), altura:Math.round(r.height),
                  largura:Math.round(r.width), direita:Math.round(r.right),
                  semOverflow:document.documentElement.scrollWidth<=390};
        }""")
        ok("R30 · mobile · Criar também é só +", MC["texto"]=="" and MC["largura"]<=36, str(MC))
        ok("R30 · mobile · botão + com altura de toque", 30<=MC["altura"]<=40, str(MC))
        ok("R30 · mobile · sem overflow com o novo botão", MC["semOverflow"], str(MC))
        ok("R30 · mobile · sem erros de consola", len(cme)==0, str(cme[:2]))
        await cm.close()

        # ============ R30 · MODO CLARO / ESCURO ============
        tm = await b.new_page(viewport={"width":1440,"height":900})
        tme=[]; tm.on("pageerror", lambda e: tme.append(str(e)))
        await novo(tm)
        T = await tm.evaluate("""()=>{
          const b=document.getElementById('btnTema');
          const ic=[...document.querySelectorAll('.bar .ic-btn')];
          const r=b.getBoundingClientRect(), sino=ic[ic.length-1].getBoundingClientRect();
          const lua=getComputedStyle(b.querySelector('.ico-lua')).display;
          const sol=getComputedStyle(b.querySelector('.ico-sol')).display;
          return {existe:!!b, antesDoSino:Math.round(r.right)<=Math.round(sino.left),
                  lua:lua, sol:sol, tema:document.documentElement.dataset.tema||'claro',
                  titulo:b.title, pressed:b.getAttribute('aria-pressed')};
        }""")
        ok("R30 · botão de tema presente na appbar", T["existe"], str(T))
        ok("R30 · botão de tema à esquerda das notificações", T["antesDoSino"], str(T))
        ok("R30 · tema começa claro (ícone de lua)", T["lua"]=="block" and T["sol"]=="none" and T["tema"]=="claro", str(T))
        ok("R30 · botão de tema com tooltip e aria-pressed", T["titulo"]=="Modo escuro" and T["pressed"]=="false", str(T))
        await tm.click("#btnTema"); await tm.wait_for_timeout(400)
        E = await tm.evaluate("""()=>{
          const b=document.getElementById('btnTema');
          const cs=s=>getComputedStyle(document.querySelector(s));
          return {tema:document.documentElement.dataset.tema,
                  lua:getComputedStyle(b.querySelector('.ico-lua')).display,
                  sol:getComputedStyle(b.querySelector('.ico-sol')).display,
                  appbar:cs('.bar').backgroundColor, cartao:cs('.car').backgroundColor,
                  textoTitulo:cs('.page-head h2').color,
                  meta:document.querySelector('meta[name=theme-color]').content,
                  titulo:b.title, pressed:b.getAttribute('aria-pressed')};
        }""")
        ok("R30 · clique ativa o modo escuro", E["tema"]=="escuro", str(E))
        ok("R30 · ícone muda para sol no modo escuro", E["sol"]=="block" and E["lua"]=="none", str(E))
        ok("R30 · appbar e cartões ficam escuros", E["appbar"]=="rgb(4, 13, 31)" and E["cartao"]=="rgb(4, 13, 31)", str(E))
        ok("R30 · texto do título legível no escuro", E["textoTitulo"]=="rgb(255, 255, 255)", str(E))
        ok("R30 · barra do sistema acompanha o tema", E["meta"]=="#040d1f", E["meta"])
        ok("R30 · estado do botão atualizado", E["titulo"]=="Modo claro" and E["pressed"]=="true", str(E))
        Contraste = await tm.evaluate("""()=>{
          const lum=c=>{const [r,g,b]=c.match(/[0-9]+/g).map(Number).map(v=>{v/=255;return v<=.03928?v/12.92:Math.pow((v+.055)/1.055,2.4);});
            return .2126*r+.7152*g+.0722*b;};
          const pares=[['.page-head h2','.content'],['.car .nm','.car'],['.tbl td','.tbl-wrap'],['.nav','.side']];
          return pares.map(([f,bg])=>{
            const a=lum(getComputedStyle(document.querySelector(f)).color);
            const c=lum(getComputedStyle(document.querySelector(bg)).backgroundColor);
            const r=(Math.max(a,c)+.05)/(Math.min(a,c)+.05);
            return [f, +r.toFixed(2)];
          });
        }""")
        ok("R30 · contraste mínimo 3:1 no modo escuro", all(r>=3 for _, r in Contraste), str(Contraste))
        await tm.reload(); await tm.wait_for_timeout(700)
        P = await tm.evaluate("()=>({tema:document.documentElement.dataset.tema, fundo:getComputedStyle(document.querySelector('.content')).backgroundColor})")
        ok("R30 · tema escuro é memorizado após recarregar", P["tema"]=="escuro" and P["fundo"]=="rgb(4, 13, 31)", str(P))
        await tm.click("#btnTema"); await tm.wait_for_timeout(400)
        V = await tm.evaluate("()=>({tema:document.documentElement.dataset.tema||'claro', guardado:localStorage.getItem('modelo_tema_v1'), fundo:getComputedStyle(document.querySelector('.content')).backgroundColor})")
        ok("R30 · volta ao modo claro e memoriza a escolha", V["tema"]=="claro" and V["guardado"]=="claro" and V["fundo"]=="rgb(255, 255, 255)", str(V))
        ok("R30 · alternância de tema sem erros de consola", len(tme)==0, str(tme[:2]))
        await tm.close()

        tmb = await b.new_page(viewport={"width":390,"height":844}, is_mobile=True, has_touch=True)
        tbe=[]; tmb.on("pageerror", lambda e: tbe.append(str(e)))
        await novo(tmb)
        TM = await tmb.evaluate("""()=>{
          const b=document.getElementById('btnTema'), r=b.getBoundingClientRect();
          const pill=document.querySelector('#netPill').getBoundingClientRect();
          const sino=document.querySelector('.bar .ic-btn:last-of-type').getBoundingClientRect();
          const back=document.querySelector('.bar .back').getBoundingClientRect();
          return {alt:Math.round(r.height), larg:Math.round(r.width),
                  entrePillESino: r.left>=pill.right-0.5 && r.right<=sino.left+0.5,
                  tituloAinda:b.innerText===undefined?null:document.querySelector('.bar h1').getBoundingClientRect().width>0,
                  semOverflow:document.documentElement.scrollWidth<=390};
        }""")
        ok("R30 · mobile · botão de tema entre Online e o sino", TM["entrePillESino"], str(TM))
        ok("R30 · mobile · botão de tema com 34px", TM["alt"]==34 and TM["larg"]==34, str(TM))
        ok("R30 · mobile · appbar continua sem overflow", TM["semOverflow"], str(TM))
        await tmb.click("#btnTema"); await tmb.wait_for_timeout(400)
        TM2 = await tmb.evaluate("()=>({tema:document.documentElement.dataset.tema, fundo:getComputedStyle(document.querySelector('.navbar')).backgroundColor})")
        ok("R30 · mobile · modo escuro aplica-se à navbar", TM2["tema"]=="escuro" and TM2["fundo"]=="rgb(4, 13, 31)", str(TM2))
        ok("R30 · mobile · tema sem erros de consola", len(tbe)==0, str(tbe[:2]))
        await tmb.close()

        # ============ R29 · LOGÓTIPO NA APPBAR ============
        lg = await b.new_page(viewport={"width":1440,"height":900})
        le=[]; lg.on("pageerror", lambda e: le.append(str(e)))
        await novo(lg)
        L = await lg.evaluate("""()=>{
          const img=document.querySelector('.brand .logo');
          const r=img.getBoundingClientRect(), p=document.querySelector('.brand').getBoundingClientRect();
          return {existe:!!img, carregou:img.naturalWidth>0,
                  altura:Math.round(r.height), largura:Math.round(r.width),
                  proporcao:(r.width/r.height).toFixed(2),
                  semTexto:!document.querySelector('.brand b') && !document.querySelector('.brand .mark'),
                  dentro: r.top>=p.top-1 && r.bottom<=p.bottom+1 && r.left>=p.left-1,
                  titulo:document.title};
        }""")
        ok("R29 · logótipo presente na appbar", L["existe"] and L["dentro"], str(L))
        ok("R29 · logótipo carregado (sem imagem partida)", L["carregou"], str(L))
        ok("R29 · logótipo com altura harmoniosa (32–40px)", 32<=L["altura"]<=40, str(L))
        ok("R29 · logótipo na proporção original (~3:1, com os 3 ticks)", 2.9<=float(L["proporcao"])<=3.2, str(L))
        ok("R29 · nome 'Modelo' e ícone antigo removidos da marca", L["semTexto"], str(L))
        ok("R29 · título do documento menciona VendaCar", "VendaCar" in L["titulo"], L["titulo"])
        Lm = await lg.evaluate("""()=>{void ir; return 1}""")
        await lg.close()

        lm = await b.new_page(viewport={"width":390,"height":844}, is_mobile=True, has_touch=True)
        lme=[]; lm.on("pageerror", lambda e: lme.append(str(e)))
        await novo(lm)
        M = await lm.evaluate("""()=>{
          const img=document.querySelector('.brand .logo');
          const r=img.getBoundingClientRect(), h1=document.querySelector('.bar h1').getBoundingClientRect();
          const pill=document.querySelector('#netPill').getBoundingClientRect();
          return {altura:Math.round(r.height), largura:Math.round(r.width),
                  semSobreposicao: r.right<=h1.left+0.5,
                  tituloInteiro: h1.right<=pill.left+0.5,
                  semOverflow: document.documentElement.scrollWidth<=390};
        }""")
        ok("R29 · logótipo compacto no telemóvel (≤28px)", M["altura"]<=28, str(M))
        ok("R29 · título não sobrepõe o logótipo no telemóvel", M["semSobreposicao"], str(M))
        ok("R29 · título completo antes de 'Online'", M["tituloInteiro"], str(M))
        ok("R29 · appbar do telemóvel sem overflow horizontal", M["semOverflow"], str(M))
        await lm.evaluate("()=>{atual=CARROS[0]; abrirDetalhe();}"); await lm.wait_for_timeout(500)
        V = await lm.evaluate("""()=>{
          const back=document.getElementById('btnBack').getBoundingClientRect();
          return {voltar:Math.round(back.left), semLogo:getComputedStyle(document.querySelector('.brand .logo')).display==='none'};
        }""")
        ok("R29 · página interior: voltar encostado à esquerda", V["voltar"]<=14, str(V))
        ok("R29 · sem erros de consola com o novo logótipo", len(le)==0 and len(lme)==0, str((le+lme)[:2]))
        await lm.close()

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
          const back=document.getElementById('btnBack'), mark=document.querySelector('.brand .logo');
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

        # ============ VÍDEOS NO POPUP E NA FICHA ============
        vd = await b.new_page(viewport={"width":1440,"height":900})
        ve=[]; vd.on("pageerror", lambda e: ve.append(str(e)))
        await novo(vd)
        await vd.click("[data-criar]:visible"); await vd.wait_for_timeout(600)
        ok("Popup · secção de vídeos presente", await vd.locator("#fVideos").count()==1, "")
        import pathlib
        pathlib.Path("/tmp/tv1.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00"*600)
        pathlib.Path("/tmp/tv2.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x01"*600)
        pathlib.Path("/tmp/tv3.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x02"*600)
        await vd.set_input_files("#fVideos", "/tmp/tv1.mp4"); await vd.wait_for_timeout(500)
        ok("Popup · vídeo entra na lista", await vd.evaluate("()=>videos.length")==1, "")
        ok("Popup · miniatura de vídeo desenhada", await vd.locator("#videosPreview .up.video").count()==1, "")
        await vd.set_input_files("#fVideos", ["/tmp/tv2.mp4","/tmp/tv3.mp4"]); await vd.wait_for_timeout(700)
        ok("Popup · limite de 2 vídeos", await vd.evaluate("()=>videos.length")==2, "")
        await vd.evaluate("()=>document.querySelector('#videosPreview [data-delvid=\"0\"]').click()")
        await vd.wait_for_timeout(400)
        ok("Popup · remover vídeo", await vd.evaluate("()=>videos.length")==1, "")
        await vd.evaluate("""async ()=>{
          const blob=new Blob([new Uint8Array(2048)],{type:'video/mp4'});
          const url=await new Promise(r=>{const f=new FileReader();f.onload=e=>r(e.target.result);f.readAsDataURL(blob);});
          CARROS.push({id:'vid1',nome:'Toyota Video 2025',tipo:'SUV · 2025 · Preto',cat:'Novo',
                       preco:120000,desc:10000,img:CARROS[0].img,
                       fotos:[CARROS[0].img,CARROS[1].img],videos:[url]});
          guardar(); atual=CARROS[CARROS.length-1]; abrirDetalhe();
        }"""); await vd.wait_for_timeout(700)
        ok("Ficha · vídeo na mesma lista das imagens",
           await vd.locator("#thumbs .t.play-t").count()==1 and await vd.locator("#thumbs .t").count()==3,
           f"{await vd.locator('#thumbs .t').count()} miniaturas")
        await vd.evaluate("()=>document.querySelector('#thumbs .t.play-t').click()")
        await vd.wait_for_timeout(600)
        ok("Ficha · clique no vídeo abre o player", await vd.locator(".hero video").count()==1, "")
        await vd.evaluate("()=>document.querySelector(\"#thumbs .t[data-foto='1']\").click()")
        await vd.wait_for_timeout(400)
        ok("Ficha · voltar à foto fecha o player",
           await vd.locator(".hero video").count()==0 and await vd.locator("#heroImg").count()==1, "")
        await vd.evaluate("()=>{atual=CARROS[0]; abrirDetalhe();}"); await vd.wait_for_timeout(500)
        ok("Ficha · modelo sem vídeo mostra só fotos", await vd.locator("#thumbs .play-t").count()==0, "")
        ok("Vídeos · sem erros de consola", len(ve)==0, str(ve[:2]))

        # ---------- Perfil: cartões clicáveis ----------
        await vd.evaluate("()=>document.getElementById('mNovoModelo').classList.remove('open')")
        await vd.wait_for_timeout(400)
        for chave, pgid in [("estoque","pg-modelos"), ("orcs","pg-listaorc"), ("clientes","pg-clientes")]:
            await vd.evaluate("()=>ir('perfil')"); await vd.wait_for_timeout(250)
            await vd.click(f".stat-card[data-perfil='{chave}']"); await vd.wait_for_timeout(400)
            ok(f"Perfil · cartão '{chave}' abre a página respetiva",
               await vd.evaluate(f"()=>!document.getElementById('{pgid}').classList.contains('hidden')"), pgid)
        await vd.close()

        # ============ CONTADOR DOS VALORES (0 → valor) ============
        ct = await b.new_page(viewport={"width":1440,"height":900})
        ce=[]; ct.on("pageerror", lambda e: ce.append(str(e)))
        await ct.goto(URL_ANIM); await ct.wait_for_timeout(300)
        await ct.evaluate("localStorage.clear()"); await ct.reload()
        vals = await ct.evaluate("""async ()=>{
            const el=document.querySelector('#grid .pr');
            const a=[]; const t0=performance.now();
            for(let i=0;i<9;i++){ a.push([Math.round(performance.now()-t0), el.textContent]);
              await new Promise(r=>setTimeout(r,1000)); }
            return a;}""")
        nums = [float(v.replace(" Kz","").replace(",","")) for _,v in vals]
        ok("Contador · valores dos Modelos começam perto de 0", nums[0] < 1500000, vals[0][1])
        ok("Contador · a contagem sobe sem recuar", all(nums[i] <= nums[i+1] + 1 for i in range(len(nums)-1)), "")
        ok("Contador · duração de 8 s (aos 6 s ainda não acabou)", nums[6] < 9750000, vals[6][1])
        ok("Contador · termina no valor certo em ~8 s", abs(nums[-1] - 9750000) < 5000, vals[-1][1])
        await ct.wait_for_timeout(300)
        ok("Contador · valor final exato", (await ct.inner_text("#grid .pr")) == "9,750,000 Kz", await ct.inner_text("#grid .pr"))
        await ct.evaluate("()=>{atual=CARROS[0];abrirOrcamento();}"); await ct.wait_for_timeout(150)
        ok("Contador · página Orçamento também conta",
           await ct.evaluate("()=>document.getElementById('oSaldo').className.includes('contando')"), "")
        seq = await ct.evaluate("""async ()=>{const el=document.getElementById('oSaldo');const a=[];
            for(let i=0;i<4;i++){a.push(parseFloat(el.textContent.replace(" Kz","").replace(/,/g,"")));
              await new Promise(r=>setTimeout(r,900));} return a;}""")
        ok("Contador · valores do Orçamento a subir", seq[0] < seq[-1], [int(x) for x in seq])
        await ct.wait_for_timeout(8200)
        ok("Contador · Orçamento termina exato",
           (await ct.inner_text("#oPrecoN")) == "9,750,000 Kz", await ct.inner_text("#oPrecoN"))

        # rolar para fora e voltar: a contagem recomeça
        ao = await b.new_page(viewport={"width":1280,"height":900})
        await ao.goto(URL_ANIM); await ao.wait_for_timeout(400)
        await ao.evaluate("""()=>{ localStorage.clear();
            const base=CARROS[0];
            for(let i=0;i<14;i++){ CARROS.push(Object.assign({},base,{id:'x'+i,nome:'Extra '+(i+1),preco:5000000+i*100000})); }
            guardar(); }""")
        await ao.reload(); await ao.wait_for_timeout(8600)
        ok("Contador · valor estabilizado antes do scroll",
           (await ao.inner_text("#grid .pr")) == "9,750,000 Kz", await ao.inner_text("#grid .pr"))
        rec = await ao.evaluate("""async ()=>{
            const c=document.querySelector('.content'); const el=document.querySelector('#grid .pr');
            c.scrollTop = c.scrollHeight; await new Promise(r=>setTimeout(r,900));
            const saiu = el._emVista === false;
            c.scrollTop = 0; await new Promise(r=>setTimeout(r,130));
            const logo = el.textContent; await new Promise(r=>setTimeout(r,1200));
            return {saiu, logo, meio: el.textContent};}""")
        ok("Contador · ao sair de vista fica marcado", rec["saiu"] is True, "")
        ok("Contador · ao voltar recomeça do 0",
           float(rec["logo"].replace(" Kz","").replace(",","")) < 9750000, rec["logo"])
        ok("Contador · e volta a subir",
           float(rec["meio"].replace(" Kz","").replace(",","")) > float(rec["logo"].replace(" Kz","").replace(",","")),
           (rec["logo"], rec["meio"]))
        await ao.close()
        await ct.evaluate("()=>ir('listaorc')"); await ct.wait_for_timeout(200)
        ok("Contador · tabela de Orçamentos conta",
           await ct.evaluate("()=>document.querySelector('#tblOrc [data-valor]').className.includes('contando')"), "")
        await ct.evaluate("()=>ir('clientes')"); await ct.wait_for_timeout(200)
        ok("Contador · tabela de Clientes conta",
           await ct.evaluate("()=>document.querySelector('#tblClientes [data-valor]').className.includes('contando')"), "")
        await ct.evaluate("()=>{atual=CARROS[0];abrirDetalhe();}"); await ct.wait_for_timeout(200)
        ok("Contador · Detalhe do Carro conta",
           await ct.evaluate("()=>document.getElementById('sPreco').className.includes('contando')"), "")
        ok("Contador · sem erros de consola", len(ce) == 0, str(ce[:2]))
        await ct.close()

        # ============ ANIMAÇÃO DOS ÍCONES DE NAVEGAÇÃO ============
        an = await b.new_page(viewport={"width":390,"height":844})
        ae=[]; an.on("pageerror", lambda e: ae.append(str(e)))
        await novo(an)
        ok("Animação · ícone ativo está animado",
           await an.evaluate("()=>getComputedStyle(document.querySelector('.nav-item.on[data-go=\"modelos\"] .ico svg path')).animationName") == "modelosBloco", "")
        await an.click(".nav-item[data-go='perfil']"); await an.wait_for_timeout(120)
        ok("Animação · ícone 'salta' ao tocar",
           await an.evaluate("()=>document.querySelector('.nav-item[data-go=\"perfil\"]').className.includes('tap')"), "")
        await an.wait_for_timeout(700)
        ok("Animação · Perfil animado quando ativo",
           await an.evaluate("()=>getComputedStyle(document.querySelector('.nav-item.on[data-go=\"perfil\"] .ico .head')).animationName") == "perfilCabeca", "")
        mov = await an.evaluate("""async ()=>{
            const h=document.querySelector('.nav-item.on[data-go="perfil"] .ico .head');
            const xs=[];
            for(let i=0;i<8;i++){ xs.push(+h.getBoundingClientRect().left.toFixed(2));
              await new Promise(r=>setTimeout(r,140)); }
            return {min:Math.min(...xs), max:Math.max(...xs)};
        }""")
        ok("Animação · cabeça do Perfil move-se para os dois lados", (mov["max"]-mov["min"]) > 1.5, round(mov["max"]-mov["min"],2))
        await an.click(".nav-item[data-go='modelos']"); await an.wait_for_timeout(600)
        ok("Animação · 'Modelos' animado quando ativo",
           await an.evaluate("()=>getComputedStyle(document.querySelector('.nav-item.on[data-go=\"modelos\"] .ico svg path')).animationName") == "modelosBloco", "")

        # Orçamentos: linha a linha, de cima para baixo
        await an.click(".nav-item[data-go='listaorc']"); await an.wait_for_timeout(500)
        ok("Animação · folha de Orçamentos tem 3 linhas de texto",
           await an.locator(".nav-item.on[data-go='listaorc'] .ico .linha").count() == 3, "")
        ok("Animação · as linhas são escritas (escreveLinha)",
           await an.evaluate("()=>getComputedStyle(document.querySelector('.nav-item.on[data-go=\"listaorc\"] .ico .l2')).animationName") == "escreveLinha", "")
        ok("Animação · linhas escrevem-se em sequência (atraso crescente)",
           await an.evaluate("""()=>{const g=s=>parseFloat(getComputedStyle(document.querySelector('.nav-item.on[data-go="listaorc"] .ico '+s)).animationDelay);
              return g('.l1')<g('.l2') && g('.l2')<g('.l3');}"""), "")
        prog = await an.evaluate("""async ()=>{
            const l=document.querySelector('.nav-item.on[data-go="listaorc"] .ico .l1');
            const a=[]; for(let i=0;i<12;i++){a.push(parseFloat(getComputedStyle(l).strokeDashoffset)); await new Promise(r=>setTimeout(r,160));}
            return a;}""")
        ok("Animação · o traço da linha cresce (dashoffset diminui)", (max(prog)-min(prog)) > 3, (min(prog), max(prog)))

        # Clientes: os bonecos revezam-se
        await an.click(".nav-item[data-go='clientes']"); await an.wait_for_timeout(500)
        ok("Animação · boneco da frente espreita (espreitaA)",
           await an.evaluate("()=>getComputedStyle(document.querySelector('.nav-item.on[data-go=\"clientes\"] .ico .cabeca-frente')).animationName") == "espreitaA", "")
        ok("Animação · boneco de trás tem a sua própria animação (espreitaB)",
           await an.evaluate("()=>getComputedStyle(document.querySelector('.nav-item.on[data-go=\"clientes\"] .ico .cabeca-tras')).animationName") == "espreitaB", "")
        rev = await an.evaluate("""async ()=>{
            const f=document.querySelector('.nav-item.on[data-go="clientes"] .ico .cabeca-frente');
            const t=document.querySelector('.nav-item.on[data-go="clientes"] .ico .cabeca-tras');
            const sy=()=>parseFloat(getComputedStyle(f).transform.split(',')[5]||0);
            const sz=()=>parseFloat(getComputedStyle(t).transform.split(',')[5]||0);
            let frenteEscondidaComTrasVisivel=false;
            for(let i=0;i<20;i++){
               const ey=sy()>3, vz=sz()<3;
               if (ey && vz) frenteEscondidaComTrasVisivel=true;
               await new Promise(r=>setTimeout(r,110));
            }
            return frenteEscondidaComTrasVisivel;}""")
        ok("Animação · quando o da frente se esconde, o de trás aparece", rev, "")
        # ícone de Clientes fora da página: mostra a cabeça do primeiro boneco
        await an.click(".nav-item[data-go='modelos']"); await an.wait_for_timeout(600)
        estado_inativo = await an.evaluate("""()=>{
            const ty = sel => parseFloat(getComputedStyle(document.querySelector(sel)).transform.split(',')[5]||0);
            return { frente: ty('.nav-item[data-go="clientes"] .cabeca-frente'),
                     tras:   ty('.nav-item[data-go="clientes"] .cabeca-tras') };}""")
        ok("Animação · fora da página Clientes mostra a cabeça do 1.º boneco",
           abs(estado_inativo["frente"]) < 0.5, estado_inativo["frente"])
        ok("Animação · fora da página Clientes o 2.º boneco fica sem cabeça",
           estado_inativo["tras"] > 7, estado_inativo["tras"])

        rd = await b.new_context(reduced_motion="reduce")
        rp = await rd.new_page(); await rp.goto(URL); await rp.wait_for_timeout(700)
        ok("Animação · respeita 'reduzir movimento'",
           await rp.evaluate("()=>getComputedStyle(document.querySelector('.nav-item.on .ico svg')).animationName") == "none", "")
        ok("Animação · sem erros de consola", len(ae) == 0, str(ae[:2]))
        await rd.close(); await an.close()

        # ============ MIGRAÇÃO DE DADOS ANTIGOS (localStorage) ============
        mg = await b.new_context()
        mp = await mg.new_page(); me=[]
        mp.on("pageerror", lambda e: me.append(str(e)))
        await mp.goto(URL); await mp.wait_for_timeout(500)
        await mp.evaluate("""([carros,orcs])=>{
            localStorage.setItem('modelo_orcamento_carros_v1', JSON.stringify(carros));
            localStorage.setItem('modelo_orcamentos_v1', JSON.stringify(orcs));
            localStorage.removeItem('modelo_versao_dados');
        }""", [
            [{"id":"corolla","nome":"Toyota Corolla 2018","tipo":"Sedan · 2018 · Branco","cat":"Usado","preco":4500000,"desc":250000,"img":""},
             {"id":"crv","nome":"Honda CR-V 2018","tipo":"SUV · 2018 · Prata","cat":"Usado","preco":7800000,"desc":400000,"img":""},
             {"id":"hilux","nome":"Toyota Hilux 2020","tipo":"Pickup · 2020 · Branco","cat":"Novo","preco":18500000,"desc":900000,"img":""},
             {"id":"tucson","nome":"Hyundai Tucson 2019","tipo":"SUV · 2019 · Azul","cat":"Semi-usado","preco":6200000,"desc":300000,"img":""},
             {"id":"meu-carro","nome":"Kia Sportage 2024","tipo":"Novo · 2024 · Branco","cat":"Novo","preco":15000000,"desc":0,"img":""}],
            [{"id":"o1","nome":"Renato","tel":"923456789","carro":"corolla","preco":4500000,"entrada":1500000,"desc":250000,"data":1794000000000,"estado":"Enviado"},
             {"id":"user9","nome":"Cliente Real","tel":"924000111","carro":"meu-carro","preco":15000000,"entrada":3000000,"desc":0,"data":1794000000000,"estado":"Enviado"}]
        ])
        await mp.reload(); await mp.wait_for_timeout(900)
        ok("Migração · browser com dados antigos passa a mostrar preços novos",
           await mp.evaluate("()=>CARROS.find(c=>c.id==='corolla').preco") == 9750000, "")
        ok("Migração · carro do utilizador não é alterado",
           await mp.evaluate("()=>CARROS.find(c=>c.id==='meu-carro').preco") == 15000000, "")
        ok("Migração · orçamento do utilizador não é alterado",
           await mp.evaluate("()=>ORCAMENTOS.find(o=>o.id==='user9').preco") == 15000000, "")
        ok("Migração · orçamento de demonstração acompanha o catálogo",
           await mp.evaluate("()=>ORCAMENTOS.find(o=>o.id==='o1').preco") == 9750000, "")
        ok("Migração · versão de dados gravada",
           await mp.evaluate("()=>localStorage.getItem('modelo_versao_dados')") == "3", "")
        await mp.evaluate("()=>{CARROS.find(c=>c.id==='corolla').preco=8800000; guardar();}")
        await mp.reload(); await mp.wait_for_timeout(700)
        ok("Migração · não volta a correr (respeita edições seguintes)",
           await mp.evaluate("()=>CARROS.find(c=>c.id==='corolla').preco") == 8800000, "")
        ok("Migração · sem erros de consola", len(me) == 0, str(me[:2]))
        await mg.close()

        # ============ ELIMINAR MODELO (card + confirmação) ============
        dl = await b.new_page(viewport={"width":1440,"height":900})
        de=[]; dl.on("pageerror", lambda e: de.append(str(e)))
        await novo(dl)
        n0 = await dl.evaluate("()=>CARROS.length")
        ok("Card · botão eliminar em todos os modelos",
           await dl.locator("#grid [data-delcar]").count() == n0, f"{await dl.locator('#grid [data-delcar]').count()} de {n0}")
        ok("Card · botão no canto superior direito",
           await dl.evaluate("()=>{const c=document.querySelector('#grid .car'),d=c.querySelector('[data-delcar]');const a=c.getBoundingClientRect(),b=d.getBoundingClientRect();return (a.right-b.right)<16&&(b.top-a.top)<16;}"), "")
        alvo = await dl.evaluate("()=>CARROS[1].nome")
        await dl.locator("#grid [data-delcar]").nth(1).click(); await dl.wait_for_timeout(500)
        ok("Eliminar · abre popup de confirmação",
           await dl.evaluate("()=>document.getElementById('mApagarModelo').classList.contains('open')"), "")
        ok("Eliminar · popup identifica o carro", (await dl.inner_text("#apNome")) == alvo, await dl.inner_text("#apNome"))
        await dl.click("#mApagarModelo .btn.ghost"); await dl.wait_for_timeout(400)
        ok("Eliminar · cancelar mantém o modelo", await dl.evaluate("()=>CARROS.length") == n0, await dl.evaluate("()=>CARROS.length"))
        await dl.locator("#grid .car").first.click(); await dl.wait_for_timeout(400)
        ok("Card · clique normal continua a abrir o Detalhe",
           await dl.evaluate("()=>!document.getElementById('pg-detalhe').classList.contains('hidden')"), "")
        await dl.evaluate("()=>ir('modelos')"); await dl.wait_for_timeout(300)
        await dl.locator("#grid [data-delcar]").nth(1).click(); await dl.wait_for_timeout(400)
        await dl.click("#btnApagarModelo"); await dl.wait_for_timeout(600)
        ok("Eliminar · confirmar remove o modelo", await dl.evaluate("()=>CARROS.length") == n0 - 1, await dl.evaluate("()=>CARROS.length"))
        ok("Eliminar · modelo sai da grelha", alvo not in (await dl.inner_text("#grid")), alvo)
        ok("Eliminar · remoção guardada no dispositivo",
           alvo not in ((await dl.evaluate("()=>localStorage.getItem('modelo_orcamento_carros_v1')")) or ""), "")
        ok("Eliminar · popup fecha depois de apagar",
           not await dl.evaluate("()=>document.getElementById('mApagarModelo').classList.contains('open')"), "")
        ok("Eliminar · sem erros de consola", len(de) == 0, str(de[:2]))
        await dl.close()

        # ============ PREÇOS REALISTAS (Angola ≥ 3.000.000 Kz) ============
        pr = await b.new_page(viewport={"width":1440,"height":900})
        await novo(pr)
        precos = await pr.evaluate("()=>CARROS.map(c=>c.preco)")
        ok("Preços · catálogo todo ≥ 3.000.000 Kz", all(x >= 3000000 for x in precos), precos)
        orcos = await pr.evaluate("()=>ORCAMENTOS.map(o=>o.preco)")
        ok("Preços · orçamentos alinhados com o catálogo", all(x >= 3000000 for x in orcos), orcos)
        ok("Preços · catálogo com valores de mercado de Luanda",
           await pr.evaluate("()=>CARROS.map(c=>c.preco).join(',')") == "9750000,13500000,28500000,12900000",
           await pr.evaluate("()=>CARROS.map(c=>c.preco).join(',')"))
        ok("Preços · orçamentos de demonstração seguem o catálogo",
           await pr.evaluate("""()=>{const ps=CARROS.map(c=>c.preco);
              return ORCAMENTOS.filter(o=>/^o[1-5]$/.test(o.id)).every(o=>ps.includes(o.preco));}"""), "")
        ok("Preços · orçamento do utilizador nunca é reescrito",
           await pr.evaluate("""()=>{ORCAMENTOS.push({id:'user1',nome:'X',tel:'923000111',carro:'corolla',
              preco:3000000,entrada:500000,desc:0,data:Date.now(),estado:'Enviado'});
              migrarPrecos(); return ORCAMENTOS.find(o=>o.id==='user1').preco;}""") == 3000000, "")
        ok("Preços · referência de câmbio visível no Perfil",
           "Mercado de Luanda" in (await pr.evaluate("()=>document.getElementById('perfilPrecos').textContent")), "")
        ok("Preços · IVA sobre 9.750.000 = 1.365.000",
           await pr.evaluate("()=>fmt(ivaDe(9750000))") == "1,365,000 Kz", await pr.evaluate("()=>fmt(ivaDe(9750000))"))
        ok("Preços · total com IVA 9.750.000 = 11.115.000",
           await pr.evaluate("()=>fmt(totalComIva(9750000))") == "11,115,000 Kz", await pr.evaluate("()=>fmt(totalComIva(9750000))"))
        await pr.close()

        # ============ IVA 14% (imposto à parte) ============
        iv = await b.new_page(viewport={"width":1440,"height":900})
        ie=[]; iv.on("pageerror", lambda e: ie.append(str(e)))
        await novo(iv)
        await iv.evaluate("()=>{atual=CARROS.find(c=>c.id==='corolla');abrirDetalhe();}"); await iv.wait_for_timeout(400)
        ok("IVA · linha no Detalhe do Carro (9,75M → 1.365.000)",
           await iv.inner_text("#sIva") == "1,365,000 Kz", await iv.inner_text("#sIva"))
        ok("IVA · etiquetado como imposto no Detalhe",
           await iv.locator("#pg-detalhe .imposto").count() == 1, "")
        await iv.click("#btnCriarOrc"); await iv.wait_for_timeout(300)
        await iv.click("#btnSalvar"); await iv.wait_for_timeout(400)
        ok("IVA · mostrado à parte no Orçamento",
           await iv.inner_text("#oIva") == "1,365,000 Kz", await iv.inner_text("#oIva"))
        ok("IVA · total com IVA = 85.500",
           await iv.inner_text("#oTotalIva") == "11,115,000 Kz", await iv.inner_text("#oTotalIva"))
        ok("IVA · preço do carro não é inflacionado",
           await iv.inner_text("#oPrecoN") == "9,750,000 Kz", await iv.inner_text("#oPrecoN"))
        ok("IVA · parcelas calculadas sobre o preço sem IVA",
           await iv.evaluate("()=>{document.getElementById('oEntrada').value='2,000,000 Kz';calc();return document.getElementById('o12').textContent;}") == "645,833.33 Kz",
           await iv.inner_text("#o12"))
        await iv.click("#btnEnviar"); await iv.wait_for_timeout(350)
        await iv.fill("#mNome", "Renato"); await iv.fill("#mTel", "923111999")
        await iv.evaluate("window.__u=null; window.open=(u)=>{window.__u=u;}")
        await iv.click("#btnZap"); await iv.wait_for_timeout(350)
        uu = up.unquote((await iv.evaluate("window.__u")).split("text=")[1])
        ok("IVA · discriminado na mensagem do WhatsApp",
           "IVA 14%: 1,365,000 Kz" in uu and "Total com IVA: 11,115,000 Kz" in uu, uu.split(chr(10))[4])
        await iv.evaluate("()=>{const id=ORCAMENTOS[0].id; abrirOrcDetalhe(id);}"); await iv.wait_for_timeout(400)
        ok("IVA · presente no orçamento guardado",
           await iv.inner_text("#odRIva") == "1,365,000 Kz" and await iv.inner_text("#odRTotalIva") == "11,115,000 Kz",
           (await iv.inner_text("#odRIva"), await iv.inner_text("#odRTotalIva")))
        ok("IVA · visível no cartão do carro no topo do Orçamento",
           await iv.inner_text("#oIvaMini") == "1,365,000 Kz" and await iv.inner_text("#oTotalIvaMini") == "11,115,000 Kz",
           (await iv.inner_text("#oIvaMini"), await iv.inner_text("#oTotalIvaMini")))
        await iv.evaluate("()=>{atual=CARROS.find(c=>c.id==='corolla');abrirOrcamento();}"); await iv.wait_for_timeout(300)
        await iv.click("#btnEnviar"); await iv.wait_for_timeout(450)
        ok("IVA · resumo dentro do popup de envio",
           await iv.inner_text("#reIva") == "1,365,000 Kz" and await iv.inner_text("#reTotal") == "11,115,000 Kz",
           (await iv.inner_text("#reIva"), await iv.inner_text("#reTotal")))
        await iv.evaluate("()=>document.getElementById('mEnviar').classList.remove('open')")
        await iv.evaluate("()=>ir('listaorc')"); await iv.wait_for_timeout(350)
        linha_orc = await iv.evaluate("()=>{const t=document.querySelector('#tblOrc tr');return t?t.innerText:''}")
        ok("IVA · coluna na lista de Orçamentos",
           "1,365,000 Kz" in linha_orc and "11,115,000 Kz" in linha_orc, linha_orc.replace(chr(9)," | ")[-40:])
        await iv.evaluate("()=>abrirOrcDetalhe(ORCAMENTOS[0].id)"); await iv.wait_for_timeout(400)
        ok("IVA · linha de topo no detalhe do orçamento",
           await iv.inner_text("#odIvaMini") == "1,365,000 Kz" and await iv.inner_text("#odTotalMini") == "11,115,000 Kz",
           (await iv.inner_text("#odIvaMini"), await iv.inner_text("#odTotalMini")))
        ok("IVA · 14% aplicado também a 28.500.000 (Hilux)",
           await iv.evaluate("()=>fmt(ivaDe(28500000))") == "3,990,000 Kz",
           await iv.evaluate("()=>fmt(ivaDe(28500000))"))
        ok("IVA · sem erros de consola", len(ie) == 0, str(ie[:2]))
        await iv.close()

        # ============ DADOS DA LOJA (Perfil ↔ popup ↔ orçamento) ============
        lo = await b.new_page(viewport={"width":1440,"height":900})
        le=[]; lo.on("pageerror", lambda e: le.append(str(e)))
        await novo(lo)
        await lo.evaluate("()=>ir('perfil')"); await lo.wait_for_timeout(300)
        ok("Perfil · Dados da Loja começa vazio",
           "não preenchido" in await lo.inner_text("#perfilLojaDados"), await lo.inner_text("#perfilLojaDados"))
        ok("Perfil · Número do WhatsApp começa vazio",
           "não preenchido" in await lo.inner_text("#perfilLojaZap"), await lo.inner_text("#perfilLojaZap"))
        await lo.click("button.edit-mini[data-abrir-loja='dados']"); await lo.wait_for_timeout(600)
        ok("Perfil · editar abre o popup dos dados", await lo.evaluate("()=>document.getElementById('mLoja').classList.contains('open')"), "")
        await lo.fill("#lDados", "ABC Seminovos · Luanda, Angola")
        await lo.fill("#lZap", "923456789")
        ok("Perfil · máscara 9XX XXX XXX", await lo.input_value("#lZap") == "923 456 789", await lo.input_value("#lZap"))
        await lo.click("#btnGuardarLoja"); await lo.wait_for_timeout(500)
        ok("Perfil · dados guardados aparecem na linha",
           await lo.inner_text("#perfilLojaDados") == "ABC Seminovos · Luanda, Angola", await lo.inner_text("#perfilLojaDados"))
        ok("Perfil · número mostrado com +244",
           await lo.inner_text("#perfilLojaZap") == "+244 923 456 789", await lo.inner_text("#perfilLojaZap"))
        ok("Perfil · dados persistem no dispositivo",
           "ABC Seminovos" in (await lo.evaluate("()=>localStorage.getItem('modelo_loja_v1')") or ""), "")
        await lo.evaluate("()=>ir('modelos')"); await lo.wait_for_timeout(250)
        await lo.click("[data-criar]:visible"); await lo.wait_for_timeout(650)
        ok("Popup novo modelo · campos Dados da Loja e WhatsApp existem",
           await lo.locator("#fLojaDados").count() == 1 and await lo.locator("#fLojaZap").count() == 1, "")
        ok("Popup novo modelo · herda o que está no Perfil",
           await lo.input_value("#fLojaDados") == "ABC Seminovos · Luanda, Angola"
           and await lo.input_value("#fLojaZap") == "923 456 789",
           (await lo.input_value("#fLojaDados"), await lo.input_value("#fLojaZap")))
        await lo.fill("#fMarca", "Kia"); await lo.fill("#fModelo", "Sportage")
        await lo.select_option("#fAno", "2024"); await lo.select_option("#fTipo", "Novo")
        await lo.fill("#fCor", "Branco"); await lo.fill("#fPreco", "99000")
        await lo.fill("#fLojaDados", "Auto Kadumbo · Talatona"); await lo.fill("#fLojaZap", "934111222")
        await lo.click("#btnGuardarModelo"); await lo.wait_for_timeout(900)
        await lo.evaluate("()=>ir('perfil')"); await lo.wait_for_timeout(300)
        ok("Criar modelo · Perfil fica atualizado",
           await lo.inner_text("#perfilLojaDados") == "Auto Kadumbo · Talatona"
           and await lo.inner_text("#perfilLojaZap") == "+244 934 111 222",
           (await lo.inner_text("#perfilLojaDados"), await lo.inner_text("#perfilLojaZap")))
        msg = await lo.evaluate("()=>{const c=CARROS.find(x=>x.nome.indexOf('Kia')===0); return textoOrcamento('Renato', c, c.preco, 20000, c.desc);}")
        ok("Orçamento enviado · contém Dados da Loja", "Auto Kadumbo · Talatona" in msg, msg.split(chr(10))[2])
        ok("Orçamento enviado · contém WhatsApp da loja", "+244 934 111 222" in msg, msg.split(chr(10))[-1])
        vazia = await lo.evaluate("()=>{LOJA={dados:'',zap:''};guardarLoja();renderPerfilLoja();const c=CARROS[0];return textoOrcamento('Ana', c, c.preco, 10000, c.desc);}")
        ok("Loja vazia · mensagem sem assinatura", "+244" not in vazia and "aqui na loja" not in vazia, vazia.split(chr(10))[2])
        ok("Dados da Loja · sem erros de consola", len(le) == 0, str(le[:2]))
        await lo.close()

        # ============ APPBAR DESKTOP LIMPA ============
        da = await b.new_page(viewport={"width":1440,"height":860})
        dde=[]; da.on("pageerror", lambda e: dde.append(str(e)))
        await novo(da)
        gd = await da.evaluate("""()=>{
          const vis=s=>{const e=document.querySelector(s); if(!e) return 'inexistente';
            return getComputedStyle(e).display==='none'?'oculto':'visivel';};
          const bar=document.querySelector('.bar').getBoundingClientRect();
          const sino=document.querySelector('.bar .ic-btn:last-of-type').getBoundingClientRect();
          return {busca:vis('.search-top'), titulo:vis('#barTitle'), pill:vis('#netPill'),
                  sinoAFrente: sino.right > bar.left + bar.width/2,
                  utilizador: vis('.who')};
        }""")
        ok("Desktop · campo de procura removido", gd["busca"]=="inexistente", str(gd))
        ok("Desktop · nome da página fora da appbar", gd["titulo"]=="oculto", str(gd))
        ok("Desktop · modo Online fora da appbar", gd["pill"]=="oculto", str(gd))
        ok("Desktop · notificações e utilizador alinhados à direita", gd["sinoAFrente"] and gd["utilizador"] in ("visivel","flex"), str(gd))
        ok("Desktop · appbar sem erros", len(dde)==0, str(dde[:2]))
        est = await da.evaluate("""()=>{
          const c=document.querySelector('.content'), st=getComputedStyle(c);
          const card=document.querySelector('.car');
          return {fundo:st.backgroundColor, bordaTopo:st.borderTopColor, bordaEsq:st.borderLeftColor,
                  cartao:getComputedStyle(card).borderColor};
        }""")
        ok("Desktop · área de conteúdo branca", est["fundo"]=="rgb(255, 255, 255)", est["fundo"])
        ok("Desktop · moldura cinzenta no conteúdo",
           est["bordaTopo"]=="rgb(216, 222, 219)", str(est))
        ok("Desktop · cartões com borda cinzenta", est["cartao"]=="rgb(216, 222, 219)", est["cartao"])
        await da.screenshot(path="/tmp/moldura.png")
        mol = await da.evaluate("""()=>{
          const g=s=>getComputedStyle(document.querySelector(s));
          const c=g('.content'), sd=g('.side'), br=g('.brand');
          return {cTopo:c.borderTopColor, cDir:c.borderRightColor, cFundo:c.borderBottomColor,
                  sDir:sd.borderRightColor, sFundo:sd.borderBottomColor,
                  bFundo:br.borderBottomColor, bEsq:br.borderLeftWidth};
        }""")
        cinza = "rgb(216, 222, 219)"
        ok("Desktop · moldura completa (1px, cantos fechados)",
           mol["cTopo"]==cinza and mol["cDir"]==cinza and mol["cFundo"]==cinza
           and mol["sDir"]==cinza and mol["sFundo"]==cinza and mol["bFundo"]==cinza, str(mol))
        hitos = await da.evaluate("""()=>{
          const q=s=>document.querySelector(s).getBoundingClientRect();
          const c=q('.content'), sd=q('.side'), b=q('.brand'), br=q('.bar');
          return {conteudoTopo:c.top, appbarFundo:Math.max(b.bottom,br.bottom),
                  conteudoEsq:c.left, lateralDir:sd.right, fim:innerHeight, fundoConteudo:c.bottom};
        }""")
        ok("Desktop · moldura alinhada com appbar e barra lateral",
           hitos["conteudoTopo"]==hitos["appbarFundo"] and hitos["conteudoEsq"]==hitos["lateralDir"], str(hitos))
        ok("Desktop · moldura fecha no fundo do ecrã", abs(hitos["fundoConteudo"]-hitos["fim"])<=1, str(hitos))
        await da.close()

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
           (await d.input_value("#odPrecoInp"))=="13,500,000 Kz" and (await d.input_value("#odEntradaInp"))=="2,700,000 Kz", "")
        await d.fill("#odEntradaInp",""); await d.type("#odEntradaInp","4000000"); await d.wait_for_timeout(300)
        ok("Resumo recalcula ao editar a entrada",
           (await d.inner_text("#odRSaldo"))=="9,500,000 Kz" and (await d.inner_text("#odR12"))=="791,666.67 Kz",
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
