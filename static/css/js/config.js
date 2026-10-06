// ==========================================================================
// CẤU HÌNH TOÀN CỤC PHÍA CLIENT
// Định nghĩa hằng số, đường dẫn API, thông tin chủ sở hữu, cờ tính năng
// ==========================================================================

(function () {
  'use strict';

  // Tránh khai báo trùng nếu tệp được nạp hai lần
  if (window.CONFIG) {
    console.warn('[Config] CONFIG đã tồn tại, bỏ qua nạp lại');
    return;
  }

  var CONFIG = {

    // ----------------------------------------------------------------------
    // THÔNG TIN ỨNG DỤNG
    // ----------------------------------------------------------------------
    APP_NAME: 'Hồ sơ của tôi',
    APP_VERSION: '1.0.0',
    APP_BUILD: '2026.10.06',

    // ----------------------------------------------------------------------
    // ĐƯỜNG DẪN API
    // ----------------------------------------------------------------------
    API_BASE: '',
    API_ENDPOINTS: {
      HEALTH:   '/api/health',
      VERSION:  '/api/version',
      OWNER:    '/api/owner',
      PROJECTS: '/api/projects',
      PROFILE:  '/api/profile',
      SPIDER:   '/api/spider/config',
      NODES:    '/api/spider/nodes',
    },

    // ----------------------------------------------------------------------
    // NGÔN NGỮ VÀ MÚI GIỜ
    // ----------------------------------------------------------------------
    LOCALE: 'vi-VN',
    TIMEZONE: 'Asia/Ho_Chi_Minh',
    TIMEZONE_OFFSET: 7,
    DATE_LOCALE: 'en-US',

    // ----------------------------------------------------------------------
    // ĐỒNG HỒ
    // ----------------------------------------------------------------------
    REFRESH_INTERVAL: 1000,
    CLOCK_FORMAT_24H: false,
    CLOCK_SHOW_SECONDS: true,
    CLOCK_SHOW_AMPM: true,

    // ----------------------------------------------------------------------
    // THÔNG TIN CHỦ SỞ HỮU
    // ----------------------------------------------------------------------
    OWNER: {
      name: 'Doãn Trần Bảo Huy',
      telegram: 'https://t.me/baohuyno1',
      telegramUsername: '@baohuyno1',
      zalo: 'https://zalo.me/0347635805',
      zaloPhone: '',
      phone: '0347635805',
      email: 'huydoan633@gmail.com',
      role: 'Seller & Website, Bot Developer',
    },

    // ----------------------------------------------------------------------
    // THÔNG TIN LIÊN KẾT
    // ----------------------------------------------------------------------
    LINKS: [
      {
        id: 'telegram',
        label: 'Telegram',
        value: '@baohuyno1',
        url: 'https://t.me/baohuyno1',
        enabled: true,
      },
      {
        id: 'zalo',
        label: 'Zalo',
        value: '0347635805',
        url: 'https://zalo.me/0347635805',
        enabled: true,
      },
    ],

    // ----------------------------------------------------------------------
    // CẤU HÌNH GIAO DIỆN
    // ----------------------------------------------------------------------
    UI: {
      CURSOR_BLINK_INTERVAL: 500,
      ANIMATION_DURATION: 600,
      TOAST_DURATION: 3000,
      DEBOUNCE_DELAY: 300,
      THROTTLE_DELAY: 300,
    },

    // ----------------------------------------------------------------------
    // CẤU HÌNH LƯU TRỮ
    // ----------------------------------------------------------------------
    STORAGE_KEYS: {
      THEME: 'app_theme',
      LOCALE: 'app_locale',
      LAST_VISIT: 'app_last_visit',
      PROFILE: 'app_profile',
    },

    // ----------------------------------------------------------------------
    // CẤU HÌNH KIỂM TRA
    // ----------------------------------------------------------------------
    VALIDATION: {
      MAX_PROFILE_FIELDS: 20,
      MAX_FIELD_NAME_LENGTH: 32,
      MAX_FIELD_VALUE_LENGTH: 500,
      MAX_NODES: 60,
    },

    // ----------------------------------------------------------------------
    // CẤU HÌNH GỌI API
    // ----------------------------------------------------------------------
    API_CONFIG: {
      TIMEOUT: 10000,
      RETRY_COUNT: 3,
      RETRY_DELAY: 1000,
      HEALTH_CHECK_INTERVAL: 60000,
      HEADERS: {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
      },
    },

    // ----------------------------------------------------------------------
    // CẤU HÌNH CON NHỆN
    // ----------------------------------------------------------------------
    SPIDER: {
      MAX_SPEED: 8,
      SPEED: 0.3,
      SIZE: 2.4,
      COLOR: '#c060ff',
      TRAIL_LENGTH: 30,
      BABIES_COUNT: 4,
      BABY_SIZE: 1.1,
      BABY_MAX_SPEED: 3,
      PARTICLE_BURST: 12,
      PARTICLE_DECAY: 0.02,
      ESCAPE_RADIUS: 120,
      ESCAPE_FORCE: 0.5,
      CANVAS_HEIGHT: 480,
      CANVAS_HEIGHT_MOBILE: 360,
    },

    // ----------------------------------------------------------------------
    // CỜ BẬT/TẮT
    // ----------------------------------------------------------------------
    FEATURES: {
      ENABLE_HEALTH_CHECK: true,
      ENABLE_CURSOR_BLINK: true,
      ENABLE_CLOCK: true,
      ENABLE_ANIMATIONS: true,
      ENABLE_STORAGE: true,
      ENABLE_SPIDER: true,
      ENABLE_API: true,
    },

    // ----------------------------------------------------------------------
    // CHẾ ĐỘ
    // ----------------------------------------------------------------------
    DEBUG: false,
    ENV: 'production',
  };

  // Đóng băng đối tượng con để tránh thay đổi ngoài ý muốn
  function deepFreeze(obj) {
    Object.getOwnPropertyNames(obj).forEach(function (key) {
      var value = obj[key];
      if (value && typeof value === 'object' && !Object.isFrozen(value)) {
        deepFreeze(value);
      }
    });
    return Object.freeze(obj);
  }

  deepFreeze(CONFIG);

  // Xuất ra phạm vi toàn cục
  window.CONFIG = CONFIG;

})();
