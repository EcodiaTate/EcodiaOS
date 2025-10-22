'use client'
// If your react-window has VariableSizeList, we export that; otherwise fall back.
import { VariableSizeList, FixedSizeList } from 'react-window'
const Comp = (VariableSizeList as any) ?? (FixedSizeList as any)
export default Comp
