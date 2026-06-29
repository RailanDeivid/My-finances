(function () {
  var ONE_YEAR = 365 * 24 * 3600 * 1000;

  function setCookie(name, value) {
    var expires = new Date(Date.now() + ONE_YEAR).toUTCString();
    document.cookie =
      name + "=" + encodeURIComponent(value) +
      "; expires=" + expires +
      "; path=/; SameSite=Lax";
  }

  function getCookie(name) {
    var match = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
    return match ? decodeURIComponent(match[1]) : null;
  }

  // ── Tema ─────────────────────────────────────────────────────────────────
  function _applyTheme(theme) {
    document.body.classList.toggle("dark-theme",  theme === "dark");
    document.body.classList.toggle("light-theme", theme === "light");
    setCookie("theme", theme);
    var wrap  = document.getElementById("theme-icon-wrap");
    var label = document.getElementById("theme-label");
    if (wrap) {
      wrap.innerHTML = '<i data-lucide="' + (theme === "dark" ? "sun" : "moon") + '"></i>';
      if (typeof lucide !== "undefined") lucide.createIcons({ root: wrap });
    }
    if (label) label.textContent = theme === "dark" ? "Modo Claro" : "Modo Escuro";

    // Re-aplica cores nos gráficos Chart.js após mudança de tema
    if (typeof Chart !== "undefined" && Chart.instances) {
      var s       = getComputedStyle(document.body);
      var clrBorder = s.getPropertyValue("--border").trim()       || "#2e3040";
      var clrMuted  = s.getPropertyValue("--text-muted").trim()   || "#9a9db5";
      Object.values(Chart.instances).forEach(function (chart) {
        if (chart.options && chart.options.scales) {
          Object.values(chart.options.scales).forEach(function (scale) {
            if (scale.grid)   { scale.grid.color   = clrBorder; }
            if (scale.border) { scale.border.color = clrBorder; }
            if (scale.ticks)  { scale.ticks.color  = clrMuted;  }
          });
        }
        chart.update("none");
      });
    }
  }

  window.toggleTheme = function () {
    _applyTheme(document.body.classList.contains("dark-theme") ? "light" : "dark");
  };

  function toggleSidebar() {
    document.body.classList.toggle("sidebar-collapsed");
    var collapsed = document.body.classList.contains("sidebar-collapsed");
    setCookie("sidebar_collapsed", collapsed ? "true" : "false");
  }

  // Sidebar state — driven solely by cookie (set server-side via template)
  var cookieSidebar = getCookie("sidebar_collapsed");
  if (cookieSidebar === "true" && !document.body.classList.contains("sidebar-collapsed")) {
    document.body.classList.add("sidebar-collapsed");
  }

  function setupUserMenu() {
    var trigger = document.getElementById("user-menu-trigger");
    var dropdown = document.getElementById("user-menu-dropdown");
    if (!trigger || !dropdown) return;

    function open() {
      dropdown.classList.add("open");
      trigger.setAttribute("aria-expanded", "true");
      dropdown.setAttribute("aria-hidden", "false");
    }
    function close() {
      dropdown.classList.remove("open");
      trigger.setAttribute("aria-expanded", "false");
      dropdown.setAttribute("aria-hidden", "true");
    }
    function isOpen() {
      return dropdown.classList.contains("open");
    }

    trigger.addEventListener("click", function (e) {
      e.stopPropagation();
      if (isOpen()) close(); else open();
    });

    document.addEventListener("click", function (e) {
      if (!isOpen()) return;
      if (dropdown.contains(e.target) || trigger.contains(e.target)) return;
      close();
    });

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && isOpen()) {
        close();
        trigger.focus();
      }
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    var brand = document.querySelector(".sidebar-brand[data-toggle-sidebar]");
    if (brand) brand.addEventListener("click", toggleSidebar);

    document.querySelectorAll("img[data-hide-on-error]").forEach(function (img) {
      img.addEventListener("error", function () {
        img.style.display = "none";
      });
    });

    setupUserMenu();


    if (typeof lucide !== "undefined") lucide.createIcons();
    document.body.classList.remove("preload");

    // Modal de exclusão em massa
    var modal = document.getElementById("modal-delete-all");
    if (modal) {
      modal.addEventListener("click", function (e) {
        if (e.target === modal) closeDeleteModal();
      });
    }

    // Escape fecha qualquer modal visível
    document.addEventListener("keydown", function (e) {
      if (e.key !== "Escape") return;
      ["modal-delete-all", "modal-delete-recorrente", "modal-novo-gasto", "modal-nova-entrada", "modal-perfil"].forEach(function (id) {
        var m = document.getElementById(id);
        if (m && m.style.display !== "none") {
          if (id === "modal-delete-all") closeDeleteModal();
          else if (id === "modal-delete-recorrente") closeDeleteRecorrenteModal();
          else closeFormModal(id);
        }
      });
    });

    // Tooltip da sidebar recolhida
    var sidebarTip = document.createElement("div");
    sidebarTip.id = "sidebar-tooltip";
    document.body.appendChild(sidebarTip);

    // Navegação da sidebar: AJAX se disponível, senão fade + navigate
    document.querySelectorAll(".sidebar-item[href]").forEach(function (item) {
      item.addEventListener("click", function (e) {
        var href = item.getAttribute("href");
        if (!href || href === "#" || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
        e.preventDefault();
        if (typeof window.ajaxNavigate === "function") {
          window.ajaxNavigate(href);
        } else {
          window.location.href = href;
        }
      });
    });

    // Botão voltar/avançar do browser
    window.addEventListener("popstate", function () {
      if (typeof window.ajaxNavigate === "function") {
        window.ajaxNavigate(window.location.href);
      } else {
        window.location.reload();
      }
    });

    document.querySelectorAll(".sidebar-item").forEach(function (item) {
      var textEl = item.querySelector(".sidebar-text");
      if (!textEl) return;

      item.addEventListener("mouseenter", function () {
        if (!document.body.classList.contains("sidebar-collapsed")) return;
        var label = textEl.textContent.trim();
        if (!label) return;
        var rect = item.getBoundingClientRect();
        sidebarTip.textContent = label;
        sidebarTip.style.top  = Math.round(rect.top + rect.height / 2 - 14) + "px";
        sidebarTip.style.left = Math.round(rect.right + 10) + "px";
        sidebarTip.classList.add("visible");
      });

      item.addEventListener("mouseleave", function () {
        sidebarTip.classList.remove("visible");
      });
    });

    // Impede fechamento dos modais de formulário ao clicar no backdrop
    ["modal-novo-gasto", "modal-nova-entrada", "modal-perfil"].forEach(function (id) {
      var el = document.getElementById(id);
      if (!el) return;
      el.addEventListener("click", function (e) {
        e.stopPropagation();
      });
      el.addEventListener("mousedown", function (e) {
        if (e.target === el) e.preventDefault();
      });
    });
  });

  window.openFormModal = function (id, opts) {
    var modal = document.getElementById(id);
    if (!modal) return;
    modal.style.display = "flex";
    modal.removeAttribute("aria-hidden");
    // Atualiza campo 'next' com a URL atual do browser (AJAX altera a URL sem recarregar)
    var nextInput = modal.querySelector('input[name="next"]');
    if (nextInput) nextInput.value = window.location.pathname + window.location.search;
    if (id === "modal-novo-gasto" && typeof window.mgFecharNovaCategoria === "function") {
      window.mgFecharNovaCategoria();
    }
    if (id === "modal-nova-entrada") {
      var chkRec = modal.querySelector('#me_recorrente');
      if (chkRec) { chkRec.checked = false; }
      if (typeof window.meToggleRecorrente === "function") window.meToggleRecorrente(false);
    }
    if (typeof lucide !== "undefined") lucide.createIcons();

    // Foca o primeiro campo do formulário ou o botão fechar
    var firstFocusable = modal.querySelector("input:not([type='hidden']), select, textarea, button");
    if (firstFocusable) firstFocusable.focus();

    var now = new Date();
    var today = now.toISOString().split("T")[0];

    modal.querySelectorAll("input[type='date']").forEach(function (inp) {
      if (!inp.value) inp.value = today;
    });

    // Mês de início das parcelas: próximo mês em relação à data da compra
    var selMes = modal.querySelector("#mg_mes_inicio");
    var selAno = modal.querySelector("#mg_ano_inicio");
    var inpDataModal = modal.querySelector("#mg_data_compra");
    var baseDate = (inpDataModal && inpDataModal.value) ? new Date(inpDataModal.value + 'T00:00:00') : now;
    var proxMes = new Date(baseDate.getFullYear(), baseDate.getMonth() + 1, 1);
    if (selMes) selMes.value = proxMes.getMonth() + 1;
    if (selAno) selAno.value = proxMes.getFullYear();

    if (id === "modal-novo-gasto") {
      var mgTipo = modal.querySelector("#mg_tipo_pagamento");
      // Pré-seleção opcional via opts (ex: botão Novo Gasto dentro de detalhe do cartão)
      if (opts && opts.cartao) {
        var selCartao = modal.querySelector("#mg_cartao");
        if (selCartao) selCartao.value = opts.cartao;
      }
      if (opts && opts.tipo && mgTipo) {
        mgTipo.value = opts.tipo;
      }
      // Sincroniza layout com o tipo atual — mostra/oculta bloco de mês e parcelas
      if (mgTipo && typeof window.mgGastoTipoToggle === "function") {
        window.mgGastoTipoToggle(mgTipo.value);
      }
      // Garante "Dividir gastos" fechado ao abrir
      var chkDiv = modal.querySelector("#mg_dividir_gasto");
      var divOpc = modal.querySelector("#mg-dividir-opcoes");
      if (chkDiv) chkDiv.checked = false;
      if (divOpc) divOpc.style.display = "none";
    }
  };

  window.closeFormModal = function (id) {
    var modal = document.getElementById(id);
    if (modal) { modal.style.display = "none"; modal.setAttribute("aria-hidden", "true"); }
  };

  window.openDeleteModal = function (action, msg, titulo, btnLabel, btnIcon) {
    var modal = document.getElementById("modal-delete-all");
    if (!modal) return;
    document.getElementById("modal-delete-msg").textContent = msg;
    document.getElementById("modal-delete-form").action = action;
    var nextInput = document.getElementById("modal-delete-next");
    if (nextInput) nextInput.value = window.location.pathname + window.location.search;
    var titleEl = document.getElementById("modal-delete-title");
    if (titleEl) titleEl.textContent = titulo || "Excluir tudo?";
    var confirmBtn = document.getElementById("modal-delete-confirm-btn");
    if (confirmBtn) {
      var icon = btnIcon || "trash-2";
      var label = btnLabel || "Confirmar exclusão";
      confirmBtn.innerHTML = '<i data-lucide="' + icon + '"></i> ' + label;
      if (typeof lucide !== "undefined") lucide.createIcons({ root: confirmBtn });
    }
    modal.style.display = "flex";
    modal.removeAttribute("aria-hidden");
    modal.querySelector("button[data-cancel]").focus();
  };

  window.closeDeleteModal = function () {
    var modal = document.getElementById("modal-delete-all");
    if (modal) { modal.style.display = "none"; modal.setAttribute("aria-hidden", "true"); }
  };

  window.openDeleteRecorrenteModal = function (action, descricao) {
    var modal = document.getElementById("modal-delete-recorrente");
    if (!modal) return;
    var desc = document.getElementById("modal-rec-desc");
    if (desc) desc.textContent = 'Deseja excluir "' + descricao + '"?';
    var next = window.location.pathname + window.location.search;
    ["modal-rec-form-este", "modal-rec-form-proximos"].forEach(function (id) {
      var f = document.getElementById(id);
      if (f) f.action = action;
    });
    var n1 = document.getElementById("modal-rec-next");
    var n2 = document.getElementById("modal-rec-next2");
    if (n1) n1.value = next;
    if (n2) n2.value = next;
    modal.style.display = "flex";
    modal.removeAttribute("aria-hidden");
    if (typeof lucide !== "undefined") lucide.createIcons({ root: modal });
  };

  window.closeDeleteRecorrenteModal = function () {
    var modal = document.getElementById("modal-delete-recorrente");
    if (modal) { modal.style.display = "none"; modal.setAttribute("aria-hidden", "true"); }
  };

  window.toggleSenha = function (id, btn) {
    var inp = document.getElementById(id);
    if (!inp) return;
    var mostrar = inp.type === "password";
    inp.type = mostrar ? "text" : "password";
    btn.querySelector("i").setAttribute("data-lucide", mostrar ? "eye-off" : "eye");
    if (typeof lucide !== "undefined") lucide.createIcons();
  };

  // ── Ordenação de colunas (client-side) ───────────────────────────────────
  // Ativa ao clicar em <th> dentro de .tabela-dados. Suporta bidirecional (↑/↓).
  (function () {
    function cellVal(td) {
      var txt = td.textContent.trim();
      // Data dd/mm/yyyy — verificada antes de numeric para evitar parseFloat("12/...") = 12
      var dm = txt.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
      if (dm) return parseInt(dm[3] + dm[2] + dm[1]); // YYYYMMDD
      // Numérico BRL: "R$ 1.234,56" → 1234.56
      var brl = txt.replace(/R\$\s*/g, "").replace(/\./g, "").replace(",", ".");
      var n = parseFloat(brl);
      if (!isNaN(n)) return n;
      return txt.toLowerCase();
    }

    function sortTable(th) {
      var table = th.closest("table");
      if (!table) return;
      var tbody = table.querySelector("tbody");
      if (!tbody) return;
      var ths = Array.from(th.parentElement.querySelectorAll("th"));
      var col = ths.indexOf(th);
      var rows = Array.from(tbody.querySelectorAll("tr")).filter(function (r) {
        return r.querySelector("td") && !r.querySelector("td[colspan]");
      });
      if (!rows.length) return;

      var asc = th.dataset.sortDir !== "asc";
      ths.forEach(function (t) {
        t.dataset.sortDir = "";
        t.classList.remove("sort-asc", "sort-desc");
        var si = t.querySelector(".sort-icon");
        if (si) { si.textContent = "⇅"; si.classList.remove("sort-ativo"); }
      });
      th.dataset.sortDir = asc ? "asc" : "desc";
      th.classList.add(asc ? "sort-asc" : "sort-desc");
      var ico = th.querySelector(".sort-icon");
      if (ico) { ico.textContent = asc ? "↑" : "↓"; ico.classList.add("sort-ativo"); }

      rows.sort(function (a, b) {
        var tds = a.querySelectorAll("td");
        var tds2 = b.querySelectorAll("td");
        if (!tds[col] || !tds2[col]) return 0;
        var va = cellVal(tds[col]);
        var vb = cellVal(tds2[col]);
        if (va < vb) return asc ? -1 : 1;
        if (va > vb) return asc ? 1 : -1;
        return 0;
      });
      rows.forEach(function (r) { tbody.appendChild(r); });
    }

    document.addEventListener("click", function (e) {
      var th = e.target.closest("th");
      if (!th) return;
      var table = th.closest("table.tabela-dados");
      if (!table) return;
      // Não sorteia colunas sem texto real (botões de ação)
      if (!th.textContent.replace(/[⇅↑↓]/g, "").trim()) return;
      sortTable(th);
    });
  }());

  // ── Utilitários globais ───────────────────────────────────────────────────
  window.MESES = [
    'Janeiro','Fevereiro','Março','Abril','Maio','Junho',
    'Julho','Agosto','Setembro','Outubro','Novembro','Dezembro'
  ];

  window.formatBRL = function (value) {
    return 'R$ ' + Number(value).toLocaleString('pt-BR', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    });
  };
})();
