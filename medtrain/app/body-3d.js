/* 影知 · BodyParts3D 3D 适配器（首页人体模型）
 *
 * 实现 body-model.js 预留的适配器契约：
 *   window.YZ_BODY_MODEL_ADAPTER = { name, mount(el, opts) -> handle }
 *   handle: highlight(regionId) / reset() / resize() / dispose() / status()
 *
 * 模型：BodyParts3D 4.0（CC BY 4.0），mm→m、Z-up→Y-up，13 个可点击单元 + 体表轮廓。
 * 依赖：./vendor/three.module.js（页面需提供 importmap: "three"）。
 */
(function () {
  "use strict";

  var MODEL_BASE = ""; // manifest 内的 file 字段已含 models/ 前缀
  var MM = 0.001;

  var STYLE = {
    body:     { color: 0xcfe6ee, opacity: 0.05 },
    skull:    { color: 0xdfe9ee, opacity: 0.14 },
    brain:    { color: 0xd9a6e8, opacity: 0.92 },
    neck:     { color: 0xf0b27a, opacity: 0.94 },
    lung:     { color: 0x7fb6d6, opacity: 0.34 },
    heart:    { color: 0xe0686a, opacity: 0.96 },
    ribcage:  { color: 0xdfe9ee, opacity: 0.14 },
    liver:    { color: 0xb85a3a, opacity: 0.96 },
    gitract:  { color: 0xd9a860, opacity: 0.42 },
    kidney:   { color: 0x9dc46a, opacity: 0.92 },
    pancreas: { color: 0xe0c46a, opacity: 0.92 },
    spine:    { color: 0xe8f0f5, opacity: 0.92 },
    pelvis:   { color: 0xdfe9ee, opacity: 0.45 },
    limbs:    { color: 0xdfe9ee, opacity: 0.32 }
  };

  var REGION_COLOR = {
    "REG-CHEST": "#2fb3c4",
    "REG-HEAD-NECK": "#8b7fd4",
    "REG-BREAST": "#d47fa8",
    "REG-ABDOMEN": "#c99a3f",
    "REG-MSK": "#3fa87a"
  };

  function hasWebGL() {
    try {
      var c = document.createElement("canvas");
      return !!(c.getContext("webgl2") || c.getContext("webgl"));
    } catch (e) {
      return false;
    }
  }

  function mount(el, opts) {
    if (!el) throw new Error("3D 适配器需要一个容器元素");
    if (!hasWebGL()) throw new Error("当前浏览器未启用 WebGL");

    var o = opts || {};
    var state = {
      el: el,
      active: null,
      meshes: new Map(),
      pickables: [],
      hovered: null,
      ready: false,
      failed: null,
      disposed: false,
      raf: 0,
      visible: true
    };

    el.classList.add("bm3d-on");
    el.innerHTML =
      '<div class="bm3d">' +
      '<canvas class="bm3d-canvas"></canvas>' +
      '<div class="bm3d-load" data-bm3d-load>正在载入解剖模型…</div>' +
      '<div class="bm3d-tip" data-bm3d-tip hidden></div>' +
      '<div class="bm3d-hint">拖动旋转 · 滚轮缩放 · 点击部位</div>' +
      "</div>";

    var handle = {
      mode: "adapter",
      el: el,
      highlight: function (id) {
        state.active = id || null;
        if (state.paint) state.paint();
      },
      reset: function () {
        state.active = null;
        if (state.paint) state.paint();
      },
      resize: function () {
        if (state.resizeFn) state.resizeFn();
      },
      dispose: function () {
        if (state.disposed) return;
        state.disposed = true;
        if (state.raf) cancelAnimationFrame(state.raf);
        if (state.cleanup) state.cleanup();
        el.innerHTML = "";
      },
      status: function () {
        return {
          contract: "1.0",
          mode: "adapter",
          adapterName: "three-body",
          ready: state.ready,
          note: state.failed
            ? "3D 模型加载失败：" + state.failed
            : state.ready
              ? "BodyParts3D 4.0 · 13 个可点击单元"
              : "3D 模型加载中"
        };
      }
    };

    init(state, o, handle);
    return handle;
  }

  function init(state, opts, handle) {
    var el = state.el;
    var canvas = el.querySelector(".bm3d-canvas");
    var loadEl = el.querySelector("[data-bm3d-load]");
    var tipEl = el.querySelector("[data-bm3d-tip]");

    Promise.all([
      import("three"),
      import("./vendor/OrbitControls.js"),
      import("./vendor/OBJLoader.js")
    ])
      .then(function (mods) {
        return start(mods[0], mods[1].OrbitControls, mods[2].OBJLoader);
      })
      .catch(function (err) {
        fail(err);
      });

    function fail(err) {
      state.failed = String((err && err.message) || err);
      el.classList.remove("bm3d-on");
      console.error("[body-3d]", err);
      // 异步失败也回落到 SVG，保证首页仍可选择部位
      if (window.YZ && window.YZ.BodyModel && typeof window.YZ.BodyModel.mountSvg === "function") {
        try {
          window.YZ.BodyModel.mountSvg(el, opts);
          handle.mode = "svg-fallback";
          return;
        } catch (e2) {
          console.error("[body-3d] svg fallback failed", e2);
        }
      }
      if (loadEl) loadEl.textContent = "3D 模型加载失败：" + state.failed;
    }

    function start(THREE, OrbitControls, OBJLoader) {
      var scene = new THREE.Scene();
      var camera = new THREE.PerspectiveCamera(30, 1, 0.05, 40);
      var renderer = new THREE.WebGLRenderer({
        canvas: canvas,
        antialias: true,
        alpha: true,
        powerPreference: "high-performance"
      });
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      renderer.toneMapping = THREE.ACESFilmicToneMapping;
      renderer.toneMappingExposure = 1.12;
      renderer.outputColorSpace = THREE.SRGBColorSpace;

      scene.add(new THREE.HemisphereLight(0xbcd8e6, 0x0a1a20, 1.15));

      var key = new THREE.DirectionalLight(0xffffff, 2.0);
      key.position.set(1.4, 2.4, 2.0);
      scene.add(key);

      var fill = new THREE.DirectionalLight(0x86b6ff, 0.8);
      fill.position.set(-2.0, 0.9, 0.6);
      scene.add(fill);

      var rim = new THREE.DirectionalLight(0xbfe6ea, 0.6);
      rim.position.set(-0.6, 1.2, -2.4);
      scene.add(rim);

      var controls = new OrbitControls(camera, canvas);
      controls.enableDamping = true;
      controls.dampingFactor = 0.08;
      controls.enablePan = false;
      controls.minDistance = 0.6;
      controls.maxDistance = 6;
      controls.minPolarAngle = 0.35;
      controls.maxPolarAngle = Math.PI - 0.35;
      controls.rotateSpeed = 0.8;

      var target = new THREE.Vector3(0, 0.86, 0);
      controls.target.copy(target);

      function fit() {
        var w = el.clientWidth || 360;
        var h = el.clientHeight || 480;
        renderer.setSize(w, h, false);
        camera.aspect = w / h;
        camera.updateProjectionMatrix();

        var need = 1.82; // 含头顶与脚底余量
        var dist = need / 2 / Math.tan((camera.fov * Math.PI) / 180 / 2);
        // 窄容器适当拉远，保证肩宽也在画面内
        if (camera.aspect < 0.62) dist *= 0.62 / camera.aspect;
        camera.position.set(dist * 0.1, 0.88, dist);
        camera.lookAt(target);
      }
      fit();

      state.resizeFn = fit;
      var ro = new ResizeObserver(function () {
        fit();
      });
      ro.observe(el);

      var raycaster = new THREE.Raycaster();
      var pointer = new THREE.Vector2();

      function pick(clientX, clientY) {
        var rect = canvas.getBoundingClientRect();
        pointer.x = ((clientX - rect.left) / rect.width) * 2 - 1;
        pointer.y = -((clientY - rect.top) / rect.height) * 2 + 1;
        raycaster.setFromCamera(pointer, camera);
        var hits = raycaster.intersectObjects(state.pickables, false);
        if (!hits.length) return null;
        var solid = hits.find(function (h) {
          return h.object.material.opacity >= 0.5;
        });
        return solid || hits[0];
      }

      var down = null;
      function onDown(e) {
        down = { x: e.clientX, y: e.clientY };
      }
      function onMove(e) {
        if (down) return;
        var hit = pick(e.clientX, e.clientY);
        hover(hit ? hit.object : null, e.clientX, e.clientY);
      }
      function onUp(e) {
        if (!down) return;
        var moved = Math.abs(e.clientX - down.x) + Math.abs(e.clientY - down.y);
        down = null;
        if (moved > 6) return;
        var hit = pick(e.clientX, e.clientY);
        if (!hit) return;
        var regionId = hit.object.userData.unit.region;
        if (!regionId) return;
        state.active = regionId;
        paint();
        if (typeof opts.onSelect === "function") opts.onSelect(regionId, regionId);
      }
      function onLeave() {
        down = null;
        hover(null);
      }

      canvas.addEventListener("pointerdown", onDown);
      canvas.addEventListener("pointermove", onMove);
      canvas.addEventListener("pointerup", onUp);
      canvas.addEventListener("pointerleave", onLeave);

      var io = new IntersectionObserver(
        function (entries) {
          state.visible = entries[0].isIntersecting;
        },
        { threshold: 0.02 }
      );
      io.observe(el);

      state.cleanup = function () {
        ro.disconnect();
        io.disconnect();
        canvas.removeEventListener("pointerdown", onDown);
        canvas.removeEventListener("pointermove", onMove);
        canvas.removeEventListener("pointerup", onUp);
        canvas.removeEventListener("pointerleave", onLeave);
        controls.dispose();
        renderer.dispose();
      };

      function animate() {
        if (state.disposed) return;
        state.raf = requestAnimationFrame(animate);
        controls.update();
        if (state.visible) renderer.render(scene, camera);
      }
      animate();

      function hover(mesh, x, y) {
        if (state.hovered === mesh) {
          if (mesh && x != null) placeTip(x, y);
          return;
        }
        if (state.hovered) paintMesh(state.hovered, null);
        state.hovered = mesh;
        canvas.style.cursor = mesh ? "pointer" : "grab";

        if (!mesh) {
          tipEl.hidden = true;
          return;
        }
        var unit = mesh.userData.unit;
        paintMesh(mesh, {
          emissive: REGION_COLOR[unit.region] || "#2fb3c4",
          intensity: 0.45
        });
        var name = (state.names && state.names[unit.region]) || unit.region;
        tipEl.textContent = (unit.label || unit.name) + " · " + name;
        tipEl.hidden = false;
        placeTip(x, y);
      }

      function placeTip(x, y) {
        var rect = el.getBoundingClientRect();
        var lx = x - rect.left + 12;
        var ly = y - rect.top + 12;
        if (lx + tipEl.offsetWidth > rect.width - 8) lx = x - rect.left - tipEl.offsetWidth - 12;
        if (ly + tipEl.offsetHeight > rect.height - 8) ly = y - rect.top - tipEl.offsetHeight - 12;
        tipEl.style.left = Math.max(6, lx) + "px";
        tipEl.style.top = Math.max(6, ly) + "px";
      }

      function paintMesh(mesh, hi) {
        if (!mesh) return;
        if (hi) {
          mesh.material.emissive = new THREE.Color(hi.emissive);
          mesh.material.emissiveIntensity = hi.intensity;
        } else {
          mesh.material.emissiveIntensity = 0;
        }
      }

      function paint() {
        state.meshes.forEach(function (list, unitId) {
          if (unitId === "body") return;
          var unit = list[0] && list[0].userData.unit;
          var on = unit && unit.region === state.active;
          list.forEach(function (mesh) {
            var base = mesh.userData.baseOpacity;
            if (!state.active) {
              mesh.material.opacity = base;
              mesh.material.emissiveIntensity = 0;
              return;
            }
            if (on) {
              mesh.material.opacity = Math.min(1, base + 0.14);
              mesh.material.emissive = new THREE.Color(REGION_COLOR[state.active] || "#2fb3c4");
              mesh.material.emissiveIntensity = 0.16;
            } else {
              mesh.material.opacity = base * 0.3;
              mesh.material.emissiveIntensity = 0;
            }
          });
        });
      }

      state.paint = paint;

      // 载入模型
      fetch(MODEL_BASE + "models/manifest.json")
        .then(function (r) {
          if (!r.ok) throw new Error("模型清单读取失败 (" + r.status + ")");
          return r.json();
        })
        .then(function (manifest) {
          var names = {};
          (opts.regions || []).forEach(function (r) {
            names[r.id] = r.name;
          });
          state.names = names;

          var loader = new OBJLoader();
          var total = manifest.units.length;
          var done = 0;

          return Promise.all(
            manifest.units.map(function (unit) {
              return new Promise(function (resolve) {
                loader.load(
                  MODEL_BASE + unit.file,
                  function (obj) {
                    try {
                      mountUnit(obj, unit);
                    } catch (err) {
                      console.error("[body-3d] mount failed", unit.id, err);
                    }
                    done += 1;
                    if (loadEl) loadEl.textContent = "正在载入解剖模型… " + done + "/" + total;
                    resolve();
                  },
                  undefined,
                  function (err) {
                    console.error("[body-3d] load failed", unit.file, err);
                    done += 1;
                    resolve();
                  }
                );
              });
            })
          );
        })
        .then(function () {
          state.ready = true;
          if (loadEl) loadEl.hidden = true;
          el.classList.add("bm3d-on");
          paint();
        })
        .catch(fail);

      function mountUnit(obj, unit) {
        var style = STYLE[unit.id] || { color: 0xcccccc, opacity: 0.9 };
        var transparent = style.opacity < 1;
        var meshes = [];

        obj.traverse(function (child) {
          if (!child.isMesh) return;
          var geom = child.geometry;
          var pos = geom.attributes.position;
          for (var i = 0; i < pos.count; i += 1) {
            var x = pos.getX(i);
            var y = pos.getY(i);
            var z = pos.getZ(i);
            pos.setXYZ(i, x * MM, z * MM, -y * MM);
          }
          pos.needsUpdate = true;
          geom.computeVertexNormals();
          geom.computeBoundingSphere();

          var mat =
            unit.id === "body"
              ? new THREE.MeshBasicMaterial({
                  color: style.color,
                  transparent: true,
                  opacity: style.opacity,
                  depthWrite: false,
                  side: THREE.FrontSide
                })
              : new THREE.MeshStandardMaterial({
                  color: style.color,
                  roughness: 0.62,
                  metalness: 0.03,
                  transparent: transparent,
                  opacity: style.opacity,
                  depthWrite: !transparent,
                  side: transparent ? THREE.DoubleSide : THREE.FrontSide
                });

          var mesh = new THREE.Mesh(geom, mat);
          mesh.userData.unit = unit;
          mesh.userData.baseOpacity = style.opacity;
          mesh.renderOrder = unit.id === "body" ? 3 : transparent ? 2 : 1;
          mesh.frustumCulled = false;

          scene.add(mesh);
          meshes.push(mesh);
          if (unit.region) state.pickables.push(mesh);
        });

        state.meshes.set(unit.id, meshes);
      }
    }
  }

  window.YZ_BODY_MODEL_ADAPTER = {
    name: "three-body",
    version: "1.0.0",
    mount: mount
  };
})();
