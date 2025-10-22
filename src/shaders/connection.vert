precision mediump float;

attribute float progress;  // attribute here is allowed
varying float vProgress;

void main() {
  vProgress = progress; // pass progress to fragment shader
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  
}
