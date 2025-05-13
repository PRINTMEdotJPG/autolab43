document.addEventListener('DOMContentLoaded', () => {
  console.log('[MAIN] DOM loaded');
  
  // Инициализация Bootstrap компонентов
  if (typeof bootstrap !== 'undefined') {
      const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
      tooltipTriggerList.map(function (tooltipTriggerEl) {
          return new bootstrap.Tooltip(tooltipTriggerEl);
      });
  }
});