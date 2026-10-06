// ==========================================================================
// ENGINE CON NHỆN CHẠY NÂNG CAO
// Đọc cấu hình từ server và điều khiển nhện, nhện con, hạt, vệt
// ==========================================================================

(function () {
  'use strict';

  // Chờ DOM sẵn sàng
  document.addEventListener('DOMContentLoaded', function () {

    // Lấy canvas
    var canvas = document.getElementById('spider-canvas');
    if (!canvas) {
      console.error('[Spider] Không tìm thấy canvas');
      return;
    }
    var ctx = canvas.getContext('2d');
    var statEl = document.getElementById('spider-stat');

    // Đọc payload từ server
    var payload = window.SPIDER_PAYLOAD || {};
    var nodeData = (payload.nodes && payload.nodes.nodes) || [];
    var spiderCfg = (payload.spider && payload.spider.main) || {};
    var babiesCfg = (payload.spider && payload.spider.babies) || {};
    var particleCfg = (payload.spider && payload.spider.particles) || {};
    var escapeCfg = (payload.spider && payload.spider.escape) || {};

    // Biến kích thước
    var W = 0, H = 0;
    var DPR = window.devicePixelRatio || 1;

    // Chuột
    var mouseX = -1000, mouseY = -1000, mouseActive = false;

    // Mảng node
    var nodes = [];

    // Nhện chính
    var spider = {
      index: 0,
      x: 0, y: 0,
      vx: 0, vy: 0,
      angle: 0,
      targetAngle: 0,
      legPhase: 0,
      wait: 0,
      size: spiderCfg.size || 2.4,
      color: spiderCfg.color || '#c060ff',
      speed: spiderCfg.speed || 0.3,
      maxSpeed: spiderCfg.maxSpeed || 8,
      trail: [],
    };

    // Nhện con
    var babies = [];

    // Hạt
    var particles = [];

    // ---------------------------------------------------------------------
    // Cập nhật kích thước
    // ---------------------------------------------------------------------
    function resize() {
      W = window.innerWidth;
      H = window.innerHeight;
      canvas.width = W * DPR;
      canvas.height = H * DPR;
      canvas.style.width = W + 'px';
      canvas.style.height = H + 'px';
      ctx.setTransform(DPR, 0, 0, DPR, 0, 0);

      buildNodes();
      resetSpider();
      buildBabies();
    }

    // ---------------------------------------------------------------------
    // Xây dựng node
    // ---------------------------------------------------------------------
    function buildNodes() {
      nodes = [];
      if (nodeData.length === 0) return;
      if (W <= 0 || H <= 0) return;

      var paddingX = Math.max(100, W / 8);
      var paddingY = Math.max(60, H / 10);
      var cols = Math.max(2, Math.floor(W / paddingX));
      var rows = Math.ceil(nodeData.length / cols);
      var offsetX = (W - (cols - 1) * paddingX) / 2;
      var offsetY = (H - (rows - 1) * paddingY) / 2;

      for (var i = 0; i < nodeData.length; i++) {
        var src = nodeData[i];
        var col = i % cols;
        var row = Math.floor(i / cols);
        nodes.push({
          label: src.label,
          color: src.color,
          radius: src.radius || 30,
          x: offsetX + col * paddingX,
          y: offsetY + row * paddingY,
          pulse: Math.random() * Math.PI * 2,
          delay: src.delay || 20,
        });
      }
    }

    // ---------------------------------------------------------------------
    // Đặt lại nhện chính
    // ---------------------------------------------------------------------
    function resetSpider() {
      if (nodes.length === 0) return;
      spider.index = 0;
      spider.x = nodes[0].x;
      spider.y = nodes[0].y;
      spider.vx = 0;
      spider.vy = 0;
      spider.trail = [];
      if (statEl) statEl.textContent = '0 / ' + nodes.length;
    }

    // ---------------------------------------------------------------------
    // Tạo nhện con
    // ---------------------------------------------------------------------
    function buildBabies() {
      babies = [];
      var count = babiesCfg.count || 4;
      for (var i = 0; i < count; i++) {
        babies.push({
          x: W / 2 + (Math.random() - 0.5) * 200,
          y: H / 2 + (Math.random() - 0.5) * 200,
          vx: 0, vy: 0,
          legPhase: Math.random() * Math.PI * 2,
          size: (babiesCfg.size || 1.1) + Math.random() * 0.4,
          color: ['#ff5a8a', '#5ad7ff', '#a8ff5a', '#ffd75a'][i % 4],
          angle: 0,
          wander: Math.random() * Math.PI * 2,
        });
      }
    }

    // ---------------------------------------------------------------------
    // Sinh hạt
    // ---------------------------------------------------------------------
    function spawnParticles(x, y, color) {
      var burst = particleCfg.burst || 12;
      for (var i = 0; i < burst; i++) {
        var a = Math.random() * Math.PI * 2;
        var speed = 1 + Math.random() * 3;
        particles.push({
          x: x, y: y,
          vx: Math.cos(a) * speed,
          vy: Math.sin(a) * speed,
          life: 1,
          color: color,
          size: 1 + Math.random() * 2,
        });
      }
    }

    // ---------------------------------------------------------------------
    // Cập nhật hạt
    // ---------------------------------------------------------------------
    function updateParticles() {
      var decay = particleCfg.decay || 0.02;
      for (var i = particles.length - 1; i >= 0; i--) {
        var p = particles[i];
        p.x += p.vx;
        p.y += p.vy;
        p.vx *= 0.95;
        p.vy *= 0.95;
        p.life -= decay;
        if (p.life <= 0) particles.splice(i, 1);
      }
    }

    // ---------------------------------------------------------------------
    // Cập nhật nhện chính
    // ---------------------------------------------------------------------
    function updateSpider() {
      if (nodes.length === 0) return;

      // Trốn chuột
      if (mouseActive && escapeCfg.radius) {
        var mdx = spider.x - mouseX;
        var mdy = spider.y - mouseY;
        var mdist = Math.sqrt(mdx * mdx + mdy * mdy);
        if (mdist < escapeCfg.radius && mdist > 0.1) {
          var force = escapeCfg.force || 0.5;
          spider.vx += (mdx / mdist) * force;
          spider.vy += (mdy / mdist) * force;
        }
      }

      if (spider.wait > 0) {
        spider.wait--;
        spider.legPhase += 0.2;
        return;
      }

      var target = nodes[spider.index];
      var dx = target.x - spider.x;
      var dy = target.y - spider.y;
      var dist = Math.sqrt(dx * dx + dy * dy);

      if (dist < 6) {
        spider.x = target.x;
        spider.y = target.y;
        spider.vx = 0;
        spider.vy = 0;
        spider.wait = target.delay || 20;
        spider.color = target.color;
        spawnParticles(spider.x, spider.y, target.color);

        if (statEl) {
          statEl.textContent = (spider.index + 1) + ' / ' + nodes.length;
        }

        spider.index = (spider.index + 1) % nodes.length;
        return;
      }

      spider.vx += (dx / dist) * spider.speed;
      spider.vy += (dy / dist) * spider.speed;

      var sp = Math.sqrt(spider.vx * spider.vx + spider.vy * spider.vy);
      if (sp > spider.maxSpeed) {
        spider.vx = (spider.vx / sp) * spider.maxSpeed;
        spider.vy = (spider.vy / sp) * spider.maxSpeed;
      }

      spider.vx *= 0.94;
      spider.vy *= 0.94;
      spider.x += spider.vx;
      spider.y += spider.vy;

      if (sp > 0.5) {
        spider.targetAngle = Math.atan2(spider.vy, spider.vx);
      }
      var da = spider.targetAngle - spider.angle;
      while (da > Math.PI) da -= Math.PI * 2;
      while (da < -Math.PI) da += Math.PI * 2;
      spider.angle += da * 0.2;

      spider.legPhase += 0.4 + sp * 0.15;

      spider.trail.push({ x: spider.x, y: spider.y, life: 1 });
      var maxTrail = spiderCfg.trailLength || 30;
      if (spider.trail.length > maxTrail) spider.trail.shift();
      for (var i = 0; i < spider.trail.length; i++) {
        spider.trail[i].life -= 0.04;
      }
    }

    // ---------------------------------------------------------------------
    // Cập nhật nhện con
    // ---------------------------------------------------------------------
    function updateBabies() {
      var maxSpeed = babiesCfg.maxSpeed || 3;
      for (var i = 0; i < babies.length; i++) {
        var b = babies[i];
        b.wander += (Math.random() - 0.5) * 0.3;
        b.vx += Math.cos(b.wander) * 0.1;
        b.vy += Math.sin(b.wander) * 0.1;

        var dx = b.x - spider.x;
        var dy = b.y - spider.y;
        var d = Math.sqrt(dx * dx + dy * dy);
        if (d < 80 && d > 0.1) {
          b.vx += (dx / d) * 0.3;
          b.vy += (dy / d) * 0.3;
        }

        b.vx *= 0.92;
        b.vy *= 0.92;

        var bsp = Math.sqrt(b.vx * b.vx + b.vy * b.vy);
        if (bsp > maxSpeed) {
          b.vx = (b.vx / bsp) * maxSpeed;
          b.vy = (b.vy / bsp) * maxSpeed;
        }

        b.x += b.vx;
        b.y += b.vy;

        if (b.x < 20) b.vx += 0.5;
        if (b.x > W - 20) b.vx -= 0.5;
        if (b.y < 20) b.vy += 0.5;
        if (b.y > H - 20) b.vy -= 0.5;

        if (Math.abs(b.vx) + Math.abs(b.vy) > 1) {
          b.angle = Math.atan2(b.vy, b.vx);
        }
        b.legPhase += 0.5;
      }
    }

    // ---------------------------------------------------------------------
    // Vẽ thân nhện dùng chung
    // ---------------------------------------------------------------------
    function drawSpiderBody(c, s, color, angle, legPhase, glow) {
      c.save();
      c.rotate(angle + Math.PI / 2);

      if (glow) {
        c.shadowColor = color;
        c.shadowBlur = 12 * s;
      }

      c.strokeStyle = color;
      c.lineWidth = 1.5 * s;
      c.lineCap = 'round';
      for (var i = 0; i < 8; i++) {
        var side = i < 4 ? -1 : 1;
        var idx = i % 4;
        var baseAngle = -Math.PI / 2 + side * (0.5 + idx * 0.45);
        var swing = Math.sin(legPhase + i) * 0.4;
        var len1 = 7 * s;
        var len2 = 9 * s;

        var a1 = baseAngle + swing;
        var x1 = Math.cos(a1) * len1;
        var y1 = Math.sin(a1) * len1;

        var a2 = a1 + side * 0.6;
        var x2 = x1 + Math.cos(a2) * len2;
        var y2 = y1 + Math.sin(a2) * len2;

        c.beginPath();
        c.moveTo(0, 0);
        c.lineTo(x1, y1);
        c.lineTo(x2, y2);
        c.stroke();
      }

      c.fillStyle = color;
      c.beginPath();
      c.ellipse(0, 2 * s, 3.5 * s, 4.5 * s, 0, 0, Math.PI * 2);
      c.fill();

      c.beginPath();
      c.ellipse(0, -3.5 * s, 2.5 * s, 2.5 * s, 0, 0, Math.PI * 2);
      c.fill();

      c.shadowBlur = 0;
      c.fillStyle = '#ffffff';
      c.beginPath();
      c.arc(-1 * s, -4 * s, 0.7 * s, 0, Math.PI * 2);
      c.arc(1 * s, -4 * s, 0.7 * s, 0, Math.PI * 2);
      c.fill();

      c.fillStyle = color;
      c.beginPath();
      c.arc(-1 * s, -4 * s, 0.35 * s, 0, Math.PI * 2);
      c.arc(1 * s, -4 * s, 0.35 * s, 0, Math.PI * 2);
      c.fill();

      c.restore();
    }

    // ---------------------------------------------------------------------
    // Vẽ nhện chính
    // ---------------------------------------------------------------------
    function drawSpider(c) {
      c.save();
      c.translate(spider.x, spider.y);
      drawSpiderBody(c, spider.size, spider.color, spider.angle, spider.legPhase, true);
      c.restore();
    }

    // ---------------------------------------------------------------------
    // Vẽ nhện con
    // ---------------------------------------------------------------------
    function drawBabies(c) {
      for (var i = 0; i < babies.length; i++) {
        var b = babies[i];
        c.save();
        c.translate(b.x, b.y);
        c.globalAlpha = 0.7;
        drawSpiderBody(c, b.size, b.color, b.angle, b.legPhase, false);
        c.restore();
      }
      c.globalAlpha = 1;
    }

    // ---------------------------------------------------------------------
    // Vẽ vệt
    // ---------------------------------------------------------------------
    function drawTrail(c) {
      for (var i = 0; i < spider.trail.length; i++) {
        var t = spider.trail[i];
        if (t.life <= 0) continue;
        c.globalAlpha = t.life * 0.3;
        c.fillStyle = spider.color;
        c.beginPath();
        c.arc(t.x, t.y, spider.size * t.life, 0, Math.PI * 2);
        c.fill();
      }
      c.globalAlpha = 1;
    }

    // ---------------------------------------------------------------------
    // Vẽ hạt
    // ---------------------------------------------------------------------
    function drawParticles(c) {
      for (var i = 0; i < particles.length; i++) {
        var p = particles[i];
        c.globalAlpha = p.life;
        c.fillStyle = p.color;
        c.beginPath();
        c.arc(p.x, p.y, p.size, 0, Math.PI * 2);
        c.fill();
      }
      c.globalAlpha = 1;
    }

    // ---------------------------------------------------------------------
    // Vẽ node
    // ---------------------------------------------------------------------
    function drawNodes(c, time) {
      for (var i = 0; i < nodes.length; i++) {
        var n = nodes[i];
        var isTarget = i === spider.index;
        var pulse = 1 + Math.sin(time * 0.003 + n.pulse) * 0.1;

        if (isTarget) {
          c.beginPath();
          c.arc(n.x, n.y, n.radius * pulse * 1.4, 0, Math.PI * 2);
          c.strokeStyle = n.color;
          c.globalAlpha = 0.3;
          c.lineWidth = 1;
          c.stroke();
          c.globalAlpha = 1;
        }

        c.beginPath();
        c.arc(n.x, n.y, n.radius * pulse, 0, Math.PI * 2);
        c.fillStyle = isTarget
          ? 'rgba(192, 96, 255, 0.15)'
          : 'rgba(255, 255, 255, 0.03)';
        c.fill();

        c.strokeStyle = isTarget ? n.color : 'rgba(255, 255, 255, 0.15)';
        c.lineWidth = isTarget ? 2 : 1;
        c.stroke();

        c.fillStyle = isTarget ? '#ffffff' : 'rgba(255, 255, 255, 0.55)';
        c.font = '11px Courier New';
        c.textAlign = 'center';
        c.textBaseline = 'middle';
        c.fillText(n.label, n.x, n.y);
      }
    }

    // ---------------------------------------------------------------------
    // Vòng lặp render
    // ---------------------------------------------------------------------
    var startTime = performance.now();
    function loop(now) {
      var t = now - startTime;

      ctx.fillStyle = 'rgba(5, 5, 8, 0.25)';
      ctx.fillRect(0, 0, W, H);

      drawNodes(ctx, t);
      drawTrail(ctx);
      updateSpider();
      drawSpider(ctx);

      updateBabies();
      drawBabies(ctx);

      updateParticles();
      drawParticles(ctx);

      requestAnimationFrame(loop);
    }

    // ---------------------------------------------------------------------
    // Sự kiện
    // ---------------------------------------------------------------------
    window.addEventListener('resize', resize);
    window.addEventListener('mousemove', function (e) {
      mouseX = e.clientX;
      mouseY = e.clientY;
      mouseActive = true;
    });
    window.addEventListener('mouseleave', function () {
      mouseActive = false;
    });
    window.addEventListener('touchmove', function (e) {
      if (e.touches.length > 0) {
        mouseX = e.touches[0].clientX;
        mouseY = e.touches[0].clientY;
        mouseActive = true;
      }
    }, { passive: true });
    window.addEventListener('touchend', function () {
      mouseActive = false;
    });

    // Khởi tạo
    resize();
    requestAnimationFrame(loop);
  });
})();
