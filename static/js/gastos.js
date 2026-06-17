(function () {
  "use strict";

  var TIPOS_CARTAO = ["credito_avista", "credito_parcelado"];

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

  // ── Filtro de mês/ano: submete ao mudar ──────────────────────────────────
  function initMesFiltro() {
    document.querySelectorAll(".auto-submit").forEach(function (el) {
      el.addEventListener("change", function () {
        el.closest("form").submit();
      });
    });
  }

  // ── Modal Novo Gasto ─────────────────────────────────────────────────────
  var _mgMeses = ['Janeiro','Fevereiro','Março','Abril','Maio','Junho','Julho','Agosto','Setembro','Outubro','Novembro','Dezembro'];

  window.mgGastoTipoToggle = function (tipo) {
    var TIPOS_C = ['credito_avista', 'credito_parcelado'];
    var isC = TIPOS_C.indexOf(tipo) !== -1;
    var isP = tipo === 'credito_parcelado';
    var isD = tipo === 'debito';
    var el;
    el = document.getElementById('mg-cartao-row');       if (el) el.style.display = isC ? 'block' : 'none';
    el = document.getElementById('mg-conta-origem-row'); if (el) el.style.display = isD ? 'block' : 'none';
    el = document.getElementById('mg-parcelas-row');     if (el) el.style.display = isP ? 'block' : 'none';
    el = document.getElementById('mg-inicio-row');       if (el) el.style.display = isP ? 'block' : 'none';
    el = document.getElementById('mg_label_valor');      if (el) el.textContent   = isP ? 'Valor da Parcela (R$) *' : 'Valor Total (R$) *';
    var dataRow = document.getElementById('mg-data-row');
    if (dataRow) {
      dataRow.style.gridColumn = isP ? '1 / -1' : '2';
      dataRow.style.gridRow    = isP ? '2'       : '1';
    }
    mgAtualizarTotal();
    mgAtualizarPreview();
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
      el.textContent = '💳 Total da compra: R$ ' + total.toLocaleString('pt-BR', {minimumFractionDigits:2}) +
                       '  (' + n + 'x de R$ ' + v.toLocaleString('pt-BR', {minimumFractionDigits:2}) + ')';
      el.style.display = 'block';
    } else {
      el.style.display = 'none';
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
      var fmt = function(x) { return 'R$ ' + x.toLocaleString('pt-BR', {minimumFractionDigits:2, maximumFractionDigits:2}); };
      if (valMeuEl)   valMeuEl.textContent   = fmt(vMeu);
      if (valOutroEl) valOutroEl.textContent = fmt(vOutro);
      previewDiv.style.display = 'grid';
    } else if (previewDiv) {
      previewDiv.style.display = 'none';
    }
  };

  function initGastoModal() {
    var mgTipo = document.getElementById("mg_tipo_pagamento");
    if (mgTipo) mgGastoTipoToggle(mgTipo.value);

    var inp  = document.getElementById('mg_valor_total');
    var parc = document.getElementById('mg_total_parcelas');
    var selR = document.getElementById('mg_responsavel');
    var chkD = document.getElementById('mg_dividir_gasto');
    if (inp)  inp.addEventListener('input',  function() { mgAtualizarTotal(); if (chkD && chkD.checked) mgAtualizarDivisao(); });
    if (parc) parc.addEventListener('input', function() { mgAtualizarTotal(); mgAtualizarPreview(); });
    if (selR) selR.addEventListener('change',function() { if (chkD && chkD.checked) mgAtualizarDivisao(); });

    var now  = new Date();
    var selM = document.getElementById('mg_mes_inicio');
    var selA = document.getElementById('mg_ano_inicio');
    if (selM) selM.value = now.getMonth() + 1;
    if (selA) selA.value = now.getFullYear();
  }

  document.addEventListener("DOMContentLoaded", function () {
    initGastoForm();
    initCartaoForm();
    initMesFiltro();
    initGastoModal();
  });
})();
