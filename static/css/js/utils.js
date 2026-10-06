// ==========================================================================
// CÁC HÀM TIỆN ÍCH DÙNG CHUNG
// Xử lý DOM, chuỗi, thời gian, số, mảng, đối tượng, bộ nhớ
// ==========================================================================

(function () {
  'use strict';

  // Tránh khai báo trùng nếu tệp được nạp hai lần
  if (window.Utils) {
    console.warn('[Utils] Utils đã tồn tại, bỏ qua nạp lại');
    return;
  }

  var Utils = (function () {

    // ======================================================================
    // HÀM XỬ LÝ DOM
    // ======================================================================
    function el(id) {
      return document.getElementById(id);
    }

    function qs(selector) {
      return document.querySelector(selector);
    }

    function qsa(selector) {
      return Array.prototype.slice.call(document.querySelectorAll(selector));
    }

    function on(target, event, handler) {
      if (target && target.addEventListener) {
        target.addEventListener(event, handler);
      }
    }

    function off(target, event, handler) {
      if (target && target.removeEventListener) {
        target.removeEventListener(event, handler);
      }
    }

    function createEl(tag, className, text) {
      var node = document.createElement(tag);
      if (className) node.className = className;
      if (text) node.textContent = text;
      return node;
    }

    function resolve(target) {
      if (typeof target === 'string') {
        return el(target) || qs(target);
      }
      return target;
    }

    function setText(target, text) {
      var node = resolve(target);
      if (node) node.textContent = text;
    }

    function setHTML(target, html) {
      var node = resolve(target);
      if (node) node.innerHTML = html;
    }

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

    function show(target) {
      var node = resolve(target);
      if (node) node.style.display = '';
    }

    function hide(target) {
      var node = resolve(target);
      if (node) node.style.display = 'none';
    }

    // ======================================================================
    // HÀM XỬ LÝ CHUỖI
    // ======================================================================
    function pad(n, length) {
      length = length || 2;
      return String(n).padStart(length, '0');
    }

    function truncate(text, limit) {
      limit = limit || 100;
      if (typeof text !== 'string') return '';
      if (text.length <= limit) return text;
      return text.slice(0, limit - 3) + '...';
    }

    function escapeHTML(text) {
      if (typeof text !== 'string') return '';
      var map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
      };
      return text.replace(/[&<>"']/g, function (ch) { return map[ch]; });
    }

    function capitalize(text) {
      if (typeof text !== 'string' || !text) return '';
      return text.charAt(0).toUpperCase() + text.slice(1);
    }

    function slugify(text) {
      if (typeof text !== 'string') return '';
      return text
        .toLowerCase()
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-+|-+$/g, '');
    }

    function stripTags(text) {
      if (typeof text !== 'string') return '';
      return text.replace(/<[^>]*>/g, '');
    }

    // ======================================================================
    // HÀM XỬ LÝ THỜI GIAN
    // ======================================================================
    var DAYS = [
      'SUNDAY', 'MONDAY', 'TUESDAY', 'WEDNESDAY',
      'THURSDAY', 'FRIDAY', 'SATURDAY'
    ];

    var MONTHS = [
      'JANUARY', 'FEBRUARY', 'MARCH', 'APRIL',
      'MAY', 'JUNE', 'JULY', 'AUGUST',
      'SEPTEMBER', 'OCTOBER', 'NOVEMBER', 'DECEMBER'
    ];

    function formatDate(date) {
      if (!(date instanceof Date)) return '';
      return DAYS[date.getDay()] + ' · ' +
        MONTHS[date.getMonth()] + ' ' +
        date.getDate() + ', ' +
        date.getFullYear();
    }

    function formatTime(date) {
      if (!(date instanceof Date)) date = new Date();
      var h = date.getHours();
      var ampm = h >= 12 ? 'PM' : 'AM';
      h = h % 12;
      if (h === 0) h = 12;
      return {
        hour: pad(h),
        minute: pad(date.getMinutes()),
        second: pad(date.getSeconds()),
        ampm: ampm,
        full: pad(h) + ':' + pad(date.getMinutes())
      };
    }

    function nowISO() {
      return new Date().toISOString();
    }

    // ======================================================================
    // HÀM XỬ LÝ SỐ
    // ======================================================================
    function clamp(value, min, max) {
      return Math.min(Math.max(value, min), max);
    }

    function randomInt(min, max) {
      return Math.floor(Math.random() * (max - min + 1)) + min;
    }

    function parseNumber(value, fallback) {
      fallback = fallback === undefined ? 0 : fallback;
      var n = Number(value);
      return Number.isFinite(n) ? n : fallback;
    }

    function formatNumber(value, locale) {
      locale = locale || 'vi-VN';
      var n = Number(value);
      if (!Number.isFinite(n)) return '0';
      return n.toLocaleString(locale);
    }

    // ======================================================================
    // HÀM XỬ LÝ MẢNG VÀ ĐỐI TƯỢNG
    // ======================================================================
    function isEmpty(value) {
      if (value === null || value === undefined) return true;
      if (typeof value === 'string') return value.trim().length === 0;
      if (Array.isArray(value)) return value.length === 0;
      if (typeof value === 'object') return Object.keys(value).length === 0;
      return false;
    }

    function deepClone(obj) {
      if (obj === null || typeof obj !== 'object') return obj;
      try {
        return JSON.parse(JSON.stringify(obj));
      } catch (e) {
        return obj;
      }
    }

    function unique(arr) {
      return Array.from(new Set(arr));
    }

    function chunk(arr, size) {
      if (!Array.isArray(arr) || size <= 0) return [];
      var result = [];
      for (var i = 0; i < arr.length; i += size) {
        result.push(arr.slice(i, i + size));
      }
      return result;
    }

    function shuffle(arr) {
      var a = arr.slice();
      for (var i = a.length - 1; i > 0; i--) {
        var j = Math.floor(Math.random() * (i + 1));
        var tmp = a[i]; a[i] = a[j]; a[j] = tmp;
      }
      return a;
    }

    // ======================================================================
    // HÀM XỬ LÝ BỘ NHỚ
    // ======================================================================
    function storageSet(key, value) {
      try {
        localStorage.setItem(key, JSON.stringify(value));
        return true;
      } catch (e) {
        console.error('Lỗi ghi storage:', e);
        return false;
      }
    }

    function storageGet(key, fallback) {
      if (fallback === undefined) fallback = null;
      try {
        var raw = localStorage.getItem(key);
        return raw ? JSON.parse(raw) : fallback;
      } catch (e) {
        return fallback;
      }
    }

    function storageRemove(key) {
      try {
        localStorage.removeItem(key);
        return true;
      } catch (e) {
        return false;
      }
    }

    function storageClear() {
      try {
        localStorage.clear();
        return true;
      } catch (e) {
        return false;
      }
    }

    // ======================================================================
    // HÀM HỖ TRỢ KHÁC
    // ======================================================================
    function sleep(ms) {
      return new Promise(function (resolve) { setTimeout(resolve, ms); });
    }

    function debounce(fn, delay) {
      delay = delay || 300;
      var timer = null;
      return function () {
        var args = arguments;
        clearTimeout(timer);
        timer = setTimeout(function () { fn.apply(null, args); }, delay);
      };
    }

    function throttle(fn, limit) {
      limit = limit || 300;
      var waiting = false;
      return function () {
        if (waiting) return;
        var args = arguments;
        fn.apply(null, args);
        waiting = true;
        setTimeout(function () { waiting = false; }, limit);
      };
    }

    function retry(fn, count, delay) {
      count = count || 3;
      delay = delay || 1000;
      return new Promise(function (resolve, reject) {
        var attempt = 0;
        function tryOnce() {
          attempt++;
          Promise.resolve()
            .then(fn)
            .then(resolve)
            .catch(function (err) {
              if (attempt >= count) reject(err);
              else setTimeout(tryOnce, delay);
            });
        }
        tryOnce();
      });
    }

    function uuid() {
      return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
        var r = (Math.random() * 16) | 0;
        var v = c === 'x' ? r : (r & 0x3) | 0x8;
        return v.toString(16);
      });
    }

    // ======================================================================
    // XUẤT API CÔNG KHAI
    // ======================================================================
    return {
      // DOM
      el: el,
      qs: qs,
      qsa: qsa,
      on: on,
      off: off,
      createEl: createEl,
      resolve: resolve,
      setText: setText,
      setHTML: setHTML,
      toggleClass: toggleClass,
      addClass: addClass,
      removeClass: removeClass,
      hasClass: hasClass,
      show: show,
      hide: hide,

      // Chuỗi
      pad: pad,
      truncate: truncate,
      escapeHTML: escapeHTML,
      capitalize: capitalize,
      slugify: slugify,
      stripTags: stripTags,

      // Thời gian
      DAYS: DAYS,
      MONTHS: MONTHS,
      formatDate: formatDate,
      formatTime: formatTime,
      nowISO: nowISO,

      // Số
      clamp: clamp,
      randomInt: randomInt,
      parseNumber: parseNumber,
      formatNumber: formatNumber,

      // Mảng, đối tượng
      isEmpty: isEmpty,
      deepClone: deepClone,
      unique: unique,
      chunk: chunk,
      shuffle: shuffle,

      // Bộ nhớ
      storageSet: storageSet,
      storageGet: storageGet,
      storageRemove: storageRemove,
      storageClear: storageClear,

      // Khác
      sleep: sleep,
      debounce: debounce,
      throttle: throttle,
      retry: retry,
      uuid: uuid
    };
  })();

  // Xuất ra phạm vi toàn cục
  window.Utils = Utils;

})();
