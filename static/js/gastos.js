(function () {
  "use strict";

  var TIPOS_CARTAO = ["credito_avista", "credito_parcelado", "recorrente"];

  // ── Formulário de Gasto: parcelas dinâmicas + filtro de cartões ──────────
  function initGastoForm() {
    var tipoPag        = document.getElementById("id_tipo_pagamento");
    var parcelasRow    = document.getElementById("parcelas-row");
    var cartaoRow      = document.getElementById("cartao-row");
    var responsavelSel = document.getElementById("id_responsavel");
    var cartaoSel      = document.getElementById("id_cartao");

    function isCartaoTipo() {
      return tipoPag && TIPOS_CARTAO.indexOf(tipoPag.value) !== -1;
    }

    function toggleTipo() {
      if (!tipoPag) return;
      if (parcelasRow)
        parcelasRow.style.display = tipoPag.value === "credito_parcelado" ? "" : "none";
      if (cartaoRow)
        cartaoRow.style.display = isCartaoTipo() ? "" : "none";
    }

    function carregarCartoes(responsavelId, selectedId) {
      if (!cartaoSel) return;
      var empty = '<option value="">— Sem cartão —</option>';
      if (!responsavelId || !isCartaoTipo()) {
        cartaoSel.innerHTML = empty;
        return;
      }
      fetch("/api/cartoes-por-responsavel/" + responsavelId + "/")
        .then(function (r) { return r.json(); })
        .then(function (data) {
          cartaoSel.innerHTML = empty;
          data.forEach(function (c) {
            var opt = document.createElement("option");
            opt.value = c.id;
            opt.textContent = c.nome + " (" + (c.tipo === "credito" ? "Crédito" : "Débito") + ")";
            if (selectedId && String(c.id) === String(selectedId)) opt.selected = true;
            cartaoSel.appendChild(opt);
          });
        });
    }

    if (tipoPag) {
      tipoPag.addEventListener("change", function () {
        toggleTipo();
        if (responsavelSel && responsavelSel.value) {
          carregarCartoes(responsavelSel.value, null);
        }
      });
      toggleTipo();
    }

    if (responsavelSel) {
      var currentCartaoId = cartaoSel ? cartaoSel.dataset.selectedId : null;
      responsavelSel.addEventListener("change", function () {
        carregarCartoes(responsavelSel.value, null);
      });
      if (responsavelSel.value) {
        carregarCartoes(responsavelSel.value, currentCartaoId);
      }
    }
  }

  // ── Formulário de Cartão: dia_fechamento só aparece para crédito ──────────
  function initCartaoForm() {
    var tipoCartao = document.getElementById("id_tipo");
    var fechRow    = document.getElementById("fechamento-row");

    function toggleFechamento() {
      if (!tipoCartao || !fechRow) return;
      fechRow.style.display = tipoCartao.value === "credito" ? "" : "none";
    }

    if (tipoCartao) {
      tipoCartao.addEventListener("change", toggleFechamento);
      toggleFechamento();
    }
  }

  // ── AJAX: troca conteúdo sem recarregar a página ─────────────────────────
  function _execScripts(container) {
    container.querySelectorAll("script").forEach(function (s) {
      var ns = document.createElement("script");
      ns.textContent = s.textContent;
      document.head.appendChild(ns);
      document.head.removeChild(ns);
    });
  }

  function _destroyCharts(container) {
    if (typeof Chart === "undefined" || !Chart.getChart) return;
    container.querySelectorAll("canvas").forEach(function (canvas) {
      var c = Chart.getChart(canvas);
      if (c) c.destroy();
    });
  }

  function _injectPageAssets(doc) {
    // ── Estilos do <head> ({% block extra_head %}) ────────────────────────
    document.querySelectorAll("style[data-ajax-page]").forEach(function (el) { el.remove(); });
    doc.querySelectorAll("head style").forEach(function (style) {
      var s = document.createElement("style");
      s.textContent = style.textContent;
      s.setAttribute("data-ajax-page", "1");
      document.head.appendChild(s);
    });

    // ── Scripts do body fora do main-content ({% block extra_js %}) ───────
    // Processa em sequência: scripts externos aguardam onload antes do próximo,
    // evitando que scripts inline executem antes de bibliotecas externas (Chart.js).
    var scripts = Array.from(doc.querySelectorAll("body > script"));

    function runNext(i) {
      if (i >= scripts.length) return;
      var script = scripts[i];
      var ns = document.createElement("script");
      if (script.src) {
        var existing = document.querySelector('script[data-ajax-src="' + script.src + '"]');
        if (existing) { runNext(i + 1); return; }
        ns.setAttribute("data-ajax-src", script.src);
        ns.src = script.src;
        ns.onload  = function () { runNext(i + 1); };
        ns.onerror = function () { runNext(i + 1); };
        document.head.appendChild(ns);
      } else {
        ns.textContent = script.textContent;
        document.head.appendChild(ns);
        document.head.removeChild(ns);
        runNext(i + 1);
      }
    }

    runNext(0);
  }

  function ajaxNavigate(url) {
    var mc = document.querySelector(".main-content");
    if (!mc) { window.location.href = url; return; }

    // Só aplica dim se a requisição demorar >250ms — evita piscar em respostas rápidas
    var dimTimer = setTimeout(function () {
      mc.style.opacity = "0.88";
      mc.style.pointerEvents = "none";
    }, 250);

    fetch(url, { headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (r) {
        if (!r.ok) throw new Error(r.status);
        return r.text();
      })
      .then(function (html) {
        clearTimeout(dimTimer);
        var doc = new DOMParser().parseFromString(html, "text/html");
        var newMc = doc.querySelector(".main-content");
        if (!newMc) { window.location.href = url; return; }

        _destroyCharts(mc);
        mc.innerHTML = newMc.innerHTML;
        history.pushState(null, "", url);

        // Injeta estilos e scripts específicos da nova página
        _injectPageAssets(doc);

        // Scripts dentro do main-content
        _execScripts(mc);

        // Atualiza título na topbar e na aba do browser
        var newTopbar = doc.querySelector(".topbar-title");
        var curTopbar = document.querySelector(".topbar-title");
        if (newTopbar && curTopbar) curTopbar.innerHTML = newTopbar.innerHTML;
        var newTitle = doc.querySelector("title");
        if (newTitle) document.title = newTitle.textContent;

        // Atualiza item ativo na sidebar
        var activeHrefs = new Set();
        doc.querySelectorAll(".sidebar-item.active").forEach(function (el) {
          var h = el.getAttribute("href");
          if (h) activeHrefs.add(h);
        });
        document.querySelectorAll(".sidebar-item").forEach(function (el) {
          el.classList.toggle("active", activeHrefs.has(el.getAttribute("href") || ""));
        });

        // Re-init ícones e handlers do novo conteúdo
        if (typeof lucide !== "undefined") lucide.createIcons();
        initMesFiltro();
        initTableSort();
        initGastoForm();
        initCartaoForm();
        _injectNextParam();

        mc.style.opacity = "";
        mc.style.pointerEvents = "";
      })
      .catch(function () {
        clearTimeout(dimTimer);
        window.location.href = url;
      });
  }

  window.ajaxNavigate = ajaxNavigate;

  // ── Filtros: AJAX sem recarregar a página ─────────────────────────────────
  function initMesFiltro() {
    // Selects com auto-submit
    document.querySelectorAll(".auto-submit").forEach(function (el) {
      el.addEventListener("change", function () {
        var form = el.closest("form");
        if (!form) return;
        var params = new URLSearchParams(new FormData(form));
        var action = form.getAttribute("action") || window.location.pathname;
        ajaxNavigate(action + "?" + params.toString());
      });
    });

    // Formulários GET com submit button (busca por texto, etc.)
    document.querySelectorAll('form[method="get"], form:not([method])').forEach(function (form) {
      if (form.dataset.ajaxBound) return;
      form.dataset.ajaxBound = "1";
      form.addEventListener("submit", function (e) {
        e.preventDefault();
        var params = new URLSearchParams(new FormData(form));
        var action = form.getAttribute("action") || window.location.pathname;
        ajaxNavigate(action + "?" + params.toString());
      });
    });

    // Links "Limpar" dentro de formulários
    document.querySelectorAll("form a[href]").forEach(function (link) {
      var href = link.getAttribute("href");
      if (!href || /^(https?:\/\/|\/\/)/.test(href) || href.startsWith("#")) return;
      if (link.dataset.ajaxBound) return;
      link.dataset.ajaxBound = "1";
      link.addEventListener("click", function (e) {
        if (e.ctrlKey || e.metaKey || e.shiftKey) return;
        e.preventDefault();
        ajaxNavigate(href);
      });
    });
  }

  // ── Modal Novo Gasto ─────────────────────────────────────────────────────
  var _mgMeses = window.MESES || ['Janeiro','Fevereiro','Março','Abril','Maio','Junho','Julho','Agosto','Setembro','Outubro','Novembro','Dezembro'];

  function _mgSetDisabled(id, disabled) {
    var el = document.getElementById(id);
    if (el) el.disabled = disabled;
  }

  function _show(id, visible) {
    var el = document.getElementById(id);
    if (el) el.style.display = visible ? 'block' : 'none';
  }

  window.mgGastoTipoToggle = function (tipo) {
    var TIPOS_C = TIPOS_CARTAO;
    var isRec    = tipo === 'recorrente';
    var isAjuste = tipo === 'ajuste_fatura';
    var isC      = TIPOS_C.indexOf(tipo) !== -1 || isRec;
    var isP      = tipo === 'credito_parcelado';
    var isA      = tipo === 'credito_avista';
    var isD      = tipo === 'debito';
    var isPix    = tipo === 'pix';
    var isEmp    = tipo === 'emprestimo';
    var el;

    _show('mg-responsavel-row',      !isAjuste);
    _show('mg-cartao-row',           isC || isAjuste);
    _show('mg-cartao-adicional-row', isC || isAjuste);
    _show('mg-ajuste-tipo-row',      isAjuste);
    _show('mg-conta-origem-row',     isD);
    _show('mg-parcelas-row',         isP);
    _show('mg-inicio-row',           isP || isA || isRec || isAjuste || isPix || isEmp);

    var inicioTxt = isA ? 'Mês da Fatura'
      : isRec    ? 'Mês de início'
      : isAjuste ? 'Mês da Fatura'
      : isPix    ? 'Mês do PIX/Transferência'
      : isEmp    ? 'Mês de início do empréstimo'
      : 'Mês de início das parcelas';
    el = document.getElementById('mg-inicio-label');  if (el) el.textContent = inicioTxt;
    el = document.getElementById('mg_label_valor');   if (el) el.textContent = isP ? 'Valor da Parcela (R$) *' : 'Valor (R$) *';

    // Desabilita campos ocultos para evitar validação HTML5 em campos escondidos
    _mgSetDisabled('mg_responsavel',   isAjuste);
    _mgSetDisabled('mg_cartao',        !(isC || isAjuste));
    _mgSetDisabled('mg_conta_origem',  !isD);
    _mgSetDisabled('mg_total_parcelas',!isP);
    _mgSetDisabled('mg_mes_inicio',    !(isP || isA || isRec || isAjuste || isPix || isEmp));
    _mgSetDisabled('mg_ano_inicio',    !(isP || isA || isRec || isAjuste || isPix || isEmp));
    _mgSetDisabled('mg_ajuste_tipo',   !isAjuste);

    var dataRow = document.getElementById('mg-data-row');
    if (dataRow) {
      if (isAjuste || isPix || isEmp) {
        dataRow.style.display = 'none';
        mgSyncDataFromFatura();
      } else {
        dataRow.style.display = '';
        dataRow.style.gridColumn = isP ? '1 / -1' : '2';
        dataRow.style.gridRow    = isP ? '2'       : '1';
      }
    }
    // Toggle recorrente para PIX / Empréstimo / Débito
    var pixEmpRecWrapper = document.getElementById('mg-pix-emp-rec-wrapper');
    var pixEmpRecChk     = document.getElementById('mg_pix_emp_rec_chk');
    var _mgTemToggle = isPix || isEmp || isD;
    if (pixEmpRecWrapper) pixEmpRecWrapper.style.display = _mgTemToggle ? 'block' : 'none';
    if (!_mgTemToggle && pixEmpRecChk) pixEmpRecChk.checked = false;
    var pixEmpRecAtivo = _mgTemToggle && pixEmpRecChk && pixEmpRecChk.checked;

    var recWrapper = document.getElementById('mg-recorrente-wrapper');
    var chkR = document.getElementById('mg_recorrente');
    if (recWrapper) recWrapper.style.display = (isRec || pixEmpRecAtivo) ? 'block' : 'none';
    if (chkR) chkR.checked = isRec || pixEmpRecAtivo;
    if (isRec || pixEmpRecAtivo) mgAtualizarRecorrenteInfo();
    mgAtualizarTotal();
    mgAtualizarPreview();
  };

  window.mgTogglePixEmpRec = function(checked) {
    var recWrapper = document.getElementById('mg-recorrente-wrapper');
    var chkR       = document.getElementById('mg_recorrente');
    if (recWrapper) recWrapper.style.display = checked ? 'block' : 'none';
    if (chkR) chkR.checked = checked;
    if (checked) mgAtualizarRecorrenteInfo();
  };

  var _MG_TIPOS_SEM_DATA = ['ajuste_fatura', 'pix', 'emprestimo'];
  window.mgSyncDataFromFatura = function () {
    var tipo = document.getElementById('mg_tipo_pagamento');
    if (!tipo || _MG_TIPOS_SEM_DATA.indexOf(tipo.value) === -1) return;
    var mes = parseInt((document.getElementById('mg_mes_inicio') || {}).value || 0);
    var ano = parseInt((document.getElementById('mg_ano_inicio') || {}).value || 0);
    var input = document.getElementById('mg_data_compra');
    if (mes && ano && input) {
      input.value = ano + '-' + String(mes).padStart(2, '0') + '-01';
    }
  };

  window.mgAtualizarPreview = function () {
    var tipo    = document.getElementById('mg_tipo_pagamento');
    var preview = document.getElementById('mg-preview-parcelas');
    if (!preview) return;
    if (!tipo || tipo.value !== 'credito_parcelado') { preview.style.display = 'none'; return; }
    var mes = parseInt((document.getElementById('mg_mes_inicio') || {}).value || 0) || 0;
    var ano = parseInt((document.getElementById('mg_ano_inicio') || {}).value || 0) || 0;
    var n   = parseInt((document.getElementById('mg_total_parcelas') || {}).value || 0) || 0;
    if (!mes || !ano) { preview.style.display = 'none'; return; }
    var pp    = document.getElementById('mg-pp-primeira');
    var arrow = document.getElementById('mg-pp-arrow');
    var pu    = document.getElementById('mg-pp-ultima');
    var pt    = document.getElementById('mg-pp-total');
    if (pp) pp.textContent = '1ª parcela: ' + _mgMeses[mes - 1] + '/' + ano;
    if (n > 0) {
      var mU = ((mes - 1 + n - 1) % 12) + 1;
      var aU = ano + Math.floor((mes - 1 + n - 1) / 12);
      if (arrow) arrow.style.display = '';
      if (pu) { pu.textContent = 'Última: ' + _mgMeses[mU - 1] + '/' + aU; pu.style.display = ''; }
      if (pt) { pt.textContent = n + 'x no total'; pt.style.display = ''; }
    } else {
      if (arrow) arrow.style.display = 'none';
      if (pu) { pu.textContent = ''; pu.style.display = 'none'; }
      if (pt) { pt.textContent = ''; pt.style.display = 'none'; }
    }
    preview.style.display = 'flex';
  };

  window.mgAtualizarTotal = function () {
    var tipo = document.getElementById('mg_tipo_pagamento');
    var el   = document.getElementById('mg-total-calculado');
    if (!el) return;
    if (!tipo || tipo.value !== 'credito_parcelado') { el.style.display = 'none'; return; }
    var v = parseFloat((document.getElementById('mg_valor_total') || {}).value || 0) || 0;
    var n = parseInt((document.getElementById('mg_total_parcelas') || {}).value || 0, 10) || 0;
    if (v > 0 && n > 0) {
      var total = v * n;
      el.textContent = '💳 Total da compra: ' + window.formatBRL(total) +
                       '  (' + n + 'x de ' + window.formatBRL(v) + ')';
      el.style.display = 'block';
    } else {
      el.style.display = 'none';
    }
  };

  window.mgToggleRecorrente = function (checked) {
    var el = document.getElementById('mg-recorrente-opcoes');
    if (el) el.style.display = checked ? 'block' : 'none';
    if (checked) mgAtualizarRecorrenteInfo();
  };

  window.mgAtualizarRecorrenteInfo = function () {
    var sel = document.getElementById('mg_recorrente_meses');
    var txt = document.getElementById('mg-recorrente-info-txt');
    if (!sel || !txt) return;
    var val = sel.value;
    if (val === 'sempre') {
      txt.textContent = 'Um gasto será gerado todo mês até dezembro de 2050.';
    } else {
      txt.textContent = 'Um gasto será gerado para cada um dos próximos ' + val + ' meses.';
    }
  };

  window.mgToggleDividir = function (checked) {
    var el = document.getElementById('mg-dividir-opcoes');
    if (el) el.style.display = checked ? 'block' : 'none';
    if (checked) mgAtualizarDivisao();
  };

  window.mgAtualizarDivisao = function () {
    var selPct   = document.getElementById('mg_pct_responsavel');
    var selCom   = document.getElementById('mg_dividir_com');
    var selResp  = document.getElementById('mg_responsavel');
    var pctMeu   = parseInt(selPct ? selPct.value : 50, 10) || 50;
    var pctOutro = 100 - pctMeu;
    var pctOutroEl = document.getElementById('mg_pct_outro_display');
    var barraEl    = document.getElementById('mg_barra_pct');
    var labelCom   = document.getElementById('mg_label_dividir_com');
    var labelMeu   = document.getElementById('mg_label_preview_meu');
    var labelOutro = document.getElementById('mg_label_preview_outro');
    var valMeuEl   = document.getElementById('mg_valor_preview_meu');
    var valOutroEl = document.getElementById('mg_valor_preview_outro');
    var previewDiv = document.getElementById('mg-divisao-preview');
    var inputVal   = document.getElementById('mg_valor_total');
    if (pctOutroEl) pctOutroEl.textContent = pctOutro + '%';
    if (barraEl)    barraEl.style.width    = pctMeu + '%';
    var nomeCom  = selCom  && selCom.selectedIndex  > 0 ? selCom.options[selCom.selectedIndex].text.trim()  : 'Outro';
    var nomeResp = selResp && selResp.selectedIndex > 0 ? selResp.options[selResp.selectedIndex].text.trim() : 'Você';
    if (labelCom)   labelCom.textContent   = nomeCom;
    if (labelMeu)   labelMeu.textContent   = nomeResp + ' (' + pctMeu   + '%)';
    if (labelOutro) labelOutro.textContent = nomeCom  + ' (' + pctOutro + '%)';
    var val = parseFloat((inputVal ? inputVal.value : '0').replace(',', '.')) || 0;
    if (val > 0 && previewDiv) {
      var vMeu   = Math.round(val * pctMeu / 100 * 100) / 100;
      var vOutro = Math.round((val - vMeu) * 100) / 100;
      if (valMeuEl)   valMeuEl.textContent   = window.formatBRL(vMeu);
      if (valOutroEl) valOutroEl.textContent = window.formatBRL(vOutro);
      previewDiv.style.display = 'grid';
    } else if (previewDiv) {
      previewDiv.style.display = 'none';
    }
  };

  // ── Nova Categoria inline ────────────────────────────────────────────────
  function _getCsrf() {
    var m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : '';
  }

  var _mgCatIconeSel = '';
  var _mgCatCorSel   = '#888888';

  window.mgCatSelecionarIcone = function (btn) {
    document.querySelectorAll('.mg-cat-icone-btn').forEach(function (b) {
      b.classList.remove('mg-selecionado');
    });
    btn.classList.add('mg-selecionado');
    _mgCatIconeSel = btn.dataset.valor;
    var hiddenIcone = document.getElementById('mg_nova_cat_icone');
    if (hiddenIcone) hiddenIcone.value = _mgCatIconeSel;
    var wrap = document.getElementById('mg-cat-preview-wrap');
    if (wrap) {
      wrap.innerHTML = '<i data-lucide="' + _mgCatIconeSel + '" style="width:18px;height:18px;stroke:#fff;"></i>';
      if (typeof lucide !== 'undefined') lucide.createIcons();
    }
  };

  window.mgCatSelecionarCor = function (el) {
    document.querySelectorAll('.mg-cat-cor-swatch').forEach(function (s) {
      s.classList.remove('mg-selecionada');
    });
    var pickerBtn = document.getElementById('mg-cat-cor-picker-btn');
    if (pickerBtn) pickerBtn.style.borderStyle = 'dashed';
    el.classList.add('mg-selecionada');
    _mgCatCorSel = el.dataset.hex;
    var hiddenCor = document.getElementById('mg_nova_cat_cor_val');
    if (hiddenCor) hiddenCor.value = _mgCatCorSel;
    var picker = document.getElementById('mg_nova_cat_cor');
    if (picker) picker.value = _mgCatCorSel;
    var wrap = document.getElementById('mg-cat-preview-wrap');
    if (wrap) wrap.style.background = _mgCatCorSel;
  };

  window.mgCatCorPersonalizada = function (hex) {
    _mgCatCorSel = hex;
    var hiddenCor = document.getElementById('mg_nova_cat_cor_val');
    if (hiddenCor) hiddenCor.value = hex;
    var wrap = document.getElementById('mg-cat-preview-wrap');
    if (wrap) wrap.style.background = hex;
    document.querySelectorAll('.mg-cat-cor-swatch').forEach(function (s) {
      s.classList.remove('mg-selecionada');
    });
    var pickerBtn = document.getElementById('mg-cat-cor-picker-btn');
    if (pickerBtn) { pickerBtn.style.borderStyle = 'solid'; pickerBtn.style.borderColor = hex; }
  };

  window.mgCatAtualizarPreviewNome = function (nome) {
    var el = document.getElementById('mg-cat-preview-nome');
    if (el) el.textContent = nome || 'Nome da categoria';
    var preset = document.getElementById('mg-cat-preset');
    if (preset) preset.value = '';
  };

  window.mgCatAplicarPreset = function (sel) {
    var opt = sel.options[sel.selectedIndex];
    if (!opt || !opt.value) return;
    var nome  = opt.value;
    var icone = opt.dataset.icone;
    var cor   = opt.dataset.cor;
    var nomeInput = document.getElementById('mg_nova_cat_nome');
    if (nomeInput) { nomeInput.value = nome; }
    var previewNome = document.getElementById('mg-cat-preview-nome');
    if (previewNome) previewNome.textContent = nome;
    if (icone) {
      var btnIcone = document.querySelector('.mg-cat-icone-btn[data-valor="' + icone + '"]');
      if (btnIcone) mgCatSelecionarIcone(btnIcone);
    }
    if (cor) {
      var swatch = document.querySelector('.mg-cat-cor-swatch[data-hex="' + cor + '"]');
      if (swatch) { mgCatSelecionarCor(swatch); }
      else { mgCatCorPersonalizada(cor); }
    }
  };

  window.mgAbrirNovaCategoria = function () {
    var form = document.getElementById('mg-nova-cat-form');
    var inp  = document.getElementById('mg_nova_cat_nome');
    var err  = document.getElementById('mg-nova-cat-erro');
    if (form) form.style.display = 'block';
    if (err)  { err.style.display = 'none'; err.textContent = ''; }
    if (inp)  { inp.value = ''; }
    // Reset preset
    var preset = document.getElementById('mg-cat-preset');
    if (preset) preset.value = '';
    // Reset preview
    var previewNome = document.getElementById('mg-cat-preview-nome');
    if (previewNome) previewNome.textContent = 'Nome da categoria';
    var previewWrap = document.getElementById('mg-cat-preview-wrap');
    if (previewWrap) {
      previewWrap.style.background = '#888888';
      previewWrap.innerHTML = '<i data-lucide="tag" style="width:18px;height:18px;stroke:#fff;"></i>';
    }
    // Reset ícone
    document.querySelectorAll('.mg-cat-icone-btn').forEach(function (b) { b.classList.remove('mg-selecionado'); });
    _mgCatIconeSel = '';
    var hiddenIcone = document.getElementById('mg_nova_cat_icone');
    if (hiddenIcone) hiddenIcone.value = '';
    // Reset cor (seleciona cinza padrão)
    _mgCatCorSel = '#888888';
    var hiddenCor = document.getElementById('mg_nova_cat_cor_val');
    if (hiddenCor) hiddenCor.value = '#888888';
    var picker = document.getElementById('mg_nova_cat_cor');
    if (picker) picker.value = '#888888';
    var pickerBtn = document.getElementById('mg-cat-cor-picker-btn');
    if (pickerBtn) pickerBtn.style.borderStyle = 'dashed';
    document.querySelectorAll('.mg-cat-cor-swatch').forEach(function (s) { s.classList.remove('mg-selecionada'); });
    var grayDefault = document.querySelector('.mg-cat-cor-swatch[data-hex="#888888"]');
    if (grayDefault) grayDefault.classList.add('mg-selecionada');
    if (typeof lucide !== 'undefined') lucide.createIcons();
    if (inp) inp.focus();
  };

  window.mgFecharNovaCategoria = function () {
    var form = document.getElementById('mg-nova-cat-form');
    if (form) form.style.display = 'none';
  };

  window.mgSalvarNovaCategoria = function () {
    var nome  = ((document.getElementById('mg_nova_cat_nome')    || {}).value || '').trim();
    var cor   = (document.getElementById('mg_nova_cat_cor_val')  || {}).value || '#888888';
    var icone = (document.getElementById('mg_nova_cat_icone')    || {}).value || '';
    var err   = document.getElementById('mg-nova-cat-erro');
    if (!nome) {
      if (err) { err.textContent = 'Digite o nome da categoria.'; err.style.display = 'block'; }
      return;
    }
    var btn = document.getElementById('mg-btn-salvar-cat');
    if (btn) { btn.disabled = true; btn.textContent = 'Salvando...'; }
    if (err) err.style.display = 'none';
    fetch('/api/categoria/criar/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': _getCsrf() },
      body: JSON.stringify({ nome: nome, cor: cor, icone: icone }),
    })
    .then(function (r) { return r.json(); })
    .then(function (data) {
      if (data.ok) {
        var sel = document.getElementById('mg_categoria');
        if (sel) {
          Array.from(sel.options).forEach(function (o) {
            if (String(o.value) === String(data.id)) sel.removeChild(o);
          });
          var opt = document.createElement('option');
          opt.value = data.id;
          opt.textContent = data.nome;
          opt.selected = true;
          sel.appendChild(opt);
        }
        mgFecharNovaCategoria();
      } else {
        if (err) { err.textContent = data.error || 'Erro ao criar categoria.'; err.style.display = 'block'; }
      }
    })
    .catch(function () {
      if (err) { err.textContent = 'Erro de conexão. Tente novamente.'; err.style.display = 'block'; }
    })
    .finally(function () {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = '<i data-lucide="check" style="width:14px;height:14px;"></i> Criar Categoria';
        if (typeof lucide !== 'undefined') lucide.createIcons();
      }
    });
  };

  function initGastoModal() {
    var mgTipo = document.getElementById("mg_tipo_pagamento");
    if (mgTipo) mgGastoTipoToggle(mgTipo.value);
    // wrapper começa oculto — mgGastoTipoToggle já cuida disso, mas garante o reset
    var recWrapper = document.getElementById('mg-recorrente-wrapper');
    var chkR = document.getElementById('mg_recorrente');
    if (recWrapper && (!mgTipo || mgTipo.value !== 'recorrente')) recWrapper.style.display = 'none';
    if (chkR && (!mgTipo || mgTipo.value !== 'recorrente')) chkR.checked = false;

    var inp  = document.getElementById('mg_valor_total');
    var parc = document.getElementById('mg_total_parcelas');
    var selR = document.getElementById('mg_responsavel');
    var chkD = document.getElementById('mg_dividir_gasto');
    if (inp)  inp.addEventListener('input',  function() { mgAtualizarTotal(); if (chkD && chkD.checked) mgAtualizarDivisao(); });
    if (parc) parc.addEventListener('input', function() { mgAtualizarTotal(); mgAtualizarPreview(); });
    if (selR) selR.addEventListener('change',function() { if (chkD && chkD.checked) mgAtualizarDivisao(); });

    var selM = document.getElementById('mg_mes_inicio');
    var selA = document.getElementById('mg_ano_inicio');
    var inpD = document.getElementById('mg_data_compra');

    function mgSincronizarInicioParc(dataVal) {
      var d = dataVal ? new Date(dataVal + 'T00:00:00') : new Date();
      var proximo = new Date(d.getFullYear(), d.getMonth() + 1, 1);
      if (selM) selM.value = proximo.getMonth() + 1;
      if (selA) selA.value = proximo.getFullYear();
      if (typeof mgAtualizarPreview === 'function') mgAtualizarPreview();
    }

    if (inpD) {
      inpD.addEventListener('change', function() { mgSincronizarInicioParc(inpD.value); });
    }
    mgSincronizarInicioParc(inpD ? inpD.value : '');
  }

  function initTableSort() {
    document.querySelectorAll(".tabela-dados").forEach(function (table) {
      if (table.dataset.sortBound) return;
      table.dataset.sortBound = "1";
      Array.from(table.querySelectorAll("thead th")).forEach(function (th) {
        if (!th.textContent.trim()) return;
        var icon = document.createElement("i");
        icon.className = "sort-icon";
        icon.textContent = "⇅";
        th.appendChild(icon);
        th.style.cursor = "pointer";
      });
    });
  }

  window.meToggleRecorrente = function (checked) {
    var hint  = document.getElementById('me_recorrente_hint');
    var label = document.getElementById('me_data_label');
    if (hint)  hint.style.display  = checked ? 'block' : 'none';
    if (label) label.textContent   = checked ? 'Mês inicial *' : 'Data *';
  };

  function _injectNextParam() {
    var mc = document.querySelector(".main-content");
    if (!mc) return;
    var current = window.location.pathname + window.location.search;
    var pattern = /\/(editar|excluir|novo|nova|atualizar-saldo|liquidar)(\/|$|\?)/;
    mc.querySelectorAll("a[href]").forEach(function (a) {
      var href = a.getAttribute("href");
      if (!href || href.charAt(0) !== "/") return;
      if (!pattern.test(href)) return;
      if (href.indexOf("next=") !== -1) return;
      a.href = href + (href.indexOf("?") !== -1 ? "&" : "?") + "next=" + encodeURIComponent(current);
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initGastoForm();
    initCartaoForm();
    initMesFiltro();
    initGastoModal();
    initTableSort();
    _injectNextParam();
  });
})();
