// ==========================================================================
// CẤU HÌNH TOÀN CỤC PHÍA CLIENT
// Định nghĩa các hằng số, đường dẫn API, thông tin chủ sở hữu
// ==========================================================================

const CONFIG = Object.freeze({

  // ------------------------------------------------------------------------
  // THÔNG TIN ỨNG DỤNG
  // ------------------------------------------------------------------------
  APP_NAME: 'Hồ sơ của tôi',
  APP_VERSION: '1.0.0',
  APP_BUILD: '2026.10.06',

  // ------------------------------------------------------------------------
  // ĐƯỜNG DẪN API
  // ------------------------------------------------------------------------
  API_BASE: '',
  API_ENDPOINTS: {
    HEALTH: '/api/health',
    VERSION: '/api/version',
    OWNER: '/api/owner',
    PROJECTS: '/api/projects',
    PROFILE: '/api/profile',
  },

  // ------------------------------------------------------------------------
  // NGÔN NGỮ VÀ MÚI GIỜ
  // ------------------------------------------------------------------------
  LOCALE: 'vi-VN',
  TIMEZONE: 'Asia/Ho_Chi_Minh',
  TIMEZONE_OFFSET: 7,

  // ------------------------------------------------------------------------
  // ĐỒNG HỒ
  // ------------------------------------------------------------------------
  REFRESH_INTERVAL: 1000,
  CLOCK_FORMAT_24H: false,
  CLOCK_SHOW_SECONDS: true,
  CLOCK_SHOW_AMPM: true,

  // ------------------------------------------------------------------------
  // THÔNG TIN CHỦ SỞ HỮU
  // ------------------------------------------------------------------------
  OWNER: {
    name: 'Doãn Trần Bảo Huy',
    telegram: 'https://t.me/baohuyno1',
    telegramUsername: '@baohuyno1',
    zalo: 'https://zalo.me/0347635807',
    zaloPhone: '0347635807',
    phone: '0347635807',
    email: '',
    role: 'Seller & Website, Bot Developer',
  },

  // ------------------------------------------------------------------------
  // THÔNG TIN LIÊN KẾT
  // ------------------------------------------------------------------------
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
      value: '0347635807',
      url: 'https://zalo.me/0347635807',
      enabled: true,
    },
  ],

  // ------------------------------------------------------------------------
  // CẤU HÌNH GIAO DIỆN
  // ------------------------------------------------------------------------
  UI: {
    CURSOR_BLINK_INTERVAL: 500,
    ANIMATION_DURATION: 600,
    TOAST_DURATION: 3000,
    DEBOUNCE_DELAY: 300,
  },

  // ------------------------------------------------------------------------
  // CẤU HÌNH LƯU TRỮ
  // ------------------------------------------------------------------------
  STORAGE_KEYS: {
    THEME: 'app_theme',
    LOCALE: 'app_locale',
    LAST_VISIT: 'app_last_visit',
    PROFILE: 'app_profile',
  },

  // ------------------------------------------------------------------------
  // CẤU HÌNH KIỂM TRA
  // ------------------------------------------------------------------------
  VALIDATION: {
    MAX_PROFILE_FIELDS: 20,
    MAX_FIELD_NAME_LENGTH: 32,
    MAX_FIELD_VALUE_LENGTH: 500,
  },

  // ------------------------------------------------------------------------
  // CẤU HÌNH GỌI API
  // ------------------------------------------------------------------------
  API_CONFIG: {
    TIMEOUT: 10000,
    RETRY_COUNT: 3,
    RETRY_DELAY: 1000,
    HEALTH_CHECK_INTERVAL: 60000,
  },

  // ------------------------------------------------------------------------
  // CỜ BẬT/TẮT
  // ------------------------------------------------------------------------
  FEATURES: {
    ENABLE_HEALTH_CHECK: true,
    ENABLE_CURSOR_BLINK: true,
    ENABLE_CLOCK: true,
    ENABLE_ANIMATIONS: true,
    ENABLE_STORAGE: true,
  },

  // ------------------------------------------------------------------------
  // CHẾ ĐỘ
  // ------------------------------------------------------------------------
  DEBUG: false,
  ENV: 'production',
});

// Đóng băng các đối tượng con để tránh thay đổi
Object.freeze(CONFIG.API_ENDPOINTS);
Object.freeze(CONFIG.OWNER);
Object.freeze(CONFIG.LINKS);
Object.freeze(CONFIG.UI);
Object.freeze(CONFIG.STORAGE_KEYS);
Object.freeze(CONFIG.VALIDATION);
Object.freeze(CONFIG.API_CONFIG);
Object.freeze(CONFIG.FEATURES);
