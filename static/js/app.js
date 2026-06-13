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

  function toggleSidebar() {
    document.body.classList.toggle("sidebar-collapsed");
    var collapsed = document.body.classList.contains("sidebar-collapsed");
    localStorage.setItem("sidebar-collapsed", collapsed);
    setCookie("sidebar_collapsed", collapsed ? "true" : "false");
  }

  // Sidebar state
  var cookieSidebar = getCookie("sidebar_collapsed");
  var lsSidebar = localStorage.getItem("sidebar-collapsed");
  var sidebarCollapsed;
  if (cookieSidebar === "true" || cookieSidebar === "false") {
    sidebarCollapsed = cookieSidebar === "true";
  } else if (lsSidebar === "true" || lsSidebar === "false") {
    sidebarCollapsed = lsSidebar === "true";
    setCookie("sidebar_collapsed", lsSidebar);
  } else {
    sidebarCollapsed = false;
  }
  if (sidebarCollapsed && !document.body.classList.contains("sidebar-collapsed")) {
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

    // Confirmações declarativas: <a data-confirm="texto"> ou <button data-confirm="...">
    document.body.addEventListener("click", function (e) {
      var el = e.target.closest("[data-confirm]");
      if (!el) return;
      var msg = el.getAttribute("data-confirm");
      if (msg && !window.confirm(msg)) {
        e.preventDefault();
        e.stopPropagation();
      }
    });

    if (typeof lucide !== "undefined") lucide.createIcons();

    // Modal de exclusão em massa
    var modal = document.getElementById("modal-delete-all");
    if (modal) {
      modal.addEventListener("click", function (e) {
        if (e.target === modal) closeDeleteModal();
      });
    }

    // Modais de formulário — fechar clicando fora ou Escape
    ["modal-novo-gasto", "modal-nova-entrada"].forEach(function (id) {
      var fm = document.getElementById(id);
      if (!fm) return;
      fm.addEventListener("click", function (e) {
        if (e.target === fm) closeFormModal(id);
      });
    });
    document.addEventListener("keydown", function (e) {
      if (e.key !== "Escape") return;
      closeDeleteModal();
      closeFormModal("modal-novo-gasto");
      closeFormModal("modal-nova-entrada");
    });
  });

  window.openFormModal = function (id) {
    var modal = document.getElementById(id);
    if (!modal) return;
    modal.style.display = "flex";
    if (typeof lucide !== "undefined") lucide.createIcons();
    var today = new Date().toISOString().split("T")[0];
    modal.querySelectorAll("input[type='date']").forEach(function (inp) {
      if (!inp.value) inp.value = today;
    });
    // Sync parcelas toggle on open
    var mgTipo = modal.querySelector("#mg_tipo_pagamento");
    if (mgTipo) mgTipo.dispatchEvent(new Event("change"));
  };

  window.closeFormModal = function (id) {
    var modal = document.getElementById(id);
    if (modal) modal.style.display = "none";
  };

  window.openDeleteModal = function (action, msg) {
    var modal = document.getElementById("modal-delete-all");
    if (!modal) return;
    document.getElementById("modal-delete-msg").textContent = msg;
    document.getElementById("modal-delete-form").action = action;
    modal.style.display = "flex";
    modal.querySelector("button[data-cancel]").focus();
  };

  window.closeDeleteModal = function () {
    var modal = document.getElementById("modal-delete-all");
    if (modal) modal.style.display = "none";
  };
})();
