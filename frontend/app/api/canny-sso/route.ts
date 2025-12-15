import { NextResponse } from 'next/server';
import jwt from 'jsonwebtoken';

// Use environment variable for the private key in production
const PRIVATE_KEY = process.env.CANNY_PRIVATE_KEY || "0b371500-5b84-691c-10f4-81c962c9c1cb"; 

export async function POST(request: Request) {
  try {
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

