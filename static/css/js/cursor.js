// ==========================================================================
// HIỆU ỨNG CON TRỎ NHẤP NHÁY
// Điều khiển con trỏ nhấp nháy trong khối trích dẫn
// ==========================================================================

const Cursor = (() => {

  // Biến lưu bộ đếm khoảng thời gian
  let intervalId = null;

  // Biến lưu trạng thái hiển thị
  let visible = true;

  // Biến lưu trạng thái hoạt động
  let running = false;

  // Biến lưu phần tử con trỏ
  let cursorEl = null;

  // ------------------------------------------------------------------------
  // LẤY PHẦN TỬ CON TRỎ
  // ------------------------------------------------------------------------
  const getCursor = () => {
    if (!cursorEl) {
      cursorEl = Utils.qs('.cursor');
    }
    return cursorEl;
  };

  // ------------------------------------------------------------------------
  // ĐẢO TRẠNG THÁI HIỂN THỊ
  // ------------------------------------------------------------------------
  const toggle = () => {
    const node = getCursor();
    if (!node) return;

    visible = !visible;
    node.style.opacity = visible ? '1' : '0';
  };

  // ------------------------------------------------------------------------
  // BẮT ĐẦU NHẤP NHÁY
  // ------------------------------------------------------------------------
  const start = () => {
    if (running) return;

    const node = getCursor();
    if (!node) {
      if (CONFIG.DEBUG) {
        console.warn('[Cursor] Không tìm thấy phần tử .cursor');
      }
      return;
    }

    // Đặt trạng thái hiển thị ban đầu
    visible = true;
    node.style.opacity = '1';

    // Lặp đảo trạng thái theo khoảng thời gian cấu hình
    const interval = CONFIG.UI?.CURSOR_BLINK_INTERVAL || 500;
    intervalId = setInterval(toggle, interval);

    running = true;

    if (CONFIG.DEBUG) {
      console.log('[Cursor] Đã khởi động');
    }
  };

  // ------------------------------------------------------------------------
  // DỪNG NHẤP NHÁY
  // ------------------------------------------------------------------------
  const stop = () => {
    if (!running) return;

    clearInterval(intervalId);
    intervalId = null;
    running = false;

    // Đảm bảo con trỏ hiển thị
    const node = getCursor();
    if (node) node.style.opacity = '1';
    visible = true;

    if (CONFIG.DEBUG) {
      console.log('[Cursor] Đã dừng');
    }
  };

  // ------------------------------------------------------------------------
  // KHỞI ĐỘNG LẠI
  // ------------------------------------------------------------------------
  const restart = () => {
    stop();
    start();
  };

  // ------------------------------------------------------------------------
  // KIỂM TRA TRẠNG THÁI
  // ------------------------------------------------------------------------
  const isRunning = () => running;

  // ------------------------------------------------------------------------
  // HIỂN THỊ CON TRỎ
  // ------------------------------------------------------------------------
  const show = () => {
    const node = getCursor();
    if (node) {
      node.style.opacity = '1';
      visible = true;
    }
  };

  // ------------------------------------------------------------------------
  // ẨN CON TRỎ
  // ------------------------------------------------------------------------
  const hide = () => {
    const node = getCursor();
    if (node) {
      node.style.opacity = '0';
      visible = false;
    }
  };

  // ------------------------------------------------------------------------
  // ĐỒNG BỘ KHI TAB ĐƯỢC KÍCH HOẠT LẠI
  // ------------------------------------------------------------------------
  const syncOnVisible = () => {
    if (document.hidden) {
      // Tạm dừng khi tab bị ẩn
      if (intervalId) {
        clearInterval(intervalId);
        intervalId = null;
      }
    } else {
      // Khởi động lại khi tab hiển thị
      if (running && !intervalId) {
        const interval = CONFIG.UI?.CURSOR_BLINK_INTERVAL || 500;
        intervalId = setInterval(toggle, interval);
      }
    }
  };

  // ------------------------------------------------------------------------
  // ĐĂNG KÝ SỰ KIỆN
  // ------------------------------------------------------------------------
  const bind = () => {
    Utils.on(document, 'visibilitychange', syncOnVisible);
  };

  // ------------------------------------------------------------------------
  // HỦY ĐĂNG KÝ SỰ KIỆN
  // ------------------------------------------------------------------------
  const unbind = () => {
    Utils.off(document, 'visibilitychange', syncOnVisible);
  };

  // ------------------------------------------------------------------------
  // KHỞI TẠO
  // ------------------------------------------------------------------------
  const init = () => {
    bind();
    start();

    if (CONFIG.DEBUG) {
      console.log('[Cursor] Đã khởi tạo');
    }
  };

  // ------------------------------------------------------------------------
  // HỦY KHỞI TẠO
  // ------------------------------------------------------------------------
  const destroy = () => {
    stop();
    unbind();

    if (CONFIG.DEBUG) {
      console.log('[Cursor] Đã hủy');
    }
  };

  // ------------------------------------------------------------------------
  // TRẢ VỀ API CÔNG KHAI
  // ------------------------------------------------------------------------
  return {
    init,
    start,
    stop,
    restart,
    toggle,
    show,
    hide,
    isRunning,
    bind,
    unbind,
    destroy,
  };
})();
