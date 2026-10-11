"use client";

import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";
import { api } from "@/lib/api";

let signupStatus: Promise<boolean> | null = null;

function loadSignupStatus(): Promise<boolean> {
  signupStatus ??= api.getSignupStatus().then(
    (status) => status.enabled,
    () => {
      // Unknown while the gateway is unreachable: assume the default (open) and ask again next time.
      signupStatus = null;
      return true;
    },
  );
  return signupStatus;
}

export function useSignupOpen(): boolean {
  const [open, setOpen] = useState(true);

  useEffect(() => {
    let active = true;
    loadSignupStatus().then((value) => {
      if (active) setOpen(value);
    });
    return () => {
      active = false;
    };
  }, []);

  return open;
}

export function SignupLink({
  className,
  children,
  hideWhenClosed = false,
}: {
  className?: string;
  children: ReactNode;
  hideWhenClosed?: boolean;
}) {
  const open = useSignupOpen();
  if (!open && hideWhenClosed) return null;

  return (
    <Link href={open ? "/signup" : "/login"} className={className}>
      {children}
    </Link>
  );
}
