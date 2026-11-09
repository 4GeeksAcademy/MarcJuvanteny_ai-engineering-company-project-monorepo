type PaginationProps = {
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
};

export function Pagination({ page, totalPages, onPageChange }: PaginationProps) {
  if (totalPages <= 1) return null;
  const buttonClass = "rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50";

  return (
    <nav aria-label="Paginación" className="mt-3 flex items-center justify-end gap-3 text-sm text-slate-600">
      <button type="button" className={buttonClass} disabled={page <= 1} onClick={() => onPageChange(page - 1)}>
        Anterior
      </button>
      <span>
        Página {page} de {totalPages}
      </span>
      <button type="button" className={buttonClass} disabled={page >= totalPages} onClick={() => onPageChange(page + 1)}>
        Siguiente
      </button>
    </nav>
  );
}
