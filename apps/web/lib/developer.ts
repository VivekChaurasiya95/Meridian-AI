/** Developer profile shown on the landing page and /developer. */

export const DEVELOPER = {
  name: "Vivek Chaurasiya",
  role: "Full-stack developer · Creator of Meridian AI",
  tagline: "I turn complex debugging into calm, evidence-backed work.",
  bio: "Vivek Chaurasiya is the developer behind Meridian AI — an AI-assisted debugging and reliability platform that turns bug reports into structured, evidence-backed investigations. He works across the whole stack, from the Next.js interface and motion design to the FastAPI backend, PostgreSQL data model, and Dockerized infrastructure.",
  photoSrc: "/developer-vivek.png",
  photoAlt: "Portrait of Vivek Chaurasiya",
  initials: "VC",
  links: {
    github: "https://github.com/VivekChaurasiya95",
    linkedin: "https://www.linkedin.com/in/vivek-chaurasiya-722037315",
    portfolio: "https://vivek-chaurasiya.vercel.app",
  },
  stack: [
    "Next.js",
    "TypeScript",
    "Tailwind CSS",
    "Framer Motion",
    "FastAPI",
    "Python",
    "PostgreSQL",
    "Docker",
    "Firebase Auth",
  ],
  highlights: [
    {
      title: "Session auth + workspaces",
      body: "First-party email/password auth with opaque sessions, workspace tenancy, and role-based membership.",
    },
    {
      title: "Social sign-in",
      body: "Google and GitHub login through Firebase, exchanged server-side for the same secure session cookie.",
    },
    {
      title: "Brand & motion system",
      body: "Editorial landing, warm light/dark themes, and restrained scroll and headline animation throughout.",
    },
  ],
} as const;
