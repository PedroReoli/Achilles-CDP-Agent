"""Erros públicos estáveis, sem detalhes sensíveis do navegador."""

from typing import Any, Dict


class ServiceError(Exception):
    def __init__(self, code: str, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable

    def as_dict(self) -> Dict[str, Any]:
        return {"code": self.code, "message": str(self), "retryable": self.retryable}
