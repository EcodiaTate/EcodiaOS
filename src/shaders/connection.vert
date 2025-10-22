precision mediump float;

attribute float progress;
varying float vProgress;
uniform float uTime;

float hash(float x){ return fract(sin(x)*43758.5453123); }

void main() {
  vProgress = progress;
  float n = hash(progress * 157.0);
  float wob = 0.0025 * sin(uTime * 0.0005 + n * 6.2831853);
  vec3 pos = position + vec3(0.0, wob, 0.0);
  gl_Position = projectionMatrix * modelViewMatrix * vec4(pos, 1.0);
}
