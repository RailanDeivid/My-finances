// Initializes Lucide icons for custom admin dashboard elements.
// Unfold loads this via SCRIPTS after lucide.min.js.
(function () {
  function init() { if (window.lucide) lucide.createIcons(); }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
