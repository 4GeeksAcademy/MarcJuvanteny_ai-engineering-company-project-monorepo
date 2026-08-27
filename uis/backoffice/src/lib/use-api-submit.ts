"use client";

import { useCallback, useState } from "react";

type SubmitState = {
  isSubmitting: boolean;
  errorMessage: string | null;
};

/**
 * Ciclo de vida compartido de envio para los formularios de autenticacion.
 *
 * Centraliza el flag `isSubmitting` y el banner `errorMessage`, y envuelve el
 * trabajo asincrono en un unico try/catch/finally. Cada formulario solo tiene
 * que describir la peticion; si la accion lanza, el mensaje del Error se
 * muestra en el banner. Si la accion setea un error de campo y hace `return`
 * (respuesta 4xx controlada), ese mensaje se respeta y no se limpia.
 */
export function useApiSubmit() {
  const [state, setState] = useState<SubmitState>({
    isSubmitting: false,
    errorMessage: null,
  });

  const setErrorMessage = useCallback((message: string | null) => {
    setState((current) => ({ ...current, errorMessage: message }));
  }, []);

  const submit = useCallback(async (action: () => Promise<void>) => {
    setState({ isSubmitting: true, errorMessage: null });
    try {
      await action();
      setState((current) => ({ ...current, isSubmitting: false }));
    } catch (error) {
      setState({
        isSubmitting: false,
        errorMessage:
          error instanceof Error ? error.message : "No se pudo conectar con la API.",
      });
    }
  }, []);

  return {
    isSubmitting: state.isSubmitting,
    errorMessage: state.errorMessage,
    setErrorMessage,
    submit,
  };
}
