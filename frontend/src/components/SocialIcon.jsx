export function SocialIcon({ name }) {
  const paths = {
    github: (
      <path d="M9 19c-4.3 1.3-4.3-2.2-6-2.7m12 5v-3.5c0-1 .1-1.5-.5-2.2 3-.3 6-1.5 6-6A4.7 4.7 0 0 0 19.2 6c.1-.4.6-2-.2-3.7 0 0-1.1-.3-3.8 1.4a13 13 0 0 0-6.8 0C5.7 2 4.6 2.3 4.6 2.3 3.8 4 4.3 5.6 4.4 6A4.7 4.7 0 0 0 3 9.5c0 4.5 3 5.7 6 6-.5.5-.6 1.2-.5 2.2v3.6" />
    ),
    gmail: (
      <>
        <rect x="2" y="4" width="20" height="16" rx="3" />
        <path d="m3 6 9 7 9-7M3 19V9m18 10V9" />
      </>
    ),
    facebook: (
      <path d="M14 22V13h3l.5-4H14V7c0-1 .3-2 2-2h2V1.5C17 1.2 16 1 15 1c-3.1 0-5 2-5 5v3H7v4h3v9" />
    ),
    instagram: (
      <>
        <rect x="3" y="3" width="18" height="18" rx="5" />
        <circle cx="12" cy="12" r="4" />
        <circle cx="17.5" cy="6.5" r=".6" fill="currentColor" />
      </>
    ),
    linkedin: (
      <>
        <rect x="2" y="2" width="20" height="20" rx="3" />
        <path d="M6 10v8m4 0v-8m0 4c0-5 7-5 7 0v4" />
        <circle cx="6" cy="6.5" r=".6" fill="currentColor" />
      </>
    ),
  };
  return (
    <svg
      width="22"
      height="22"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name]}
    </svg>
  );
}
