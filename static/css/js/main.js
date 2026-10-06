// ==========================================================================
// ĐIỂM KHỞI CHẠY CHÍNH
// Tự chứa toàn bộ logic đồng hồ, con trỏ, sự kiện, không phụ thuộc tệp ngoài
// ==========================================================================

(function () {
  'use strict';

  // ========================================================================
  // CẤU HÌNH NỘI BỘ
  // ========================================================================
  var CONFIG = {
    APP_NAME: 'Hồ sơ của tôi',
    APP_VERSION: '1.0.0',
    DEBUG: false,
    REFRESH_INTERVAL: 1000,
    CURSOR_BLINK: 500,
  };

  var DAYS = [
    'SUNDAY', 'MONDAY', 'TUESDAY', 'WEDNESDAY',
    'THURSDAY', 'FRIDAY', 'SATURDAY'
  ];

  var MONTHS = [
    'JANUARY', 'FEBRUARY', 'MARCH', 'APRIL',
    'MAY', 'JUNE', 'JULY', 'AUGUST',
    'SEPTEMBER', 'OCTOBER', 'NOVEMBER', 'DECEMBER'
  ];

  // ========================================================================
  // TIỆN ÍCH
  // ========================================================================
  function pad(n) {
    return String(n).padStart(2, '0');
  }

  function el(id) {
    return document.getElementById(id);
  }

  function log() {
    if (CONFIG.DEBUG) {
      console.log.apply(console, ['[App]'].concat(Array.prototype.slice.call(arguments)));
    }
  }

  // ========================================================================
  // ĐỒNG HỒ
  // ========================================================================
  var Clock = (function () {
    var timer = null;
    var running = false;

    function update() {
      var d = new Date();
      var h = d.getHours();
      var ampm = h >= 12 ? 'PM' : 'AM';
      h = h % 12;
      if (h === 0) h = 12;

      var hm = el('time-hm');
      var s = el('time-s');
      var ap = el('time-ampm');
      var dt = el('date-text');

      if (hm) hm.textContent = pad(h) + ':' + pad(d.getMinutes());
      if (s) s.textContent = pad(d.getSeconds());
      if (ap) ap.textContent = ampm;
      if (dt) {
        dt.textContent =
          DAYS[d.getDay()] + ' · ' +
          MONTHS[d.getMonth()] + ' ' +
          d.getDate() + ', ' +
          d.getFullYear();
      }
    }

    function start() {
      if (running) return;
      update();
      timer = setInterval(update, CONFIG.REFRESH_INTERVAL);
      running = true;
      log('Đồng hồ đã chạy');
    }

    function stop() {
      if (!running) return;
      clearInterval(timer);
      timer = null;
      running = false;
    }

    return { start: start, stop: stop, update: update };
  })();

  // ========================================================================
  // CON TRỎ NHẤP NHÁY
  // ========================================================================
  var Cursor = (function () {
    var timer = null;
    var visible = true;
    var running = false;

    function toggle() {
      var node = document.querySelector('.cursor');
      if (!node) return;
      visible = !visible;
      node.style.opacity = visible ? '1' : '0';
    }

    function start() {
      if (running) return;
      var node = document.querySelector('.cursor');
      if (!node) return;
      timer = setInterval(toggle, CONFIG.CURSOR_BLINK);
      running = true;
    }

    function stop() {
      if (!running) return;
      clearInterval(timer);
      timer = null;
      running = false;
      var node = document.querySelector('.cursor');
      if (node) node.style.opacity = '1';
    }

    return { start: start, stop: stop };
  })();

  // ========================================================================
  // SỰ KIỆN
  // ========================================================================
  var Events = (function () {
    var bound = false;

    function onVisibility() {
      if (!document.hidden) Clock.update();
    }

    function onFocus() {
      Clock.update();
    }

    function onResize() {
      Clock.update();
    }

    function onKey(e) {
      if (e.key === 'Escape') {
        var toasts = document.querySelectorAll('.toast');
        for (var i = 0; i < toasts.length; i++) {
          if (toasts[i].parentNode) toasts[i].parentNode.removeChild(toasts[i]);
        }
      }
    }

    function bind() {
      if (bound) return;
      document.addEventListener('visibilitychange', onVisibility);
      window.addEventListener('focus', onFocus);
      window.addEventListener('resize', onResize);
      document.addEventListener('keydown', onKey);
      bound = true;
    }

    function unbind() {
      if (!bound) return;
      document.removeEventListener('visibilitychange', onVisibility);
      window.removeEventListener('focus', onFocus);
      window.removeEventListener('resize', onResize);
      document.removeEventListener('keydown', onKey);
      bound = false;
    }

    return { bind: bind, unbind: unbind };
  })();

  // ========================================================================
  // LỖI TOÀN CỤC
  // ========================================================================
  function onError(event) {
    if (CONFIG.DEBUG) {
      console.error('[App] Lỗi toàn cục:', event.error || event.message);
    }
  }

  function onRejection(event) {
    if (CONFIG.DEBUG) {
      console.error('[App] Promise bị từ chối:', event.reason);
    }
  }

  // ========================================================================
  // KHỞI TẠO
  // ========================================================================
  var initialized = false;

  function init() {
    if (initialized) return;
    log('Khởi tạo ' + CONFIG.APP_NAME + ' v' + CONFIG.APP_VERSION);

    Clock.start();
    Cursor.start();
    Events.bind();

    initialized = true;
    log('Khởi tạo hoàn tất');
  }

  function destroy() {
    if (!initialized) return;
    Clock.stop();
    Cursor.stop();
    Events.unbind();
    initialized = false;
  }

  function bootstrap() {
    window.addEventListener('error', onError);
    window.addEventListener('unhandledrejection', onRejection);

    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', init);
    } else {
      init();
    }
  }

  // Xuất API công khai
  window.App = {
    init: init,
    destroy: destroy,
    Clock: Clock,
    Cursor: Cursor,
    Events: Events,
    CONFIG: CONFIG,
  };

  // Khởi chạy
  bootstrap();

})();
