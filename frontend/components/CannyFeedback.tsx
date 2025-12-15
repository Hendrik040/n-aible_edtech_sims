"use client";

import { useEffect } from 'react';
import { useAuth } from '@/lib/auth-context';

const CANNY_APP_ID = "68d725b9e886d512e0fc3fcc"; // From docs
const BOARD_TOKEN = "c1ab1386-9d40-8994-b046-5f985d3f768b"; // From docs

interface CannyFeedbackProps {
  className?: string;
}

export default function CannyFeedback({ className = "" }: CannyFeedbackProps) {
  const { user } = useAuth();

  useEffect(() => {
    // 1. Define the Canny function on window
    // @ts-ignore
    if (typeof window.Canny !== 'function') {
      // @ts-ignore
      window.Canny = function() {
        // @ts-ignore
        (window.Canny.q = window.Canny.q || []).push(arguments);
      };
    }

    // 2. Load the SDK if not already loaded
    if (!document.getElementById('canny-jssdk')) {
      const script = document.createElement('script');
      script.type = 'text/javascript';
      script.async = true;
      script.id = 'canny-jssdk';
      script.src = 'https://canny.io/sdk.js';
      const firstScript = document.getElementsByTagName('script')[0];
      firstScript?.parentNode?.insertBefore(script, firstScript);
    }

    // 3. Generate SSO token (Mock/Local only)
    const renderWidget = async () => {
      let ssoToken = null;
      
      if (user) {
        try {
          const response = await fetch('/api/canny-sso', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user }),
          });
          
          if (response.ok) {
            const data = await response.json();
            ssoToken = data.token;
          }
        } catch (err) {
          console.error("Error fetching Canny SSO token:", err);
        }
      }

      // 4. Render the widget
      // @ts-ignore
      window.Canny('render', {
        boardToken: BOARD_TOKEN,
        basePath: '/feedback', // Sync with our route
        ssoToken: ssoToken,
        theme: 'light', // Force light mode
      });
    };

    renderWidget();

  }, [user]);

  return (
    <div className={`w-full bg-white ${className}`}>
      <div data-canny />
    </div>
  );
}
