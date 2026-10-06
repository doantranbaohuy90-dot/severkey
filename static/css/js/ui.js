// ==========================================================================
// QUẢN LÝ GIAO DIỆN
// Định nghĩa các hàm hiển thị thông báo, lớp, trạng thái tải
// ==========================================================================

const UI = (() => {

  // Danh sách thông báo đang hiển thị
  const toasts = [];

  // ------------------------------------------------------------------------
  // HIỂN THỊ THÔNG BÁO
  // ------------------------------------------------------------------------
  const toast = (message, type = 'info', duration = null) => {
    const timeout = duration || CONFIG.UI?.TOAST_DURATION || 3000;

    // Ghi log ra console
    if (CONFIG.DEBUG) {
      console.log(`[UI][${type.toUpperCase()}]`, message);
    }

    // Tạo phần tử thông báo
    const node = Utils.createEl('div', `toast toast-${type}`, message);

    // Gắn vào body
    document.body.appendChild(node);

    // Lưu vào danh sách
    toasts.push(node);

    // Tự động xóa sau thời gian
    setTimeout(() => {
      removeToast(node);
    }, timeout);

    return node;
  };

  // ------------------------------------------------------------------------
  // XÓA THÔNG BÁO
  // ------------------------------------------------------------------------
  const removeToast = (node) => {
    if (!node || !node.parentNode) return;

    // Hiệu ứng mờ dần
    node.style.opacity = '0';
    node.style.transform = 'translateY(-8px)';

    setTimeout(() => {
      if (node.parentNode) {
        node.parentNode.removeChild(node);
      }
      const index = toasts.indexOf(node);
      if (index > -1) toasts.splice(index, 1);
    }, 200);
  };

  // ------------------------------------------------------------------------
  // XÓA TẤT CẢ THÔNG BÁO
  // ------------------------------------------------------------------------
  const clearToasts = () => {
    toasts.forEach((node) => removeToast(node));
    toasts.length = 0;
  };

  // ------------------------------------------------------------------------
  // BẬT/TẮT LỚP
  // ------------------------------------------------------------------------
  const toggleClass = (target, className, force) => {
    const node = typeof target === 'string' ? Utils.qs(target) : target;
    if (node) node.classList.toggle(className, force);
  };

  // ------------------------------------------------------------------------
  // THÊM LỚP
  // ------------------------------------------------------------------------
  const addClass = (target, className) => {
    const node = typeof target === 'string' ? Utils.qs(target) : target;
    if (node) node.classList.add(className);
  };

  // ------------------------------------------------------------------------
  // XÓA LỚP
  // ------------------------------------------------------------------------
  const removeClass = (target, className) => {
    const node = typeof target === 'string' ? Utils.qs(target) : target;
    if (node) node.classList.remove(className);
  };

  // ------------------------------------------------------------------------
  // ĐẶT VĂN BẢN
  // ------------------------------------------------------------------------
  const setText = (target, text) => {
    const node = typeof target === 'string' ? Utils.el(target) : target;
    if (node) node.textContent = text;
  };

  // ------------------------------------------------------------------------
  // ĐẶT HTML
  // ------------------------------------------------------------------------
  const setHTML = (target, html) => {
    const node = typeof target === 'string' ? Utils.el(target) : target;
    if (node) node.innerHTML = html;
  };

  // ------------------------------------------------------------------------
  // BẬT TRẠNG THÁI TẢI
  // ------------------------------------------------------------------------
  const showLoading = (target) => {
    const node = typeof target === 'string' ? Utils.qs(target) : target;
    if (node) {
      node.classList.add('loading');
      node.setAttribute('aria-busy', 'true');
    }
  };

  // ------------------------------------------------------------------------
  // TẮT TRẠNG THÁI TẢI
  // ------------------------------------------------------------------------
  const hideLoading = (target) => {
    const node = typeof target === 'string' ? Utils.qs(target) : target;
    if (node) {
      node.classList.remove('loading');
      node.setAttribute('aria-busy', 'false');
    }
  };

  // ------------------------------------------------------------------------
  // HIỂN THỊ PHẦN TỬ
  // ------------------------------------------------------------------------
  const show = (target) => {
    const node = typeof target === 'string' ? Utils.qs(target) : target;
    if (node) node.style.display = '';
  };

  // ------------------------------------------------------------------------
  // ẨN PHẦN TỬ
  // ------------------------------------------------------------------------
  const hide = (target) => {
    const node = typeof target === 'string' ? Utils.qs(target) : target;
    if (node) node.style.display = 'none';
  };

  // ------------------------------------------------------------------------
  // BẬT/TẮT PHẦN TỬ
  // ------------------------------------------------------------------------
  const toggle = (target) => {
    const node = typeof target === 'string' ? Utils.qs(target) : target;
    if (!node) return;
    node.style.display = node.style.display === 'none' ? '' : 'none';
  };

  // ------------------------------------------------------------------------
  // CUỘN TỚI PHẦN TỬ
  // ------------------------------------------------------------------------
  const scrollTo = (target, smooth = true) => {
    const node = typeof target === 'string' ? Utils.qs(target) : target;
    if (node) {
      node.scrollIntoView({
        behavior: smooth ? 'smooth' : 'auto',
        block: 'start',
      });
    }
  };

  // ------------------------------------------------------------------------
  // ĐẶT THUỘC TÍNH
  // ------------------------------------------------------------------------
  const setAttr = (target, name, value) => {
    const node = typeof target === 'string' ? Utils.qs(target) : target;
    if (node) node.setAttribute(name, value);
  };

  // ------------------------------------------------------------------------
  // XÓA THUỘC TÍNH
  // ------------------------------------------------------------------------
  const removeAttr = (target, name) => {
    const node = typeof target === 'string' ? Utils.qs(target) : target;
    if (node) node.removeAttribute(name);
  };

  // ------------------------------------------------------------------------
  // VÔ HIỆU HÓA PHẦN TỬ
  // ------------------------------------------------------------------------
  const disable = (target) => {
    const node = typeof target === 'string' ? Utils.qs(target) : target;
    if (node) {
      node.disabled = true;
      node.classList.add('disabled');
    }
  };

  // ------------------------------------------------------------------------
  // KÍCH HOẠT PHẦN TỬ
  // ------------------------------------------------------------------------
  const enable = (target) => {
    const node = typeof target === 'string' ? Utils.qs(target) : target;
    if (node) {
      node.disabled = false;
      node.classList.remove('disabled');
    }
  };

  // ------------------------------------------------------------------------
  // ĐẶT TIÊU ĐIỂM
  // ------------------------------------------------------------------------
  const setFocus = (target) => {
    const node = typeof target === 'string' ? Utils.qs(target) : target;
    if (node && typeof node.focus === 'function') node.focus();
  };

  // ------------------------------------------------------------------------
  // ĐẶT THUỘC TÍNH ARIA
  // ------------------------------------------------------------------------
  const setAria = (target, name, value) => {
    const node = typeof target === 'string' ? Utils.qs(target) : target;
    if (node) node.setAttribute(`aria-${name}`, value);
  };

  // ------------------------------------------------------------------------
  // TRẢ VỀ API CÔNG KHAI
  // ------------------------------------------------------------------------
  return {
    toast,
    removeToast,
    clearToasts,
    toggleClass,
    addClass,
    removeClass,
    setText,
    setHTML,
    showLoading,
    hideLoading,
    show,
    hide,
    toggle,
    scrollTo,
    setAttr,
    removeAttr,
    disable,
    enable,
    setFocus,
    setAria,
  };
})();
