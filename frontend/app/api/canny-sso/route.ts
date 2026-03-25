import { NextResponse } from 'next/server';
import jwt from 'jsonwebtoken';

// Get CANNY_PRIVATE_KEY - check at runtime, not at build time
const PRIVATE_KEY = process.env.CANNY_PRIVATE_KEY;

export async function POST(request: Request) {
  try {
    // Check for private key at runtime (not at build time)
    if (!PRIVATE_KEY) {
      console.error('CANNY_PRIVATE_KEY environment variable is required but not set');
      return NextResponse.json({ error: 'Canny SSO not configured' }, { status: 500 });
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
