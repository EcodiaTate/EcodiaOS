precision mediump float;

uniform float uTime;
uniform float uDuration;
uniform float uActivatedAt;
uniform vec3 uColor;
uniform float uIsCore;
uniform float uTheme;
uniform float uReverse; // ✅ new uniform

varying float vProgress;

void main() {
  float idleOpacity = mix(0.1, 0.2, uTheme); // Light-dark blend
  float opacity = idleOpacity;

  float timeFactor = mod(uTime * 0.001 + vProgress * 2.0, 2.0);
  float shimmer = 0.1 * sin(timeFactor * 6.28318);
  opacity += shimmer;

  if (uActivatedAt >= 0.0) {
    float elapsed = uTime - uActivatedAt;

    if (elapsed >= 0.0 && elapsed <= uDuration) {
      float t = elapsed / uDuration;
      float waveFront = t;
      float waveWidth = 0.2;

      // ✅ Flip direction if needed
      float v = uReverse > 0.5 ? (1.0 - vProgress) : vProgress;

      float dist = abs(v - waveFront);
      float pulse = 1.0 - smoothstep(0.0, waveWidth, dist);

      float coreBoost = 1.0 + 0.4 * uIsCore;
      opacity += pulse * coreBoost;
    }
  }

  gl_FragColor = vec4(uColor, clamp(opacity, 0.0, 1.0));
}
