import { NextResponse } from 'next/server';
import jwt from 'jsonwebtoken';

// Make CANNY_PRIVATE_KEY optional for build - will fail at runtime if used without the key
const PRIVATE_KEY = process.env.CANNY_PRIVATE_KEY;

export async function POST(request: Request) {
  try {
    // Check if CANNY_PRIVATE_KEY is set at runtime
    if (!PRIVATE_KEY) {
      return NextResponse.json({ error: 'Canny integration not configured' }, { status: 503 });
    }

    const body = await request.json();
    const { user } = body;

    if (!user || !user.email) {
      return NextResponse.json({ error: 'User data required' }, { status: 400 });
    }

    const userData = {
      email: user.email,
      id: user.id || user.email,
      name: user.full_name || user.email.split('@')[0],
      avatarURL: user.avatar_url,
    };

    const ssoToken = jwt.sign(userData, PRIVATE_KEY, { algorithm: 'HS256' });

    return NextResponse.json({ token: ssoToken });
  } catch (error) {
    console.error('Error generating Canny token:', error);
    return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 });
  }
}
