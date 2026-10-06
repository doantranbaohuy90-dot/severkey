// ==========================================================================
// ĐIỂM KHỞI CHẠY CHÍNH
// Khởi tạo toàn bộ thành phần giao diện và xử lý vòng đời ứng dụng
// ==========================================================================

const App = (() => {

  // Trạng thái đã khởi tạo
  let initialized = false;

  // ------------------------------------------------------------------------
  // KHỞI TẠO CÁC THÀNH PHẦN
  // ------------------------------------------------------------------------
  const initComponents = () => {
    // Khởi tạo đồng hồ
    if (CONFIG.FEATURES?.ENABLE_CLOCK) {
      Clock.init();
    }

    // Khởi tạo con trỏ nhấp nháy
    if (CONFIG.FEATURES?.ENABLE_CURSOR_BLINK) {
      Cursor.init();
    }

    // Khởi tạo sự kiện
    Events.init();
  };

  // ------------------------------------------------------------------------
  // KHỞI TẠO ỨNG DỤNG
  // ------------------------------------------------------------------------
  const init = () => {
    if (initialized) return;

    // Ghi log khởi tạo
    if (CONFIG.DEBUG) {
      console.log(`[App] Khởi tạo ${CONFIG.APP_NAME} v${CONFIG.APP_VERSION}`);
    }

    // Khởi tạo các thành phần
    initComponents();

    // Đánh dấu đã khởi tạo
    initialized = true;

    // Ghi log hoàn tất
    if (CONFIG.DEBUG) {
      console.log('[App] Khởi tạo hoàn tất');
    }
  };

  // ------------------------------------------------------------------------
  // HỦY ỨNG DỤNG
  // ------------------------------------------------------------------------
  const destroy = () => {
    if (!initialized) return;

    // Dừng đồng hồ
    Clock.stop();

    // Dừng con trỏ
    Cursor.destroy();

    // Hủy sự kiện
    Events.destroy();

    // Xóa thông báo
    UI.clearToasts();

    // Đánh dấu chưa khởi tạo
    initialized = false;

    if (CONFIG.DEBUG) {
      console.log('[App] Đã hủy');
    }
  };

  // ------------------------------------------------------------------------
  // KHỞI ĐỘNG LẠI ỨNG DỤNG
  // ------------------------------------------------------------------------
  const restart = () => {
    destroy();
    init();
  };

  // ------------------------------------------------------------------------
  // KIỂM TRA TRẠNG THÁI
  // ------------------------------------------------------------------------
  const isInitialized = () => initialized;

  // ------------------------------------------------------------------------
  // LẤY THÔNG TIN ỨNG DỤNG
  // ------------------------------------------------------------------------
  const getInfo = () => {
    return {
      name: CONFIG.APP_NAME,
      version: CONFIG.APP_VERSION,
      build: CONFIG.APP_BUILD,
      env: CONFIG.ENV,
      debug: CONFIG.DEBUG,
      initialized,
    };
  };

  // ------------------------------------------------------------------------
  // XỬ LÝ KHI DOM SẴN SÀNG
  // ------------------------------------------------------------------------
  const onDOMReady = () => {
    // Kiểm tra trạng thái tài liệu
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', init);
    } else {
      init();
    }
  };

  // ------------------------------------------------------------------------
  // XỬ LÝ LỖI TOÀN CỤC
  // ------------------------------------------------------------------------
  const onError = (event) => {
    // Ghi log lỗi
    if (CONFIG.DEBUG) {
      console.error('[App] Lỗi toàn cục:', event.error || event.message);
    }

    // Hiển thị thông báo lỗi
    UI.toast('Đã xảy ra lỗi. Vui lòng tải lại trang.', 'error');
  };

  // ------------------------------------------------------------------------
  // XỬ LÝ PROMISE BỊ TỪ CHỐI
  // ------------------------------------------------------------------------
  const onUnhandledRejection = (event) => {
    // Ghi log lỗi
    if (CONFIG.DEBUG) {
      console.error('[App] Promise bị từ chối:', event.reason);
    }

    // Hiển thị thông báo lỗi
    UI.toast('Không thể kết nối máy chủ.', 'error');
  };

  // ------------------------------------------------------------------------
  // ĐĂNG KÝ SỰ KIỆN LỖI TOÀN CỤC
  // ------------------------------------------------------------------------
  const bindGlobalHandlers = () => {
    Utils.on(window, 'error', onError);
    Utils.on(window, 'unhandledrejection', onUnhandledRejection);
  };

  // ------------------------------------------------------------------------
  // HỦY ĐĂNG KÝ SỰ KIỆN LỖI TOÀN CỤC
  // ------------------------------------------------------------------------
  const unbindGlobalHandlers = () => {
    Utils.off(window, 'error', onError);
    Utils.off(window, 'unhandledrejection', onUnhandledRejection);
  };

  // ------------------------------------------------------------------------
  // TỰ ĐỘNG KHỞI CHẠY
  // ------------------------------------------------------------------------
  const bootstrap = () => {
    bindGlobalHandlers();
    onDOMReady();
  };

  // ------------------------------------------------------------------------
  // TRẢ VỀ API CÔNG KHAI
  // ------------------------------------------------------------------------
  return {
    init,
    destroy,
    restart,
    isInitialized,
    getInfo,
    bootstrap,
    bindGlobalHandlers,
    unbindGlobalHandlers,
  };
})();

// ==========================================================================
// TỰ ĐỘNG KHỞI CHẠY KHI TẢI TRANG
// ==========================================================================

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => App.bootstrap());
} else {
  App.bootstrap();
}

// ==========================================================================
// XUẤT ĐỐI TƯỢNG APP CHO MÔI TRƯỜNG TOÀN CỤC
// ==========================================================================

window.App = App;
