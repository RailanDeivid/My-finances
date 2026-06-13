(function () {
  "use strict";

  // ── Formulário de Gasto: parcelas dinâmicas + filtro de cartões ──────────
  function initGastoForm() {
    var tipoPag   = document.getElementById("id_tipo_pagamento");
    var parcelasRow = document.getElementById("parcelas-row");
    var responsavelSel = document.getElementById("id_responsavel");
    var cartaoSel = document.getElementById("id_cartao");

    function toggleParcelas() {
      if (!tipoPag || !parcelasRow) return;
      parcelasRow.style.display = tipoPag.value === "credito_parcelado" ? "" : "none";
    }

    function carregarCartoes(responsavelId, selectedId) {
      if (!cartaoSel) return;
      if (!responsavelId) {
        cartaoSel.innerHTML = '<option value="">— Selecione um cartão —</option>';
        return;
      }
      fetch("/api/cartoes-por-responsavel/" + responsavelId + "/")
        .then(function (r) { return r.json(); })
        .then(function (data) {
          cartaoSel.innerHTML = '<option value="">— Selecione um cartão —</option>';
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
      tipoPag.addEventListener("change", toggleParcelas);
      toggleParcelas();
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

  // ── Modal Novo Gasto: toggle parcelas ───────────────────────────────────
  function initGastoModalForm() {
    var mgTipo = document.getElementById("mg_tipo_pagamento");
    var mgParcelasRow = document.getElementById("mg-parcelas-row");
    var mgInicioRow = document.getElementById("mg-inicio-row");
    var mgLabelValor = document.getElementById("mg_label_valor");

    function mgToggle() {
      var isParcelado = mgTipo && mgTipo.value === "credito_parcelado";
      if (mgParcelasRow) mgParcelasRow.style.display = isParcelado ? "block" : "none";
      if (mgInicioRow)   mgInicioRow.style.display   = isParcelado ? "block" : "none";
      if (mgLabelValor)  mgLabelValor.textContent     = isParcelado ? "Valor da Parcela (R$) *" : "Valor Total (R$) *";
    }

    if (mgTipo) {
      mgTipo.addEventListener("change", mgToggle);
      mgToggle();
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    initGastoForm();
    initCartaoForm();
    initMesFiltro();
    initGastoModalForm();
  });
})();
