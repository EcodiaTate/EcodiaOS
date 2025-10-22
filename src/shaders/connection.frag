precision mediump float;

uniform float uTime;         // ms
uniform float uDuration;     // ms (reserved)
uniform float uActivatedAt;  // ms (reserved)
uniform vec3  uTint;         // small tint from app (MUST match material)
uniform float uIsHub;        // 0..1 (this edge touches a hub)
uniform float uTheme;        // 0..1 (light→dark bias)

varying float vProgress;

// Eco-solarpunk ramp
vec3 rampColor(float t) {
  vec3 mint   = vec3(0.50, 0.82, 0.58); // #7fd069
  vec3 gold   = vec3(0.96, 0.83, 0.37); // #f4d35e
  vec3 forest = vec3(0.22, 0.38, 0.26); // #396041
  vec3 a = mix(mint, gold, smoothstep(0.0, 0.55, t));
  return mix(a, forest, smoothstep(0.45, 1.0, t));
}

void main() {
  // base opacity for light scene; uTheme can darken slightly
  float base = mix(0.10, 0.22, uTheme);

  // canopy breath (very slow)
  float breath = 0.04 * sin(uTime * 0.00035 + vProgress * 6.2831853);

  // midpoint swell (cooperation gathers near center)
  float center = 0.5;
  float width  = 0.28;
  float distMid = abs(vProgress - center);
  float swell = 1.0 - smoothstep(0.0, width, distMid);

  // supportive packets drifting along the edge
  float t = uTime * 0.00015;
  float p1 = fract(t + vProgress);
  float p2 = fract(t * 0.77 + vProgress * 0.93);
  float packet1 = exp(-40.0 * pow(p1 - 0.5, 2.0));
  float packet2 = exp(-32.0 * pow(p2 - 0.5, 2.0));
  float packets = 0.08 * (packet1 + 0.7 * packet2);

  // subtly lift hub-adjacent edges
  float hubBoost = mix(1.0, 1.2, clamp(uIsHub, 0.0, 1.0));

  float opacity = (base + breath) * hubBoost;
  opacity += 0.25 * swell;
  opacity += packets;

  vec3 col = mix(rampColor(vProgress), uTint, 0.25);
  gl_FragColor = vec4(col, clamp(opacity, 0.0, 1.0));
}
