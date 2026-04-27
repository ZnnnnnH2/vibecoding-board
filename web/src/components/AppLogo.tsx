import { useId } from 'react'

type AppLogoProps = {
  className?: string
  size?: number
  title?: string
}

export function AppLogo({
  className,
  size = 56,
  title = 'VibeCoding Board',
}: AppLogoProps) {
  const id = useId().replace(/:/g, '')
  const titleId = `${id}-title`
  const bgId = `${id}-bg`
  const panelId = `${id}-panel`
  const routeId = `${id}-route`
  const hubId = `${id}-hub`

  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 64 64"
      fill="none"
      role="img"
      aria-labelledby={titleId}
      xmlns="http://www.w3.org/2000/svg"
    >
      <title id={titleId}>{title}</title>
      <defs>
        <linearGradient id={bgId} x1="8" y1="6" x2="56" y2="58" gradientUnits="userSpaceOnUse">
          <stop stopColor="#0F172A" />
          <stop offset="0.58" stopColor="#1D4ED8" />
          <stop offset="1" stopColor="#22D3EE" />
        </linearGradient>
        <linearGradient id={panelId} x1="16" y1="12" x2="48" y2="52" gradientUnits="userSpaceOnUse">
          <stop stopColor="#0B1120" stopOpacity="0.22" />
          <stop offset="1" stopColor="#0F172A" stopOpacity="0.5" />
        </linearGradient>
        <linearGradient id={routeId} x1="22" y1="32" x2="40.5" y2="32" gradientUnits="userSpaceOnUse">
          <stop stopColor="#67E8F9" />
          <stop offset="1" stopColor="#F8FAFC" />
        </linearGradient>
        <linearGradient id={hubId} x1="42" y1="26" x2="51" y2="38" gradientUnits="userSpaceOnUse">
          <stop stopColor="#F8FAFC" stopOpacity="0.94" />
          <stop offset="1" stopColor="#BFDBFE" stopOpacity="0.92" />
        </linearGradient>
      </defs>

      <rect x="4" y="4" width="56" height="56" rx="18" fill={`url(#${bgId})`} />
      <rect x="7.5" y="7.5" width="49" height="49" rx="14.5" stroke="#E0F2FE" strokeOpacity="0.18" />
      <rect
        x="12"
        y="12"
        width="40"
        height="40"
        rx="12"
        fill={`url(#${panelId})`}
        stroke="#E0F2FE"
        strokeOpacity="0.14"
      />

      <path d="M20 20H44" stroke="#E0F2FE" strokeOpacity="0.06" strokeWidth="1.5" />
      <path d="M20 32H44" stroke="#E0F2FE" strokeOpacity="0.08" strokeWidth="1.5" />
      <path d="M20 44H44" stroke="#E0F2FE" strokeOpacity="0.06" strokeWidth="1.5" />

      <path
        d="M22 18C31.5 18 36 22 42 29"
        stroke="#BFDBFE"
        strokeOpacity="0.68"
        strokeWidth="4"
        strokeLinecap="round"
      />
      <path
        d="M22 32H40.5"
        stroke={`url(#${routeId})`}
        strokeWidth="5"
        strokeLinecap="round"
      />
      <path
        d="M22 46C31.5 46 36 42 42 35"
        stroke="#BFDBFE"
        strokeOpacity="0.68"
        strokeWidth="4"
        strokeLinecap="round"
      />

      <circle cx="18" cy="18" r="3.75" fill="#E2E8F0" fillOpacity="0.95" />
      <circle cx="18" cy="32" r="6.75" fill="#22D3EE" fillOpacity="0.18" />
      <circle cx="18" cy="32" r="4.5" fill="#67E8F9" />
      <circle cx="18" cy="46" r="3.75" fill="#E2E8F0" fillOpacity="0.95" />

      <rect
        x="40.5"
        y="25.5"
        width="12"
        height="13"
        rx="4.25"
        fill={`url(#${hubId})`}
        stroke="#F8FAFC"
        strokeOpacity="0.72"
        strokeWidth="1.5"
      />
      <path
        d="M45 29.5V34.5"
        stroke="#0F172A"
        strokeOpacity="0.82"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
      <path
        d="M48 29.5V34.5"
        stroke="#0F172A"
        strokeOpacity="0.58"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  )
}
