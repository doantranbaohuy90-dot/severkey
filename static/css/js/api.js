// ==========================================================================
// GỌI API TỪ MÁY CHỦ
// Định nghĩa các hàm giao tiếp với backend Flask
// ==========================================================================

const Api = (() => {

  // ------------------------------------------------------------------------
  // HÀM GỌI CƠ BẢN
  // ------------------------------------------------------------------------
  const request = async (path, options = {}) => {
    const url = `${CONFIG.API_BASE}${path}`;
    const config = {
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
      },
      ...options,
    };

    // Tạo bộ điều khiển hủy sau thời gian chờ
    const controller = new AbortController();
    const timeoutId = setTimeout(
      () => controller.abort(),
      CONFIG.API_CONFIG.TIMEOUT
    );
    config.signal = controller.signal;

    try {
      const res = await fetch(url, config);
      clearTimeout(timeoutId);

      // Kiểm tra mã trạng thái
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }

      // Đọc kiểu nội dung
      const contentType = res.headers.get('content-type') || '';
      if (contentType.includes('application/json')) {
        return await res.json();
      }
      return await res.text();
    } catch (err) {
      clearTimeout(timeoutId);

      // Ghi log lỗi
      if (CONFIG.DEBUG) {
        console.error(`[API] Lỗi gọi ${path}:`, err.message);
      }

      throw err;
    }
  };

  // ------------------------------------------------------------------------
  // HÀM GỌI GET
  // ------------------------------------------------------------------------
  const get = (path, params = null) => {
    let url = path;
    if (params && typeof params === 'object') {
      const query = new URLSearchParams(params).toString();
      url += `?${query}`;
    }
    return request(url, { method: 'GET' });
  };

  // ------------------------------------------------------------------------
  // HÀM GỌI POST
  // ------------------------------------------------------------------------
  const post = (path, payload = {}) => {
    return request(path, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  };

  // ------------------------------------------------------------------------
  // HÀM GỌI PUT
  // ------------------------------------------------------------------------
  const put = (path, payload = {}) => {
    return request(path, {
      method: 'PUT',
      body: JSON.stringify(payload),
    });
  };

  // ------------------------------------------------------------------------
  // HÀM GỌI DELETE
  // ------------------------------------------------------------------------
  const del = (path) => {
    return request(path, { method: 'DELETE' });
  };

  // ------------------------------------------------------------------------
  // ENDPOINT KIỂM TRA TÌNH TRẠNG
  // ------------------------------------------------------------------------
  const health = () => {
    return get(CONFIG.API_ENDPOINTS.HEALTH);
  };

  // ------------------------------------------------------------------------
  // ENDPOINT LẤY PHIÊN BẢN
  // ------------------------------------------------------------------------
  const version = () => {
    return get(CONFIG.API_ENDPOINTS.VERSION);
  };

  // ------------------------------------------------------------------------
  // ENDPOINT LẤY THÔNG TIN CHỦ SỞ HỮU
  // ------------------------------------------------------------------------
  const owner = () => {
    return get(CONFIG.API_ENDPOINTS.OWNER);
  };

  // ------------------------------------------------------------------------
  // ENDPOINT LẤY DANH SÁCH DỰ ÁN
  // ------------------------------------------------------------------------
  const projects = () => {
    return get(CONFIG.API_ENDPOINTS.PROJECTS);
  };

  // ------------------------------------------------------------------------
  // ENDPOINT LƯU HỒ SƠ
  // ------------------------------------------------------------------------
  const saveProfile = (payload) => {
    return post(CONFIG.API_ENDPOINTS.PROFILE, payload);
  };

  // ------------------------------------------------------------------------
  // ENDPOINT LẤY HỒ SƠ THEO MÃ
  // ------------------------------------------------------------------------
  const getProfile = (userId) => {
    return get(`${CONFIG.API_ENDPOINTS.PROFILE}/${userId}`);
  };

  // ------------------------------------------------------------------------
  // HÀM GỌI CÓ THỬ LẠI
  // ------------------------------------------------------------------------
  const getWithRetry = async (path) => {
    return Utils.retry(
      () => get(path),
      CONFIG.API_CONFIG.RETRY_COUNT,
      CONFIG.API_CONFIG.RETRY_DELAY
    );
  };

  // ------------------------------------------------------------------------
  // HÀM KIỂM TRA KẾT NỐI
  // ------------------------------------------------------------------------
  const isOnline = async () => {
    try {
      const res = await health();
      return res && res.status === 'ok';
    } catch (e) {
      return false;
    }
  };

  // ------------------------------------------------------------------------
  // TRẢ VỀ API CÔNG KHAI
  // ------------------------------------------------------------------------
  return {
    request,
    get,
    post,
    put,
    del,
    health,
    version,
    owner,
    projects,
    saveProfile,
    getProfile,
    getWithRetry,
    isOnline,
  };
})();
