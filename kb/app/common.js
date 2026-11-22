/* RadioCheck · 阅片四页共享外壳
 * 顶栏品牌、导航、页面参数、通用提示集中在这里；四页不再各自复制一份。
 */
(function () {
  'use strict';

  /* v7 收缩版不再使用 Service Worker；清掉旧版缓存，避免演示时看到旧页面 */
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.getRegistrations().then(function (rs) {
      rs.forEach(function (r) { r.unregister(); });
    }).catch(function () {});
  }
  if (window.caches && caches.keys) {
    caches.keys().then(function (ks) {
      ks.forEach(function (k) { caches.delete(k); });
    }).catch(function () {});
  }

  const NAV = [
    { id: 'clinic', label: '胸片阅片', href: 'clinic.html', hint: '唯一功能页' },
    { id: 'home', label: '方法与边界', href: '../index.html#method', hint: '范围、数据与声明' },
  ];

  function barHTML(page) {
    const nav = NAV.map((n) =>
      `<a href="${n.href}" class="${n.id === page ? 'on' : ''}" title="${n.hint}">${n.label}</a>`
    ).join('');
    return `
      <a class="logo" href="../index.html" title="RadioCheck · 返回首页">
        <span class="m">R</span>
        <div><b>RadioCheck · 影像循证</b><i>REGION · CITATION · TRACE</i></div>
      </a>
      <nav class="switch" aria-label="页面导航">${nav}</nav>`;
  }

  function mountBar() {
    const bar = document.querySelector('.bar[data-page]');
    if (!bar) return;
    bar.insertAdjacentHTML('afterbegin', barHTML(bar.dataset.page));
  }

  function query(key) {
    try { return new URLSearchParams(location.search).get(key) || ''; }
    catch (e) { return ''; }
  }

  function toast(msg, ms) {
    let el = document.getElementById('yzToast');
    if (!el) {
      el = document.createElement('div');
      el.id = 'yzToast';
      el.style.cssText = 'position:fixed;left:50%;bottom:26px;transform:translateX(-50%) translateY(8px);' +
        'background:#10232e;color:#fff;font-size:12.5px;padding:9px 15px;border-radius:9px;' +
        'box-shadow:0 10px 30px -12px rgba(0,0,0,.5);opacity:0;transition:.22s;z-index:9999;' +
        'pointer-events:none;max-width:70vw;text-align:center';
      document.body.appendChild(el);
    }
    el.textContent = msg;
    requestAnimationFrame(() => { el.style.opacity = '1'; el.style.transform = 'translateX(-50%) translateY(0)'; });
    clearTimeout(el._t);
    el._t = setTimeout(() => {
      el.style.opacity = '0';
      el.style.transform = 'translateX(-50%) translateY(8px)';
    }, ms || 2200);
  }

  function fitFrame(img, container, frame) {
    if (!img || !container || !frame || !img.naturalWidth) return;
    const W = container.clientWidth - 6, H = container.clientHeight - 6;
    const sc = Math.min(W / img.naturalWidth, H / img.naturalHeight, 1.4);
    frame.style.width = Math.round(img.naturalWidth * sc) + 'px';
    frame.style.height = Math.round(img.naturalHeight * sc) + 'px';
    img.style.width = '100%';
    img.style.height = '100%';
  }

  mountBar();

  window.YZCommon = { NAV, query, toast, fitFrame, mountBar };
})();
