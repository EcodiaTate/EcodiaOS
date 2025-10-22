import { NextResponse } from 'next/server'

// This assumes your Python/FastAPI backend is running on http://localhost:8000
const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000'

export async function POST(request: Request) {
  try {
    const body = await request.json()

    // The endpoint we created in Python
    const apiRes = await fetch(`${API_URL}/voxis/profile/consent`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    })

    if (!apiRes.ok) {
      const errorBody = await apiRes.text()
      console.error('API Error:', errorBody)
      return new NextResponse(errorBody || 'An error occurred', { status: apiRes.status })
    }

    const data = await apiRes.json()
    return NextResponse.json(data)
  } catch (error: any) {
    console.error('Route handler error:', error)
    return new NextResponse('Internal Server Error', { status: 500 })
  }
}