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
            # R44: as prestações são arredondadas a 1.000 Kz (nenhum vendedor envia cêntimos)
            def prest(m): return (saldo // m) // 1000 * 1000
            esperado = {
              'saldo': saldo,
              'd12': prest(12), 'd24': prest(24), 'd36': prest(36)
            }
            bate = all(abs(dados[k]-v) <= 1 for k,v in esperado.items())
            ok(f"Aritmética · {nome}", bate,
               f"saldo {dados['saldo']:,} | 12x {dados['d12']:,} (esperado {esperado['d12']:,})")

        # ---------- 2. À VISTA = preço - desconto ----------
        await pg.evaluate("()=>{atual=CARROS.find(c=>c.id==='corolla'); abrirDetalhe();}"); await pg.wait_for_timeout(250)
        await pg.click("#btnCriarOrc"); await pg.wait_for_timeout(250)
        await pg.click("#btnSalvar"); await pg.wait_for_timeout(300)
        # R65: o detalhe do carro mostra o preço do automóvel (não 0 Kz)
        ok("R65 · detalhe mostra o valor do automóvel",
           "9,750,000" in await pg.evaluate("()=>document.getElementById('dPreco').textContent"),
           await pg.evaluate("()=>document.getElementById('dPreco').textContent"))

        v = await pg.evaluate("()=>document.getElementById('oVista').textContent")
        ok("R64 · orçamento abre sem desconto — à vista = preço (9.750.000)", "9,750,000" in v, v)
        await pg.type("#oDesc","450000"); await pg.wait_for_timeout(8600)
        vd = await pg.evaluate("()=>document.getElementById('oVista').textContent")
        ok("R64 · desconto escrito no orçamento (9.750.000 − 450.000)", "9,300,000" in vd, vd)

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
        ok("R64 · mensagem contém o valor à vista negociado", "9,300,000" in txt, txt.split("\n")[-4])
        # R67: a mensagem tem de chegar ao WhatsApp sem caracteres estragados (�)
        ok("R67 \u00b7 mensagem sem emojis nem caracteres estragados",
           "\ufffd" not in txt and all(ord(ch) < 0x2100 for ch in txt), txt[:60])
        ok("R67 \u00b7 mensagem mantém os acentos do português", "or\u00e7amento" in txt and "Simula\u00e7\u00e3o" in txt, "")

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
        ok("Novo modelo mostra o motivo (aviso visível)",
           await pg.evaluate("()=>document.getElementById('avisoModelo').classList.contains('on')"),
           "aviso escondido")

        # marca input: capitalização
        await pg.fill("#fMarca","  mitsubishi   motors "); await pg.fill("#fModelo","L200")
        await pg.select_option("#fAno","2022"); await pg.select_option("#fTipo","Novo")
        await pg.type("#fPreco","30000000")
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
        # R64: o catalogo nao tem desconto --- escreve preco valido e grava
        await pg.fill("#fPreco",""); await pg.type("#fPreco","5000000")
        await pg.click("#btnGuardarModelo"); await pg.wait_for_timeout(600)
        guardado = await pg.evaluate("()=>({desc:CARROS[CARROS.length-1].desc, preco:CARROS[CARROS.length-1].preco})")
        ok("R64 · carro registado sem desconto no catalogo", guardado["desc"] == 0 and guardado["preco"] == 5000000, guardado)

        # R64: o valor a vista nasce a 0 no orcamento e nunca fica negativo
        await pg.click("#btnCriarOrc"); await pg.wait_for_timeout(300)
        ok("R64 · popup de criar orcamento ja nao pede desconto",
           await pg.evaluate("()=>!document.getElementById('mDesc')"), "")
        await pg.click("#btnSalvar"); await pg.wait_for_timeout(400)
        vista0 = await pg.evaluate("()=>document.getElementById('oVista').textContent")
        ok("R64 · orcamento comeca sem desconto (à vista = preço)",
           await pg.evaluate("()=>!document.getElementById('oDesc').value") and "5,000,000" in vista0, vista0)

        # R64: baixar o desconto atualiza TUDO no mesmo instante
        await pg.type("#oDesc","900000"); await pg.wait_for_timeout(8600)
        r64 = await pg.evaluate("""()=>({
            campo: document.getElementById('oDesc').value,
            vista: document.getElementById('oVista').textContent,
            recursivo: document.getElementById('oVistaCalc').textContent,
            linhaDesc: document.getElementById('oDescTxt').textContent,
            miniDesc: document.getElementById('oDescMini').textContent,
            saldo: document.getElementById('oSaldo').textContent,
            descontoGuardado: DESCONTO_ORC})""")
        ok("R64 · desconto escrito no campo do orcamento", "900,000" in r64["campo"], r64["campo"])
        ok("R64 · à vista passa a preço − desconto", "4,100,000" in r64["vista"], r64["vista"])
        cartao64 = await pg.evaluate("()=>document.getElementById('oPreco').textContent")
        ok("R64 · o preço em destaque no cartão acompanha (à vista)", "4,100,000" in cartao64, cartao64)
        ok("R64 · o resumo direito acompanha (à vista + desconto aplicado)",
           "4,100,000" in r64["recursivo"] and "900,000" in r64["miniDesc"], r64)
        ok("R64 · a linha do desconto aparece no resumo", "900,000" in r64["linhaDesc"], r64["linhaDesc"])
        ok("R64 · o valor negociado fica guardado para o envio", r64["descontoGuardado"] == 900000, r64["descontoGuardado"])

        # R64: mudar outra vez (o cliente pede mais) volta a atualizar tudo
        await pg.fill("#oDesc",""); await pg.type("#oDesc","1500000"); await pg.wait_for_timeout(8600)
        r64b = await pg.evaluate("""()=>({vista: document.getElementById('oVista').textContent,
            desc: DESCONTO_ORC})""")
        ok("R64 · segundo desconto recalcula outra vez", "3,500,000" in r64b["vista"] and r64b["desc"] == 1500000, r64b)

        # R64: o texto enviado por WhatsApp usa o desconto negociado
        await pg.click("#btnEnviar"); await pg.wait_for_timeout(300)
        await pg.fill("#mNome","Cliente Teste"); await pg.fill("#mTel","923456789")
        msg = await pg.evaluate("()=>mensagem()")
        ok("R64 · mensagem do WhatsApp usa o valor à vista negociado", "3,500,000" in msg, msg[-120:])
        await pg.evaluate("()=>{document.getElementById('mEnviar').classList.remove('open');ir('modelos')}")
        await pg.wait_for_timeout(300)

        # R64: o desconto alterado no detalhe do orcamento grava-se sozinho
        await pg.evaluate("ir('listaorc')"); await pg.wait_for_timeout(300)
        await pg.evaluate("()=>abrirOrcDetalhe('o2')"); await pg.wait_for_timeout(400)
        await pg.fill("#odDescInp",""); await pg.type("#odDescInp","1000000"); await pg.wait_for_timeout(8600)
        alvo64 = await pg.evaluate("""()=>{const o=ORCAMENTOS.find(x=>x.id==='o2');
            return o.preco - 1000000;}""")
        lido64 = await pg.evaluate("""()=>{const t=document.getElementById('odRVista').textContent;
            return Number(t.replace(/[^0-9.]/g,''))}""")
        ok("R64 · detalhe do orçamento recalcula o à vista",
           abs(lido64 - alvo64) < 1, f"{lido64} vs {alvo64}")
        await pg.reload(); await pg.wait_for_timeout(700)
        ok("R64 · desconto do detalhe fica gravado sem clicar em Guardar",
           await pg.evaluate("()=>ORCAMENTOS.find(o=>o.id==='o2').desc") == 1000000, "")
        await pg.evaluate("ir('modelos')"); await pg.wait_for_timeout(300)

        await pg.evaluate("ir('modelos')"); await pg.wait_for_timeout(200)
        await pg.locator("[data-criar]:visible").click(); await pg.wait_for_timeout(300)
        # fotos de teste geradas na hora (o projeto já não guarda ficheiros extra)
        import tempfile, struct, zlib
        def _foto(caminho, cor, n):
            raw=b""
            for y in range(60):
                raw += b"\x00" + bytes(cor*n if False else (cor*(n))) 
            # PNG mínimo 60x60 gerado com zlib
            def chunk(t,d):
                c=struct.pack(">I",len(d))+t+d
                return c+struct.pack(">I",zlib.crc32(t+d)&0xffffffff)
            linhas=b""
            for y in range(60):
                linhas += b"\x00" + bytes([ (cor[0]+y)%256, (cor[1]+n)%256, (cor[2]+y)%256 ])*60
            png=(b"\x89PNG\r\n\x1a\n"
                 + chunk(b"IHDR", struct.pack(">IIBBBBB",60,60,8,2,0,0,0))
                 + chunk(b"IDAT", zlib.compress(linhas))
                 + chunk(b"IEND", b""))
            open(caminho,"wb").write(png)
        tmpd = tempfile.mkdtemp()
        fotos = []
        for i,c in enumerate([(200,40,40),(40,160,80),(60,90,200),(220,170,40),(150,60,200),(30,180,180),(200,90,140)],1):
            caminho = f"{tmpd}/foto{i}.png"; _foto(caminho,c,i*20); fotos.append(caminho)
        await pg.set_input_files("#fFotos", fotos)
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
        ok("Arranque online", (await o.inner_text("#linhaOffline")).strip().startswith("Ativo"),
           await o.inner_text("#linhaOffline"))
        await ctxo.set_offline(True); await o.wait_for_timeout(600)
        ok("Offline detetado pela app", (await o.inner_text("#linhaOffline")).strip().startswith("Sem ligação"),
           await o.inner_text("#linhaOffline"))
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

        # ============ R34 · FOTO DE PERFIL NO POPUP DADOS DA LOJA ============
        import base64 as _b64
        _img = _b64.b64decode(
            "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0a"
            "HBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPDg8PDs8Ozw8PDz/wAALCAAQABABAREA/8QAFAAB"
            "AAAAAAAAAAAAAAAAAAAACf/EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AKp//2Q==")
        avpath = "/tmp/qa_avatar.jpg"
        with open(avpath, "wb") as fh: fh.write(_img)
        fp = await b.new_page(viewport={"width":1440,"height":900})
        fpe=[]; fp.on("pageerror", lambda e: fpe.append(str(e)))
        await novo(fp)
        await fp.evaluate("()=>{ir('perfil'); abrirLoja('dados');}"); await fp.wait_for_timeout(600)
        AV0 = await fp.evaluate("""()=>{
          const p=document.getElementById('lAvatarPrev'), inp=document.getElementById('lAvatarInput');
          const r=p.getBoundingClientRect();
          return {existe:!!p, visivel:r.width>0, redondo:getComputedStyle(p).borderRadius,
                  iniciais:document.getElementById('lAvatarIni').textContent.trim(),
                  input:!!inp, aceita:inp?inp.accept:'', removerEscondido:document.getElementById('lAvatarRemover').classList.contains('hidden'),
                  dentro:!!document.querySelector('#mLoja .body #lAvatarPrev')};
        }""")
        ok("R34 · popup Dados da Loja tem carregador de foto", AV0["existe"] and AV0["visivel"] and AV0["input"], str(AV0))
        ok("R34 · foto por omissão mostra as iniciais da loja", len(AV0["iniciais"])==2, str(AV0))
        ok("R34 · carregador aceita apenas imagens", AV0["aceita"]=="image/*", str(AV0))
        ok("R34 · botão Remover começa escondido", AV0["removerEscondido"], str(AV0))
        await fp.set_input_files("#lAvatarInput", avpath); await fp.wait_for_timeout(700)
        AV1 = await fp.evaluate("""()=>{
          const img=document.getElementById('lAvatarImg');
          return {previa:!img.classList.contains('hidden') && img.naturalWidth>0,
                  tmp:!!AVATAR_TMP, dados:(AVATAR_TMP||'').slice(0,22),
                  lado:img.naturalWidth, removerVisivel:!document.getElementById('lAvatarRemover').classList.contains('hidden')};
        }""")
        ok("R34 · escolher imagem mostra a pré-visualização", AV1["previa"], str(AV1))
        ok("R34 · imagem é recortada em quadrado 256px", AV1["lado"]==256 and AV1["dados"].startswith("data:image/jpeg"), str(AV1))
        ok("R34 · botão Remover aparece com foto escolhida", AV1["removerVisivel"], str(AV1))
        await fp.click("#btnGuardarLoja"); await fp.wait_for_timeout(500)
        AV2 = await fp.evaluate("""()=>{
          const av=document.querySelector('.who .av');
          const st=getComputedStyle(av);
          return {guardada:(LOJA.avatar||'').slice(0,22), noPerfil:!!(JSON.parse(localStorage.getItem('modelo_loja_v1')||'{}').avatar||''),
                  appbar:st.backgroundImage.indexOf('data:image')>=0, texto:av.textContent.trim()};
        }""")
        ok("R34 · foto é guardada e memorizada", AV2["guardada"].startswith("data:image/jpeg") and AV2["noPerfil"], str(AV2))
        ok("R34 · appbar mostra a foto de perfil", AV2["appbar"] and AV2["texto"]=="", str(AV2))
        await fp.reload(); await fp.wait_for_timeout(800)
        AV3 = await fp.evaluate("""()=>{
          const av=document.querySelector('.who .av');
          return {guardada:(LOJA.avatar||'').length>100, appbar:getComputedStyle(av).backgroundImage.indexOf('data:image')>=0};
        }""")
        ok("R34 · foto persiste depois de recarregar", AV3["guardada"] and AV3["appbar"], str(AV3))
        await fp.evaluate("()=>abrirLoja('dados')"); await fp.wait_for_timeout(500)
        await fp.click("#lAvatarRemover"); await fp.wait_for_timeout(300)
        AV4 = await fp.evaluate("""()=>{
          const img=document.getElementById('lAvatarImg');
          return {semPrevia:img.classList.contains('hidden'), iniciais:document.getElementById('lAvatarIni').textContent.trim()};
        }""")
        ok("R34 · Remover volta às iniciais", AV4["semPrevia"] and len(AV4["iniciais"])==2, str(AV4))
        await fp.click("#btnGuardarLoja"); await fp.wait_for_timeout(500)
        AV5 = await fp.evaluate("()=>({foto:LOJA.avatar, appbar:getComputedStyle(document.querySelector('.who .av')).backgroundImage})")
        ok("R34 · remover a foto limpa a appbar", AV5["foto"]=="" and AV5["appbar"]=="none", str(AV5))
        await fp.click("#btnTema"); await fp.wait_for_timeout(400)
        await fp.evaluate("()=>abrirLoja('dados')"); await fp.wait_for_timeout(500)
        AV6 = await fp.evaluate("""()=>{
          const p=document.getElementById('lAvatarPrev'); const st=getComputedStyle(p);
          return {fundo:st.backgroundColor, visivel:p.getBoundingClientRect().width>0};
        }""")
        ok("R34 · carregador visível também no modo escuro", AV6["visivel"] and AV6["fundo"]=="rgb(4, 43, 37)", str(AV6))
        ok("R34 · foto de perfil sem erros de consola", len(fpe)==0, str(fpe[:2]))
        await fp.close()

        # ============ R38 · CUMPRIMENTO EM BOLD NA APPBAR ============
        r8 = await b.new_page(viewport={"width":1440,"height":900})
        r8e=[]; r8.on("pageerror", lambda e: r8e.append(str(e)))
        await novo(r8)
        B8 = await r8.evaluate("""()=>{
          const oi=document.querySelector('.who .oi'), b=document.getElementById('whoNome');
          const co=getComputedStyle(oi), cb=getComputedStyle(b);
          const pai=getComputedStyle(document.querySelector('.who'));
          return {texto:oi.textContent.trim(), pesoOi:co.fontWeight, pesoNome:cb.fontWeight,
                  pesoBloco:pai.fontWeight, corOi:co.color, corNome:cb.color,
                  umSoTexto: oi.children.length===1 && b.textContent.trim()==='ABC Seminovos'};
        }""")
        ok("R38 · todo o cumprimento em bold", B8["pesoOi"] in ("700","bold") and B8["pesoNome"] in ("700","bold"), str(B8))
        ok("R38 · texto 'Oi <nome>' numa só linha", B8["texto"]=="Oi ABC Seminovos" and B8["umSoTexto"], str(B8))
        await r8.evaluate("()=>{LOJA.dados='123'; guardarLoja(); renderAvatarLoja();}")
        await r8.wait_for_timeout(250)
        ok("R38 · aceita nome curto de empresa (ex.: 123)",
           await r8.evaluate("()=>document.querySelector('.who .oi').textContent.trim()")=="Oi 123", "")
        await r8.click("#btnTema"); await r8.wait_for_timeout(450)
        B9 = await r8.evaluate("()=>{const o=getComputedStyle(document.querySelector('.who .oi'));return {p:o.fontWeight,c:o.color};}")
        ok("R38 · bold mantém-se no modo escuro", B9["p"] in ("700","bold") and B9["c"]=="rgb(207, 224, 245)", str(B9))
        await r8.evaluate("()=>{LOJA.dados=''; guardarLoja(); renderAvatarLoja();}")
        ok("R38 · sem erros de consola", len(r8e)==0, str(r8e[:2]))
        await r8.close()

        # ============ R37 · BARRA LATERAL SEM O CONTAINER DA LOGOMARCA ============
        sd = await b.new_page(viewport={"width":1440,"height":900})
        sde=[]; sd.on("pageerror", lambda e: sde.append(str(e)))
        await novo(sd)
        L = await sd.evaluate("""()=>{
          const side=document.querySelector('.side');
          const filhos=[...side.children];
          const ultimo=filhos[filhos.length-1];
          const navs=[...side.querySelectorAll('.nav')];
          const ultimoNav=navs[navs.length-1].getBoundingClientRect();
          const s=side.getBoundingClientRect();
          return {semStore: !document.querySelector('.side .store'),
                  semLogo: side.querySelectorAll('img').length===0,
                  semPlano: !document.body.innerText.includes('Plano Pro'),
                  ultimoFilho: ultimo.className,
                  espacoAbaixoNav: Math.round(s.bottom - ultimoNav.bottom),
                  semCaixa: [...side.children].every(e=>e.className==='side-fim' ||
                            e.className==='nav' || e.className==='nav on' || e.className==='lbl'),
                  navsVisiveis: navs.length};
        }""")
        ok("R37 · barra lateral sem o container da logomarca", L["semStore"] and L["semLogo"], str(L))
        ok("R37 · sem 'Plano Pro' no rodapé", L["semPlano"], str(L))
        ok("R54 · barra lateral termina no botão Encerrar", L["ultimoFilho"]=="side-fim" and L["navsVisiveis"]==6, str(L))
        ok("R54 · Encerrar encostado ao fundo, com espaço antes dele", L["espacoAbaixoNav"]>0 and L["semStore"] and L["semLogo"], str(L))
        await sd.click("#btnTema"); await sd.wait_for_timeout(450)
        L2 = await sd.evaluate("""()=>{
          const side=document.querySelector('.side'), s=side.getBoundingClientRect();
          const navs=[...side.querySelectorAll('.nav')];
          const u=navs[navs.length-1].getBoundingClientRect();
          return {semLogo: side.querySelectorAll('img').length===0,
                  fundo:getComputedStyle(side).backgroundColor,
                  espaco:Math.round(s.bottom-u.bottom),
                  semCaixa: !document.querySelector('.side .store') && [...side.querySelectorAll('div')].every(d=>d.className==='lbl' || d.className==='side-fim')};
        }""")
        ok("R37 · modo escuro também sem a logomarca no rodapé", L2["semLogo"] and L2["fundo"]=="rgb(4, 13, 31)", str(L2))
        ok("R54 · modo escuro mantém o Encerrar no fundo", L2["semCaixa"] and L2["espaco"]>0, str(L2))
        ok("R37 · barra lateral sem erros de consola", len(sde)==0, str(sde[:2]))
        await sd.close()

        # ============ R54 · BOTÃO ENCERRAR NO FUNDO DA BARRA LATERAL ============
        en = await b.new_page(viewport={"width":1440,"height":900})
        ene=[]; en.on("pageerror", lambda e: ene.append(str(e)))
        await novo(en)
        E1 = await en.evaluate("""()=>{
          const bt=document.querySelector('.side [data-encerrar]');
          const r=bt.getBoundingClientRect(), s=document.querySelector('.side').getBoundingClientRect();
          const navs=[...document.querySelectorAll('.side .nav')].map(n=>n.getBoundingClientRect().bottom);
          return {texto:bt.innerText.trim(), titulo:bt.getAttribute('title'),
                  existe:!!bt, eUltimoNav: [...document.querySelectorAll('.side .nav')].pop()===bt,
                  fundo: Math.round(s.bottom-r.bottom), altura:Math.round(r.height), largura:Math.round(r.width),
                  abaixoDosOutros: r.top >= Math.max(...navs.slice(0,-1)),
                  cor:getComputedStyle(bt).color,
                  alturaNav:Math.round(document.querySelector('.side .nav[data-go=\"perfil\"]').getBoundingClientRect().height)};
        }""")
        ok("R54 · botão Encerrar existe no fundo da barra lateral", E1["existe"] and E1["texto"]=="Encerrar" and E1["titulo"]=="Encerrar", str(E1))
        ok("R54 · é o último item, abaixo de Perfil, colado ao fundo", E1["eUltimoNav"] and E1["abaixoDosOutros"] and 0 <= E1["fundo"] <= 40, str(E1))
        ok("R54 · mesma altura e largura dos restantes itens", E1["altura"]==E1["alturaNav"] and E1["largura"]>200, str(E1))
        await en.click(".side [data-encerrar]"); await en.wait_for_timeout(500)
        E2 = await en.evaluate("""()=>{
          const m=document.getElementById('mEncerrar');
          return {aberto:m.classList.contains('open'), titulo:document.getElementById('ttEncerrar').innerText,
                  botao:document.getElementById('btnEncerrarOk').innerText.trim(),
                  centrado: Math.abs((m.querySelector('.modal').getBoundingClientRect().left +
                            m.querySelector('.modal').getBoundingClientRect().right)/2 - innerWidth/2) < 3};
        }""")
        ok("R54 · clicar abre confirmação centrada antes de encerrar", E2["aberto"] and E2["centrado"] and E2["botao"]=="Encerrar", str(E2))
        await en.click("#mEncerrar .btn.ghost"); await en.wait_for_timeout(400)
        ok("R54 · Cancelar não encerra nada", await en.evaluate("()=>!document.getElementById('mEncerrar').classList.contains('open') && !document.querySelector('.ecra-fim')"))
        await en.click(".side [data-encerrar]"); await en.wait_for_timeout(300)
        await en.click("#btnEncerrarOk"); await en.wait_for_timeout(700)
        E3 = await en.evaluate("""()=>{
          const f=document.querySelector('.ecra-fim');
          return {ecra:!!f, texto:f?f.innerText.split(String.fromCharCode(10)).join(' | '):'', visivel:f?getComputedStyle(f).opacity:'0',
                  guardado: !!localStorage.getItem('modelo_orcamento_carros_v1')};
        }""")
        ok("R54 · encerrar mostra o ecrã de encerramento", E3["ecra"] and E3["visivel"]=="1" and "Aplica" in E3["texto"], str(E3))
        ok("R54 · dados ficam guardados ao encerrar", E3["guardado"], str(E3))
        await en.click("#btnReabrir"); await en.wait_for_timeout(1500)
        E4 = await en.evaluate("()=>({ok:window.__arranqueOK, n:document.querySelectorAll('#grid .car').length, fim:!!document.querySelector('.ecra-fim')})")
        ok("R54 · Abrir novamente repõe a app", E4["ok"] and E4["n"]==4 and not E4["fim"], str(E4))
        ok("R54 · sem erros de consola no fluxo Encerrar", len(ene)==0, str(ene[:2]))
        await en.close()
        em = await b.new_page(viewport={"width":390,"height":844})
        await novo(em)
        ok("R54 · Encerrar não aparece no telemóvel (barra lateral escondida)",
           not await em.evaluate("()=>{const e=document.querySelector('[data-encerrar]');return !!e.offsetParent}"))
        await em.close()

        # ============ R32 · MODO ESCURO · ATIVO A VERDE ============
        nv = await b.new_page(viewport={"width":1440,"height":900})
        nve=[]; nv.on("pageerror", lambda e: nve.append(str(e)))
        await novo(nv)
        await nv.click("#btnTema"); await nv.wait_for_timeout(450)
        N1 = await nv.evaluate("""()=>{
          const cs=s=>getComputedStyle(document.querySelector(s));
          const rgb=c=>c.match(/[0-9]+/g).map(Number);
          const verde=c=>{const [r,g,b]=rgb(c); return g>150 && g>r+60 && g>b+30;};
          return {ativoTexto:cs('.side .nav.on').color, ativoIcone:cs('.side .nav.on .ico svg').color,
                  inativoTexto:cs('.side .nav:not(.on)').color,
                  ativoVerde:verde(cs('.side .nav.on').color) && verde(cs('.side .nav.on .ico svg').color),
                  inativoNao:!verde(cs('.side .nav:not(.on)').color)};
        }""")
        ok("R32 · escuro · nome da página ativa a verde", N1["ativoVerde"] and N1["inativoNao"], str(N1))
        await nv.evaluate("()=>ir('clientes')"); await nv.wait_for_timeout(500)
        N2 = await nv.evaluate("""()=>{
          const item=[...document.querySelectorAll('.side .nav.on')];
          const rgb=c=>c.match(/[0-9]+/g).map(Number);
          const verde=c=>{const [r,g,b]=rgb(c); return g>150 && g>r+60 && g>b+30;};
          return {nome:item.length?item[0].textContent.trim():'', verde:item.length?verde(getComputedStyle(item[0]).color):false,
                  so1:document.querySelectorAll('.side .nav.on').length};
        }""")
        ok("R32 · escuro · o verde acompanha a página aberta", N2["nome"].startswith("Clientes") and N2["verde"] and N2["so1"]==1, str(N2))
        await nv.reload(); await nv.wait_for_timeout(600)
        N3 = await nv.evaluate("""()=>{
          const it=document.querySelector('.side .nav.on');
          const rgb=c=>c.match(/[0-9]+/g).map(Number);
          const c=getComputedStyle(it).color; const [r,g,b]=rgb(c);
          return {tema:document.documentElement.dataset.tema, verde:g>150&&g>r+60&&g>b+30, cor:c};
        }""")
        ok("R32 · escuro memorizado mantém o ativo a verde", N3["tema"]=="escuro" and N3["verde"], str(N3))
        ok("R32 · ativo a verde sem erros de consola", len(nve)==0, str(nve[:2]))
        await nv.close()

        nm2 = await b.new_page(viewport={"width":390,"height":844}, is_mobile=True, has_touch=True)
        nme=[]; nm2.on("pageerror", lambda e: nme.append(str(e)))
        await novo(nm2)
        await nm2.click("#btnTema"); await nm2.wait_for_timeout(450)
        M1 = await nm2.evaluate("""()=>{
          const on=document.querySelector('.navbar .nav-item.on');
          const off=document.querySelector('.navbar .nav-item:not(.on)');
          const rgb=c=>c.match(/[0-9]+/g).map(Number);
          const verde=c=>{const [r,g,b]=rgb(c); return g>150 && g>r+60 && g>b+30;};
          return {nome:on.textContent.trim(), texto:verde(getComputedStyle(on).color),
                  icone:verde(getComputedStyle(on.querySelector('.ico svg')).color),
                  inativo:!verde(getComputedStyle(off).color)};
        }""")
        ok("R32 · mobile escuro · ícone e nome ativos a verde", M1["texto"] and M1["icone"] and M1["inativo"], str(M1))
        await nm2.evaluate("()=>ir('perfil')"); await nm2.wait_for_timeout(500)
        M2 = await nm2.evaluate("""()=>{
          const on=document.querySelector('.navbar .nav-item.on');
          const rgb=c=>c.match(/[0-9]+/g).map(Number);
          const [r,g,b]=rgb(getComputedStyle(on).color);
          return {nome:on.textContent.trim(), verde:g>150&&g>r+60&&g>b+30};
        }""")
        ok("R32 · mobile escuro · verde segue a página (Perfil)", M2["nome"].startswith("Perfil") and M2["verde"], str(M2))
        ok("R32 · mobile escuro sem erros de consola", len(nme)==0, str(nme[:2]))
        await nm2.close()

        # no modo claro continua igual
        cl = await b.new_page(viewport={"width":1440,"height":900})
        await novo(cl)
        C0 = await cl.evaluate("""()=>{
          const on=document.querySelector('.side .nav.on');
          const rgb=c=>c.match(/[0-9]+/g).map(Number);
          const [r,g,b]=rgb(getComputedStyle(on).color);
          return {cor:getComputedStyle(on).color, verde:g>r+40&&g>b+20};
        }""")
        ok("R32 · modo claro mantém o verde do item ativo", C0["verde"], str(C0))
        await cl.close()

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
                  logoClaro:document.querySelectorAll('.brand .logo').length===1
                            ? getComputedStyle(document.querySelector('.brand .logo')).display : 'x'};
        }""")
        ok("R31 · modo escuro · fundo azul-marinho em todos os painéis", PAL["tudoAzul"], str(PAL["alvos"]))
        ok("R31 · modo escuro · mesmo tom da referência (#040d1f)", PAL["iguais"], str(PAL["alvos"]))
        ok("R31 · modo escuro · bordas azuis visíveis", PAL["bordasAzuis"], str(PAL["bordas"]))
        ok("R58 · modo escuro · um único logótipo, sempre visível", PAL["logoClaro"]=="block", str(PAL["logoClaro"]))
        LOGOD = await lg2.evaluate("""()=>{
          const imgs=[...document.querySelectorAll('.brand img')];
          const img=imgs[0], r=img.getBoundingClientRect();
          return {quantos:imgs.length, visivel:r.width>0, ratio:+(r.width/r.height).toFixed(2),
                  nat:img.naturalWidth>0, mostra:getComputedStyle(img).display!=='none'};
        }""")
        ok("R58 · um só logótipo no modo escuro, com a proporção certa",
           LOGOD["quantos"]==1 and LOGOD["visivel"] and LOGOD["nat"] and LOGOD["mostra"]
           and LOGOD["ratio"]>2.9, str(LOGOD))
        ok("R31 · logótipo/paleta sem erros de consola", len(lge)==0, str(lge[:2]))
        await lg2.close()

        # ============ R62 · TITULO DA PAGINA NA APPBAR (desktop + tablet) ============
        for larg,etiq in ((1440,"desktop"),(1000,"tablet")):
            r62 = await b.new_page(viewport={"width":larg,"height":860})
            r62e=[]; r62.on("pageerror", lambda e: r62e.append(str(e)))
            await novo(r62)
            for pag in ["modelos","listaorc","vendas","clientes","perfil"]:
                await r62.evaluate(f"()=>ir('{pag}')"); await r62.wait_for_timeout(420)
                T62 = await r62.evaluate("""()=>{
                  const t=document.getElementById('barTitle'), s=document.getElementById('barSub');
                  const bar=document.querySelector('.bar').getBoundingClientRect();
                  const tr=t.getBoundingClientRect();
                  const sec=document.querySelector('.content section:not(.hidden)');
                  return {titulo:t.innerText, sub:s?s.innerText:'',
                          dentro: tr.top>=bar.top-1 && tr.bottom<=bar.bottom+1 && tr.left>=bar.left,
                          h2: [...sec.querySelectorAll('h2')].filter(e=>e.offsetParent).length,
                          subNoConteudo: [...sec.querySelectorAll('.page-head .sub')].filter(e=>e.offsetParent).length};
                }""")
                ok(f"R62 · {etiq} · «{pag}» com título dentro da appbar",
                   T62["dentro"] and len(T62["titulo"])>0, str(T62))
                ok(f"R62 · {etiq} · subtítulo na appbar e fora do conteúdo",
                   len(T62["sub"])>0 and T62["subNoConteudo"]==0, str(T62))
                ok(f"R62 · {etiq} · nenhum título repetido no conteúdo", T62["h2"]==0, str(T62["h2"]))
            ok(f"R62 · {etiq} · sem erros de consola", len(r62e)==0, str(r62e[:2]))
            await r62.close()

        # ============ R61 · ICONE VENDAS = shopping-cart-plus (Lucide) ============
        r61 = await b.new_page(viewport={"width":1440,"height":900})
        r61e=[]; r61.on("pageerror", lambda e: r61e.append(str(e)))
        await novo(r61)
        await r61.evaluate("()=>ir('vendas')"); await r61.wait_for_timeout(700)
        C61 = await r61.evaluate("""()=>{
          const side=document.querySelector('.side .nav[data-go="vendas"] .ico svg');
          const nav=document.querySelector('.navbar .nav-item[data-go="vendas"] .ico svg');
          const info=s=>s?{circ:s.querySelectorAll('circle').length, paths:s.querySelectorAll('path').length,
                           mais:!!s.querySelector('.mais'), carrinho:!!s.querySelector('path[stroke-dasharray]')||s.querySelectorAll('path').length===2}
                          :null;
          return {side:info(side), nav:info(nav),
                  texto:document.querySelector('.side .nav[data-go="vendas"] .tx').innerText.trim(),
                  contador:document.querySelector('.side .nav[data-go="vendas"] .cnt').innerText.trim(),
                  anim:getComputedStyle(side.querySelector('.mais')).animationName,
                  funilAntigo:!!document.querySelector('.side [data-go="vendas"] path[d^="M3 4h18"]')};
        }""")
        ok("R61 · barra lateral usa o carrinho com "+" (2 rodas + sinal)",
           C61["side"]["circ"]==2 and C61["side"]["mais"], str(C61["side"]))
        ok("R61 · mesma troca na navbar do telemóvel",
           C61["nav"]["circ"]==2 and C61["nav"]["mais"], str(C61["nav"]))
        ok("R61 · o funil antigo desapareceu do menu", not C61["funilAntigo"], str(C61["funilAntigo"]))
        ok("R61 · nome e contador intactos", C61["texto"]=="Vendas" and C61["contador"]!="", str(C61))
        ok("R61 · só o "+" anima (carrinhoMais)", C61["anim"]=="carrinhoMais", str(C61["anim"]))
        Z61 = await r61.evaluate("""async ()=>{
          const m=document.querySelector('.side .nav[data-go="vendas"] .ico svg .mais');
          const v=[]; for(let i=0;i<10;i++){ v.push(getComputedStyle(m).transform);
            await new Promise(r=>setTimeout(r,120)); }
          return [...new Set(v)].length;
        }""")
        ok("R61 · o "+" pulsa mesmo (transform a variar)", Z61>=4, str(Z61))
        ok("R61 · sem erros de consola", len(r61e)==0, str(r61e[:2]))
        await r61.close()

        # ============ R60 · ANIMACAO DO AUTOMOVEL EM MOVIMENTO ============
        r60 = await b.new_page(viewport={"width":1440,"height":900})
        r60e=[]; r60.on("pageerror", lambda e: r60e.append(str(e)))
        await novo(r60)
        A60 = await r60.evaluate("""()=>{
          const svg=document.querySelector('.side .nav[data-go="modelos"] .ico svg');
          const est=svg.querySelector('.estrada');
          return {anim:getComputedStyle(svg).animationName, dur:getComputedStyle(svg).animationDuration,
                  estrada:!!est, opacidade:est?+getComputedStyle(est).opacity:1,
                  rodas:svg.querySelectorAll('circle').length,
                  viewBox:svg.getAttribute('viewBox')};
        }""")
        ok("R60 · com a página aberta o carro põe-se a andar",
           A60["anim"]=="carroAnda" and A60["dur"]=="1.8s", str(A60))
        ok("R60 · estrada discreta por baixo (opacidade < .5)", A60["estrada"] and A60["opacidade"]<0.5, str(A60))
        ok("R60 · desenho do carro inteiro no viewBox (sem corte)", A60["viewBox"]=="1.6 5.4 20.8 14.9", str(A60["viewBox"]))
        MOV = await r60.evaluate("""async ()=>{
          const svg=document.querySelector('.side .nav[data-go="modelos"] .ico svg');
          const est=svg.querySelector('.estrada');
          const xs=[], ds=[];
          for(let i=0;i<12;i++){
            xs.push(+svg.getBoundingClientRect().x.toFixed(2));
            ds.push(getComputedStyle(est).strokeDashoffset);
            await new Promise(r=>setTimeout(r,90));
          }
          return {dx:+(Math.max(...xs)-Math.min(...xs)).toFixed(2), offsets:[...new Set(ds)].length};
        }""")
        ok("R60 · o carro desloca-se de facto (≈1 px, ida e volta)", MOV["dx"]>=0.6, str(MOV))
        ok("R60 · a estrada tracejada está em movimento", MOV["offsets"]>=4, str(MOV))
        # noutra pagina o carro fica parado
        await r60.evaluate("()=>ir('clientes')"); await r60.wait_for_timeout(500)
        P60 = await r60.evaluate("""()=>{const svg=document.querySelector('.side .nav[data-go="modelos"] .ico svg');
            return getComputedStyle(svg).animationName;}""")
        ok("R60 · fora da página o carro não anda", P60=="none", P60)
        ok("R60 · sem erros de consola", len(r60e)==0, str(r60e[:2]))
        await r60.close()

        # ============ R59 · "MODELOS" PASSA A "AUTOMÓVEL" ============
        r59 = await b.new_page(viewport={"width":1440,"height":900})
        r59e=[]; r59.on("pageerror", lambda e: r59e.append(str(e)))
        await novo(r59)
        N59 = await r59.evaluate("""()=>{
          const nav=document.querySelector('.side .nav[data-go="modelos"]');
          const it={txt:nav.querySelector('.tx').innerText.trim(),
                    iconeCarro:nav.querySelectorAll('.ico svg circle').length===2,
                    temContador:nav.querySelector('.cnt').innerText.trim().length>0,
                    go:nav.dataset.go};
          return {it, titulo:document.getElementById('barSub').innerText ? document.getElementById('barTitle').innerText : '',
                  appbar:document.getElementById('barTitle').innerText,
                  pagina:TITLES.modelos[0],
                  menu:[...document.querySelectorAll('.side .nav .tx')].map(e=>e.innerText.trim()),
                  sobraTexto:document.getElementById('pg-modelos').innerText.includes('Modelos'),
                  voltar:[...document.querySelectorAll('[data-go="modelos"].btn')].map(b=>b.innerText.trim())};
        }""")
        ok("R59 · barra lateral diz «Automóvel»", N59["it"]["txt"]=="Automóvel", str(N59["it"]))
        ok("R59 · novo ícone é um carro (2 rodas)", N59["it"]["iconeCarro"], str(N59["it"]))
        ok("R59 · contador mantém-se no item", N59["it"]["temContador"], str(N59["it"]))
        ok("R59 · título da página, appbar e TITLES dizem «Automóvel»",
           N59["titulo"]=="Automóvel" and N59["appbar"]=="Automóvel" and N59["pagina"]=="Automóvel", str(N59))
        ok("R59 · menu completo na ordem certa",
           N59["menu"]==["Automóvel","Orçamentos","Vendas","Clientes","Perfil","Encerrar"], str(N59["menu"]))
        ok("R59 · nenhum «Modelos» esquecido na página", not N59["sobraTexto"], str(N59["sobraTexto"]))
        ok("R59 · botões «Voltar aos Automóveis»",
           len(N59["voltar"])>0 and all(v=="Voltar aos Automóveis" for v in N59["voltar"]), str(N59["voltar"]))
        M59 = await r59.evaluate("""()=>{const it=document.querySelector('.navbar .nav-item[data-go="modelos"]');
            return {texto:it.innerText.trim(), icone:it.querySelectorAll('svg circle').length===2,
                    cabe:it.scrollWidth<=it.clientWidth+2};}""")
        ok("R59 · no telemóvel também «Automóvel», com o carro e sem corte",
           M59["texto"]=="Automóvel" and M59["icone"] and M59["cabe"], str(M59))
        ok("R59 · sem erros de consola", len(r59e)==0, str(r59e[:2]))
        await r59.close()

        # ============ R58 · IMAGENS NO CÓDIGO (sem duplicados) ============
        r58 = await b.new_page(viewport={"width":1440,"height":900})
        r58e=[]; r58.on("pageerror", lambda e: r58e.append(str(e)))
        await novo(r58)
        IM = await r58.evaluate("""()=>{
          const srcs=[...document.images].map(i=>i.getAttribute('src')||'').filter(s=>s.startsWith('data:image'));
          const todas=[...document.querySelectorAll('img')].map(i=>i.getAttribute('src')||'');
          /* o mesmo carro aparece em varios sitios: conta so as imagens distintas */
          const reais=todas.filter(u=>u && u.startsWith('data:image'));
          const unicas=[...new Set(reais)];
          const logo=unicas.filter(u=>u.length>60000);
          return {imgs:document.querySelectorAll('.brand img').length,
                  dataUris:unicas.length, duplicadas:reais.length-unicas.length,
                  fotosDeCarro:reais.filter(u=>u.startsWith('data:image/jpeg')).length / Math.max(1, unicas.filter(u=>u.startsWith('data:image/jpeg')).length),
                  logotiposDistintos:logo.length,
                  logoEscuro:!!document.querySelector('.logo-escuro')};
        }""")
        ok("R58 · um só logótipo no código (sem a variante escura sem uso)",
           IM["imgs"]==1 and not IM["logoEscuro"], str(IM))
        ok("R58 · um único logótipo embebido (fotos não se repetem no código)",
           IM["logotiposDistintos"]==1 and IM["dataUris"]==5, str(IM))
        ok("R58 · sem erros de consola", len(r58e)==0, str(r58e[:2]))
        await r58.close()

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
          const r=b.getBoundingClientRect(), qu=document.getElementById('whoBtn').getBoundingClientRect();
          const lua=getComputedStyle(b.querySelector('.ico-lua')).display;
          const sol=getComputedStyle(b.querySelector('.ico-sol')).display;
          return {existe:!!b, antesDoSino:Math.round(r.right)<=Math.round(qu.left),
                  lua:lua, sol:sol, tema:document.documentElement.dataset.tema||'claro',
                  titulo:b.title, pressed:b.getAttribute('aria-pressed')};
        }""")
        ok("R30 · botão de tema presente na appbar", T["existe"], str(T))
        ok("R35 · botão de tema à esquerda da foto de perfil", T["antesDoSino"], str(T))
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
                  textoTitulo:cs('#barTitle').color,
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
          const pares=[['#barTitle','.bar'],['.car .nm','.car'],['.tbl td','.tbl-wrap'],['.nav','.side']];
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
          const sino=document.getElementById('whoBtn').getBoundingClientRect();
          const back=document.querySelector('.bar .back').getBoundingClientRect();
          const tit=document.querySelector('.bar h1').getBoundingClientRect();
          return {alt:Math.round(r.height), larg:Math.round(r.width),
                  entrePillESino: r.left>=tit.right-0.5 && r.right<=sino.left+0.5,
                  tituloAinda:b.innerText===undefined?null:document.querySelector('.bar h1').getBoundingClientRect().width>0,
                  semOverflow:document.documentElement.scrollWidth<=390};
        }""")
        ok("R36 · mobile · botão de tema entre o título e a foto de perfil", TM["entrePillESino"], str(TM))
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
          const quem=document.querySelector('.bar-acoes').getBoundingClientRect();
          return {altura:Math.round(r.height), largura:Math.round(r.width),
                  semSobreposicao: r.right<=h1.left+0.5,
                  tituloInteiro: h1.right<=quem.left+0.5,
                  semOverflow: document.documentElement.scrollWidth<=390};
        }""")
        ok("R29 · logótipo compacto no telemóvel (≤28px)", M["altura"]<=28, str(M))
        ok("R29 · título não sobrepõe o logótipo no telemóvel", M["semSobreposicao"], str(M))
        ok("R29 · título completo antes das ações da appbar", M["tituloInteiro"], str(M))
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
          const brand=q('.brand'), pill=q('.bar-acoes'), sino=q('#whoBtn'), cont=q('.content');
          return {appbar:Math.round(brand.height), topoConteudo:Math.round(cont.top),
                  barraExtra:Math.round(q('.bar').top),
                  pillDentro: pill.top>=brand.top && pill.bottom<=brand.bottom,
                  sinoDentro: sino.top>=brand.top && sino.bottom<=brand.bottom};
        }""")
        ok("Mobile · appbar única (sem barra extra)", g["appbar"]==58 and g["topoConteudo"]==58 and g["barraExtra"]==0, str(g))
        ok("R36 · mobile · ações da appbar dentro da barra", g["pillDentro"], str(g))
        ok("R35 · mobile · foto de perfil no lugar das notificações", g["sinoDentro"], str(g))
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
           await an.evaluate("()=>getComputedStyle(document.querySelector('.nav-item.on[data-go=\"modelos\"] .ico svg\')).animationName") == "carroAnda", "")
        await an.click(".nav-item[data-go='perfil']"); await an.wait_for_timeout(120)
        ok("Animação · ícone 'salta' ao tocar",
           await an.evaluate("()=>document.querySelector('.nav-item[data-go=\"perfil\"]').className.includes('tap')"), "")
        await an.wait_for_timeout(700)
        ok("R63 · Perfil animado quando ativo (acena + anel)",
           await an.evaluate("()=>{const g=s=>getComputedStyle(document.querySelector('.nav-item.on[data-go=\"perfil\"] '+s)).animationName;"
                             "return g('.todo')+'|'+g('.head')+'|'+g('.halo')+'|'+g('.ombros')}") == "perfilAcena|perfilCabeca|perfilHalo|perfilOmbros", "")
        mov = await an.evaluate("""async ()=>{
            const mat = e => {const t=getComputedStyle(e).transform;
              return t==='none' ? new DOMMatrix() : new DOMMatrix(t);};
            const h=document.querySelector('.nav-item.on[data-go="perfil"] .ico .head');
            const t=document.querySelector('.nav-item.on[data-go="perfil"] .ico .todo');
            const ho=document.querySelector('.nav-item.on[data-go="perfil"] .ico .halo');
            const sx=[], rot=[], op=[];
            for(let i=0;i<40;i++){
              sx.push(Math.hypot(mat(h).a, mat(h).b));
              rot.push(mat(t).b);
              op.push(+(getComputedStyle(ho).opacity||0));
              await new Promise(r=>setTimeout(r,60));
            }
            return {escala:Math.max(...sx)-Math.min(...sx), rot:Math.max(...rot)-Math.min(...rot),
                    halo:Math.max(...op)};
        }""")
        ok("R63 · cabeça do Perfil cresce (escala >= 0.15)", mov["escala"] >= 0.15, round(mov["escala"],3))
        ok("R63 · o Perfil inclina para os dois lados", mov["rot"] > 0.06, round(mov["rot"],3))
        ok("R63 · o anel do Perfil fica visível (opac. >= 0.5)", mov["halo"] >= 0.5, round(mov["halo"],3))
        await an.click(".nav-item[data-go='modelos']"); await an.wait_for_timeout(600)
        ok("Animação · 'Automóvel' animado quando ativo",
           await an.evaluate("()=>getComputedStyle(document.querySelector('.nav-item.on[data-go=\"modelos\"] .ico svg\')).animationName") == "carroAnda", "")

        rodas = await an.evaluate("""()=>{const svg=document.querySelector('.nav-item.on[data-go="modelos"] .ico svg');
            const est=svg.querySelector('.estrada');
            return {rodas:svg.querySelectorAll('circle').length,
                    anim:getComputedStyle(svg).animationName,
                    estrada:!!est, estradaAnim:est?getComputedStyle(est).animationName:''};}""")
        ok("R60 · ícone Automóvel tem duas rodas e estrada",
           rodas["rodas"]==2 and rodas["estrada"], str(rodas))
        ok("R60 · o carro anda (carroAnda) e a estrada passa (estradaPassa)",
           rodas["anim"]=="carroAnda" and rodas["estradaAnim"]=="estradaPassa", str(rodas))

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
        ok("R63 · boneco da frente cede lugar (cabecaFrente)",
           await an.evaluate("()=>getComputedStyle(document.querySelector('.nav-item.on[data-go=\"clientes\"] .ico .cabeca-frente')).animationName") == "cabecaFrente", "")
        ok("R63 · boneco de trás entra em cena (cabecaTras) e o par balança (parAcena)",
           await an.evaluate("()=>getComputedStyle(document.querySelector('.nav-item.on[data-go=\"clientes\"] .ico .cabeca-tras')).animationName"
                             "+'|'+getComputedStyle(document.querySelector('.nav-item.on[data-go=\"clientes\"] .ico .par')).animationName") == "cabecaTras|parAcena", "")
        rev = await an.evaluate("""async ()=>{
            const mat = e => {const t=getComputedStyle(e).transform;
              return t==='none' ? new DOMMatrix() : new DOMMatrix(t);};
            const f=document.querySelector('.nav-item.on[data-go="clientes"] .ico .cabeca-frente');
            const t=document.querySelector('.nav-item.on[data-go="clientes"] .ico .cabeca-tras');
            let opTras=0, escFrente=1, trasEntra=false;
            for(let i=0;i<26;i++){
               const ot=+getComputedStyle(t).opacity;
               const ef=Math.hypot(mat(f).a, mat(f).b);
               opTras=Math.max(opTras,ot); escFrente=Math.min(escFrente,ef);
               if (ot>0.9 && ef<0.97) trasEntra=true;
               await new Promise(r=>setTimeout(r,100));
            }
            return {opTras, escFrente, trasEntra};}""")
        ok("R63 · a 2.ª cabeça chega a aparecer por completo", rev["opTras"] > 0.9, round(rev["opTras"],2))
        ok("R63 · a cabeça da frente encolhe para lhe dar lugar", rev["escFrente"] < 0.95, round(rev["escFrente"],3))
        ok("R63 · as duas cabeças revezam-se (entra uma, cede a outra)", rev["trasEntra"], str(rev))
        # ícone de Clientes fora da página: mostra a cabeça do primeiro boneco
        estado_inativo = await an.evaluate("""()=>{
            const mat = sel => {const t=getComputedStyle(document.querySelector(sel)).transform;
              return t==='none' ? new DOMMatrix() : new DOMMatrix(t);};
            const op = sel => parseFloat(getComputedStyle(document.querySelector(sel)).opacity);
            const mf = mat('.nav-item[data-go="clientes"] .cabeca-frente');
            const mt = mat('.nav-item[data-go="clientes"] .cabeca-tras');
            return { escalaFrente: Math.hypot(mf.a, mf.b), desvioFrente: Math.abs(mf.e)+Math.abs(mf.f),
                     escalaTras: Math.hypot(mt.a, mt.b), opTras: op('.nav-item[data-go="clientes"] .cabeca-tras') };}""")
        # clicar em Automovel pelo meio do botao: o <svg> tem overflow visible (anel do Perfil)
        # e pode apanhar o clique nos cantos
        await an.evaluate("""()=>{const b=document.querySelector('.nav-item[data-go="modelos"]');
            const r=b.getBoundingClientRect(); b.dispatchEvent(new MouseEvent('click',{bubbles:true,
              clientX:r.x+r.width/2, clientY:r.y+r.height/2}));}""")
        await an.wait_for_timeout(700)
        fora = await an.evaluate("""()=>{
            const mat = sel => {const t=getComputedStyle(document.querySelector(sel)).transform;
              return t==='none' ? new DOMMatrix() : new DOMMatrix(t);};
            const op = sel => parseFloat(getComputedStyle(document.querySelector(sel)).opacity);
            const mt = mat('.nav-item[data-go="clientes"] .cabeca-tras');
            return { escalaTras: Math.hypot(mt.a, mt.b), opTras: op('.nav-item[data-go="clientes"] .cabeca-tras'),
                     anim: getComputedStyle(document.querySelector('.nav-item[data-go="clientes"] .cabeca-tras')).animationName };}""")
        ok("R63 · fora da página Clientes o 2.º boneco fica invisível (sem 2.a cabeça)",
           fora["opTras"] < 0.05 and fora["escalaTras"] < 0.75 and fora["anim"] == "none", fora)

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
           await mp.evaluate("()=>localStorage.getItem('modelo_versao_dados')") == "5", "")
        ok("R41 · migração acrescenta o negócio de demonstração em Vendas",
           await mp.evaluate("()=>ORCAMENTOS.some(o=>o.id==='o6' && o.estado==='Em negociação')"), "")
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
           await iv.evaluate("()=>{document.getElementById('oEntrada').value='2,000,000 Kz';calc();return document.getElementById('o12').textContent;}") == "645,000 Kz",
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
        await lo.fill("#fCor", "Branco"); await lo.fill("#fPreco", "29900000")
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
          const sino=document.getElementById('whoBtn').getBoundingClientRect();
          return {busca:vis('.search-top'), titulo:vis('#barTitle'), pill: (document.querySelector('#netPill') ? vis('#netPill') : 'inexistente'),
                  sinoAFrente: sino.right > bar.left + bar.width/2,
                  utilizador: vis('#whoBtn'), oi: (document.querySelector('.who .oi')||{}).textContent||''};
        }""")
        ok("Desktop · campo de procura removido", gd["busca"]=="inexistente", str(gd))
        ok("R62 · nome da página dentro da appbar (desktop)", gd["titulo"]=="visivel", str(gd))
        ok("Desktop · modo Online fora da appbar", gd["pill"] in ("oculto","inexistente"), str(gd))
        ok("Desktop · foto de perfil alinhada à direita (sem notificações)", gd["sinoAFrente"] and gd["utilizador"] in ("visivel","flex"), str(gd))
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
           (await d.inner_text("#odRSaldo"))=="9,500,000 Kz" and (await d.inner_text("#odR12"))=="791,000 Kz",
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

        # ============ R35 · APPBAR: FOTO DE PERFIL NO LUGAR DAS NOTIFICAÇÕES ============
        r5 = await b.new_page(viewport={"width":1440,"height":900})
        r5e=[]; r5.on("pageerror", lambda e: r5e.append(str(e)))
        await novo(r5)
        A = await r5.evaluate("""()=>{
          const bar=document.querySelector('.bar');
          const txt=[...bar.querySelectorAll('button')].map(x=>x.getAttribute('aria-label')||x.title||'');
          const tema=getComputedStyle(document.getElementById('btnTema'));
          const av=document.querySelector('.who .av').getBoundingClientRect();
          const oi=document.querySelector('.who .oi').getBoundingClientRect();
          const who=document.querySelector('.who').getBoundingClientRect();
          return {sino: bar.innerHTML.includes('Notificações'),
                  semTextoNotif: !txt.some(t=>t.includes('Notificações')),
                  bordas: tema.borderTopWidth, fundoBtn: tema.backgroundColor,
                  fotoAcimaDoNome: av.bottom<=oi.top+1, nomeAbaixo: oi.top>=av.bottom-1,
                  centrado: Math.abs((av.left+av.right)/2-(who.left+who.right)/2)<1.5,
                  oiTexto: document.querySelector('.who .oi').textContent.trim()};
        }""")
        ok("R35 · desktop · ícone de notificações removido", not A["sino"] and A["semTextoNotif"], str(A))
        ok("R35 · ícones da appbar sem bordas", A["bordas"]=="0px" and A["fundoBtn"]=="rgba(0, 0, 0, 0)", str(A))
        ok("R35 · nome da loja debaixo da foto de perfil", A["fotoAcimaDoNome"] and A["centrado"], str(A))
        ok("R38 · cumprimento 'Oi <nome da loja>' sem vírgula", A["oiTexto"].startswith("Oi ") and "," not in A["oiTexto"], A["oiTexto"])
        await r5.evaluate("()=>{LOJA.dados='Seminovos Kianda'; guardarLoja(); renderAvatarLoja();}")
        await r5.wait_for_timeout(250)
        N = await r5.evaluate("()=>document.querySelector('.who .oi').textContent.trim()")
        ok("R38 · o nome segue os Dados da Loja", N=="Oi Seminovos Kianda", N)
        await r5.click("#whoBtn"); await r5.wait_for_timeout(600)
        ok("R35 · clicar na foto abre o Perfil",
           await r5.evaluate("()=>!document.getElementById('pg-perfil').classList.contains('hidden')"), "")
        await r5.evaluate("()=>{LOJA.dados=''; guardarLoja(); renderAvatarLoja();}")
        ok("R35 · sem erros de consola (desktop)", len(r5e)==0, str(r5e[:2]))
        await r5.close()

        r5m = await b.new_page(viewport={"width":390,"height":844}, is_mobile=True, has_touch=True)
        r5me=[]; r5m.on("pageerror", lambda e: r5me.append(str(e)))
        await novo(r5m)
        M = await r5m.evaluate("""()=>{
          const who=document.getElementById('whoBtn');
          const r=who.getBoundingClientRect(), bar=document.querySelector('.bar').getBoundingClientRect();
          const tema=document.getElementById('btnTema').getBoundingClientRect();
          const av=document.querySelector('.who .av').getBoundingClientRect();
          const oi=document.querySelector('.who .oi').getBoundingClientRect();
          const t=getComputedStyle(document.getElementById('btnTema'));
          return {visivel:getComputedStyle(who).display!=='none' && r.width>0,
                  lugarDoSino: r.left>=tema.right-0.5 && r.right<=bar.right+0.5,
                  dentroDaBarra: r.top>=bar.top && r.bottom<=bar.bottom,
                  depoisDoTema: r.left>=tema.right-0.5,
                  fotoAcima: av.bottom<=oi.top+1,
                  bordas: t.borderTopWidth + '|' + t.backgroundColor,
                  overflow: document.documentElement.scrollWidth-390,
                  oi: document.querySelector('.who .oi').textContent.trim()};
        }""")
        ok("R35 · mobile · foto de perfil no lugar das notificações", M["visivel"] and M["lugarDoSino"] and M["dentroDaBarra"], str(M))
        ok("R35 · mobile · nome debaixo da foto", M["fotoAcima"], str(M))
        ok("R35 · mobile · ícones sem bordas", M["bordas"]=="0px|rgba(0, 0, 0, 0)", M["bordas"])
        ok("R35 · mobile · appbar mantém-se dentro do ecrã", M["overflow"]<=0, str(M["overflow"]))
        ok("R35 · mobile · sem erros de consola", len(r5me)==0, str(r5me[:2]))
        await r5m.close()

        r5f = await b.new_page(viewport={"width":1440,"height":900})
        await novo(r5f)
        await r5f.evaluate("""()=>{LOJA.avatar='data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7'; renderAvatarLoja();}""")
        await r5f.wait_for_timeout(250)
        F = await r5f.evaluate("""()=>{const av=document.querySelector('.who .av');
          return {fundo:getComputedStyle(av).backgroundImage.includes('url('), texto:av.textContent.trim()};}""")
        ok("R35 · foto de perfil escolhida aparece na appbar", F["fundo"] and F["texto"]=="", str(F))
        await r5f.evaluate("()=>{LOJA.avatar=''; renderAvatarLoja();}")
        await r5f.close()

        # ============ R36 · APPBAR SEM 'ONLINE' E ORGANIZADA ============
        r6 = await b.new_page(viewport={"width":1440,"height":900})
        r6e=[]; r6.on("pageerror", lambda e: r6e.append(str(e)))
        await novo(r6)
        A6 = await r6.evaluate("""()=>{
          const grupo=document.querySelector('.bar-acoes');
          const tema=document.getElementById('btnTema').getBoundingClientRect();
          const sep=document.querySelector('.bar-sep').getBoundingClientRect();
          const who=document.getElementById('whoBtn').getBoundingClientRect();
          const bar=document.querySelector('.bar').getBoundingClientRect();
          return {pill:!!document.getElementById('netPill'),
                  online:document.querySelector('.bar').innerText.includes('Online'),
                  grupoExiste:!!grupo,
                  grupoADireita: grupo?getComputedStyle(grupo).marginLeft:'-',
                  temaAntesDoSep: tema.right<=sep.left+0.5,
                  sepAntesDoPerfil: sep.right<=who.left+0.5,
                  margemDireita: Math.round(bar.right-who.right),
                  espacoMeio: document.querySelector('.bar-acoes').parentElement==document.querySelector('.bar')};
        }""")
        ok("R36 · cápsula 'Online' removida da appbar", not A6["pill"] and not A6["online"], str(A6))
        ok("R36 · ações agrupadas e encostadas à direita", A6["grupoExiste"] and A6["margemDireita"]<=32, str(A6))
        ok("R36 · ordem: tema · divisor · perfil", A6["temaAntesDoSep"] and A6["sepAntesDoPerfil"], str(A6))
        ok("R36 · margem direita harmoniosa", 12<=A6["margemDireita"]<=32, str(A6["margemDireita"]))
        ok("R36 · desktop sem erros de consola", len(r6e)==0, str(r6e[:2]))
        await r6.close()

        r6m = await b.new_page(viewport={"width":390,"height":844}, is_mobile=True, has_touch=True)
        r6me=[]; r6m.on("pageerror", lambda e: r6me.append(str(e)))
        await novo(r6m)
        M6 = await r6m.evaluate("""()=>{
          const h=document.querySelector('.bar h1');
          const tema=document.getElementById('btnTema').getBoundingClientRect();
          const who=document.getElementById('whoBtn').getBoundingClientRect();
          const bar=document.querySelector('.bar').getBoundingClientRect();
          const sep=document.querySelector('.bar-sep');
          return {semPill: !document.getElementById('netPill'),
                  tituloInteiro: h.scrollWidth<=h.clientWidth,
                  espacoTitulo: Math.round(tema.left - h.getBoundingClientRect().right),
                  whoDentro: who.right<=bar.right+0.5 && who.top>=bar.top-0.5,
                  sepVisivel: getComputedStyle(sep).display!=='none',
                  overflow: document.documentElement.scrollWidth-390};
        }""")
        ok("R36 · mobile · sem 'Online' na appbar", M6["semPill"], str(M6))
        ok("R36 · mobile · título e ações com folga", M6["tituloInteiro"] and M6["espacoTitulo"]>=6, str(M6))
        ok("R36 · mobile · perfil dentro da barra", M6["whoDentro"] and M6["sepVisivel"], str(M6))
        ok("R36 · mobile · sem overflow", M6["overflow"]<=0, str(M6["overflow"]))
        await r6m.evaluate("()=>ir('listaorc')"); await r6m.wait_for_timeout(500)
        ok("R36 · mobile · título longo continua legível",
           await r6m.evaluate("()=>{const h=document.querySelector('.bar h1');return h.scrollWidth<=h.clientWidth;}"), "")
        ok("R36 · mobile · sem erros de consola", len(r6me)==0, str(r6me[:2]))
        await r6m.close()

        r6o = await b.new_context(viewport={"width":1440,"height":860})
        p6 = await r6o.new_page()
        await novo(p6)
        await r6o.set_offline(True); await p6.wait_for_timeout(600)
        ok("R36 · estado offline continua visível no Perfil",
           (await p6.inner_text("#linhaOffline")).strip().startswith("Sem ligação"), "")
        await p6.evaluate("()=>ir('perfil')"); await p6.wait_for_timeout(400)
        ok("R36 · Perfil mostra o estado da ligação",
           "Sem ligação" in await p6.inner_text("#pg-perfil"), "")
        await r6o.close()

        # ============ R39 · PÁGINA VENDAS ============
        rv = await b.new_page(viewport={"width":1440,"height":900})
        rve=[]; rv.on("pageerror", lambda e: rve.append(str(e)))
        await novo(rv)
        V1 = await rv.evaluate("""()=>{
          const menu=[...document.querySelectorAll('.side .nav')].map(n=>n.dataset.go);
          return {pagina: PAGES.includes('vendas'), titulo: TITLES.vendas[0],
                  menu: menu, ordem: menu.indexOf('vendas')===2};
        }""")
        ok("R39 · página Vendas registada no app", V1["pagina"] and V1["titulo"]=="Vendas", str(V1))
        ok("R39 · Vendas no menu entre Orçamentos e Clientes", V1["ordem"], str(V1["menu"]))
        # R68: seletor de estados no grupo "Negócios em curso"
        await rv.evaluate("()=>ir('vendas')"); await rv.wait_for_timeout(600)
        ops68 = await rv.evaluate("()=>[...document.querySelectorAll('#filtroEstadoVendas option')].map(o=>o.textContent)")
        ok("R68 · dropdown de estados em Vendas tem os cinco estados",
           ops68 == ['Todos','Pendente','Em negociação','Venda concluída','Perdido','Cancelado'], str(ops68))
        await rv.select_option('#filtroEstadoVendas','Em negociação'); await rv.wait_for_timeout(600)
        R68a = await rv.evaluate("""()=>({cartoes:document.querySelectorAll('#vendasLista .vneg').length,
            pills:[...document.querySelectorAll('#vendasLista .vneg .pill')].map(e=>e.textContent),
            contagem:document.getElementById('vendasContagem').textContent})""")
        ok("R68 · filtrar por estado mostra só esse estado",
           R68a["cartoes"] >= 1 and all(x == 'Em negociação' for x in R68a["pills"]), str(R68a))
        ok("R68 · a contagem diz quantos de quantos", 'de' in R68a["contagem"], R68a["contagem"])
        await rv.select_option('#filtroEstadoVendas','Cancelado'); await rv.wait_for_timeout(500)
        v68 = await rv.evaluate("()=>{const p=document.querySelector('#vendasLista p');return p?p.textContent:'';}")
        ok("R68 · estado sem negócios mostra mensagem própria",
           'Cancelado' in v68 and 'Todos' in v68, v68[:60])
        await rv.select_option('#filtroEstadoVendas','Todos'); await rv.wait_for_timeout(500)
        todos68 = await rv.evaluate("()=>document.querySelectorAll('#vendasLista .vneg').length")
        ok("R68 · voltar a “Todos” repõe a lista completa", todos68 >= R68a["cartoes"], str(todos68))
        # marcar um negócio como vendido com o filtro activo: sai da lista em curso
        await rv.select_option('#filtroEstadoVendas','Pendente'); await rv.wait_for_timeout(500)
        antes68 = await rv.evaluate("()=>document.querySelectorAll('#vendasLista .vneg').length")
        await rv.evaluate("""()=>{const b=document.querySelector('#vendasLista [data-etapa=\"Venda conclu\u00edda\"]'); if(b) b.click();}""")
        await rv.wait_for_timeout(600)
        depois68 = await rv.evaluate("()=>document.querySelectorAll('#vendasLista .vneg').length")
        ok("R68 · negócio vendido sai da lista filtrada por Pendente", depois68 == antes68 - 1, f'{antes68} -> {depois68}')
        await rv.select_option('#filtroEstadoVendas','Todos'); await rv.wait_for_timeout(400)
        await rv.evaluate("()=>ir('vendas')"); await rv.wait_for_timeout(700)
        V2 = await rv.evaluate("""()=>{
          const s=document.getElementById('pg-vendas');
          const n=[...s.querySelectorAll('.funil .n')].map(e=>Number(e.textContent));
          return {visivel:!s.classList.contains('hidden'),
                  etapas:[...s.querySelectorAll('.funil .l')].map(e=>e.textContent),
                  nums:n, contadoresDerivados: JSON.stringify(n)===JSON.stringify([clientesAgrupados().length,
                    ORCAMENTOS.filter(o=>o.estado!=='Perdido'&&o.estado!=='Cancelado').length,
                    ORCAMENTOS.filter(o=>o.estado==='Em negociação').length,
                    ORCAMENTOS.filter(o=>o.estado==='Venda concluída').length]),
                  semDemo: !s.innerText.includes('demonstração')};
        }""")
        ok("R39 · quatro etapas do funil", V2["visivel"] and V2["etapas"]==["Contactos captados","Orçamentos enviados","Em negociação","Vendas concluídas"], str(V2["etapas"]))
        ok("R39 · números do funil vêm dos dados reais", V2["contadoresDerivados"] and V2["semDemo"], str(V2["nums"]))
        # mudar de etapa na edição do orçamento e refletir em Vendas
        await rv.evaluate("()=>{ir('listaorc'); abrirOrcDetalhe('o2');}"); await rv.wait_for_timeout(500)
        await rv.select_option("#odEstadoInp","Em negociação"); await rv.click("#odGuardar"); await rv.wait_for_timeout(600)
        await rv.evaluate("()=>ir('vendas')"); await rv.wait_for_timeout(700)
        V3 = await rv.evaluate("""()=>({neg:Number(document.getElementById('fnNegociacao').textContent),
            cartoes:document.querySelectorAll('.vneg').length,
            menu:Number(document.querySelector('.side [data-cnt=\"vendas\"]').textContent)})""")
        ok("R39 · orçamento em negociação aparece na página", V3["neg"]>=1 and V3["cartoes"]>=1, str(V3))
        ok("R39 · contador do menu acompanha", V3["menu"]==V3["neg"], str(V3))
        await rv.click("[data-orc='o2'] [data-etapa='Venda concluída']"); await rv.wait_for_timeout(900)
        V4 = await rv.evaluate("""()=>({vend:Number(document.getElementById('fnVendas').textContent),
            estado:ORCAMENTOS.find(o=>o.id==='o2').estado, guardado:(JSON.parse(localStorage.getItem('modelo_orcamentos_v1')).find(o=>o.id==='o2')||{}).estado,
            stVendas:document.getElementById('stVendas').textContent,
            toast:document.getElementById('toast').textContent})""")
        ok("R39 · 'Marcar como vendido' muda o estado", V4["estado"]=="Venda concluída" and V4["vend"]>=1, str(V4))
        ok("R39 · estado persistido no dispositivo", V4["guardado"]=="Venda concluída", str(V4))
        ok("R39 · cartão do Perfil conta as vendas", V4["stVendas"]==str(V4["vend"]), str(V4))
        ok("R39 · confirmação por toast", "Venda concluída" in V4["toast"], V4["toast"])
        # coerência nas outras páginas
        await rv.evaluate("()=>ir('listaorc')"); await rv.wait_for_timeout(600)
        ok("R39 · tabela de Orçamentos mostra a mesma etiqueta",
           "Venda concluída" in await rv.inner_text("#tblOrc"), "")
        await rv.evaluate("()=>{ir('clientes'); abrirCliente('Ana Silva','912887340');}"); await rv.wait_for_timeout(700)
        ok("R39 · página do Cliente mostra a mesma etiqueta",
           "Venda concluída" in await rv.inner_text("#pg-cliente"), "")
        ok("R39 · Vendas sem erros de consola", len(rve)==0, str(rve[:2]))
        await rv.close()

        rvm = await b.new_page(viewport={"width":390,"height":844}, is_mobile=True, has_touch=True)
        rvme=[]; rvm.on("pageerror", lambda e: rvme.append(str(e)))
        await novo(rvm)
        M1 = await rvm.evaluate("""()=>{
          const itens=[...document.querySelectorAll('.nav-item')];
          const alvo=itens.find(n=>n.dataset.go==='vendas');
          const r=alvo.getBoundingClientRect();
          return {itens:itens.length, existe:!!alvo, largura:Math.round(r.width),
                  dentro: r.left>=0 && r.right<=document.documentElement.clientWidth,
                  overflow: document.documentElement.scrollWidth-390};
        }""")
        ok("R39 · telemóvel · Vendas no menu inferior (5 áreas)", M1["existe"] and M1["itens"]==5, str(M1))
        ok("R39 · telemóvel · menu sem overflow", M1["overflow"]<=0 and M1["dentro"], str(M1))
        await rvm.evaluate("()=>ir('vendas')"); await rvm.wait_for_timeout(700)
        M2 = await rvm.evaluate("""()=>{
          const s=document.getElementById('pg-vendas');
          const etapas=[...s.querySelectorAll('.etapa')];
          const prim=etapas[0].getBoundingClientRect(), seg=etapas[1].getBoundingClientRect();
          return {empilhado: seg.top>=prim.bottom-1, semScroll: document.documentElement.scrollWidth-390,
                  titulo: document.getElementById('barTitle').textContent};
        }""")
        ok("R39 · telemóvel · funil em lista empilhada", M2["empilhado"], str(M2))
        ok("R39 · telemóvel · título 'Vendas' na appbar", M2["titulo"]=="Vendas", str(M2))
        ok("R39 · telemóvel · sem erros de consola", len(rvme)==0, str(rvme[:2]))
        await rvm.close()

        rvd = await b.new_page(viewport={"width":1440,"height":900})
        await novo(rvd); await rvd.click("#btnTema"); await rvd.wait_for_timeout(400)
        await rvd.evaluate("()=>ir('vendas')"); await rvd.wait_for_timeout(700)
        D1 = await rvd.evaluate("""()=>{
          const f=document.querySelector('.funil'), e=document.querySelector('.etapa'), n=document.querySelector('.etapa .n');
          return {fundo:getComputedStyle(f).backgroundColor, borda:getComputedStyle(f).borderColor,
                  etapaFundo:getComputedStyle(e).backgroundColor, num:getComputedStyle(n).color,
                  ativoVerde:getComputedStyle(document.querySelector('.side .nav.on')).color};
        }""")
        ok("R39 · modo escuro aplica-se ao funil", D1["fundo"]=="rgb(4, 13, 31)" and D1["etapaFundo"]=="rgb(7, 21, 40)", str(D1))
        ok("R39 · menu ativo a verde no escuro", D1["ativoVerde"]=="rgb(52, 217, 122)", str(D1["ativoVerde"]))
        await rvd.close()

        # ============ R41 · NEGÓCIO EM CURSO + ANIMAÇÃO DO ÍCONE VENDAS ============
        r41 = await b.new_page(viewport={"width":1440,"height":900})
        r41e=[]; r41.on("pageerror", lambda e: r41e.append(str(e)))
        await novo(r41)
        N1 = await r41.evaluate("""()=>{
          const o=ORCAMENTOS.find(x=>x.id==='o6');
          const c=CARROS.find(x=>x.id===(o||{}).carro);
          return {existe:!!o, estado:(o||{}).estado, nome:(o||{}).nome,
                  precoIgualCatalogo: !!o && !!c && Number(o.preco)===Number(c.preco),
                  notas: !!(o&&o.notas)};
        }""")
        ok("R41 · negócio de demonstração existe em negociação", N1["existe"] and N1["estado"]=="Em negociação", str(N1))
        ok("R41 · negócio com preço atual do catálogo", N1["precoIgualCatalogo"], str(N1))
        await r41.evaluate("()=>ir('vendas')"); await r41.wait_for_timeout(700)
        N2 = await r41.evaluate("""()=>{
          const cartoes=[...document.querySelectorAll('.vneg')];
          const alvo=cartoes.find(c=>c.innerText.includes('Paulo Neto'));
          return {cartoes:cartoes.length, encontrado:!!alvo,
                  temBotao: !!alvo && !!alvo.querySelector('[data-etapa]'),
                  valor: (document.getElementById('vtNeg').textContent||'').includes('Kz'),
                  funilNeg: Number(document.getElementById('fnNegociacao').textContent)};
        }""")
        ok("R41 · aparece na lista 'Negócios em curso'", N2["encontrado"] and N2["cartoes"]>=1 and N2["funilNeg"]>=1, str(N2))
        ok("R41 · cartão com botão 'Marcar como vendido'", N2["temBotao"], str(N2))
        N2b = await r41.evaluate("""()=>{const c=document.querySelector('.vneg');
          const bs=[...c.querySelectorAll('.est button')].map(x=>({t:x.textContent.trim(),e:x.dataset.etapa}));
          return {n:bs.length, textos:bs.map(x=>x.t).join(' / '),
                  temVend:bs.some(x=>x.e==='Venda concluída'), temPend:bs.some(x=>x.e==='Pendente'),
                  temNeg:bs.some(x=>x.e==='Em negociação'), temPerd:bs.some(x=>x.e==='Perdido')};}""")
        ok("R56 · cada item aberto tem 4 ações (pendente + negociação + vendido + perdido)",
           N2b["n"]==4 and N2b["temVend"] and N2b["temPend"] and N2b["temNeg"] and N2b["temPerd"], str(N2b))
        await r41.click("[data-orc='o6'] .pend"); await r41.wait_for_timeout(700)
        P1 = await r41.evaluate("""()=>({estado:ORCAMENTOS.find(o=>o.id==='o6').estado,
            pill:(document.querySelector("[data-orc='o6'] .pill")||{}).textContent.trim(),
            neg:Number(document.getElementById('fnNegociacao').textContent),
            cartoes:[...document.querySelectorAll('.vneg:not(.fechado)')].length,
            pressed:document.querySelector("[data-orc='o6'] .pend").getAttribute('aria-pressed')})""")
        ok("R42 · 'Marcar pendente' põe o negócio pendente", P1["estado"]=="Pendente" and P1["pill"]=="Pendente" and P1["neg"]==0 and P1["cartoes"]>=1, str(P1))
        await r41.click("[data-orc='o6'] .pend"); await r41.wait_for_timeout(700)
        P2 = await r41.evaluate("()=>ORCAMENTOS.find(o=>o.id==='o6').estado")
        ok("R42 · segundo clique no pendente volta a 'Em negociação'", P2=="Em negociação", str(P2))
        await r41.click("[data-orc='o6'] [data-etapa='Venda concluída']"); await r41.wait_for_timeout(800)
        N3 = await r41.evaluate("""()=>({estado:ORCAMENTOS.find(o=>o.id==='o6').estado,
            vendas:Number(document.getElementById('fnVendas').textContent),
            fechado: !!document.querySelector('.vneg.fechado'),
            botoesFechado: document.querySelectorAll('.vneg.fechado [data-etapa]:not(.reabrir)').length,
            reabrir: document.querySelectorAll('.vneg.fechado .reabrir').length})""")
        ok("R41 · marcar como vendido funciona neste negócio", N3["estado"]=="Venda concluída" and N3["vendas"]>=1 and N3["fechado"], str(N3))
        ok("R56 · negócio fechado só mostra 'Reabrir'", N3["botoesFechado"]==0 and N3["reabrir"]==1, str(N3))

        # animação do ícone (desktop e mobile)
        A1 = await r41.evaluate("""()=>{
          const on=document.querySelector('.nav.on[data-go="vendas"] .ico svg .mais');
          return {nome:on?getComputedStyle(on).animationName:'', dur:on?getComputedStyle(on).animationDuration:'',
                  iter:on?getComputedStyle(on).animationIterationCount:''};
        }""")
        ok("R61 · ícone Vendas (carrinho) animado quando ativo", A1["nome"]=="carrinhoMais" and A1["iter"]=="infinite", str(A1))
        await r41.evaluate("()=>ir('modelos')"); await r41.wait_for_timeout(400)
        A2 = await r41.evaluate("""()=>{
          const off=document.querySelector('.nav[data-go="vendas"] .ico svg path');
          return {nome:getComputedStyle(off).animationName, opac:getComputedStyle(off).opacity};
        }""")
        ok("R41 · ícone Vendas parado quando inativo", A2["nome"]=="none" and A2["opac"]=="1", str(A2))
        ok("R41 · sem erros de consola", len(r41e)==0, str(r41e[:2]))
        await r41.close()

        # ============ R43 · CONTADOR 0 -> VALOR (8 s) NA PÁGINA VENDAS ============
        r43 = await b.new_page(viewport={"width":1440,"height":900})
        r43e = []; r43.on("pageerror", lambda e: r43e.append(str(e)))
        await r43.goto(URL_ANIM); await r43.wait_for_timeout(400)
        await r43.evaluate("localStorage.clear()"); await r43.reload(); await r43.wait_for_timeout(600)
        await r43.evaluate("()=>ir('vendas')")
        C1 = await r43.evaluate("""()=>({dur:DURACAO_CONTAGEM,
            inteiros:[...document.querySelectorAll('.etapa .n')].map(e=>e.dataset.int),
            total:document.getElementById('vtNeg').dataset.valor===undefined?'':document.getElementById('vtNeg').dataset.valor})""")
        ok("R43 · contagem de 8 s configurada", C1["dur"]==8000, str(C1))
        ok("R43 · números do funil contam como inteiros", C1["inteiros"]==["1","1","1","1"], str(C1))
        meio = []
        for _ in range(3):
            await r43.wait_for_timeout(700)
            meio.append(await r43.evaluate("""()=>{const v=document.getElementById('vtNeg');
              return {fn:Number(document.getElementById('fnEnviados').textContent),
                      vt:v.textContent, temKz:v.textContent.includes('Kz'),
                      contando:document.querySelectorAll('#pg-vendas .contando').length};}"""))
        ok("R43 · valores a meio da contagem ainda não chegaram ao fim",
           any(m["fn"]<6 for m in meio) and all(m["temKz"] for m in meio)
           and any(m["contando"]>=4 for m in meio), str(meio))
        await r43.wait_for_timeout(8000)
        C3 = await r43.evaluate("""()=>({fn:[...document.querySelectorAll('.etapa .n')].map(e=>e.textContent),
            vtNeg:document.getElementById('vtNeg').textContent,
            vtFech:document.getElementById('vtFech').textContent,
            vn:document.getElementById('vnTotal').textContent,
            vl:document.querySelector('.vneg .vl').textContent,
            esperado: fmt(ORCAMENTOS.reduce((t,o)=>t+((o.estado==='Pendente'||o.estado==='Em negocia\u00e7\u00e3o')?totalComIva(o.preco):0),0)),
            vf: fmt(totalComIva(ORCAMENTOS.find(o=>o.estado==='Pendente').preco)),
            contando:document.querySelectorAll('#pg-vendas .contando').length})""")
        ok("R43 · valores finais exatos nos 8 s",
           C3["fn"]==["5","6","1","0"] and C3["vtNeg"]==C3["esperado"] and C3["vn"]==C3["esperado"]
           and C3["vl"]==C3["vf"] and C3["vtFech"]=="0 Kz" and C3["contando"]==0, str(C3))
        await r43.evaluate("()=>ir('modelos')"); await r43.wait_for_timeout(400)
        await r43.evaluate("()=>ir('vendas')"); await r43.wait_for_timeout(700)
        C4 = await r43.evaluate("()=>({fn:document.getElementById('fnEnviados').textContent, vt:document.getElementById('vtNeg').textContent})")
        ok("R43 · ao voltar à página a contagem recomeça do 0",
           int(C4["fn"])<6 and C4["vt"]!="14,706,000 Kz", str(C4))
        ok("R43 · sem erros de consola", len(r43e)==0, str(r43e[:2]))
        await r43.close()

        r41m = await b.new_page(viewport={"width":390,"height":844}, is_mobile=True, has_touch=True)
        await novo(r41m)
        await r41m.evaluate("()=>ir('vendas')"); await r41m.wait_for_timeout(700)
        A3 = await r41m.evaluate("""()=>{
          const p=document.querySelector('.nav-item.on[data-go="vendas"] .ico svg .mais');
          const cs=getComputedStyle(p);
          return {nome:cs.animationName, iter:cs.animationIterationCount,
                  itens:document.querySelectorAll('.nav-item').length};
        }""")
        ok("R61 · animação do carrinho também na navbar do telemóvel", A3["nome"]=="carrinhoMais" and A3["iter"]=="infinite", str(A3))
        M2 = await r41m.evaluate("""()=>{const bs=[...document.querySelectorAll('.vneg .est button')].slice(0,4);
          const r=bs.map(b=>{const q=b.getBoundingClientRect();return {w:q.width,h:q.height}});
          return {n:bs.length, dentroDoEcra: r.every(q=>q.w>0&&q.h>0&&q.h<=44), ecra:innerWidth};}""")
        ok("R56 · quatro ações também no telemóvel, dentro do ecrã", M2["n"]==4 and M2["dentroDoEcra"], str(M2))
        await r41m.close()

        # ============ R56 · ESTADOS DO NEGOCIO (Pendente automatico) ============
        r56 = await b.new_page(viewport={"width":1440,"height":900})
        r56e=[]; r56.on("pageerror", lambda e: r56e.append(str(e)))
        await novo(r56)
        S1 = await r56.evaluate("""()=>{
          const cinco=['Pendente','Em negociação','Venda concluída','Perdido','Cancelado'];
          return {estados:CINCO_ESTADOS, iguais:JSON.stringify(CINCO_ESTADOS)===JSON.stringify(cinco),
                  fechados:ORC_FECHADOS, curso:ORC_CURSO,
                  enviadoDeixouDeExistir: !ORCAMENTOS.some(o=>o.estado==='Enviado'),
                  todosTemSelo: ORCAMENTOS.every(o=>typeof o.enviado==='boolean')};
        }""")
        ok("R56 · os cinco estados do negócio estão definidos", S1["iguais"], str(S1["estados"]))
        ok("R56 · 'Enviado' deixou de ser um estado", S1["enviadoDeixouDeExistir"] and S1["todosTemSelo"], str(S1))
        ok("R56 · em curso = Pendente + Em negociação",
           S1["curso"]==["Pendente","Em negociação"], str(S1["curso"]))
        ok("R56 · fechados = Venda concluída + Perdido + Cancelado",
           S1["fechados"]==["Venda concluída","Perdido","Cancelado"], str(S1["fechados"]))

        # criar orçamento: nasce Pendente e aparece de imediato em Negócios em Curso
        S2 = await r56.evaluate("""()=>{
          ORCAMENTOS.unshift({id:'r56a', nome:'Cliente R56', tel:'923111222', carro:CARROS[0].id,
            preco:9750000, entrada:1800000, desc:0, data:Date.now(), estado:'Pendente', enviado:true, reenvios:0});
          guardarOrc(); ir('vendas');
          const c=document.querySelector("[data-orc='r56a']");
          return {estado:ORCAMENTOS[0].estado, naLista:!!c,
                  etiqueta:c?c.querySelector('.pill').innerText.trim():'',
                  emCurso:!!c && !c.classList.contains('fechado'),
                  selo:c?c.querySelector('.nota').innerText.trim():''};
        }""")
        await r56.wait_for_timeout(1600)
        S2b = await r56.evaluate("""()=>{
          const c=document.querySelector("[data-orc='r56a']");
          return {naLista:!!c, etiqueta:c?c.querySelector('.pill').innerText.trim():'',
                  primeiro:document.querySelector('.vneg .nm').innerText,
                  selo:c?c.querySelector('.nota').innerText.trim():''};
        }""")
        ok("R56 · orçamento criado nasce Pendente", S2["estado"]=="Pendente" and S2b["etiqueta"]=="Pendente", str(S2b))
        ok("R56 · aparece logo em Negócios em Curso, no topo", S2b["naLista"] and S2b["primeiro"]=="Cliente R56", str(S2b))
        ok("R56 · o envio aparece como selo, não como estado", "enviado" in S2b["selo"] and "Pendente" not in S2b["selo"], str(S2b["selo"]))

        # as quatro ações e as transições
        S3 = await r56.evaluate("""()=>{
          const acoes=[...document.querySelectorAll("[data-orc='r56a'] .acao button")].map(b=>b.dataset.etapa);
          return {acoes, texto:[...document.querySelectorAll("[data-orc='r56a'] .acao button")].map(b=>b.innerText.trim())};
        }""")
        ok("R56 · quatro ações por negócio aberto",
           S3["acoes"]==["Pendente","Em negociação","Venda concluída","Perdido"], str(S3))
        await r56.click("[data-orc='r56a'] [data-etapa='Em negociação']"); await r56.wait_for_timeout(600)
        ok("R56 · marcar Em negociação", await r56.evaluate("()=>ORCAMENTOS[0].estado")=="Em negociação")
        await r56.click("[data-orc='r56a'] [data-etapa='Perdido']"); await r56.wait_for_timeout(700)
        S4 = await r56.evaluate("""()=>{
          const c=document.querySelector("[data-orc='r56a']");
          return {estado:ORCAMENTOS[0].estado, fechado:!!c && c.classList.contains('fechado'),
                  reabrir:!!(c&&c.querySelector('.reabrir')),
                  enviados:Number(document.getElementById('fnEnviados').textContent)};
        }""")
        ok("R56 · Perdido fecha o negócio e dá para reabrir",
           S4["estado"]=="Perdido" and S4["fechado"] and S4["reabrir"], str(S4))
        await r56.click("[data-orc='r56a'] .reabrir"); await r56.wait_for_timeout(600)
        ok("R56 · Reabrir devolve o negócio a Pendente",
           await r56.evaluate("()=>ORCAMENTOS[0].estado")=="Pendente")
        await r56.click("[data-orc='r56a'] [data-etapa='Venda concluída']"); await r56.wait_for_timeout(700)
        ok("R56 · marcar Vendido", await r56.evaluate("()=>ORCAMENTOS[0].estado")=="Venda concluída")

        # migração de dados antigos
        await r56.evaluate("""()=>{localStorage.setItem('modelo_orcamentos_v1', JSON.stringify([
            {id:'velho', nome:'Antigo', tel:'923999888', carro:CARROS[0].id, preco:9750000,
             entrada:2000000, desc:0, data:Date.now(), estado:'Enviado'}]));}""")
        await r56.reload(); await r56.wait_for_timeout(1500)
        S5 = await r56.evaluate("""()=>{const o=ORCAMENTOS.find(x=>x.id==='velho');
            return {estado:o.estado, enviado:o.enviado,
                    guardado:JSON.parse(localStorage.getItem('modelo_orcamentos_v1')).find(x=>x.id==='velho').estado};}""")
        ok("R56 · orçamentos antigos 'Enviado' passam a Pendente + selo",
           S5["estado"]=="Pendente" and S5["enviado"] is True and S5["guardado"]=="Pendente", str(S5))

        # lista de orçamentos e detalhe
        S6 = await r56.evaluate("""()=>{
          ir('listaorc');
          const ops=[...document.querySelectorAll('#odEstadoInp option')].map(o=>o.text);
          return {ops, filtros:[...document.querySelectorAll('#filtrosOrc .chip')].map(c=>c.innerText.trim())};
        }""")
        ok("R56 · o seletor de estado tem os cinco, sem 'Enviado'",
           S6["ops"]==["Pendente","Em negociação","Venda concluída","Perdido","Cancelado"], str(S6["ops"]))
        S7 = await r56.evaluate("""()=>{
          const f=[];
          document.querySelectorAll('#filtrosOrc .chip').forEach(c=>{
            if(c.innerText.trim()==='Fechados') c.click();
          });
          f.push(...[...document.querySelectorAll('#tblOrc .pill')].map(e=>e.innerText));
          document.querySelectorAll('#filtrosOrc .chip').forEach(c=>{
            if(c.innerText.trim()==='Em curso') c.click();
          });
          return {fechados:f, curso:[...document.querySelectorAll('#tblOrc .pill')].map(e=>e.innerText)};
        }""")
        ok("R56 · filtro Fechados mostra só estados fechados",
           all(x in ["Venda concluída","Perdido","Cancelado"] for x in S7["fechados"]), str(S7["fechados"]))
        ok("R56 · filtro Em curso mostra só Pendente e Em negociação",
           all(x in ["Pendente","Em negociação"] for x in S7["curso"]) and len(S7["curso"])>0, str(S7["curso"]))
        ok("R56 · sem erros de consola no fluxo de estados", len(r56e)==0, str(r56e[:2]))
        await r56.close()

        # ============ R44 · CORREÇÕES DA AUDITORIA (filtros, exportar, avisos, prestações) ============
        r44 = await b.new_page(viewport={"width":1440,"height":900})
        r44e = []; r44.on("pageerror", lambda e: r44e.append(str(e)))
        dl = []; r44.on("download", lambda d: dl.append(d.suggested_filename))
        await novo(r44)

        E1 = await r44.evaluate("()=>{abrirOrcDetalhe(ORCAMENTOS[0].id);const o=[...document.querySelectorAll('#odEstadoInp option')].map(x=>x.textContent);return {op:o, unicos:new Set(o).size};}")
        ok("R44 · Estado sem opções duplicadas", len(E1["op"])==E1["unicos"] and E1["unicos"]==5, str(E1))

        CL = await r44.evaluate("()=>['Enviado','Em negociação','Pendente','Venda concluída','Cancelado'].map(e=>classeEstado(e).trim())")
        ok("R44 · cada estado com a sua cor", len(set(CL))==5 and CL[1]=="p" and CL[2]=="pd" and CL[3]=="v" and CL[4]=="c", str(CL))

        PR = await r44.evaluate("()=>{const p=prestacao(7750000,12);return {base:p.base, ultima:p.ultima, soma:p.base*11+p.ultima};}")
        ok("R44 · prestações redondas e soma exata",
           PR["base"]==645000 and PR["soma"]==7750000 and PR["ultima"]==655000, str(PR))
        ok("R44 · prestação aparece sem cêntimos no ecrã",
           "645,000 Kz" == (await r44.inner_text("#odR12")), await r44.inner_text("#odR12"))

        await r44.evaluate("()=>ir('listaorc')"); await r44.wait_for_timeout(500)
        F = {}
        F["todos"] = len(await r44.query_selector_all("#tblOrc tr"))
        await r44.click('[data-forc="Fechados"]'); await r44.wait_for_timeout(350)
        F["fechados"] = len(await r44.query_selector_all("#tblOrc tr"))
        F["txt"] = await r44.inner_text("#tblOrc")
        await r44.click('[data-forc="Abertos"]'); await r44.wait_for_timeout(350)
        F["abertos"] = len(await r44.query_selector_all("#tblOrc tr"))
        await r44.click('[data-forc="Todos"]'); await r44.wait_for_timeout(250)
        ok("R44 · filtros da lista funcionam (em curso / fechados / todos)",
           F["fechados"]==1 and "fechados" in F["txt"] and F["abertos"]==F["todos"] and F["todos"]==6, str(F))

        await r44.evaluate("()=>ir('perfil')"); await r44.wait_for_timeout(400)
        await r44.click('[data-exportar="csv"]'); await r44.wait_for_timeout(800)
        ok("R44 · Exportar orçamentos em CSV descarrega", len(dl)==1 and dl[0].endswith(".csv"), str(dl))
        # R66: o CSV tem de levar o desconto negociado e o valor à vista
        csv66 = await r44.evaluate("""()=>{const c=linhasCSV();
            return {cab:c[0], linha:c[1], descontoCol:c[0].indexOf('Desconto a vista'),
                    vistaCol:c[0].indexOf('A vista')};}""")
        ok("R66 · CSV exportado inclui desconto à vista e valor à vista",
           csv66["descontoCol"] >= 0 and csv66["vistaCol"] > csv66["descontoCol"]
           and len(csv66["linha"]) == len(csv66["cab"]), str(csv66))
        janelas = []
        r44.context.on("page", lambda np: janelas.append(np))
        await r44.click('[data-exportar="pdf"]'); await r44.wait_for_timeout(1200)
        pdf_txt = (await janelas[0].inner_text("body")) if janelas else ""
        ok("R44 · Exportar em PDF abre a folha de impressão", len(janelas)==1 and "Orçamentos" in pdf_txt, str(len(janelas)))
        if janelas:
            ok("R44 · PDF diz que o IVA vai à parte", "IVA 14% apresentado à parte" in pdf_txt, "")
            await janelas[0].close()

        await r44.evaluate("()=>ir('modelos')"); await r44.wait_for_timeout(400)
        R57 = await r44.evaluate("""()=>{const cab=document.querySelector('#pg-modelos .page-head');
            const bs=[...cab.querySelectorAll('button')].map(b=>b.innerText.trim()||'[+]');
            return {botoes:bs, temExportar:!!document.getElementById('btnExportarModelos'),
                    textoExportar:cab.innerText.includes('Exportar')};}""")
        ok("R57 · página Modelos sem botão Exportar",
           not R57["temExportar"] and not R57["textoExportar"] and R57["botoes"]==["[+]"], str(R57))
        ok("R57 · o estoque já não gera ficheiro CSV", len(dl)==1, str(dl))

        await r44.evaluate("()=>ir('perfil')"); await r44.wait_for_timeout(300)
        await r44.click("#btnVerModelo"); await r44.wait_for_timeout(900)
        msg_txt = (await janelas[1].inner_text("body")) if len(janelas)>1 else ""
        ok("R44 · Ver modelo de mensagem abre o texto", len(janelas)==2
           and "Olá" in msg_txt and "IVA 14%" in msg_txt, str(len(janelas)))
        if len(janelas)>1: await janelas[1].close()

        # avisos de validação no popup de envio
        await r44.evaluate("()=>{atual=CARROS[0];abrirOrcamento();}"); await r44.wait_for_timeout(400)
        await r44.evaluate("()=>[...document.querySelectorAll('#pg-orcamento button')].find(b=>/WhatsApp/i.test(b.textContent)).click()")
        await r44.wait_for_timeout(500)
        await r44.evaluate("()=>document.getElementById('btnZap').click()"); await r44.wait_for_timeout(350)
        ok("R44 · envio sem nome mostra aviso dentro do popup",
           await r44.evaluate("()=>document.getElementById('avisoEnvio').classList.contains('on')"),
           await r44.inner_text("#avisoEnvio"))
        await r44.fill("#mNome", "Teste Aviso"); await r44.fill("#mTel", "923")
        await r44.evaluate("()=>document.getElementById('btnZap').click()"); await r44.wait_for_timeout(350)
        ok("R44 · telefone curto mostra aviso específico",
           "Telefone" in await r44.inner_text("#avisoEnvio"), await r44.inner_text("#avisoEnvio"))

        # prestações no texto do WhatsApp com aviso de juros
        MSG = await r44.evaluate("()=>{document.getElementById('mTel').value='923111999';return mensagem();}")
        ok("R44 · mensagem avisa que a simulação é sem juros",
           "Simulação sem juros" in MSG and MSG.count("Simulação sem juros")==1, MSG[-90:])
        ok("R44 · mensagem com prestações redondas", "645" in MSG or "731" in MSG, MSG[:120])

        # eliminado do estoque: orçamento mantém nome e não mostra foto errada
        await r44.evaluate("()=>{document.querySelectorAll('.ov.open').forEach(o=>o.classList.remove('open'));ir('modelos');}")
        await r44.wait_for_timeout(300)
        await r44.click("[data-delcar]"); await r44.wait_for_timeout(400)
        await r44.click("#btnApagarModelo"); await r44.wait_for_timeout(600)
        DEL = await r44.evaluate("()=>({nomes:ORCAMENTOS.filter(o=>o.carroNome).map(o=>o.carroNome), total:ORCAMENTOS.length})")
        ok("R44 · orçamentos guardam o nome do modelo eliminado", len(DEL["nomes"])>0, str(DEL))
        await r44.evaluate("()=>ir('listaorc')"); await r44.wait_for_timeout(500)
        ok("R44 · lista mantém o modelo eliminado legível", "Corolla" in await r44.inner_text("#tblOrc"), "")
        ok("R44 · sem imagens partidas depois de eliminar",
           await r44.evaluate("()=>[...document.images].filter(i=>i.offsetParent&&i.complete&&i.naturalWidth===0).length")==0, "")
        ok("R44 · sem erros de consola", len(r44e)==0, str(r44e[:2]))
        await r44.close()

        # ============ R49 · ROBUSTEZ (ASCII no JS, aviso de arranque, sem duplicacao) ============
        import re as _re
        _h = open("/home/user/index.html", encoding="utf-8").read()
        _js = "\n".join(_re.findall(r"<script>(.*?)</script>", _h, _re.S))
        ok("R51 · ficheiro inteiro em ASCII puro (imune a corrupção de codificação)",
           all(ord(c) < 128 for c in _h), str(sorted({c for c in _h if ord(c) > 127})[:5]))
        # R53: nenhuma tag de fecho crua dentro do JS (o browser fecharia o <script> a meio)
        _cru = _re.findall(r"</(?:body|html|style|head|script)", _js)
        ok("R53 · sem tags de fecho cruas dentro do JavaScript", len(_cru) == 0, str(_cru[:3]))
        # browsers antigos (Safari 11, WebViews) rejeitam 'catch {' sem variável — ES2019
        ok("R51 · sem 'catch {' sem variável (compatível com Safari 11 / WebViews)",
           len(_re.findall(r"catch\s*\{", _js)) == 0, str(len(_re.findall(r"catch\s*\{", _js))))
        ok("R51 · JavaScript 100% ASCII",
           all(ord(c) < 128 for c in _js), str(sorted({c for c in _js if ord(c) > 127})[:5]))
        ok("R49 · charset declarado em duas formas",
           'charset="UTF-8"' in _h and 'http-equiv="Content-Type"' in _h, "")
        ok("R49 · um só id heroImg (sem duplicacao)",
           _h.count('id="heroImg"') == 1, str(_h.count('id="heroImg"')))
        ok("R49 · mensagem() reutiliza textoOrcamento() (sem texto duplicado)",
           _h.count("Conforme falamos") == 1, str(_h.count("Conforme falamos")))

        r49 = await b.new_page(viewport={"width":1280,"height":860})
        _e49 = []; r49.on("pageerror", lambda e: _e49.append(str(e)))
        await r49.goto(URL); await r49.wait_for_timeout(900)
        ok("R49 · arranque concluído e sem aviso de falha",
           await r49.evaluate("()=>window.__arranqueOK===true")
           and await r49.evaluate("()=>getComputedStyle(document.getElementById('falhaArranque')).display==='none'"),
           str(_e49[:2]))
        _m49 = await r49.evaluate("()=>{atual=CARROS[0];abrirOrcamento();document.getElementById('mNome').value='João Ação';return mensagem();}")
        ok("R49 · acentos intactos e texto limpo no envio (R67 tirou os emojis)",
           "Joao A\u00e7\u00e3o".replace("Joao","Jo\u00e3o") in _m49 and "\U0001F697" not in _m49
           and _m49.count("Simula\u00e7\u00e3o sem juros") == 1,
           _m49.split(chr(10))[0])
        ok("R49 · galeria do detalhe continua a funcionar",
           await r49.evaluate("()=>{atual=CARROS[0];abrirDetalhe();const i=document.querySelector('.hero img');return !!i && i.naturalWidth>0;}"), "")
        await r49.close()

        await b.close()

    print("\n" + "="*70)
    falhas = [r for r in R if r[0]=="FALHA"]
    print(f"TOTAL: {len(R)} testes · {len(R)-len(falhas)} passaram · {len(falhas)} falharam")
    for f in falhas: print("  ✘", f[1], "—", f[2])
    json.dump([{"r":a,"n":b,"d":c} for a,b,c in R], open('/home/user/qa/resultados.json','w'), ensure_ascii=False, indent=1)

asyncio.run(main())
