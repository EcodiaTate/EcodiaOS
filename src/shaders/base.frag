precision mediump float;

varying vec2 vUv;
uniform float uTime;
uniform float uIntensity;

float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1,311.7)))*43758.5453); }
float noise(vec2 p){
  vec2 i=floor(p), f=fract(p);
  vec2 u=f*f*(3.0-2.0*f);
  float a=hash(i), b=hash(i+vec2(1.0,0.0)), c=hash(i+vec2(0.0,1.0)), d=hash(i+vec2(1.0,1.0));
  return mix(mix(a,b,u.x), mix(c,d,u.x), u.y);
}
float fbm(vec2 p){
  float v=0.0; float a=0.5;
  for(int i=0;i<5;i++){ v+=a*noise(p); p*=2.0; a*=0.5; }
  return v;
}

void main() {
  // center & scale
  vec2 uv = (vUv * 2.0 - 1.0) * 2.0;
  float t = uTime * 0.05;

  // slow flow direction
  vec2 flow = vec2(sin(t*0.10), cos(t*0.10)) * 0.30;
  float n = fbm(uv + flow * 2.0);

  // veinlines from gradient magnitude
  float gx = dFdx(n), gy = dFdy(n);
  float grad = sqrt(gx*gx + gy*gy);
  float veins = smoothstep(0.08, 0.18, grad);

  // gentle pulsation
  float pulse = 0.5 + 0.5 * sin(t*2.0 + n*6.2831853);
  veins *= pulse;

  // teal→mint glow for light scene
  vec3 teal = vec3(0.10, 0.40, 0.30);
  vec3 mint = vec3(0.60, 1.00, 0.80);
  vec3 col = mix(teal, mint, n);

  gl_FragColor = vec4(col, veins * uIntensity);
}
