'use client';

import Script from 'next/script';
import { usePathname } from 'next/navigation';
import { useEffect, useRef } from 'react';
import { trackMetaPixelEvent } from '@/lib/metaPixel';

const pixelId = process.env.NEXT_PUBLIC_META_PIXEL_ID;
const validPixelId = pixelId && /^\d+$/.test(pixelId) ? pixelId : null;

export default function MetaPixel() {
  const pathname = usePathname();
  const initialPageViewTracked = useRef(false);

  useEffect(() => {
    if (!validPixelId) return;

    if (!initialPageViewTracked.current) {
      initialPageViewTracked.current = true;
      return;
    }

    trackMetaPixelEvent('PageView');
  }, [pathname]);

  if (!validPixelId) return null;

  return (
    <>
      <Script id="meta-pixel" strategy="afterInteractive">
        {`
          !function(f,b,e,v,n,t,s)
          {if(f.fbq)return;n=f.fbq=function(){n.callMethod?
          n.callMethod.apply(n,arguments):n.queue.push(arguments)};
          if(!f._fbq)f._fbq=n;n.push=n;n.loaded=!0;n.version='2.0';
          n.queue=[];t=b.createElement(e);t.async=!0;
          t.src=v;s=b.getElementsByTagName(e)[0];
          s.parentNode.insertBefore(t,s)}(window, document,'script',
          'https://connect.facebook.net/en_US/fbevents.js');
          fbq('init', '${validPixelId}');
          fbq('track', 'PageView');
        `}
      </Script>
      <noscript>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          alt=""
          height="1"
          width="1"
          style={{ display: 'none' }}
          src={`https://www.facebook.com/tr?id=${validPixelId}&ev=PageView&noscript=1`}
        />
      </noscript>
    </>
  );
}
