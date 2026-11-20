/* RadioCheck · 快捷进入组件
 *
 * 做三件事：
 *   1. 注册 Service Worker（离线外壳 + 二次打开更快）
 *   2. 接管浏览器安装事件，把「安装到桌面/主屏」变成页面里的一个按钮
 *   3. 按平台给出可执行的入口说明（Chrome/Edge 安装、iOS 添加到主屏幕）
 *
 * 页面里只需放带 .js-install 的按钮和 #pwaState / #pwaHint 两个占位节点，
 * 没有这些节点时脚本静默跳过，不影响其它页面。
 */
(function () {
  'use strict';

  var isHttp = location.protocol === 'http:' || location.protocol === 'https:';
  var standalone =
    window.matchMedia('(display-mode: standalone)').matches ||
    window.matchMedia('(display-mode: window-controls-overlay)').matches ||
    window.navigator.standalone === true;

  var deferredPrompt = null;
  var stateEl = document.getElementById('pwaState');
  var hintEl = document.getElementById('pwaHint');
  var installBtns = Array.prototype.slice.call(document.querySelectorAll('.js-install'));

  function setState(text, kind) {
    if (!stateEl) return;
    stateEl.textContent = text;
    stateEl.dataset.kind = kind || '';
  }

  function setHint(html) {
    if (hintEl) hintEl.innerHTML = html;
  }

  function showButtons(show) {
    installBtns.forEach(function (btn) {
      btn.hidden = !show;
      btn.setAttribute('aria-hidden', show ? 'false' : 'true');
    });
  }

  function platformHint() {
    var ua = navigator.userAgent;
    var isIOS = /iPad|iPhone|iPod/.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
    var isAndroid = /Android/.test(ua);
    if (isIOS) {
      return '在 Safari 中点底部「分享」→「添加到主屏幕」，桌面就会出现「RadioCheck」图标。';
    }
    if (isAndroid) {
      return '在 Chrome 中点右上角「⋮」→「安装应用」或「添加到主屏幕」。';
    }
    return '在 Chrome / Edge 中点击地址栏右侧的安装图标，或使用本页按钮；安装后从桌面/程序坞直接打开。';
  }

  if (isHttp) {
    var script = document.currentScript;
    var base = script ? new URL('./', script.src) : new URL('./', location.href);
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker
        .register(new URL('sw.js', base), { scope: base.pathname })
        .catch(function () { /* 本地 file:// 或隐私模式会失败，不影响使用 */ });
    }
  }

  if (standalone) {
    document.documentElement.classList.add('pwa-standalone');
    setState('已作为独立应用运行', 'ok');
    setHint('从桌面或主屏图标启动，没有地址栏。');
    showButtons(false);
  } else {
    setState('网页版 · 可安装为桌面应用', 'idle');
    setHint(platformHint());
    showButtons(false);
  }

  window.addEventListener('beforeinstallprompt', function (e) {
    e.preventDefault();
    deferredPrompt = e;
    setState('可以安装到这台设备', 'ready');
    setHint('安装后从桌面/主屏一键直达，独立窗口打开，不经过浏览器地址栏。');
    showButtons(true);
  });

  window.addEventListener('appinstalled', function () {
    deferredPrompt = null;
    setState('已安装 · 从桌面图标启动', 'ok');
    setHint('之后从桌面、程序坞或主屏图标打开「RadioCheck」即可。');
    showButtons(false);
  });

  installBtns.forEach(function (btn) {
    btn.addEventListener('click', function (ev) {
      ev.preventDefault();
      if (deferredPrompt) {
        deferredPrompt.prompt();
        deferredPrompt.userChoice.then(function (choice) {
          if (choice && choice.outcome === 'accepted') {
            setState('正在安装…', 'ready');
          } else {
            setState('已取消安装，可随时再装', 'idle');
          }
          deferredPrompt = null;
          showButtons(false);
        });
        return;
      }
      // 浏览器没有给出安装事件（iOS / 已安装 / 非 HTTPS）：展开手动说明
      var box = document.getElementById('pwaHint');
      if (box) {
        box.innerHTML = platformHint();
        box.classList.add('is-flash');
        setTimeout(function () { box.classList.remove('is-flash'); }, 1200);
      }
      setState('按下面的说明手动添加', 'idle');
    });
  });

  // 页内锚点：安装卡片被点到时平滑滚动过去
  Array.prototype.forEach.call(document.querySelectorAll('[data-scroll="install"]'), function (el) {
    el.addEventListener('click', function (ev) {
      var target = document.getElementById('install');
      if (!target) return;
      ev.preventDefault();
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  });
})();
