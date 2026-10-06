// ==========================================================================
// CÁC HÀM TIỆN ÍCH DÙNG CHUNG
// Định nghĩa hàm xử lý DOM, chuỗi, thời gian, số và bộ nhớ
// ==========================================================================

const Utils = (() => {

  // ------------------------------------------------------------------------
  // HÀM XỬ LÝ DOM
  // ------------------------------------------------------------------------
  const el = (id) => document.getElementById(id);

  const qs = (selector) => document.querySelector(selector);

  const qsa = (selector) => Array.from(document.querySelectorAll(selector));

  const on = (target, event, handler) => {
    if (target) target.addEventListener(event, handler);
  };

  const off = (target, event, handler) => {
    if (target) target.removeEventListener(event, handler);
  };

  const createEl = (tag, className = '', text = '') => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  };

  const setText = (target, text) => {
    const node = typeof target === 'string' ? el(target) : target;
    if (node) node.textContent = text;
  };

  const setHTML = (target, html) => {
    const node = typeof target === 'string' ? el(target) : target;
    if (node) node.innerHTML = html;
  };

  const toggleClass = (target, className, force) => {
    const node = typeof target === 'string' ? qs(target) : target;
    if (node) node.classList.toggle(className, force);
  };

  const addClass = (target, className) => {
    const node = typeof target === 'string' ? qs(target) : target;
    if (node) node.classList.add(className);
  };

  const removeClass = (target, className) => {
    const node = typeof target === 'string' ? qs(target) : target;
    if (node) node.classList.remove(className);
  };

  const hasClass = (target, className) => {
    const node = typeof target === 'string' ? qs(target) : target;
    return node ? node.classList.contains(className) : false;
  };

  // ------------------------------------------------------------------------
  // HÀM XỬ LÝ CHUỖI
  // ------------------------------------------------------------------------
  const pad = (n, length = 2) => String(n).padStart(length, '0');

  const truncate = (text, limit = 100) => {
    if (typeof text !== 'string') return '';
    if (text.length <= limit) return text;
    return text.slice(0, limit - 3) + '...';
  };

  const escapeHTML = (text) => {
    if (typeof text !== 'string') return '';
    const map = {
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;',
    };
    return text.replace(/[&<>"']/g, (ch) => map[ch]);
  };

  const capitalize = (text) => {
    if (typeof text !== 'string' || !text) return '';
    return text.charAt(0).toUpperCase() + text.slice(1);
  };

  const slugify = (text) => {
    if (typeof text !== 'string') return '';
    return text
      .toLowerCase()
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '');
  };

  // ------------------------------------------------------------------------
  // HÀM XỬ LÝ THỜI GIAN
  // ------------------------------------------------------------------------
  const DAYS = [
    'SUNDAY', 'MONDAY', 'TUESDAY', 'WEDNESDAY',
    'THURSDAY', 'FRIDAY', 'SATURDAY',
  ];

  const MONTHS = [
    'JANUARY', 'FEBRUARY', 'MARCH', 'APRIL',
    'MAY', 'JUNE', 'JULY', 'AUGUST',
    'SEPTEMBER', 'OCTOBER', 'NOVEMBER', 'DECEMBER',
  ];

  const formatDate = (date) => {
    if (!(date instanceof Date)) return '';
    return `${DAYS[date.getDay()]} · ${MONTHS[date.getMonth()]} ${date.getDate()}, ${date.getFullYear()}`;
  };

  const formatTime = (date) => {
    if (!(date instanceof Date)) date = new Date();
    let h = date.getHours();
    const ampm = h >= 12 ? 'PM' : 'AM';
    h = h % 12;
    if (h === 0) h = 12;
    return {
      hour: pad(h),
      minute: pad(date.getMinutes()),
      second: pad(date.getSeconds()),
      ampm,
      full: `${pad(h)}:${pad(date.getMinutes())}`,
    };
  };

  const nowISO = () => new Date().toISOString();

  // ------------------------------------------------------------------------
  // HÀM XỬ LÝ SỐ
  // ------------------------------------------------------------------------
  const clamp = (value, min, max) => Math.min(Math.max(value, min), max);

  const randomInt = (min, max) => Math.floor(Math.random() * (max - min + 1)) + min;

  const parseNumber = (value, fallback = 0) => {
    const n = Number(value);
    return Number.isFinite(n) ? n : fallback;
  };

  const formatNumber = (value, locale = 'vi-VN') => {
    const n = Number(value);
    if (!Number.isFinite(n)) return '0';
    return n.toLocaleString(locale);
  };

  // ------------------------------------------------------------------------
  // HÀM XỬ LÝ MẢNG VÀ ĐỐI TƯỢNG
  // ------------------------------------------------------------------------
  const isEmpty = (value) => {
    if (value === null || value === undefined) return true;
    if (typeof value === 'string') return value.trim().length === 0;
    if (Array.isArray(value)) return value.length === 0;
    if (typeof value === 'object') return Object.keys(value).length === 0;
    return false;
  };

  const deepClone = (obj) => {
    if (obj === null || typeof obj !== 'object') return obj;
    return JSON.parse(JSON.stringify(obj));
  };

  const unique = (arr) => Array.from(new Set(arr));

  const chunk = (arr, size) => {
    if (!Array.isArray(arr) || size <= 0) return [];
    const result = [];
    for (let i = 0; i < arr.length; i += size) {
      result.push(arr.slice(i, i + size));
    }
    return result;
  };

  // ------------------------------------------------------------------------
  // HÀM XỬ LÝ BỘ NHỚ
  // ------------------------------------------------------------------------
  const storageSet = (key, value) => {
    try {
      localStorage.setItem(key, JSON.stringify(value));
      return true;
    } catch (e) {
      console.error('Lỗi ghi storage:', e);
      return false;
    }
  };

  const storageGet = (key, fallback = null) => {
    try {
      const raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch (e) {
      return fallback;
    }
  };

  const storageRemove = (key) => {
    try {
      localStorage.removeItem(key);
      return true;
    } catch (e) {
      return false;
    }
  };

  const storageClear = () => {
    try {
      localStorage.clear();
      return true;
    } catch (e) {
      return false;
    }
  };

  // ------------------------------------------------------------------------
  // HÀM HỖ TRỢ KHÁC
  // ------------------------------------------------------------------------
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  const debounce = (fn, delay = 300) => {
    let timer = null;
    return (...args) => {
      clearTimeout(timer);
      timer = setTimeout(() => fn(...args), delay);
    };
  };

  const throttle = (fn, limit = 300) => {
    let waiting = false;
    return (...args) => {
      if (waiting) return;
      fn(...args);
      waiting = true;
      setTimeout(() => { waiting = false; }, limit);
    };
  };

  const retry = async (fn, count = 3, delay = 1000) => {
    for (let i = 0; i < count; i++) {
      try {
        return await fn();
      } catch (e) {
        if (i === count - 1) throw e;
        await sleep(delay);
      }
    }
  };

  const uuid = () => {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
      const r = (Math.random() * 16) | 0;
      const v = c === 'x' ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  };

  // ------------------------------------------------------------------------
  // TRẢ VỀ API CÔNG KHAI
  // ------------------------------------------------------------------------
  return {
    el,
    qs,
    qsa,
    on,
    off,
    createEl,
    setText,
    setHTML,
    toggleClass,
    addClass,
    removeClass,
    hasClass,
    pad,
    truncate,
    escapeHTML,
    capitalize,
    slugify,
    DAYS,
    MONTHS,
    formatDate,
    formatTime,
    nowISO,
    clamp,
    randomInt,
    parseNumber,
    formatNumber,
    isEmpty,
    deepClone,
    unique,
    chunk,
    storageSet,
    storageGet,
    storageRemove,
    storageClear,
    sleep,
    debounce,
    throttle,
    retry,
    uuid,
  };
})();
