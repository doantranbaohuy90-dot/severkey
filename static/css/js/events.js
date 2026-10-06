// ==========================================================================
// ĐĂNG KÝ SỰ KIỆN GIAO DIỆN
// Định nghĩa các sự kiện tương tác, vòng đời và kiểm tra máy chủ
// ==========================================================================

const Events = (() => {

  // Bộ đếm kiểm tra tình trạng máy chủ
  let healthIntervalId = null;

  // Trạng thái đã đăng ký
  let bound = false;

  // ------------------------------------------------------------------------
  // XỬ LÝ KHI TAB ĐƯỢC KÍCH HOẠT LẠI
  // ------------------------------------------------------------------------
  const onVisibilityChange = () => {
    if (!document.hidden) {
      // Cập nhật lại đồng hồ khi quay lại tab
      Clock.update();

      if (CONFIG.DEBUG) {
        console.log('[Events] Tab được kích hoạt lại');
      }
    }
  };

  // ------------------------------------------------------------------------
  // XỬ LÝ KHI CỬA SỔ ĐƯỢC FOCUS
  // ------------------------------------------------------------------------
  const onFocus = () => {
    // Cập nhật lại đồng hồ
    Clock.update();
  };

  // ------------------------------------------------------------------------
  // XỬ LÝ KHI CỬA SỔ MẤT FOCUS
  // ------------------------------------------------------------------------
  const onBlur = () => {
    // Ghi log khi mất focus
    if (CONFIG.DEBUG) {
      console.log('[Events] Cửa sổ mất focus');
    }
  };

  // ------------------------------------------------------------------------
  // XỬ LÝ KHI KÍCH THƯỚC THAY ĐỔI
  // ------------------------------------------------------------------------
  const onResize = Utils.throttle(() => {
    // Cập nhật lại đồng hồ sau khi resize
    Clock.update();
  }, 300);

  // ------------------------------------------------------------------------
  // XỬ LÝ KHI CUỘN TRANG
  // ------------------------------------------------------------------------
  const onScroll = Utils.throttle(() => {
    // Ghi log vị trí cuộn khi debug
    if (CONFIG.DEBUG) {
      // Không ghi log liên tục để tránh nhiễu
    }
  }, 500);

  // ------------------------------------------------------------------------
  // XỬ LÝ KHI NHẤN PHÍM
  // ------------------------------------------------------------------------
  const onKeyDown = (event) => {
    // Phím tắt R để tải lại
    if (event.key === 'r' && event.ctrlKey) {
      return;
    }

    // Phím Escape để xóa thông báo
    if (event.key === 'Escape') {
      UI.clearToasts();
    }
  };

  // ------------------------------------------------------------------------
  // XỬ LÝ KHI NHẤN CHUỘT
  // ------------------------------------------------------------------------
  const onClick = (event) => {
    // Xử lý liên kết ngoài
    const link = event.target.closest('a[href^="http"]');
    if (link) {
      // Ghi log khi nhấn liên kết ngoài
      if (CONFIG.DEBUG) {
        console.log('[Events] Nhấn liên kết:', link.href);
      }
    }
  };

  // ------------------------------------------------------------------------
  // XỬ LÝ KHI TẢI TRANG XONG
  // ------------------------------------------------------------------------
  const onLoad = () => {
    if (CONFIG.DEBUG) {
      console.log('[Events] Trang đã tải xong');
    }

    // Kiểm tra tình trạng máy chủ lần đầu
    checkHealth();
  };

  // ------------------------------------------------------------------------
  // XỬ LÝ KHI RỜI TRANG
  // ------------------------------------------------------------------------
  const onBeforeUnload = () => {
    // Dừng đồng hồ và con trỏ
    Clock.stop();
    Cursor.stop();

    if (CONFIG.DEBUG) {
      console.log('[Events] Trang sắp đóng');
    }
  };

  // ------------------------------------------------------------------------
  // KIỂM TRA TÌNH TRẠNG MÁY CHỦ
  // ------------------------------------------------------------------------
  const checkHealth = async () => {
    if (!CONFIG.FEATURES?.ENABLE_HEALTH_CHECK) return;

    try {
      const online = await Api.isOnline();
      if (!online && CONFIG.DEBUG) {
        console.warn('[Events] Máy chủ không phản hồi');
      }
    } catch (e) {
      if (CONFIG.DEBUG) {
        console.error('[Events] Lỗi kiểm tra máy chủ:', e.message);
      }
    }
  };

  // ------------------------------------------------------------------------
  // BẮT ĐẦU KIỂM TRA ĐỊNH KỲ
  // ------------------------------------------------------------------------
  const startHealthCheck = () => {
    if (healthIntervalId) return;

    const interval = CONFIG.API_CONFIG?.HEALTH_CHECK_INTERVAL || 60000;
    healthIntervalId = setInterval(checkHealth, interval);

    if (CONFIG.DEBUG) {
      console.log('[Events] Bắt đầu kiểm tra máy chủ định kỳ');
    }
  };

  // ------------------------------------------------------------------------
  // DỪNG KIỂM TRA ĐỊNH KỲ
  // ------------------------------------------------------------------------
  const stopHealthCheck = () => {
    if (healthIntervalId) {
      clearInterval(healthIntervalId);
      healthIntervalId = null;
    }
  };

  // ------------------------------------------------------------------------
  // ĐĂNG KÝ SỰ KIỆN
  // ------------------------------------------------------------------------
  const bind = () => {
    if (bound) return;

    // Sự kiện vòng đời tài liệu
    Utils.on(document, 'visibilitychange', onVisibilityChange);
    Utils.on(document, 'keydown', onKeyDown);
    Utils.on(document, 'click', onClick);

    // Sự kiện cửa sổ
    Utils.on(window, 'focus', onFocus);
    Utils.on(window, 'blur', onBlur);
    Utils.on(window, 'resize', onResize);
    Utils.on(window, 'scroll', onScroll);
    Utils.on(window, 'load', onLoad);
    Utils.on(window, 'beforeunload', onBeforeUnload);

    // Bắt đầu kiểm tra máy chủ định kỳ
    startHealthCheck();

    bound = true;

    if (CONFIG.DEBUG) {
      console.log('[Events] Đã đăng ký sự kiện');
    }
  };

  // ------------------------------------------------------------------------
  // HỦY ĐĂNG KÝ SỰ KIỆN
  // ------------------------------------------------------------------------
  const unbind = () => {
    if (!bound) return;

    // Sự kiện vòng đời tài liệu
    Utils.off(document, 'visibilitychange', onVisibilityChange);
    Utils.off(document, 'keydown', onKeyDown);
    Utils.off(document, 'click', onClick);

    // Sự kiện cửa sổ
    Utils.off(window, 'focus', onFocus);
    Utils.off(window, 'blur', onBlur);
    Utils.off(window, 'resize', onResize);
    Utils.off(window, 'scroll', onScroll);
    Utils.off(window, 'load', onLoad);
    Utils.off(window, 'beforeunload', onBeforeUnload);

    // Dừng kiểm tra máy chủ định kỳ
    stopHealthCheck();

    bound = false;

    if (CONFIG.DEBUG) {
      console.log('[Events] Đã hủy đăng ký sự kiện');
    }
  };

  // ------------------------------------------------------------------------
  // KHỞI TẠO
  // ------------------------------------------------------------------------
  const init = () => {
    bind();

    if (CONFIG.DEBUG) {
      console.log('[Events] Đã khởi tạo');
    }
  };

  // ------------------------------------------------------------------------
  // HỦY KHỞI TẠO
  // ------------------------------------------------------------------------
  const destroy = () => {
    unbind();

    if (CONFIG.DEBUG) {
      console.log('[Events] Đã hủy');
    }
  };

  // ------------------------------------------------------------------------
  // TRẢ VỀ API CÔNG KHAI
  // ------------------------------------------------------------------------
  return {
    init,
    bind,
    unbind,
    destroy,
    checkHealth,
    startHealthCheck,
    stopHealthCheck,
  };
})();
