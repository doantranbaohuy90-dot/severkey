// ==========================================================================
// ĐỒNG HỒ THỜI GIAN THỰC
// Cập nhật giờ, phút, giây, AM/PM và ngày tháng mỗi giây
// ==========================================================================

const Clock = (() => {

  // Biến lưu bộ đếm khoảng thời gian
  let intervalId = null;

  // Biến lưu trạng thái hoạt động
  let running = false;

  // ------------------------------------------------------------------------
  // LẤY CÁC PHẦN TỬ DOM
  // ------------------------------------------------------------------------
  const getElements = () => {
    return {
      hourMinute: Utils.el('time-hm'),
      seconds: Utils.el('time-s'),
      ampm: Utils.el('time-ampm'),
      date: Utils.el('date-text'),
    };
  };

  // ------------------------------------------------------------------------
  // CẬP NHẬT ĐỒNG HỒ
  // ------------------------------------------------------------------------
  const update = () => {
    const now = new Date();
    const time = Utils.formatTime(now);
    const dateText = Utils.formatDate(now);
    const els = getElements();

    // Cập nhật giờ và phút
    if (els.hourMinute) {
      els.hourMinute.textContent = `${time.hour}:${time.minute}`;
    }

    // Cập nhật giây
    if (els.seconds) {
      els.seconds.textContent = time.second;
    }

    // Cập nhật AM/PM
    if (els.ampm) {
      els.ampm.textContent = time.ampm;
    }

    // Cập nhật ngày tháng
    if (els.date) {
      els.date.textContent = dateText;
    }
  };

  // ------------------------------------------------------------------------
  // BẮT ĐẦU ĐỒNG HỒ
  // ------------------------------------------------------------------------
  const start = () => {
    if (running) return;

    // Cập nhật ngay lập tức
    update();

    // Lặp cập nhật theo khoảng thời gian cấu hình
    intervalId = setInterval(
      update,
      CONFIG.REFRESH_INTERVAL || 1000
    );

    running = true;

    if (CONFIG.DEBUG) {
      console.log('[Clock] Đã khởi động');
    }
  };

  // ------------------------------------------------------------------------
  // DỪNG ĐỒNG HỒ
  // ------------------------------------------------------------------------
  const stop = () => {
    if (!running) return;

    clearInterval(intervalId);
    intervalId = null;
    running = false;

    if (CONFIG.DEBUG) {
      console.log('[Clock] Đã dừng');
    }
  };

  // ------------------------------------------------------------------------
  // KHỞI ĐỘNG LẠI ĐỒNG HỒ
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
  // LẤY THỜI GIAN HIỆN TẠI
  // ------------------------------------------------------------------------
  const getCurrentTime = () => {
    return Utils.formatTime(new Date());
  };

  // ------------------------------------------------------------------------
  // LẤY NGÀY HIỆN TẠI
  // ------------------------------------------------------------------------
  const getCurrentDate = () => {
    return Utils.formatDate(new Date());
  };

  // ------------------------------------------------------------------------
  // ĐỒNG BỘ KHI TAB ĐƯỢC KÍCH HOẠT LẠI
  // ------------------------------------------------------------------------
  const syncOnVisible = () => {
    if (!document.hidden) {
      update();
    }
  };

  // ------------------------------------------------------------------------
  // ĐĂNG KÝ SỰ KIỆN
  // ------------------------------------------------------------------------
  const bind = () => {
    // Cập nhật khi tab được kích hoạt lại
    Utils.on(document, 'visibilitychange', syncOnVisible);

    // Cập nhật khi cửa sổ được focus
    Utils.on(window, 'focus', update);

    // Cập nhật khi kích thước thay đổi
    Utils.on(window, 'resize', Utils.throttle(update, 300));
  };

  // ------------------------------------------------------------------------
  // HỦY ĐĂNG KÝ SỰ KIỆN
  // ------------------------------------------------------------------------
  const unbind = () => {
    Utils.off(document, 'visibilitychange', syncOnVisible);
    Utils.off(window, 'focus', update);
    Utils.off(window, 'resize', update);
  };

  // ------------------------------------------------------------------------
  // KHỞI TẠO ĐỒNG HỒ
  // ------------------------------------------------------------------------
  const init = () => {
    bind();
    start();

    if (CONFIG.DEBUG) {
      console.log('[Clock] Đã khởi tạo');
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
    update,
    isRunning,
    getCurrentTime,
    getCurrentDate,
    bind,
    unbind,
  };
})();
