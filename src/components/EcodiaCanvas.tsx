// src/components/vox/EcodiaCanvas.tsx
"use client";

import React, { useEffect, useRef } from "react";
import * as THREE from "three";
import { EffectComposer } from "three/examples/jsm/postprocessing/EffectComposer.js";
import { RenderPass } from "three/examples/jsm/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/examples/jsm/postprocessing/UnrealBloomPass.js";

/* =======================
   Palette (Sunrise Solarpunk)
   ======================= */
const COLORS = {
  deepForest: new THREE.Color(0x396041),
  ecoGreen: new THREE.Color(0x7fd069),
  solarYellow: new THREE.Color(0xf4d35e),
  sleekWhite: new THREE.Color(0xffffff),
  coolCyan: new THREE.Color(0xd4fff1),

  bgPearl: new THREE.Color(0xf5f8f7),
  fogMint: new THREE.Color(0xe8f4ee),
};

/* =======================
   Parallax (moderate)
   ======================= */
const PARALLAX = {
  laminarX: 0.040,
  laminarY: 0.020,
  camX: 0.75,
  camY: 0.50,
};

/* =======================
   GLSL building blocks
   ======================= */
const GLSL_NOISE = `
vec4 permute(vec4 x){return mod(((x*34.0)+1.0)*x, 289.0);}
vec4 taylorInvSqrt(vec4 r){return 1.79284291400159 - 0.85373472095314 * r;}
vec3 fade(vec3 t){return t*t*t*(t*(t*6.0-15.0)+10.0);}
float cnoise(vec3 P){
  vec3 Pi0 = floor(P), Pi1 = Pi0 + vec3(1.0);
  Pi0 = mod(Pi0, 289.0); Pi1 = mod(Pi1, 289.0);
  vec3 Pf0 = fract(P), Pf1 = Pf0 - vec3(1.0);
  vec4 ix = vec4(Pi0.x, Pi1.x, Pi0.x, Pi1.x);
  vec4 iy = vec4(Pi0.y, Pi0.y, Pi1.y, Pi1.y);
  vec4 iz0 = Pi0.zzzz, iz1 = Pi1.zzzz;
  vec4 ixy = permute(permute(ix) + iy);
  vec4 ixy0 = permute(ixy + iz0); vec4 ixy1 = permute(ixy + iz1);
  vec4 gx0 = ixy0 / 7.0; vec4 gy0 = fract(floor(gx0)/7.0) - 0.5; gx0 = fract(gx0);
  vec4 gz0 = vec4(0.5) - abs(gx0) - abs(gy0); vec4 sz0 = step(gz0, vec4(0.0));
  gx0 -= sz0*(step(0.0,gx0)-0.5); gy0 -= sz0*(step(0.0,gy0)-0.5);
  vec4 gx1 = ixy1 / 7.0; vec4 gy1 = fract(floor(gx1)/7.0) - 0.5; gx1 = fract(gx1);
  vec4 gz1 = vec4(0.5) - abs(gx1) - abs(gy1); vec4 sz1 = step(gz1, vec4(0.0));
  gx1 -= sz1*(step(0.0,gx1)-0.5); gy1 -= sz1*(step(0.0,gy1)-0.5);
  vec3 g000 = vec3(gx0.x,gy0.x,gz0.x), g100 = vec3(gx0.y,gy0.y,gz0.y);
  vec3 g010 = vec3(gx0.z,gy0.z,gz0.z), g110 = vec3(gx0.w,gy0.w,gz0.w);
  vec3 g001 = vec3(gx1.x,gy1.x,gz1.x), g101 = vec3(gx1.y,gy1.y,gz1.y);
  vec3 g011 = vec3(gx1.z,gy1.z,gz1.z), g111 = vec3(gx1.w,gy1.w,gz1.w);
  vec4 norm0 = taylorInvSqrt(vec4(dot(g000,g000),dot(g010,g010),dot(g100,g100),dot(g110,g110)));
  g000*=norm0.x; g010*=norm0.y; g100*=norm0.z; g110*=norm0.w;
  vec4 norm1 = taylorInvSqrt(vec4(dot(g001,g001),dot(g011,g011),dot(g101,g101),dot(g111,g111)));
  g001*=norm1.x; g011*=norm1.y; g101*=norm1.z; g111*=norm1.w;
  float n000 = dot(g000, Pf0);
  float n100 = dot(g100, vec3(Pf1.x, Pf0.y, Pf0.z));
  float n010 = dot(g010, vec3(Pf0.x, Pf1.y, Pf0.z));
  float n110 = dot(g110, vec3(Pf1.x, Pf1.y, Pf0.z));
  float n001 = dot(g001, vec3(Pf0.x, Pf0.y, Pf1.z));
  float n101 = dot(g101, vec3(Pf1.x, Pf0.y, Pf1.z));
  float n011 = dot(g011, vec3(Pf0.x, Pf1.y, Pf1.z));
  float n111 = dot(g111, vec3(Pf1.x, Pf1.y, Pf1.z));
  vec3 fade_xyz = fade(Pf0);
  vec4 n_z = mix(vec4(n000,n100,n010,n110), vec4(n001,n101,n011,n111), fade_xyz.z);
  vec2 n_yz = mix(n_z.xy, n_z.zw, fade_xyz.y);
  float n_xyz = mix(n_yz.x, n_yz.y, fade_xyz.x);
  return 2.2 * n_xyz;
}
vec3 curl(vec3 p){
  float e = 0.1;
  float n1 = cnoise(p + vec3(0.0, e, 0.0));
  float n2 = cnoise(p - vec3(0.0, e, 0.0));
  float n3 = cnoise(p + vec3(e, 0.0, 0.0));
  float n4 = cnoise(p - vec3(e, 0.0, 0.0));
  float n5 = cnoise(p + vec3(0.0, 0.0, e));
  float n6 = cnoise(p - vec3(0.0, 0.0, e));
  vec3 grad = vec3((n5 - n6), (n3 - n4), (n1 - n2)) / (2.0*e);
  return normalize(vec3(grad.y - grad.z, grad.z - grad.x, grad.x - grad.y));
}
`;

/* =======================
   Tunables (brighter but controlled)
   ======================= */
const TUNE = {
  particleCount: 2000,
  glintCount: 50,
  lineCount: 600,
  sphereRadius: 48,
  flowSpeed: 0.12,
  noiseScale: 0.055,
  pulseSpeed: 1.0,
  // Post look (brighter than last version, not washed)
  exposure: 0.52,
  bloom: { strength: 0.50, radius: 1.05, threshold: 0.94 },
  fogDensity: 0.0105,
};

/* =======================
   Tendril helpers
   ======================= */
function makeCurvesAroundSphere(count: number, radius: number) {
  const curves: THREE.CatmullRomCurve3[] = [];
  for (let i = 0; i < count; i++) {
    const pts: THREE.Vector3[] = [];
    const turns = 3 + Math.floor(Math.random() * 3); // 3–5 control points
    let base = new THREE.Vector3().randomDirection().multiplyScalar(radius * 0.6);
    for (let k = 0; k < turns; k++) {
      const jitter = new THREE.Vector3().randomDirection().multiplyScalar(radius * 0.35);
      const p = base.clone().add(jitter);
      pts.push(p);
      base.add(new THREE.Vector3().randomDirection().multiplyScalar(radius * 0.25));
    }
    const curve = new THREE.CatmullRomCurve3(pts, false, "catmullrom", 0.65);
    curves.push(curve);
  }
  return curves;
}

function createTendrils(scene: THREE.Scene, c1: THREE.Color, c2: THREE.Color) {
  const TENDRIL_COUNT = 18;
  const SEGMENTS = 140;
  const RADIUS = 0.06;
  const curves = makeCurvesAroundSphere(TENDRIL_COUNT, 24);
  const group = new THREE.Group();

  const uniforms = {
    u_time: { value: 0 },
    u_cA: { value: c1.clone() },
    u_cB: { value: c2.clone() },
    u_emissive: { value: 0.95 }, // brighter emission
  };

  const mat = new THREE.ShaderMaterial({
    uniforms,
    vertexShader: `
      ${GLSL_NOISE}
      uniform float u_time;
      varying float vAlong;
      varying float vDepth;
      varying float vFresnel;
      varying vec3  vColMix;
      void main(){
        vec3 p = position;

        // Along-tube coordinate
        vAlong = uv.y;

        // Curl wobble
        vec3 v = curl(p * 0.05 + vec3(u_time*0.12));
        p += v * 0.3;

        // Depth cue
        vDepth = clamp((p.z + 48.0) / 96.0, 0.0, 1.0);

        // Fresnel rim for luminous edge
        vec3 n = normalize(normalMatrix * normal);
        vec3 viewPos = (modelViewMatrix * vec4(p,1.0)).xyz;
        vec3 V = normalize(-viewPos);
        vFresnel = pow(1.0 - max(dot(n, V), 0.0), 2.0);

        gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0);
      }
    `,
    fragmentShader: `
      uniform float u_time, u_emissive;
      uniform vec3  u_cA, u_cB;
      varying float vAlong;
      varying float vDepth;
      varying float vFresnel;
      void main(){
        // traveling pulse
        float head = fract(u_time*0.28);
        float d = abs(vAlong - head);
        float pulse = smoothstep(0.16, 0.0, d);
        pulse = pow(pulse, 3.0);

        vec3 col = mix(u_cA, u_cB, vDepth);

        // Base alpha + fresnel rim + pulse
        float alpha = 0.42 + 0.18*(1.0 - vDepth) + pulse * 0.35 + vFresnel * 0.25;

        // Emission boost (kept under control to avoid wash)
        float e = (0.65 + u_emissive * (0.50 + pulse*0.70) + vFresnel*0.35);
        gl_FragColor = vec4(col * e, alpha);

        if (gl_FragColor.a < 0.03) discard;
      }
    `,
    transparent: true,
    depthTest: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending, // restore glow
  });

  curves.forEach((c) => {
    const tube = new THREE.TubeGeometry(c, SEGMENTS, RADIUS, 6, false);
    const mesh = new THREE.Mesh(tube, mat);
    group.add(mesh);
  });

  scene.add(group);
  return { group, uniforms };
}

/* =======================
   Component
   ======================= */
const EcodiaCanvas: React.FC = () => {
  const mountRef = useRef<HTMLDivElement>(null);
  const raf = useRef<number | null>(null);

  useEffect(() => {
    if (!mountRef.current) return;
    const mount = mountRef.current;

    /* Scene */
    const scene = new THREE.Scene();
    scene.background = COLORS.bgPearl.clone();
    scene.fog = new THREE.FogExp2(COLORS.fogMint.clone(), TUNE.fogDensity);

    const width = mount.clientWidth;
    const height = mount.clientHeight;

    const camera = new THREE.PerspectiveCamera(70, width / height, 0.1, 1000);
    camera.position.set(0, 0, 22);

    const renderer = new THREE.WebGLRenderer({
      antialias: true,
      alpha: false,
      powerPreference: "high-performance",
      premultipliedAlpha: false,
    });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = TUNE.exposure;
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    mount.appendChild(renderer.domElement);

    /* Post */
    const composer = new EffectComposer(renderer);
    const renderPass = new RenderPass(scene, camera);
    composer.addPass(renderPass);
    const bloomPass = new UnrealBloomPass(
      new THREE.Vector2(width, height),
      TUNE.bloom.strength,
      TUNE.bloom.radius,
      TUNE.bloom.threshold
    );
    composer.addPass(bloomPass);

    /* Mouse (container space) */
    const mouse = new THREE.Vector2(0, 0);
    const onPointerMove = (e: MouseEvent) => {
      const rect = mount.getBoundingClientRect();
      mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      mouse.y = -(((e.clientY - rect.top) / rect.height) * 2 - 1);
    };
    mount.addEventListener("mousemove", onPointerMove);

    /* ===== Laminar Flow Plane (brighter/clearer) ===== */
    const laminarUniforms = {
      u_time: { value: 0 },
      u_mouse: { value: new THREE.Vector2(0, 0) },
      u_c1: { value: COLORS.ecoGreen.clone() },
      u_c2: { value: COLORS.solarYellow.clone() },
      u_bg: { value: COLORS.bgPearl.clone() },
      u_aspect: { value: width / height },
      u_mix: { value: 0.42 },     // more visible than 0.34
      u_filament: { value: 0.08 },// brighter micro-specular
      u_px: { value: PARALLAX.laminarX },
      u_py: { value: PARALLAX.laminarY },
    };

    const laminarMat = new THREE.ShaderMaterial({
      uniforms: laminarUniforms,
      vertexShader: `
        varying vec2 vUv;
        void main(){
          vUv = uv;
          vec3 pos = position;
          float bend = 6.0;
          float ny = pos.y / 30.0;
          pos.z -= pow(abs(ny), 2.0) * bend;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(pos, 1.0);
        }
      `,
      fragmentShader: `
        ${GLSL_NOISE}
        uniform float u_time, u_mix, u_filament, u_aspect, u_px, u_py;
        uniform vec2  u_mouse;
        uniform vec3  u_c1, u_c2, u_bg;
        varying vec2  vUv;
        void main(){
          vec2 uv = vUv;
          uv.x += u_mouse.x * u_px;
          uv.y += u_mouse.y * u_py;

          float t = u_time * ${TUNE.flowSpeed.toFixed(3)};
          float band = 0.0;
          for (int i=0;i<3;i++){
            float s = float(i+1) * 0.8;
            band += 0.4 * cnoise(vec3(uv.x*(3.0*s), uv.y*0.6 + t*s, t*0.5 + float(i)*7.0));
          }
          band = smoothstep(-0.3, 0.6, band);

          float fil = cnoise(vec3(uv.x*9.0, uv.y*5.0 + t*1.2, t*0.9));
          fil = smoothstep(0.45, 0.52, fil);
          fil = pow(fil, 3.0);

          vec3 col = mix(u_bg, mix(u_c1, u_c2, band), u_mix);
          col += fil * u_filament;

          vec2 p = (vUv - 0.5) * vec2(u_aspect, 1.0);
          float r = length(p);
          float feather = smoothstep(0.68, 0.40, r);
          float vignette = smoothstep(0.98, 0.8, 1.0 - r);
          float alpha = feather * vignette * 0.95;

          gl_FragColor = vec4(col, alpha);
          if (gl_FragColor.a < 0.02) discard;
        }
      `,
      transparent: true,
      depthWrite: false,
      depthTest: true,
      blending: THREE.NormalBlending,
    });

    const laminarPlane = new THREE.Mesh(new THREE.PlaneGeometry(160, 110), laminarMat);
    laminarPlane.position.z = -40;
    scene.add(laminarPlane);

    /* ===== Caustic Light Sheet (slightly stronger than last) ===== */
    const causticUniforms = {
      u_time: { value: 0 },
      u_alpha: { value: 0.28 }, // 0.22 -> 0.28 to read better
    };
    const causticMat = new THREE.ShaderMaterial({
      uniforms: causticUniforms,
      vertexShader: `
        varying vec2 vUv;
        void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }
      `,
      fragmentShader: `
        ${GLSL_NOISE}
        uniform float u_time;
        uniform float u_alpha;
        varying vec2 vUv;

        float bandLayer(vec2 uv, float t, float scale, float speed){
          float n = cnoise(vec3(uv*scale, t*speed));
          n = abs(n);
          n = smoothstep(0.55, 0.85, n);
          return n;
        }

        void main(){
          vec2 uv = vUv;
          float t = u_time;

          float b1 = bandLayer(uv + vec2(0.03*t, 0.0), t, 6.0, 0.25);
          float b2 = bandLayer(uv + vec2(-0.02*t, 0.01*t), t, 10.5, 0.35);
          float b3 = bandLayer(uv + vec2(0.0, -0.015*t), t, 14.0, 0.45);

          float caustics = (b1*0.6 + b2*0.8 + b3*1.0);
          caustics = pow(caustics, 1.6);

          gl_FragColor = vec4(vec3(caustics), u_alpha);
          if(gl_FragColor.a < 0.02) discard;
        }
      `,
      transparent: true,
      depthWrite: false,
      depthTest: false,
      blending: THREE.AdditiveBlending,
    });
    const causticPlane = new THREE.Mesh(new THREE.PlaneGeometry(160, 110), causticMat);
    causticPlane.position.z = -5.0;
    scene.add(causticPlane);

    /* ===== Particles (body + glints) ===== */
    const makeParticleLayer = (count: number, additive = false) => {
      const geo = new THREE.BufferGeometry();
      const pos = new Float32Array(count * 3);
      const col = new Float32Array(count * 3);
      const size = new Float32Array(count);
      const rand = new Float32Array(count);

      for (let i = 0; i < count; i++) {
        const r = TUNE.sphereRadius * Math.cbrt(Math.random());
        const theta = Math.random() * Math.PI * 2.0;
        const phi = Math.acos(2 * Math.random() - 1);
        pos[i*3+0] = r * Math.sin(phi) * Math.cos(theta);
        pos[i*3+1] = r * Math.sin(phi) * Math.sin(theta);
        pos[i*3+2] = r * Math.cos(phi);

        // sunrise bias: ecoGreen 45%, yellow 35%, white 20%
        const roll = Math.random();
        const c = roll < 0.45 ? COLORS.ecoGreen : roll < 0.80 ? COLORS.solarYellow : COLORS.sleekWhite;
        col[i*3+0] = c.r; col[i*3+1] = c.g; col[i*3+2] = c.b;

        size[i] = additive ? 1.0 + Math.random() * 1.0 : 1.2 + Math.random() * 2.2;
        rand[i] = Math.random() * 100.0;
      }

      geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
      geo.setAttribute("color", new THREE.BufferAttribute(col, 3));
      geo.setAttribute("a_size", new THREE.BufferAttribute(size, 1));
      geo.setAttribute("a_rand", new THREE.BufferAttribute(rand, 1));

      const uniforms = { u_time: { value: 0 }, u_mouse: { value: new THREE.Vector2(0, 0) } };

      const mat = new THREE.ShaderMaterial({
        uniforms,
        vertexShader: `
          ${GLSL_NOISE}
          uniform float u_time;
          uniform vec2  u_mouse;
          attribute float a_size, a_rand;
          attribute vec3  color;
          varying vec3 vColor;
          varying float vGlow;
          void main(){
            vColor = color;
            vec3 p = position;
            vec3 v = curl(p * ${TUNE.noiseScale.toFixed(3)} + vec3(u_time*${TUNE.flowSpeed.toFixed(3)}));
            p += v * 2.0;
            float s = a_size * (0.85 + 0.15 * sin(u_time*1.5 + a_rand));
            vec3 m = vec3(u_mouse.x*24.0, u_mouse.y*16.0, 10.0);
            float md = length((modelViewMatrix*vec4(p,1.0)).xyz - (modelViewMatrix*vec4(m,1.0)).xyz);
            vGlow = smoothstep(12.0, 0.0, md);
            vec4 mv = modelViewMatrix * vec4(p, 1.0);
            gl_PointSize = s * (300.0 / -mv.z);
            gl_Position = projectionMatrix * mv;
          }
        `,
        fragmentShader: `
          varying vec3 vColor; varying float vGlow;
          void main(){
            float d = length(gl_PointCoord - vec2(0.5));
            float alpha = smoothstep(0.57, 0.0, d);
            alpha = pow(alpha, 1.32);
            alpha += vGlow * 0.22; // a touch brighter than previous
            if(alpha < 0.02) discard;
            gl_FragColor = vec4(vColor, alpha);
          }
        `,
        transparent: true,
        depthWrite: false,
        depthTest: true,
        blending: additive ? THREE.AdditiveBlending : THREE.NormalBlending,
      });

      return { points: new THREE.Points(geo, mat), uniforms, geo, mat };
    };

    const body = makeParticleLayer(TUNE.particleCount, false);
    const glints = makeParticleLayer(TUNE.glintCount, true);
    scene.add(body.points);
    scene.add(glints.points);

    /* ===== Mycelial Weave (soft but present) ===== */
    const weaveGeo = new THREE.BufferGeometry();
    const linePos = new Float32Array(TUNE.lineCount * 2 * 3);
    const seed = new Float32Array(TUNE.lineCount);
    const particlePositions = (body.geo.getAttribute("position") as THREE.BufferAttribute).array as Float32Array;

    for (let i = 0; i < TUNE.lineCount; i++) {
      const i1 = (Math.random() * TUNE.particleCount) | 0;
      const i2 = (Math.random() * TUNE.particleCount) | 0;
      const a = i * 6;
      linePos[a+0] = particlePositions[i1*3+0];
      linePos[a+1] = particlePositions[i1*3+1];
      linePos[a+2] = particlePositions[i1*3+2];
      linePos[a+3] = particlePositions[i2*3+0];
      linePos[a+4] = particlePositions[i2*3+1];
      linePos[a+5] = particlePositions[i2*3+2];
      seed[i] = Math.random() * Math.PI * 2;
    }
    weaveGeo.setAttribute("position", new THREE.BufferAttribute(linePos, 3));
    weaveGeo.setAttribute("a_seed", new THREE.BufferAttribute(seed, 1));

    const weaveUniforms = {
      u_time: { value: 0 },
      u_cA: { value: COLORS.ecoGreen.clone() },
      u_cB: { value: COLORS.solarYellow.clone() },
      u_baseAlpha: { value: 0.22 }, // a hair stronger than last
      u_pulseAdd: { value: 0.13 },
    };

    const weaveMat = new THREE.ShaderMaterial({
      uniforms: weaveUniforms,
      vertexShader: `
        ${GLSL_NOISE}
        uniform float u_time;
        attribute float a_seed;
        varying float vPhase;
        varying float vDepth;
        void main(){
          vec3 p = position;
          vec3 v = curl(p * ${TUNE.noiseScale.toFixed(3)} + vec3(u_time*${TUNE.flowSpeed.toFixed(3)}));
          p += v * 1.6;
          vDepth = clamp((p.z + ${TUNE.sphereRadius.toFixed(1)}) / (${(TUNE.sphereRadius*2).toFixed(1)}), 0.0, 1.0);
          vPhase = a_seed;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0);
        }
      `,
      fragmentShader: `
        uniform float u_time;
        uniform vec3  u_cA, u_cB;
        uniform float u_baseAlpha, u_pulseAdd;
        varying float vPhase, vDepth;
        void main(){
          float alpha = u_baseAlpha + (0.07*(1.0 - vDepth));
          float pulse = 0.5 + 0.5 * sin(u_time*${(2.2*TUNE.pulseSpeed).toFixed(2)} + vPhase);
          pulse = pow(pulse, 3.0);
          alpha += pulse * u_pulseAdd;
          vec3 col = mix(u_cA, u_cB, vDepth);
          gl_FragColor = vec4(col, alpha);
          if (gl_FragColor.a < 0.03) discard;
        }
      `,
      transparent: true,
      depthTest: true,
      depthWrite: false,
      blending: THREE.NormalBlending,
    });

    const weave = new THREE.LineSegments(weaveGeo, weaveMat);
    scene.add(weave);

    /* ===== Tendrils (hero, glowing) ===== */
    const tendrils = createTendrils(scene, COLORS.ecoGreen, COLORS.solarYellow);

    /* Resize */
    const onResize = () => {
      const w = mount.clientWidth;
      const h = mount.clientHeight;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
      composer.setSize(w, h);
      laminarUniforms.u_aspect.value = w / h;
    };
    window.addEventListener("resize", onResize);

    /* Animate */
    const loop = (tms: number) => {
      raf.current = requestAnimationFrame(loop);
      const t = tms * 0.001;

      laminarUniforms.u_time.value = t;
      laminarUniforms.u_mouse.value.lerp(mouse, 0.12);

      causticUniforms.u_time.value = t;

      body.uniforms.u_time.value = t;
      body.uniforms.u_mouse.value.lerp(mouse, 0.15);

      glints.uniforms.u_time.value = t;
      glints.uniforms.u_mouse.value.lerp(mouse, 0.15);

      weaveUniforms.u_time.value = t;
      tendrils.uniforms.u_time.value = t;

      // camera parallax
      camera.position.x = mouse.x * PARALLAX.camX;
      camera.position.y = mouse.y * PARALLAX.camY;
      camera.lookAt(0, 0, 0);

      composer.render();
    };
    raf.current = requestAnimationFrame(loop);

    /* Cleanup */
    return () => {
      if (raf.current) cancelAnimationFrame(raf.current);
      window.removeEventListener("resize", onResize);
      mount.removeEventListener("mousemove", onPointerMove);

      scene.traverse((obj) => {
        const m: any = (obj as any).material;
        const g: any = (obj as any).geometry;
        g?.dispose?.();
        if (m) Array.isArray(m) ? m.forEach((mm: any) => mm?.dispose?.()) : m.dispose?.();
      });
      composer.dispose();
      renderer.dispose();
      mount.removeChild(renderer.domElement);
    };
  }, []);

  return (
    <div className="relative w-full h-screen overflow-hidden">
      <div ref={mountRef} className="absolute inset-0" />
    </div>
  );
};

export default EcodiaCanvas;
