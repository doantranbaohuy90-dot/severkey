// ==========================================================================
// QUẢN LÝ GIAO DIỆN
// Thông báo, lớp, trạng thái tải, thuộc tính, tiêu điểm, ARIA
// ==========================================================================

(function () {
  'use strict';

  // Tránh khai báo trùng nếu tệp được nạp hai lần
  if (window.UI) {
    console.warn('[UI] UI đã tồn tại, bỏ qua nạp lại');
    return;
  }

  var UI = (function () {

    // ======================================================================
    // TRẠNG THÁI NỘI BỘ
    // ======================================================================
    var toasts = [];
    var toastContainer = null;

    // ======================================================================
    // HÀM HỖ TRỢ NỘI BỘ
    // ======================================================================
    function log() {
      if (window.CONFIG && window.CONFIG.DEBUG) {
        console.log.apply(console, ['[UI]'].concat(Array.prototype.slice.call(arguments)));
      }
    }

    function resolve(target) {
      if (!target) return null;
      if (typeof target === 'string') {
        return document.getElementById(target) || document.querySelector(target);
      }
      return target;
    }

    function getContainer() {
      if (toastContainer && toastContainer.parentNode) return toastContainer;
      toastContainer = document.getElementById('toast-container');
      if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.id = 'toast-container';
        toastContainer.className = 'toast-container';
        document.body.appendChild(toastContainer);
      }
      return toastContainer;
    }

    // ======================================================================
    // THÔNG BÁO
    // ======================================================================
    function toast(message, type, duration) {
      type = type || 'info';
      var timeout = duration ||
        (window.CONFIG && window.CONFIG.UI && window.CONFIG.UI.TOAST_DURATION) ||
        3000;

      log('Toast', type.toUpperCase(), message);

      var node = document.createElement('div');
      node.className = 'toast toast-' + type;
      node.setAttribute('role', 'status');
      node.setAttribute('aria-live', 'polite');
      node.textContent = message;

      getContainer().appendChild(node);
      toasts.push(node);

      // Hiệu ứng xuất hiện
      requestAnimationFrame(function () {
        node.classList.add('visible');
      });

      // Tự động xóa
      setTimeout(function () { removeToast(node); }, timeout);

      return node;
    }

    function removeToast(node) {
      if (!node || !node.parentNode) return;

      node.classList.remove('visible');
      node.classList.add('leaving');

      setTimeout(function () {
        if (node.parentNode) node.parentNode.removeChild(node);
        var i = toasts.indexOf(node);
        if (i > -1) toasts.splice(i, 1);
      }, 250);
    }

    function clearToasts() {
      toasts.slice().forEach(function (node) { removeToast(node); });
    }

    // ======================================================================
    // LỚP
    // ======================================================================
    function toggleClass(target, className, force) {
      var node = resolve(target);
      if (node) node.classList.toggle(className, force);
    }

    function addClass(target, className) {
      var node = resolve(target);
      if (node) node.classList.add(className);
    }

    function removeClass(target, className) {
      var node = resolve(target);
      if (node) node.classList.remove(className);
    }

    function hasClass(target, className) {
      var node = resolve(target);
      return node ? node.classList.contains(className) : false;
    }

    // ======================================================================
    // NỘI DUNG
    // ======================================================================
    function setText(target, text) {
      var node = resolve(target);
      if (node) node.textContent = text;
    }

    function setHTML(target, html) {
      var node = resolve(target);
      if (node) node.innerHTML = html;
    }

    function getText(target) {
      var node = resolve(target);
      return node ? node.textContent : '';
    }

    // ======================================================================
    // TRẠNG THÁI TẢI
    // ======================================================================
    function showLoading(target) {
      var node = resolve(target);
      if (node) {
        node.classList.add('loading');
        node.setAttribute('aria-busy', 'true');
      }
    }

    function hideLoading(target) {
      var node = resolve(target);
      if (node) {
        node.classList.remove('loading');
        node.setAttribute('aria-busy', 'false');
      }
    }

    // ======================================================================
    // HIỂN THỊ
    // ======================================================================
    function show(target) {
      var node = resolve(target);
      if (node) {
        node.style.display = '';
        node.removeAttribute('hidden');
      }
    }

    function hide(target) {
      var node = resolve(target);
      if (node) {
        node.style.display = 'none';
      }
    }

    function toggle(target) {
      var node = resolve(target);
      if (!node) return;
      node.style.display = node.style.display === 'none' ? '' : 'none';
    }

    function isVisible(target) {
      var node = resolve(target);
      if (!node) return false;
      if (node.style.display === 'none') return false;
      if (node.hasAttribute('hidden')) return false;
      return node.offsetWidth > 0 || node.offsetHeight > 0;
    }

    // ======================================================================
    // CUỘN
    // ======================================================================
    function scrollTo(target, smooth) {
      smooth = smooth !== false;
      var node = resolve(target);
      if (node) {
        node.scrollIntoView({
          behavior: smooth ? 'smooth' : 'auto',
          block: 'start'
        });
      }
    }

    function scrollTop(smooth) {
      smooth = smooth !== false;
      window.scrollTo({
        top: 0,
        behavior: smooth ? 'smooth' : 'auto'
      });
    }

    // ======================================================================
    // THUỘC TÍNH
    // ======================================================================
    function setAttr(target, name, value) {
      var node = resolve(target);
      if (node) node.setAttribute(name, value);
    }

    function removeAttr(target, name) {
      var node = resolve(target);
      if (node) node.removeAttribute(name);
    }

    function getAttr(target, name) {
      var node = resolve(target);
      return node ? node.getAttribute(name) : null;
    }

    // ======================================================================
    // TRẠNG THÁI PHẦN TỬ
    // ======================================================================
    function disable(target) {
      var node = resolve(target);
      if (node) {
        node.disabled = true;
        node.classList.add('disabled');
        node.setAttribute('aria-disabled', 'true');
      }
    }

    function enable(target) {
      var node = resolve(target);
      if (node) {
        node.disabled = false;
        node.classList.remove('disabled');
        node.removeAttribute('aria-disabled');
      }
    }

    function isDisabled(target) {
      var node = resolve(target);
      return node ? !!node.disabled : false;
    }

    // ======================================================================
    // TIÊU ĐIỂM
    // ======================================================================
    function setFocus(target) {
      var node = resolve(target);
      if (node && typeof node.focus === 'function') {
        node.focus();
      }
    }

    function blur(target) {
      var node = resolve(target);
      if (node && typeof node.blur === 'function') {
        node.blur();
      }
    }

    // ======================================================================
    // ARIA
    // ======================================================================
    function setAria(target, name, value) {
      var node = resolve(target);
      if (node) node.setAttribute('aria-' + name, value);
    }

    function removeAria(target, name) {
      var node = resolve(target);
      if (node) node.removeAttribute('aria-' + name);
    }

    // ======================================================================
    // LỚP CSS CHUYỂN ĐỘNG
    // ======================================================================
    function fadeIn(target, duration) {
      duration = duration || 300;
      var node = resolve(target);
      if (!node) return;
      node.style.opacity = '0';
      node.style.transition = 'opacity ' + duration + 'ms ease';
      node.style.display = '';
      requestAnimationFrame(function () {
        node.style.opacity = '1';
      });
    }

    function fadeOut(target, duration) {
      duration = duration || 300;
      var node = resolve(target);
      if (!node) return;
      node.style.transition = 'opacity ' + duration + 'ms ease';
      node.style.opacity = '0';
      setTimeout(function () {
        node.style.display = 'none';
      }, duration);
    }

    // ======================================================================
    // XUẤT API CÔNG KHAI
    // ======================================================================
    return {
      // Toast
      toast: toast,
      removeToast: removeToast,
      clearToasts: clearToasts,

      // Lớp
      toggleClass: toggleClass,
      addClass: addClass,
      removeClass: removeClass,
      hasClass: hasClass,

      // Nội dung
      setText: setText,
      setHTML: setHTML,
      getText: getText,

      // Tải
      showLoading: showLoading,
      hideLoading: hideLoading,

      // Hiển thị
      show: show,
      hide: hide,
      toggle: toggle,
      isVisible: isVisible,

      // Cuộn
      scrollTo: scrollTo,
      scrollTop: scrollTop,

      // Thuộc tính
      setAttr: setAttr,
      removeAttr: removeAttr,
      getAttr: getAttr,

      // Trạng thái
      disable: disable,
      enable: enable,
      isDisabled: isDisabled,

      // Tiêu điểm
      setFocus: setFocus,
      blur: blur,

      // ARIA
      setAria: setAria,
      removeAria: removeAria,

      // Chuyển động
      fadeIn: fadeIn,
      fadeOut: fadeOut
    };
  })();

  // Xuất ra phạm vi toàn cục
  window.UI = UI;

})();
