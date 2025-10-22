import { Material } from 'three'
export class LineMaterial extends Material {
  linewidth: number
  resolution: { x: number; y: number }
  alphaToCoverage: boolean
  dashed: boolean
}
