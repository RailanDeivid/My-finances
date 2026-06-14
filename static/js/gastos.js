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

  // ── Modal Novo Gasto: toggle inicial via função definida no template ────
  function initGastoModalForm() {
    var mgTipo = document.getElementById("mg_tipo_pagamento");
    if (mgTipo && typeof mgGastoTipoToggle === "function") {
      mgGastoTipoToggle(mgTipo.value);
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    initGastoForm();
    initCartaoForm();
    initMesFiltro();
    initGastoModalForm();
  });
})();
