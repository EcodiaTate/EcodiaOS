import { extend } from '@react-three/fiber'
import { Line2 } from 'three/examples/jsm/lines/Line2'
import { LineMaterial } from 'three/examples/jsm/lines/LineMaterial'
import { LineGeometry } from 'three/examples/jsm/lines/LineGeometry'

// 👇 Register these with R3F
extend({ Line2, LineMaterial, LineGeometry })
