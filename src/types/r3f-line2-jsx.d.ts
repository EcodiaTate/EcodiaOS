import { Line2 } from 'three/examples/jsm/lines/Line2'

declare global {
  namespace JSX {
    interface IntrinsicElements {
      line2: ReactThreeFiber.Object3DNode<Line2, typeof Line2>
      linematerial: ReactThreeFiber.Object3DNode<any, any>
      linegeometry: ReactThreeFiber.Object3DNode<any, any>
    }
  }
}
