"use client";

import { useEffect, useId } from "react";

type ModalProps = {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
};

export function Modal({ title, onClose, children }: ModalProps) {
  const titleId = useId();

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-900/40 p-4 sm:items-center">
      <div role="dialog" aria-modal="true" aria-labelledby={titleId} className="w-full max-w-2xl rounded-xl bg-white p-6 shadow-xl">
        <div className="mb-4 flex items-start justify-between gap-4">
          <h2 id={titleId} className="text-lg font-semibold text-slate-900">
            {title}
          </h2>
          <button type="button" onClick={onClose} aria-label="Cerrar" className="rounded-md px-2 text-xl leading-none text-slate-500 hover:bg-slate-100">
            ×
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
