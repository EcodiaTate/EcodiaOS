import { BufferGeometry } from 'three'
export class LineGeometry extends BufferGeometry {
  setPositions(positions: number[] | Float32Array): void
  setColors(colors: number[] | Float32Array): void
}
