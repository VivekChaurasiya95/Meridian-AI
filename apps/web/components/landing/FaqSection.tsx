"use client";

import * as React from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { Plus } from "lucide-react";
import { Reveal } from "@/components/ui/Reveal";
import { StaggerHeadline } from "@/components/ui/AnimatedHeadline";
import { DEVELOPER } from "@/lib/developer";
import { cn } from "@/lib/cn";

interface Faq {
  question: string;
  answer: React.ReactNode;
}

const FAQS: Faq[] = [
  {
    question: "What is Meridian AI?",
    answer:
      "An AI-assisted debugging and reliability platform. It turns a bug report into a structured, evidence-backed investigation — reproduce, capture evidence, hypothesize, test, patch, verify — with a human approving every step.",
  },
  {
    question: "How is this different from asking a chatbot?",
    answer:
      "A chatbot answers from the report alone. Meridian reproduces the failure in isolation, captures linked evidence, and verifies patches with real test runs — and labels guesses as guesses, never as facts.",
  },
  {
    question: "How do I get started?",
    answer:
      "Create an account, sign in, and make your first workspace from the Overview page. You can sign in with email and password, or with Google/GitHub where offered — sessions stay valid for 24 hours of idle time.",
  },
  {
    question: "What is a workspace?",
    answer:
      "Your team's shared home in Meridian. A workspace holds projects and their investigations, and you can invite teammates by email with a role — owner, admin, developer, or viewer — so everyone sees exactly what they should.",
  },
  {
    question: "Will Meridian change my code without asking?",
    answer:
      "Never. No patch is applied, pushed, or deployed without your explicit review of the exact diff — files, lines, and risks. The model proposes; you dispose.",
  },
  {
    question: "Is my code safe during an investigation?",
    answer:
      "Yes. Your code runs in a separate, resource-limited worker — never in the main app and never on your machine. Only members of your workspace can see its projects and investigations.",
  },
  {
    question: "Is Meridian open source?",
    answer: (
      <>
        Yes — Meridian is MIT licensed. The code lives on{" "}
        <a
          href={`${DEVELOPER.links.github}/Meridian-AI`}
          target="_blank"
          rel="noreferrer"
          className="font-semibold text-sage underline decoration-sage/50 decoration-2 underline-offset-4 transition-colors hover:text-ink"
        >
          GitHub
        </a>
        .
      </>
    ),
  },
];

/**
 * One accordion row: the question is always visible; the answer expands with
 * a height animation and the row smooth-scrolls into view when opened.
 */
function FaqItem({
  faq,
  index,
  open,
  onToggle,
}: {
  faq: Faq;
  index: number;
  open: boolean;
  onToggle: () => void;
}) {
  const reduceMotion = useReducedMotion();
  const rowRef = React.useRef<HTMLDivElement>(null);
  const scrollTimer = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  const panelId = `faq-panel-${index}`;
  const buttonId = `faq-button-${index}`;

  React.useEffect(
    () => () => {
      if (scrollTimer.current) clearTimeout(scrollTimer.current);
    },
    [],
  );

  function handleToggle() {
    const willOpen = !open;
    onToggle();
    if (willOpen && !reduceMotion) {
      // Let the answer start expanding first, then ease the whole open
      // row into view — a scroll animation for this question only.
      if (scrollTimer.current) clearTimeout(scrollTimer.current);
      scrollTimer.current = setTimeout(() => {
        rowRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }, 120);
    }
  }

  return (
    <div
      ref={rowRef}
      className={cn(
        "group scroll-mt-24 border-t border-line/70 transition-colors duration-200 last:border-b",
        open ? "bg-surface-1/80" : "hover:bg-surface-1/60",
      )}
    >
      <button
        type="button"
        id={buttonId}
        aria-expanded={open}
        aria-controls={panelId}
        onClick={handleToggle}
        className="flex w-full cursor-pointer items-center gap-5 px-2 py-5 text-left outline-none focus-visible:shadow-[inset_0_0_0_2px_var(--color-sage)] sm:gap-7 sm:px-4"
      >
        <span
          aria-hidden="true"
          className={cn(
            "font-display tnum w-10 shrink-0 text-xl font-semibold transition-colors duration-200",
            open ? "text-sage" : "text-line-strong group-hover:text-sage",
          )}
        >
          {String(index + 1).padStart(2, "0")}
        </span>
        <span className="min-w-0 flex-1 text-[15px] font-semibold text-ink sm:text-base">
          {faq.question}
        </span>
        <span
          aria-hidden="true"
          className={cn(
            "flex size-8 shrink-0 items-center justify-center rounded-full border transition-all duration-300",
            open
              ? "rotate-45 border-sage/40 bg-sage-subtle text-sage"
              : "border-line text-ink-3 group-hover:border-line-strong group-hover:text-ink",
          )}
        >
          <Plus className="size-4" strokeWidth={2.5} />
        </span>
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            key="answer"
            id={panelId}
            role="region"
            aria-labelledby={buttonId}
            className="overflow-hidden"
            initial={reduceMotion ? false : { height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={reduceMotion ? undefined : { height: 0, opacity: 0 }}
            transition={{ duration: 0.32, ease: [0.16, 1, 0.3, 1] }}
          >
            <p className="max-w-2xl px-2 pb-6 pl-[4.25rem] text-[15px] leading-7 text-ink-2 sm:px-4 sm:pl-[5.25rem]">
              {faq.answer}
            </p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/** Landing FAQ: single-open accordion with animated answers. */
export function FaqSection() {
  const [openIndex, setOpenIndex] = React.useState<number | null>(0);

  return (
    <section id="faq" className="mx-auto w-full max-w-6xl scroll-mt-20 px-4 py-16 sm:px-6 md:py-24">
      <div className="grid gap-10 md:grid-cols-[0.9fr_1.1fr] md:gap-16">
        <div className="md:sticky md:top-24 md:self-start">
          <Reveal>
            <p className="flex items-center gap-3 font-mono text-xs font-medium text-sage">
              <span aria-hidden="true" className="h-px w-8 bg-sage" />
              Frequently asked
            </p>
            <h2 className="font-display mt-5 text-3xl leading-[1.1] font-semibold tracking-tight text-balance sm:text-4xl">
              <StaggerHeadline text="Questions, answered honestly." />
            </h2>
            <p className="mt-4 max-w-md text-[15px] leading-7 text-ink-2">
              The short version of what Meridian is, how to use it, and how
              it treats your code. Click a question to read the answer.
            </p>
          </Reveal>
        </div>
        <ul className="flex min-w-0 flex-col">
          {FAQS.map((faq, i) => (
            <Reveal as="li" key={faq.question} delay={Math.min(i * 0.04, 0.2)}>
              <FaqItem
                faq={faq}
                index={i}
                open={openIndex === i}
                onToggle={() => setOpenIndex((current) => (current === i ? null : i))}
              />
            </Reveal>
          ))}
        </ul>
      </div>
    </section>
  );
}
