/** The Flow Kit mark: a play glyph on an indigo gradient tile. */
export function BrandMark({ size = 28 }: { size?: number }) {
  return (
    <span
      aria-hidden
      className="relative inline-flex items-center justify-center shrink-0 rounded-[9px]"
      style={{
        width: size,
        height: size,
        background: 'linear-gradient(135deg, #a5abff 0%, #6f78f7 55%, #4a3fd1 100%)',
        boxShadow: '0 0 0 1px rgb(255 255 255 / 0.12) inset, 0 6px 18px rgb(111 120 247 / 0.35)',
      }}
    >
      <svg width={size * 0.46} height={size * 0.46} viewBox="0 0 16 16" fill="none">
        <path d="M5 3.2v9.6c0 .6.66.97 1.17.65l7.2-4.8a.77.77 0 0 0 0-1.3l-7.2-4.8A.77.77 0 0 0 5 3.2Z" fill="white" />
      </svg>
    </span>
  )
}
